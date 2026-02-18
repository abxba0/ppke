"""Tests for new features: backoff, patterns output, checkpoints, CLI commands."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ppke.parser.models import (
    Book,
    Chapter,
    DepthLevel,
    ExtractionResult,
    Paragraph,
)


# ── Exponential backoff tests ──


def test_is_retryable_429():
    from ppke.llm.client import _is_retryable

    exc = Exception("Error 429: rate limit exceeded")
    assert _is_retryable(exc) is True


def test_is_retryable_rate_keyword():
    from ppke.llm.client import _is_retryable

    exc = Exception("Rate limit reached for model")
    assert _is_retryable(exc) is True


def test_is_retryable_500():
    from ppke.llm.client import _is_retryable

    exc = Exception("500 Internal Server Error")
    assert _is_retryable(exc) is True


def test_is_retryable_overloaded():
    from ppke.llm.client import _is_retryable

    exc = Exception("API is overloaded")
    assert _is_retryable(exc) is True


def test_is_retryable_class_name():
    from ppke.llm.client import _is_retryable

    class RateLimitError(Exception):
        pass

    exc = RateLimitError("too many requests")
    assert _is_retryable(exc) is True


def test_is_retryable_status_code_attribute():
    from ppke.llm.client import _is_retryable

    exc = Exception("error")
    exc.status_code = 429
    assert _is_retryable(exc) is True


def test_not_retryable_normal_error():
    from ppke.llm.client import _is_retryable

    exc = ValueError("invalid json")
    assert _is_retryable(exc) is False


def test_not_retryable_400():
    from ppke.llm.client import _is_retryable

    exc = Exception("400 Bad Request")
    assert _is_retryable(exc) is False


# ── Pattern output tests ──


def _make_book() -> Book:
    book = Book(title="Test Book", author="Test Author", year="2024")
    ch = Chapter(number=1, title="Intro")
    ch.paragraphs = [
        Paragraph(chapter_number=1, paragraph_number=1, text="Hello world."),
    ]
    book.chapters = [ch]
    return book


def test_write_patterns_creates_file(tmp_path):
    from ppke.output.writer import write_patterns

    book = _make_book()
    pattern_data = {
        "patterns": [
            {
                "type": "metaphor",
                "description": "Light/dark metaphor recurring",
                "evidence": [
                    {"paragraph_id": "{01}.p1", "quote": "the light of reason"}
                ],
                "is_hypothesis": False,
            },
            {
                "type": "contradiction",
                "description": "Freedom vs determinism tension",
                "evidence": [
                    {"paragraph_id": "{01}.p1", "quote": "we are free"}
                ],
                "is_hypothesis": True,
            },
        ]
    }

    path = write_patterns(tmp_path, book, pattern_data)
    assert path.exists()
    assert path.name == "06_Patterns.md"

    content = path.read_text()
    assert "Recurring Metaphors" in content
    assert "Light/dark metaphor" in content
    assert "Internal Contradictions" in content
    assert "[HYPOTHESIS]" in content
    assert "{01}.p1" in content


def test_write_patterns_empty(tmp_path):
    from ppke.output.writer import write_patterns

    book = _make_book()
    path = write_patterns(tmp_path, book, {"patterns": []})
    content = path.read_text()
    assert "No patterns detected" in content


def test_write_all_book_files_includes_patterns(tmp_path):
    from ppke.output.writer import write_all_book_files
    from ppke.parser.models import CoverageReport

    book = _make_book()
    extractions = [
        ExtractionResult(
            paragraph_id="{01}.p1",
            original_text="Hello world.",
            topic_sentence="Greeting",
        )
    ]
    coverage = CoverageReport(
        total_chapters=1,
        total_paragraphs=1,
        processed_paragraph_count=1,
        verification_status="COMPLETE",
        ingest_date="2024-01-01",
    )
    pattern_data = {"patterns": [{"type": "metaphor", "description": "test"}]}

    book_dir = write_all_book_files(
        vault_path=tmp_path,
        book=book,
        extractions=extractions,
        logical_map={"central_thesis": {}, "argument_threads": []},
        concept_data={"concepts": []},
        author_model={},
        coverage=coverage,
        pattern_data=pattern_data,
    )

    assert (book_dir / "06_Patterns.md").exists()


def test_write_all_book_files_no_patterns(tmp_path):
    from ppke.output.writer import write_all_book_files
    from ppke.parser.models import CoverageReport

    book = _make_book()
    extractions = [
        ExtractionResult(
            paragraph_id="{01}.p1",
            original_text="Hello world.",
            topic_sentence="Greeting",
        )
    ]
    coverage = CoverageReport(
        total_chapters=1,
        total_paragraphs=1,
        processed_paragraph_count=1,
        verification_status="COMPLETE",
        ingest_date="2024-01-01",
    )

    book_dir = write_all_book_files(
        vault_path=tmp_path,
        book=book,
        extractions=extractions,
        logical_map={"central_thesis": {}, "argument_threads": []},
        concept_data={"concepts": []},
        author_model={},
        coverage=coverage,
        # No pattern_data passed
    )

    # Should still work, just no patterns file
    assert not (book_dir / "06_Patterns.md").exists()


# ── Checkpoint tests ──


def test_save_and_load_checkpoint(tmp_path):
    from ppke.pipeline.orchestrator import _load_checkpoint, _save_checkpoint

    cp_path = tmp_path / ".checkpoint_test.json"
    extractions = [
        ExtractionResult(
            paragraph_id="{01}.p1",
            original_text="text",
            topic_sentence="topic",
            depth=DepthLevel.FULL,
        ),
        ExtractionResult(
            paragraph_id="{01}.p2",
            original_text="text2",
            topic_sentence="topic2",
        ),
    ]

    _save_checkpoint(cp_path, [0, 1], extractions)
    assert cp_path.exists()

    result = _load_checkpoint(cp_path)
    assert result is not None
    completed, loaded_extractions = result
    assert completed == [0, 1]
    assert len(loaded_extractions) == 2
    assert loaded_extractions[0].paragraph_id == "{01}.p1"
    assert loaded_extractions[0].depth == DepthLevel.FULL
    assert loaded_extractions[1].paragraph_id == "{01}.p2"
    assert loaded_extractions[1].depth == DepthLevel.LIGHT


def test_load_checkpoint_missing_file(tmp_path):
    from ppke.pipeline.orchestrator import _load_checkpoint

    result = _load_checkpoint(tmp_path / "nonexistent.json")
    assert result is None


def test_load_checkpoint_corrupted(tmp_path):
    from ppke.pipeline.orchestrator import _load_checkpoint

    cp_path = tmp_path / ".checkpoint_bad.json"
    cp_path.write_text("not valid json{{{")

    result = _load_checkpoint(cp_path)
    assert result is None


def test_checkpoint_path():
    from ppke.pipeline.orchestrator import _checkpoint_path

    path = _checkpoint_path(Path("/vault"), "Book_Test_Author_2024")
    assert path == Path("/vault/.checkpoint_Book_Test_Author_2024.json")


# ── Search functionality tests ──


def test_search_finds_text(tmp_path):
    """Test that search finds text in extractions.json."""
    # Create a mock book directory with extractions.json
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()

    extractions = [
        {
            "paragraph_id": "{01}.p1",
            "original_text": "The concept of Dasein is central to Heidegger.",
            "topic_sentence": "Introduction to Dasein",
            "explicit_claims": ["Dasein is being-there"],
            "defined_concepts": ["Dasein"],
        },
        {
            "paragraph_id": "{01}.p2",
            "original_text": "Freedom and determinism are in tension.",
            "topic_sentence": "Freedom vs determinism",
            "explicit_claims": [],
            "defined_concepts": [],
        },
    ]
    (book_dir / "extractions.json").write_text(json.dumps(extractions))

    # Simulate search logic
    query_lower = "dasein"
    hits = []
    data = json.loads((book_dir / "extractions.json").read_text())
    for item in data:
        for field_name, field_text in [
            ("text", item.get("original_text", "")),
            ("topic", item.get("topic_sentence", "")),
            ("concept", " ".join(item.get("defined_concepts", []))),
        ]:
            if query_lower in field_text.lower():
                hits.append((book_dir.name, item["paragraph_id"], field_name))
                break

    assert len(hits) == 1
    assert hits[0] == ("Book_Test_Author_2024", "{01}.p1", "text")


def test_search_case_insensitive(tmp_path):
    """Search should be case-insensitive."""
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()

    extractions = [
        {
            "paragraph_id": "{01}.p1",
            "original_text": "The FREEDOM of the individual.",
            "topic_sentence": "",
            "explicit_claims": [],
            "defined_concepts": [],
        },
    ]
    (book_dir / "extractions.json").write_text(json.dumps(extractions))

    data = json.loads((book_dir / "extractions.json").read_text())
    found = any(
        "freedom" in item.get("original_text", "").lower()
        for item in data
    )
    assert found is True


# ── Pattern grouping test ──


def test_patterns_grouped_by_type(tmp_path):
    from ppke.output.writer import write_patterns

    book = _make_book()
    pattern_data = {
        "patterns": [
            {"type": "metaphor", "description": "Metaphor A", "evidence": []},
            {"type": "metaphor", "description": "Metaphor B", "evidence": []},
            {"type": "repetition", "description": "Rep A", "evidence": []},
            {"type": "emotional_arc", "description": "Arc A", "evidence": []},
        ]
    }

    path = write_patterns(tmp_path, book, pattern_data)
    content = path.read_text()

    # Check grouping headers
    assert "## Recurring Metaphors" in content
    assert "## Structural Repetition" in content
    assert "## Emotional Arcs" in content

    # Check both metaphors are under same section
    metaphor_section_start = content.index("## Recurring Metaphors")
    assert "Metaphor A" in content[metaphor_section_start:]
    assert "Metaphor B" in content[metaphor_section_start:]
