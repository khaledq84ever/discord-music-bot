"""End-to-end test for the cookie-free YouTube resolver.

Exercises search() + resolve_stream() across every link shape the bot must
handle.  Prints PASS/FAIL with the exact reason, never raises.

Run:  .venv/bin/python test_links.py
"""
import asyncio
import sys
import time
import urllib.request

import ytdl

# Use ASCII fallbacks if the terminal can't render the emoji.
_PASS = "✅ PASS"
_FAIL = "❌ FAIL"
_INFO = "  •"


CASES = [
    # (label, query, expectation)
    ("watch?v= URL",           "https://www.youtube.com/watch?v=jNQXAC9IVRw",  "track"),
    ("youtu.be short link",    "https://youtu.be/jNQXAC9IVRw",                  "track"),
    ("URL with extra params",  "https://www.youtube.com/watch?v=jNQXAC9IVRw&list=PL0123&t=10s&si=ab", "track"),
    ("plain search words",     "first video on youtube",                        "track"),
    ("playlist URL",           "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf", "many"),
    ("private/removed video",  "https://www.youtube.com/watch?v=aaaaaaaaaaa",   "graceful"),
    ("invalid URL",            "https://example.com/foo",                       "none"),
]


def _stream_is_real(url: str) -> str:
    """HEAD the resolved URL and report content-type + length so we can prove
    the MP3 actually exists, not just that the API returned a URL."""
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            ct = r.headers.get("Content-Type", "?")
            cl = r.headers.get("Content-Length", "?")
            return f"HTTP {r.status}, Content-Type={ct}, Content-Length={cl}"
    except Exception as e:
        return f"HEAD failed: {e}"


async def run_case(label: str, query: str, expect: str) -> bool:
    print(f"\n--- {label} ---")
    print(f"  query: {query!r}  (expect={expect})")
    t0 = time.time()
    try:
        tracks = await ytdl.search(query, "tester")
    except Exception as e:
        print(f"{_FAIL}  search() raised: {e}")
        return False
    elapsed = time.time() - t0
    print(f"{_INFO} search() returned {len(tracks)} track(s) in {elapsed:.1f}s")

    if expect == "none":
        if not tracks:
            print(f"{_PASS}  no results, as expected")
            return True
        print(f"{_FAIL}  expected empty, got {len(tracks)}")
        return False

    if expect == "graceful":
        # Either empty results OR a non-resolving stream is acceptable here —
        # the contract is "no exception, no silent hang".
        if not tracks:
            print(f"{_PASS}  no results (graceful)")
            return True
        # Try resolving — should return None within the iotacloud retry window.
        t0 = time.time()
        stream = await ytdl.resolve_stream(tracks[0].url)
        print(f"{_INFO} resolve_stream() returned {stream!r} in {time.time()-t0:.1f}s")
        if stream is None:
            print(f"{_PASS}  resolver returned None (graceful)")
            return True
        print(f"{_FAIL}  expected None or empty, got a URL — unexpected")
        return False

    if expect == "many":
        if len(tracks) >= 2:
            print(f"{_PASS}  got {len(tracks)} tracks from playlist")
            print(f"{_INFO} first: {tracks[0].title!r}")
            return True
        print(f"{_FAIL}  playlist resolved {len(tracks)} tracks (need >=2)")
        return False

    # expect == "track" — must get exactly one valid track AND a stream URL.
    if not tracks:
        print(f"{_FAIL}  no tracks returned")
        return False
    t = tracks[0]
    print(f"{_INFO} title:    {t.title!r}")
    print(f"{_INFO} uploader: {t.uploader!r}")
    print(f"{_INFO} url:      {t.url}")
    t0 = time.time()
    try:
        stream = await ytdl.resolve_stream(t.url)
    except Exception as e:
        print(f"{_FAIL}  resolve_stream() raised: {e}")
        return False
    elapsed = time.time() - t0
    print(f"{_INFO} resolve_stream() done in {elapsed:.1f}s")
    if not stream:
        print(f"{_FAIL}  resolver returned no URL (datacenter blocked?)")
        return False
    print(f"{_INFO} stream:   {stream[:90]}{'...' if len(stream) > 90 else ''}")
    head = _stream_is_real(stream)
    print(f"{_INFO} HEAD:     {head}")
    if "audio" in head or "octet-stream" in head:
        print(f"{_PASS}")
        return True
    print(f"{_FAIL}  HEAD didn't look like audio")
    return False


async def main() -> int:
    print("=" * 60)
    print("Cookie-free YouTube resolver — link test matrix")
    print("=" * 60)
    results = []
    for label, query, expect in CASES:
        ok = await run_case(label, query, expect)
        results.append((label, ok))

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    for label, ok in results:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}]  {label}")
    print(f"\n  {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
