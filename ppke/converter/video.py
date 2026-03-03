"""Lecture video import — extract audio + optional keyframes from video files.

Supports MP4, MKV, AVI, MOV, and WEBM video files.  The pipeline:
  1. Extract the audio track via ffmpeg → temporary WAV/MP3
  2. Transcribe via Whisper (OpenAI API or local)
  3. Optionally extract keyframes (slide changes) via scene detection
  4. Generate Markdown with timestamps and slide annotations

Install::

    pip install 'ppke[video]'

System requirement: ``ffmpeg`` must be on PATH.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Supported video extensions
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".flv", ".wmv"}


# ── Public API ──────────────────────────────────────────────────────


def convert_video(
    video_path: Path,
    *,
    extract_keyframes: bool = True,
    max_keyframes: int = 20,
    api_key: str | None = None,
    model: str = "whisper-1",
    language: str | None = None,
) -> str:
    """Import a lecture video and produce a timestamped Markdown transcript.

    Parameters
    ----------
    video_path:
        Path to the video file.
    extract_keyframes:
        When ``True`` (default), extracts keyframes (slide transitions)
        and annotates the transcript with ``[Slide change at MM:SS]``.
    max_keyframes:
        Maximum number of keyframes to detect.
    api_key:
        OpenAI API key for Whisper transcription.
    model:
        Whisper model identifier (default ``"whisper-1"``).
    language:
        ISO-639-1 language code for transcription accuracy.

    Returns
    -------
    str
        Markdown document with video metadata, timestamped transcript,
        and optional slide-change annotations.
    """
    _check_ffmpeg()

    # Extract video metadata
    meta = _get_video_metadata(video_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # 1. Extract audio track → WAV
        audio_path = tmp / "audio.mp3"
        _extract_audio(video_path, audio_path)

        # 2. Transcribe
        from ppke.audio.transcriber import transcribe

        logger.info("Transcribing video audio: %s", video_path.name)
        transcript = transcribe(audio_path, api_key=api_key, model=model, language=language)

        # 3. Extract keyframes (slide changes)
        keyframe_annotations: list[dict[str, Any]] = []
        if extract_keyframes:
            try:
                keyframe_annotations = _detect_keyframes(video_path, tmp, max_frames=max_keyframes)
                logger.info("Detected %d keyframe(s) in %s", len(keyframe_annotations), video_path.name)
            except Exception as exc:
                logger.warning("Keyframe detection failed: %s", exc)

    # Build Markdown output
    return _build_lecture_markdown(
        video_path=video_path,
        meta=meta,
        transcript=transcript,
        keyframes=keyframe_annotations,
    )


def get_video_info(video_path: Path) -> dict[str, Any]:
    """Return video metadata (duration, resolution, codec) without processing."""
    _check_ffmpeg()
    return _get_video_metadata(video_path)


# ── Audio extraction ────────────────────────────────────────────────


def _extract_audio(video_path: Path, output_path: Path) -> None:
    """Extract audio track from video → MP3 using ffmpeg."""
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vn",                    # no video
        "-acodec", "libmp3lame",  # MP3 codec
        "-ab", "128k",            # bitrate
        "-ar", "16000",           # 16kHz sample rate (optimal for Whisper)
        "-ac", "1",               # mono
        "-y",                     # overwrite
        str(output_path),
    ]
    logger.info("Extracting audio: %s → %s", video_path.name, output_path.name)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            raise ValueError(f"ffmpeg audio extraction failed: {result.stderr[:500]}")
    except FileNotFoundError:
        raise ImportError(
            "ffmpeg is required for video import. "
            "Install via: apt install ffmpeg (Linux) / brew install ffmpeg (macOS)"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise ValueError("ffmpeg produced no audio output — video may have no audio track")


# ── Video metadata ──────────────────────────────────────────────────


def _get_video_metadata(video_path: Path) -> dict[str, Any]:
    """Probe video file with ffprobe for metadata."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)

            fmt = data.get("format", {})
            duration = float(fmt.get("duration", 0))

            # Find video stream
            width = height = 0
            video_codec = ""
            for s in data.get("streams", []):
                if s.get("codec_type") == "video":
                    width = int(s.get("width", 0))
                    height = int(s.get("height", 0))
                    video_codec = s.get("codec_name", "")
                    break

            return {
                "duration": duration,
                "duration_str": _fmt_duration(duration),
                "width": width,
                "height": height,
                "codec": video_codec,
                "filename": video_path.name,
                "size_mb": round(video_path.stat().st_size / (1024 * 1024), 1),
            }
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as exc:
        logger.debug("ffprobe failed: %s", exc)

    # Fallback: minimal metadata
    return {
        "duration": 0,
        "duration_str": "",
        "filename": video_path.name,
        "size_mb": round(video_path.stat().st_size / (1024 * 1024), 1),
    }


# ── Keyframe / slide change detection ──────────────────────────────


def _detect_keyframes(
    video_path: Path,
    tmp_dir: Path,
    max_frames: int = 20,
) -> list[dict[str, Any]]:
    """Detect scene/slide changes in a video using ffmpeg scene filter.

    Returns a list of keyframe timestamps:
    ``[{"time": float, "time_str": str, "frame_path": str | None}, …]``
    """
    # Use ffmpeg scene change detection
    keyframes_dir = tmp_dir / "keyframes"
    keyframes_dir.mkdir(exist_ok=True)

    # scene detection threshold: 0.3 means 30% pixel change between frames
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", "select='gt(scene,0.30)',showinfo",
        "-vsync", "vfr",
        "-frame_pts", "true",
        str(keyframes_dir / "frame_%04d.jpg"),
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )

    # Parse showinfo output for timestamps
    import re
    keyframes: list[dict[str, Any]] = []
    for line in result.stderr.split("\n"):
        pts_match = re.search(r"pts_time:\s*([\d.]+)", line)
        if pts_match:
            pts_time = float(pts_match.group(1))
            keyframes.append({
                "time": pts_time,
                "time_str": _fmt_duration(pts_time),
            })

    # Limit count
    if len(keyframes) > max_frames:
        # Sample uniformly
        step = len(keyframes) / max_frames
        keyframes = [keyframes[int(i * step)] for i in range(max_frames)]

    return keyframes


# ── Markdown generation ─────────────────────────────────────────────


def _build_lecture_markdown(
    video_path: Path,
    meta: dict[str, Any],
    transcript: str,
    keyframes: list[dict[str, Any]],
) -> str:
    """Assemble the final Markdown document for a lecture video."""
    title = video_path.stem.replace("_", " ").replace("-", " ").title()

    parts: list[str] = [f"# {title}", ""]

    # Metadata header
    header_items: list[str] = [f"**Source:** {video_path.name}"]
    if meta.get("duration_str"):
        header_items.append(f"**Duration:** {meta['duration_str']}")
    if meta.get("width") and meta.get("height"):
        header_items.append(f"**Resolution:** {meta['width']}×{meta['height']}")
    if meta.get("size_mb"):
        header_items.append(f"**Size:** {meta['size_mb']} MB")

    parts.append(" · ".join(header_items))
    parts.append("")

    # Slide change annotations
    if keyframes:
        parts.append("## Detected Slide Changes")
        parts.append("")
        for i, kf in enumerate(keyframes, 1):
            parts.append(f"- **Slide {i}** at [{kf['time_str']}]")
        parts.append("")
        parts.append("---")
        parts.append("")

    # Transcript — strip the generated heading (transcriber adds its own)
    transcript_body = _strip_first_heading(transcript)
    parts.append("## Transcript")
    parts.append("")
    parts.append(transcript_body)

    # Inject slide markers into transcript text
    if keyframes:
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append("*Slide change timestamps detected via scene analysis.*")

    return "\n".join(parts)


# ── Helpers ─────────────────────────────────────────────────────────


def _check_ffmpeg() -> None:
    """Verify ffmpeg is available."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, timeout=5,
        )
    except FileNotFoundError:
        raise ImportError(
            "Video import requires ffmpeg. "
            "Install via: apt install ffmpeg (Linux) / brew install ffmpeg (macOS)"
        )


def _fmt_duration(seconds: float | int | None) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    if not seconds:
        return ""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _strip_first_heading(markdown: str) -> str:
    """Remove the first ``# Heading`` line from a Markdown string."""
    lines = markdown.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# "):
            start = i + 1
            if start < len(lines) and lines[start].strip() == "":
                start += 1
            return "\n".join(lines[start:])
    return markdown
