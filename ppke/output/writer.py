"""Output writer - generates all book files for the KnowledgeBase vault."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from ppke.parser.models import (
    Book,
    CoverageReport,
    DepthLevel,
    ExtractionResult,
)

logger = logging.getLogger(__name__)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_meta_yml(
    book_dir: Path,
    book: Book,
    coverage: CoverageReport,
    agent_version: str = "ppke-0.1.0",
) -> Path:
    """Write meta.yml with book metadata."""
    meta = {
        "title": book.title,
        "author": book.author,
        "year": book.year,
        "source_format": "markdown",
        "source_path": book.source_path,
        "ingest_date": coverage.ingest_date,
        "ingest_mode": coverage.ingest_mode,
        "agent_version": agent_version,
        "total_chapters": coverage.total_chapters,
        "total_paragraphs": coverage.total_paragraphs,
        "verification_status": coverage.verification_status,
    }
    path = book_dir / "meta.yml"
    path.write_text(yaml.dump(meta, default_flow_style=False, sort_keys=False))
    logger.info("Wrote %s", path)
    return path


def write_raw_structure(
    book_dir: Path,
    book: Book,
    extractions: list[ExtractionResult],
) -> Path:
    """Write 01_Raw_Structure.md with per-paragraph extraction data."""
    extraction_map = {e.paragraph_id: e for e in extractions}
    lines = [
        f"# Raw Structure: {book.title}",
        f"**Author:** {book.author}",
        "",
    ]

    for chapter in book.chapters:
        lines.append(f"## Chapter {chapter.number:02d}: {chapter.title}")
        lines.append("")

        for para in chapter.paragraphs:
            ext = extraction_map.get(para.paragraph_id)
            lines.append(f"### {para.paragraph_id}")
            lines.append("")
            lines.append(f"**Original Text:**")
            lines.append(f"> {para.text}")
            lines.append("")

            if ext:
                lines.append(f"**Topic:** {ext.topic_sentence}")
                lines.append(f"**Function:** {ext.function_in_argument}")
                lines.append(f"**Depth:** {ext.depth.value}")
                lines.append("")

                if ext.explicit_claims:
                    lines.append("**Explicit Claims:**")
                    for claim in ext.explicit_claims:
                        lines.append(f"- {claim}")
                    lines.append("")

                if ext.depth == DepthLevel.FULL:
                    if ext.implicit_assumptions:
                        lines.append("**Implicit Assumptions:**")
                        for assumption in ext.implicit_assumptions:
                            lines.append(f"- {assumption}")
                        lines.append("")

                    if ext.logical_steps:
                        lines.append("**Logical Steps:**")
                        for step in ext.logical_steps:
                            lines.append(f"- {step}")
                        lines.append("")

                if ext.defined_concepts:
                    lines.append("**Defined Concepts:**")
                    for concept in ext.defined_concepts:
                        lines.append(f"- {concept}")
                    lines.append("")

                if ext.emotional_tone:
                    lines.append(f"**Tone:** {ext.emotional_tone}")
                    if ext.tone_evidence:
                        lines.append(f"**Tone Evidence:** \"{ext.tone_evidence}\"")
                    lines.append("")

                if ext.internal_references:
                    lines.append("**Internal References:**")
                    for ref in ext.internal_references:
                        lines.append(f"- {ref}")
                    lines.append("")

            lines.append("---")
            lines.append("")

    path = book_dir / "01_Raw_Structure.md"
    path.write_text("\n".join(lines))
    logger.info("Wrote %s", path)
    return path


def write_logical_map(
    book_dir: Path,
    book: Book,
    logical_map: dict[str, Any],
) -> Path:
    """Write 02_Logical_Map.md."""
    lines = [
        f"# Logical Map: {book.title}",
        f"**Author:** {book.author}",
        "",
    ]

    thesis = logical_map.get("central_thesis", {})
    lines.append("## Central Thesis")
    lines.append(f"**Claim:** {thesis.get('claim', 'N/A')}")
    lines.append(f"**Paragraph IDs:** {', '.join(thesis.get('paragraph_ids', []))}")
    lines.append(f"**Evidence:** {thesis.get('evidence', 'N/A')}")
    lines.append("")

    threads = logical_map.get("argument_threads", [])
    if threads:
        lines.append("## Argument Threads")
        lines.append("")
        for i, thread in enumerate(threads, 1):
            lines.append(f"### Thread {i}: {thread.get('name', 'Unnamed')}")
            lines.append("")
            premises = thread.get("premises", [])
            if premises:
                lines.append("**Premises:**")
                for p in premises:
                    inference_tag = " [INFERENCE]" if p.get("is_inference") else ""
                    ids = ", ".join(p.get("paragraph_ids", []))
                    lines.append(f"- {p.get('claim', '')}{inference_tag} ({ids})")
                lines.append("")

            conclusion = thread.get("conclusion", {})
            if conclusion:
                ids = ", ".join(conclusion.get("paragraph_ids", []))
                lines.append(f"**Conclusion:** {conclusion.get('claim', '')} ({ids})")
                lines.append("")

            issues = thread.get("logical_issues", [])
            if issues:
                lines.append("**Logical Issues:**")
                for issue in issues:
                    lines.append(f"- {issue}")
                lines.append("")

    assumptions = logical_map.get("key_assumptions", [])
    if assumptions:
        lines.append("## Key Assumptions")
        for a in assumptions:
            lines.append(f"- {a.get('assumption', '')}")
            deps = a.get("depends_on", [])
            if deps:
                lines.append(f"  - Depends on: {', '.join(deps)}")
        lines.append("")

    path = book_dir / "02_Logical_Map.md"
    path.write_text("\n".join(lines))
    logger.info("Wrote %s", path)
    return path


def write_concept_index(
    book_dir: Path,
    book: Book,
    concept_data: dict[str, Any],
) -> Path:
    """Write 03_Concept_Index.md."""
    lines = [
        f"# Concept Index: {book.title}",
        f"**Author:** {book.author}",
        "",
    ]

    concepts = concept_data.get("concepts", [])
    for concept in concepts:
        lines.append(f"## {concept.get('name', 'Unknown')}")
        lines.append("")

        definition = concept.get("definition", "")
        if definition:
            lines.append(f"**Definition:** {definition}")
            lines.append("")

        occurrences = concept.get("occurrences", [])
        if occurrences:
            lines.append("**Occurrences:**")
            for occ in occurrences:
                pid = occ.get("paragraph_id", "?")
                quote = occ.get("quote", "")
                context = occ.get("usage_context", "")
                lines.append(f"- **{pid}**: \"{quote}\"")
                if context:
                    lines.append(f"  - Context: {context}")
            lines.append("")

        shifts = concept.get("semantic_shifts", [])
        if shifts:
            lines.append("**Semantic Shifts:**")
            for shift in shifts:
                lines.append(
                    f"- {shift.get('from_id', '?')} → {shift.get('to_id', '?')}: "
                    f"{shift.get('description', '')}"
                )
            lines.append("")

        related = concept.get("related_concepts", [])
        if related:
            lines.append(f"**Related:** {', '.join(related)}")
            lines.append("")

        lines.append("---")
        lines.append("")

    path = book_dir / "03_Concept_Index.md"
    path.write_text("\n".join(lines))
    logger.info("Wrote %s", path)
    return path


def write_author_model(
    book_dir: Path,
    book: Book,
    author_model: dict[str, Any],
) -> Path:
    """Write 04_Author_Model.md."""
    lines = [
        f"# Author Model: {book.author}",
        f"**Based on:** {book.title}",
        "",
    ]

    sections = [
        ("Ontology", "ontology"),
        ("Epistemology", "epistemology"),
        ("Moral Framework", "moral_framework"),
        ("Emotional Philosophy", "emotional_philosophy"),
        ("Logical Style", "logical_style"),
        ("Recurring Structural Pattern", "recurring_pattern"),
    ]

    for heading, key in sections:
        section = author_model.get(key, {})
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(section.get("description", "N/A"))
        lines.append("")
        evidence = section.get("evidence", [])
        if evidence:
            lines.append("**Evidence:**")
            for e in evidence:
                pid = e.get("paragraph_id", "?")
                quote = e.get("quote", "")
                lines.append(f"- **{pid}**: \"{quote}\"")
            lines.append("")

    tensions = author_model.get("core_tensions", [])
    if tensions:
        lines.append("## Core Tensions")
        lines.append("")
        for t in tensions:
            lines.append(f"### {t.get('tension', 'Unknown')}")
            evidence = t.get("evidence", [])
            if evidence:
                for e in evidence:
                    pid = e.get("paragraph_id", "?")
                    quote = e.get("quote", "")
                    lines.append(f"- **{pid}**: \"{quote}\"")
            lines.append("")

    path = book_dir / "04_Author_Model.md"
    path.write_text("\n".join(lines))
    logger.info("Wrote %s", path)
    return path


def write_coverage_report(
    book_dir: Path,
    coverage: CoverageReport,
) -> Path:
    """Write 05_Coverage_Report.md."""
    lines = [
        "# Coverage Report",
        "",
        f"- **total_chapters:** {coverage.total_chapters}",
        f"- **total_paragraphs:** {coverage.total_paragraphs}",
        f"- **processed_paragraphs_count:** {coverage.processed_paragraph_count}",
        f"- **missing_paragraph_ids:** {coverage.missing_paragraph_ids or '[]'}",
        f"- **re_read_pass_completed:** {'yes' if coverage.re_read_pass_completed else 'no'}",
        f"- **verification_status:** {coverage.verification_status}",
        f"- **ingest_mode:** {coverage.ingest_mode}",
        f"- **ingest_date:** {coverage.ingest_date}",
        f"- **notes:** {coverage.notes or 'none'}",
    ]

    path = book_dir / "05_Coverage_Report.md"
    path.write_text("\n".join(lines))
    logger.info("Wrote %s", path)
    return path


def write_all_book_files(
    vault_path: Path,
    book: Book,
    extractions: list[ExtractionResult],
    logical_map: dict[str, Any],
    concept_data: dict[str, Any],
    author_model: dict[str, Any],
    coverage: CoverageReport,
) -> Path:
    """Write all files for a book to the KnowledgeBase vault.

    Returns the book directory path.
    """
    book_dir = _ensure_dir(vault_path / book.folder_name)
    logger.info("Writing book files to %s", book_dir)

    write_meta_yml(book_dir, book, coverage)
    write_raw_structure(book_dir, book, extractions)
    write_logical_map(book_dir, book, logical_map)
    write_concept_index(book_dir, book, concept_data)
    write_author_model(book_dir, book, author_model)
    write_coverage_report(book_dir, coverage)

    logger.info("All files written for %s", book.title)
    return book_dir
