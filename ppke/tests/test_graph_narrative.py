"""Tests for ppke.graph.narrative — graph-to-text generation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def graph_data():
    """Minimal knowledge graph JSON structure."""
    return {
        "nodes": [
            {"id": "concept:consciousness", "label": "Consciousness", "type": "concept",
             "books": ["Book_A", "Book_B"], "degree": 3},
            {"id": "concept:free_will", "label": "Free Will", "type": "concept",
             "books": ["Book_A"], "degree": 2},
            {"id": "concept:determinism", "label": "Determinism", "type": "concept",
             "books": ["Book_B"], "degree": 2},
            {"id": "concept:qualia", "label": "Qualia", "type": "concept",
             "books": ["Book_A", "Book_B"], "degree": 1},
            {"id": "concept:isolated", "label": "Isolated Concept", "type": "concept",
             "books": ["Book_A", "Book_B"], "degree": 0},
            {"id": "book:Book_A", "label": "Mind and Reality (Smith)", "type": "book",
             "title": "Mind and Reality", "author": "Smith", "year": 2020},
            {"id": "book:Book_B", "label": "Determinism Revisited (Jones)", "type": "book",
             "title": "Determinism Revisited", "author": "Jones", "year": 2018},
        ],
        "edges": [
            {"source": "concept:consciousness", "target": "concept:free_will",
             "relation": "supports"},
            {"source": "concept:consciousness", "target": "concept:qualia",
             "relation": "defines"},
            {"source": "concept:free_will", "target": "concept:determinism",
             "relation": "contradicts"},
            {"source": "concept:determinism", "target": "concept:consciousness",
             "relation": "related_to"},
            {"source": "book:Book_A", "target": "concept:consciousness",
             "relation": "defines"},
            {"source": "book:Book_B", "target": "concept:determinism",
             "relation": "claims"},
        ],
    }


@pytest.fixture()
def vault_with_graph(tmp_path, graph_data):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "knowledge_graph.json").write_text(json.dumps(graph_data))
    return vault


@pytest.fixture()
def empty_vault(tmp_path):
    vault = tmp_path / "empty_vault"
    vault.mkdir()
    return vault


@pytest.fixture()
def mock_llm():
    client = MagicMock()
    client.complete.return_value = "This is the generated narrative text."
    return client


# ── build_graph_summary ───────────────────────────────────────────────────────


class TestBuildGraphSummary:
    def test_returns_summary_structure(self, vault_with_graph):
        from ppke.graph.narrative import build_graph_summary

        result = build_graph_summary(vault_with_graph)
        assert "concepts" in result
        assert "supports" in result
        assert "contradictions" in result
        assert "related" in result
        assert "books" in result
        assert "gaps" in result
        assert "stats" in result

    def test_concepts_ranked(self, vault_with_graph):
        from ppke.graph.narrative import build_graph_summary

        result = build_graph_summary(vault_with_graph)
        concepts = result["concepts"]
        assert len(concepts) > 0
        # Consciousness has the most edges so should rank high
        labels = [c["label"] for c in concepts]
        assert "Consciousness" in labels

    def test_contradictions_detected(self, vault_with_graph):
        from ppke.graph.narrative import build_graph_summary

        result = build_graph_summary(vault_with_graph)
        contradictions = result["contradictions"]
        assert len(contradictions) == 1
        assert contradictions[0]["source_label"] == "Free Will"
        assert contradictions[0]["target_label"] == "Determinism"

    def test_supports_detected(self, vault_with_graph):
        from ppke.graph.narrative import build_graph_summary

        result = build_graph_summary(vault_with_graph)
        support_rels = {r["relation"] for r in result["supports"]}
        assert "supports" in support_rels or "defines" in support_rels

    def test_books_extracted(self, vault_with_graph):
        from ppke.graph.narrative import build_graph_summary

        result = build_graph_summary(vault_with_graph)
        books = result["books"]
        assert len(books) == 2
        titles = [b["title"] for b in books]
        assert "Mind and Reality" in titles

    def test_gaps_detected(self, vault_with_graph):
        from ppke.graph.narrative import build_graph_summary

        # "isolated" concept has 2 books but no concept-concept edge
        result = build_graph_summary(vault_with_graph)
        gaps = result["gaps"]
        assert "Isolated Concept" in gaps

    def test_stats_populated(self, vault_with_graph):
        from ppke.graph.narrative import build_graph_summary

        result = build_graph_summary(vault_with_graph)
        stats = result["stats"]
        assert stats["total_nodes"] == 7
        assert stats["total_edges"] == 6
        assert stats["book_count"] == 2

    def test_missing_graph_returns_error(self, empty_vault):
        from ppke.graph.narrative import build_graph_summary

        result = build_graph_summary(empty_vault)
        assert "error" in result

    def test_invalid_json_returns_error(self, tmp_path):
        from ppke.graph.narrative import build_graph_summary

        (tmp_path / "knowledge_graph.json").write_text("{invalid json")
        result = build_graph_summary(tmp_path)
        assert "error" in result

    def test_empty_graph(self, tmp_path):
        from ppke.graph.narrative import build_graph_summary

        (tmp_path / "knowledge_graph.json").write_text(json.dumps({"nodes": [], "edges": []}))
        result = build_graph_summary(tmp_path)
        assert result["concepts"] == []
        assert result["books"] == []
        assert result["contradictions"] == []


# ── generate_narrative ────────────────────────────────────────────────────────


class TestGenerateNarrative:
    def test_essay_style(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        result = generate_narrative(vault_with_graph, mock_llm, style="essay")
        assert isinstance(result, str)
        assert len(result) > 0
        mock_llm.complete.assert_called_once()
        # System prompt should mention "academic"
        args = mock_llm.complete.call_args
        system_prompt = args[0][0]
        assert "academic" in system_prompt.lower()

    def test_report_style(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        result = generate_narrative(vault_with_graph, mock_llm, style="report")
        assert isinstance(result, str)
        mock_llm.complete.assert_called_once()

    def test_literature_review_style(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        result = generate_narrative(vault_with_graph, mock_llm, style="literature_review")
        assert isinstance(result, str)
        mock_llm.complete.assert_called_once()

    def test_invalid_style_raises(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        with pytest.raises(ValueError, match="Unknown style"):
            generate_narrative(vault_with_graph, mock_llm, style="blog_post")

    def test_missing_graph_raises(self, empty_vault, mock_llm):
        from ppke.graph.narrative import generate_narrative

        with pytest.raises(ValueError, match="No knowledge graph"):
            generate_narrative(empty_vault, mock_llm)

    def test_focus_concept_included_in_prompt(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        generate_narrative(vault_with_graph, mock_llm, focus_concept="Consciousness")
        args = mock_llm.complete.call_args
        user_prompt = args[0][1]
        assert "Consciousness" in user_prompt

    def test_prompt_includes_concepts(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        generate_narrative(vault_with_graph, mock_llm)
        args = mock_llm.complete.call_args
        user_prompt = args[0][1]
        assert "Key Concepts" in user_prompt

    def test_prompt_includes_contradictions(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        generate_narrative(vault_with_graph, mock_llm)
        args = mock_llm.complete.call_args
        user_prompt = args[0][1]
        assert "Contradictions" in user_prompt

    def test_prompt_includes_books(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        generate_narrative(vault_with_graph, mock_llm)
        args = mock_llm.complete.call_args
        user_prompt = args[0][1]
        assert "Source Books" in user_prompt

    def test_essay_instructions_in_prompt(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        generate_narrative(vault_with_graph, mock_llm, style="essay")
        args = mock_llm.complete.call_args
        user_prompt = args[0][1]
        assert "essay" in user_prompt.lower()

    def test_report_instructions_in_prompt(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        generate_narrative(vault_with_graph, mock_llm, style="report")
        args = mock_llm.complete.call_args
        user_prompt = args[0][1]
        assert "report" in user_prompt.lower()

    def test_literature_review_instructions_in_prompt(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        generate_narrative(vault_with_graph, mock_llm, style="literature_review")
        args = mock_llm.complete.call_args
        user_prompt = args[0][1]
        assert "literature" in user_prompt.lower()

    def test_llm_return_value_passed_through(self, vault_with_graph, mock_llm):
        from ppke.graph.narrative import generate_narrative

        mock_llm.complete.return_value = "Custom essay output."
        result = generate_narrative(vault_with_graph, mock_llm)
        assert result == "Custom essay output."


# ── Internal helpers ──────────────────────────────────────────────────────────


class TestEdgeHelpers:
    def test_edge_src(self):
        from ppke.graph.narrative import _edge_src

        assert _edge_src({"source": "a"}) == "a"
        assert _edge_src({"src": "b"}) == "b"
        assert _edge_src({}) == ""

    def test_edge_dst(self):
        from ppke.graph.narrative import _edge_dst

        assert _edge_dst({"target": "a"}) == "a"
        assert _edge_dst({"dst": "b"}) == "b"
        assert _edge_dst({}) == ""

    def test_edge_rel(self):
        from ppke.graph.narrative import _edge_rel

        assert _edge_rel({"relation": "supports"}) == "supports"
        assert _edge_rel({"rel": "defines"}) == "defines"
        assert _edge_rel({}) == "related_to"


class TestRankConcepts:
    def test_returns_sorted_by_degree(self, graph_data):
        from ppke.graph.narrative import _rank_concepts

        result = _rank_concepts(graph_data, top_n=10)
        assert len(result) > 0
        # Highest degree concept should appear first
        assert result[0]["degree"] >= result[-1]["degree"]

    def test_top_n_limit(self, graph_data):
        from ppke.graph.narrative import _rank_concepts

        result = _rank_concepts(graph_data, top_n=2)
        assert len(result) <= 2

    def test_empty_graph(self):
        from ppke.graph.narrative import _rank_concepts

        result = _rank_concepts({"nodes": [], "edges": []})
        assert result == []


class TestDetectGaps:
    def test_detects_isolated_concept(self, graph_data):
        from ppke.graph.narrative import _detect_gaps

        concept_ids = {n["id"] for n in graph_data["nodes"] if n.get("type") == "concept"}
        gaps = _detect_gaps(graph_data, concept_ids)
        assert "Isolated Concept" in gaps

    def test_connected_concepts_not_gaps(self, graph_data):
        from ppke.graph.narrative import _detect_gaps

        concept_ids = {n["id"] for n in graph_data["nodes"] if n.get("type") == "concept"}
        gaps = _detect_gaps(graph_data, concept_ids)
        assert "Consciousness" not in gaps
        assert "Free Will" not in gaps

    def test_empty_graph(self):
        from ppke.graph.narrative import _detect_gaps

        assert _detect_gaps({"nodes": [], "edges": []}, set()) == []
