"""Per-guild playback: a queue + a background loop that streams each track
through FFmpeg, plus a manager that holds one player per guild.
"""
import asyncio
import collections
import logging
import random

import discord

import config
import ytdl

log = logging.getLogger("music.player")


def _in_same_voice(interaction: discord.Interaction, player: "GuildPlayer") -> bool:
    """Only members in the bot's current voice channel can drive the buttons."""
    u = interaction.user
    if not isinstance(u, discord.Member) or not u.voice or not u.voice.channel:
        return False
    vc = player.voice
    return bool(vc and vc.channel and vc.channel.id == u.voice.channel.id)


class MusicControls(discord.ui.View):
    """Buttons attached to the now-playing message."""

    def __init__(self, player: "GuildPlayer"):
        super().__init__(timeout=None)  # persist for the life of the track
        self.player = player

    async def _gate(self, interaction: discord.Interaction) -> bool:
        if not _in_same_voice(interaction, self.player):
            await interaction.response.send_message(
                "🔇 ادخل نفس الروم الصوتي / join the same voice channel first.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        if not await self._gate(interaction):
            return
        vc = self.player.voice
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ توقف / paused.", ephemeral=True)
        elif vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ استئناف / resumed.", ephemeral=True)
        else:
            await interaction.response.send_message("ماكو شي يشتغل / nothing playing.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        if not await self._gate(interaction):
            return
        if not self.player.current:
            return await interaction.response.send_message("ماكو شي يشتغل / nothing playing.", ephemeral=True)
        title = self.player.current.title
        self.player.skip()
        await interaction.response.send_message(f"⏭️ تخطّيت / skipped **{title}**", ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def loop(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        if not await self._gate(interaction):
            return
        self.player.loop_one = not self.player.loop_one
        state = "🔂 مفعّل / on" if self.player.loop_one else "➡️ متوقف / off"
        await interaction.response.send_message(f"التكرار / loop: {state}", ephemeral=True)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary)
    async def shuffle(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        if not await self._gate(interaction):
            return
        if len(self.player.tracks) < 2:
            return await interaction.response.send_message("الطابور قصير / queue too short.", ephemeral=True)
        random.shuffle(self.player.tracks)
        await interaction.response.send_message("🔀 خلطت / shuffled.", ephemeral=True)

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.primary)
    async def queue_btn(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        if not await self._gate(interaction):
            return
        if not self.player.current and not self.player.tracks:
            return await interaction.response.send_message("📭 الطابور فاضي / queue is empty.", ephemeral=True)
        lines = []
        if self.player.current:
            lines.append(f"🎶 **الآن / now:** [{self.player.current.title}]({self.player.current.url})")
        for i, t in enumerate(list(self.player.tracks)[:10], 1):
            lines.append(f"`{i}.` [{t.title}]({t.url})")
        extra = max(0, len(self.player.tracks) - 10)
        if extra:
            lines.append(f"… و **{extra}** غيرها / and {extra} more")
        e = discord.Embed(title="📜 الطابور / Queue",
                          description="\n".join(lines), color=0xE8001C)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        if not await self._gate(interaction):
            return
        await self.player.disconnect(reason="button stop")
        await interaction.response.send_message("⏹️ وقفت وطلعت / stopped & left.", ephemeral=True)

# Reconnect flags keep the stream alive across brief network hiccups; -vn drops
# any video track so FFmpeg only pushes audio.
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class GuildPlayer:
    def __init__(self, bot, guild, text_channel, manager):
        self.bot = bot
        self.guild = guild
        self.text_channel = text_channel
        self.manager = manager
        self.tracks: collections.deque[ytdl.Track] = collections.deque()
        self.current: ytdl.Track | None = None
        self.volume = config.DEFAULT_VOLUME
        self.loop_one = False
        self._source: discord.PCMVolumeTransformer | None = None
        self._next = asyncio.Event()
        self._wakeup = asyncio.Event()
        self._task = bot.loop.create_task(self._run())

    # --- queue mutation --------------------------------------------------- #
    def add(self, track: ytdl.Track):
        self.tracks.append(track)
        self._wakeup.set()

    @property
    def voice(self) -> discord.VoiceClient | None:
        return self.guild.voice_client

    def _after(self, error):
        if error:
            log.warning("playback error: %s", error)
        self.bot.loop.call_soon_threadsafe(self._next.set)

    # --- the playback loop ------------------------------------------------ #
    async def _run(self):
        while True:
            self._next.clear()

            if not self.tracks:
                self._wakeup.clear()
                try:
                    await asyncio.wait_for(self._wakeup.wait(),
                                           timeout=config.IDLE_TIMEOUT)
                except asyncio.TimeoutError:
                    return await self.disconnect(reason="idle")
                continue

            track = self.tracks.popleft()
            try:
                stream = await ytdl.resolve_stream(track.url)
            except Exception as e:  # extraction can fail (geo/age/removed)
                await self._say(f"⚠️ تعذّر التشغيل / couldn't play "
                                f"**{track.title}** — `{e}`")
                continue
            if not stream:
                await self._say(f"⚠️ ماقدرت أجيب الصوت / no audio for "
                                f"**{track.title}**")
                continue

            vc = self.voice
            if not vc or not vc.is_connected():
                return await self.disconnect(reason="disconnected")

            self._source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(stream, **FFMPEG_OPTIONS),
                volume=self.volume)
            self.current = track
            vc.play(self._source, after=self._after)
            await self._say(embed=self._now_playing_embed(track),
                            view=MusicControls(self))

            await self._next.wait()
            if self.loop_one and self.current:
                self.tracks.appendleft(self.current)
            self.current = None
            self._source = None

    # --- helpers ---------------------------------------------------------- #
    async def _say(self, content=None, *, embed=None, view=None):
        if self.text_channel:
            try:
                await self.text_channel.send(content, embed=embed, view=view)
            except discord.HTTPException:
                pass

    def _now_playing_embed(self, t: ytdl.Track) -> discord.Embed:
        e = discord.Embed(
            title="🎶 يشتغل الآن / Now Playing",
            description=f"**[{t.title}]({t.url})**",
            color=0xE8001C,
        )
        if t.uploader:
            e.add_field(name="القناة / Channel", value=t.uploader, inline=True)
        e.add_field(name="المدة / Length", value=t.duration_str, inline=True)
        e.add_field(name="طلبها / Requested by", value=t.requester, inline=True)
        if self.loop_one:
            e.set_footer(text="🔂 التكرار مفعّل / loop on")
        if t.thumbnail:
            e.set_thumbnail(url=t.thumbnail)
        return e

    def set_volume(self, vol: float):
        self.volume = max(0.0, min(vol, 2.0))
        if self._source:
            self._source.volume = self.volume

    def skip(self):
        if self.voice and (self.voice.is_playing() or self.voice.is_paused()):
            self.voice.stop()  # triggers _after -> advances the loop

    async def disconnect(self, reason="stop"):
        self.tracks.clear()
        self.current = None
        if self.voice:
            try:
                await self.voice.disconnect(force=True)
            except Exception:
                pass
        if not self._task.done():
            self._task.cancel()
        self.manager.players.pop(self.guild.id, None)
        log.info("player for guild %s torn down (%s)", self.guild.id, reason)


class MusicManager:
    def __init__(self, bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    def get(self, guild, text_channel=None) -> GuildPlayer:
        p = self.players.get(guild.id)
        if p is None:
            p = GuildPlayer(self.bot, guild, text_channel, self)
            self.players[guild.id] = p
        elif text_channel is not None:
            p.text_channel = text_channel
        return p

    def find(self, guild_id: int) -> GuildPlayer | None:
        return self.players.get(guild_id)
