"""Vector Database integration for PPKE using ChromaDB.

Provides a fast semantic search layer over all extracted knowledge. Allows
"give me all books mentioning [concept]" queries in milliseconds without
LLM involvement. Used as a first-pass filter before full LLM synthesis.

ChromaDB is an optional dependency. When not installed the store silently
degrades: all write operations are no-ops and search returns an empty list.
Install with:  pip install "ppke[vector]"
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Optional dependency guard
_CHROMA_AVAILABLE = False
try:
    import chromadb  # type: ignore[import]

    _CHROMA_AVAILABLE = True
except ImportError:  # pragma: no cover
    pass

_COLLECTION_NAME = "ppke_extractions"
_BATCH_SIZE = 100  # Max documents per ChromaDB upsert call


class VectorStore:
    """ChromaDB-backed semantic search over PPKE extractions.

    Each document in the collection represents one paragraph extraction,
    with a rich composite text built from topic sentence, claims, concepts,
    and assumptions. Metadata fields (book_folder, author, paragraph_id, …)
    allow fast filtered retrieval.

    Usage::

        store = VectorStore(vault_path)
        if store.available:
            store.index_extractions("Book_Foo_Bar", "Foo", "Bar", extractions)
            hits = store.search("the nature of consciousness", n_results=5)
    """

    def __init__(self, vault_path: Path):
        self._vault_path = vault_path
        self._db_path = vault_path / ".vector_db"
        self._client: Any = None
        self._collection: Any = None

        if not _CHROMA_AVAILABLE:
            logger.debug(
                "chromadb not installed — vector search unavailable. "
                "Install with: pip install chromadb"
            )
            return

        try:
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._db_path))
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to initialise ChromaDB: %s", exc)
            self._client = None
            self._collection = None

    # ── Public API ──

    @property
    def available(self) -> bool:
        """True when ChromaDB is installed and the collection is ready."""
        return _CHROMA_AVAILABLE and self._collection is not None

    def index_extractions(
        self,
        book_folder: str,
        book_title: str,
        author: str,
        extractions: list[dict[str, Any]],
    ) -> int:
        """Index extraction results for a book into the vector store.

        Args:
            book_folder: Vault folder name (used as a metadata filter key).
            book_title: Human-readable title.
            author: Author name.
            extractions: List of extraction dicts (as written to extractions.json).

        Returns:
            Number of documents indexed (0 if unavailable).
        """
        if not self.available:
            return 0

        documents: list[str] = []
        metadatas: list[dict] = []
        ids: list[str] = []
        seen_ids: set[str] = set()

        for ext in extractions:
            pid = ext.get("paragraph_id", "")
            if not pid:
                continue

            doc_id = f"{book_folder}::{pid}"
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)

            # Build a rich composite document for embedding
            parts: list[str] = []
            topic = ext.get("topic_sentence", "")
            if topic and not topic.startswith("["):
                parts.append(topic)
            parts.extend(c for c in ext.get("explicit_claims", []) if c)
            parts.extend(c for c in ext.get("defined_concepts", []) if c)
            parts.extend(a for a in ext.get("implicit_assumptions", []) if a)

            doc_text = " | ".join(parts)
            if not doc_text.strip():
                # Fall back to original text, but skip low-information markers
                original = ext.get("original_text", "")
                if original.strip().startswith("["):
                    continue  # Skip [LOW INFORMATION] / [EXTRACTION FAILED] etc.
                doc_text = original[:500]
            if not doc_text.strip():
                continue

            documents.append(doc_text)
            metadatas.append(
                {
                    "book_folder": book_folder,
                    "book_title": book_title,
                    "author": author,
                    "paragraph_id": pid,
                    "depth": ext.get("depth", "light"),
                    "emotional_tone": ext.get("emotional_tone", ""),
                    "function_in_argument": ext.get("function_in_argument", ""),
                }
            )
            ids.append(doc_id)

        if not documents:
            return 0

        try:
            for i in range(0, len(documents), _BATCH_SIZE):
                self._collection.upsert(
                    documents=documents[i : i + _BATCH_SIZE],
                    metadatas=metadatas[i : i + _BATCH_SIZE],
                    ids=ids[i : i + _BATCH_SIZE],
                )
        except Exception as exc:
            logger.error("Vector store upsert failed: %s", exc)
            return 0

        logger.info(
            "Indexed %d documents for '%s' in vector store", len(documents), book_title
        )
        return len(documents)

    def index_book_from_disk(self, book_dir: Path) -> int:
        """Load extractions.json for a vault directory and index it.

        Convenience method for (re-)indexing an already-ingested book.

        Returns:
            Number of documents indexed, or 0 on failure.
        """
        if not self.available:
            return 0

        import yaml  # local import to keep module load fast

        ext_path = book_dir / "extractions.json"
        meta_path = book_dir / "meta.yml"

        if not ext_path.exists():
            logger.warning("No extractions.json in %s — skipping vector index", book_dir)
            return 0

        try:
            extractions = json.loads(ext_path.read_text())
        except Exception as exc:
            logger.error("Failed to read extractions.json from %s: %s", book_dir, exc)
            return 0

        meta: dict = {}
        if meta_path.exists():
            try:
                meta = yaml.safe_load(meta_path.read_text()) or {}
            except Exception:
                pass

        return self.index_extractions(
            book_folder=book_dir.name,
            book_title=meta.get("title", book_dir.name),
            author=meta.get("author", "Unknown"),
            extractions=extractions,
        )

    def search(
        self,
        query: str,
        n_results: int = 10,
        book_filter: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Semantic search across all indexed extractions.

        This is the "millisecond recall" layer described in the roadmap:
        it finds relevant paragraphs without any LLM calls, returning ranked
        results that can then be sent to the LLM for synthesis.

        Args:
            query: Natural language query / concept name.
            n_results: Maximum results to return.
            book_filter: If set, restrict results to this book_folder.

        Returns:
            List of result dicts, sorted by ascending cosine distance:
            ``[{"paragraph_id", "book_folder", "book_title", "author",
               "distance", "document"}, …]``
        """
        if not self.available:
            return []

        total = self._collection.count()
        if total == 0:
            return []

        where: Optional[dict] = {"book_folder": book_filter} if book_filter else None

        try:
            raw = self._collection.query(
                query_texts=[query],
                n_results=min(n_results, total),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.error("Vector search failed: %s", exc)
            return []

        hits: list[dict[str, Any]] = []
        for doc, meta, dist in zip(
            raw["documents"][0],
            raw["metadatas"][0],
            raw["distances"][0],
        ):
            hits.append(
                {
                    "paragraph_id": meta.get("paragraph_id", "?"),
                    "book_folder": meta.get("book_folder", "?"),
                    "book_title": meta.get("book_title", "?"),
                    "author": meta.get("author", "?"),
                    "distance": round(float(dist), 4),
                    "document": doc,
                }
            )

        return hits

    def count(self) -> int:
        """Return total number of indexed paragraph vectors."""
        if not self.available:
            return 0
        return self._collection.count()

    def delete_book(self, book_folder: str) -> int:
        """Remove all vectors belonging to a book.

        Returns:
            Number of vectors deleted.
        """
        if not self.available:
            return 0
        try:
            existing = self._collection.get(
                where={"book_folder": book_folder},
                include=[],
            )
            ids_to_delete: list[str] = existing.get("ids", [])
            if ids_to_delete:
                self._collection.delete(ids=ids_to_delete)
            return len(ids_to_delete)
        except Exception as exc:
            logger.error("Failed to delete vectors for '%s': %s", book_folder, exc)
            return 0

    def rebuild_index(self, vault_path: Path) -> dict[str, int]:
        """Re-index all books in the vault from scratch.

        Clears the collection and re-indexes every book directory that has
        an extractions.json file.

        Returns:
            Dict mapping book_folder → documents_indexed.
        """
        if not self.available:
            return {}

        # Delete existing collection and recreate
        try:
            assert self._client is not None
            self._client.delete_collection(_COLLECTION_NAME)
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            logger.error("Failed to reset collection: %s", exc)
            return {}

        results: dict[str, int] = {}
        book_dirs = sorted(
            d for d in vault_path.iterdir() if d.is_dir() and d.name.startswith("Book_")
        )
        for book_dir in book_dirs:
            count = self.index_book_from_disk(book_dir)
            results[book_dir.name] = count

        return results
