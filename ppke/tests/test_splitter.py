"""Tests for paragraph splitting and sub-paragraph IDs."""

from ppke.parser.markdown import (
    _estimate_tokens,
    _split_text_at_sentences,
    parse_markdown_text,
    split_long_paragraphs,
)
from ppke.parser.models import Paragraph


def test_estimate_tokens():
    # ~4 chars per token
    assert _estimate_tokens("abcd") == 1
    assert _estimate_tokens("a" * 400) == 100


def test_split_text_at_sentences_under_limit():
    text = "First sentence. Second sentence. Third sentence."
    chunks = _split_text_at_sentences(text, max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_at_sentences_over_limit():
    s1 = "A" * 50 + "."
    s2 = "B" * 50 + "."
    s3 = "C" * 50 + "."
    text = f"{s1} {s2} {s3}"
    chunks = _split_text_at_sentences(text, max_chars=110)
    assert len(chunks) >= 2
    # All text is preserved
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_sub_paragraph_id():
    p = Paragraph(chapter_number=3, paragraph_number=12, text="hello", sub_number=1)
    assert p.paragraph_id == "{03}.p12.1"


def test_sub_paragraph_id_none():
    p = Paragraph(chapter_number=3, paragraph_number=12, text="hello")
    assert p.paragraph_id == "{03}.p12"


def test_split_long_paragraphs_no_split_needed():
    text = "# Chapter 1: Intro\n\nShort paragraph.\n\nAnother short one."
    book = parse_markdown_text(text, "Test", "Author")
    original_count = book.total_paragraphs
    split_long_paragraphs(book, max_tokens=2000)
    assert book.total_paragraphs == original_count
    # No sub_number set
    for p in book.all_paragraphs:
        assert p.sub_number is None


def test_split_long_paragraphs_splits_when_needed():
    # Create a paragraph that's very long (~4000 tokens = ~16000 chars)
    long_text = ". ".join(["This is sentence number " + str(i) for i in range(500)])
    text = f"# Chapter 1: Test\n\n{long_text}"
    book = parse_markdown_text(text, "Test", "Author")
    assert book.total_paragraphs == 1  # One big paragraph

    split_long_paragraphs(book, max_tokens=500)  # Low threshold to force split
    assert book.total_paragraphs > 1

    # All sub-paragraphs have sub_number set
    for p in book.all_paragraphs:
        assert p.sub_number is not None

    # IDs follow the {CH}.p{P}.{S} pattern
    ids = book.all_paragraph_ids
    assert ids[0] == "{01}.p1.1"
    assert ids[1] == "{01}.p1.2"


def test_split_preserves_chapter_number():
    long_text = ". ".join(["Sentence " + str(i) for i in range(300)])
    text = f"# Chapter 5: Deep\n\n{long_text}"
    book = parse_markdown_text(text, "Test", "Author")
    split_long_paragraphs(book, max_tokens=200)

    for p in book.all_paragraphs:
        assert p.chapter_number == 5
        assert p.paragraph_number == 1
        assert p.sub_number is not None
