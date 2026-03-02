"""Academic tools — literature review, bibliography, argument maps.

Provides LLM-powered academic content generation and structured bibliography
output from book metadata.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ── Shared helpers ──


def _load_meta(book_dir: Path) -> dict[str, Any]:
    meta_path = book_dir / "meta.yml"
    if meta_path.exists():
        return yaml.safe_load(meta_path.read_text()) or {}
    return {}


def _load_md_file(book_dir: Path, filename: str, max_chars: int = 0) -> str:
    path = book_dir / filename
    if not path.exists():
        return ""
    text = path.read_text()
    if max_chars and len(text) > max_chars:
        return text[:max_chars]
    return text


def _load_extractions(book_dir: Path) -> list[dict]:
    path = book_dir / "extractions.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


# ── Bibliography ──

_CITATION_FORMATS = {
    "apa": "apa",
    "mla": "mla",
    "chicago": "chicago",
}


def format_citation_apa(meta: dict[str, Any]) -> str:
    """Format a single citation in APA style."""
    author = meta.get("author", "Unknown")
    year = meta.get("year", "n.d.")
    title = meta.get("title", "Untitled")

    # APA: Author, A. A. (Year). *Title of work*.
    return f"{author} ({year}). *{title}*."


def format_citation_mla(meta: dict[str, Any]) -> str:
    """Format a single citation in MLA style."""
    author = meta.get("author", "Unknown")
    title = meta.get("title", "Untitled")
    year = meta.get("year", "")

    # MLA: Author. *Title*. Year.
    parts = [f"{author}.", f"*{title}*."]
    if year:
        parts.append(f"{year}.")
    return " ".join(parts)


def format_citation_chicago(meta: dict[str, Any]) -> str:
    """Format a single citation in Chicago style."""
    author = meta.get("author", "Unknown")
    title = meta.get("title", "Untitled")
    year = meta.get("year", "")

    # Chicago: Author. *Title*. Place: Publisher, Year.
    parts = [f"{author}.", f"*{title}*."]
    if year:
        parts.append(f"{year}.")
    return " ".join(parts)


_FORMATTERS = {
    "apa": format_citation_apa,
    "mla": format_citation_mla,
    "chicago": format_citation_chicago,
}


def generate_bibliography(vault_path: Path, style: str = "apa",
                           book_folders: list[str] | None = None) -> str:
    """Generate a formatted bibliography from all books in the vault.

    Parameters
    ----------
    vault_path : Path
        Root vault directory.
    style : str
        Citation style: ``apa``, ``mla``, or ``chicago``.
    book_folders : list[str] | None
        Specific book folders to include. If None, includes all.

    Returns
    -------
    str
        Markdown-formatted bibliography.
    """
    formatter = _FORMATTERS.get(style, format_citation_apa)
    style_label = {"apa": "APA (7th ed.)", "mla": "MLA (9th ed.)", "chicago": "Chicago (17th ed.)"}

    entries: list[tuple[str, str]] = []  # (sort_key, formatted_citation)

    book_dirs = sorted(vault_path.iterdir()) if vault_path.exists() else []
    for d in book_dirs:
        if not d.is_dir() or not d.name.startswith("Book_"):
            continue
        if book_folders and d.name not in book_folders:
            continue
        meta = _load_meta(d)
        if not meta:
            continue
        citation = formatter(meta)
        sort_key = meta.get("author", "ZZZ").lower()
        entries.append((sort_key, citation))

    entries.sort(key=lambda x: x[0])

    lines = [
        f"# Bibliography",
        f"*Format: {style_label.get(style, style.upper())}*",
        "",
        "---",
        "",
    ]
    for _, citation in entries:
        lines.append(f"- {citation}")

    if not entries:
        lines.append("*No books found in the library.*")

    lines.extend(["", f"---", f"*{len(entries)} sources*"])
    return "\n".join(lines)


def export_bibliography_bibtex(
    vault_path: Path,
    book_folders: list[str] | None = None,
) -> str:
    """Export all books in the vault as a BibTeX bibliography file.

    Parameters
    ----------
    vault_path : Path
        Root vault directory.
    book_folders : list[str] | None
        Specific book folders to include. If None, includes all.

    Returns
    -------
    str
        BibTeX source string containing one ``@book`` entry per book.
    """
    from ppke.export.exporters import meta_to_bibtex_entry

    lines = [
        "% BibTeX bibliography exported by PPKE",
        f"% Vault: {vault_path.name}",
        "",
    ]

    book_dirs = sorted(vault_path.iterdir()) if vault_path.exists() else []
    entry_count = 0
    seen_keys: set[str] = set()

    for d in book_dirs:
        if not d.is_dir() or not d.name.startswith("Book_"):
            continue
        if book_folders and d.name not in book_folders:
            continue
        meta = _load_meta(d)
        if not meta:
            continue

        # Ensure unique cite keys by appending a numeric suffix when needed
        from ppke.export.exporters import _make_cite_key
        base_key = _make_cite_key(meta)
        cite_key = base_key
        suffix = 2
        while cite_key in seen_keys:
            cite_key = f"{base_key}_{suffix}"
            suffix += 1
        seen_keys.add(cite_key)

        lines.append(meta_to_bibtex_entry(meta, cite_key=cite_key))
        lines.append("")
        entry_count += 1

    if entry_count == 0:
        lines.append("% No books found in the library.")

    lines.append(f"% {entry_count} entries")
    return "\n".join(lines)


# ── Literature Review ──


def generate_literature_review(
    vault_path: Path,
    llm_client: Any,
    book_folders: list[str] | None = None,
) -> str:
    """Generate a cross-book literature review using LLM synthesis.

    Gathers summaries, concept indices, and logical maps from selected books,
    then asks the LLM to produce a structured literature review section.

    Parameters
    ----------
    vault_path : Path
        Root vault directory.
    llm_client : LLMClient
        Configured LLM client instance.
    book_folders : list[str] | None
        Specific book folders. If None, uses all books.

    Returns
    -------
    str
        Markdown literature review.
    """
    book_summaries: list[str] = []

    book_dirs = sorted(vault_path.iterdir()) if vault_path.exists() else []
    for d in book_dirs:
        if not d.is_dir() or not d.name.startswith("Book_"):
            continue
        if book_folders and d.name not in book_folders:
            continue

        meta = _load_meta(d)
        title = meta.get("title", d.name)
        author = meta.get("author", "Unknown")
        year = meta.get("year", "")

        # Gather source material
        summary = _load_md_file(d, "summary.md", max_chars=1500)
        concepts = _load_md_file(d, "03_Concept_Index.md", max_chars=1000)
        logical = _load_md_file(d, "02_Logical_Map.md", max_chars=1000)
        patterns = _load_md_file(d, "06_Patterns.md", max_chars=800)

        block = f"### {title} ({author}{f', {year}' if year else ''})\n"
        if summary:
            block += f"**Summary:** {summary[:1000]}\n"
        if concepts:
            block += f"**Key Concepts:** {concepts[:600]}\n"
        if logical:
            block += f"**Logical Structure:** {logical[:600]}\n"
        if patterns:
            block += f"**Patterns:** {patterns[:500]}\n"

        book_summaries.append(block)

    if not book_summaries:
        return "# Literature Review\n\n*No books available for review. Upload and analyze at least two books first.*"

    source_material = "\n---\n".join(book_summaries)

    system = (
        "You are an expert academic writer. Write a structured literature review "
        "in clear, scholarly Markdown. Synthesize across sources rather than "
        "summarizing each one in turn. Use proper academic language."
    )

    user = f"""Write a literature review section synthesizing the following {len(book_summaries)} sources.

Use this exact Markdown structure:
# Literature Review

## Introduction
[1-2 paragraphs: scope of the review, what these works collectively address]

## Thematic Analysis
### [Theme 1 Title]
[Discuss how multiple sources address this theme, noting agreements and differences]

### [Theme 2 Title]
[Continue thematic analysis across sources]

### [Theme 3 Title]
[Additional theme if warranted]

## Key Debates & Disagreements
[Where do these authors disagree? What tensions exist between their positions?]

## Gaps in the Literature
[What questions remain unanswered? What topics need further investigation?]

## Conclusion
[Synthesize the overall state of knowledge represented by these sources]

---
SOURCE MATERIAL:

{source_material[:12000]}"""

    content = llm_client.complete(system, user)
    return content


# ── Argument Map ──


def generate_argument_map(book_dir: Path) -> dict[str, Any]:
    """Build a visual argument map from a book's logical map and extraction data.

    Returns a structured dict suitable for rendering as an interactive diagram:
    - nodes: list of argument nodes (claims, assumptions, conclusions)
    - edges: list of support/challenge relationships

    Parameters
    ----------
    book_dir : Path
        Book directory containing extractions.json and 02_Logical_Map.md.

    Returns
    -------
    dict with ``nodes``, ``edges``, ``stats`` keys.
    """
    extractions = _load_extractions(book_dir)
    meta = _load_meta(book_dir)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_id_map: dict[str, str] = {}  # text_key → node_id
    node_counter = 0

    def _add_node(label: str, node_type: str, paragraph_id: str = "") -> str:
        nonlocal node_counter
        key = label.lower().strip()[:80]
        if key in node_id_map:
            return node_id_map[key]
        node_id = f"arg_{node_counter}"
        node_counter += 1
        nodes.append({
            "id": node_id,
            "label": label[:150],
            "type": node_type,  # claim, assumption, conclusion, concept
            "paragraph_id": paragraph_id,
        })
        node_id_map[key] = node_id
        return node_id

    # Process extractions
    for ext in extractions:
        pid = ext.get("paragraph_id", "")

        # Explicit claims → claim nodes
        for claim in ext.get("explicit_claims", []):
            if len(claim) > 15:
                _add_node(claim, "claim", pid)

        # Implicit assumptions → assumption nodes
        for assumption in ext.get("implicit_assumptions", []):
            if len(assumption) > 15:
                _add_node(assumption, "assumption", pid)

        # Logical steps show support relationships
        logical_steps = ext.get("logical_steps", [])
        claims = ext.get("explicit_claims", [])
        assumptions = ext.get("implicit_assumptions", [])

        # Connect assumptions → claims (assumptions support claims)
        for assumption in assumptions[:3]:
            if len(assumption) <= 15:
                continue
            a_key = assumption.lower().strip()[:80]
            for claim in claims[:3]:
                if len(claim) <= 15:
                    continue
                c_key = claim.lower().strip()[:80]
                if a_key in node_id_map and c_key in node_id_map:
                    edges.append({
                        "source": node_id_map[a_key],
                        "target": node_id_map[c_key],
                        "relation": "supports",
                    })

        # Connect claims within same paragraph (they form an argument chain)
        claim_ids = []
        for claim in claims[:4]:
            if len(claim) > 15:
                c_key = claim.lower().strip()[:80]
                if c_key in node_id_map:
                    claim_ids.append(node_id_map[c_key])
        for i in range(len(claim_ids) - 1):
            edges.append({
                "source": claim_ids[i],
                "target": claim_ids[i + 1],
                "relation": "leads_to",
            })

    # Add concept nodes and connect to claims they appear with
    for ext in extractions:
        pid = ext.get("paragraph_id", "")
        concepts = ext.get("defined_concepts", [])
        claims = ext.get("explicit_claims", [])

        for concept in concepts[:3]:
            concept_id = _add_node(concept, "concept", pid)

            for claim in claims[:2]:
                c_key = claim.lower().strip()[:80]
                if c_key in node_id_map:
                    edges.append({
                        "source": concept_id,
                        "target": node_id_map[c_key],
                        "relation": "grounds",
                    })

    # Deduplicate edges
    seen_edges: set[tuple[str, str, str]] = set()
    unique_edges: list[dict] = []
    for e in edges:
        key = (e["source"], e["target"], e["relation"])
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)

    # Stats
    type_counts = {}
    for n in nodes:
        t = n["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "title": meta.get("title", book_dir.name),
        "nodes": nodes,
        "edges": unique_edges,
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(unique_edges),
            "type_counts": type_counts,
        },
    }


def argument_map_to_markdown(arg_map: dict[str, Any]) -> str:
    """Convert an argument map dict to a readable Markdown document."""
    title = arg_map.get("title", "Unknown")
    nodes = arg_map.get("nodes", [])
    edges = arg_map.get("edges", [])
    stats = arg_map.get("stats", {})

    lines = [
        f"# Argument Map: {title}",
        "",
        f"**{stats.get('total_nodes', 0)} nodes** · **{stats.get('total_edges', 0)} relationships**",
        "",
    ]

    # Group by type
    type_labels = {"claim": "Claims", "assumption": "Assumptions", "conclusion": "Conclusions", "concept": "Concepts"}
    by_type: dict[str, list[dict]] = {}
    for n in nodes:
        by_type.setdefault(n["type"], []).append(n)

    for node_type, label in type_labels.items():
        type_nodes = by_type.get(node_type, [])
        if not type_nodes:
            continue
        lines.append(f"## {label} ({len(type_nodes)})")
        lines.append("")
        for n in type_nodes[:20]:  # Cap display
            pid = f" [{n['paragraph_id']}]" if n.get("paragraph_id") else ""
            lines.append(f"- {n['label']}{pid}")
        lines.append("")

    # Key relationships
    if edges:
        lines.append("## Key Relationships")
        lines.append("")
        # Build node label lookup
        node_labels = {n["id"]: n["label"][:60] for n in nodes}
        rel_symbols = {"supports": "→ supports →", "leads_to": "→ leads to →", "grounds": "→ grounds →", "challenges": "→ challenges →"}
        for e in edges[:30]:  # Cap display
            src_label = node_labels.get(e["source"], e["source"])
            tgt_label = node_labels.get(e["target"], e["target"])
            rel = rel_symbols.get(e["relation"], f"→ {e['relation']} →")
            lines.append(f"- {src_label} {rel} {tgt_label}")
        lines.append("")

    return "\n".join(lines)
