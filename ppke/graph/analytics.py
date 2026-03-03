"""Graph analytics for PPKE — centrality, clustering, path finding, gap detection.

All functions accept a ``vault_path`` and load ``knowledge_graph.json``.
NetworkX is required for centrality and clustering; lighter functions
(search, gaps, contradictions) work directly from the JSON.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_nx_available = False
try:
    import networkx as nx  # type: ignore[import]

    _nx_available = True
except ImportError:
    pass


# ── Internal helpers ──


def _load_graph_json(vault_path: Path) -> dict[str, Any] | None:
    """Load the raw JSON graph.  Returns None when no graph exists."""
    path = vault_path / "knowledge_graph.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.error("Failed to load knowledge_graph.json: %s", exc)
        return None


def _edge_src(e: dict) -> str:
    return e.get("src") or e.get("source", "")


def _edge_dst(e: dict) -> str:
    return e.get("dst") or e.get("target", "")


def _edge_rel(e: dict) -> str:
    return e.get("rel") or e.get("relation", "related_to")


def _build_nx_graph(data: dict) -> Any:
    """Build a NetworkX DiGraph from the JSON blob."""
    if not _nx_available:
        return None
    G = nx.DiGraph()
    for n in data.get("nodes", []):
        attrs = {k: v for k, v in n.items() if k != "id"}
        G.add_node(n["id"], **attrs)
    for e in data.get("edges", []):
        src, dst = _edge_src(e), _edge_dst(e)
        if src and dst:
            attrs = {
                k: v
                for k, v in e.items()
                if k not in ("src", "dst", "source", "target", "rel", "relation")
            }
            attrs["relation"] = _edge_rel(e)
            G.add_edge(src, dst, **attrs)
    return G


def _node_labels(data: dict) -> dict[str, str]:
    return {n["id"]: n.get("label", n["id"]) for n in data.get("nodes", [])}


# ── Public API ──


def search_nodes(vault_path: Path, query: str, limit: int = 15) -> list[dict]:
    """Fuzzy search for nodes by label. No NetworkX required."""
    data = _load_graph_json(vault_path)
    if not data:
        return []
    q = query.lower().strip()
    if not q:
        return []
    results: list[dict] = []
    for n in data.get("nodes", []):
        label = n.get("label", n.get("id", ""))
        ll = label.lower()
        if q in ll:
            score = 100 if ll == q else (90 if ll.startswith(q) else 50)
            results.append(
                {
                    "id": n["id"],
                    "label": label,
                    "type": n.get("type", "unknown"),
                    "score": score,
                }
            )
    results.sort(key=lambda x: (-x["score"], x["label"].lower()))
    return results[:limit]


def compute_clusters(vault_path: Path) -> dict[str, Any]:
    """Louvain community detection. Requires NetworkX."""
    if not _nx_available:
        return {"error": "NetworkX not installed — install with: pip install ppke[graph]"}
    data = _load_graph_json(vault_path)
    if not data:
        return {"error": "No knowledge graph found"}

    G = _build_nx_graph(data)
    UG = G.to_undirected()
    if UG.number_of_nodes() == 0:
        return {"clusters": {}, "total_clusters": 0}

    try:
        communities = nx.community.louvain_communities(UG, seed=42)
    except Exception as exc:
        logger.error("Louvain clustering failed: %s", exc)
        return {"error": str(exc)}

    mapping: dict[str, int] = {}
    for i, community in enumerate(communities):
        for node_id in community:
            mapping[node_id] = i
    return {"clusters": mapping, "total_clusters": len(communities)}


def compute_centrality(vault_path: Path, top_n: int = 15) -> dict[str, Any]:
    """PageRank + betweenness centrality on concept nodes. Requires NetworkX."""
    if not _nx_available:
        return {"error": "NetworkX not installed — install with: pip install ppke[graph]"}
    data = _load_graph_json(vault_path)
    if not data:
        return {"error": "No knowledge graph found"}

    G = _build_nx_graph(data)
    if G.number_of_nodes() == 0:
        return {"pagerank": [], "betweenness": []}

    labels = _node_labels(data)

    try:
        pr = nx.pagerank(G, max_iter=200)
    except Exception:
        pr = {}
    try:
        bc = nx.betweenness_centrality(G)
    except Exception:
        bc = {}

    def _top(scores: dict, prefix: str = "concept:") -> list[dict]:
        filtered = [(nid, s) for nid, s in scores.items() if nid.startswith(prefix)]
        filtered.sort(key=lambda x: -x[1])
        return [
            {"id": nid, "label": labels.get(nid, nid), "score": round(s, 6)}
            for nid, s in filtered[:top_n]
        ]

    return {"pagerank": _top(pr), "betweenness": _top(bc)}


def find_shortest_path(
    vault_path: Path, source: str, target: str
) -> dict[str, Any]:
    """Shortest undirected path between two node IDs. Requires NetworkX."""
    if not _nx_available:
        return {"error": "NetworkX not installed — install with: pip install ppke[graph]"}
    data = _load_graph_json(vault_path)
    if not data:
        return {"error": "No knowledge graph found"}

    G = _build_nx_graph(data)
    UG = G.to_undirected()

    try:
        path = nx.shortest_path(UG, source, target)
    except nx.NetworkXNoPath:
        return {"error": f"No path between '{source}' and '{target}'"}
    except nx.NodeNotFound as e:
        return {"error": str(e)}

    labels = _node_labels(data)
    edges: list[dict] = []
    for i in range(len(path) - 1):
        ed = G.get_edge_data(path[i], path[i + 1]) or G.get_edge_data(
            path[i + 1], path[i]
        ) or {}
        edges.append(
            {
                "source": path[i],
                "target": path[i + 1],
                "relation": ed.get("relation", "related_to"),
            }
        )

    return {
        "path": [{"id": nid, "label": labels.get(nid, nid)} for nid in path],
        "edges": edges,
        "length": len(path) - 1,
    }


def detect_gaps(vault_path: Path, min_books: int = 2) -> dict[str, Any]:
    """Concepts in N+ books but with no concept↔concept edges. No NetworkX needed."""
    data = _load_graph_json(vault_path)
    if not data:
        return {"gaps": []}

    # Collect concepts appearing in multiple books
    concept_books: dict[str, dict] = {}
    for n in data.get("nodes", []):
        if n.get("type") == "concept":
            books = n.get("books", [])
            if isinstance(books, list) and len(books) >= min_books:
                concept_books[n["id"]] = {
                    "id": n["id"],
                    "label": n.get("label", n["id"]),
                    "books": books,
                }

    # Build set of directly connected concept pairs
    connected: set[str] = set()
    for e in data.get("edges", []):
        src, dst = _edge_src(e), _edge_dst(e)
        if src.startswith("concept:") and dst.startswith("concept:"):
            connected.add(src)
            connected.add(dst)

    # Gaps = multi-book concepts that are never in a concept↔concept edge
    gaps = [
        info for cid, info in concept_books.items() if cid not in connected
    ]
    gaps.sort(key=lambda g: -len(g["books"]))
    return {"gaps": gaps[:30]}


def detect_contradictions(vault_path: Path) -> dict[str, Any]:
    """Find all edges with 'contradicts' relation. No NetworkX needed."""
    data = _load_graph_json(vault_path)
    if not data:
        return {"contradictions": []}

    labels = _node_labels(data)
    results: list[dict] = []
    for e in data.get("edges", []):
        if _edge_rel(e) == "contradicts":
            src, dst = _edge_src(e), _edge_dst(e)
            results.append(
                {
                    "source": src,
                    "source_label": labels.get(src, src),
                    "target": dst,
                    "target_label": labels.get(dst, dst),
                }
            )
    return {"contradictions": results}


def obsidian_vault_zip(vault_path: Path) -> bytes:
    """Generate a ZIP containing one ``.md`` per concept with [[wikilinks]].

    Returns the raw ZIP bytes for streaming to the client.
    """
    import io
    import zipfile

    data = _load_graph_json(vault_path)
    if not data:
        return b""

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    labels = _node_labels(data)

    # Build concept → related entries
    relations: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in edges:
        src, dst, rel = _edge_src(e), _edge_dst(e), _edge_rel(e)
        if src.startswith("concept:"):
            relations[src].append((dst, rel))
        if dst.startswith("concept:"):
            relations[dst].append((src, rel))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
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

            # Concept-to-concept links
            concept_links = [
                (other, rel) for other, rel in relations.get(nid, [])
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
                (other, rel) for other, rel in relations.get(nid, [])
                if other.startswith("book:")
            ]
            if book_links:
                lines.append("## Sources")
                for other_id, rel in book_links:
                    other_label = labels.get(other_id, other_id)
                    lines.append(f"- {other_label} ({rel})")
                lines.append("")

            safe_name = label.replace("/", "-").replace("\\", "-").replace(":", "-")[:60]
            zf.writestr(f"concepts/{safe_name}.md", "\n".join(lines))

    return buf.getvalue()


def markdown_export_zip(vault_path: Path) -> bytes:
    """Download interlinked Markdown files (one per concept)."""
    # Reuse the Obsidian format — it's already interlinked Markdown
    return obsidian_vault_zip(vault_path)


# ── Temporal view ──────────────────────────────────────────────────


def get_temporal_range(vault_path: Path) -> dict[str, Any]:
    """Return the min/max year across all book nodes in the graph.

    Also returns a list of all unique years found, sorted ascending.
    """
    data = _load_graph_json(vault_path)
    if not data:
        return {"min_year": None, "max_year": None, "years": []}

    years: set[int] = set()

    # Collect years from book nodes
    for n in data.get("nodes", []):
        y = n.get("year")
        if y is not None:
            try:
                years.add(int(y))
            except (ValueError, TypeError):
                pass

    # Collect years from edges
    for e in data.get("edges", []):
        y = e.get("year")
        if y is not None:
            try:
                years.add(int(y))
            except (ValueError, TypeError):
                pass

    if not years:
        return {"min_year": None, "max_year": None, "years": []}

    sorted_years = sorted(years)
    return {
        "min_year": sorted_years[0],
        "max_year": sorted_years[-1],
        "years": sorted_years,
    }


def filter_graph_by_year(
    vault_path: Path,
    *,
    min_year: int | None = None,
    max_year: int | None = None,
) -> dict[str, Any]:
    """Return a filtered graph containing only nodes/edges within a year range.

    Nodes are included if:
      - They have a ``year`` attribute within ``[min_year, max_year]``, OR
      - They are concept nodes connected to at least one edge within the range.

    Edges are included if they have a ``year`` attribute within the range,
    or if they connect two included nodes and have no year attribute.

    Parameters
    ----------
    min_year:
        Earliest year to include (inclusive). ``None`` = no lower bound.
    max_year:
        Latest year to include (inclusive). ``None`` = no upper bound.

    Returns dict with ``nodes``, ``edges``, and ``range`` keys.
    """
    data = _load_graph_json(vault_path)
    if not data:
        return {"nodes": [], "edges": [], "range": {"min_year": min_year, "max_year": max_year}}

    all_nodes = {n["id"]: n for n in data.get("nodes", [])}
    all_edges = data.get("edges", [])

    def _year_in_range(y: Any) -> bool:
        if y is None:
            return True  # edges/nodes without year are included by default
        try:
            yi = int(y)
        except (ValueError, TypeError):
            return True
        if min_year is not None and yi < min_year:
            return False
        if max_year is not None and yi > max_year:
            return False
        return True

    def _node_year_in_range(n: dict) -> bool:
        y = n.get("year")
        if y is None:
            return True  # concepts without explicit year pass through
        return _year_in_range(y)

    # First pass: filter edges
    filtered_edges: list[dict] = []
    edge_node_ids: set[str] = set()
    for e in all_edges:
        ey = e.get("year")
        if _year_in_range(ey):
            src = _edge_src(e)
            dst = _edge_dst(e)
            filtered_edges.append(e)
            edge_node_ids.add(src)
            edge_node_ids.add(dst)

    # Second pass: include nodes that are in-range or connected by a surviving edge
    filtered_nodes: list[dict] = []
    for n in data.get("nodes", []):
        nid = n["id"]
        ntype = n.get("type", "concept")
        if ntype == "book":
            # Book nodes must match year range
            if _node_year_in_range(n):
                filtered_nodes.append(n)
        elif nid in edge_node_ids:
            # Concept/paragraph nodes survive if any edge references them
            filtered_nodes.append(n)

    return {
        "nodes": filtered_nodes,
        "edges": filtered_edges,
        "range": {"min_year": min_year, "max_year": max_year},
    }
