"""YouTube → Markdown converter using yt-dlp and Whisper transcription.

Downloads the audio track of any YouTube video (or Shorts) and transcribes
it with the existing ``ppke.audio.transcriber`` module, producing the same
timestamped Markdown format as any other audio converter.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def convert_youtube(url: str) -> str:
    """Download a YouTube video's audio and transcribe it to timestamped Markdown.

    Parameters
    ----------
    url:
        A YouTube watch URL (``https://www.youtube.com/watch?v=...``) or
        short URL (``https://youtu.be/...``).

    Raises
    ------
    ImportError
        If ``yt-dlp`` is not installed.
    ValueError
        If the download or transcription fails.
    """
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        raise ImportError(
            "YouTube import requires yt-dlp. "
            "Install with: pip install yt-dlp"
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        ydl_opts = {
            # Best audio, prefer m4a/mp3
            "format": "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best",
            "outtmpl": str(tmp_path / "audio.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }
            ],
            "quiet": True,
            "no_warnings": True,
            # Restrict download size — refuse videos > 2 hours
            "match_filter": _duration_filter,
        }

        info: dict = {}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True) or {}
            except yt_dlp.utils.DownloadError as exc:
                raise ValueError(f"yt-dlp download failed: {exc}") from exc
            except Exception as exc:
                raise ValueError(f"Failed to download YouTube video: {exc}") from exc

        # Find the actual downloaded audio file (extension may vary)
        audio_files = list(tmp_path.glob("audio.*"))
        if not audio_files:
            raise ValueError(
                "yt-dlp completed but produced no audio file — "
                "is ffmpeg installed?"
            )
        audio_file = audio_files[0]

        # Transcribe using the shared audio module
        from ppke.audio.transcriber import transcribe

        logger.info(
            "Transcribing YouTube audio (%s, %s)",
            info.get("title", "?"),
            audio_file.name,
        )
        transcript = transcribe(audio_file)

    # Build the final Markdown document with video metadata prepended
    title = info.get("title") or "YouTube Video"
    channel = info.get("uploader") or info.get("channel") or "Unknown"
    upload_date: str = info.get("upload_date", "") or ""
    if len(upload_date) == 8:  # "YYYYMMDD"
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    duration_str: str = info.get("duration_string") or _fmt_duration(info.get("duration"))
    view_count: int | None = info.get("view_count")

    header_parts: list[str] = [f"Channel: {channel}"]
    if upload_date:
        header_parts.append(f"Published: {upload_date}")
    if duration_str:
        header_parts.append(f"Duration: {duration_str}")
    if view_count is not None:
        header_parts.append(f"Views: {view_count:,}")

    header = f"# {title}\n\n"
    header += "*" + " · ".join(header_parts) + "*\n\n"
    header += f"Source: {url}\n\n---\n\n"

    # The transcript already starts with its own # heading — strip that
    # and use the YouTube title instead.
    transcript_body = _strip_first_heading(transcript)

    return header + transcript_body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _duration_filter(info: dict, *, incomplete: bool) -> str | None:
    """Reject videos longer than 7200 seconds (2 hours)."""
    dur = info.get("duration")
    if dur and dur > 7200:
        return "Video exceeds 2-hour limit — please trim before importing."
    return None


def _fmt_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _strip_first_heading(markdown: str) -> str:
    """Remove the first ``# Heading`` line from a Markdown string."""
    lines = markdown.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# "):
            # Also skip the immediately following blank line
            start = i + 1
            if start < len(lines) and lines[start].strip() == "":
                start += 1
            return "\n".join(lines[start:])
    return markdown
