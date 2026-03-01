"""Podcast RSS feed import — download and transcribe recent episodes.

Parses an RSS feed to find audio enclosures, downloads the most recent
episodes, transcribes them via Whisper, and returns Markdown suitable
for PPKE ingestion.

Requires ``feedparser`` (installed with ``pip install feedparser``).
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Maximum episode duration we'll attempt to transcribe (seconds)
_MAX_DURATION_SECONDS = 7200  # 2 hours


def _parse_duration(duration_str: str) -> int | None:
    """Parse iTunes-style duration string to seconds. Returns None on failure."""
    if not duration_str:
        return None
    parts = duration_str.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(parts[0])
    except (ValueError, IndexError):
        return None


def parse_feed(feed_url: str, max_episodes: int = 3) -> dict[str, Any]:
    """Parse a podcast RSS feed and return metadata + episode list.

    Returns
    -------
    dict with keys:
        - ``title``: Podcast title
        - ``author``: Podcast author / owner
        - ``description``: Podcast description
        - ``episodes``: list of dicts with ``title``, ``url``, ``duration``, ``published``
    """
    try:
        import feedparser
    except ImportError:
        raise ImportError(
            "Podcast RSS import requires feedparser. "
            "Install with: pip install feedparser"
        )

    feed = feedparser.parse(feed_url)
    if feed.bozo and not feed.entries:
        raise ValueError(f"Failed to parse RSS feed: {feed.bozo_exception}")

    podcast_title = feed.feed.get("title", "Unknown Podcast")
    podcast_author = feed.feed.get("author", feed.feed.get("itunes_author", "Unknown"))
    podcast_desc = feed.feed.get("subtitle", feed.feed.get("summary", ""))

    episodes: list[dict[str, Any]] = []
    for entry in feed.entries[:max_episodes]:
        audio_url = None
        # Look for audio enclosure
        for link in entry.get("enclosures", []) + entry.get("links", []):
            href = link.get("href", "")
            mtype = link.get("type", "")
            if "audio" in mtype or href.endswith((".mp3", ".m4a", ".ogg", ".wav")):
                audio_url = href
                break

        if not audio_url:
            continue

        duration_str = entry.get("itunes_duration", "")
        duration_secs = _parse_duration(duration_str)

        episodes.append({
            "title": entry.get("title", "Untitled Episode"),
            "url": audio_url,
            "duration": duration_str,
            "duration_seconds": duration_secs,
            "published": entry.get("published", ""),
            "summary": (entry.get("summary", "") or "")[:500],
        })

    return {
        "title": podcast_title,
        "author": podcast_author,
        "description": podcast_desc[:500],
        "episodes": episodes,
    }


def download_and_transcribe(
    episode_url: str,
    episode_title: str = "Episode",
    podcast_title: str = "Podcast",
    podcast_author: str = "Unknown",
) -> str:
    """Download a podcast episode and transcribe it to Markdown.

    Returns
    -------
    str
        Markdown document with podcast metadata header + timestamped transcript.
    """
    import urllib.request

    # Determine file extension from URL
    ext = ".mp3"
    for candidate in (".m4a", ".ogg", ".wav", ".mp4"):
        if candidate in episode_url.lower():
            ext = candidate
            break

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = Path(tmpdir) / f"episode{ext}"
        logger.info("Downloading episode: %s", episode_url[:120])

        # Download with a 60s timeout
        req = urllib.request.Request(
            episode_url,
            headers={"User-Agent": "PPKE/2.0 (podcast importer)"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio_path.write_bytes(resp.read())

        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        logger.info("Downloaded %.1f MB to %s", file_size_mb, audio_path)

        # Transcribe
        from ppke.audio.transcriber import transcribe

        transcript = transcribe(audio_path)

    # Build Markdown document
    safe_title = re.sub(r"[^\w\s\-]", "", episode_title).strip()
    lines = [
        f"# {safe_title}",
        "",
        f"**Podcast:** {podcast_title}",
        f"**Author:** {podcast_author}",
        f"**Source:** Podcast RSS import",
        "",
        "---",
        "",
        transcript,
    ]

    return "\n".join(lines)
