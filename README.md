# 🎵 YouTube Music Bot for Discord (Arabic-first)

شغّل أي أغنية من يوتيوب داخل الروم الصوتي — بحث، طابور، تحكّم كامل.
Stream any YouTube audio into a Discord voice channel — search, queue, full controls.

## Features / المميزات
- **`/play`** a URL **or** search words — joins your voice channel and queues it.
- Full controls: **skip · pause · resume · queue · nowplaying · volume · loop · shuffle · stop · leave**.
- Per-server queue, live **now-playing** embeds, auto-leave when idle/alone.
- Playlists supported (paste a playlist URL).
- Streams (never downloads) via **yt-dlp + FFmpeg**.

## 1. Discord setup
1. https://discord.com/developers/applications → **New Application**.
2. **Bot** tab → **Reset Token** → copy into `DISCORD_TOKEN`.
3. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`;
   permissions: *View Channels, Send Messages, Embed Links, Connect, Speak*.
   Open the generated URL to invite it. (No privileged intents needed.)

## 2. Run locally
```bash
pip install -r requirements.txt   # needs FFmpeg installed on your system
cp .env.example .env              # fill in DISCORD_TOKEN
python3 bot.py
```

## 3. Deploy on Railway
```bash
railway init
railway up
```
The included `Dockerfile` installs FFmpeg automatically. Set `DISCORD_TOKEN`
in the Variables tab.

> **Heads-up:** on datacenter IPs (Railway/most clouds) YouTube often returns
> *"Sign in to confirm you're not a bot."* Export a `cookies.txt` from a
> logged-in browser and point `COOKIES_FILE` at it to fix playback.

## Usage / الاستخدام
1. Join a voice channel.
2. `/play <رابط يوتيوب أو بحث>` — and it starts.
3. `/queue`, `/skip`, `/volume`, `/loop`, `/shuffle`, `/stop` as you like.
