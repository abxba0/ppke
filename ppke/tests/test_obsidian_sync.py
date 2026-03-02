"""Tests for ppke.export.obsidian_sync — Obsidian vault synchronization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


# ── Fixtures ──


@pytest.fixture()
def ppke_vault(tmp_path):
    """Create a minimal PPKE vault with one book and a knowledge graph."""
    vault = tmp_path / "ppke_data"
    vault.mkdir()

    # Book directory
    book = vault / "Book_SyncTest"
    book.mkdir()
    meta = {"title": "Sync Test Book", "author": "Tester", "year": 2025}
    (book / "meta.yml").write_text(yaml.dump(meta))
    (book / "summary.md").write_text("# Summary\n\nTest summary content.")
    (book / "01_Raw_Structure.md").write_text("# Structure\n\nChapter 1.")
    (book / "extractions.json").write_text(json.dumps([
        {"paragraph_id": "{01}.{01}", "topic_sentence": "Test topic",
         "defined_concepts": ["alpha"]}
    ]))

    # Knowledge graph
    graph = {
        "nodes": [
            {"id": "concept:alpha", "label": "Alpha", "type": "concept", "books": ["Sync Test Book"]},
            {"id": "concept:beta", "label": "Beta", "type": "concept", "books": ["Sync Test Book"]},
            {"id": "book:sync_test", "label": "Sync Test Book", "type": "book"},
        ],
        "edges": [
            {"src": "concept:alpha", "dst": "concept:beta", "rel": "related_to"},
            {"src": "concept:alpha", "dst": "book:sync_test", "rel": "defined_in"},
        ],
    }
    (vault / "knowledge_graph.json").write_text(json.dumps(graph))
    return vault


@pytest.fixture()
def obsidian_vault(tmp_path):
    """Target directory for Obsidian vault output."""
    return tmp_path / "obsidian_vault"


# ══════════════════════════════════════════════════════════════
# SyncManifest
# ══════════════════════════════════════════════════════════════


class TestSyncManifest:
    def test_empty_manifest(self, tmp_path):
        from ppke.export.obsidian_sync import SyncManifest

        m = SyncManifest(tmp_path / ".ppke_sync_manifest.json")
        assert m.entries == {}
        assert m.last_sync is None

    def test_needs_update_new_file(self, tmp_path):
        from ppke.export.obsidian_sync import SyncManifest

        m = SyncManifest(tmp_path / ".ppke_sync_manifest.json")
        assert m.needs_update("test.md", "hello") is True

    def test_needs_update_unchanged(self, tmp_path):
        from ppke.export.obsidian_sync import SyncManifest

        m = SyncManifest(tmp_path / ".ppke_sync_manifest.json")
        m.record("test.md", "hello")
        assert m.needs_update("test.md", "hello") is False

    def test_needs_update_changed(self, tmp_path):
        from ppke.export.obsidian_sync import SyncManifest

        m = SyncManifest(tmp_path / ".ppke_sync_manifest.json")
        m.record("test.md", "hello")
        assert m.needs_update("test.md", "world") is True

    def test_save_and_reload(self, tmp_path):
        from ppke.export.obsidian_sync import SyncManifest

        m = SyncManifest(tmp_path / ".ppke_sync_manifest.json")
        m.record("a.md", "content")
        m.save()

        m2 = SyncManifest(tmp_path / ".ppke_sync_manifest.json")
        assert "a.md" in m2.entries
        assert m2.last_sync is not None

    def test_corrupt_manifest(self, tmp_path):
        from ppke.export.obsidian_sync import SyncManifest

        path = tmp_path / ".ppke_sync_manifest.json"
        path.write_text("not json")
        m = SyncManifest(path)
        assert m.entries == {}


# ══════════════════════════════════════════════════════════════
# ObsidianSyncEngine — sync_to_vault
# ══════════════════════════════════════════════════════════════


class TestSyncToVault:
    def test_creates_vault_directory(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        result = engine.sync_to_vault()

        assert result["status"] == "ok"
        assert result["direction"] == "to_vault"
        assert obsidian_vault.exists()

    def test_syncs_book_files(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        result = engine.sync_to_vault()

        book_dir = obsidian_vault / "books" / "Book_SyncTest"
        assert book_dir.exists()
        assert (book_dir / "meta.yml").exists()
        assert (book_dir / "summary.md").exists()
        assert (book_dir / "01_Raw_Structure.md").exists()
        assert result["written"] > 0

    def test_syncs_concept_notes(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        engine.sync_to_vault()

        concepts_dir = obsidian_vault / "concepts"
        assert concepts_dir.exists()
        alpha_file = concepts_dir / "Alpha.md"
        assert alpha_file.exists()
        content = alpha_file.read_text()
        assert "# Alpha" in content
        assert "[[Beta]]" in content

    def test_incremental_skip(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        r1 = engine.sync_to_vault()
        assert r1["written"] > 0

        engine2 = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        r2 = engine2.sync_to_vault()
        assert r2["written"] == 0
        assert r2["skipped"] > 0

    def test_detects_changes(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        engine.sync_to_vault()

        # Modify a source file
        (ppke_vault / "Book_SyncTest" / "summary.md").write_text("# Updated Summary")

        engine2 = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        r2 = engine2.sync_to_vault()
        assert r2["written"] >= 1

    def test_empty_vault(self, tmp_path, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        empty_vault = tmp_path / "empty"
        empty_vault.mkdir()
        engine = ObsidianSyncEngine(empty_vault, obsidian_vault)
        result = engine.sync_to_vault()
        assert result["status"] == "ok"
        assert result["written"] == 0

    def test_no_knowledge_graph(self, tmp_path, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        vault = tmp_path / "no_graph"
        vault.mkdir()
        book = vault / "Book_X"
        book.mkdir()
        (book / "meta.yml").write_text(yaml.dump({"title": "X"}))

        engine = ObsidianSyncEngine(vault, obsidian_vault)
        result = engine.sync_to_vault()
        assert result["status"] == "ok"
        # Book files synced, but no concepts
        assert result["written"] >= 1


# ══════════════════════════════════════════════════════════════
# ObsidianSyncEngine — sync_from_vault
# ══════════════════════════════════════════════════════════════


class TestSyncFromVault:
    def test_import_edited_file(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        # First sync out
        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        engine.sync_to_vault()

        # Simulate user editing a file in Obsidian
        vault_summary = obsidian_vault / "books" / "Book_SyncTest" / "summary.md"
        vault_summary.write_text("# Edited Summary\n\nUser added notes here.")

        # Sync back
        engine2 = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        result = engine2.sync_from_vault()
        assert result["status"] == "ok"
        assert result["imported"] >= 1

        # Verify PPKE side is updated
        ppke_summary = ppke_vault / "Book_SyncTest" / "summary.md"
        assert "Edited Summary" in ppke_summary.read_text()

    def test_no_books_dir(self, ppke_vault, tmp_path):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        empty_obsidian = tmp_path / "empty_obs"
        empty_obsidian.mkdir()
        engine = ObsidianSyncEngine(ppke_vault, empty_obsidian)
        result = engine.sync_from_vault()
        assert result["status"] == "ok"
        assert result["imported"] == 0

    def test_skip_unmatched_book(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        # Create a book dir in Obsidian that doesn't exist in PPKE
        books = obsidian_vault / "books" / "Book_Unknown"
        books.mkdir(parents=True)
        (books / "notes.md").write_text("Some notes")

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        result = engine.sync_from_vault()
        assert result["imported"] == 0


# ══════════════════════════════════════════════════════════════
# ObsidianSyncEngine — full_sync
# ══════════════════════════════════════════════════════════════


class TestFullSync:
    def test_full_sync_both_directions(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        # Initial sync out
        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        engine.sync_to_vault()

        # Edit in Obsidian
        (obsidian_vault / "books" / "Book_SyncTest" / "summary.md").write_text(
            "# User Edited"
        )
        # Edit in PPKE
        (ppke_vault / "Book_SyncTest" / "01_Raw_Structure.md").write_text(
            "# New Structure"
        )

        engine2 = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        result = engine2.full_sync()

        assert result["status"] == "ok"
        assert result["direction"] == "full"
        assert result["imported"] >= 1
        assert result["written"] >= 1

    def test_full_sync_log(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        result = engine.full_sync()
        assert "log" in result
        assert isinstance(result["log"], list)


# ══════════════════════════════════════════════════════════════
# ObsidianSyncEngine — get_status
# ══════════════════════════════════════════════════════════════


class TestGetStatus:
    def test_status_before_sync(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        status = engine.get_status()
        assert status["configured"] is False
        assert status["tracked_files"] == 0
        assert status["last_sync"] is None

    def test_status_after_sync(self, ppke_vault, obsidian_vault):
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        engine.sync_to_vault()

        status = engine.get_status()
        assert status["configured"] is True
        assert status["tracked_files"] > 0
        assert status["last_sync"] is not None


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════


class TestHelpers:
    def test_content_hash(self):
        from ppke.export.obsidian_sync import _content_hash

        h1 = _content_hash("hello")
        h2 = _content_hash("hello")
        h3 = _content_hash("world")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64  # SHA-256 hex digest

    def test_safe_filename(self):
        from ppke.export.obsidian_sync import _safe_filename

        assert _safe_filename("normal") == "normal"
        assert "/" not in _safe_filename("path/to/file")
        assert ":" not in _safe_filename("key: value")
        assert len(_safe_filename("a" * 200)) <= 60


# ══════════════════════════════════════════════════════════════
# Data integrity
# ══════════════════════════════════════════════════════════════


class TestDataIntegrity:
    def test_round_trip_preserves_content(self, ppke_vault, obsidian_vault):
        """Sync out then back in should preserve file contents."""
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        original = (ppke_vault / "Book_SyncTest" / "summary.md").read_text()

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        engine.sync_to_vault()

        # Vault copy should match source
        vault_copy = (obsidian_vault / "books" / "Book_SyncTest" / "summary.md").read_text()
        assert vault_copy == original

    def test_concept_wikilinks_integrity(self, ppke_vault, obsidian_vault):
        """Concept notes should contain valid wikilinks."""
        from ppke.export.obsidian_sync import ObsidianSyncEngine

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        engine.sync_to_vault()

        alpha = (obsidian_vault / "concepts" / "Alpha.md").read_text()
        # Should have wikilink to Beta
        assert "[[Beta]]" in alpha
        # Should reference the book
        assert "Sync Test Book" in alpha

    def test_manifest_integrity_after_sync(self, ppke_vault, obsidian_vault):
        """Manifest should accurately reflect synced files."""
        from ppke.export.obsidian_sync import ObsidianSyncEngine, SyncManifest, MANIFEST_FILENAME

        engine = ObsidianSyncEngine(ppke_vault, obsidian_vault)
        engine.sync_to_vault()

        manifest = SyncManifest(obsidian_vault / MANIFEST_FILENAME)
        # Every tracked file should exist on disk
        for rel_path in manifest.entries:
            assert (obsidian_vault / rel_path).exists(), f"Tracked file missing: {rel_path}"
