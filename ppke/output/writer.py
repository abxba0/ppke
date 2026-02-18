"""Output writer - generates all book files for the KnowledgeBase vault."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from ppke.parser.models import (
    Book,
    CoverageReport,
    ExtractionResult,
)

logger = logging.getLogger(__name__)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── Per-book files ──


def write_meta_yml(
    book_dir: Path,
    book: Book,
    coverage: CoverageReport,
    agent_version: str = "ppke-0.1.0",
    human_operator: str = "",
) -> Path:
    """Write meta.yml with book metadata.

    Includes all fields required by spec section 10 (Versioning & Permanence).
    """
    meta = {
        "title": book.title,
        "author": book.author,
        "year": book.year,
        "source_format": "markdown",
        "source_path": book.source_path,
        "ingest_date": coverage.ingest_date,
        "ingest_mode": coverage.ingest_mode,
        "agent_version": agent_version,
        "human_operator": human_operator or "unspecified",
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
            lines.append("**Original Text:**")
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
                    f"- {shift.get('from_id', '?')} -> {shift.get('to_id', '?')}: "
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
    """Write 04_Author_Model.md with all 7 sections from the spec."""
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
    """Write 05_Coverage_Report.md matching the spec format exactly."""
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


def _save_extractions_json(book_dir: Path, extractions: list[ExtractionResult]) -> Path:
    """Persist extraction data as JSON for re-read support."""
    data = []
    for ext in extractions:
        data.append({
            "paragraph_id": ext.paragraph_id,
            "original_text": ext.original_text,
            "topic_sentence": ext.topic_sentence,
            "function_in_argument": ext.function_in_argument,
            "explicit_claims": ext.explicit_claims,
            "implicit_assumptions": ext.implicit_assumptions,
            "logical_steps": ext.logical_steps,
            "defined_concepts": ext.defined_concepts,
            "emotional_tone": ext.emotional_tone,
            "tone_evidence": ext.tone_evidence,
            "internal_references": ext.internal_references,
            "is_argument_carrying": ext.is_argument_carrying,
            "depth": ext.depth.value,
        })
    path = book_dir / "extractions.json"
    path.write_text(json.dumps(data, indent=1))
    return path


def load_extractions_json(book_dir: Path) -> list[ExtractionResult]:
    """Load previously saved extraction data from JSON."""
    from ppke.parser.models import DepthLevel

    path = book_dir / "extractions.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    results = []
    for item in data:
        depth_str = item.get("depth", "LIGHT")
        try:
            depth = DepthLevel(depth_str)
        except ValueError:
            depth = DepthLevel.LIGHT
        results.append(ExtractionResult(
            paragraph_id=item["paragraph_id"],
            original_text=item.get("original_text", ""),
            topic_sentence=item.get("topic_sentence", ""),
            function_in_argument=item.get("function_in_argument", ""),
            explicit_claims=item.get("explicit_claims", []),
            implicit_assumptions=item.get("implicit_assumptions", []),
            logical_steps=item.get("logical_steps", []),
            defined_concepts=item.get("defined_concepts", []),
            emotional_tone=item.get("emotional_tone", ""),
            tone_evidence=item.get("tone_evidence", ""),
            internal_references=item.get("internal_references", []),
            is_argument_carrying=item.get("is_argument_carrying", False),
            depth=depth,
        ))
    return results


def write_all_book_files(
    vault_path: Path,
    book: Book,
    extractions: list[ExtractionResult],
    logical_map: dict[str, Any],
    concept_data: dict[str, Any],
    author_model: dict[str, Any],
    coverage: CoverageReport,
    human_operator: str = "",
) -> Path:
    """Write all files for a book to the KnowledgeBase vault.

    Returns the book directory path.
    """
    book_dir = _ensure_dir(vault_path / book.folder_name)
    logger.info("Writing book files to %s", book_dir)

    write_meta_yml(book_dir, book, coverage, human_operator=human_operator)
    write_raw_structure(book_dir, book, extractions)
    write_logical_map(book_dir, book, logical_map)
    write_concept_index(book_dir, book, concept_data)
    write_author_model(book_dir, book, author_model)
    write_coverage_report(book_dir, coverage)
    _save_extractions_json(book_dir, extractions)

    logger.info("All files written for %s", book.title)
    return book_dir


# ── Global vault files (spec section 4) ──


def _deduplicate_concepts(
    concepts_by_book: dict[str, list[str]],
    config: Any,
) -> list[dict[str, Any]]:
    """Use LLM to semantically deduplicate concepts across books.

    Returns a list of concept groups with canonical names and members.
    Falls back to empty list on failure.
    """
    from ppke.llm.client import LLMClient
    from ppke.llm.prompts import CONCEPT_DEDUP_SYSTEM, CONCEPT_DEDUP_USER

    try:
        client = LLMClient(config.llm)
        user_prompt = CONCEPT_DEDUP_USER.format(
            concepts_by_book_json=json.dumps(concepts_by_book, indent=1),
        )
        result = client.complete_json(CONCEPT_DEDUP_SYSTEM, user_prompt)
        groups = result.get("groups", [])
        # Only keep groups with 2+ members (actual cross-book matches)
        return [g for g in groups if len(g.get("members", [])) >= 2]
    except Exception as e:
        logger.warning("Concept deduplication failed (non-fatal): %s", e)
        return []


def write_global_files(vault_path: Path, config: Any) -> None:
    """Write/update the global KnowledgeBase files.

    These live at the vault root, not inside any book folder:
    - 00_PROJECT_SETTINGS.md
    - MASTER_CONCEPT_INDEX.md
    - QA_RESULTS.md
    - PLAYBOOK.md
    """
    _ensure_dir(vault_path)

    # Discover all encoded books
    book_dirs = sorted(
        d for d in vault_path.iterdir()
        if d.is_dir() and d.name.startswith("Book_")
    )

    book_list_lines = []
    for bd in book_dirs:
        meta_path = bd / "meta.yml"
        if meta_path.exists():
            meta = yaml.safe_load(meta_path.read_text()) or {}
            status = meta.get("verification_status", "UNKNOWN")
            book_list_lines.append(
                f"- **{bd.name}** — {meta.get('title', '?')} by "
                f"{meta.get('author', '?')} [{status}]"
            )
        else:
            book_list_lines.append(f"- **{bd.name}** — (no meta.yml)")

    book_list = "\n".join(book_list_lines) if book_list_lines else "(none yet)"

    # 00_PROJECT_SETTINGS.md
    settings_content = (
        "# PPKE Project Settings\n"
        "\n"
        "## Configuration\n"
        f"- **Vault Path:** {config.vault_path}\n"
        f"- **LLM Provider:** {config.llm.provider}\n"
        f"- **Model:** {config.llm.model}\n"
        f"- **Selective Depth:** {config.selective_depth}\n"
        f"- **Double Pass:** {config.double_pass}\n"
        "\n"
        "## Encoded Books\n"
        f"{book_list}\n"
        "\n"
        "## Last Updated\n"
        f"{date.today().isoformat()}\n"
    )
    (vault_path / "00_PROJECT_SETTINGS.md").write_text(settings_content)

    # MASTER_CONCEPT_INDEX.md — aggregate concepts with semantic deduplication
    master_lines = [
        "# Master Concept Index",
        "",
        "Cross-book concept tracking with semantic deduplication.",
        "```",
        "Book_Folder_Name -> {CH}.p{P}",
        "```",
        "",
    ]

    # Collect concept names per book for deduplication
    concepts_by_book: dict[str, list[str]] = {}
    for bd in book_dirs:
        concept_path = bd / "03_Concept_Index.md"
        if concept_path.exists():
            content = concept_path.read_text()
            names = re.findall(r"^## (.+)$", content, re.MULTILINE)
            if names:
                concepts_by_book[bd.name] = names

    # Attempt semantic deduplication if 2+ books have concepts
    dedup_groups: list[dict[str, Any]] = []
    if len(concepts_by_book) >= 2 and config.llm.active_api_key:
        dedup_groups = _deduplicate_concepts(concepts_by_book, config)

    if dedup_groups:
        master_lines.append("## Semantic Groups (Cross-Book)")
        master_lines.append("")
        for group in dedup_groups:
            canonical = group.get("canonical_name", "Unknown")
            master_lines.append(f"### {canonical}")
            master_lines.append("")
            members = group.get("members", [])
            for m in members:
                reason = m.get("reason", "")
                reason_str = f" — {reason}" if reason else ""
                master_lines.append(
                    f"- **{m.get('book_folder', '?')}**: "
                    f"{m.get('concept_name', '?')}{reason_str}"
                )
            master_lines.append("")
        master_lines.append("---")
        master_lines.append("")

    # Per-book concept index (full content)
    for bd in book_dirs:
        concept_path = bd / "03_Concept_Index.md"
        if concept_path.exists():
            master_lines.append(f"## From: {bd.name}")
            master_lines.append("")
            content = concept_path.read_text()
            for line in content.split("\n"):
                if line.startswith("# Concept Index") or line.startswith("**Author:**"):
                    continue
                master_lines.append(line)
            master_lines.append("")

    (vault_path / "MASTER_CONCEPT_INDEX.md").write_text("\n".join(master_lines))

    # QA_RESULTS.md — aggregate coverage status
    qa_lines = [
        "# QA Results",
        "",
        "## Book Verification Status",
        "",
    ]
    all_complete = True
    for bd in book_dirs:
        report_path = bd / "05_Coverage_Report.md"
        if report_path.exists():
            content = report_path.read_text()
            qa_lines.append(f"### {bd.name}")
            qa_lines.append("")
            qa_lines.append(content)
            qa_lines.append("")
            if "INCOMPLETE" in content:
                all_complete = False
        else:
            qa_lines.append(f"### {bd.name}")
            qa_lines.append("- **Status:** NO COVERAGE REPORT FOUND")
            qa_lines.append("")
            all_complete = False

    qa_lines.append("---")
    qa_lines.append("")
    qa_lines.append(f"**Overall Status:** {'ALL COMPLETE' if all_complete else 'INCOMPLETE — review missing books above'}")
    qa_lines.append(f"**Last checked:** {date.today().isoformat()}")

    (vault_path / "QA_RESULTS.md").write_text("\n".join(qa_lines))

    # PLAYBOOK.md
    playbook_content = (
        "# PPKE Playbook\n"
        "\n"
        "## Commands\n"
        "\n"
        "### Ingest a Book\n"
        "```bash\n"
        'ppke ingest <book.md> --title "Title" --author "Author" --year YYYY\n'
        "```\n"
        "\n"
        "### Parse Only (dry run, no LLM)\n"
        "```bash\n"
        'ppke parse <book.md> --title "Title" --author "Author"\n'
        "```\n"
        "\n"
        "### Query a Single Book\n"
        "```bash\n"
        'ppke query --book "Book_Title_Author_YYYY" --question "Your question"\n'
        "```\n"
        "\n"
        "### Cross-Book Query\n"
        "```bash\n"
        'ppke cross-query --question "Your question"\n'
        "```\n"
        "\n"
        "### Configure\n"
        "```bash\n"
        "ppke config --show\n"
        "ppke config --provider anthropic --model claude-sonnet-4-20250514\n"
        "ppke config --vault-path /path/to/vault\n"
        "```\n"
        "\n"
        "## File Structure\n"
        "\n"
        "Each book produces:\n"
        "- `meta.yml` — Book metadata and versioning\n"
        "- `01_Raw_Structure.md` — Per-paragraph structural extraction\n"
        "- `02_Logical_Map.md` — Argument architecture\n"
        "- `03_Concept_Index.md` — Concept tracking with semantic drift\n"
        "- `04_Author_Model.md` — Author's intellectual framework (7 sections)\n"
        "- `05_Coverage_Report.md` — Completeness verification\n"
        "\n"
        "Global vault files:\n"
        "- `00_PROJECT_SETTINGS.md` — Configuration and book inventory\n"
        "- `MASTER_CONCEPT_INDEX.md` — Cross-book concept aggregation\n"
        "- `QA_RESULTS.md` — Aggregated quality assurance results\n"
        "- `PLAYBOOK.md` — This file\n"
    )
    (vault_path / "PLAYBOOK.md").write_text(playbook_content)

    logger.info("Global vault files updated at %s", vault_path)
