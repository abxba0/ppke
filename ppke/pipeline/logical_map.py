"""Skill 3: Logical Architecture Builder - maps argument structures via LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from ppke.llm.client import LLMClient
from ppke.llm.prompts import LOGICAL_MAP_SYSTEM, LOGICAL_MAP_USER
from ppke.parser.models import ExtractionResult

logger = logging.getLogger(__name__)


def _extraction_to_summary(results: list[ExtractionResult]) -> str:
    """Convert extraction results to a condensed JSON summary for the LLM.

    We don't send full text - just the structured extractions to stay within limits.
    """
    items = []
    for r in results:
        item: dict[str, Any] = {
            "paragraph_id": r.paragraph_id,
            "topic_sentence": r.topic_sentence,
            "function": r.function_in_argument,
            "claims": r.explicit_claims,
            "assumptions": r.implicit_assumptions,
            "logical_steps": r.logical_steps,
            "concepts": r.defined_concepts,
        }
        items.append(item)
    return json.dumps(items, indent=1)


def build_logical_map(
    client: LLMClient,
    extraction_results: list[ExtractionResult],
    book_title: str,
    author: str,
) -> dict[str, Any]:
    """Build the logical architecture map for the entire book.

    Returns the raw dict structure for writing to 02_Logical_Map.md.
    """
    # For very large books, we may need to chunk this too
    # For now, send all extractions (summarized form)
    extraction_json = _extraction_to_summary(extraction_results)

    user_prompt = LOGICAL_MAP_USER.format(
        book_title=book_title,
        author=author,
        extraction_json=extraction_json,
    )

    try:
        result = client.complete_json(LOGICAL_MAP_SYSTEM, user_prompt)
        logger.info("Logical map built successfully")
        return result
    except Exception as e:
        logger.error("Failed to build logical map: %s", e)
        return {
            "central_thesis": {"claim": "[ANALYSIS FAILED]", "paragraph_ids": [], "evidence": ""},
            "argument_threads": [],
            "key_assumptions": [],
            "error": str(e),
        }
