"""Media resolver for the player.

Accepts: YouTube URLs · YouTube playlists · search words · direct media URLs
(.mp3 / .m4a / .wav / .ogg / .opus / .mp4). Returns a stream URL that FFmpeg
pipes straight into the Discord voice channel.

Public interface:
  - search(query, requester) -> list[Track]
  - resolve_stream(url)       -> str | None

Extraction goes through yt-dlp (actively maintained against YouTube's
countermeasures). Signed stream URLs expire, so resolve_stream() is called
fresh right before each track plays rather than cached from search().
"""
import asyncio
import ipaddress
import re
import socket
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import yt_dlp

_MEDIA_EXT_RE = re.compile(r"\.(mp3|m4a|wav|ogg|opus|aac|flac|mp4|webm|mkv|mov)(?:$|\?)", re.I)

# How many videos to pull off a playlist URL.
PLAYLIST_LIMIT = 50

# The VPS's datacenter IP gets YouTube's "Sign in to confirm you're not a
# bot" wall on plain requests. bgutil-ytdlp-pot-provider (already running
# locally on :4416, see ~/bgutil-pot) supplies a proof-of-origin token that
# makes some of those checks pass — it doesn't help when YouTube 429s the
# request outright, only the softer bot-check case.
_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "format": "bestaudio/best",
    "noplaylist": True,
    "skip_download": True,
    "socket_timeout": 15,
    "extractor_retries": 3,
    "geo_bypass": True,
    "extractor_args": {"youtubepot-bgutilhttp": {"base_url": ["http://127.0.0.1:4416"]}},
}


def _is_direct_media(url: str) -> bool:
    """True for direct .mp3 / .mp4 / etc. URLs — we play these as-is."""
    return bool(_MEDIA_EXT_RE.search(url))


def _is_safe_direct_url(url: str) -> bool:
    """Reject direct-media URLs pointing at loopback/private/link-local
    addresses so /play can't be used to probe the host's internal network."""
    try:
        host = urllib.parse.urlsplit(url).hostname
        if not host:
            return False
        for family, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return True
    except Exception:
        return False


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


def _best_thumbnail(info: dict) -> Optional[str]:
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = info.get("thumbnails") or []
    return thumbs[-1]["url"] if thumbs else None


def _track_from_info(info: dict, requester: str) -> Track:
    return Track(
        title=info.get("title") or "YouTube audio",
        url=info.get("webpage_url") or info.get("original_url") or info.get("url"),
        duration=info.get("duration"),
        thumbnail=_best_thumbnail(info),
        uploader=info.get("uploader") or info.get("channel") or "",
        requester=requester,
    )


# --------------------------------------------------------------------------- #
#  Blocking work (always called via run_in_executor)
# --------------------------------------------------------------------------- #
def _search_blocking(query: str, requester: str) -> list[Track]:
    query = query.strip()
    is_url = query.startswith(("http://", "https://"))

    if is_url and _is_direct_media(query):
        if not _is_safe_direct_url(query):
            return []
        name = urllib.parse.unquote(query.rsplit("/", 1)[-1].split("?")[0])
        return [Track(title=name or "Audio", url=query, duration=None,
                      thumbnail=None, uploader=None, requester=requester)]

    # A playlist URL with no specific video -> expand the whole list.
    if is_url and "list=" in query and "v=" not in query and "youtu.be/" not in query:
        opts = dict(_YDL_OPTS, noplaylist=False, extract_flat="in_playlist",
                    playlistend=PLAYLIST_LIMIT)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
        tracks = []
        for e in (info.get("entries") or [])[:PLAYLIST_LIMIT]:
            if not e or not e.get("id"):
                continue
            tracks.append(Track(
                title=e.get("title") or "YouTube audio",
                url=f"https://www.youtube.com/watch?v={e['id']}",
                duration=e.get("duration"),
                thumbnail=_best_thumbnail(e),
                uploader=e.get("uploader") or e.get("channel") or "",
                requester=requester,
            ))
        return tracks

    target = query if is_url else f"ytsearch1:{query}"
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        info = ydl.extract_info(target, download=False)
    if info and info.get("entries"):
        entries = [e for e in info["entries"] if e]
        info = entries[0] if entries else None
    if not info:
        return []
    return [_track_from_info(info, requester)]


def _resolve_blocking(url: str) -> Optional[str]:
    if _is_direct_media(url):
        return url if _is_safe_direct_url(url) else None
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        info = ydl.extract_info(url, download=False)
    return info.get("url") if info else None


# --------------------------------------------------------------------------- #
#  Public async interface
# --------------------------------------------------------------------------- #
async def search(query: str, requester: str) -> list[Track]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _search_blocking, query, requester)


async def resolve_stream(url: str) -> Optional[str]:
    """Return a playable URL for FFmpeg. Raises on extraction failure so the
    caller can surface a real error instead of a generic 'no audio' message."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _resolve_blocking, url)
