"""Audio Overview Generator — NotebookLM-style podcast conversations.

Generates a two-host conversational script from book analysis, then
synthesizes it to audio using TTS (OpenAI TTS / ElevenLabs / edge-tts).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Script generation prompt ──

OVERVIEW_SCRIPT_SYSTEM = """\
You are an expert podcast script writer. You create engaging, educational
conversations between two hosts discussing academic content.

HOST_A is curious, enthusiastic, and asks probing questions.
HOST_B is the knowledgeable expert who explains concepts accessibly.

Rules:
- The conversation should feel natural and unscripted
- Use accessible language — explain jargon when it first appears
- Include natural reactions: "That's fascinating!", "Wait, so you're saying..."
- Reference specific quotes and concepts from the source material
- The script should be 5-10 minutes when spoken aloud (~800-1500 words)
- Output ONLY valid JSON, no commentary

Output format — a JSON array of turns:
[
  {"speaker": "HOST_A", "text": "..."},
  {"speaker": "HOST_B", "text": "..."},
  ...
]
"""

OVERVIEW_SCRIPT_USER = """\
Create an engaging podcast conversation about this book analysis.

BOOK: {title} by {author}

KEY CONCEPTS:
{concepts}

LOGICAL ARCHITECTURE:
{logical_map}

PATTERNS & TENSIONS:
{patterns}

Generate the podcast script now as a JSON array.
"""


def generate_script(
    book_dir: Path,
    llm_client: Any,
    *,
    max_tokens: int = 4096,
) -> list[dict[str, str]]:
    """Generate a conversational podcast script from a book's analysis files.

    Parameters
    ----------
    book_dir:
        Path to the book folder in the vault (contains 01_Raw_Structure.md, etc.).
    llm_client:
        An instance of ``ppke.llm.client.LLMClient``.
    max_tokens:
        Maximum tokens for the script generation.

    Returns
    -------
    list[dict]:
        List of ``{"speaker": "HOST_A"|"HOST_B", "text": "..."}`` dicts.
    """
    import yaml

    meta_path = book_dir / "meta.yml"
    meta = yaml.safe_load(meta_path.read_text()) if meta_path.exists() else {}

    title = meta.get("title", book_dir.name)
    author = meta.get("author", "Unknown")

    concept_path = book_dir / "03_Concept_Index.md"
    logical_path = book_dir / "02_Logical_Map.md"
    pattern_path = book_dir / "06_Patterns.md"

    concepts = concept_path.read_text()[:3000] if concept_path.exists() else "N/A"
    logical_map = logical_path.read_text()[:3000] if logical_path.exists() else "N/A"
    patterns = pattern_path.read_text()[:2000] if pattern_path.exists() else "N/A"

    user_prompt = OVERVIEW_SCRIPT_USER.format(
        title=title,
        author=author,
        concepts=concepts,
        logical_map=logical_map,
        patterns=patterns,
    )

    result = llm_client.complete_json(OVERVIEW_SCRIPT_SYSTEM, user_prompt)

    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "script" in result:
        return result["script"]
    raise ValueError(f"Unexpected script format: {type(result)}")


def synthesize_audio(
    script: list[dict[str, str]],
    output_path: Path,
    *,
    provider: str = "openai",
    api_key: str | None = None,
    voice_a: str = "alloy",
    voice_b: str = "onyx",
) -> Path:
    """Convert a dialogue script to an MP3 audio file.

    Parameters
    ----------
    script:
        List of ``{"speaker": "HOST_A"|"HOST_B", "text": "..."}`` turns.
    output_path:
        Where to write the final MP3 file.
    provider:
        TTS provider: "openai" or "edge" (free, no API key).
    api_key:
        API key for the TTS provider.
    voice_a:
        Voice ID for HOST_A.
    voice_b:
        Voice ID for HOST_B.

    Returns
    -------
    Path:
        The path to the generated audio file.
    """
    if provider == "openai":
        return _synthesize_openai(script, output_path, api_key, voice_a, voice_b)
    elif provider == "edge":
        return _synthesize_edge(script, output_path, voice_a, voice_b)
    else:
        raise ValueError(f"Unsupported TTS provider: {provider}")


def _synthesize_openai(
    script: list[dict[str, str]],
    output_path: Path,
    api_key: str | None,
    voice_a: str,
    voice_b: str,
) -> Path:
    """Synthesize audio using OpenAI TTS."""
    try:
        import openai
    except ImportError:
        raise ImportError("Audio synthesis requires openai. Install with: pip install openai")

    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("Audio synthesis requires pydub. Install with: pip install 'ppke[audio]'")

    client = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()
    voice_map = {"HOST_A": voice_a, "HOST_B": voice_b}

    segments: list[AudioSegment] = []
    pause = AudioSegment.silent(duration=400)  # 400ms pause between turns

    for i, turn in enumerate(script):
        speaker = turn.get("speaker", "HOST_A")
        text = turn.get("text", "")
        if not text:
            continue

        voice = voice_map.get(speaker, voice_a)
        logger.info("Synthesizing turn %d/%d (%s, voice=%s)", i + 1, len(script), speaker, voice)

        response = client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=text,
        )

        # Write to temp file and load as AudioSegment
        temp_path = output_path.parent / f"_turn_{i}.mp3"
        temp_path.write_bytes(response.content)
        segment = AudioSegment.from_mp3(str(temp_path))
        segments.append(segment)
        segments.append(pause)
        temp_path.unlink()

    # Concatenate all segments
    combined = segments[0]
    for seg in segments[1:]:
        combined += seg

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3")
    logger.info("Audio overview saved to %s", output_path)
    return output_path


def _synthesize_edge(
    script: list[dict[str, str]],
    output_path: Path,
    voice_a: str,
    voice_b: str,
) -> Path:
    """Synthesize audio using edge-tts (free, no API key required)."""
    try:
        import asyncio
        import edge_tts
    except ImportError:
        raise ImportError(
            "Free TTS requires edge-tts. Install with: pip install edge-tts"
        )

    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("Audio synthesis requires pydub. Install with: pip install 'ppke[audio]'")

    # Default edge-tts voices
    if voice_a == "alloy":
        voice_a = "en-US-JennyNeural"
    if voice_b == "onyx":
        voice_b = "en-US-GuyNeural"

    voice_map = {"HOST_A": voice_a, "HOST_B": voice_b}

    async def _generate():
        segments: list[AudioSegment] = []
        pause = AudioSegment.silent(duration=400)

        for i, turn in enumerate(script):
            speaker = turn.get("speaker", "HOST_A")
            text = turn.get("text", "")
            if not text:
                continue

            voice = voice_map.get(speaker, voice_a)
            temp_path = output_path.parent / f"_edge_turn_{i}.mp3"

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(temp_path))

            segment = AudioSegment.from_mp3(str(temp_path))
            segments.append(segment)
            segments.append(pause)
            temp_path.unlink()

        if segments:
            combined = segments[0]
            for seg in segments[1:]:
                combined += seg
            output_path.parent.mkdir(parents=True, exist_ok=True)
            combined.export(str(output_path), format="mp3")

    asyncio.run(_generate())
    logger.info("Audio overview (edge-tts) saved to %s", output_path)
    return output_path
