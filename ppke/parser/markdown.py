"""Markdown book parser with heading-based chapter detection."""

from __future__ import annotations

import re
from pathlib import Path

from ppke.parser.models import Book, Chapter, Paragraph

# Default: ~2000 tokens ≈ ~8000 characters (4 chars/token heuristic)
DEFAULT_MAX_PARAGRAPH_TOKENS = 2000
_CHARS_PER_TOKEN = 4


# Patterns for detecting chapter headings
CHAPTER_PATTERNS = [
    # "# Chapter 1: Title" or "# Chapter One: Title"
    re.compile(r"^#{1,2}\s+chapter\s+(\w+)\s*[:\.\-—–]?\s*(.*)", re.IGNORECASE),
    # "# 1. Title" or "# 1 - Title"
    re.compile(r"^#{1,2}\s+(\d+)\s*[:\.\-—–]\s*(.*)", re.IGNORECASE),
    # "# I. Title" (Roman numerals)
    re.compile(
        r"^#{1,2}\s+(I{1,3}|IV|V|VI{0,3}|IX|X{0,3})\s*[:\.\-—–]\s*(.*)",
        re.IGNORECASE,
    ),
    # Any H1 heading (fallback - treat all H1s as chapters)
    re.compile(r"^#\s+(.+)"),
]

# Words for chapter number detection
WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}

ROMAN_TO_NUM = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
    "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
    "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15,
    "xvi": 16, "xvii": 17, "xviii": 18, "xix": 19, "xx": 20,
}


def _parse_chapter_number(raw: str) -> int | None:
    """Try to extract a chapter number from a raw string."""
    raw = raw.strip().lower()
    if raw.isdigit():
        return int(raw)
    if raw in WORD_TO_NUM:
        return WORD_TO_NUM[raw]
    if raw in ROMAN_TO_NUM:
        return ROMAN_TO_NUM[raw]
    return None


def _detect_chapter_heading(line: str) -> tuple[str, int | None] | None:
    """Check if a line is a chapter heading. Returns (title, chapter_num) or None."""
    stripped = line.strip()
    if not stripped.startswith("#"):
        return None

    # Try specific chapter patterns first
    for i, pattern in enumerate(CHAPTER_PATTERNS[:-1]):
        match = pattern.match(stripped)
        if match:
            groups = match.groups()
            num_str = groups[0]
            title = groups[1].strip() if len(groups) > 1 else ""
            chapter_num = _parse_chapter_number(num_str)
            if not title:
                title = f"Chapter {chapter_num or num_str}"
            return title, chapter_num

    # Fallback: any H1 heading
    fallback = CHAPTER_PATTERNS[-1]
    match = fallback.match(stripped)
    if match:
        title = match.group(1).strip()
        return title, None

    return None


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs by blank lines, filtering out empty ones."""
    blocks = re.split(r"\n\s*\n", text)
    paragraphs = []
    for block in blocks:
        cleaned = block.strip()
        if cleaned and not cleaned.startswith("#"):
            paragraphs.append(cleaned)
    return paragraphs


def parse_markdown_book(
    filepath: str | Path,
    title: str,
    author: str,
    year: str | None = None,
) -> Book:
    """Parse a markdown file into a Book with chapters and paragraphs.

    Chapter boundaries are detected by heading patterns.
    Paragraphs are separated by blank lines within each chapter.
    Each paragraph gets an ID in {CH}.p{P} format.
    """
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8")
    return parse_markdown_text(text, title, author, year, source_path=str(filepath))


def parse_markdown_text(
    text: str,
    title: str,
    author: str,
    year: str | None = None,
    source_path: str | None = None,
) -> Book:
    """Parse markdown text into a Book structure."""
    lines = text.split("\n")

    # Find chapter boundaries
    chapter_boundaries: list[tuple[int, str, int | None]] = []  # (line_idx, title, num)
    for i, line in enumerate(lines):
        result = _detect_chapter_heading(line)
        if result:
            ch_title, ch_num = result
            chapter_boundaries.append((i, ch_title, ch_num))

    book = Book(title=title, author=author, year=year, source_path=source_path)

    if not chapter_boundaries:
        # No chapters detected: treat entire text as one chapter
        paragraphs_text = _split_paragraphs(text)
        chapter = Chapter(number=1, title="Full Text")
        for p_idx, p_text in enumerate(paragraphs_text, start=1):
            chapter.paragraphs.append(
                Paragraph(chapter_number=1, paragraph_number=p_idx, text=p_text)
            )
        book.chapters.append(chapter)
        return book

    # Extract text between chapter boundaries.
    # Track the last assigned number so auto-numbered headings always increment
    # monotonically, even when mixed with explicitly numbered headings.
    _last_ch_num = 0
    for boundary_idx, (line_idx, ch_title, ch_num) in enumerate(chapter_boundaries):
        if ch_num is None:
            # Auto-number: one past the highest chapter number seen so far.
            ch_num = _last_ch_num + 1
        _last_ch_num = max(_last_ch_num, ch_num)

        # Get text from this heading to next heading (or end of file)
        start = line_idx + 1
        if boundary_idx + 1 < len(chapter_boundaries):
            end = chapter_boundaries[boundary_idx + 1][0]
        else:
            end = len(lines)

        chapter_text = "\n".join(lines[start:end])
        paragraphs_text = _split_paragraphs(chapter_text)

        chapter = Chapter(number=ch_num, title=ch_title)
        for p_idx, p_text in enumerate(paragraphs_text, start=1):
            chapter.paragraphs.append(
                Paragraph(
                    chapter_number=ch_num,
                    paragraph_number=p_idx,
                    text=p_text,
                )
            )
        book.chapters.append(chapter)

    return book


def _estimate_tokens(text: str) -> int:
    """Estimate token count using character-based heuristic."""
    return len(text) // _CHARS_PER_TOKEN


def _split_text_at_sentences(text: str, max_chars: int) -> list[str]:
    """Split text into chunks at sentence boundaries, respecting max size."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        sentence_len = len(sentence)
        if current and (current_len + sentence_len + 1) > max_chars:
            chunks.append(" ".join(current))
            current = [sentence]
            current_len = sentence_len
        else:
            current.append(sentence)
            current_len += sentence_len + 1

    if current:
        chunks.append(" ".join(current))

    return chunks


def split_long_paragraphs(
    book: Book,
    max_tokens: int = DEFAULT_MAX_PARAGRAPH_TOKENS,
) -> Book:
    """Split paragraphs that exceed max_tokens into sub-paragraphs.

    Sub-paragraphs get IDs like {03}.p12.1, {03}.p12.2.
    The original paragraph is replaced by its sub-paragraphs in the chapter.
    Returns the modified book (mutated in place).
    """
    max_chars = max_tokens * _CHARS_PER_TOKEN

    for chapter in book.chapters:
        new_paragraphs: list[Paragraph] = []

        for para in chapter.paragraphs:
            if _estimate_tokens(para.text) <= max_tokens:
                new_paragraphs.append(para)
                continue

            # Split this paragraph into sub-paragraphs
            chunks = _split_text_at_sentences(para.text, max_chars)
            if len(chunks) <= 1:
                # Can't split further at sentence level
                new_paragraphs.append(para)
                continue

            for sub_idx, chunk_text in enumerate(chunks, start=1):
                sub_para = Paragraph(
                    chapter_number=para.chapter_number,
                    paragraph_number=para.paragraph_number,
                    text=chunk_text,
                    depth=para.depth,
                    sub_number=sub_idx,
                )
                new_paragraphs.append(sub_para)

        chapter.paragraphs = new_paragraphs

    return book
