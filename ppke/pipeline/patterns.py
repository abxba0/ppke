"""Skill 5: Pattern & Tension Detector - finds recurring patterns via LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from ppke.llm.client import LLMClient
from ppke.llm.prompts import PATTERN_DETECTION_SYSTEM, PATTERN_DETECTION_USER
from ppke.parser.models import ExtractionResult

logger = logging.getLogger(__name__)

# Max paragraphs per LLM call to stay within token limits
_PATTERN_CHUNK_SIZE = 30


def _extraction_to_pattern_input(results: list[ExtractionResult]) -> str:
    """Build input focusing on tones, claims, and structural data.

    All paragraphs are included (needed for emotional arc tracking).
    Full verbatim text is preserved — no truncation. Empty fields are
    omitted to reduce token usage without losing content.
    """
    items = []
    for r in results:
        item: dict = {"paragraph_id": r.paragraph_id, "original_text": r.original_text}
        if r.topic_sentence:
            item["topic"] = r.topic_sentence
        if r.function_in_argument:
            item["function"] = r.function_in_argument
        if r.emotional_tone:
            item["tone"] = r.emotional_tone
        if r.explicit_claims:
            item["claims"] = r.explicit_claims
        if r.implicit_assumptions:
            item["assumptions"] = r.implicit_assumptions
        items.append(item)
    return json.dumps(items, separators=(',', ':'))


def _merge_pattern_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge pattern detection results from multiple chunks."""
    all_patterns: list[dict[str, Any]] = []
    for result in results:
        all_patterns.extend(result.get("patterns", []))
    return {"patterns": all_patterns}


def detect_patterns(
    client: LLMClient,
    extraction_results: list[ExtractionResult],
    book_title: str,
    author: str,
    system_prompt: str | None = None,
    user_template: str | None = None,
) -> dict[str, Any]:
    """Detect patterns, tensions, and findings in the book.

    Processes in chunks to respect token limits while preserving full text.
    Returns dict structure for writing to the stage 4 output file.

    Args:
        system_prompt: Override system prompt from the active domain template.
        user_template: Override user template; must contain {book_title},
            {author}, {extraction_json} placeholders.
    """
    effective_system = system_prompt if system_prompt else PATTERN_DETECTION_SYSTEM
    effective_user_tpl = user_template if user_template else PATTERN_DETECTION_USER

    if not extraction_results:
        return {"patterns": []}

    chunk_results: list[dict[str, Any]] = []

    for i in range(0, len(extraction_results), _PATTERN_CHUNK_SIZE):
        chunk = extraction_results[i : i + _PATTERN_CHUNK_SIZE]
        extraction_json = _extraction_to_pattern_input(chunk)

        user_prompt = effective_user_tpl.format(
            book_title=book_title,
            author=author,
            extraction_json=extraction_json,
        )

        try:
            result = client.complete_json(effective_system, user_prompt)
            chunk_results.append(result)
            logger.info(
                "Pattern chunk %d-%d: %d patterns found",
                i + 1,
                min(i + _PATTERN_CHUNK_SIZE, len(extraction_results)),
                len(result.get("patterns", [])),
            )
        except Exception as e:
            logger.error("Failed to detect patterns for chunk %d: %s", i, e)

    if not chunk_results:
        return {"patterns": [], "error": "All pattern detection chunks failed"}

    merged = _merge_pattern_results(chunk_results)
    logger.info("Pattern detection complete: %d patterns total", len(merged["patterns"]))
    return merged
