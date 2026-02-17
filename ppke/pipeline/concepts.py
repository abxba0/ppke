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

    Full verbatim text is preserved — no truncation. The caller is responsible
    for chunking to stay within token limits.
    """
    items = []
    for r in results:
        if r.defined_concepts or r.explicit_claims:
            items.append({
                "paragraph_id": r.paragraph_id,
                "topic": r.topic_sentence,
                "concepts": r.defined_concepts,
                "claims": r.explicit_claims,
                "original_text": r.original_text,
            })
    return json.dumps(items, indent=1)


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
) -> dict[str, Any]:
    """Build concept index for the book.

    Processes in chunks to respect token limits while preserving full text.
    Returns dict structure for writing to 03_Concept_Index.md.
    """
    # Filter to paragraphs that have concepts or claims
    relevant = [r for r in extraction_results if r.defined_concepts or r.explicit_claims]

    if not relevant:
        return {"concepts": []}

    chunk_results: list[dict[str, Any]] = []

    for i in range(0, len(relevant), _CONCEPT_CHUNK_SIZE):
        chunk = relevant[i : i + _CONCEPT_CHUNK_SIZE]
        extraction_json = _extraction_to_concept_input(chunk)

        user_prompt = CONCEPT_INDEX_USER.format(
            book_title=book_title,
            author=author,
            extraction_json=extraction_json,
        )

        try:
            result = client.complete_json(CONCEPT_INDEX_SYSTEM, user_prompt)
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
