"""Audio Overview Generator — NotebookLM-style podcast conversations.

Generates a two-host conversational script from book analysis, then
synthesizes it to audio using TTS (OpenAI TTS / edge-tts).

Phase 5 enhancements: voice presets, length control, topic focus, cross-book.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Voice presets ──

VOICE_PRESETS: dict[str, dict] = {
    # Edge TTS presets (free)
    "natural": {
        "label": "Natural Pair",
        "provider": "edge",
        "voice_a": "en-US-JennyNeural",
        "voice_b": "en-US-GuyNeural",
    },
    "professional": {
        "label": "Professional",
        "provider": "edge",
        "voice_a": "en-US-AriaNeural",
        "voice_b": "en-US-DavisNeural",
    },
    "british": {
        "label": "British",
        "provider": "edge",
        "voice_a": "en-GB-SoniaNeural",
        "voice_b": "en-GB-RyanNeural",
    },
    "australian": {
        "label": "Australian",
        "provider": "edge",
        "voice_a": "en-AU-NatashaNeural",
        "voice_b": "en-AU-WilliamNeural",
    },
    # OpenAI TTS presets (paid)
    "classic": {
        "label": "Classic (OpenAI)",
        "provider": "openai",
        "voice_a": "alloy",
        "voice_b": "onyx",
    },
    "warm": {
        "label": "Warm (OpenAI)",
        "provider": "openai",
        "voice_a": "nova",
        "voice_b": "echo",
    },
    "dynamic": {
        "label": "Dynamic (OpenAI)",
        "provider": "openai",
        "voice_a": "shimmer",
        "voice_b": "fable",
    },
}

# ── Length presets ──

LENGTH_PRESETS: dict[str, dict] = {
    "short": {"label": "Short (~2 min)", "words": 400, "max_tokens": 2048},
    "medium": {"label": "Medium (~5 min)", "words": 1000, "max_tokens": 4096},
    "long": {"label": "Long (~10 min)", "words": 2000, "max_tokens": 8192},
}


# ── Script generation prompts ──

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
- Output ONLY valid JSON, no commentary

Output format — a JSON array of turns:
[
  {{"speaker": "HOST_A", "text": "..."}},
  {{"speaker": "HOST_B", "text": "..."}},
  ...
]
"""

CROSS_BOOK_SYSTEM = """\
You are an expert podcast script writer. You create engaging comparative
discussions between two hosts analyzing multiple books.

HOST_A is the moderator who draws comparisons and asks pointed questions.
HOST_B is the expert who has read both works deeply and identifies connections.

Rules:
- Compare and contrast the two works' arguments, methods, and conclusions
- Highlight agreements, disagreements, and complementary ideas
- Use accessible language — explain jargon when it first appears
- Reference specific concepts from both books
- Output ONLY valid JSON, no commentary

Output format — a JSON array of turns:
[
  {{"speaker": "HOST_A", "text": "..."}},
  {{"speaker": "HOST_B", "text": "..."}},
  ...
]
"""


def generate_script(
    book_dir: Path,
    llm_client: Any,
    *,
    length: str = "medium",
    topic: str | None = None,
    max_tokens: int | None = None,
) -> list[dict[str, str]]:
    """Generate a conversational podcast script from a book's analysis files.

    Parameters
    ----------
    book_dir:
        Path to the book folder in the vault.
    llm_client:
        An instance of ``ppke.llm.client.LLMClient``.
    length:
        ``"short"`` (~2 min), ``"medium"`` (~5 min), or ``"long"`` (~10 min).
    topic:
        Optional topic to focus on (e.g. a specific concept or chapter).
    max_tokens:
        Override for max generation tokens (uses length preset if None).
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

    preset = LENGTH_PRESETS.get(length, LENGTH_PRESETS["medium"])
    word_target = preset["words"]

    topic_instruction = ""
    if topic:
        topic_instruction = (
            f"\n\nFOCUS: The conversation should specifically explore the topic "
            f'"{topic}" as discussed in this book. Spend at least 60% of the '
            f"conversation on this topic while connecting it to the broader themes."
        )

    user_prompt = f"""\
Create an engaging podcast conversation about this book analysis.
The script should be approximately {word_target} words when spoken aloud.

BOOK: {title} by {author}

KEY CONCEPTS:
{concepts}

LOGICAL ARCHITECTURE:
{logical_map}

PATTERNS & TENSIONS:
{patterns}{topic_instruction}

Generate the podcast script now as a JSON array."""

    result = llm_client.complete_json(OVERVIEW_SCRIPT_SYSTEM, user_prompt)

    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "script" in result:
        return result["script"]
    raise ValueError(f"Unexpected script format: {type(result)}")


def generate_cross_book_script(
    book_dir_a: Path,
    book_dir_b: Path,
    llm_client: Any,
    *,
    length: str = "medium",
) -> list[dict[str, str]]:
    """Generate a comparative podcast script for two books."""
    import yaml

    def _read_meta(d: Path) -> dict:
        p = d / "meta.yml"
        return yaml.safe_load(p.read_text()) if p.exists() else {}

    def _read(d: Path, name: str, limit: int = 2000) -> str:
        p = d / name
        return p.read_text()[:limit] if p.exists() else "N/A"

    meta_a = _read_meta(book_dir_a)
    meta_b = _read_meta(book_dir_b)
    preset = LENGTH_PRESETS.get(length, LENGTH_PRESETS["medium"])

    user_prompt = f"""\
Create a comparative podcast conversation (~{preset['words']} words).

BOOK A: "{meta_a.get('title', book_dir_a.name)}" by {meta_a.get('author', 'Unknown')}
Concepts: {_read(book_dir_a, '03_Concept_Index.md')}
Logical map: {_read(book_dir_a, '02_Logical_Map.md')}

BOOK B: "{meta_b.get('title', book_dir_b.name)}" by {meta_b.get('author', 'Unknown')}
Concepts: {_read(book_dir_b, '03_Concept_Index.md')}
Logical map: {_read(book_dir_b, '02_Logical_Map.md')}

Compare and contrast these two works. Generate the podcast script as a JSON array."""

    result = llm_client.complete_json(CROSS_BOOK_SYSTEM, user_prompt)

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


def synthesize_from_preset(
    script: list[dict[str, str]],
    output_path: Path,
    preset_name: str = "natural",
    api_key: str | None = None,
) -> Path:
    """Convenience wrapper that uses a named voice preset."""
    preset = VOICE_PRESETS.get(preset_name, VOICE_PRESETS["natural"])
    return synthesize_audio(
        script,
        output_path,
        provider=preset["provider"],
        api_key=api_key,
        voice_a=preset["voice_a"],
        voice_b=preset["voice_b"],
    )


def script_to_transcript(script: list[dict[str, str]]) -> str:
    """Convert a script to a readable Markdown transcript."""
    lines: list[str] = ["# Audio Overview Transcript\n"]
    for turn in script:
        speaker = turn.get("speaker", "HOST_A")
        name = "Host A" if speaker == "HOST_A" else "Host B"
        text = turn.get("text", "")
        lines.append(f"**{name}:** {text}\n")
    return "\n".join(lines)


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
