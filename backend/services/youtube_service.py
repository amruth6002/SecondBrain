"""YouTube transcript extraction service."""

import re
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


def extract_transcript(youtube_url: str) -> str:
    """Extract transcript text from a YouTube video.

    Args:
        youtube_url: Full YouTube URL

    Returns:
        Full transcript as a single string
    """
    video_id = extract_youtube_id(youtube_url)
    ytt = YouTubeTranscriptApi()

    # Try multiple language codes — videos may have en, en-US, en-GB etc.
    lang_attempts = [
        ['en'],
        ['en-US'],
        ['en-GB'],
        ['en', 'en-US', 'en-GB'],
    ]

    last_error = None
    for langs in lang_attempts:
        try:
            transcript = ytt.fetch(video_id, languages=langs)
            full_text = " ".join(snippet.text for snippet in transcript)
            return full_text
        except Exception as e:
            last_error = e
            continue

    # Last resort — try without specifying language (gets default)
    try:
        transcript = ytt.fetch(video_id)
        full_text = " ".join(snippet.text for snippet in transcript)
        return full_text
    except Exception as e:
        raise ValueError(
            f"Could not get transcript for video {video_id}. "
            f"The video may not have captions. Error: {str(last_error or e)}"
        )
