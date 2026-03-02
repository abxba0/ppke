"""Hybrid search: combines full-text and vector-based retrieval.

Provides a unified search interface that merges results from:
  1. Full-text keyword matching across ``extractions.json`` files on disk.
  2. Vector similarity search via :class:`ppke.vectordb.store.VectorStore`.

Results are deduplicated by ``(book_folder, paragraph_id)`` and ranked using
a weighted combination of text-match and vector-distance scores.  When only
one backend is available the module degrades gracefully to that single source.

Usage::

    from ppke.search import hybrid_search, fulltext_search

    hits = hybrid_search(vault_path, "free will", n_results=10)
    text_hits = fulltext_search(vault_path, "Dasein")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------


def fulltext_search(
    vault_path: Path,
    query: str,
    *,
    book_filter: Optional[str] = None,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """Case-insensitive substring search over vault extractions on disk.

    Searches ``original_text``, ``topic_sentence``, ``explicit_claims``, and
    ``defined_concepts`` fields inside every book's ``extractions.json``.

    Args:
        vault_path: Root vault directory.
        query: Search string (case-insensitive).
        book_filter: If set, restrict results to this book folder name.
        max_results: Maximum number of results to return.

    Returns:
        List of result dicts with keys: ``paragraph_id``, ``book_folder``,
        ``book_title``, ``author``, ``document``, ``field``, ``snippet``,
        ``score`` (1.0 for exact substring match).
    """
    if not query:
        return []

    query_lower = query.lower()
    hits: list[dict[str, Any]] = []

    if not vault_path.exists():
        return hits

    book_dirs = sorted(
        d for d in vault_path.iterdir() if d.is_dir() and d.name.startswith("Book_")
    )

    for bd in book_dirs:
        if book_filter and bd.name != book_filter:
            continue

        ext_path = bd / "extractions.json"
        if not ext_path.exists():
            continue
        try:
            data = json.loads(ext_path.read_text())
        except Exception:
            continue

        # Try to load meta for title/author
        meta: dict = {}
        meta_path = bd / "meta.yml"
        if meta_path.exists():
            try:
                import yaml

                meta = yaml.safe_load(meta_path.read_text()) or {}
            except Exception:
                pass

        book_title = meta.get("title", bd.name)
        author = meta.get("author", "Unknown")

        for item in data:
            pid = item.get("paragraph_id", "?")
            original = item.get("original_text", "")
            topic = item.get("topic_sentence", "")
            claims = " ".join(item.get("explicit_claims", []))
            concepts = " ".join(item.get("defined_concepts", []))

            for field_name, field_text in [
                ("text", original),
                ("topic", topic),
                ("claim", claims),
                ("concept", concepts),
            ]:
                field_lower = field_text.lower()
                if query_lower in field_lower:
                    idx = field_lower.index(query_lower)
                    start = max(0, idx - 60)
                    end = min(len(field_text), idx + len(query) + 60)
                    snippet = field_text[start:end]
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(field_text):
                        snippet = snippet + "..."

                    # Use original_text (or topic) as the document text
                    doc_text = original[:300] if original else topic[:300]

                    hits.append(
                        {
                            "paragraph_id": pid,
                            "book_folder": bd.name,
                            "book_title": book_title,
                            "author": author,
                            "document": doc_text,
                            "field": field_name,
                            "snippet": snippet,
                            "score": 1.0,
                            "source": "fulltext",
                        }
                    )
                    break  # one hit per paragraph

            if len(hits) >= max_results:
                break
        if len(hits) >= max_results:
            break

    return hits


# ---------------------------------------------------------------------------
# Hybrid search
# ---------------------------------------------------------------------------

_DEFAULT_VECTOR_WEIGHT = 0.6
_DEFAULT_TEXT_WEIGHT = 0.4


def hybrid_search(
    vault_path: Path,
    query: str,
    *,
    book_filter: Optional[str] = None,
    n_results: int = 10,
    vector_weight: float = _DEFAULT_VECTOR_WEIGHT,
    text_weight: float = _DEFAULT_TEXT_WEIGHT,
) -> list[dict[str, Any]]:
    """Combined full-text and vector search with relevance ranking.

    Runs both search backends, normalises their scores into ``[0, 1]``,
    merges results by ``(book_folder, paragraph_id)``, and returns a single
    ranked list.

    When ChromaDB is unavailable the function falls back to pure full-text
    search.  When no extractions exist on disk it falls back to pure vector
    search.

    Args:
        vault_path: Root vault directory.
        query: Natural language search query.
        book_filter: Optional book folder name to restrict search.
        n_results: Maximum results to return.
        vector_weight: Weight for vector similarity score (0–1).
        text_weight: Weight for full-text match score (0–1).

    Returns:
        Merged list of result dicts sorted by descending combined score.
        Each dict contains: ``paragraph_id``, ``book_folder``, ``book_title``,
        ``author``, ``document``, ``score``, ``source``
        (``"hybrid"``, ``"vector"``, or ``"fulltext"``).
    """
    # -- Full-text results ---------------------------------------------------
    text_hits = fulltext_search(
        vault_path,
        query,
        book_filter=book_filter,
        max_results=n_results * 3,  # over-fetch for merge
    )

    # -- Vector results ------------------------------------------------------
    vector_hits: list[dict[str, Any]] = []
    try:
        from ppke.vectordb.store import VectorStore

        store = VectorStore(vault_path)
        if store.available:
            vector_hits = store.search(
                query,
                n_results=n_results * 3,
                book_filter=book_filter,
            )
    except Exception as exc:
        logger.debug("Vector search skipped during hybrid: %s", exc)

    # -- Merge & deduplicate -------------------------------------------------
    merged: dict[str, dict[str, Any]] = {}  # key = "book_folder::paragraph_id"

    # Normalise vector distances → scores (cosine distance in [0, 2])
    for hit in vector_hits:
        key = f"{hit['book_folder']}::{hit['paragraph_id']}"
        # Convert cosine distance to similarity score in [0, 1]
        vscore = max(0.0, 1.0 - hit.get("distance", 1.0))
        entry = {
            "paragraph_id": hit["paragraph_id"],
            "book_folder": hit["book_folder"],
            "book_title": hit.get("book_title", "?"),
            "author": hit.get("author", "?"),
            "document": hit.get("document", ""),
            "vector_score": vscore,
            "text_score": 0.0,
            "source": "vector",
        }
        merged[key] = entry

    for hit in text_hits:
        key = f"{hit['book_folder']}::{hit['paragraph_id']}"
        tscore = hit.get("score", 1.0)
        if key in merged:
            merged[key]["text_score"] = tscore
            merged[key]["source"] = "hybrid"
            # Keep richer document text if available
            if hit.get("document") and len(hit["document"]) > len(
                merged[key].get("document", "")
            ):
                merged[key]["document"] = hit["document"]
        else:
            merged[key] = {
                "paragraph_id": hit["paragraph_id"],
                "book_folder": hit["book_folder"],
                "book_title": hit.get("book_title", "?"),
                "author": hit.get("author", "?"),
                "document": hit.get("document", ""),
                "vector_score": 0.0,
                "text_score": tscore,
                "source": "fulltext",
            }

    # -- Combined scoring & ranking ------------------------------------------
    results: list[dict[str, Any]] = []
    for entry in merged.values():
        combined = (
            vector_weight * entry["vector_score"]
            + text_weight * entry["text_score"]
        )
        results.append(
            {
                "paragraph_id": entry["paragraph_id"],
                "book_folder": entry["book_folder"],
                "book_title": entry["book_title"],
                "author": entry["author"],
                "document": entry["document"],
                "score": round(combined, 4),
                "source": entry["source"],
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:n_results]
