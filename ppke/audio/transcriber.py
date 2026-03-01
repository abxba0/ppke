"""Audio transcription — converts audio files to timestamped Markdown.

Uses OpenAI Whisper API by default with local whisper as a fallback option.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def transcribe(
    audio_path: Path,
    *,
    api_key: str | None = None,
    model: str = "whisper-1",
    language: str | None = None,
) -> str:
    """Transcribe an audio file to timestamped Markdown.

    Uses the OpenAI Whisper API. Returns Markdown with ``[MM:SS]`` timestamps
    that the existing parser can ingest as paragraphs.

    Parameters
    ----------
    audio_path:
        Path to audio file (.mp3, .mp4, .m4a, .wav, .webm, .ogg, etc.).
    api_key:
        OpenAI API key. Falls back to ``OPENAI_API_KEY`` env var.
    model:
        Whisper model identifier.
    language:
        Optional ISO-639-1 language code to improve accuracy.
    """
    try:
        import openai
    except ImportError:
        raise ImportError(
            "Audio transcription requires the openai package. "
            "Install with: pip install 'ppke[audio]'"
        )

    client = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()

    logger.info("Transcribing %s via Whisper (%s)", audio_path.name, model)

    with open(audio_path, "rb") as f:
        kwargs: dict = {
            "model": model,
            "file": f,
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment"],
        }
        if language:
            kwargs["language"] = language
        transcript = client.audio.transcriptions.create(**kwargs)

    # Build timestamped Markdown
    title = audio_path.stem.replace("_", " ").replace("-", " ").title()
    lines = [f"# {title}", "", f"**Source:** {audio_path.name}", ""]

    segments = getattr(transcript, "segments", None) or []
    if segments:
        for seg in segments:
            ts = _format_timestamp(seg.get("start", seg.start) if isinstance(seg, dict) else seg.start)
            text = seg.get("text", "").strip() if isinstance(seg, dict) else seg.text.strip()
            if text:
                lines.append(f"**[{ts}]** {text}")
                lines.append("")
    else:
        # Fallback: no segment-level timestamps
        full_text = getattr(transcript, "text", str(transcript))
        lines.append(full_text)
        lines.append("")

    return "\n".join(lines)


def transcribe_local(
    audio_path: Path,
    *,
    model_size: str = "base",
    language: str | None = None,
) -> str:
    """Transcribe audio locally using the open-source Whisper model.

    Requires a GPU for acceptable performance on models larger than 'base'.
    """
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "Local transcription requires openai-whisper. "
            "Install with: pip install openai-whisper"
        )

    logger.info("Loading Whisper model '%s' for local transcription", model_size)
    model = whisper.load_model(model_size)
    result = model.transcribe(str(audio_path), language=language)

    title = audio_path.stem.replace("_", " ").replace("-", " ").title()
    lines = [f"# {title}", "", f"**Source:** {audio_path.name}", ""]

    for seg in result.get("segments", []):
        ts = _format_timestamp(seg["start"])
        text = seg["text"].strip()
        if text:
            lines.append(f"**[{ts}]** {text}")
            lines.append("")

    return "\n".join(lines)
