"""Skill 4: Concept Indexer - tracks recurring concepts across a book via LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from ppke.llm.client import LLMClient
from ppke.llm.prompts import CONCEPT_INDEX_SYSTEM, CONCEPT_INDEX_USER
from ppke.parser.models import ExtractionResult

logger = logging.getLogger(__name__)

# Max paragraphs per LLM call to stay within token limits
_CONCEPT_CHUNK_SIZE = 30


def _extraction_to_concept_input(results: list[ExtractionResult]) -> str:
    """Build input focusing on concepts and their paragraph contexts.

    Original text is omitted — topic_sentence plus defined_concepts and
    claims provide sufficient context for concept indexing.  Short key
    names reduce serialized size.  The caller chunks for token limits.
    """
    items = []
    for r in results:
        if r.defined_concepts or r.explicit_claims:
            item: dict = {"id": r.paragraph_id}
            if r.topic_sentence:
                item["topic"] = r.topic_sentence
            if r.defined_concepts:
                item["concepts"] = r.defined_concepts
            if r.explicit_claims:
                item["claims"] = r.explicit_claims
            items.append(item)
    return json.dumps(items, separators=(',', ':'))


def _merge_concept_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge concept index results from multiple chunks into one index."""
    concept_map: dict[str, dict[str, Any]] = {}

    for result in results:
        for concept in result.get("concepts", []):
            name = concept.get("name", "").lower().strip()
            if name not in concept_map:
                concept_map[name] = {
                    "name": concept.get("name", ""),
                    "definition": concept.get("definition", ""),
                    "occurrences": [],
                    "semantic_shifts": [],
                    "related_concepts": [],
                }
            entry = concept_map[name]
            entry["occurrences"].extend(concept.get("occurrences", []))
            entry["semantic_shifts"].extend(concept.get("semantic_shifts", []))
            for rel in concept.get("related_concepts", []):
                if rel not in entry["related_concepts"]:
                    entry["related_concepts"].append(rel)
            # Keep the longer definition
            new_def = concept.get("definition", "")
            if len(new_def) > len(entry["definition"]):
                entry["definition"] = new_def

    return {"concepts": list(concept_map.values())}


def build_concept_index(
    client: LLMClient,
    extraction_results: list[ExtractionResult],
    book_title: str,
    author: str,
    system_prompt: str | None = None,
    user_template: str | None = None,
) -> dict[str, Any]:
    """Build concept/entity index for the book.

    Processes in chunks to respect token limits while preserving full text.
    Returns dict structure for writing to the stage 3 output file.

    Args:
        system_prompt: Override system prompt from the active domain template.
        user_template: Override user template; must contain {book_title},
            {author}, {extraction_json} placeholders.
    """
    effective_system = system_prompt if system_prompt else CONCEPT_INDEX_SYSTEM
    effective_user_tpl = user_template if user_template else CONCEPT_INDEX_USER

    # Filter to paragraphs that have concepts or claims
    relevant = [r for r in extraction_results if r.defined_concepts or r.explicit_claims]

    if not relevant:
        return {"concepts": []}

    chunk_results: list[dict[str, Any]] = []

    for i in range(0, len(relevant), _CONCEPT_CHUNK_SIZE):
        chunk = relevant[i : i + _CONCEPT_CHUNK_SIZE]
        extraction_json = _extraction_to_concept_input(chunk)

        user_prompt = effective_user_tpl.format(
            book_title=book_title,
            author=author,
            extraction_json=extraction_json,
        )

        try:
            result = client.complete_json(effective_system, user_prompt)
            chunk_results.append(result)
            logger.info(
                "Concept chunk %d-%d: %d concepts found",
                i + 1,
                min(i + _CONCEPT_CHUNK_SIZE, len(relevant)),
                len(result.get("concepts", [])),
            )
        except Exception as e:
            logger.error("Failed to build concept index for chunk %d: %s", i, e)

    if not chunk_results:
        return {"concepts": [], "error": "All concept extraction chunks failed"}

    merged = _merge_concept_results(chunk_results)
    logger.info("Concept index built: %d concepts total", len(merged["concepts"]))
    return merged
