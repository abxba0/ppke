"""Skill 5: Pattern & Tension Detector - finds recurring patterns via LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from ppke.llm.client import LLMClient
from ppke.llm.prompts import PATTERN_DETECTION_SYSTEM, PATTERN_DETECTION_USER
from ppke.parser.models import ExtractionResult

logger = logging.getLogger(__name__)


def _extraction_to_pattern_input(results: list[ExtractionResult]) -> str:
    """Build input focusing on tones, claims, and structural data."""
    items = []
    for r in results:
        items.append({
            "paragraph_id": r.paragraph_id,
            "topic": r.topic_sentence,
            "function": r.function_in_argument,
            "tone": r.emotional_tone,
            "claims": r.explicit_claims,
            "assumptions": r.implicit_assumptions,
            "original_text": r.original_text[:400],
        })
    return json.dumps(items, indent=1)


def detect_patterns(
    client: LLMClient,
    extraction_results: list[ExtractionResult],
    book_title: str,
    author: str,
) -> dict[str, Any]:
    """Detect patterns and tensions in the book.

    Returns dict structure for writing to pattern sections.
    """
    extraction_json = _extraction_to_pattern_input(extraction_results)

    user_prompt = PATTERN_DETECTION_USER.format(
        book_title=book_title,
        author=author,
        extraction_json=extraction_json,
    )

    try:
        result = client.complete_json(PATTERN_DETECTION_SYSTEM, user_prompt)
        logger.info(
            "Pattern detection complete: %d patterns found",
            len(result.get("patterns", [])),
        )
        return result
    except Exception as e:
        logger.error("Failed to detect patterns: %s", e)
        return {"patterns": [], "error": str(e)}
