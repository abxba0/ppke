"""Speaker diarization — identifies 'who spoke when' in audio files.

Uses pyannote.audio for speaker segmentation with optional Whisper
transcription merging.  Install the extra with::

    pip install 'ppke[diarization]'

A Hugging Face token with access to the pyannote models is required.
See https://huggingface.co/pyannote/speaker-diarization-3.1 for details.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Core types ───────────────────────────────────────────────────────

DiarSegment = dict[str, Any]
"""A single diarization segment: ``{"speaker": str, "start": float, "end": float}``."""


# ── Helpers ──────────────────────────────────────────────────────────


def _format_ts(seconds: float) -> str:
    """Format *seconds* as ``HH:MM:SS`` or ``MM:SS``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ── Diarization pipeline ────────────────────────────────────────────


def diarize(
    audio_path: Path,
    *,
    hf_token: str | None = None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    pipeline_name: str = "pyannote/speaker-diarization-3.1",
) -> list[DiarSegment]:
    """Run speaker diarization on *audio_path*.

    Returns a list of segments sorted by start time, each containing
    ``speaker``, ``start`` (seconds) and ``end`` (seconds).

    Parameters
    ----------
    audio_path:
        Path to an audio file supported by pyannote/torchaudio.
    hf_token:
        Hugging Face access token.  Falls back to ``HF_TOKEN`` env var.
    num_speakers:
        Exact number of speakers (if known).
    min_speakers / max_speakers:
        Optional speaker-count bounds for the clustering step.
    pipeline_name:
        Pre-trained pipeline identifier on the Hugging Face Hub.
    """
    try:
        from pyannote.audio import Pipeline  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "Speaker diarization requires pyannote.audio. "
            "Install with: pip install 'ppke[diarization]'"
        )

    import os

    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError(
            "A Hugging Face token is required for pyannote.audio. "
            "Set HF_TOKEN or pass hf_token explicitly."
        )

    logger.info("Loading diarization pipeline %s", pipeline_name)
    pipeline = Pipeline.from_pretrained(pipeline_name, token=token)

    params: dict[str, Any] = {}
    if num_speakers is not None:
        params["num_speakers"] = num_speakers
    if min_speakers is not None:
        params["min_speakers"] = min_speakers
    if max_speakers is not None:
        params["max_speakers"] = max_speakers

    logger.info("Running diarization on %s", audio_path.name)
    diarization_result = pipeline(str(audio_path), **params)

    segments: list[DiarSegment] = []
    for turn, _, speaker in diarization_result.itertracks(yield_label=True):
        segments.append({
            "speaker": speaker,
            "start": round(turn.start, 2),
            "end": round(turn.end, 2),
        })

    logger.info(
        "Diarization complete: %d segments, %d speakers",
        len(segments),
        len({s["speaker"] for s in segments}),
    )
    return segments


# ── Merge with transcription ────────────────────────────────────────


def merge_transcription_diarization(
    transcript_segments: list[dict[str, Any]],
    diar_segments: list[DiarSegment],
) -> list[dict[str, Any]]:
    """Assign speaker labels to Whisper transcript segments.

    Each transcript segment is expected to have ``start``, ``end``, and
    ``text`` keys.  The function finds the diarization segment with the
    greatest temporal overlap and copies its ``speaker`` label.

    Returns a new list (original segments are not mutated).
    """
    merged: list[dict[str, Any]] = []
    for tseg in transcript_segments:
        t_start = tseg.get("start", 0.0)
        t_end = tseg.get("end", t_start)
        best_speaker = "UNKNOWN"
        best_overlap = 0.0

        for dseg in diar_segments:
            overlap_start = max(t_start, dseg["start"])
            overlap_end = min(t_end, dseg["end"])
            overlap = max(0.0, overlap_end - overlap_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = dseg["speaker"]

        merged.append({**tseg, "speaker": best_speaker})
    return merged


# ── Formatting ──────────────────────────────────────────────────────


def format_diarized_transcript(
    segments: list[dict[str, Any]],
    *,
    title: str = "Diarized Transcript",
    source: str = "",
) -> str:
    """Render diarized segments as Markdown with speaker labels.

    Parameters
    ----------
    segments:
        List of dicts with at least ``speaker``, ``start`` and ``text``.
    title:
        Markdown heading for the transcript.
    source:
        Optional source filename shown under the heading.
    """
    lines = [f"# {title}", ""]
    if source:
        lines.append(f"**Source:** {source}")
        lines.append("")

    # Build a friendly label map (SPEAKER_00 → Speaker 1, etc.)
    unique = list(dict.fromkeys(s.get("speaker", "UNKNOWN") for s in segments))
    label_map = {raw: f"Speaker {i + 1}" for i, raw in enumerate(unique)}

    for seg in segments:
        ts = _format_ts(seg.get("start", 0.0))
        speaker = label_map.get(seg.get("speaker", "UNKNOWN"), seg.get("speaker", "UNKNOWN"))
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"**[{ts}] {speaker}:** {text}")
            lines.append("")

    return "\n".join(lines)


# ── Persistence helpers ─────────────────────────────────────────────


def save_diarization(segments: list[DiarSegment], path: Path) -> None:
    """Write diarization segments to a JSON file."""
    path.write_text(json.dumps(segments, indent=2, ensure_ascii=False))


def load_diarization(path: Path) -> list[DiarSegment]:
    """Read diarization segments from a JSON file."""
    return json.loads(path.read_text())  # type: ignore[return-value]
