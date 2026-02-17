"""Skill 2: Coverage Validator - local logic to verify all paragraphs processed."""

from __future__ import annotations

from datetime import date

from ppke.parser.models import Book, CoverageReport, ExtractionResult


def validate_coverage(
    book: Book,
    extraction_results: list[ExtractionResult],
) -> CoverageReport:
    """Validate that all paragraphs in the book have been processed.

    This is pure local logic - no LLM calls needed.
    """
    expected_ids = set(book.all_paragraph_ids)
    processed_ids = {r.paragraph_id for r in extraction_results}

    missing = sorted(expected_ids - processed_ids)
    extra = sorted(processed_ids - expected_ids)

    report = CoverageReport(
        total_chapters=len(book.chapters),
        total_paragraphs=book.total_paragraphs,
        processed_paragraph_count=len(processed_ids & expected_ids),
        missing_paragraph_ids=missing,
        re_read_pass_completed=False,
        verification_status="COMPLETE" if not missing else "INCOMPLETE",
        ingest_mode="QUALITY_MAX",
        ingest_date=date.today().isoformat(),
    )

    if extra:
        report.notes = f"Extra IDs not in book: {extra}"

    return report


def validate_chapter_coverage(
    chapter_number: int,
    chapter_paragraph_ids: list[str],
    extraction_results: list[ExtractionResult],
) -> tuple[bool, list[str]]:
    """Quick check: did all paragraphs in a chapter get extracted?

    Returns (is_complete, missing_ids).
    """
    expected = set(chapter_paragraph_ids)
    processed = {r.paragraph_id for r in extraction_results}
    missing = sorted(expected - processed)
    return len(missing) == 0, missing
