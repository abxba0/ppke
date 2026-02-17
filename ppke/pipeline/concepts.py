"""Skill 4: Concept Indexer - tracks recurring concepts across a book via LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from ppke.llm.client import LLMClient
from ppke.llm.prompts import CONCEPT_INDEX_SYSTEM, CONCEPT_INDEX_USER
from ppke.parser.models import ExtractionResult

logger = logging.getLogger(__name__)


def _extraction_to_concept_input(results: list[ExtractionResult]) -> str:
    """Build input focusing on concepts and their paragraph contexts."""
    items = []
    for r in results:
        if r.defined_concepts or r.explicit_claims:
            items.append({
                "paragraph_id": r.paragraph_id,
                "topic": r.topic_sentence,
                "concepts": r.defined_concepts,
                "claims": r.explicit_claims,
                "original_text": r.original_text[:500],  # Truncate for token limits
            })
    return json.dumps(items, indent=1)


def build_concept_index(
    client: LLMClient,
    extraction_results: list[ExtractionResult],
    book_title: str,
    author: str,
) -> dict[str, Any]:
    """Build concept index for the book.

    Returns dict structure for writing to 03_Concept_Index.md.
    """
    extraction_json = _extraction_to_concept_input(extraction_results)

    user_prompt = CONCEPT_INDEX_USER.format(
        book_title=book_title,
        author=author,
        extraction_json=extraction_json,
    )

    try:
        result = client.complete_json(CONCEPT_INDEX_SYSTEM, user_prompt)
        logger.info(
            "Concept index built: %d concepts found",
            len(result.get("concepts", [])),
        )
        return result
    except Exception as e:
        logger.error("Failed to build concept index: %s", e)
        return {"concepts": [], "error": str(e)}
