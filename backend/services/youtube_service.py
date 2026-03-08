"""YouTube transcript extraction service.

Strategies tried in order:
1. youtube-transcript-api (lightweight, no auth needed if IP isn't blocked)
2. Direct page scrape + timedtext URL extraction (fallback)
3. yt-dlp with browser cookies (local dev with Firefox/Chrome)
4. yt-dlp with cookies file (YOUTUBE_COOKIES_FILE env var, for deployment)
5. yt-dlp plain (no auth)
"""

import html as html_module
import json
import os
import re
import urllib.request

import requests
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi


def extract_youtube_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    patterns = [
        r'(?:youtube\.com/watch\?v=)([\w-]+)',
        r'(?:youtu\.be/)([\w-]+)',
        r'(?:youtube\.com/embed/)([\w-]+)',
        r'(?:youtube\.com/v/)([\w-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_transcript(youtube_url: str) -> str:
    """Extract transcript from a YouTube video using multiple fallback strategies."""
    video_id = extract_youtube_id(youtube_url)
    errors: list[str] = []

    # ── Strategy 1: youtube-transcript-api (fastest, works on many IPs) ──
    try:
        text = _strategy_yt_transcript_api(video_id)
        if text:
            print(f"[YT] Success with youtube-transcript-api")
            return text
    except Exception as e:
        errors.append(f"transcript-api: {e}")

    # ── Strategy 2: Direct page scrape → extract caption URL ──
    try:
        text = _strategy_page_scrape(video_id)
        if text:
            print(f"[YT] Success with page scrape")
            return text
    except Exception as e:
        errors.append(f"page-scrape: {e}")

    # ── Strategy 3+: yt-dlp with various cookie sources ──
    for label, opts in _build_ytdlp_strategies():
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
            text = _extract_subs_from_ytdlp_info(info, video_id)
            if text:
                print(f"[YT] Success with {label}")
                return text
        except Exception as e:
            err_str = str(e).lower()
            # Don't log expected browser-not-found noise
            if "cookie" not in err_str and "browser" not in err_str:
                errors.append(f"{label}: {e}")

    raise ValueError(
        f"Could not get transcript for video {video_id}. "
        f"Tried {2 + len(_build_ytdlp_strategies())} strategies. "
        f"Errors: {'; '.join(errors[-3:])}"  # Last 3 errors
    )


# ---------------------------------------------------------------------------
# Strategy 1: youtube-transcript-api
# ---------------------------------------------------------------------------

def _strategy_yt_transcript_api(video_id: str) -> str | None:
    ytt = YouTubeTranscriptApi()
    # Try specific languages, then any
    for langs in [["en"], ["en-US"], ["en-GB"], None]:
        try:
            if langs:
                transcript = ytt.fetch(video_id, languages=langs)
            else:
                transcript = ytt.fetch(video_id)
            text = " ".join(snippet.text for snippet in transcript)
            if text.strip():
                return text
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Strategy 2: Direct page scrape
# ---------------------------------------------------------------------------

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _strategy_page_scrape(video_id: str) -> str | None:
    """Fetch the YouTube watch page, extract caption track URL, fetch captions."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": _BROWSER_UA,
        "Accept-Language": "en-US,en;q=0.9",
    })

    resp = session.get(
        f"https://www.youtube.com/watch?v={video_id}",
        timeout=20,
    )
    resp.raise_for_status()

    # Extract ytInitialPlayerResponse JSON
    match = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\});\s*var", resp.text)
    if not match:
        match = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\});", resp.text)
    if not match:
        return None

    player = json.loads(match.group(1))
    captions = player.get("captions", {})
    renderer = captions.get("playerCaptionsTracklistRenderer", {})
    tracks = renderer.get("captionTracks", [])

    if not tracks:
        return None

    # Find English track
    en_track = None
    for t in tracks:
        if t.get("languageCode", "").startswith("en"):
            en_track = t
            break
    if not en_track:
        en_track = tracks[0]  # Fall back to first available

    caption_url = en_track.get("baseUrl", "")
    if not caption_url:
        return None

    # Fetch as srv1 XML (most reliable format)
    cap_resp = session.get(caption_url, timeout=15)
    if cap_resp.status_code != 200 or not cap_resp.text.strip():
        # Try with &fmt=json3
        cap_resp = session.get(caption_url + "&fmt=json3", timeout=15)
        if cap_resp.status_code == 200 and cap_resp.text.strip():
            try:
                return _parse_json3_text(cap_resp.text, video_id)
            except Exception:
                pass
        return None

    # Parse XML captions
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(cap_resp.text)
        texts = []
        for elem in root.findall(".//text"):
            if elem.text:
                texts.append(html_module.unescape(elem.text))
        text = " ".join(texts)
        return text if text.strip() else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Strategy 3+: yt-dlp variants
# ---------------------------------------------------------------------------

def _build_ytdlp_strategies() -> list[tuple[str, dict]]:
    base = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "quiet": True,
        "no_warnings": True,
    }
    strategies: list[tuple[str, dict]] = []

    # Browser cookies (local dev)
    for browser in ("firefox", "chrome", "chromium"):
        opts = {**base, "cookiesfrombrowser": (browser,)}
        strategies.append((f"yt-dlp + {browser} cookies", opts))

    # Cookies file (server / Docker)
    cookies_file = os.environ.get("YOUTUBE_COOKIES_FILE", "")
    if cookies_file and os.path.isfile(cookies_file):
        opts = {**base, "cookiefile": cookies_file}
        strategies.append(("yt-dlp + cookies file", opts))

    # Plain (no auth)
    strategies.append(("yt-dlp (no auth)", dict(base)))
    return strategies


def _extract_subs_from_ytdlp_info(info: dict, video_id: str) -> str | None:
    subs = info.get("subtitles", {})
    auto_subs = info.get("automatic_captions", {})

    en_subs = None
    for lang in ("en", "en-US", "en-GB"):
        en_subs = subs.get(lang) or auto_subs.get(lang)
        if en_subs:
            break
    if not en_subs:
        return None

    urls_by_format: dict[str, str] = {}
    for fmt in en_subs:
        urls_by_format[fmt["ext"]] = fmt["url"]

    for ext in ("json3", "srt", "vtt"):
        url = urls_by_format.get(ext)
        if not url:
            continue
        if ext == "json3":
            return _parse_json3_url(url, video_id)
        else:
            return _parse_text_subs_url(url, video_id)
    return None


# ---------------------------------------------------------------------------
# Subtitle parsers
# ---------------------------------------------------------------------------

def _parse_json3_text(raw: str, video_id: str) -> str:
    data = json.loads(raw)
    events = data.get("events", [])
    texts = []
    for event in events:
        for seg in event.get("segs", []):
            text = seg.get("utf8", "").strip()
            if text and text != "\n":
                texts.append(text)
    full = " ".join(texts)
    if not full.strip():
        raise ValueError(f"Transcript for video {video_id} was empty.")
    return full


def _parse_json3_url(url: str, video_id: str) -> str:
    resp = urllib.request.urlopen(url, timeout=30)
    return _parse_json3_text(resp.read().decode("utf-8"), video_id)


def _parse_text_subs_url(url: str, video_id: str) -> str:
    resp = urllib.request.urlopen(url, timeout=30)
    raw = resp.read().decode("utf-8")

    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"[\d:.,\-\s>]+$", line):
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)

    full = " ".join(lines)
    if not full.strip():
        raise ValueError(f"Transcript for video {video_id} was empty.")
    return full
