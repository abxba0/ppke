"""Tests for the coverage validator."""

from ppke.parser.models import Book, Chapter, CoverageReport, ExtractionResult, Paragraph
from ppke.pipeline.validator import (
    EXTRACTION_FAILED_MARKER,
    validate_chapter_coverage,
    validate_coverage,
)


def _make_book() -> Book:
    """Create a simple test book."""
    book = Book(title="Test", author="Author")
    ch1 = Chapter(number=1, title="Chapter One")
    ch1.paragraphs = [
        Paragraph(chapter_number=1, paragraph_number=1, text="Para 1"),
        Paragraph(chapter_number=1, paragraph_number=2, text="Para 2"),
        Paragraph(chapter_number=1, paragraph_number=3, text="Para 3"),
    ]
    ch2 = Chapter(number=2, title="Chapter Two")
    ch2.paragraphs = [
        Paragraph(chapter_number=2, paragraph_number=1, text="Para 1 ch2"),
        Paragraph(chapter_number=2, paragraph_number=2, text="Para 2 ch2"),
    ]
    book.chapters = [ch1, ch2]
    return book


def _make_extraction(pid: str, failed: bool = False) -> ExtractionResult:
    topic = EXTRACTION_FAILED_MARKER if failed else "Some topic"
    return ExtractionResult(paragraph_id=pid, original_text="text", topic_sentence=topic)


def test_complete_coverage():
    book = _make_book()
    extractions = [
        _make_extraction("{01}.p1"),
        _make_extraction("{01}.p2"),
        _make_extraction("{01}.p3"),
        _make_extraction("{02}.p1"),
        _make_extraction("{02}.p2"),
    ]
    report = validate_coverage(book, extractions)
    assert report.verification_status == "COMPLETE"
    assert report.processed_paragraph_count == 5
    assert report.missing_paragraph_ids == []


def test_incomplete_coverage_missing():
    book = _make_book()
    extractions = [
        _make_extraction("{01}.p1"),
        _make_extraction("{01}.p3"),
        _make_extraction("{02}.p1"),
    ]
    report = validate_coverage(book, extractions)
    assert report.verification_status == "INCOMPLETE"
    assert report.processed_paragraph_count == 3
    assert "{01}.p2" in report.missing_paragraph_ids
    assert "{02}.p2" in report.missing_paragraph_ids


def test_failed_extraction_not_counted():
    """Failed extractions should NOT count as processed."""
    book = _make_book()
    extractions = [
        _make_extraction("{01}.p1"),
        _make_extraction("{01}.p2", failed=True),  # Failed!
        _make_extraction("{01}.p3"),
        _make_extraction("{02}.p1"),
        _make_extraction("{02}.p2"),
    ]
    report = validate_coverage(book, extractions)
    assert report.verification_status == "INCOMPLETE"
    assert report.processed_paragraph_count == 4
    assert "{01}.p2" in report.missing_paragraph_ids
    assert "Extraction failed" in report.notes


def test_chapter_coverage_complete():
    ids = ["{01}.p1", "{01}.p2", "{01}.p3"]
    extractions = [_make_extraction(pid) for pid in ids]
    is_complete, missing = validate_chapter_coverage(1, ids, extractions)
    assert is_complete is True
    assert missing == []


def test_chapter_coverage_incomplete():
    ids = ["{01}.p1", "{01}.p2", "{01}.p3"]
    extractions = [_make_extraction("{01}.p1"), _make_extraction("{01}.p3")]
    is_complete, missing = validate_chapter_coverage(1, ids, extractions)
    assert is_complete is False
    assert "{01}.p2" in missing


def test_chapter_coverage_failed_counts_as_missing():
    ids = ["{01}.p1", "{01}.p2"]
    extractions = [
        _make_extraction("{01}.p1"),
        _make_extraction("{01}.p2", failed=True),
    ]
    is_complete, missing = validate_chapter_coverage(1, ids, extractions)
    assert is_complete is False
    assert "{01}.p2" in missing


def test_extra_ids_noted():
    book = _make_book()
    extractions = [
        _make_extraction("{01}.p1"),
        _make_extraction("{01}.p2"),
        _make_extraction("{01}.p3"),
        _make_extraction("{02}.p1"),
        _make_extraction("{02}.p2"),
        _make_extraction("{99}.p1"),  # Extra!
    ]
    report = validate_coverage(book, extractions)
    assert report.verification_status == "COMPLETE"
    assert "Extra IDs" in report.notes


def test_coverage_report_fields():
    book = _make_book()
    extractions = [_make_extraction(pid) for pid in book.all_paragraph_ids]
    report = validate_coverage(book, extractions)
    assert report.total_chapters == 2
    assert report.total_paragraphs == 5
    assert report.ingest_mode == "QUALITY_MAX"
    assert report.ingest_date  # Should be set
    assert report.re_read_pass_completed is False
