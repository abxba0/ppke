"""Graph-to-Text narrative generation for PPKE.

Transforms a knowledge graph (concepts, claims, links, contradictions)
into a high-fidelity essay, structured report, or literature review,
preserving argument structure and analytical flow.

Supported output styles:
- ``"essay"``            — flowing prose that develops the central argument
- ``"report"``           — structured analytical report with sections
- ``"literature_review"``— academic synthesis tracing debates and gaps

All functions work from the ``knowledge_graph.json`` file in the vault.
NetworkX is **not** required.

Usage::

    from ppke.graph.narrative import generate_narrative
    from ppke.llm.client import LLMClient
    from ppke.config import Config

    config = Config()
    client = LLMClient(config.llm)
    text = generate_narrative(vault_path, client, style="essay")
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Number of top concepts to surface in the prompt
_DEFAULT_TOP_CONCEPTS = 25
# Maximum relationships to include in the prompt
_DEFAULT_MAX_RELATIONS = 40
# Maximum number of contradictions to highlight
_DEFAULT_MAX_CONTRADICTIONS = 15

_VALID_STYLES = frozenset({"essay", "report", "literature_review"})

# ── Prompt templates ─────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert academic writer and knowledge synthesiser. \
Your task is to transform structured knowledge-graph data into \
a coherent, high-fidelity piece of long-form writing. \
Preserve the argument structure and analytical flow encoded in \
the graph. Do not invent facts; work strictly from the provided data. \
Write in a scholarly but accessible register."""

_ESSAY_INSTRUCTIONS = """\
Write a flowing, argumentative **essay** (800-1200 words) that:
1. Opens with a thesis that emerges from the dominant concepts.
2. Develops each major concept in turn, weaving in the supporting \
   relationships (supports / defines / claims).
3. Acknowledges tensions and contradictions where they appear.
4. Closes with a synthesis that resolves or contextualises the tensions.

Produce **only** the essay text — no meta-commentary."""

_REPORT_INSTRUCTIONS = """\
Produce a structured **analytical report** with these sections:
## Executive Summary
## Key Concepts and Definitions
## Argument Architecture
## Supporting Evidence and Relationships
## Tensions and Contradictions
## Conclusions and Implications

Use bullet points where appropriate. 600-1000 words total.
Produce **only** the report — no meta-commentary."""

_LITERATURE_REVIEW_INSTRUCTIONS = """\
Write an academic **literature review** (900-1300 words) that:
1. Introduces the research area as defined by the concept network.
2. Groups sources (books) by the themes/clusters they address.
3. Traces the key debates (contradictions) across sources.
4. Highlights consensus positions (mutually-supporting claims).
5. Identifies gaps in the network — well-cited concepts with \
   no direct concept-to-concept links.
6. Concludes with open questions for future research.

Use an academic citation style: (Source, year) or [Source].
Produce **only** the literature review — no meta-commentary."""

_STYLE_INSTRUCTIONS: dict[str, str] = {
    "essay": _ESSAY_INSTRUCTIONS,
    "report": _REPORT_INSTRUCTIONS,
    "literature_review": _LITERATURE_REVIEW_INSTRUCTIONS,
}


# ── Internal helpers ──────────────────────────────────────────────────────────


def _load_graph_json(vault_path: Path) -> dict[str, Any] | None:
    """Load the raw JSON knowledge graph.  Returns None when no file exists."""
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


def _rank_concepts(
    data: dict[str, Any],
    top_n: int = _DEFAULT_TOP_CONCEPTS,
) -> list[dict[str, Any]]:
    """Rank concept nodes by how many other concepts they connect to.

    Falls back to book-mention count when edge data is sparse.

    Returns a list of dicts: ``[{"id", "label", "books", "degree"}, …]``
    """
    nodes = {n["id"]: n for n in data.get("nodes", [])}
    edges = data.get("edges", [])

    # Degree count — count only concept↔concept edges
    degree: dict[str, int] = defaultdict(int)
    for e in edges:
        src, dst = _edge_src(e), _edge_dst(e)
        if src.startswith("concept:"):
            degree[src] += 1
        if dst.startswith("concept:"):
            degree[dst] += 1

    concept_nodes = [n for n in data.get("nodes", []) if n.get("id", "").startswith("concept:")]
    ranked = sorted(
        concept_nodes,
        key=lambda n: (degree.get(n["id"], 0), len(n.get("books", []))),
        reverse=True,
    )
    result: list[dict[str, Any]] = []
    for n in ranked[:top_n]:
        books = n.get("books", [])
        if isinstance(books, str):
            books = [books]
        result.append(
            {
                "id": n["id"],
                "label": n.get("label", n["id"].replace("concept:", "")),
                "books": list(books),
                "degree": degree.get(n["id"], 0),
            }
        )
    return result


def _collect_relations(
    data: dict[str, Any],
    concept_ids: set[str],
    max_relations: int = _DEFAULT_MAX_RELATIONS,
) -> list[dict[str, Any]]:
    """Collect concept↔concept edges for the given concept set.

    Returns list of dicts: ``[{"source_label", "target_label", "relation"}, …]``
    """
    nodes = {n["id"]: n.get("label", n["id"]) for n in data.get("nodes", [])}
    relations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for e in data.get("edges", []):
        src, dst, rel = _edge_src(e), _edge_dst(e), _edge_rel(e)
        if not (src.startswith("concept:") and dst.startswith("concept:")):
            continue
        if src not in concept_ids and dst not in concept_ids:
            continue
        key = (src, dst, rel)
        if key in seen:
            continue
        seen.add(key)
        relations.append(
            {
                "source_label": nodes.get(src, src.replace("concept:", "")),
                "target_label": nodes.get(dst, dst.replace("concept:", "")),
                "relation": rel,
            }
        )
        if len(relations) >= max_relations:
            break
    return relations


def _collect_book_metadata(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of book nodes with their metadata."""
    books = []
    for n in data.get("nodes", []):
        if n.get("type") == "book" or n.get("id", "").startswith("book:"):
            books.append(
                {
                    "id": n["id"],
                    "label": n.get("label", n["id"].replace("book:", "")),
                    "title": n.get("title", ""),
                    "author": n.get("author", ""),
                    "year": n.get("year"),
                }
            )
    return books


def _detect_gaps(
    data: dict[str, Any],
    concept_ids: set[str],
    min_books: int = 2,
) -> list[str]:
    """Concepts present in 2+ books but not linked to any other concept."""
    connected: set[str] = set()
    for e in data.get("edges", []):
        src, dst = _edge_src(e), _edge_dst(e)
        if src.startswith("concept:") and dst.startswith("concept:"):
            connected.add(src)
            connected.add(dst)

    nodes_map = {n["id"]: n for n in data.get("nodes", [])}
    gaps = []
    for cid in concept_ids:
        if cid in connected:
            continue
        n = nodes_map.get(cid, {})
        books = n.get("books", [])
        if isinstance(books, (list, set)) and len(books) >= min_books:
            gaps.append(n.get("label", cid.replace("concept:", "")))
    return gaps[:10]


def build_graph_summary(
    vault_path: Path,
    *,
    top_concepts: int = _DEFAULT_TOP_CONCEPTS,
    max_relations: int = _DEFAULT_MAX_RELATIONS,
    max_contradictions: int = _DEFAULT_MAX_CONTRADICTIONS,
) -> dict[str, Any]:
    """Extract a structured summary of the knowledge graph for LLM prompting.

    Returns a dict with keys:
    - ``concepts``: ranked list of top concept dicts
    - ``supports``: list of (source_label, target_label) support edges
    - ``contradictions``: list of (source_label, target_label) contradiction edges
    - ``related``: list of (source_label, target_label) other relation edges
    - ``books``: list of book metadata dicts
    - ``gaps``: list of concept labels that are under-connected
    - ``stats``: high-level counts

    Returns an empty dict with an ``error`` key when no graph is found.
    """
    data = _load_graph_json(vault_path)
    if not data:
        return {"error": "No knowledge graph found at this vault path"}

    top = _rank_concepts(data, top_n=top_concepts)
    concept_ids = {c["id"] for c in top}

    all_relations = _collect_relations(data, concept_ids, max_relations=max_relations * 2)

    supports = [r for r in all_relations if r["relation"] in ("supports", "defines", "claims")][:max_relations]
    contradictions = [r for r in all_relations if r["relation"] == "contradicts"][:max_contradictions]
    related = [
        r for r in all_relations
        if r["relation"] not in ("supports", "defines", "claims", "contradicts")
    ][:max_relations]

    books = _collect_book_metadata(data)
    gaps = _detect_gaps(data, concept_ids)

    n_nodes = len(data.get("nodes", []))
    n_edges = len(data.get("edges", []))

    return {
        "concepts": top,
        "supports": supports,
        "contradictions": contradictions,
        "related": related,
        "books": books,
        "gaps": gaps,
        "stats": {
            "total_nodes": n_nodes,
            "total_edges": n_edges,
            "top_concept_count": len(top),
            "book_count": len(books),
        },
    }


def _build_user_prompt(summary: dict[str, Any], style: str, focus_concept: str | None) -> str:
    """Convert the graph summary into the LLM user prompt."""
    lines: list[str] = []

    stats = summary.get("stats", {})
    lines.append(
        f"# Knowledge Graph Summary\n"
        f"Total nodes: {stats.get('total_nodes', '?')} | "
        f"Total edges: {stats.get('total_edges', '?')} | "
        f"Books: {stats.get('book_count', '?')}\n"
    )

    if focus_concept:
        lines.append(f"**Focus concept:** {focus_concept}\n")

    # Books
    books = summary.get("books", [])
    if books:
        lines.append("## Source Books")
        for b in books[:20]:
            title = b.get("title") or b.get("label", "Unknown")
            author = b.get("author", "")
            year = b.get("year", "")
            entry = f"- {title}"
            if author:
                entry += f" — {author}"
            if year:
                entry += f" ({year})"
            lines.append(entry)
        lines.append("")

    # Top concepts
    concepts = summary.get("concepts", [])
    if concepts:
        lines.append("## Key Concepts (ranked by centrality)")
        for c in concepts:
            book_list = ", ".join(c.get("books", []))
            lines.append(f"- **{c['label']}** (degree: {c['degree']}, sources: {book_list or 'n/a'})")
        lines.append("")

    # Supports / defines
    supports = summary.get("supports", [])
    if supports:
        lines.append("## Supporting / Definitional Relationships")
        for r in supports:
            lines.append(f"- {r['source_label']} **{r['relation']}** {r['target_label']}")
        lines.append("")

    # Contradictions
    contradictions = summary.get("contradictions", [])
    if contradictions:
        lines.append("## Contradictions and Tensions")
        for r in contradictions:
            lines.append(f"- {r['source_label']} **contradicts** {r['target_label']}")
        lines.append("")

    # Other relations
    related = summary.get("related", [])
    if related:
        lines.append("## Other Conceptual Links")
        for r in related[:20]:
            lines.append(f"- {r['source_label']} → {r['target_label']} ({r['relation']})")
        lines.append("")

    # Gaps
    gaps = summary.get("gaps", [])
    if gaps:
        lines.append("## Under-connected Concepts (potential research gaps)")
        for g in gaps:
            lines.append(f"- {g}")
        lines.append("")

    # Writing instructions
    instructions = _STYLE_INSTRUCTIONS.get(style, _ESSAY_INSTRUCTIONS)
    lines.append("---")
    lines.append(f"## Writing Task\n{instructions}")

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────


def generate_narrative(
    vault_path: Path,
    llm_client: Any,
    *,
    style: str = "essay",
    focus_concept: str | None = None,
    top_concepts: int = _DEFAULT_TOP_CONCEPTS,
    max_relations: int = _DEFAULT_MAX_RELATIONS,
) -> str:
    """Generate a long-form narrative from the knowledge graph.

    Parameters
    ----------
    vault_path:
        Path to the PPKE vault directory containing ``knowledge_graph.json``.
    llm_client:
        An ``LLMClient`` instance (from ``ppke.llm.client``).
    style:
        One of ``"essay"``, ``"report"``, or ``"literature_review"``.
    focus_concept:
        Optional concept label to centre the narrative around.  When
        provided, the prompt explicitly highlights this concept.
    top_concepts:
        How many of the most-connected concepts to surface.
    max_relations:
        Maximum number of relationships to include in the prompt.

    Returns
    -------
    str
        The generated narrative text.

    Raises
    ------
    ValueError
        If *style* is not one of the supported values or no knowledge graph
        exists in *vault_path*.
    """
    if style not in _VALID_STYLES:
        raise ValueError(
            f"Unknown style {style!r}. Must be one of: {sorted(_VALID_STYLES)}"
        )

    summary = build_graph_summary(
        vault_path,
        top_concepts=top_concepts,
        max_relations=max_relations,
    )
    if "error" in summary:
        raise ValueError(summary["error"])

    user_prompt = _build_user_prompt(summary, style, focus_concept)

    logger.info(
        "Generating graph narrative (style=%s, focus=%s, concepts=%d)",
        style,
        focus_concept,
        len(summary.get("concepts", [])),
    )

    return llm_client.complete(_SYSTEM_PROMPT, user_prompt)
