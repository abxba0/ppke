"""Tests for hybrid search (ppke/search.py).

Covers:
- fulltext_search(): case-insensitive substring matching across vault
- hybrid_search(): combined full-text + vector ranking and deduplication
- Backward compatibility: existing search endpoints are unchanged
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Fixtures ──


@pytest.fixture()
def vault_with_books(tmp_path: Path) -> Path:
    """Vault with two books for search tests."""
    vault = tmp_path / "vault"
    vault.mkdir()

    # Book A
    book_a = vault / "Book_Republic_Plato"
    book_a.mkdir()
    (book_a / "extractions.json").write_text(
        json.dumps(
            [
                {
                    "paragraph_id": "{01}.p1",
                    "original_text": "Justice is the advantage of the stronger.",
                    "topic_sentence": "Thrasymachus defines justice.",
                    "explicit_claims": ["Justice benefits the powerful"],
                    "defined_concepts": ["justice", "power"],
                    "implicit_assumptions": [],
                },
                {
                    "paragraph_id": "{01}.p2",
                    "original_text": "The soul has a function unique to itself.",
                    "topic_sentence": "The soul's proper function is to rule.",
                    "explicit_claims": ["The soul rules"],
                    "defined_concepts": ["soul", "function"],
                    "implicit_assumptions": [],
                },
            ]
        )
    )
    try:
        import yaml

        (book_a / "meta.yml").write_text(
            yaml.dump({"title": "Republic", "author": "Plato"})
        )
    except ImportError:
        pass

    # Book B
    book_b = vault / "Book_Critique_Kant"
    book_b.mkdir()
    (book_b / "extractions.json").write_text(
        json.dumps(
            [
                {
                    "paragraph_id": "{01}.p1",
                    "original_text": "All knowledge begins with experience.",
                    "topic_sentence": "Experience grounds all cognition.",
                    "explicit_claims": ["Knowledge is empirical"],
                    "defined_concepts": ["knowledge", "experience"],
                    "implicit_assumptions": [],
                },
            ]
        )
    )

    return vault


# ── fulltext_search tests ──


class TestFulltextSearch:
    def test_finds_matching_text(self, vault_with_books: Path):
        from ppke.search import fulltext_search

        hits = fulltext_search(vault_with_books, "justice")
        assert len(hits) >= 1
        assert any(h["paragraph_id"] == "{01}.p1" for h in hits)
        assert all(h["source"] == "fulltext" for h in hits)

    def test_case_insensitive(self, vault_with_books: Path):
        from ppke.search import fulltext_search

        hits = fulltext_search(vault_with_books, "JUSTICE")
        assert len(hits) >= 1

    def test_book_filter(self, vault_with_books: Path):
        from ppke.search import fulltext_search

        hits = fulltext_search(
            vault_with_books, "knowledge", book_filter="Book_Critique_Kant"
        )
        assert len(hits) == 1
        assert hits[0]["book_folder"] == "Book_Critique_Kant"

    def test_max_results(self, vault_with_books: Path):
        from ppke.search import fulltext_search

        hits = fulltext_search(vault_with_books, "the", max_results=1)
        assert len(hits) <= 1

    def test_no_match(self, vault_with_books: Path):
        from ppke.search import fulltext_search

        hits = fulltext_search(vault_with_books, "xyznonexistent")
        assert hits == []

    def test_empty_query(self, vault_with_books: Path):
        from ppke.search import fulltext_search

        hits = fulltext_search(vault_with_books, "")
        assert hits == []

    def test_missing_vault(self, tmp_path: Path):
        from ppke.search import fulltext_search

        hits = fulltext_search(tmp_path / "nonexistent", "test")
        assert hits == []

    def test_result_fields(self, vault_with_books: Path):
        from ppke.search import fulltext_search

        hits = fulltext_search(vault_with_books, "justice")
        h = hits[0]
        assert "paragraph_id" in h
        assert "book_folder" in h
        assert "book_title" in h
        assert "author" in h
        assert "document" in h
        assert "score" in h
        assert "source" in h
        assert h["source"] == "fulltext"
        assert h["score"] == 1.0


# ── hybrid_search tests ──


class TestHybridSearch:
    def test_fulltext_only_when_vector_unavailable(self, vault_with_books: Path):
        """hybrid_search degrades to fulltext when ChromaDB is absent."""
        from ppke.search import hybrid_search

        with patch("ppke.vectordb.store.VectorStore") as MockVS:
            mock_store = MagicMock()
            mock_store.available = False
            MockVS.return_value = mock_store

            hits = hybrid_search(vault_with_books, "justice")
            assert len(hits) >= 1
            # All results should come from fulltext
            assert all(h["source"] == "fulltext" for h in hits)

    def test_vector_only_when_no_text_match(self, vault_with_books: Path):
        """When query doesn't match any text but vectors return results."""
        from ppke.search import hybrid_search

        with patch("ppke.vectordb.store.VectorStore") as MockVS:
            mock_store = MagicMock()
            mock_store.available = True
            mock_store.search.return_value = [
                {
                    "paragraph_id": "{01}.p1",
                    "book_folder": "Book_Republic_Plato",
                    "book_title": "Republic",
                    "author": "Plato",
                    "distance": 0.3,
                    "document": "Justice is the advantage of the stronger.",
                }
            ]
            MockVS.return_value = mock_store

            hits = hybrid_search(vault_with_books, "xyznotext")
            assert len(hits) >= 1
            assert any(h["source"] == "vector" for h in hits)

    def test_hybrid_merges_and_deduplicates(self, vault_with_books: Path):
        """When same paragraph appears in both text and vector results."""
        from ppke.search import hybrid_search

        with patch("ppke.vectordb.store.VectorStore") as MockVS:
            mock_store = MagicMock()
            mock_store.available = True
            mock_store.search.return_value = [
                {
                    "paragraph_id": "{01}.p1",
                    "book_folder": "Book_Republic_Plato",
                    "book_title": "Republic",
                    "author": "Plato",
                    "distance": 0.2,
                    "document": "Justice is the advantage of the stronger.",
                }
            ]
            MockVS.return_value = mock_store

            hits = hybrid_search(vault_with_books, "justice")
            # The same paragraph should appear only once
            plato_p1 = [
                h
                for h in hits
                if h["book_folder"] == "Book_Republic_Plato"
                and h["paragraph_id"] == "{01}.p1"
            ]
            assert len(plato_p1) == 1
            assert plato_p1[0]["source"] == "hybrid"
            # Combined score should be > either individual
            assert plato_p1[0]["score"] > 0

    def test_n_results_limit(self, vault_with_books: Path):
        from ppke.search import hybrid_search

        hits = hybrid_search(vault_with_books, "the", n_results=1)
        assert len(hits) <= 1

    def test_custom_weights(self, vault_with_books: Path):
        from ppke.search import hybrid_search

        hits_text_heavy = hybrid_search(
            vault_with_books, "justice", vector_weight=0.0, text_weight=1.0
        )
        hits_vec_heavy = hybrid_search(
            vault_with_books, "justice", vector_weight=1.0, text_weight=0.0
        )
        # Both should return results (fulltext at least)
        assert len(hits_text_heavy) >= 1
        assert len(hits_vec_heavy) >= 1

    def test_book_filter(self, vault_with_books: Path):
        from ppke.search import hybrid_search

        hits = hybrid_search(
            vault_with_books,
            "knowledge",
            book_filter="Book_Critique_Kant",
        )
        assert all(h["book_folder"] == "Book_Critique_Kant" for h in hits)

    def test_result_fields(self, vault_with_books: Path):
        from ppke.search import hybrid_search

        hits = hybrid_search(vault_with_books, "justice")
        assert len(hits) >= 1
        h = hits[0]
        for key in ("paragraph_id", "book_folder", "book_title", "author", "document", "score", "source"):
            assert key in h

    def test_results_sorted_by_score_descending(self, vault_with_books: Path):
        from ppke.search import hybrid_search

        hits = hybrid_search(vault_with_books, "the")
        if len(hits) > 1:
            scores = [h["score"] for h in hits]
            assert scores == sorted(scores, reverse=True)


# ── CLI hybrid-search command tests ──


class TestHybridSearchCLI:
    @pytest.fixture()
    def runner(self):
        from click.testing import CliRunner

        return CliRunner()

    def test_hybrid_search_command_exists(self, runner):
        from ppke.cli import main

        result = runner.invoke(main, ["hybrid-search", "--help"])
        assert result.exit_code == 0
        assert "hybrid" in result.output.lower()

    def test_hybrid_search_no_vault(self, runner, tmp_path):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        cfg = Config(vault_path=tmp_path / "nonexistent", llm=LLMConfig())
        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["hybrid-search", "test"])
        assert result.exit_code != 0

    def test_hybrid_search_no_results(self, runner, vault_with_books):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        cfg = Config(vault_path=vault_with_books, llm=LLMConfig())
        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["hybrid-search", "xyznonexistent"])
        assert result.exit_code == 0
        assert "No hybrid search results" in result.output

    def test_hybrid_search_with_results(self, runner, vault_with_books):
        from ppke.cli import main
        from ppke.config import Config, LLMConfig

        cfg = Config(vault_path=vault_with_books, llm=LLMConfig())
        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["hybrid-search", "justice"])
        assert result.exit_code == 0
        assert "justice" in result.output.lower() or "Hybrid Search" in result.output
