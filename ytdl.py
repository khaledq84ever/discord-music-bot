"""Media resolver for the player.

Accepts: YouTube URLs · YouTube playlists · search words · direct media URLs
(.mp3 / .m4a / .wav / .ogg / .opus / .mp4) · Spotify track/album/playlist
links. Returns a stream URL that FFmpeg pipes straight into the Discord
voice channel.

Public interface:
  - search(query, requester) -> list[Track]
  - resolve_stream(url)       -> str | None

Extraction goes through yt-dlp (actively maintained against YouTube's
countermeasures). Signed stream URLs expire, so resolve_stream() is called
fresh right before each track plays rather than cached from search().

Spotify has no yt-dlp extractor (DRM — it never serves the audio itself).
A Spotify link is instead resolved to track titles via Spotify's own public
embed page (no auth needed), and each title is turned into a lazy
"ytsearch1:<title> <artist>" pseudo-URL that yt-dlp resolves to real YouTube
audio the moment it's about to play — same as any other search-based track,
just queued ahead of time from the Spotify tracklist.
"""
import asyncio
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

import yt_dlp

_MEDIA_EXT_RE = re.compile(r"\.(mp3|m4a|wav|ogg|opus|aac|flac|mp4|webm|mkv|mov)(?:$|\?)", re.I)
_SPOTIFY_RE = re.compile(
    r"open\.spotify\.com/(?:intl-\w+/)?(track|album|playlist|episode|artist|show|user)/([A-Za-z0-9]+)"
)

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
    url: str                 # canonical watch URL, or a lazy "ytsearch1:..."
                              # query for Spotify-sourced tracks; stream is
                              # re-resolved from this at play time either way
    duration: Optional[int]
    thumbnail: Optional[str]
    uploader: Optional[str]
    requester: str
    source_url: Optional[str] = None  # real page link, when url is a lazy query

    @property
    def display_url(self) -> str:
        """The link to show the user — the Spotify track page when url is a
        lazy YouTube search query, otherwise the same as url."""
        return self.source_url or self.url

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


def _spotify_embed_entity(kind: str, sid: str) -> dict:
    """Spotify's embed page (open.spotify.com/embed/<kind>/<id>) ships the
    full track/album/playlist data as JSON in a __NEXT_DATA__ script tag —
    public, no auth, no API key. This is not a documented API and could
    break if Spotify reshapes the embed page."""
    req = urllib.request.Request(
        f"https://open.spotify.com/embed/{kind}/{sid}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        html = r.read().decode("utf-8", "replace")
    m = re.search(r'__NEXT_DATA__"\s*type="application/json">(.*?)</script>', html)
    if not m:
        raise ValueError("Spotify didn't return track data")
    data = json.loads(m.group(1))
    entity = (data.get("props", {}).get("pageProps", {})
              .get("state", {}).get("data", {}).get("entity"))
    if not entity:
        raise ValueError("Spotify link not found or private")
    return entity


def _spotify_cover(entity: dict) -> Optional[str]:
    cover = entity.get("coverArt")
    if cover and cover.get("sources"):
        return cover["sources"][-1].get("url")
    images = (entity.get("visualIdentity") or {}).get("image") or []
    if images:
        return max(images, key=lambda i: i.get("maxWidth") or 0).get("url")
    return None


def _spotify_tracks(url: str, requester: str) -> list["Track"]:
    m = _SPOTIFY_RE.search(url)
    if not m:
        return []
    kind, sid = m.group(1), m.group(2)
    if kind not in ("track", "album", "playlist"):
        raise ValueError(
            "بس روابط مقطع/ألبوم/قائمة تشغيل من سبوتيفاي / "
            "only Spotify track, album or playlist links are supported"
        )

    entity = _spotify_embed_entity(kind, sid)
    cover = _spotify_cover(entity)

    if kind == "track":
        title = entity.get("name") or "Spotify track"
        artists = ", ".join(a["name"] for a in (entity.get("artists") or []) if a.get("name"))
        query = f"{title} {artists}".strip()
        return [Track(
            title=f"{title} — {artists}" if artists else title,
            url=f"ytsearch1:{query}",
            duration=(entity.get("duration") or 0) // 1000 or None,
            thumbnail=cover,
            uploader=artists,
            requester=requester,
            source_url=f"https://open.spotify.com/track/{sid}",
        )]

    # album / playlist: the embed page caps at ~50 tracks — same as our own
    # PLAYLIST_LIMIT, so no extra truncation logic needed.
    tracks = []
    for t in (entity.get("trackList") or [])[:PLAYLIST_LIMIT]:
        title = t.get("title") or "Spotify track"
        artists = t.get("subtitle") or ""
        tid = (t.get("uri") or "").rsplit(":", 1)[-1]
        tracks.append(Track(
            title=f"{title} — {artists}" if artists else title,
            url=f"ytsearch1:{title} {artists}".strip(),
            duration=(t.get("duration") or 0) // 1000 or None,
            thumbnail=cover,
            uploader=artists,
            requester=requester,
            source_url=f"https://open.spotify.com/track/{tid}" if tid else None,
        ))
    return tracks


# --------------------------------------------------------------------------- #
#  Blocking work (always called via run_in_executor)
# --------------------------------------------------------------------------- #
def _search_blocking(query: str, requester: str) -> list[Track]:
    query = query.strip()
    is_url = query.startswith(("http://", "https://"))

    if is_url and "open.spotify.com" in query:
        return _spotify_tracks(query, requester)

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
    # A lazy "ytsearch1:..." query (Spotify-sourced tracks) comes back as a
    # one-entry playlist result rather than a single video's info dict.
    if info and info.get("entries"):
        entries = [e for e in info["entries"] if e]
        info = entries[0] if entries else None
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
