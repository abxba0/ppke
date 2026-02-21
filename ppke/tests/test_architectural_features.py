"""Tests for the four architectural roadmap features:

1. Progress/Task Tracking System (ppke/progress/tracker.py)
2. Vector DB Integration (ppke/vectordb/store.py)  -- mocked (no chromadb required)
3. Async Orchestrator (ppke/pipeline/async_orchestrator.py)
4. Knowledge Graph (ppke/graph/knowledge_graph.py)
5. New CLI commands (status, vector-search, async-ingest, graph-query, graph-stats, graph-build)
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_vault(tmp_path: Path) -> Path:
    """A temporary vault directory with one fake book."""
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


@pytest.fixture()
def sample_extractions() -> list[dict]:
    return [
        {
            "paragraph_id": "{01}.p1",
            "original_text": "The world is the totality of facts.",
            "topic_sentence": "The world consists of facts, not things.",
            "function_in_argument": "opening thesis",
            "explicit_claims": ["Reality is composed of facts", "Facts are atomic states of affairs"],
            "implicit_assumptions": ["There is an objective world", "Language mirrors reality"],
            "logical_steps": ["Fact → state of affairs", "State → combination of objects"],
            "defined_concepts": ["fact", "world", "state of affairs"],
            "emotional_tone": "declarative",
            "tone_evidence": "Short crisp statements.",
            "internal_references": [],
            "depth": "full",
        },
        {
            "paragraph_id": "{01}.p2",
            "original_text": "What is the case—a fact—is the existence of states of affairs.",
            "topic_sentence": "Facts are existing states of affairs.",
            "function_in_argument": "definition",
            "explicit_claims": ["A fact is an existing state of affairs"],
            "implicit_assumptions": ["States of affairs can exist or not exist"],
            "logical_steps": [],
            "defined_concepts": ["fact", "state of affairs", "existence"],
            "emotional_tone": "neutral",
            "tone_evidence": "Definitional sentence.",
            "internal_references": ["{01}.p1"],
            "depth": "full",
        },
        {
            "paragraph_id": "{02}.p1",
            "original_text": "[LOW INFORMATION]",
            "topic_sentence": "[LOW INFORMATION]",
            "function_in_argument": "boilerplate",
            "explicit_claims": [],
            "implicit_assumptions": [],
            "logical_steps": [],
            "defined_concepts": [],
            "emotional_tone": "",
            "tone_evidence": "",
            "internal_references": [],
            "depth": "skip",
        },
    ]


@pytest.fixture()
def fake_book_dir(tmp_vault: Path, sample_extractions: list[dict]) -> Path:
    """Create a fake book directory with extractions.json and meta.yml."""
    book_dir = tmp_vault / "Book_Tractatus_Wittgenstein_1921"
    book_dir.mkdir()
    (book_dir / "extractions.json").write_text(json.dumps(sample_extractions))
    meta = {
        "title": "Tractatus Logico-Philosophicus",
        "author": "Wittgenstein",
        "year": "1921",
        "total_chapters": 2,
        "total_paragraphs": 3,
        "verification_status": "COMPLETE",
    }
    import yaml
    (book_dir / "meta.yml").write_text(yaml.dump(meta))
    return book_dir


# ────────────────────────────────────────────────────────────────────────────
# 1. Progress Tracker Tests
# ────────────────────────────────────────────────────────────────────────────


class TestProgressTracker:
    def test_register_and_start(self, tmp_path: Path):
        from ppke.progress.tracker import ProgressTracker

        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.register_book("Book_Foo", "Foo", "Bar", total_chapters=5, total_paragraphs=100)

        bp = tracker.get_book("Book_Foo")
        assert bp is not None
        assert bp.status == "queued"
        assert bp.total_chapters == 5
        assert bp.total_paragraphs == 100
        assert bp.title == "Foo"
        assert bp.author == "Bar"

        tracker.start_book("Book_Foo")
        bp = tracker.get_book("Book_Foo")
        assert bp.status == "in_progress"

    def test_update_chapter(self, tmp_path: Path):
        from ppke.progress.tracker import ProgressTracker

        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.register_book("Book_Foo", "Foo", "Bar", total_chapters=10, total_paragraphs=200)
        tracker.start_book("Book_Foo")
        tracker.update_chapter("Book_Foo", "Chapter 3: Time", completed_chapters=3, completed_paragraphs=60)

        bp = tracker.get_book("Book_Foo")
        assert bp.completed_chapters == 3
        assert bp.completed_paragraphs == 60
        assert bp.current_chapter == "Chapter 3: Time"
        assert abs(bp.chapter_pct - 30.0) < 0.01
        assert abs(bp.paragraph_pct - 30.0) < 0.01

    def test_complete_book(self, tmp_path: Path):
        from ppke.progress.tracker import ProgressTracker

        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.register_book("Book_Bar", "Bar", "Baz", total_chapters=3, total_paragraphs=50)
        tracker.start_book("Book_Bar")
        tracker.complete_book("Book_Bar")

        bp = tracker.get_book("Book_Bar")
        assert bp.status == "complete"
        assert bp.completed_at is not None
        assert bp.current_chapter is None
        assert bp.completed_chapters == 3  # set to total on completion

    def test_fail_book(self, tmp_path: Path):
        from ppke.progress.tracker import ProgressTracker

        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.register_book("Book_Bad", "Bad", "X")
        tracker.fail_book("Book_Bad", "API key expired")

        bp = tracker.get_book("Book_Bad")
        assert bp.status == "failed"
        assert "API key" in bp.error

    def test_summary(self, tmp_path: Path):
        from ppke.progress.tracker import ProgressTracker

        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.register_book("Book_A", "A", "x", total_chapters=5, total_paragraphs=100)
        tracker.register_book("Book_B", "B", "y", total_chapters=3, total_paragraphs=60)
        tracker.start_book("Book_A")
        tracker.complete_book("Book_B")

        s = tracker.summary()
        assert s["total"] == 2
        assert s["in_progress"] == 1
        assert s["complete"] == 1
        assert s["queued"] == 0

    def test_clear_completed(self, tmp_path: Path):
        from ppke.progress.tracker import ProgressTracker

        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.register_book("Book_A", "A", "x")
        tracker.complete_book("Book_A")
        tracker.register_book("Book_B", "B", "y")

        removed = tracker.clear_completed()
        assert removed == 1
        assert tracker.get_book("Book_A") is None
        assert tracker.get_book("Book_B") is not None

    def test_persistence(self, tmp_path: Path):
        from ppke.progress.tracker import ProgressTracker

        path = tmp_path / "progress.json"
        tracker = ProgressTracker(path)
        tracker.register_book("Book_X", "X", "Y", total_chapters=7)

        # Reload from disk
        tracker2 = ProgressTracker(path)
        bp = tracker2.get_book("Book_X")
        assert bp is not None
        assert bp.total_chapters == 7

    def test_queued_in_progress_complete_failed_lists(self, tmp_path: Path):
        from ppke.progress.tracker import ProgressTracker

        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.register_book("q", "Q", "Q")
        tracker.register_book("ip", "IP", "IP")
        tracker.start_book("ip")
        tracker.register_book("c", "C", "C")
        tracker.complete_book("c")
        tracker.register_book("f", "F", "F")
        tracker.fail_book("f", "err")

        assert len(tracker.queued()) == 1
        assert len(tracker.in_progress()) == 1
        assert len(tracker.complete()) == 1
        assert len(tracker.failed()) == 1

    def test_re_register_updates_counts(self, tmp_path: Path):
        """Re-registering an in-progress book updates totals but keeps status."""
        from ppke.progress.tracker import ProgressTracker

        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.register_book("Book_X", "X", "Y", total_chapters=3)
        tracker.start_book("Book_X")
        # Re-register with new totals
        tracker.register_book("Book_X", "X", "Y", total_chapters=5)
        bp = tracker.get_book("Book_X")
        assert bp.status == "in_progress"
        assert bp.total_chapters == 5

    def test_update_nonexistent_book_is_noop(self, tmp_path: Path):
        from ppke.progress.tracker import ProgressTracker

        tracker = ProgressTracker(tmp_path / "progress.json")
        # Should not raise
        tracker.update_chapter("nonexistent", "ch", 1, 10)
        tracker.complete_book("nonexistent")
        tracker.fail_book("nonexistent", "err")

    def test_chapter_pct_zero_totals(self, tmp_path: Path):
        from ppke.progress.tracker import ProgressTracker, BookProgress

        bp = BookProgress(book_folder="x", title="X", author="Y", status="queued")
        assert bp.chapter_pct == 0.0
        assert bp.paragraph_pct == 0.0


# ────────────────────────────────────────────────────────────────────────────
# 2. Vector Store Tests (mocked ChromaDB)
# ────────────────────────────────────────────────────────────────────────────


class TestVectorStoreDegradedMode:
    """Test VectorStore when chromadb is NOT installed (graceful degradation)."""

    def test_unavailable_when_chroma_missing(self, tmp_vault: Path):
        from ppke.vectordb import store as vs_module

        original = vs_module._CHROMA_AVAILABLE
        vs_module._CHROMA_AVAILABLE = False
        try:
            from ppke.vectordb.store import VectorStore

            store = VectorStore(tmp_vault)
            assert not store.available
            assert store.index_extractions("Book_X", "X", "A", []) == 0
            assert store.search("consciousness") == []
            assert store.count() == 0
            assert store.delete_book("Book_X") == 0
        finally:
            vs_module._CHROMA_AVAILABLE = original


class TestVectorStoreMocked:
    """Test VectorStore with a mocked chromadb client."""

    def _make_store_with_mock(self, tmp_vault: Path):
        """Return a VectorStore whose _collection is a MagicMock and chromadb is treated as available."""
        from ppke.vectordb.store import VectorStore

        store = VectorStore.__new__(VectorStore)
        store._vault_path = tmp_vault
        store._db_path = tmp_vault / ".vector_db"
        store._client = MagicMock()
        store._collection = MagicMock()
        # Override the available property on this instance's class clone
        # so it always returns True regardless of whether chromadb is installed
        store.__class__ = type(
            "_MockVectorStore",
            (VectorStore,),
            {"available": property(lambda self: True)},
        )
        return store

    def test_index_extractions(self, tmp_vault: Path, sample_extractions: list[dict]):
        store = self._make_store_with_mock(tmp_vault)
        count = store.index_extractions("Book_Foo", "Foo", "Bar", sample_extractions)
        # Only paragraphs with non-empty doc_text are indexed; skip ones with [LOW INFORMATION]
        assert count > 0
        assert store._collection.upsert.called

    def test_index_extractions_empty(self, tmp_vault: Path):
        store = self._make_store_with_mock(tmp_vault)
        assert store.index_extractions("Book_X", "X", "Y", []) == 0

    def test_search_returns_hits(self, tmp_vault: Path):
        store = self._make_store_with_mock(tmp_vault)
        # Mock the query response
        store._collection.count.return_value = 5
        store._collection.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [
                [
                    {"book_folder": "Book_A", "book_title": "A", "author": "X", "paragraph_id": "{01}.p1"},
                    {"book_folder": "Book_B", "book_title": "B", "author": "Y", "paragraph_id": "{02}.p3"},
                ]
            ],
            "distances": [[0.12, 0.34]],
        }
        hits = store.search("consciousness", n_results=5)
        assert len(hits) == 2
        assert hits[0]["distance"] == 0.12
        assert hits[0]["paragraph_id"] == "{01}.p1"

    def test_search_empty_collection(self, tmp_vault: Path):
        store = self._make_store_with_mock(tmp_vault)
        store._collection.count.return_value = 0
        hits = store.search("anything")
        assert hits == []

    def test_delete_book(self, tmp_vault: Path):
        store = self._make_store_with_mock(tmp_vault)
        store._collection.get.return_value = {"ids": ["Book_A::p1", "Book_A::p2"]}
        deleted = store.delete_book("Book_A")
        assert deleted == 2
        assert store._collection.delete.called

    def test_index_skips_low_info_paragraphs(
        self, tmp_vault: Path, sample_extractions: list[dict]
    ):
        store = self._make_store_with_mock(tmp_vault)
        # The fixture has one [LOW INFORMATION] paragraph
        count = store.index_extractions("Book_X", "X", "Y", sample_extractions)
        # Should index 2 (the two real paragraphs), skip the LOW INFO one
        assert count == 2

    def test_index_book_from_disk(self, tmp_vault: Path, fake_book_dir: Path):
        store = self._make_store_with_mock(tmp_vault)
        count = store.index_book_from_disk(fake_book_dir)
        assert count == 2  # two non-skip extractions

    def test_index_book_from_disk_missing_file(self, tmp_vault: Path):
        store = self._make_store_with_mock(tmp_vault)
        missing_dir = tmp_vault / "Book_NonExistent"
        missing_dir.mkdir()
        assert store.index_book_from_disk(missing_dir) == 0

    def test_rebuild_index(self, tmp_vault: Path, fake_book_dir: Path):
        store = self._make_store_with_mock(tmp_vault)
        store._client.get_or_create_collection.return_value = store._collection
        results = store.rebuild_index(tmp_vault)
        assert "Book_Tractatus_Wittgenstein_1921" in results
        assert results["Book_Tractatus_Wittgenstein_1921"] == 2


# ────────────────────────────────────────────────────────────────────────────
# 3. Knowledge Graph Tests
# ────────────────────────────────────────────────────────────────────────────


class TestKnowledgeGraph:
    def test_add_extractions_and_stats(
        self, tmp_vault: Path, sample_extractions: list[dict]
    ):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_vault)
        edges = kg.add_book_extractions(
            "Book_Tractatus", "Tractatus", "Wittgenstein", sample_extractions
        )
        assert edges > 0
        s = kg.stats()
        assert s["books"] >= 1
        assert s["concepts"] > 0

    def test_books_mentioning(self, tmp_vault: Path, sample_extractions: list[dict]):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_vault)
        kg.add_book_extractions("Book_T", "Tractatus", "W", sample_extractions)

        books = kg.books_mentioning("fact")
        assert "Book_T" in books

    def test_concept_provenance(self, tmp_vault: Path, sample_extractions: list[dict]):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_vault)
        kg.add_book_extractions("Book_T", "Tractatus", "W", sample_extractions)

        provenance = kg.concept_provenance("fact")
        assert len(provenance) > 0
        assert all("book_folder" in p for p in provenance)
        assert all("paragraph_id" in p for p in provenance)

    def test_expand_concept(self, tmp_vault: Path, sample_extractions: list[dict]):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_vault)
        kg.add_book_extractions("Book_T", "Tractatus", "W", sample_extractions)

        results = kg.expand_concept("fact", depth=2)
        # Should return related concepts (the ones from the extractions)
        assert isinstance(results, list)

    def test_all_concepts(self, tmp_vault: Path, sample_extractions: list[dict]):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_vault)
        kg.add_book_extractions("Book_T", "Tractatus", "W", sample_extractions)
        concepts = kg.all_concepts()
        assert len(concepts) > 0
        assert all("concept_id" in c for c in concepts)
        assert all("label" in c for c in concepts)

    def test_save_and_reload(self, tmp_vault: Path, sample_extractions: list[dict]):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_vault)
        kg.add_book_extractions("Book_T", "Tractatus", "W", sample_extractions)
        kg.save()

        assert (tmp_vault / "knowledge_graph.json").exists()

        # Reload
        kg2 = KnowledgeGraph(tmp_vault)
        s = kg2.stats()
        assert s["books"] >= 1
        assert s["concepts"] > 0

    def test_add_concept_relation(self, tmp_vault: Path):
        from ppke.graph.knowledge_graph import KnowledgeGraph, REL_CONTRADICTS

        kg = KnowledgeGraph(tmp_vault)
        kg.add_concept_relation("free will", "determinism", relation=REL_CONTRADICTS)

        # Should exist as concept nodes with an edge
        s = kg.stats()
        assert s["concepts"] >= 2
        assert s["edges"] >= 1

    def test_build_from_vault(self, tmp_vault: Path, fake_book_dir: Path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_vault)
        results = kg.build_from_vault(tmp_vault)
        assert "Book_Tractatus_Wittgenstein_1921" in results
        assert results["Book_Tractatus_Wittgenstein_1921"] > 0

    def test_empty_provenance_for_unknown_concept(self, tmp_vault: Path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_vault)
        assert kg.concept_provenance("nonexistent_concept_xyz") == []
        assert kg.books_mentioning("nonexistent_concept_xyz") == []
        assert kg.expand_concept("nonexistent_concept_xyz") == []

    def test_stats_empty_graph(self, tmp_vault: Path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_vault)
        s = kg.stats()
        assert s["books"] == 0
        assert s["concepts"] == 0
        assert s["edges"] == 0

    def test_normalise_concept_ids(self, tmp_vault: Path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_vault)
        # Both "Dasein" and "dasein" should map to same node
        kg.add_concept_relation("Dasein", "Being")
        kg.add_concept_relation("dasein", "Time")
        # Both point to the same node concept:dasein
        books = kg.books_mentioning("Dasein")
        books2 = kg.books_mentioning("dasein")
        # Both look up the same normalised key so they return same result
        assert books == books2

    def test_corrupt_graph_file_is_ignored(self, tmp_vault: Path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        (tmp_vault / "knowledge_graph.json").write_text("{invalid json{{")
        # Should not raise
        kg = KnowledgeGraph(tmp_vault)
        assert kg.stats()["concepts"] == 0


# ────────────────────────────────────────────────────────────────────────────
# 4. Async Orchestrator Tests
# ────────────────────────────────────────────────────────────────────────────


class TestAsyncOrchestrator:
    def _make_book(self):
        from ppke.parser.models import Book, Chapter, Paragraph, DepthLevel

        para = Paragraph(chapter_number=1, paragraph_number=1, text="A fact is the case.", depth=DepthLevel.FULL)
        chapter = Chapter(number=1, title="Introduction", paragraphs=[para])
        book = Book(title="Tractatus", author="Wittgenstein", year="1921", chapters=[chapter])
        return book

    def test_run_ingest_async_delegates_to_ingest_book(self, tmp_path: Path):
        """run_ingest_async should call the existing ingest_book pipeline."""
        from ppke.pipeline.async_orchestrator import run_ingest_async
        from ppke.config import Config, LLMConfig

        config = Config(
            vault_path=tmp_path / "vault",
            llm=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"),
        )

        book = self._make_book()

        with patch("ppke.pipeline.async_orchestrator._extract_with_retry") as mock_extract, \
             patch("ppke.pipeline.async_orchestrator.build_logical_map") as mock_lm, \
             patch("ppke.pipeline.async_orchestrator.build_concept_index") as mock_ci, \
             patch("ppke.pipeline.async_orchestrator.detect_patterns") as mock_dp, \
             patch("ppke.pipeline.async_orchestrator.LLMClient") as mock_client_cls, \
             patch("ppke.pipeline.async_orchestrator.write_all_book_files") as mock_write, \
             patch("ppke.pipeline.async_orchestrator.write_global_files"), \
             patch("ppke.pipeline.async_orchestrator.validate_coverage") as mock_vc:

            from ppke.parser.models import ExtractionResult, DepthLevel
            from ppke.parser.models import CoverageReport

            mock_extract.return_value = [
                ExtractionResult(
                    paragraph_id="{01}.p1",
                    original_text="A fact is the case.",
                    topic_sentence="A fact is the case.",
                    function_in_argument="thesis",
                    depth=DepthLevel.FULL,
                )
            ]
            mock_lm.return_value = {"central_thesis": "The world is facts"}
            mock_ci.return_value = {"concepts": []}
            mock_dp.return_value = {"patterns": []}
            mock_client_cls.return_value = MagicMock()
            mock_client_cls.return_value.complete_json.return_value = {"model": "ok"}

            mock_coverage = CoverageReport(
                total_chapters=1,
                total_paragraphs=1,
                processed_paragraph_count=1,
                missing_paragraph_ids=[],
                verification_status="COMPLETE",
            )
            mock_vc.return_value = mock_coverage

            expected_dir = tmp_path / "vault" / "Book_Tractatus_Wittgenstein_1921"
            expected_dir.mkdir(parents=True, exist_ok=True)
            mock_write.return_value = expected_dir

            result = run_ingest_async(book, config)
            assert result == expected_dir

    def test_ingest_book_async_can_be_awaited(self, tmp_path: Path):
        """ingest_book_async should be a coroutine."""
        from ppke.pipeline.async_orchestrator import ingest_book_async
        import inspect
        assert inspect.iscoroutinefunction(ingest_book_async)


# ────────────────────────────────────────────────────────────────────────────
# 5. CLI command tests
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def mock_config(tmp_path: Path):
    """Patch Config.load() to return a config pointing at tmp_path."""
    from ppke.config import Config, LLMConfig

    cfg = Config(
        vault_path=tmp_path / "vault",
        llm=LLMConfig(provider="anthropic", model="test-model"),
    )
    cfg.vault_path.mkdir(parents=True, exist_ok=True)
    return cfg


class TestStatusCommand:
    def test_status_no_jobs(self, runner, tmp_path):
        from ppke.cli import main
        from ppke.progress.tracker import ProgressTracker
        from ppke.config import Config, LLMConfig

        empty_tracker = ProgressTracker(tmp_path / "progress.json")
        cfg = Config(vault_path=tmp_path / "vault", llm=LLMConfig())
        cfg.vault_path.mkdir(parents=True, exist_ok=True)

        with patch("ppke.progress.tracker.ProgressTracker", return_value=empty_tracker), \
             patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "No ingestion jobs" in result.output

    def test_status_with_jobs(self, runner, tmp_path):
        from ppke.cli import main
        from ppke.progress.tracker import ProgressTracker
        from ppke.config import Config, LLMConfig

        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file)
        tracker.register_book("Book_A", "Book A", "Author", total_chapters=5, total_paragraphs=100)
        tracker.start_book("Book_A")

        cfg = Config(vault_path=tmp_path / "vault", llm=LLMConfig())
        cfg.vault_path.mkdir(parents=True, exist_ok=True)

        # The ProgressTracker() in the status command uses default path, so we mock it
        # to return our pre-populated tracker instance
        with patch("ppke.progress.tracker.ProgressTracker", return_value=tracker), \
             patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "Book A" in result.output

    def test_status_clear_done(self, runner, tmp_path):
        from ppke.cli import main
        from ppke.progress.tracker import ProgressTracker
        from ppke.config import Config, LLMConfig

        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file)
        tracker.register_book("Book_A", "A", "X")
        tracker.complete_book("Book_A")

        cfg = Config(vault_path=tmp_path / "vault", llm=LLMConfig())
        cfg.vault_path.mkdir(parents=True, exist_ok=True)

        with patch("ppke.progress.tracker.ProgressTracker", return_value=tracker), \
             patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["status", "--clear-done"])
        assert result.exit_code == 0
        assert "Removed 1" in result.output


class TestVectorSearchCommand:
    def test_vector_search_unavailable(self, runner, tmp_path):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        cfg = Config(vault_path=tmp_path / "vault", llm=LLMConfig())
        cfg.vault_path.mkdir(parents=True, exist_ok=True)

        with patch("ppke.cli.Config.load", return_value=cfg), \
             patch("ppke.vectordb.store._CHROMA_AVAILABLE", False):
            result = runner.invoke(main, ["vector-search", "consciousness"])
        assert result.exit_code != 0
        assert "not installed" in result.output

    def test_vector_search_with_mock_store(self, runner, tmp_path):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig
        from ppke.vectordb.store import VectorStore

        cfg = Config(vault_path=tmp_path / "vault", llm=LLMConfig())
        cfg.vault_path.mkdir(parents=True, exist_ok=True)

        mock_store = MagicMock(spec=VectorStore)
        mock_store.available = True
        mock_store.count.return_value = 10
        mock_store.search.return_value = [
            {
                "paragraph_id": "{01}.p1",
                "book_folder": "Book_T",
                "book_title": "Tractatus",
                "author": "W",
                "distance": 0.15,
                "document": "A fact is the case.",
            }
        ]

        # Patch at the source module since vector_search uses a local import
        with patch("ppke.cli.Config.load", return_value=cfg), \
             patch("ppke.vectordb.store.VectorStore", return_value=mock_store):
            result = runner.invoke(main, ["vector-search", "fact"])
        assert result.exit_code == 0
        assert "Tractatus" in result.output or "Book_T" in result.output

    def test_vector_search_rebuild(self, runner, tmp_path):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig
        from ppke.vectordb.store import VectorStore

        cfg = Config(vault_path=tmp_path / "vault", llm=LLMConfig())
        cfg.vault_path.mkdir(parents=True, exist_ok=True)

        mock_store = MagicMock(spec=VectorStore)
        mock_store.available = True
        mock_store.rebuild_index.return_value = {"Book_A": 50}

        with patch("ppke.cli.Config.load", return_value=cfg), \
             patch("ppke.vectordb.store.VectorStore", return_value=mock_store):
            result = runner.invoke(main, ["vector-search", "--rebuild", ""])
        assert result.exit_code == 0
        assert "1 books" in result.output or "Rebuilt" in result.output


class TestGraphCommands:
    def test_graph_stats_empty(self, runner, tmp_path):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        cfg = Config(vault_path=tmp_path / "vault", llm=LLMConfig())
        cfg.vault_path.mkdir(parents=True, exist_ok=True)

        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["graph-stats"])
        assert result.exit_code == 0
        assert "Concepts:" in result.output

    def test_graph_build(self, runner, tmp_path, fake_book_dir):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        vault = fake_book_dir.parent
        cfg = Config(vault_path=vault, llm=LLMConfig())

        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["graph-build"])
        assert result.exit_code == 0
        assert "Book_Tractatus_Wittgenstein_1921" in result.output
        assert (vault / "knowledge_graph.json").exists()

    def test_graph_build_with_reset(self, runner, tmp_path, fake_book_dir):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        vault = fake_book_dir.parent
        # Create a pre-existing graph file
        (vault / "knowledge_graph.json").write_text('{"nodes":[],"edges":[]}')
        cfg = Config(vault_path=vault, llm=LLMConfig())

        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["graph-build", "--reset"])
        assert result.exit_code == 0
        assert "deleted" in result.output or "concepts" in result.output

    def test_graph_query_empty_graph(self, runner, tmp_path):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        cfg = Config(vault_path=tmp_path / "vault", llm=LLMConfig())
        cfg.vault_path.mkdir(parents=True, exist_ok=True)

        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["graph-query", "Dasein"])
        assert result.exit_code != 0
        assert "empty" in result.output

    def test_graph_query_with_concepts(self, runner, tmp_path, fake_book_dir):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        vault = fake_book_dir.parent
        cfg = Config(vault_path=vault, llm=LLMConfig())

        # Build graph first
        from ppke.graph.knowledge_graph import KnowledgeGraph
        import json
        extractions = json.loads((fake_book_dir / "extractions.json").read_text())
        kg = KnowledgeGraph(vault)
        kg.add_book_extractions("Book_Tractatus_Wittgenstein_1921", "Tractatus", "W", extractions)
        kg.save()

        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["graph-query", "fact"])
        assert result.exit_code == 0

    def test_graph_query_provenance(self, runner, tmp_path, fake_book_dir):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        vault = fake_book_dir.parent
        cfg = Config(vault_path=vault, llm=LLMConfig())

        # Build graph first
        from ppke.graph.knowledge_graph import KnowledgeGraph
        import json
        extractions = json.loads((fake_book_dir / "extractions.json").read_text())
        kg = KnowledgeGraph(vault)
        kg.add_book_extractions("Book_Tractatus_Wittgenstein_1921", "Tractatus", "W", extractions)
        kg.save()

        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["graph-query", "fact", "--provenance"])
        assert result.exit_code == 0
        assert "Provenance" in result.output


class TestAsyncIngestCommand:
    def test_async_ingest_command_calls_pipeline(self, runner, tmp_path):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        cfg = Config(vault_path=tmp_path / "vault", llm=LLMConfig(provider="anthropic"))
        cfg.vault_path.mkdir(parents=True, exist_ok=True)

        # Create a minimal markdown file
        md_file = tmp_path / "book.md"
        md_file.write_text("# Chapter 1\n\nThis is a test paragraph with enough words.\n")

        expected_dir = cfg.vault_path / "Book_Test_Author_2024"
        expected_dir.mkdir(parents=True, exist_ok=True)

        # Patch at source module level since async_ingest uses local imports
        with patch("ppke.cli.Config.load", return_value=cfg), \
             patch("ppke.cli._require_api_key"), \
             patch("ppke.pipeline.async_orchestrator.run_ingest_async", return_value=expected_dir) as mock_run, \
             patch("ppke.vectordb.store.VectorStore") as mock_vs_cls, \
             patch("ppke.graph.knowledge_graph.KnowledgeGraph") as mock_kg_cls:

            mock_vs = MagicMock()
            mock_vs.available = False
            mock_vs_cls.return_value = mock_vs

            mock_kg = MagicMock()
            mock_kg_cls.return_value = mock_kg

            result = runner.invoke(main, [
                "async-ingest", str(md_file),
                "--title", "Test",
                "--author", "Author",
                "--year", "2024",
            ])

        assert result.exit_code == 0, result.output
        assert mock_run.called
        assert "Done!" in result.output


# ────────────────────────────────────────────────────────────────────────────
# 6. Orchestrator integration tests (progress + vector + graph)
# ────────────────────────────────────────────────────────────────────────────


class TestOrchestratorIntegration:
    """Test that the updated ingest_book passes tracker/vector_store/graph correctly."""

    def _make_book(self):
        from ppke.parser.models import Book, Chapter, Paragraph, DepthLevel

        para = Paragraph(
            chapter_number=1, paragraph_number=1,
            text="Being is prior to essence.",
            depth=DepthLevel.FULL,
        )
        chapter = Chapter(number=1, title="Intro", paragraphs=[para])
        return Book(title="Being and Time", author="Heidegger", year="1927", chapters=[chapter])

    def test_ingest_book_calls_tracker(self, tmp_path: Path):
        from ppke.pipeline.orchestrator import ingest_book
        from ppke.config import Config, LLMConfig
        from ppke.progress.tracker import ProgressTracker

        cfg = Config(
            vault_path=tmp_path / "vault",
            llm=LLMConfig(provider="anthropic", model="test"),
        )
        book = self._make_book()
        tracker = ProgressTracker(tmp_path / "progress.json")

        with patch("ppke.pipeline.orchestrator._extract_with_retry") as mock_extract, \
             patch("ppke.pipeline.orchestrator.build_logical_map") as mock_lm, \
             patch("ppke.pipeline.orchestrator.build_concept_index") as mock_ci, \
             patch("ppke.pipeline.orchestrator.detect_patterns") as mock_dp, \
             patch("ppke.pipeline.orchestrator.LLMClient") as mock_client_cls, \
             patch("ppke.pipeline.orchestrator.write_all_book_files") as mock_write, \
             patch("ppke.pipeline.orchestrator.write_global_files"), \
             patch("ppke.pipeline.orchestrator.validate_coverage") as mock_vc:

            from ppke.parser.models import ExtractionResult, DepthLevel, CoverageReport

            mock_extract.return_value = [
                ExtractionResult(
                    paragraph_id="{01}.p1",
                    original_text="Being is prior to essence.",
                    topic_sentence="Being is prior to essence.",
                    function_in_argument="thesis",
                    depth=DepthLevel.FULL,
                )
            ]
            mock_lm.return_value = {}
            mock_ci.return_value = {}
            mock_dp.return_value = {}
            mock_client_cls.return_value = MagicMock()
            mock_client_cls.return_value.complete_json.return_value = {}
            mock_coverage = CoverageReport(
                total_chapters=1,
                total_paragraphs=1,
                processed_paragraph_count=1,
                missing_paragraph_ids=[],
                verification_status="COMPLETE",
            )
            mock_vc.return_value = mock_coverage
            expected_dir = cfg.vault_path / book.folder_name
            expected_dir.mkdir(parents=True, exist_ok=True)
            mock_write.return_value = expected_dir

            ingest_book(book, cfg, tracker=tracker)

        # Tracker should have marked the book complete
        bp = tracker.get_book(book.folder_name)
        assert bp is not None
        assert bp.status == "complete"

    def test_ingest_book_calls_vector_store(self, tmp_path: Path):
        from ppke.pipeline.orchestrator import ingest_book
        from ppke.config import Config, LLMConfig
        from ppke.vectordb.store import VectorStore

        cfg = Config(
            vault_path=tmp_path / "vault",
            llm=LLMConfig(provider="anthropic", model="test"),
        )
        book = self._make_book()
        mock_store = MagicMock(spec=VectorStore)
        mock_store.available = True
        mock_store.index_extractions.return_value = 1

        with patch("ppke.pipeline.orchestrator._extract_with_retry") as mock_extract, \
             patch("ppke.pipeline.orchestrator.build_logical_map", return_value={}), \
             patch("ppke.pipeline.orchestrator.build_concept_index", return_value={}), \
             patch("ppke.pipeline.orchestrator.detect_patterns", return_value={}), \
             patch("ppke.pipeline.orchestrator.LLMClient") as mock_client_cls, \
             patch("ppke.pipeline.orchestrator.write_all_book_files") as mock_write, \
             patch("ppke.pipeline.orchestrator.write_global_files"), \
             patch("ppke.pipeline.orchestrator.validate_coverage") as mock_vc:

            from ppke.parser.models import ExtractionResult, DepthLevel, CoverageReport

            mock_extract.return_value = [
                ExtractionResult(
                    paragraph_id="{01}.p1",
                    original_text="Being is prior.",
                    topic_sentence="Being is prior.",
                    function_in_argument="thesis",
                    depth=DepthLevel.FULL,
                )
            ]
            mock_client_cls.return_value = MagicMock()
            mock_client_cls.return_value.complete_json.return_value = {}
            mock_coverage = CoverageReport(
                total_chapters=1,
                total_paragraphs=1,
                processed_paragraph_count=1,
                missing_paragraph_ids=[],
                verification_status="COMPLETE",
            )
            mock_vc.return_value = mock_coverage
            expected_dir = cfg.vault_path / book.folder_name
            expected_dir.mkdir(parents=True, exist_ok=True)
            # Create a fake extractions.json for the vector store call
            (expected_dir / "extractions.json").write_text("[]")
            mock_write.return_value = expected_dir

            ingest_book(book, cfg, vector_store=mock_store)

        assert mock_store.index_extractions.called

    def test_ingest_book_calls_knowledge_graph(self, tmp_path: Path):
        from ppke.pipeline.orchestrator import ingest_book
        from ppke.config import Config, LLMConfig
        from ppke.graph.knowledge_graph import KnowledgeGraph

        cfg = Config(
            vault_path=tmp_path / "vault",
            llm=LLMConfig(provider="anthropic", model="test"),
        )
        book = self._make_book()
        mock_kg = MagicMock(spec=KnowledgeGraph)
        mock_kg.add_book_extractions.return_value = 5

        with patch("ppke.pipeline.orchestrator._extract_with_retry") as mock_extract, \
             patch("ppke.pipeline.orchestrator.build_logical_map", return_value={}), \
             patch("ppke.pipeline.orchestrator.build_concept_index", return_value={}), \
             patch("ppke.pipeline.orchestrator.detect_patterns", return_value={}), \
             patch("ppke.pipeline.orchestrator.LLMClient") as mock_client_cls, \
             patch("ppke.pipeline.orchestrator.write_all_book_files") as mock_write, \
             patch("ppke.pipeline.orchestrator.write_global_files"), \
             patch("ppke.pipeline.orchestrator.validate_coverage") as mock_vc:

            from ppke.parser.models import ExtractionResult, DepthLevel, CoverageReport

            mock_extract.return_value = [
                ExtractionResult(
                    paragraph_id="{01}.p1",
                    original_text="Being is prior.",
                    topic_sentence="Being is prior.",
                    function_in_argument="thesis",
                    depth=DepthLevel.FULL,
                )
            ]
            mock_client_cls.return_value = MagicMock()
            mock_client_cls.return_value.complete_json.return_value = {}
            mock_coverage = CoverageReport(
                total_chapters=1,
                total_paragraphs=1,
                processed_paragraph_count=1,
                missing_paragraph_ids=[],
                verification_status="COMPLETE",
            )
            mock_vc.return_value = mock_coverage
            expected_dir = cfg.vault_path / book.folder_name
            expected_dir.mkdir(parents=True, exist_ok=True)
            (expected_dir / "extractions.json").write_text("[]")
            mock_write.return_value = expected_dir

            ingest_book(book, cfg, knowledge_graph=mock_kg)

        assert mock_kg.add_book_extractions.called
        assert mock_kg.save.called
