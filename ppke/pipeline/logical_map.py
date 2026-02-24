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
    Empty fields are omitted to reduce token usage without losing content.
    """
    items = []
    for r in results:
        item: dict[str, Any] = {"paragraph_id": r.paragraph_id}
        if r.topic_sentence:
            item["topic_sentence"] = r.topic_sentence
        if r.function_in_argument:
            item["function"] = r.function_in_argument
        if r.explicit_claims:
            item["claims"] = r.explicit_claims
        if r.implicit_assumptions:
            item["assumptions"] = r.implicit_assumptions
        if r.logical_steps:
            item["logical_steps"] = r.logical_steps
        if r.defined_concepts:
            item["concepts"] = r.defined_concepts
        items.append(item)
    return json.dumps(items, separators=(',', ':'))


def build_logical_map(
    client: LLMClient,
    extraction_results: list[ExtractionResult],
    book_title: str,
    author: str,
    system_prompt: str | None = None,
    user_template: str | None = None,
) -> dict[str, Any]:
    """Build the logical architecture / second-stage analysis map for the book.

    Returns the raw dict structure for writing to the stage 2 output file.

    Args:
        system_prompt: Override system prompt from the active domain template.
        user_template: Override user template; must contain {book_title},
            {author}, {extraction_json} placeholders.
    """
    effective_system = system_prompt if system_prompt else LOGICAL_MAP_SYSTEM
    effective_user_tpl = user_template if user_template else LOGICAL_MAP_USER

    extraction_json = _extraction_to_summary(extraction_results)

    user_prompt = effective_user_tpl.format(
        book_title=book_title,
        author=author,
        extraction_json=extraction_json,
    )

    try:
        result = client.complete_json(effective_system, user_prompt)
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
