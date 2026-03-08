"""YouTube transcript extraction service using yt-dlp.

Strategies tried in order:
1. yt-dlp with browser cookies (Firefox → Chrome)
2. yt-dlp with cookies file (YOUTUBE_COOKIES_FILE env var, for deployment)
3. yt-dlp plain (no auth — works when IP isn't flagged)
"""

import json
import os
import re
import urllib.request

import yt_dlp


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
# Strategy helpers
# ---------------------------------------------------------------------------

def _base_opts() -> dict:
    return {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "quiet": True,
        "no_warnings": True,
    }


def _build_strategies() -> list[tuple[str, dict]]:
    """Return a list of (label, ydl_opts) to try in order."""
    strategies: list[tuple[str, dict]] = []

    # 1. Browser cookies (local dev)
    for browser in ("firefox", "chrome", "chromium", "brave", "edge"):
        opts = _base_opts()
        opts["cookiesfrombrowser"] = (browser,)
        strategies.append((f"yt-dlp + {browser} cookies", opts))

    # 2. Cookies file (server / CI / Azure)
    cookies_file = os.environ.get("YOUTUBE_COOKIES_FILE", "")
    if cookies_file and os.path.isfile(cookies_file):
        opts = _base_opts()
        opts["cookiefile"] = cookies_file
        strategies.append(("yt-dlp + cookies file", opts))

    # 3. Plain (no auth)
    strategies.append(("yt-dlp (no auth)", _base_opts()))

    return strategies


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_transcript(youtube_url: str) -> str:
    """Extract transcript text from a YouTube video.

    Tries multiple yt-dlp strategies (browser cookies → cookies file → plain).

    Args:
        youtube_url: Full YouTube URL

    Returns:
        Full transcript as a single string
    """
    video_id = extract_youtube_id(youtube_url)
    strategies = _build_strategies()
    last_error = None

    for label, opts in strategies:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)

            transcript = _extract_subs_from_info(info, video_id)
            if transcript:
                print(f"[YT] Success with strategy: {label}")
                return transcript
        except Exception as e:
            last_error = e
            # Don't spam logs for expected browser-not-found failures
            if "cookie" not in str(e).lower() and "browser" not in str(e).lower():
                print(f"[YT] Strategy '{label}' failed: {e}")
            continue

    raise ValueError(
        f"Could not get transcript for video {video_id}. "
        f"YouTube is blocking requests — try logging into YouTube in Firefox or Chrome "
        f"on this machine so cookies can be used. Last error: {last_error}"
    )


def _extract_subs_from_info(info: dict, video_id: str) -> str | None:
    """Given yt-dlp info dict, find and download English subtitles."""
    subs = info.get("subtitles", {})
    auto_subs = info.get("automatic_captions", {})

    en_subs = None
    for lang in ("en", "en-US", "en-GB"):
        en_subs = subs.get(lang) or auto_subs.get(lang)
        if en_subs:
            break

    if not en_subs:
        return None

    # Pick best format: json3 > srt > vtt
    urls_by_format: dict[str, str] = {}
    for fmt in en_subs:
        urls_by_format[fmt["ext"]] = fmt["url"]

    for ext in ("json3", "srt", "vtt"):
        url = urls_by_format.get(ext)
        if not url:
            continue
        if ext == "json3":
            return _parse_json3(url, video_id)
        else:
            return _parse_text_subs(url, video_id)

    return None


# ---------------------------------------------------------------------------
# Subtitle parsers
# ---------------------------------------------------------------------------

def _parse_json3(url: str, video_id: str) -> str:
    """Parse json3 subtitle format into plain text."""
    try:
        resp = urllib.request.urlopen(url, timeout=30)
        data = json.loads(resp.read())
    except Exception as e:
        raise ValueError(f"Failed to download subtitles for {video_id}. Error: {e}")

    events = data.get("events", [])
    texts = []
    for event in events:
        for seg in event.get("segs", []):
            text = seg.get("utf8", "").strip()
            if text and text != "\n":
                texts.append(text)

    full_text = " ".join(texts)
    if not full_text.strip():
        raise ValueError(f"Transcript for video {video_id} was empty.")
    return full_text


def _parse_text_subs(url: str, video_id: str) -> str:
    """Parse SRT/VTT subtitle format into plain text (fallback)."""
    try:
        resp = urllib.request.urlopen(url, timeout=30)
        raw = resp.read().decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to download subtitles for {video_id}. Error: {e}")

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

    full_text = " ".join(lines)
    if not full_text.strip():
        raise ValueError(f"Transcript for video {video_id} was empty.")
    return full_text
