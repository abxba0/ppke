"""Knowledge Graph for PPKE - concept-level graph over extracted knowledge.

Represents all extracted concepts, claims, and their relations as a directed
graph (nodes = concepts/books, edges = semantic relations). Enables:
- Fast "concept expansion": all related ideas reachable from a seed concept
- Cross-book provenance tracking: which books/paragraphs mention a concept
- Ultra-scalable queries (10,000+ books) via graph traversal instead of LLM
- Tension/alignment detection at scale

NetworkX is an optional dependency. When not installed the graph gracefully
degrades to JSON-file-only storage.  Install with:  pip install networkx
(or: pip install "ppke[graph]")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_nx_available = False
try:
    import networkx as nx  # type: ignore[import]

    _nx_available = True
except ImportError:  # pragma: no cover
    pass

_GRAPH_FILE = "knowledge_graph.json"

# Edge relation types
REL_DEFINES = "defines"           # book/paragraph defines a concept
REL_CLAIMS = "claims"             # book/paragraph makes a claim about concept
REL_ASSUMES = "assumes"           # book/paragraph implicitly assumes concept
REL_RELATED = "related_to"        # two concepts are related
REL_CONTRADICTS = "contradicts"   # two concepts/claims contradict each other
REL_SUPPORTS = "supports"         # one concept/claim supports another


class KnowledgeGraph:
    """Graph-based intermediate layer over all PPKE extractions.

    Nodes:
        - ``concept:<name>``   — a philosophical concept (normalised, lowercase)
        - ``book:<folder>``    — a book (folder name)
        - ``para:<book>::<id>``— a paragraph

    Edges:
        - book  → concept  (defines / claims / assumes)
        - para  → concept  (defines / claims / assumes)
        - concept → concept (related_to / contradicts / supports)

    Node attributes:
        ``type`` ("concept" | "book" | "paragraph"),
        ``label`` (human-readable name),
        ``books`` (set of book folders that mention this concept)

    Usage::

        graph = KnowledgeGraph(vault_path)
        graph.add_book_extractions("Book_Foo", "Foo", "Bar", extractions)
        graph.save()

        # Query
        related = graph.expand_concept("dasein")
        provenance = graph.concept_provenance("dasein")
    """

    def __init__(self, vault_path: Path):
        self._vault_path = vault_path
        self._graph_path = vault_path / _GRAPH_FILE

        if _nx_available:
            self._g: Any = nx.DiGraph()
        else:
            self._g = None

        # Fallback storage: lightweight dict graph
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []

        self._load()

    # ── Persistence ──

    def _load(self) -> None:
        """Load existing graph from disk (JSON format)."""
        if not self._graph_path.exists():
            return
        try:
            data = json.loads(self._graph_path.read_text())
            for node in data.get("nodes", []):
                nid = node["id"]
                attrs = {k: v for k, v in node.items() if k != "id"}
                self._nodes[nid] = attrs
                if _nx_available:
                    self._g.add_node(nid, **attrs)
            for edge in data.get("edges", []):
                src, dst, rel = edge["src"], edge["dst"], edge["rel"]
                eattrs = {k: v for k, v in edge.items() if k not in ("src", "dst", "rel")}
                self._edges.append({"src": src, "dst": dst, "rel": rel, **eattrs})
                if _nx_available:
                    self._g.add_edge(src, dst, rel=rel, **eattrs)
        except Exception as exc:
            logger.error("Failed to load knowledge graph: %s", exc)

    def save(self) -> None:
        """Persist graph to disk as JSON."""
        if _nx_available:
            nodes = [
                {"id": n, **{k: list(v) if isinstance(v, set) else v for k, v in self._g.nodes[n].items()}}
                for n in self._g.nodes
            ]
            edges = [
                {"src": u, "dst": v, **{k: list(vv) if isinstance(vv, set) else vv for k, vv in d.items()}}
                for u, v, d in self._g.edges(data=True)
            ]
        else:
            nodes = [
                {"id": nid, **{k: list(v) if isinstance(v, set) else v for k, v in attrs.items()}}
                for nid, attrs in self._nodes.items()
            ]
            edges = [
                {k: list(v) if isinstance(v, set) else v for k, v in e.items()}
                for e in self._edges
            ]

        self._vault_path.mkdir(parents=True, exist_ok=True)
        self._graph_path.write_text(
            json.dumps({"nodes": nodes, "edges": edges}, indent=2, ensure_ascii=False)
        )

    # ── Graph building ──

    def _norm(self, concept: str) -> str:
        """Normalise a concept name for use as a node ID."""
        return concept.strip().lower().replace(" ", "_")[:80]

    def _add_node(self, node_id: str, **attrs) -> None:
        if _nx_available:
            if node_id not in self._g:
                self._g.add_node(node_id, **attrs)
            else:
                # Merge books set
                existing_books = self._g.nodes[node_id].get("books", set())
                new_books = attrs.get("books", set())
                if isinstance(existing_books, list):
                    existing_books = set(existing_books)
                if isinstance(new_books, list):
                    new_books = set(new_books)
                self._g.nodes[node_id]["books"] = existing_books | new_books
        else:
            if node_id not in self._nodes:
                self._nodes[node_id] = attrs
            else:
                existing = self._nodes[node_id].get("books", set())
                new = attrs.get("books", set())
                if isinstance(existing, list):
                    existing = set(existing)
                if isinstance(new, list):
                    new = set(new)
                self._nodes[node_id]["books"] = existing | new

    def _add_edge(self, src: str, dst: str, rel: str, **attrs) -> None:
        if _nx_available:
            self._g.add_edge(src, dst, rel=rel, **attrs)
        else:
            self._edges.append({"src": src, "dst": dst, "rel": rel, **attrs})

    def add_book_extractions(
        self,
        book_folder: str,
        book_title: str,
        author: str,
        extractions: list[dict[str, Any]],
    ) -> int:
        """Ingest extraction results into the graph.

        For each extraction, adds:
        - A book node
        - Concept nodes for every defined concept
        - Concept nodes for claims (distilled as concept labels)
        - book→concept edges for defines / claims / assumes

        Returns:
            Total number of graph edges added.
        """
        book_node = f"book:{book_folder}"
        self._add_node(
            book_node,
            type="book",
            label=f"{book_title} ({author})",
            title=book_title,
            author=author,
            books={book_folder},
        )

        edges_added = 0
        for ext in extractions:
            pid = ext.get("paragraph_id", "")
            para_node = f"para:{book_folder}::{pid}"

            # Paragraph node (lightweight: just connects book to para)
            self._add_node(
                para_node,
                type="paragraph",
                label=pid,
                books={book_folder},
                topic=ext.get("topic_sentence", "")[:120],
            )
            self._add_edge(book_node, para_node, rel="contains")
            edges_added += 1

            # Defined concepts → concept nodes
            for concept in ext.get("defined_concepts", []):
                if not concept or len(concept) < 2:
                    continue
                cid = f"concept:{self._norm(concept)}"
                self._add_node(
                    cid,
                    type="concept",
                    label=concept,
                    books={book_folder},
                )
                self._add_edge(para_node, cid, rel=REL_DEFINES, book=book_folder, pid=pid)
                self._add_edge(book_node, cid, rel=REL_DEFINES, book=book_folder)
                edges_added += 2

            # Explicit claims — extract key noun phrases as concept proxies
            for claim in ext.get("explicit_claims", []):
                if not claim or len(claim) < 4:
                    continue
                # Use the first 60 chars as the concept label
                claim_label = claim[:60].strip()
                cid = f"concept:{self._norm(claim_label)}"
                self._add_node(
                    cid,
                    type="concept",
                    label=claim_label,
                    books={book_folder},
                )
                self._add_edge(para_node, cid, rel=REL_CLAIMS, book=book_folder, pid=pid)
                edges_added += 1

            # Implicit assumptions
            for assumption in ext.get("implicit_assumptions", []):
                if not assumption or len(assumption) < 4:
                    continue
                assumption_label = assumption[:60].strip()
                cid = f"concept:{self._norm(assumption_label)}"
                self._add_node(
                    cid,
                    type="concept",
                    label=assumption_label,
                    books={book_folder},
                )
                self._add_edge(para_node, cid, rel=REL_ASSUMES, book=book_folder, pid=pid)
                edges_added += 1

        return edges_added

    def add_concept_relation(
        self,
        concept_a: str,
        concept_b: str,
        relation: str = REL_RELATED,
        **attrs,
    ) -> None:
        """Add a directed semantic relation between two concepts."""
        cid_a = f"concept:{self._norm(concept_a)}"
        cid_b = f"concept:{self._norm(concept_b)}"
        self._add_node(cid_a, type="concept", label=concept_a, books=set())
        self._add_node(cid_b, type="concept", label=concept_b, books=set())
        self._add_edge(cid_a, cid_b, rel=relation, **attrs)

    # ── Queries ──

    def expand_concept(
        self, concept: str, depth: int = 2
    ) -> list[dict[str, Any]]:
        """Return all concepts reachable from *concept* within *depth* hops.

        Each result includes the concept label, relation type, and which books
        mention it — enabling fast concept expansion for queries like
        "what ideas are related to X?".

        Returns:
            List of dicts: ``[{"concept_id", "label", "relation", "books", "distance"}, …]``
        """
        cid = f"concept:{self._norm(concept)}"
        results: list[dict] = []

        if _nx_available:
            if cid not in self._g:
                return []
            for node, data in nx.bfs_successors(self._g, cid, depth_limit=depth):
                for successor in data:
                    if not successor.startswith("concept:"):
                        continue
                    edge_data = self._g.get_edge_data(node, successor, default={})
                    attrs = self._g.nodes.get(successor, {})
                    books = attrs.get("books", set())
                    results.append(
                        {
                            "concept_id": successor,
                            "label": attrs.get("label", successor),
                            "relation": edge_data.get("rel", "related"),
                            "books": list(books) if isinstance(books, set) else books,
                            "distance": 1,  # BFS depth approximation
                        }
                    )
        else:
            # Fallback: linear scan of edges
            if cid not in self._nodes:
                return []
            seen = {cid}
            frontier = [cid]
            for d in range(depth):
                next_frontier = []
                for src in frontier:
                    for edge in self._edges:
                        if edge["src"] == src and edge["dst"].startswith("concept:"):
                            dst = edge["dst"]
                            if dst not in seen:
                                seen.add(dst)
                                next_frontier.append(dst)
                                attrs = self._nodes.get(dst, {})
                                books = attrs.get("books", set())
                                results.append(
                                    {
                                        "concept_id": dst,
                                        "label": attrs.get("label", dst),
                                        "relation": edge.get("rel", "related"),
                                        "books": list(books) if isinstance(books, set) else books,
                                        "distance": d + 1,
                                    }
                                )
                frontier = next_frontier

        return results

    def concept_provenance(self, concept: str) -> list[dict[str, Any]]:
        """Return all books and paragraphs that mention *concept*.

        Returns:
            List of dicts: ``[{"book_folder", "paragraph_id", "relation"}, …]``
        """
        cid = f"concept:{self._norm(concept)}"
        results: list[dict] = []

        if _nx_available:
            if cid not in self._g:
                return []
            for src, _, data in self._g.in_edges(cid, data=True):
                if src.startswith("para:"):
                    # para:<book_folder>::<pid>
                    parts = src.split("::", 1)
                    book_folder = parts[0].replace("para:", "")
                    pid = parts[1] if len(parts) > 1 else "?"
                    results.append(
                        {
                            "book_folder": book_folder,
                            "paragraph_id": pid,
                            "relation": data.get("rel", "?"),
                        }
                    )
        else:
            for edge in self._edges:
                if edge["dst"] == cid and edge["src"].startswith("para:"):
                    parts = edge["src"].split("::", 1)
                    book_folder = parts[0].replace("para:", "")
                    pid = parts[1] if len(parts) > 1 else "?"
                    results.append(
                        {
                            "book_folder": book_folder,
                            "paragraph_id": pid,
                            "relation": edge.get("rel", "?"),
                        }
                    )

        return results

    def books_mentioning(self, concept: str) -> list[str]:
        """Return a sorted list of book folders that mention *concept*."""
        cid = f"concept:{self._norm(concept)}"
        if _nx_available:
            if cid not in self._g:
                return []
            attrs = self._g.nodes[cid]
        else:
            attrs = self._nodes.get(cid, {})

        books = attrs.get("books", set())
        if isinstance(books, list):
            books = set(books)
        return sorted(books)

    def all_concepts(self) -> list[dict[str, Any]]:
        """Return all concept nodes with their metadata."""
        if _nx_available:
            return [
                {
                    "concept_id": n,
                    "label": self._g.nodes[n].get("label", n),
                    "books": list(self._g.nodes[n].get("books", set())),
                }
                for n in self._g.nodes
                if n.startswith("concept:")
            ]
        return [
            {
                "concept_id": nid,
                "label": attrs.get("label", nid),
                "books": list(attrs.get("books", set())),
            }
            for nid, attrs in self._nodes.items()
            if nid.startswith("concept:")
        ]

    def stats(self) -> dict[str, Any]:
        """Return high-level graph statistics."""
        if _nx_available:
            g = self._g
            n_books = sum(1 for n in g.nodes if n.startswith("book:"))
            n_concepts = sum(1 for n in g.nodes if n.startswith("concept:"))
            n_paras = sum(1 for n in g.nodes if n.startswith("para:"))
            n_edges = g.number_of_edges()
            connected_components = nx.number_weakly_connected_components(g) if g.nodes else 0
        else:
            n_books = sum(1 for n in self._nodes if n.startswith("book:"))
            n_concepts = sum(1 for n in self._nodes if n.startswith("concept:"))
            n_paras = sum(1 for n in self._nodes if n.startswith("para:"))
            n_edges = len(self._edges)
            connected_components = 0  # requires graph library

        return {
            "books": n_books,
            "concepts": n_concepts,
            "paragraphs": n_paras,
            "edges": n_edges,
            "weakly_connected_components": connected_components,
            "networkx_available": _nx_available,
        }

    def build_from_vault(self, vault_path: Path) -> dict[str, int]:
        """(Re-)build graph from all extractions.json files in the vault.

        Returns:
            Dict mapping book_folder → edges_added.
        """
        import yaml

        results: dict[str, int] = {}
        book_dirs = sorted(
            d for d in vault_path.iterdir() if d.is_dir() and d.name.startswith("Book_")
        )
        for book_dir in book_dirs:
            ext_path = book_dir / "extractions.json"
            if not ext_path.exists():
                continue
            try:
                extractions = json.loads(ext_path.read_text())
            except Exception as exc:
                logger.error("Failed reading %s: %s", ext_path, exc)
                continue

            meta: dict = {}
            meta_path = book_dir / "meta.yml"
            if meta_path.exists():
                try:
                    meta = yaml.safe_load(meta_path.read_text()) or {}
                except Exception:
                    pass

            edges = self.add_book_extractions(
                book_folder=book_dir.name,
                book_title=meta.get("title", book_dir.name),
                author=meta.get("author", "Unknown"),
                extractions=extractions,
            )
            results[book_dir.name] = edges

        return results
