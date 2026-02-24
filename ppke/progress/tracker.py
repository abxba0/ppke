"""Progress/Task Tracking System for PPKE ingestion pipeline.

Tracks ingestion progress for books, chapters, and paragraphs.
Persists state to ~/.ppke/progress.json so status survives restarts.
Thread-safe for use with parallel chapter extraction.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

_DEFAULT_PROGRESS_FILE = Path.home() / ".ppke" / "progress.json"
_lock = threading.Lock()


@dataclass
class BookProgress:
    """Progress record for a single book ingestion job."""

    book_folder: str
    title: str
    author: str
    # Status: "queued" | "in_progress" | "complete" | "failed"
    status: str
    total_chapters: int = 0
    completed_chapters: int = 0
    total_paragraphs: int = 0
    completed_paragraphs: int = 0
    current_chapter: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None

    @property
    def chapter_pct(self) -> float:
        """Completion percentage by chapter count (0–100)."""
        if self.total_chapters == 0:
            return 0.0
        return self.completed_chapters / self.total_chapters * 100

    @property
    def paragraph_pct(self) -> float:
        """Completion percentage by paragraph count (0–100)."""
        if self.total_paragraphs == 0:
            return 0.0
        return self.completed_paragraphs / self.total_paragraphs * 100


@dataclass
class ProgressState:
    """Root state persisted to disk."""

    books: dict[str, BookProgress] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize state to a JSON-compatible dictionary."""
        return {"books": {k: asdict(v) for k, v in self.books.items()}}

    @classmethod
    def from_dict(cls, data: dict) -> "ProgressState":
        """Deserialize state from a dictionary."""
        state = cls()
        for k, v in data.get("books", {}).items():
            try:
                state.books[k] = BookProgress(**v)
            except TypeError:
                pass  # Skip malformed records
        return state


class ProgressTracker:
    """Thread-safe progress tracker for the PPKE ingestion pipeline.

    Usage::

        tracker = ProgressTracker()
        tracker.register_book("Book_Foo_Bar_1900", "Foo", "Bar",
                               total_chapters=12, total_paragraphs=340)
        tracker.start_book("Book_Foo_Bar_1900")
        # ... extraction loop ...
        tracker.update_chapter("Book_Foo_Bar_1900", "Chapter 1 - Introduction",
                                completed_chapters=1, completed_paragraphs=28)
        tracker.complete_book("Book_Foo_Bar_1900")

    All mutations are saved to disk immediately.
    """

    def __init__(self, path: Path = _DEFAULT_PROGRESS_FILE):
        self._path = path
        self._state = self._load()

    # ── Persistence ──

    def _load(self) -> ProgressState:
        if not self._path.exists():
            return ProgressState()
        try:
            return ProgressState.from_dict(json.loads(self._path.read_text()))
        except Exception:
            return ProgressState()

    def _save(self) -> None:
        """Write state to disk (caller must hold _lock)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._state.to_dict(), indent=2))

    # ── Mutations ──

    def register_book(
        self,
        book_folder: str,
        title: str,
        author: str,
        total_chapters: int = 0,
        total_paragraphs: int = 0,
    ) -> None:
        """Register a new book job as 'queued'.

        Safe to call multiple times; subsequent calls update counts only if the
        book is still queued (preserves in-progress state on re-run).
        """
        with _lock:
            existing = self._state.books.get(book_folder)
            if existing and existing.status not in ("failed",):
                # Only refresh totals if already registered
                existing.total_chapters = total_chapters
                existing.total_paragraphs = total_paragraphs
            else:
                self._state.books[book_folder] = BookProgress(
                    book_folder=book_folder,
                    title=title,
                    author=author,
                    status="queued",
                    total_chapters=total_chapters,
                    total_paragraphs=total_paragraphs,
                    started_at=datetime.now().isoformat(),
                )
            self._save()

    def start_book(self, book_folder: str) -> None:
        """Mark book as actively being ingested."""
        with _lock:
            if book_folder in self._state.books:
                bp = self._state.books[book_folder]
                bp.status = "in_progress"
                bp.started_at = bp.started_at or datetime.now().isoformat()
                self._save()

    def update_chapter(
        self,
        book_folder: str,
        chapter_title: str,
        completed_chapters: int,
        completed_paragraphs: int,
    ) -> None:
        """Update progress after a chapter completes."""
        with _lock:
            if book_folder in self._state.books:
                bp = self._state.books[book_folder]
                bp.current_chapter = chapter_title
                bp.completed_chapters = completed_chapters
                bp.completed_paragraphs = completed_paragraphs
                self._save()

    def complete_book(self, book_folder: str) -> None:
        """Mark book as fully ingested."""
        with _lock:
            if book_folder in self._state.books:
                bp = self._state.books[book_folder]
                bp.status = "complete"
                bp.completed_at = datetime.now().isoformat()
                bp.current_chapter = None
                bp.completed_chapters = bp.total_chapters
                self._save()

    def fail_book(self, book_folder: str, error: str) -> None:
        """Mark book as failed with an error message."""
        with _lock:
            if book_folder in self._state.books:
                bp = self._state.books[book_folder]
                bp.status = "failed"
                bp.error = error
                self._save()

    # ── Queries ──

    def get_all(self) -> dict[str, BookProgress]:
        """Return a copy of all book progress records."""
        with _lock:
            return dict(self._state.books)

    def get_book(self, book_folder: str) -> Optional[BookProgress]:
        """Return progress for a specific book, or None."""
        return self._state.books.get(book_folder)

    def queued(self) -> list[BookProgress]:
        """Return all books that are waiting to be processed."""
        return [b for b in self._state.books.values() if b.status == "queued"]

    def in_progress(self) -> list[BookProgress]:
        """Return all books currently being processed."""
        return [b for b in self._state.books.values() if b.status == "in_progress"]

    def complete(self) -> list[BookProgress]:
        """Return all successfully completed books."""
        return [b for b in self._state.books.values() if b.status == "complete"]

    def failed(self) -> list[BookProgress]:
        """Return all failed books."""
        return [b for b in self._state.books.values() if b.status == "failed"]

    def clear_completed(self) -> int:
        """Remove completed books from progress records. Returns count removed."""
        with _lock:
            before = len(self._state.books)
            self._state.books = {
                k: v
                for k, v in self._state.books.items()
                if v.status != "complete"
            }
            after = len(self._state.books)
            self._save()
            return before - after

    def summary(self) -> dict:
        """Return a high-level summary dict for display."""
        all_books = list(self._state.books.values())
        return {
            "total": len(all_books),
            "queued": sum(1 for b in all_books if b.status == "queued"),
            "in_progress": sum(1 for b in all_books if b.status == "in_progress"),
            "complete": sum(1 for b in all_books if b.status == "complete"),
            "failed": sum(1 for b in all_books if b.status == "failed"),
            "total_chapters": sum(b.total_chapters for b in all_books),
            "completed_chapters": sum(b.completed_chapters for b in all_books),
            "total_paragraphs": sum(b.total_paragraphs for b in all_books),
            "completed_paragraphs": sum(b.completed_paragraphs for b in all_books),
        }
