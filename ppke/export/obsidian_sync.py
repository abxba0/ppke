"""Obsidian / PKM vault synchronization engine.

Provides two-way sync between PPKE's internal data and a local Obsidian
(or compatible PKM) vault directory.  Replaces the one-time ZIP export
with a live, incremental sync that:

* Maps books → ``books/<FolderName>/`` with analysis Markdown files
* Maps concepts → ``concepts/<Name>.md`` with ``[[wikilinks]]``
* Tracks sync state via a JSON manifest (``.ppke_sync_manifest.json``)
* Supports sync-from-vault (import edits back into PPKE)
* Provides status / log information
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Files produced by the PPKE pipeline that should be synced to the vault
_BOOK_FILES = [
    "meta.yml",
    "01_Raw_Structure.md",
    "02_Logical_Map.md",
    "03_Concept_Index.md",
    "04_Author_Model.md",
    "06_Patterns.md",
    "summary.md",
    "study_guide.md",
    "extractions.json",
]

MANIFEST_FILENAME = ".ppke_sync_manifest.json"


# ── Helpers ──


def _content_hash(text: str) -> str:
    """Return a hex SHA-256 digest of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_filename(name: str, max_len: int = 60) -> str:
    """Sanitise a string for use as a filename."""
    safe = re.sub(r'[<>:"/\\|?*]', "-", name)
    return safe[:max_len]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Sync manifest ──


class SyncManifest:
    """Tracks per-file content hashes so we only write changed files."""

    def __init__(self, manifest_path: Path) -> None:
        self.path = manifest_path
        self.entries: dict[str, dict[str, str]] = {}  # rel_path → {hash, synced_at}
        self.last_sync: str | None = None
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self.entries = data.get("files", {})
                self.last_sync = data.get("last_sync")
            except (json.JSONDecodeError, OSError):
                pass

    def needs_update(self, rel_path: str, content: str) -> bool:
        h = _content_hash(content)
        existing = self.entries.get(rel_path)
        if existing and existing.get("hash") == h:
            return False
        return True

    def record(self, rel_path: str, content: str) -> None:
        self.entries[rel_path] = {
            "hash": _content_hash(content),
            "synced_at": _now_iso(),
        }

    def save(self) -> None:
        self.last_sync = _now_iso()
        payload = {"last_sync": self.last_sync, "files": self.entries}
        self.path.write_text(json.dumps(payload, indent=2))


# ── Sync engine ──


class ObsidianSyncEngine:
    """Two-way sync between a PPKE vault and a local Obsidian vault directory.

    Parameters
    ----------
    ppke_vault : Path
        The PPKE data directory (contains ``Book_*`` folders and
        ``knowledge_graph.json``).
    obsidian_vault : Path
        Target Obsidian vault directory (will be created if missing).
    """

    def __init__(self, ppke_vault: Path, obsidian_vault: Path) -> None:
        self.ppke_vault = ppke_vault
        self.obsidian_vault = obsidian_vault
        self._log: list[dict[str, str]] = []

    # ── internal logging ──

    def _record(self, action: str, path: str, detail: str = "") -> None:
        entry = {"ts": _now_iso(), "action": action, "path": path}
        if detail:
            entry["detail"] = detail
        self._log.append(entry)
        logger.info("sync %s: %s %s", action, path, detail)

    # ── public API ──

    def sync_to_vault(self) -> dict[str, Any]:
        """Export / push PPKE data → Obsidian vault (incremental)."""
        self.obsidian_vault.mkdir(parents=True, exist_ok=True)
        manifest = SyncManifest(self.obsidian_vault / MANIFEST_FILENAME)

        written = 0
        skipped = 0

        # 1. Sync books
        bw, bs = self._sync_books(manifest)
        written += bw
        skipped += bs

        # 2. Sync concept notes from knowledge graph
        cw, cs = self._sync_concepts(manifest)
        written += cw
        skipped += cs

        manifest.save()
        return {
            "status": "ok",
            "direction": "to_vault",
            "written": written,
            "skipped": skipped,
            "last_sync": manifest.last_sync,
            "log": self._log,
        }

    def sync_from_vault(self) -> dict[str, Any]:
        """Import edits from Obsidian vault → PPKE data.

        Detects modified Markdown files in the Obsidian ``books/`` tree
        and copies them back to the corresponding PPKE book directory.
        """
        manifest = SyncManifest(self.obsidian_vault / MANIFEST_FILENAME)

        imported = 0
        books_dir = self.obsidian_vault / "books"
        if not books_dir.exists():
            self._record("skip", "books/", "no books directory in vault")
            return {
                "status": "ok",
                "direction": "from_vault",
                "imported": imported,
                "log": self._log,
            }

        for book_folder in sorted(books_dir.iterdir()):
            if not book_folder.is_dir():
                continue
            ppke_book = self.ppke_vault / book_folder.name
            if not ppke_book.exists():
                self._record("skip", book_folder.name, "no matching PPKE book")
                continue

            for md_file in book_folder.glob("*.md"):
                rel = f"books/{book_folder.name}/{md_file.name}"
                vault_content = md_file.read_text()
                # Check if the obsidian version differs from what we last synced
                if not manifest.needs_update(rel, vault_content):
                    continue
                # The user edited this file in Obsidian → copy back
                ppke_target = ppke_book / md_file.name
                ppke_target.write_text(vault_content)
                manifest.record(rel, vault_content)
                self._record("import", rel, "updated from vault")
                imported += 1

        manifest.save()
        return {
            "status": "ok",
            "direction": "from_vault",
            "imported": imported,
            "last_sync": manifest.last_sync,
            "log": self._log,
        }

    def full_sync(self) -> dict[str, Any]:
        """Two-way sync: import vault edits first, then export updates."""
        from_result = self.sync_from_vault()
        to_result = self.sync_to_vault()
        return {
            "status": "ok",
            "direction": "full",
            "imported": from_result.get("imported", 0),
            "written": to_result.get("written", 0),
            "skipped": to_result.get("skipped", 0),
            "last_sync": to_result.get("last_sync"),
            "log": self._log,
        }

    def get_status(self) -> dict[str, Any]:
        """Return current sync status without performing any writes."""
        manifest = SyncManifest(self.obsidian_vault / MANIFEST_FILENAME)
        tracked = len(manifest.entries)
        return {
            "configured": self.obsidian_vault.exists(),
            "ppke_vault": str(self.ppke_vault),
            "obsidian_vault": str(self.obsidian_vault),
            "tracked_files": tracked,
            "last_sync": manifest.last_sync,
        }

    # ── internal sync helpers ──

    def _sync_books(self, manifest: SyncManifest) -> tuple[int, int]:
        """Sync all Book_* folders. Returns (written, skipped)."""
        written = skipped = 0
        if not self.ppke_vault.exists():
            return written, skipped

        for book_dir in sorted(self.ppke_vault.iterdir()):
            if not book_dir.is_dir() or not book_dir.name.startswith("Book_"):
                continue

            target_dir = self.obsidian_vault / "books" / book_dir.name
            target_dir.mkdir(parents=True, exist_ok=True)

            for fname in _BOOK_FILES:
                src = book_dir / fname
                if not src.exists():
                    continue
                content = src.read_text()
                rel = f"books/{book_dir.name}/{fname}"
                if manifest.needs_update(rel, content):
                    (target_dir / fname).write_text(content)
                    manifest.record(rel, content)
                    self._record("write", rel)
                    written += 1
                else:
                    skipped += 1

        return written, skipped

    def _sync_concepts(self, manifest: SyncManifest) -> tuple[int, int]:
        """Sync concept notes from knowledge_graph.json. Returns (written, skipped)."""
        written = skipped = 0
        graph_path = self.ppke_vault / "knowledge_graph.json"
        if not graph_path.exists():
            return written, skipped

        try:
            data = json.loads(graph_path.read_text())
        except (json.JSONDecodeError, OSError):
            return written, skipped

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        labels = {n["id"]: n.get("label", n["id"]) for n in nodes}

        # Build concept → related entries
        relations: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for e in edges:
            src = e.get("src") or e.get("source", "")
            dst = e.get("dst") or e.get("target", "")
            rel = e.get("rel") or e.get("relation", "related_to")
            if src.startswith("concept:"):
                relations[src].append((dst, rel))
            if dst.startswith("concept:"):
                relations[dst].append((src, rel))

        concepts_dir = self.obsidian_vault / "concepts"
        concepts_dir.mkdir(parents=True, exist_ok=True)

        for n in nodes:
            if n.get("type") != "concept":
                continue
            nid = n["id"]
            label = n.get("label", nid)
            books = n.get("books", [])

            lines = [f"# {label}", ""]
            if books:
                lines.append(f"**Books:** {', '.join(books)}")
                lines.append("")

            # Concept-to-concept links (wikilinks)
            concept_links = [
                (other, rel)
                for other, rel in relations.get(nid, [])
                if other.startswith("concept:")
            ]
            if concept_links:
                lines.append("## Related Concepts")
                seen: set[str] = set()
                for other_id, rel in concept_links:
                    other_label = labels.get(other_id, other_id)
                    if other_label in seen:
                        continue
                    seen.add(other_label)
                    lines.append(f"- [[{other_label}]] ({rel})")
                lines.append("")

            # Book links
            book_links = [
                (other, rel)
                for other, rel in relations.get(nid, [])
                if other.startswith("book:")
            ]
            if book_links:
                lines.append("## Sources")
                for other_id, rel in book_links:
                    other_label = labels.get(other_id, other_id)
                    lines.append(f"- {other_label} ({rel})")
                lines.append("")

            content = "\n".join(lines)
            safe_name = _safe_filename(label)
            rel_path = f"concepts/{safe_name}.md"
            if manifest.needs_update(rel_path, content):
                (concepts_dir / f"{safe_name}.md").write_text(content)
                manifest.record(rel_path, content)
                self._record("write", rel_path)
                written += 1
            else:
                skipped += 1

        return written, skipped
