"""Smart chapter detection via PDF Table of Contents (TOC / bookmarks).

Uses PyMuPDF's ``get_toc()`` API to extract the hierarchical outline
structure from PDF files and split content into chapters accordingly.

This produces more accurate chapter boundaries than heuristic heading
detection, especially for academic papers and textbooks that embed a
proper TOC.

Install::

    pip install 'ppke[ocr]'   # PyMuPDF is included in the ocr extra
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Public types ────────────────────────────────────────────────────

TocEntry = dict[str, Any]
"""A single TOC entry: ``{"level": int, "title": str, "page": int}``."""


# ── Public API ──────────────────────────────────────────────────────


def extract_toc(pdf_path: Path) -> list[TocEntry]:
    """Extract the Table of Contents from a PDF using PyMuPDF.

    Returns a list of entries sorted by page number, each containing:
        - ``level``: heading depth (1 = chapter, 2 = section, etc.)
        - ``title``: heading text
        - ``page``: 1-based page number

    Returns an empty list when no TOC is embedded in the PDF.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError(
            "Smart chapter detection requires PyMuPDF. "
            "Install with: pip install 'ppke[ocr]'"
        )

    doc = fitz.open(str(pdf_path))
    raw_toc = doc.get_toc(simple=True)  # [(level, title, page), …]
    doc.close()

    if not raw_toc:
        logger.debug("No TOC found in %s", pdf_path.name)
        return []

    entries: list[TocEntry] = []
    for level, title, page in raw_toc:
        title = title.strip()
        if not title:
            continue
        entries.append({
            "level": int(level),
            "title": title,
            "page": max(1, int(page)),  # clamp to at least page 1
        })

    logger.info("Extracted TOC with %d entries from %s", len(entries), pdf_path.name)
    return entries


def split_pdf_by_toc(
    pdf_path: Path,
    *,
    max_level: int = 2,
    include_text: bool = True,
) -> list[dict[str, Any]]:
    """Split a PDF into chapters based on its embedded TOC.

    Parameters
    ----------
    pdf_path:
        Path to the PDF file.
    max_level:
        Maximum TOC depth to use as chapter boundaries.
        ``1`` = only top-level chapters.
        ``2`` = chapters + sections (default).
        ``3`` = chapters + sections + subsections.
    include_text:
        When ``True`` (default), each chapter dict includes the
        extracted text from its page range.

    Returns a list of chapter dicts:
        - ``title``: chapter/section title
        - ``level``: heading depth
        - ``start_page``: 1-based start page (inclusive)
        - ``end_page``: 1-based end page (inclusive)
        - ``text``: extracted text (only when ``include_text=True``)
    """
    try:
        import fitz
    except ImportError:
        raise ImportError(
            "Smart chapter detection requires PyMuPDF. "
            "Install with: pip install 'ppke[ocr]'"
        )

    toc = extract_toc(pdf_path)
    if not toc:
        return []

    # Filter by max_level
    filtered = [e for e in toc if e["level"] <= max_level]
    if not filtered:
        filtered = toc[:1]  # Fallback: use first entry

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    chapters: list[dict[str, Any]] = []

    for i, entry in enumerate(filtered):
        start_page = entry["page"]
        # End page = next chapter's start page - 1 (or last page)
        if i + 1 < len(filtered):
            end_page = filtered[i + 1]["page"] - 1
        else:
            end_page = total_pages

        # Ensure valid range
        start_page = max(1, min(start_page, total_pages))
        end_page = max(start_page, min(end_page, total_pages))

        chapter: dict[str, Any] = {
            "title": entry["title"],
            "level": entry["level"],
            "start_page": start_page,
            "end_page": end_page,
        }

        if include_text:
            page_texts: list[str] = []
            for p in range(start_page - 1, end_page):  # fitz is 0-based
                if 0 <= p < total_pages:
                    page = doc[p]
                    page_texts.append(page.get_text("text").strip())
            chapter["text"] = "\n\n".join(t for t in page_texts if t)

        chapters.append(chapter)

    doc.close()
    logger.info("Split %s into %d chapters via TOC", pdf_path.name, len(chapters))
    return chapters


def toc_to_markdown(toc: list[TocEntry]) -> str:
    """Render a TOC as a Markdown outline (indented list).

    Useful for showing the user what structure was detected.
    """
    if not toc:
        return "*(No table of contents detected)*"

    lines: list[str] = ["## Table of Contents", ""]
    for entry in toc:
        indent = "  " * (entry["level"] - 1)
        lines.append(f"{indent}- {entry['title']} (p. {entry['page']})")
    return "\n".join(lines)


def convert_pdf_with_chapters(pdf_path: Path) -> str:
    """Convert a PDF to Markdown using TOC-based chapter detection.

    Falls back to the standard page-by-page conversion when no TOC
    is available.  This function is meant to be called from the
    converter registry as an enhancement to ``_convert_pdf()``.

    Returns Markdown with proper heading hierarchy derived from the TOC.
    """
    chapters = split_pdf_by_toc(pdf_path, max_level=3, include_text=True)

    if not chapters:
        return ""  # Caller should fall back to standard conversion

    title = pdf_path.stem.replace("_", " ").replace("-", " ").title()
    parts: list[str] = [f"# {title}", ""]

    # Include TOC outline
    toc = extract_toc(pdf_path)
    if toc:
        parts.append(toc_to_markdown(toc))
        parts.append("")
        parts.append("---")
        parts.append("")

    # Render each chapter
    for ch in chapters:
        level = ch["level"]
        heading_prefix = "#" * (level + 1)  # TOC level 1 → ## heading
        parts.append(f"{heading_prefix} {ch['title']}")
        parts.append("")
        if ch.get("text"):
            parts.append(ch["text"])
            parts.append("")
        parts.append(f"*(Pages {ch['start_page']}–{ch['end_page']})*")
        parts.append("")

    return "\n".join(parts)
