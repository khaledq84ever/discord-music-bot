"""Cookie-free YouTube audio resolver for the player.

YouTube blocks datacenter IPs ("Sign in to confirm you're not a bot"), so
yt-dlp / Invidious / Piped all fail from Railway. Instead we use the
v3.y2mate.nu → iotacloud.org pipeline, which runs the extraction from a
non-blocked IP and hands back a signed direct **MP3** URL that FFmpeg streams
straight into the voice channel — no account, no cookies, no download to disk.

Public interface (unchanged, so player.py/bot.py don't care how it works):
  - search(query, requester) -> list[Track]   (a URL, a playlist, or words)
  - resolve_stream(url)       -> str | None    (fresh signed MP3 URL, at play time)
"""
import asyncio
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_VID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")

# How many videos to pull off a playlist URL.
PLAYLIST_LIMIT = 50


@dataclass
class Track:
    title: str
    url: str                 # canonical watch URL; stream re-resolved at play time
    duration: Optional[int]
    thumbnail: Optional[str]
    uploader: Optional[str]
    requester: str

    @property
    def duration_str(self) -> str:
        if not self.duration:
            return "—"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _video_id(url: str) -> Optional[str]:
    m = _VID_RE.search(url)
    return m.group(1) if m else None


def _watch_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


# --------------------------------------------------------------------------- #
#  HTTP helpers (blocking; always called via run_in_executor)
# --------------------------------------------------------------------------- #
def _get(url: str, headers: dict, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _oembed(vid: str) -> dict:
    """Title / uploader / thumbnail — instant, never bot-checked."""
    try:
        u = urllib.parse.quote(_watch_url(vid), safe="")
        body = _get(f"https://www.youtube.com/oembed?url={u}&format=json",
                    {"User-Agent": _UA, "Accept": "application/json"}, timeout=8)
        d = json.loads(body)
        return {
            "title": d.get("title") or "YouTube audio",
            "uploader": d.get("author_name") or "",
            "thumbnail": d.get("thumbnail_url")
            or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        }
    except Exception:
        return {"title": "YouTube audio", "uploader": "",
                "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}


def _iotacloud_mp3(vid: str) -> Optional[tuple[str, str]]:
    """Run the y2mate→iotacloud pipeline. Returns (mp3_url, title) or None.

    The signed URL embeds an expiry, so we resolve it fresh at play time and
    hand it straight to FFmpeg (don't cache it).
    """
    hdr = {"User-Agent": _UA,
           "Origin": "https://v3.y2mate.nu",
           "Referer": "https://v3.y2mate.nu/"}
    # Priming the y2mate page kicks off the backend conversion (and used to be
    # where a data-key lived — no longer required). Failure here is non-fatal.
    try:
        _get(f"https://v3.y2mate.nu/mp3/{vid}/", {"User-Agent": _UA}, timeout=15)
    except Exception:
        pass

    for r in range(1, 8):
        try:
            body = _get(f"https://iotacloud.org/api/?r={r}&v={vid}&_={int(time.time())}",
                        hdr, timeout=20)
        except Exception:
            return None
        try:
            d = json.loads(body)
        except Exception:
            return None
        if d.get("url"):
            return d["url"], (d.get("title") or "")
        if d.get("progress") in ("error", None) and not d.get("url"):
            if d.get("progress") == "error":
                return None
        time.sleep(4)
    return None


def _scrape_first_video_id(query: str) -> Optional[str]:
    """Resolve search words → first videoId via the public results page
    (no API key, no login). Best-effort; YouTube may rate-limit."""
    try:
        q = urllib.parse.quote(query)
        body = _get(f"https://www.youtube.com/results?search_query={q}",
                    {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
                    timeout=12).decode("utf-8", "ignore")
    except Exception:
        return None
    m = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', body)
    return m.group(1) if m else None


def _scrape_playlist_ids(url: str) -> list[str]:
    """Pull the first PLAYLIST_LIMIT unique videoIds from a playlist URL."""
    try:
        body = _get(url, {"User-Agent": _UA,
                          "Accept-Language": "en-US,en;q=0.9"},
                    timeout=15).decode("utf-8", "ignore")
    except Exception:
        return []
    seen, ids = set(), []
    for m in re.finditer(r'"videoId":"([A-Za-z0-9_-]{11})"', body):
        v = m.group(1)
        if v not in seen:
            seen.add(v)
            ids.append(v)
            if len(ids) >= PLAYLIST_LIMIT:
                break
    return ids


def _track_from_id(vid: str, requester: str) -> Track:
    meta = _oembed(vid)
    return Track(title=meta["title"], url=_watch_url(vid), duration=None,
                 thumbnail=meta["thumbnail"], uploader=meta["uploader"],
                 requester=requester)


# --------------------------------------------------------------------------- #
#  Public async interface
# --------------------------------------------------------------------------- #
async def search(query: str, requester: str) -> list[Track]:
    loop = asyncio.get_running_loop()
    query = query.strip()
    is_url = query.startswith(("http://", "https://"))

    if is_url:
        # A playlist URL with no specific video -> expand the whole list.
        if "list=" in query and "v=" not in query and "youtu.be/" not in query:
            ids = await loop.run_in_executor(None, _scrape_playlist_ids, query)
            return [await loop.run_in_executor(None, _track_from_id, v, requester)
                    for v in ids]
        vid = _video_id(query)
        if not vid:
            return []
        return [await loop.run_in_executor(None, _track_from_id, vid, requester)]

    # Plain search words.
    vid = await loop.run_in_executor(None, _scrape_first_video_id, query)
    if not vid:
        return []
    return [await loop.run_in_executor(None, _track_from_id, vid, requester)]


async def resolve_stream(url: str) -> Optional[str]:
    """Fresh signed MP3 URL for FFmpeg, resolved at play time."""
    vid = _video_id(url)
    if not vid:
        return None
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, _iotacloud_mp3, vid)
    return res[0] if res else None
