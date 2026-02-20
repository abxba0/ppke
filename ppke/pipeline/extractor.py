"""Skill 1: Structural Extractor - extracts structured data from paragraphs via LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from ppke.llm.client import LLMClient
from ppke.llm.prompts import STRUCTURAL_EXTRACTION_SYSTEM, STRUCTURAL_EXTRACTION_USER
from ppke.parser.models import (
    Chapter,
    DepthLevel,
    ExtractionResult,
    Paragraph,
)

logger = logging.getLogger(__name__)


def _paragraphs_to_json(paragraphs: list[Paragraph]) -> str:
    """Convert paragraphs to JSON for the LLM prompt."""
    items = []
    for p in paragraphs:
        items.append({
            "paragraph_id": p.paragraph_id,
            "text": p.text,
        })
    return json.dumps(items, separators=(',', ':'))


def _parse_extraction_response(
    raw: list[dict[str, Any]], paragraphs: list[Paragraph]
) -> list[ExtractionResult]:
    """Parse LLM JSON response into ExtractionResult objects."""
    results = []
    para_map = {p.paragraph_id: p for p in paragraphs}

    for item in raw:
        pid = item.get("paragraph_id", "")
        para = para_map.get(pid)
        original_text = para.text if para else ""

        is_argument = item.get("is_argument_carrying", False)
        depth = DepthLevel.FULL if is_argument else DepthLevel.LIGHT

        # Update the paragraph's depth level
        if para:
            para.depth = depth

        result = ExtractionResult(
            paragraph_id=pid,
            original_text=original_text,
            topic_sentence=item.get("topic_sentence", ""),
            function_in_argument=item.get("function_in_argument", ""),
            explicit_claims=item.get("explicit_claims", []),
            implicit_assumptions=item.get("implicit_assumptions", []),
            logical_steps=item.get("logical_steps", []),
            defined_concepts=item.get("defined_concepts", []),
            emotional_tone=item.get("emotional_tone", ""),
            tone_evidence=item.get("tone_evidence", ""),
            internal_references=item.get("internal_references", []),
            depth=depth,
        )
        results.append(result)

    return results


def extract_chapter(
    client: LLMClient,
    chapter: Chapter,
    book_title: str,
    author: str,
    batch_size: int = 5,
    model_override: str | None = None,
) -> list[ExtractionResult]:
    """Extract structural data from all paragraphs in a chapter.

    Processes paragraphs in batches to stay within token limits.

    Args:
        client: LLM client to use.
        chapter: Chapter to extract.
        book_title: Title of the book.
        author: Author of the book.
        batch_size: Number of paragraphs per LLM call.
        model_override: If provided, use this model instead of client's default
            (supports two-tier architecture for cheaper extraction).
    """
    all_results: list[ExtractionResult] = []

    for i in range(0, len(chapter.paragraphs), batch_size):
        batch = chapter.paragraphs[i : i + batch_size]
        batch_ids = [p.paragraph_id for p in batch]
        logger.info(
            "Extracting chapter %d, batch %d-%d: %s",
            chapter.number,
            i + 1,
            min(i + batch_size, len(chapter.paragraphs)),
            batch_ids,
        )

        user_prompt = STRUCTURAL_EXTRACTION_USER.format(
            book_title=book_title,
            author=author,
            chapter_num=f"{chapter.number:02d}",
            chapter_title=chapter.title,
            paragraphs_json=_paragraphs_to_json(batch),
        )

        try:
            response = client.complete_json(
                STRUCTURAL_EXTRACTION_SYSTEM, user_prompt, model_override=model_override
            )
            # Response should be a list
            if isinstance(response, dict) and "paragraphs" in response:
                response = response["paragraphs"]
            if not isinstance(response, list):
                response = [response]

            batch_results = _parse_extraction_response(response, batch)
            all_results.extend(batch_results)
            logger.info(
                "Extracted %d paragraphs from batch", len(batch_results)
            )
        except Exception as e:
            logger.error(
                "Extraction failed for batch %s: %s", batch_ids, e
            )
            # Create minimal results for failed paragraphs
            for p in batch:
                all_results.append(
                    ExtractionResult(
                        paragraph_id=p.paragraph_id,
                        original_text=p.text,
                        topic_sentence="[EXTRACTION FAILED]",
                        function_in_argument="unknown",
                    )
                )

    return all_results
