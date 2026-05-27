"""Stress test: 10 different YouTube videos resolve in a row + a real playlist.

Picks a varied set — short / long, music / talk, English / Arabic — and reports
timing per case so we can see if any one hangs the player loop.
"""
import asyncio
import statistics
import sys
import time
import urllib.request

import ytdl


VIDEOS = [
    ("first ever video (19s)",   "https://www.youtube.com/watch?v=jNQXAC9IVRw"),
    ("Rick Astley (3m)",         "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("PSY Gangnam Style",        "https://www.youtube.com/watch?v=9bZkp7q19f0"),
    ("Despacito",                "https://www.youtube.com/watch?v=kJQP7kiw5Fk"),
    ("Shape of You",             "https://www.youtube.com/watch?v=JGwWNGJdvx8"),
    ("Bohemian Rhapsody",        "https://www.youtube.com/watch?v=fJ9rUzIMcZQ"),
    ("Arabic search — Fairouz",  "فيروز كفى يا قلب"),
    ("English search — Beatles", "the beatles here comes the sun"),
    ("Lo-Fi long stream-ish",    "https://www.youtube.com/watch?v=5qap5aO4i9A"),
    ("youtu.be short link",      "https://youtu.be/L_jWHffIx5E"),
]

PLAYLIST = "https://www.youtube.com/playlist?list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj"  # Billie Eilish official


def _head(url: str) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            ct = r.headers.get("Content-Type", "")
            cl = r.headers.get("Content-Length", "0")
            mb = float(cl) / (1024 * 1024) if cl.isdigit() else 0
            ok = ("audio" in ct or "octet" in ct) and r.status == 200
            return ok, f"{ct} · {mb:.1f} MB"
    except Exception as e:
        return False, f"HEAD failed: {e}"


async def run_video(i: int, label: str, query: str) -> tuple[bool, float]:
    t0 = time.time()
    try:
        tracks = await ytdl.search(query, "loop10")
        if not tracks:
            print(f"  [{i:>2}] ❌ no results — {label}")
            return False, time.time() - t0
        stream = await ytdl.resolve_stream(tracks[0].url)
    except Exception as e:
        print(f"  [{i:>2}] 💥 exception — {label}: {e}")
        return False, time.time() - t0
    elapsed = time.time() - t0
    if not stream:
        print(f"  [{i:>2}] ❌ no stream — {label}  ({elapsed:.1f}s)")
        return False, elapsed
    ok, info = _head(stream)
    mark = "✅" if ok else "⚠️ "
    print(f"  [{i:>2}] {mark} {label:<32} · {elapsed:>4.1f}s · {tracks[0].title[:40]:<40} · {info}")
    return ok, elapsed


async def main() -> int:
    print("=" * 78)
    print("  LOOP-10 stress: 10 videos (varied) + 1 playlist")
    print("=" * 78)
    results = []
    timings = []
    for i, (label, q) in enumerate(VIDEOS, 1):
        ok, elapsed = await run_video(i, label, q)
        results.append((label, ok))
        timings.append(elapsed)

    print("\n  -- playlist --")
    t0 = time.time()
    try:
        pl = await ytdl.search(PLAYLIST, "loop10")
    except Exception as e:
        pl = []
        print(f"  💥 playlist exception: {e}")
    elapsed = time.time() - t0
    if pl:
        print(f"  ✅ playlist returned {len(pl)} tracks in {elapsed:.1f}s")
        print(f"      first three: {[t.title[:30] for t in pl[:3]]}")
        pl_ok = len(pl) >= 5
    else:
        print(f"  ❌ playlist returned 0 tracks in {elapsed:.1f}s")
        pl_ok = False

    passed = sum(1 for _, ok in results if ok)
    print()
    print("=" * 78)
    print(f"  Videos: {passed}/{len(VIDEOS)} passed")
    if timings:
        print(f"  Resolve time: min={min(timings):.1f}s  "
              f"max={max(timings):.1f}s  "
              f"median={statistics.median(timings):.1f}s  "
              f"avg={sum(timings)/len(timings):.1f}s")
    print(f"  Playlist: {'PASS' if pl_ok else 'FAIL'}")
    print("=" * 78)
    return 0 if (passed == len(VIDEOS) and pl_ok) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
