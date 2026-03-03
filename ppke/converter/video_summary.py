"""Video summaries — generate structured summaries from video transcripts.

Takes a video transcript (from lecture video import or YouTube) and
produces a structured summary with key points, topics, and timestamps.

Depends on the video import feature (``ppke.converter.video``) and
the LLM client (``ppke.llm.client``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Public API ──────────────────────────────────────────────────────


def generate_video_summary(
    transcript: str,
    *,
    title: str = "Video",
    api_key: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    detail_level: str = "medium",
) -> dict[str, Any]:
    """Generate a structured summary from a video transcript.

    Parameters
    ----------
    transcript:
        The full Markdown transcript text (with timestamps).
    title:
        Video title for context.
    api_key:
        LLM API key. Falls back to environment variables.
    provider:
        LLM provider (``"anthropic"``, ``"openai"``, ``"google"``).
        Defaults to the configured provider.
    model:
        Specific model name. Defaults to provider's default.
    detail_level:
        How detailed the summary should be:
        ``"brief"`` = short overview (~200 words),
        ``"medium"`` = key points + timestamps (~500 words),
        ``"detailed"`` = comprehensive chapter-by-chapter (~1000 words).

    Returns
    -------
    dict
        Structured summary with keys:
        ``title``, ``overview``, ``key_points``, ``topics``,
        ``timestamps``, ``markdown``
    """
    from ppke.llm.client import ask_llm

    word_targets = {"brief": 200, "medium": 500, "detailed": 1000}
    target_words = word_targets.get(detail_level, 500)

    prompt = f"""Analyze this video transcript and produce a structured summary.

VIDEO TITLE: {title}
DETAIL LEVEL: {detail_level} (~{target_words} words)

TRANSCRIPT:
{transcript[:12000]}

Return a JSON object with these keys:
{{
  "overview": "A 2-3 sentence overview of the video's content and purpose.",
  "key_points": ["List", "of", "key", "points", "or", "takeaways"],
  "topics": [
    {{"topic": "Topic name", "description": "Brief description", "timestamp": "MM:SS if identifiable"}}
  ],
  "timestamps": [
    {{"time": "MM:SS", "label": "What happens at this point"}}
  ],
  "action_items": ["Any action items or recommendations mentioned"],
  "questions": ["Open questions or discussion points raised"]
}}

Guidelines:
- Extract ALL major topics discussed
- Include timestamps when identifiable from the transcript's [MM:SS] markers
- Key points should be concise, actionable statements
- For lectures: focus on concepts taught, definitions, and examples
- For presentations: focus on claims, evidence, and conclusions
- Return ONLY the JSON object, no other text."""

    try:
        response = ask_llm(
            prompt,
            api_key=api_key,
            provider=provider,
            model=model,
        )

        # Parse the JSON response
        summary = _parse_json_response(response)
        summary["title"] = title
        summary["detail_level"] = detail_level

        # Generate Markdown rendering
        summary["markdown"] = _render_summary_markdown(summary)

        return summary

    except Exception as exc:
        logger.error("Video summary generation failed: %s", exc)
        # Return a basic fallback summary
        return {
            "title": title,
            "overview": f"Summary generation failed: {exc}",
            "key_points": [],
            "topics": [],
            "timestamps": [],
            "action_items": [],
            "questions": [],
            "detail_level": detail_level,
            "markdown": f"# {title} — Summary\n\n*Summary generation failed: {exc}*",
            "error": str(exc),
        }


def summarize_video_file(
    video_path: Path,
    *,
    api_key: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    detail_level: str = "medium",
) -> dict[str, Any]:
    """End-to-end: import a video file and generate its summary.

    Combines ``convert_video()`` + ``generate_video_summary()``.

    Parameters
    ----------
    video_path:
        Path to a video file (MP4, MKV, AVI, MOV, etc.).
    """
    from ppke.converter.video import convert_video

    title = video_path.stem.replace("_", " ").replace("-", " ").title()

    # Step 1: extract transcript
    transcript = convert_video(video_path, api_key=api_key)

    # Step 2: generate summary
    return generate_video_summary(
        transcript,
        title=title,
        api_key=api_key,
        provider=provider,
        model=model,
        detail_level=detail_level,
    )


# ── Helpers ─────────────────────────────────────────────────────────


def _parse_json_response(response: str) -> dict[str, Any]:
    """Extract and parse JSON from an LLM response.

    Handles cases where the LLM wraps JSON in markdown code blocks.
    """
    text = response.strip()

    # Strip markdown code fence
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences)
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    # Fallback: return raw text as overview
    return {
        "overview": text[:500],
        "key_points": [],
        "topics": [],
        "timestamps": [],
        "action_items": [],
        "questions": [],
    }


def _render_summary_markdown(summary: dict[str, Any]) -> str:
    """Render a structured summary dict as readable Markdown."""
    title = summary.get("title", "Video Summary")
    lines: list[str] = [f"# {title} — Summary", ""]

    # Overview
    overview = summary.get("overview", "")
    if overview:
        lines.append("## Overview")
        lines.append("")
        lines.append(overview)
        lines.append("")

    # Key Points
    key_points = summary.get("key_points", [])
    if key_points:
        lines.append("## Key Points")
        lines.append("")
        for point in key_points:
            lines.append(f"- {point}")
        lines.append("")

    # Topics
    topics = summary.get("topics", [])
    if topics:
        lines.append("## Topics Covered")
        lines.append("")
        for t in topics:
            ts = f" [{t['timestamp']}]" if t.get("timestamp") else ""
            lines.append(f"### {t.get('topic', 'Topic')}{ts}")
            lines.append("")
            if t.get("description"):
                lines.append(t["description"])
                lines.append("")

    # Key Timestamps
    timestamps = summary.get("timestamps", [])
    if timestamps:
        lines.append("## Key Timestamps")
        lines.append("")
        for ts in timestamps:
            lines.append(f"- **[{ts.get('time', '??:??')}]** {ts.get('label', '')}")
        lines.append("")

    # Action Items
    action_items = summary.get("action_items", [])
    if action_items:
        lines.append("## Action Items")
        lines.append("")
        for item in action_items:
            lines.append(f"- [ ] {item}")
        lines.append("")

    # Open Questions
    questions = summary.get("questions", [])
    if questions:
        lines.append("## Open Questions")
        lines.append("")
        for q in questions:
            lines.append(f"- {q}")
        lines.append("")

    return "\n".join(lines)
