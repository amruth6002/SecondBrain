"""YouTube transcript extraction service using yt-dlp."""

import json
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


def extract_transcript(youtube_url: str) -> str:
    """Extract transcript text from a YouTube video using yt-dlp.

    Uses yt-dlp to fetch subtitles (manual or auto-generated) and parses
    the json3 subtitle format to extract plain text.

    Args:
        youtube_url: Full YouTube URL

    Returns:
        Full transcript as a single string
    """
    video_id = extract_youtube_id(youtube_url)

    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
    except Exception as e:
        raise ValueError(
            f"Could not fetch video info for {video_id}. Error: {e}"
        )

    # Prefer manual subs, fall back to auto-generated
    subs = info.get("subtitles", {})
    auto_subs = info.get("automatic_captions", {})

    en_subs = None
    for lang in ["en", "en-US", "en-GB"]:
        en_subs = subs.get(lang) or auto_subs.get(lang)
        if en_subs:
            break

    if not en_subs:
        raise ValueError(
            f"No English subtitles found for video {video_id}. "
            "The video may not have captions."
        )

    # Find the json3 format URL for structured parsing
    json3_url = None
    srt_url = None
    vtt_url = None
    for fmt in en_subs:
        if fmt["ext"] == "json3":
            json3_url = fmt["url"]
        elif fmt["ext"] == "srt":
            srt_url = fmt["url"]
        elif fmt["ext"] == "vtt":
            vtt_url = fmt["url"]

    if json3_url:
        return _parse_json3(json3_url, video_id)
    elif srt_url:
        return _parse_text_subs(srt_url, video_id)
    elif vtt_url:
        return _parse_text_subs(vtt_url, video_id)
    else:
        raise ValueError(
            f"No parseable subtitle format found for video {video_id}."
        )


def _parse_json3(url: str, video_id: str) -> str:
    """Parse json3 subtitle format into plain text."""
    try:
        resp = urllib.request.urlopen(url, timeout=30)
        data = json.loads(resp.read())
    except Exception as e:
        raise ValueError(
            f"Failed to download subtitles for {video_id}. Error: {e}"
        )

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
        raise ValueError(
            f"Failed to download subtitles for {video_id}. Error: {e}"
        )

    # Strip timestamps and formatting, keep text lines
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        # Skip blank lines, sequence numbers, timestamps
        if not line:
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"[\d:.,\-\s>]+$", line):
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        # Strip HTML tags
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)

    full_text = " ".join(lines)
    if not full_text.strip():
        raise ValueError(f"Transcript for video {video_id} was empty.")
    return full_text
