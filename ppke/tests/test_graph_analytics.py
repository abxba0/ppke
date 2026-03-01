"""Tests for ppke.graph.analytics — centrality, clustering, search, gaps, exports."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest


@pytest.fixture()
def vault_with_graph(tmp_path):
    """Create a vault with a knowledge graph JSON file."""
    vault = tmp_path / "vault"
    vault.mkdir()
    graph = {
        "nodes": [
            {"id": "concept:logic", "label": "Logic", "type": "concept", "books": ["Book_A", "Book_B"]},
            {"id": "concept:ethics", "label": "Ethics", "type": "concept", "books": ["Book_A"]},
            {"id": "concept:epistemology", "label": "Epistemology", "type": "concept", "books": ["Book_B"]},
            {"id": "concept:metaphysics", "label": "Metaphysics", "type": "concept", "books": ["Book_A", "Book_B"]},
            {"id": "concept:isolated", "label": "Isolated", "type": "concept", "books": ["Book_A", "Book_B"]},
            {"id": "book:Book_A", "label": "Philosophy 101", "type": "book"},
            {"id": "book:Book_B", "label": "Advanced Logic", "type": "book"},
        ],
        "edges": [
            {"source": "concept:logic", "target": "concept:ethics", "relation": "related_to"},
            {"source": "concept:logic", "target": "concept:epistemology", "relation": "related_to"},
            {"source": "concept:ethics", "target": "concept:metaphysics", "relation": "supports"},
            {"source": "concept:logic", "target": "concept:metaphysics", "relation": "contradicts"},
            {"source": "book:Book_A", "target": "concept:logic", "relation": "defines"},
            {"source": "book:Book_B", "target": "concept:epistemology", "relation": "defines"},
        ],
    }
    (vault / "knowledge_graph.json").write_text(json.dumps(graph))
    return vault


@pytest.fixture()
def empty_vault(tmp_path):
    vault = tmp_path / "empty_vault"
    vault.mkdir()
    return vault


class TestLoadGraphJson:
    def test_loads_graph(self, vault_with_graph):
        from ppke.graph.analytics import _load_graph_json
        data = _load_graph_json(vault_with_graph)
        assert data is not None
        assert len(data["nodes"]) == 7
        assert len(data["edges"]) == 6

    def test_no_graph_file(self, empty_vault):
        from ppke.graph.analytics import _load_graph_json
        assert _load_graph_json(empty_vault) is None

    def test_invalid_json(self, tmp_path):
        from ppke.graph.analytics import _load_graph_json
        (tmp_path / "knowledge_graph.json").write_text("not json{{{")
        assert _load_graph_json(tmp_path) is None


class TestEdgeHelpers:
    def test_edge_src(self):
        from ppke.graph.analytics import _edge_src
        assert _edge_src({"source": "a"}) == "a"
        assert _edge_src({"src": "b"}) == "b"
        assert _edge_src({}) == ""

    def test_edge_dst(self):
        from ppke.graph.analytics import _edge_dst
        assert _edge_dst({"target": "a"}) == "a"
        assert _edge_dst({"dst": "b"}) == "b"
        assert _edge_dst({}) == ""

    def test_edge_rel(self):
        from ppke.graph.analytics import _edge_rel
        assert _edge_rel({"relation": "supports"}) == "supports"
        assert _edge_rel({"rel": "defines"}) == "defines"
        assert _edge_rel({}) == "related_to"


class TestBuildNxGraph:
    def test_builds_graph(self, vault_with_graph):
        from ppke.graph.analytics import _build_nx_graph, _load_graph_json
        data = _load_graph_json(vault_with_graph)
        G = _build_nx_graph(data)
        assert G is not None
        assert G.number_of_nodes() == 7
        assert G.number_of_edges() == 6

    def test_empty_data(self):
        from ppke.graph.analytics import _build_nx_graph
        G = _build_nx_graph({"nodes": [], "edges": []})
        assert G is not None
        assert G.number_of_nodes() == 0


class TestSearchNodes:
    def test_exact_match(self, vault_with_graph):
        from ppke.graph.analytics import search_nodes
        results = search_nodes(vault_with_graph, "Logic")
        assert len(results) >= 1
        assert results[0]["label"] == "Logic"
        assert results[0]["score"] == 100

    def test_partial_match(self, vault_with_graph):
        from ppke.graph.analytics import search_nodes
        results = search_nodes(vault_with_graph, "log")
        assert len(results) >= 1
        assert results[0]["label"] == "Logic"

    def test_no_match(self, vault_with_graph):
        from ppke.graph.analytics import search_nodes
        results = search_nodes(vault_with_graph, "quantum")
        assert results == []

    def test_empty_query(self, vault_with_graph):
        from ppke.graph.analytics import search_nodes
        assert search_nodes(vault_with_graph, "") == []

    def test_no_graph(self, empty_vault):
        from ppke.graph.analytics import search_nodes
        assert search_nodes(empty_vault, "logic") == []

    def test_limit(self, vault_with_graph):
        from ppke.graph.analytics import search_nodes
        results = search_nodes(vault_with_graph, "o", limit=2)
        assert len(results) <= 2


class TestComputeClusters:
    def test_clusters(self, vault_with_graph):
        from ppke.graph.analytics import compute_clusters
        result = compute_clusters(vault_with_graph)
        assert "clusters" in result
        assert "total_clusters" in result
        assert result["total_clusters"] >= 1

    def test_no_graph(self, empty_vault):
        from ppke.graph.analytics import compute_clusters
        result = compute_clusters(empty_vault)
        assert "error" in result

    def test_empty_graph(self, tmp_path):
        from ppke.graph.analytics import compute_clusters
        (tmp_path / "knowledge_graph.json").write_text(json.dumps({"nodes": [], "edges": []}))
        result = compute_clusters(tmp_path)
        assert result["total_clusters"] == 0


class TestComputeCentrality:
    def test_centrality(self, vault_with_graph):
        from ppke.graph.analytics import compute_centrality
        result = compute_centrality(vault_with_graph)
        assert "pagerank" in result
        assert "betweenness" in result

    def test_no_graph(self, empty_vault):
        from ppke.graph.analytics import compute_centrality
        result = compute_centrality(empty_vault)
        assert "error" in result

    def test_empty_graph(self, tmp_path):
        from ppke.graph.analytics import compute_centrality
        (tmp_path / "knowledge_graph.json").write_text(json.dumps({"nodes": [], "edges": []}))
        result = compute_centrality(tmp_path)
        assert result["pagerank"] == []
        assert result["betweenness"] == []


class TestFindShortestPath:
    def test_direct_path(self, vault_with_graph):
        from ppke.graph.analytics import find_shortest_path
        result = find_shortest_path(vault_with_graph, "concept:logic", "concept:ethics")
        assert "path" in result
        assert result["length"] == 1

    def test_indirect_path(self, vault_with_graph):
        from ppke.graph.analytics import find_shortest_path
        result = find_shortest_path(vault_with_graph, "concept:ethics", "concept:epistemology")
        assert "path" in result
        assert result["length"] >= 2

    def test_no_path(self, vault_with_graph):
        from ppke.graph.analytics import find_shortest_path
        result = find_shortest_path(vault_with_graph, "concept:logic", "concept:isolated")
        assert "error" in result

    def test_node_not_found(self, vault_with_graph):
        from ppke.graph.analytics import find_shortest_path
        result = find_shortest_path(vault_with_graph, "concept:nonexistent", "concept:logic")
        assert "error" in result

    def test_no_graph(self, empty_vault):
        from ppke.graph.analytics import find_shortest_path
        result = find_shortest_path(empty_vault, "a", "b")
        assert "error" in result


class TestDetectGaps:
    def test_gaps(self, vault_with_graph):
        from ppke.graph.analytics import detect_gaps
        result = detect_gaps(vault_with_graph)
        assert "gaps" in result
        # "isolated" has 2 books but no concept-concept edges
        gap_ids = [g["id"] for g in result["gaps"]]
        assert "concept:isolated" in gap_ids

    def test_no_graph(self, empty_vault):
        from ppke.graph.analytics import detect_gaps
        result = detect_gaps(empty_vault)
        assert result["gaps"] == []


class TestDetectContradictions:
    def test_finds_contradictions(self, vault_with_graph):
        from ppke.graph.analytics import detect_contradictions
        result = detect_contradictions(vault_with_graph)
        assert "contradictions" in result
        assert len(result["contradictions"]) == 1
        assert result["contradictions"][0]["source"] == "concept:logic"

    def test_no_graph(self, empty_vault):
        from ppke.graph.analytics import detect_contradictions
        result = detect_contradictions(empty_vault)
        assert result["contradictions"] == []


class TestObsidianExport:
    def test_export(self, vault_with_graph):
        from ppke.graph.analytics import obsidian_vault_zip
        data = obsidian_vault_zip(vault_with_graph)
        assert isinstance(data, bytes)
        assert len(data) > 0

        zf = zipfile.ZipFile(BytesIO(data))
        names = zf.namelist()
        assert any("Logic" in n for n in names)
        # Check content has wikilinks
        for name in names:
            if "Logic" in name:
                content = zf.read(name).decode("utf-8")
                assert "# Logic" in content
                assert "[[" in content  # wikilinks
                break

    def test_empty_vault(self, empty_vault):
        from ppke.graph.analytics import obsidian_vault_zip
        data = obsidian_vault_zip(empty_vault)
        assert data == b""


class TestMarkdownExport:
    def test_export(self, vault_with_graph):
        from ppke.graph.analytics import markdown_export_zip
        data = markdown_export_zip(vault_with_graph)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_empty_vault(self, empty_vault):
        from ppke.graph.analytics import markdown_export_zip
        data = markdown_export_zip(empty_vault)
        assert data == b""


class TestNodeLabels:
    def test_labels(self, vault_with_graph):
        from ppke.graph.analytics import _node_labels, _load_graph_json
        data = _load_graph_json(vault_with_graph)
        labels = _node_labels(data)
        assert labels["concept:logic"] == "Logic"
        assert labels["book:Book_A"] == "Philosophy 101"
