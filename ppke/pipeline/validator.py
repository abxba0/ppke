"""Skill 2: Coverage Validator - local logic to verify all paragraphs processed."""

from __future__ import annotations

from datetime import date

from ppke.parser.models import Book, CoverageReport, ExtractionResult

# Sentinel indicating an extraction failed for a paragraph
EXTRACTION_FAILED_MARKER = "[EXTRACTION FAILED]"


def validate_coverage(
    book: Book,
    extraction_results: list[ExtractionResult],
) -> CoverageReport:
    """Validate that all paragraphs in the book have been processed.

    A paragraph is only considered "processed" if:
    1. It has a matching ExtractionResult
    2. That result was NOT a failure placeholder

    This is pure local logic - no LLM calls needed.
    """
    expected_ids = set(book.all_paragraph_ids)
    result_map = {r.paragraph_id: r for r in extraction_results}

    # Only count paragraphs that were genuinely extracted (not failed)
    processed_ids = set()
    failed_ids = []
    for pid, result in result_map.items():
        if pid in expected_ids:
            if result.topic_sentence == EXTRACTION_FAILED_MARKER:
                failed_ids.append(pid)
            else:
                processed_ids.add(pid)

    missing = sorted(expected_ids - processed_ids)
    extra = sorted(set(result_map.keys()) - expected_ids)

    notes_parts = []
    if extra:
        notes_parts.append(f"Extra IDs not in book: {extra}")
    if failed_ids:
        notes_parts.append(f"Extraction failed for: {sorted(failed_ids)}")

    report = CoverageReport(
        total_chapters=len(book.chapters),
        total_paragraphs=book.total_paragraphs,
        processed_paragraph_count=len(processed_ids),
        missing_paragraph_ids=missing,
        re_read_pass_completed=False,
        verification_status="COMPLETE" if not missing else "INCOMPLETE",
        ingest_mode="QUALITY_MAX",
        ingest_date=date.today().isoformat(),
        notes="; ".join(notes_parts) if notes_parts else "",
    )

    return report


def validate_chapter_coverage(
    chapter_number: int,
    chapter_paragraph_ids: list[str],
    extraction_results: list[ExtractionResult],
) -> tuple[bool, list[str]]:
    """Quick check: did all paragraphs in a chapter get extracted successfully?

    Returns (is_complete, missing_ids).
    Failed extractions count as missing.
    """
    expected = set(chapter_paragraph_ids)
    processed = set()
    for r in extraction_results:
        if r.paragraph_id in expected and r.topic_sentence != EXTRACTION_FAILED_MARKER:
            processed.add(r.paragraph_id)
    missing = sorted(expected - processed)
    return len(missing) == 0, missing
