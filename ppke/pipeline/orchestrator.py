"""Master Controller - orchestrates the full book ingestion pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ppke.config import Config
from ppke.llm.client import LLMClient
from ppke.llm.prompts import AUTHOR_MODEL_SYSTEM, AUTHOR_MODEL_USER
from ppke.output.writer import write_all_book_files
from ppke.parser.models import Book, CoverageReport, ExtractionResult
from ppke.pipeline.concepts import build_concept_index
from ppke.pipeline.extractor import extract_chapter
from ppke.pipeline.logical_map import build_logical_map
from ppke.pipeline.patterns import detect_patterns
from ppke.pipeline.validator import validate_chapter_coverage, validate_coverage

logger = logging.getLogger(__name__)


def _build_author_model(
    client: LLMClient,
    book: Book,
    logical_map: dict[str, Any],
    concept_data: dict[str, Any],
    pattern_data: dict[str, Any],
) -> dict[str, Any]:
    """Build author model from all analysis results."""
    user_prompt = AUTHOR_MODEL_USER.format(
        book_title=book.title,
        author=book.author,
        logical_map_json=json.dumps(logical_map, indent=1),
        concept_index_json=json.dumps(concept_data, indent=1),
        patterns_json=json.dumps(pattern_data, indent=1),
    )

    try:
        result = client.complete_json(AUTHOR_MODEL_SYSTEM, user_prompt)
        logger.info("Author model built successfully")
        return result
    except Exception as e:
        logger.error("Failed to build author model: %s", e)
        return {"error": str(e)}


def ingest_book(
    book: Book,
    config: Config,
    progress_callback=None,
) -> Path:
    """Run the full ingestion pipeline for a book.

    Pipeline stages:
    1. Structural extraction (per chapter, batched)
    2. Coverage validation (per chapter + full book)
    3. Logical architecture building
    4. Concept indexing
    5. Pattern detection
    6. Author model generation
    7. Write all output files

    Args:
        book: Parsed Book object.
        config: PPKE configuration.
        progress_callback: Optional callable(stage_name, detail) for progress updates.

    Returns:
        Path to the book's output directory.
    """
    client = LLMClient(config.llm)

    def _progress(stage: str, detail: str = ""):
        if progress_callback:
            progress_callback(stage, detail)
        logger.info("[%s] %s", stage, detail)

    # Stage 1: Structural extraction
    _progress("extraction", f"Processing {len(book.chapters)} chapters")
    all_extractions: list[ExtractionResult] = []

    for chapter in book.chapters:
        _progress(
            "extraction",
            f"Chapter {chapter.number:02d}: {chapter.title} "
            f"({chapter.paragraph_count} paragraphs)",
        )

        chapter_results = extract_chapter(
            client=client,
            chapter=chapter,
            book_title=book.title,
            author=book.author,
            batch_size=config.llm.paragraphs_per_batch,
        )

        # Per-chapter coverage check
        is_complete, missing = validate_chapter_coverage(
            chapter.number,
            [p.paragraph_id for p in chapter.paragraphs],
            chapter_results,
        )
        if not is_complete:
            _progress(
                "validation",
                f"Chapter {chapter.number:02d} incomplete. "
                f"Missing: {missing}. Attempting re-extraction.",
            )
            # Re-extract missing paragraphs
            missing_paras = [
                p for p in chapter.paragraphs if p.paragraph_id in missing
            ]
            if missing_paras:
                from ppke.parser.models import Chapter as Ch

                retry_chapter = Ch(
                    number=chapter.number,
                    title=chapter.title,
                    paragraphs=missing_paras,
                )
                retry_results = extract_chapter(
                    client=client,
                    chapter=retry_chapter,
                    book_title=book.title,
                    author=book.author,
                    batch_size=config.llm.paragraphs_per_batch,
                )
                chapter_results.extend(retry_results)

        all_extractions.extend(chapter_results)

    # Stage 2: Full coverage validation
    _progress("validation", "Running full coverage validation")
    coverage = validate_coverage(book, all_extractions)
    _progress(
        "validation",
        f"Status: {coverage.verification_status} "
        f"({coverage.processed_paragraph_count}/{coverage.total_paragraphs})",
    )

    # Stage 3: Logical architecture
    _progress("logical_map", "Building logical architecture")
    logical_map = build_logical_map(client, all_extractions, book.title, book.author)

    # Stage 4: Concept indexing
    _progress("concepts", "Building concept index")
    concept_data = build_concept_index(client, all_extractions, book.title, book.author)

    # Stage 5: Pattern detection
    _progress("patterns", "Detecting patterns and tensions")
    pattern_data = detect_patterns(client, all_extractions, book.title, book.author)

    # Stage 6: Author model
    _progress("author_model", "Building author model")
    author_model = _build_author_model(
        client, book, logical_map, concept_data, pattern_data
    )

    # Stage 7: Write all files
    _progress("output", f"Writing files to {config.vault_path}")
    book_dir = write_all_book_files(
        vault_path=config.vault_path,
        book=book,
        extractions=all_extractions,
        logical_map=logical_map,
        concept_data=concept_data,
        author_model=author_model,
        coverage=coverage,
    )

    _progress("complete", f"Book ingested: {book_dir}")
    return book_dir
