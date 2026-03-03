"""PDF table structure detection — extracts tables as Markdown tables.

Uses pdfplumber for high-fidelity table detection from PDF pages.
Falls back to a simple heuristic (line-count based) when pdfplumber
is not installed.

Install the extra with::

    pip install 'ppke[tables]'
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Public API ──────────────────────────────────────────────────────


def extract_tables_from_pdf(
    pdf_path: Path,
    *,
    pages: list[int] | None = None,
    min_rows: int = 2,
    min_cols: int = 2,
) -> list[dict[str, Any]]:
    """Extract tables from a PDF and return them as structured dicts.

    Each result dict contains:
        - ``page``: 0-based page index
        - ``rows``: list of lists (header + data rows)
        - ``markdown``: pre-rendered Markdown table string
        - ``bbox``: bounding box ``(x0, y0, x1, y1)`` or ``None``

    Parameters
    ----------
    pdf_path:
        Path to the PDF file.
    pages:
        0-based page indices to scan.  ``None`` means all pages.
    min_rows:
        Minimum rows required to consider a detection a table (default 2).
    min_cols:
        Minimum columns required (default 2).
    """
    try:
        return _extract_with_pdfplumber(pdf_path, pages=pages, min_rows=min_rows, min_cols=min_cols)
    except ImportError:
        logger.info("pdfplumber not installed — trying PyMuPDF table extraction")
        try:
            return _extract_with_pymupdf(pdf_path, pages=pages, min_rows=min_rows, min_cols=min_cols)
        except ImportError:
            logger.warning(
                "Neither pdfplumber nor PyMuPDF available for table extraction. "
                "Install with: pip install 'ppke[tables]'"
            )
            return []


def tables_to_markdown(tables: list[dict[str, Any]]) -> str:
    """Render a list of extracted tables as a combined Markdown string.

    Each table gets a ``### Table N (Page M)`` heading followed by a
    Markdown table.
    """
    if not tables:
        return ""

    parts: list[str] = []
    for i, tbl in enumerate(tables, 1):
        page_num = tbl.get("page", 0) + 1
        parts.append(f"### Table {i} (Page {page_num})")
        parts.append("")
        parts.append(tbl.get("markdown", "*(empty table)*"))
        parts.append("")
    return "\n".join(parts)


# ── pdfplumber backend ──────────────────────────────────────────────


def _extract_with_pdfplumber(
    pdf_path: Path,
    *,
    pages: list[int] | None,
    min_rows: int,
    min_cols: int,
) -> list[dict[str, Any]]:
    """Extract tables using pdfplumber's built-in table detection."""
    import pdfplumber  # ImportError propagates to caller

    results: list[dict[str, Any]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        page_indices = pages if pages is not None else range(len(pdf.pages))

        for page_idx in page_indices:
            if page_idx < 0 or page_idx >= len(pdf.pages):
                continue
            page = pdf.pages[page_idx]

            # pdfplumber table settings — tolerate slight imperfections
            table_settings = {
                "vertical_strategy": "lines_strict",
                "horizontal_strategy": "lines_strict",
                "snap_tolerance": 5,
                "join_tolerance": 5,
                "edge_min_length": 10,
                "min_words_vertical": 2,
                "min_words_horizontal": 1,
            }

            try:
                raw_tables = page.extract_tables(table_settings)
            except Exception:
                # Retry with more lenient settings
                table_settings["vertical_strategy"] = "lines"
                table_settings["horizontal_strategy"] = "lines"
                try:
                    raw_tables = page.extract_tables(table_settings)
                except Exception as exc:
                    logger.debug("Table extraction failed on page %d: %s", page_idx + 1, exc)
                    continue

            if not raw_tables:
                # Try text-based strategy as final fallback
                table_settings["vertical_strategy"] = "text"
                table_settings["horizontal_strategy"] = "text"
                try:
                    raw_tables = page.extract_tables(table_settings)
                except Exception:
                    continue

            for raw_table in raw_tables or []:
                if not raw_table:
                    continue

                # Clean cells
                rows = _clean_table_rows(raw_table)
                if len(rows) < min_rows:
                    continue
                if max(len(r) for r in rows) < min_cols:
                    continue

                md = _rows_to_markdown(rows)
                results.append({
                    "page": page_idx,
                    "rows": rows,
                    "markdown": md,
                    "bbox": None,  # pdfplumber doesn't expose per-table bbox easily
                })

    logger.info("Extracted %d table(s) from %s via pdfplumber", len(results), pdf_path.name)
    return results


# ── PyMuPDF backend ─────────────────────────────────────────────────


def _extract_with_pymupdf(
    pdf_path: Path,
    *,
    pages: list[int] | None,
    min_rows: int,
    min_cols: int,
) -> list[dict[str, Any]]:
    """Extract tables using PyMuPDF (fitz) find_tables() (requires PyMuPDF >= 1.23.0)."""
    import fitz  # ImportError propagates

    results: list[dict[str, Any]] = []
    doc = fitz.open(str(pdf_path))

    page_indices = pages if pages is not None else range(len(doc))

    for page_idx in page_indices:
        if page_idx < 0 or page_idx >= len(doc):
            continue
        page = doc[page_idx]

        try:
            tabs = page.find_tables()
        except AttributeError:
            logger.debug("PyMuPDF version too old for find_tables(); skipping table detection")
            doc.close()
            return results
        except Exception as exc:
            logger.debug("find_tables failed on page %d: %s", page_idx + 1, exc)
            continue

        for tab in tabs:
            try:
                raw_rows = tab.extract()
            except Exception:
                continue

            if not raw_rows:
                continue

            rows = _clean_table_rows(raw_rows)
            if len(rows) < min_rows:
                continue
            if max(len(r) for r in rows) < min_cols:
                continue

            bbox = tuple(tab.bbox) if hasattr(tab, "bbox") else None
            md = _rows_to_markdown(rows)
            results.append({
                "page": page_idx,
                "rows": rows,
                "markdown": md,
                "bbox": bbox,
            })

    doc.close()
    logger.info("Extracted %d table(s) from %s via PyMuPDF", len(results), pdf_path.name)
    return results


# ── Shared helpers ──────────────────────────────────────────────────


def _clean_table_rows(raw_rows: list[list[Any]]) -> list[list[str]]:
    """Normalise a list of cell rows: stringify, strip, replace None."""
    cleaned: list[list[str]] = []
    for row in raw_rows:
        cells = [
            str(cell).strip().replace("\n", " ").replace("|", "\\|")
            if cell is not None else ""
            for cell in row
        ]
        # Skip entirely empty rows
        if any(c for c in cells):
            cleaned.append(cells)
    return cleaned


def _rows_to_markdown(rows: list[list[str]]) -> str:
    """Convert a list of rows (first = header) into a Markdown table."""
    if not rows:
        return ""

    # Normalise column count across all rows
    col_count = max(len(r) for r in rows)
    padded = [(r + [""] * col_count)[:col_count] for r in rows]

    header = padded[0]
    separator = ["---"] * col_count
    data = padded[1:]

    lines: list[str] = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in data:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)
