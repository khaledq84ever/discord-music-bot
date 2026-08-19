"""Simple media-player bot for Discord — slash commands, per-guild queue.
Plays YouTube links, search words, playlists, and direct media URLs.
"""
import asyncio
import logging

import discord
from discord import app_commands

import config
import ytdl
from player import MusicManager, MusicControls

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("music")

# Voice + slash commands need no privileged intents.
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)
manager = MusicManager(bot)

# on_ready fires on every gateway reconnect, not just the first login — guard
# so command sync (a REST call subject to Discord's rate limits) runs once.
_synced = False


@bot.event
async def on_ready():
    global _synced
    if not _synced:
        if config.DEV_GUILD_ID:
            g = discord.Object(id=int(config.DEV_GUILD_ID))
            tree.copy_global_to(guild=g)
            await tree.sync(guild=g)
            log.info("Synced commands instantly to dev guild %s", config.DEV_GUILD_ID)
        await tree.sync()
        _synced = True
    log.info("Logged in as %s — in %d server(s).", bot.user, len(bot.guilds))


@tree.error
async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Safety net: without this, an unhandled error (e.g. a voice-connect
    timeout) leaves the interaction hanging with no response at all."""
    log.exception("command error", exc_info=error)
    msg = "⚠️ صار خطأ غير متوقع / an unexpected error occurred."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass


@bot.event
async def on_voice_state_update(member, before, after):
    """Leave automatically when the bot is left alone in a voice channel."""
    if member.bot:
        return
    vc = member.guild.voice_client
    if vc and vc.channel and len([m for m in vc.channel.members if not m.bot]) == 0:
        player = manager.find(member.guild.id)
        if player:
            await player.disconnect(reason="alone")


async def _ensure_voice(interaction: discord.Interaction):
    """Connect the bot to the caller's voice channel. Returns (player, error)."""
    user = interaction.user
    if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
        return None, "ادخل روم صوتي أول / join a voice channel first."
    channel = user.voice.channel
    vc = interaction.guild.voice_client
    try:
        if vc is None:
            await channel.connect()
        elif vc.channel.id != channel.id:
            await vc.move_to(channel)
    except (discord.ClientException, asyncio.TimeoutError) as e:
        return None, f"تعذّر الاتصال / can't connect: {e}"
    return manager.get(interaction.guild, interaction.channel), None


# --------------------------------------------------------------------------- #
#  Slash commands
# --------------------------------------------------------------------------- #
@tree.command(name="play", description="شغّل من يوتيوب أو سبوتيفاي (رابط أو بحث) / Play from YouTube or Spotify (URL or search)")
@app_commands.describe(query="رابط يوتيوب/سبوتيفاي أو كلمات بحث / a YouTube/Spotify URL or search words")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    player, err = await _ensure_voice(interaction)
    if err:
        return await interaction.followup.send(f"🔇 {err}")
    try:
        tracks = await ytdl.search(query, interaction.user.display_name)
    except Exception as e:
        return await interaction.followup.send(f"⚠️ خطأ في البحث / search failed: `{e}`")
    if not tracks:
        return await interaction.followup.send("🔍 ماحصلت نتيجة / no results.")

    for t in tracks:
        player.add(t)

    if len(tracks) == 1:
        t = tracks[0]
        pos = len(player.tracks)
        embed = discord.Embed(
            title="➕ أُضيف للطابور / Added to queue",
            description=f"**[{t.title}]({t.display_url})** · `{t.duration_str}`",
            color=0xD4A843,
        )
        if pos > 0 and player.current:
            embed.set_footer(text=f"مكانه في الطابور / position #{pos}")
        if t.thumbnail:
            embed.set_thumbnail(url=t.thumbnail)
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(
            f"➕ أضفت **{len(tracks)}** مقطع للطابور / queued **{len(tracks)}** tracks.")


@tree.command(name="skip", description="تخطَّ المقطع الحالي / Skip the current track")
async def skip(interaction: discord.Interaction):
    player = manager.find(interaction.guild_id)
    if not player or not player.current:
        return await interaction.response.send_message("ماكو شي يشتغل / nothing playing.", ephemeral=True)
    title = player.current.title
    player.skip()
    await interaction.response.send_message(f"⏭️ تخطّيت / skipped **{title}**")


@tree.command(name="pause", description="إيقاف مؤقت / Pause")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ توقف مؤقت / paused.")
    else:
        await interaction.response.send_message("ماكو شي يشتغل / nothing playing.", ephemeral=True)


@tree.command(name="resume", description="استئناف / Resume")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ استئناف / resumed.")
    else:
        await interaction.response.send_message("مو متوقف / not paused.", ephemeral=True)


@tree.command(name="stop", description="إيقاف ومسح الطابور والخروج / Stop, clear queue & leave")
async def stop(interaction: discord.Interaction):
    player = manager.find(interaction.guild_id)
    if not player:
        return await interaction.response.send_message("مو متصل / not connected.", ephemeral=True)
    await player.disconnect(reason="stop command")
    await interaction.response.send_message("⏹️ وقفت وطلعت / stopped & left.")


@tree.command(name="queue", description="اعرض الطابور / Show the queue")
async def queue_cmd(interaction: discord.Interaction):
    player = manager.find(interaction.guild_id)
    if not player or (not player.current and not player.tracks):
        return await interaction.response.send_message("📭 الطابور فاضي / queue is empty.", ephemeral=True)
    lines = []
    if player.current:
        lines.append(f"🎶 **يشتغل الآن / now:** [{player.current.title}]({player.current.display_url})")
    upcoming = list(player.tracks)[:10]
    for i, t in enumerate(upcoming, 1):
        lines.append(f"`{i}.` [{t.title}]({t.display_url}) · `{t.duration_str}`")
    extra = len(player.tracks) - len(upcoming)
    if extra > 0:
        lines.append(f"… و **{extra}** غيرها / and {extra} more")
    embed = discord.Embed(title="📜 الطابور / Queue",
                          description="\n".join(lines), color=0xE8001C)
    if player.loop_one:
        embed.set_footer(text="🔂 التكرار مفعّل / loop on")
    await interaction.response.send_message(embed=embed)


@tree.command(name="nowplaying", description="المقطع الحالي / What's playing now")
async def nowplaying(interaction: discord.Interaction):
    player = manager.find(interaction.guild_id)
    if not player or not player.current:
        return await interaction.response.send_message("ماكو شي يشتغل / nothing playing.", ephemeral=True)
    await interaction.response.send_message(embed=player._now_playing_embed(player.current))


@tree.command(name="volume", description="غيّر الصوت 0-200 / Set volume 0-200%")
@app_commands.describe(percent="0 إلى 200 / 0 to 200")
async def volume(interaction: discord.Interaction, percent: app_commands.Range[int, 0, 200]):
    player = manager.find(interaction.guild_id)
    if not player:
        return await interaction.response.send_message("مو متصل / not connected.", ephemeral=True)
    player.set_volume(percent / 100)
    await interaction.response.send_message(f"🔊 الصوت / volume: **{percent}%**")


@tree.command(name="loop", description="كرّر المقطع الحالي / Toggle repeat of the current track")
async def loop_cmd(interaction: discord.Interaction):
    player = manager.find(interaction.guild_id)
    if not player:
        return await interaction.response.send_message("مو متصل / not connected.", ephemeral=True)
    player.loop_one = not player.loop_one
    state = "🔂 مفعّل / on" if player.loop_one else "➡️ متوقف / off"
    await interaction.response.send_message(f"التكرار / loop: {state}")


@tree.command(name="shuffle", description="اخلط الطابور / Shuffle the queue")
async def shuffle(interaction: discord.Interaction):
    player = manager.find(interaction.guild_id)
    if not player or len(player.tracks) < 2:
        return await interaction.response.send_message("الطابور قصير / queue too short.", ephemeral=True)
    import random
    random.shuffle(player.tracks)
    await interaction.response.send_message("🔀 خلطت الطابور / shuffled.")


@tree.command(name="leave", description="اخرج من الروم الصوتي / Leave the voice channel")
async def leave(interaction: discord.Interaction):
    player = manager.find(interaction.guild_id)
    if player:
        await player.disconnect(reason="leave command")
    elif interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect(force=True)
    await interaction.response.send_message("👋 طلعت / left.")


@tree.command(name="help", description="الأوامر / Commands")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎵 Music Bot — الأوامر / Commands",
        description=(
            "**/play** `<رابط يوتيوب/سبوتيفاي أو بحث>` — شغّل أو أضف للطابور، يدعم قوائم تشغيل سبوتيفاي / "
            "play or queue — supports Spotify playlists\n"
            "**/skip** — تخطَّ / skip\n"
            "**/pause** · **/resume** — إيقاف/استئناف / pause·resume\n"
            "**/queue** — الطابور / the queue\n"
            "**/nowplaying** — المقطع الحالي / now playing\n"
            "**/volume** `<0-200>` — الصوت / volume\n"
            "**/loop** — كرّر الحالي / repeat current\n"
            "**/shuffle** — اخلط / shuffle\n"
            "**/stop** — وقف واخرج / stop & leave\n"
            "**/leave** — اخرج / leave"
        ),
        color=0xE8001C,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set — see .env.example")
    bot.run(config.DISCORD_TOKEN)
