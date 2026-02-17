"""Skill 6: Cross-Book Synthesizer - compares concepts and structures across books."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from ppke.llm.client import LLMClient
from ppke.llm.prompts import CROSS_BOOK_SYSTEM, CROSS_BOOK_USER

logger = logging.getLogger(__name__)


def _load_book_analysis(book_dir: Path) -> dict[str, Any] | None:
    """Load the key analysis files from a book directory."""
    meta_path = book_dir / "meta.yml"
    if not meta_path.exists():
        return None

    meta = yaml.safe_load(meta_path.read_text()) or {}

    result: dict[str, Any] = {
        "folder": book_dir.name,
        "title": meta.get("title", "Unknown"),
        "author": meta.get("author", "Unknown"),
    }

    # Load concept index
    concept_path = book_dir / "03_Concept_Index.md"
    if concept_path.exists():
        result["concept_index"] = concept_path.read_text()

    # Load logical map
    logical_path = book_dir / "02_Logical_Map.md"
    if logical_path.exists():
        result["logical_map"] = logical_path.read_text()

    # Load author model
    author_path = book_dir / "04_Author_Model.md"
    if author_path.exists():
        result["author_model"] = author_path.read_text()

    return result


def discover_books(vault_path: Path) -> list[dict[str, Any]]:
    """Find all encoded books in the vault."""
    books = []
    for d in sorted(vault_path.iterdir()):
        if d.is_dir() and d.name.startswith("Book_"):
            analysis = _load_book_analysis(d)
            if analysis:
                books.append(analysis)
    return books


def cross_book_synthesis(
    client: LLMClient,
    vault_path: Path,
    question: str | None = None,
) -> dict[str, Any]:
    """Run cross-book synthesis comparing all encoded books.

    If a question is provided, focus the synthesis on answering it.
    Otherwise, produce a general comparison.

    Returns the synthesis result dict.
    """
    books = discover_books(vault_path)

    if len(books) < 2:
        return {
            "error": f"Need at least 2 encoded books for cross-synthesis. Found {len(books)}.",
            "books_found": [b["folder"] for b in books],
        }

    # Build a condensed summary of each book for the LLM
    book_summaries = []
    for b in books:
        summary = {
            "folder": b["folder"],
            "title": b["title"],
            "author": b["author"],
        }
        # Include key sections (truncated if massive for token limits)
        if "author_model" in b:
            summary["author_model"] = b["author_model"][:3000]
        if "concept_index" in b:
            summary["concept_index"] = b["concept_index"][:3000]
        if "logical_map" in b:
            summary["logical_map"] = b["logical_map"][:2000]
        book_summaries.append(summary)

    user_prompt = CROSS_BOOK_USER.format(
        books_json=json.dumps(book_summaries, indent=1),
        question=question or "Produce a general cross-book synthesis.",
    )

    try:
        result = client.complete_json(CROSS_BOOK_SYSTEM, user_prompt)
        logger.info("Cross-book synthesis complete")
        return result
    except Exception as e:
        logger.error("Cross-book synthesis failed: %s", e)
        return {"error": str(e)}
