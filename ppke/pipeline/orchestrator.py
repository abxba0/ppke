"""Master Controller - orchestrates the full book ingestion pipeline."""

from __future__ import annotations

import json
import logging
import re as _re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import yaml

from ppke.config import Config
from ppke.llm.client import LLMClient
from ppke.llm.prompts import AUTHOR_MODEL_SYSTEM, AUTHOR_MODEL_USER
from ppke.output.writer import load_extractions_json, write_all_book_files, write_global_files
from ppke.parser.markdown import split_long_paragraphs
from ppke.parser.models import Book, Chapter, DepthLevel, ExtractionResult
from ppke.pipeline.concepts import build_concept_index
from ppke.pipeline.extractor import extract_chapter
from ppke.pipeline.logical_map import build_logical_map
from ppke.pipeline.patterns import detect_patterns
from ppke.pipeline.validator import (
    EXTRACTION_FAILED_MARKER,
    validate_chapter_coverage,
    validate_coverage,
)
from ppke.progress.tracker import ProgressTracker
from ppke.vectordb.store import VectorStore
from ppke.graph.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

_progress_lock = threading.Lock()

ProgressCallback = Callable[[str, str], None]

# ── Skip Logic ──

# Regex matching strings that are just page numbers (digits, roman numerals)
_PAGE_NUMBER_RE = _re.compile(r'^[ivxlcdmIVXLCDM\d]+$')

# Maximum word count for a paragraph to be considered "low information"
# Only single-word paragraphs are skipped per spec ("boilerplate, single words, page numbers")
_LOW_INFO_MAX_WORDS = 1

# Common boilerplate patterns (case-insensitive prefix/whole matches)
_BOILERPLATE_PATTERNS = (
    "all rights reserved",
    "copyright",
    "printed in",
    "isbn",
    "published by",
    "first published",
    "table of contents",
    "acknowledgements",
    "acknowledgments",
    "bibliography",
    "index",
    "glossary",
    "about the author",
    "also by",
)


def _is_low_information(text: str) -> bool:
    """Return True if *text* is a low-information paragraph that should be skipped.

    Skipped paragraphs include:
    - Very short text (≤ _LOW_INFO_MAX_WORDS words)
    - Bare page numbers (digits or roman numerals only)
    - Common boilerplate lines
    """
    stripped = text.strip()
    if not stripped:
        return True
    words = stripped.split()
    # Single token: check for page numbers (digits or roman numerals)
    if len(words) == 1 and _PAGE_NUMBER_RE.match(stripped):
        return True
    # Very short paragraphs
    if len(words) <= _LOW_INFO_MAX_WORDS:
        return True
    # Boilerplate prefix/whole match
    lower = stripped.lower()
    for pattern in _BOILERPLATE_PATTERNS:
        if lower.startswith(pattern):
            return True
    return False


# ── Stop-word chapter detection ──

# Built-in skip titles (always applied regardless of domain template)
_SKIP_CHAPTER_TITLES: frozenset[str] = frozenset({
    "bibliography", "index", "appendix", "appendices",
    "references", "works cited", "glossary", "endnotes",
    "notes", "further reading", "about the author",
})


def _is_skip_chapter(title: str, extra_skip: frozenset[str] | None = None) -> bool:
    """Return True if the chapter title matches a non-content section.

    Args:
        title: Chapter title to test.
        extra_skip: Additional lowercase skip titles loaded from the active
            domain template's ``skip_chapters`` list.
    """
    normalised = title.strip().lower()
    if normalised in _SKIP_CHAPTER_TITLES:
        return True
    if extra_skip and normalised in extra_skip:
        return True
    return False


# ── Checkpoint support ──


def _checkpoint_path(vault_path: Path, book_folder: str) -> Path:
    """Return path for the in-progress checkpoint file."""
    return vault_path / f".checkpoint_{book_folder}.json"


def _save_checkpoint(
    path: Path,
    completed_indices: list[int],
    extractions: list[ExtractionResult],
) -> None:
    """Save extraction checkpoint after each chapter completes.

    Omits empty list fields and uses compact JSON to minimize checkpoint
    file size.  original_text is still included so that resumed runs can
    pass complete ExtractionResult objects to downstream stages.
    """
    ext_list = []
    for ext in extractions:
        entry: dict[str, Any] = {
            "paragraph_id": ext.paragraph_id,
            "original_text": ext.original_text,
            "topic_sentence": ext.topic_sentence,
            "function_in_argument": ext.function_in_argument,
            "depth": ext.depth.value,
        }
        if ext.explicit_claims:
            entry["explicit_claims"] = ext.explicit_claims
        if ext.implicit_assumptions:
            entry["implicit_assumptions"] = ext.implicit_assumptions
        if ext.logical_steps:
            entry["logical_steps"] = ext.logical_steps
        if ext.defined_concepts:
            entry["defined_concepts"] = ext.defined_concepts
        if ext.emotional_tone:
            entry["emotional_tone"] = ext.emotional_tone
        if ext.tone_evidence:
            entry["tone_evidence"] = ext.tone_evidence
        if ext.internal_references:
            entry["internal_references"] = ext.internal_references
        ext_list.append(entry)
    data = {
        "completed_chapter_indices": completed_indices,
        "extractions": ext_list,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(',', ':')))


_MAX_CHECKPOINT_BYTES = 256 * 1024 * 1024  # 256 MiB hard cap


def _load_checkpoint(
    path: Path,
) -> tuple[list[int], list[ExtractionResult]] | None:
    """Load and structurally validate a checkpoint file.

    Returns (completed_indices, extractions) on success, or ``None`` if the
    file is missing, corrupt, oversized, or structurally invalid (which will
    cause the caller to start from scratch rather than trust bad data).
    """
    if not path.exists():
        return None

    # Guard against checkpoint files that have been inflated / tampered with
    file_size = path.stat().st_size
    if file_size > _MAX_CHECKPOINT_BYTES:
        logger.error(
            "Checkpoint file %s is suspiciously large (%d MiB > %d MiB limit). "
            "Refusing to load — starting fresh.",
            path, file_size // (1024 * 1024), _MAX_CHECKPOINT_BYTES // (1024 * 1024),
        )
        return None

    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)

        # Structural integrity checks
        if not isinstance(data, dict):
            raise ValueError("Checkpoint root must be a JSON object")

        completed = data.get("completed_chapter_indices", [])
        if not isinstance(completed, list) or not all(isinstance(i, int) for i in completed):
            raise ValueError("'completed_chapter_indices' must be a list of integers")

        raw_extractions = data.get("extractions", [])
        if not isinstance(raw_extractions, list):
            raise ValueError("'extractions' must be a list")

        extractions: list[ExtractionResult] = []
        for item in raw_extractions:
            if not isinstance(item, dict):
                raise ValueError(f"Extraction entry is not a dict: {type(item)}")
            pid = item.get("paragraph_id", "")
            if not isinstance(pid, str) or not pid:
                raise ValueError(f"Extraction entry has invalid paragraph_id: {pid!r}")

            depth_str = item.get("depth", "light")
            try:
                depth = DepthLevel(depth_str)
            except ValueError:
                depth = DepthLevel.LIGHT

            extractions.append(ExtractionResult(
                paragraph_id=pid,
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
                depth=depth,
            ))
        return completed, extractions

    except Exception as e:
        logger.error(
            "Checkpoint file %s is corrupt or invalid (%s). "
            "Starting extraction from scratch. The bad checkpoint will be "
            "overwritten once the first chapter completes.",
            path, e,
        )
        return None


def _truncate_json(data: dict[str, Any], max_chars: int = 8000) -> str:
    """Serialize *data* to compact JSON, truncating if it exceeds *max_chars*.

    This prevents the author-model prompt from blowing up when analysis
    stages produce very large outputs (e.g. hundreds of concepts).
    """
    raw = json.dumps(data, separators=(',', ':'))
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + '..."}'


def _build_author_model(
    client: LLMClient,
    book: Book,
    logical_map: dict[str, Any],
    concept_data: dict[str, Any],
    pattern_data: dict[str, Any],
) -> dict[str, Any]:
    """Build author model from all analysis results.

    Analysis data is truncated to keep total prompt within reasonable
    token bounds — the author model needs representative data, not every
    last occurrence entry.
    """
    user_prompt = AUTHOR_MODEL_USER.format(
        book_title=book.title,
        author=book.author,
        logical_map_json=_truncate_json(logical_map, 10000),
        concept_index_json=_truncate_json(concept_data, 8000),
        patterns_json=_truncate_json(pattern_data, 6000),
    )

    try:
        result = client.complete_json(AUTHOR_MODEL_SYSTEM, user_prompt)
        logger.info("Author model built successfully")
        return result
    except Exception as e:
        logger.error("Failed to build author model: %s", e)
        return {"error": str(e)}


def _extract_with_retry(
    client: LLMClient,
    chapter: Chapter,
    book_title: str,
    author: str,
    batch_size: int,
    progress: ProgressCallback | None,
    model_override: str | None = None,
    extra_skip: frozenset[str] | None = None,
    extraction_system: str | None = None,
    extraction_user_tpl: str | None = None,
) -> list[ExtractionResult]:
    """Extract a chapter with automatic retry for missing/failed paragraphs.

    First pass extracts all paragraphs. If any are missing or failed,
    a re-read pass re-extracts only the missing ones from raw text.

    If the chapter title matches a non-content section (Bibliography, Index,
    etc.) all paragraphs are marked SKIP without LLM calls. Otherwise,
    low-information paragraphs (boilerplate, page numbers, etc.) are skipped
    individually and assigned minimal placeholder results directly.

    Args:
        extra_skip: Additional lowercase chapter titles to skip, from the
            active domain template's ``skip_chapters`` list.
        extraction_system: Domain-specific system prompt for extraction stage.
        extraction_user_tpl: Domain-specific user template for extraction stage.
    """
    # Stop-word chapter detection: skip non-content sections entirely
    if _is_skip_chapter(chapter.title, extra_skip=extra_skip):
        logger.info(
            "Skipping non-content chapter %02d: %s", chapter.number, chapter.title
        )
        return [
            ExtractionResult(
                paragraph_id=p.paragraph_id,
                original_text=p.text,
                topic_sentence="[LOW INFORMATION]",
                function_in_argument="non-content",
                depth=DepthLevel.SKIP,
            )
            for p in chapter.paragraphs
        ]

    # ── Skip Logic: filter out low-information paragraphs before LLM call ──
    substantive: list = []
    skipped_results: list[ExtractionResult] = []
    for p in chapter.paragraphs:
        if _is_low_information(p.text):
            skipped_results.append(
                ExtractionResult(
                    paragraph_id=p.paragraph_id,
                    original_text=p.text,
                    topic_sentence="[LOW INFORMATION]",
                    function_in_argument="boilerplate",
                )
            )
        else:
            substantive.append(p)

    if not substantive:
        return skipped_results

    # Build a temporary chapter view with only substantive paragraphs
    substantive_chapter = Chapter(
        number=chapter.number,
        title=chapter.title,
        paragraphs=substantive,
    )

    results = extract_chapter(
        client=client,
        chapter=substantive_chapter,
        book_title=book_title,
        author=author,
        batch_size=batch_size,
        model_override=model_override,
        system_prompt=extraction_system,
        user_template=extraction_user_tpl,
    )

    # Check for missing or failed extractions (among substantive paragraphs only)
    is_complete, missing = validate_chapter_coverage(
        chapter.number,
        [p.paragraph_id for p in substantive],
        results,
    )

    if is_complete:
        return results + skipped_results

    if progress:
        progress(
            "re-read",
            f"Chapter {chapter.number:02d} incomplete. "
            f"Missing: {missing}. Re-reading raw text for re-extraction.",
        )

    # Remove failed results for the missing IDs so they get replaced
    missing_set = set(missing)
    results = [r for r in results if r.paragraph_id not in missing_set]

    # Build a sub-chapter with only the missing paragraphs
    missing_paras = [
        p for p in substantive if p.paragraph_id in missing_set
    ]
    if missing_paras:
        retry_chapter = Chapter(
            number=chapter.number,
            title=chapter.title,
            paragraphs=missing_paras,
        )
        retry_results = extract_chapter(
            client=client,
            chapter=retry_chapter,
            book_title=book_title,
            author=author,
            batch_size=batch_size,
            model_override=model_override,
            system_prompt=extraction_system,
            user_template=extraction_user_tpl,
        )
        results.extend(retry_results)

    return results + skipped_results


def ingest_book(
    book: Book,
    config: Config,
    domain: str = "philosophy",
    progress_callback: ProgressCallback | None = None,
    human_operator: str = "",
    resume: bool = False,
    tracker: ProgressTracker | None = None,
    vector_store: VectorStore | None = None,
    knowledge_graph: KnowledgeGraph | None = None,
    mode: str = "linear",
) -> Path:
    """Run the full ingestion pipeline for a book using the specified domain template.

    Pipeline stages (QUALITY_MAX mode):
    1. Load and validate domain template (prompts + skip_chapters)
    2. Structural extraction (per chapter, batched) with template prompts
       - Per-chapter coverage validation with automatic re-read retry
       - Checkpoint saved after each chapter (resumable on failure)
    3. Optional double-pass: re-extract entire book if config.double_pass is True
    4. Full coverage validation
    5. Secondary analysis (logical map / methodology / evidence) with template prompts
    6. Concept / entity indexing with template prompts
    7. Pattern / findings detection with template prompts
    8. Author model generation
    9. Write all output files (per-book + global vault files)
    10. Index into vector store (if available)
    11. Update knowledge graph (if available)

    Args:
        book: Parsed Book object.
        config: PPKE configuration.
        domain: Domain template name (e.g. 'philosophy', 'science', 'legal').
            Loaded from ``ppke/templates/official/`` or ``~/.ppke/plugins/``.
        progress_callback: Optional callable(stage_name, detail) for progress updates.
        human_operator: Name of the human operator for meta.yml versioning.
        resume: If True, resume from last checkpoint instead of starting fresh.
        tracker: Optional ProgressTracker for task/progress tracking.
        vector_store: Optional VectorStore for semantic search indexing.
        knowledge_graph: Optional KnowledgeGraph for graph-based reasoning.
        mode: Processing mode — ``"linear"`` (default) or ``"swarm"`` (multi-agent).

    Returns:
        Path to the book's output directory.
    """
    # ── Load domain template ──
    from ppke.templates.loader import load_template
    try:
        template = load_template(domain)
        logger.info("Loaded domain template: %s v%s", template.name, template.version)
    except Exception as _te:
        logger.warning(
            "Failed to load template '%s' (%s) — falling back to philosophy defaults", domain, _te
        )
        template = None

    # Build prompt lookup: stage_id -> {system, user_template}
    def _stage_prompts(stage_id: str) -> tuple[str | None, str | None]:
        """Return (system_prompt, user_template) for a given stage ID from the template."""
        if template is None:
            return None, None
        stage_def = next((s for s in template.stages if s.get("id") == stage_id), None)
        if stage_def is None:
            return None, None
        prompt_key = stage_def.get("prompt")
        if prompt_key is None:
            return None, None
        prompt_cfg = template.prompts.get(prompt_key, {})
        if not isinstance(prompt_cfg, dict):
            return None, None
        return prompt_cfg.get("system"), prompt_cfg.get("user_template")

    # Build extra skip set from template's skip_chapters list
    extra_skip: frozenset[str] | None = None
    if template is not None and template.skip_chapters:
        extra_skip = frozenset(s.strip().lower() for s in template.skip_chapters)

    client = LLMClient(config.llm)

    def _progress(stage: str, detail: str = ""):
        with _progress_lock:
            if progress_callback:
                progress_callback(stage, detail)
            logger.info("[%s] %s", stage, detail)

    # ── Progress tracker: register book ──
    if tracker is not None:
        tracker.register_book(
            book_folder=book.folder_name,
            title=book.title,
            author=book.author,
            total_chapters=len(book.chapters),
            total_paragraphs=book.total_paragraphs,
        )
        tracker.start_book(book.folder_name)

    # ── Stage 0: Split long paragraphs into sub-paragraphs ──
    split_count_before = book.total_paragraphs
    split_long_paragraphs(book, max_tokens=config.llm.max_paragraph_tokens)
    split_count_after = book.total_paragraphs
    if split_count_after > split_count_before:
        _progress(
            "split",
            f"Split long paragraphs: {split_count_before} -> {split_count_after} "
            f"({split_count_after - split_count_before} sub-paragraphs created)",
        )

    # ── Checkpoint: load existing progress if resuming ──
    cp_path = _checkpoint_path(config.vault_path, book.folder_name)
    completed_indices: list[int] = []
    all_extractions: list[ExtractionResult] = []

    if resume:
        checkpoint = _load_checkpoint(cp_path)
        if checkpoint is not None:
            completed_indices, all_extractions = checkpoint
            _progress(
                "resume",
                f"Resuming from checkpoint: {len(completed_indices)}/{len(book.chapters)} "
                f"chapters already completed ({len(all_extractions)} paragraphs)",
            )
        elif cp_path.exists():
            # File existed but _load_checkpoint returned None → it was corrupt.
            _progress("resume", f"WARNING: Checkpoint {cp_path.name} is corrupt — starting fresh")
        else:
            _progress("resume", "No checkpoint found, starting fresh")

    # ── Stage 1: Structural extraction (first pass) ──
    remaining_indices = [
        idx for idx in range(len(book.chapters))
        if idx not in set(completed_indices)
    ]
    max_workers = config.llm.max_workers
    _progress(
        "extraction",
        f"Pass 1: Processing {len(remaining_indices)}/{len(book.chapters)} chapters "
        f"(max {max_workers} parallel workers)",
    )

    if max_workers > 1 and len(remaining_indices) > 1:
        # Parallel extraction using thread pool
        chapter_results_map: dict[int, list[ExtractionResult]] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for idx in remaining_indices:
                chapter = book.chapters[idx]
                _progress(
                    "extraction",
                    f"Submitting Chapter {chapter.number:02d}: {chapter.title} "
                    f"({chapter.paragraph_count} paragraphs)",
                )
                _ext_sys, _ext_usr = _stage_prompts("extraction")
                future = executor.submit(
                    _extract_with_retry,
                    client=client,
                    chapter=chapter,
                    book_title=book.title,
                    author=book.author,
                    batch_size=config.llm.paragraphs_per_batch,
                    progress=_progress,
                    model_override=config.llm.effective_small_model,
                    extra_skip=extra_skip,
                    extraction_system=_ext_sys,
                    extraction_user_tpl=_ext_usr,
                )
                futures[future] = idx

            for future in as_completed(futures):
                idx = futures[future]
                ch = book.chapters[idx]
                try:
                    results = future.result()
                    # Guard shared state and checkpoint write under the progress lock
                    # to prevent concurrent futures from corrupting the lists or file.
                    with _progress_lock:
                        chapter_results_map[idx] = results
                        completed_indices.append(idx)
                        all_extractions.extend(results)
                        _save_checkpoint(cp_path, completed_indices, all_extractions)
                        if tracker is not None:
                            tracker.update_chapter(
                                book.folder_name,
                                ch.title,
                                len(completed_indices),
                                len(all_extractions),
                            )
                    _progress("extraction", f"Chapter {ch.number:02d} complete (checkpoint saved)")
                except Exception as e:
                    logger.error(
                        "Chapter %02d extraction failed: %s", ch.number, e
                    )
                    with _progress_lock:
                        chapter_results_map[idx] = []

        # Re-sort extractions to maintain chapter order
        ext_map: dict[str, ExtractionResult] = {e.paragraph_id: e for e in all_extractions}
        all_extractions = []
        for idx, chapter_item in enumerate(book.chapters):
            for p in chapter_item.paragraphs:
                if p.paragraph_id in ext_map:
                    all_extractions.append(ext_map[p.paragraph_id])
    else:
        # Sequential extraction (single worker or single chapter)
        for idx in remaining_indices:
            chapter = book.chapters[idx]
            _progress(
                "extraction",
                f"Chapter {chapter.number:02d}: {chapter.title} "
                f"({chapter.paragraph_count} paragraphs)",
            )
            _ext_sys, _ext_usr = _stage_prompts("extraction")
            chapter_results = _extract_with_retry(
                client=client,
                chapter=chapter,
                book_title=book.title,
                author=book.author,
                batch_size=config.llm.paragraphs_per_batch,
                progress=_progress,
                model_override=config.llm.effective_small_model,
                extra_skip=extra_skip,
                extraction_system=_ext_sys,
                extraction_user_tpl=_ext_usr,
            )
            all_extractions.extend(chapter_results)
            completed_indices.append(idx)
            _save_checkpoint(cp_path, completed_indices, all_extractions)
            if tracker is not None:
                tracker.update_chapter(
                    book.folder_name,
                    chapter.title,
                    len(completed_indices),
                    len(all_extractions),
                )
            _progress("checkpoint", f"Chapter {chapter.number:02d} checkpoint saved")

    # ── Stage 2: Double-pass (if enabled) ──
    if config.double_pass:
        _progress("double_pass", "Pass 2: Re-extracting all chapters for verification")
        pass2_extractions: list[ExtractionResult] = []

        for chapter in book.chapters:
            _progress(
                "double_pass",
                f"Pass 2 - Chapter {chapter.number:02d}: {chapter.title}",
            )
            _ext_sys, _ext_usr = _stage_prompts("extraction")
            chapter_results = extract_chapter(
                client=client,
                chapter=chapter,
                book_title=book.title,
                author=book.author,
                batch_size=config.llm.paragraphs_per_batch,
                model_override=config.llm.effective_small_model,
                system_prompt=_ext_sys,
                user_template=_ext_usr,
            )
            pass2_extractions.extend(chapter_results)

        # Merge: prefer pass 2 results where they are valid, keep pass 1 otherwise
        pass1_map = {r.paragraph_id: r for r in all_extractions}
        pass2_map = {r.paragraph_id: r for r in pass2_extractions}

        merged: list[ExtractionResult] = []
        for pid in book.all_paragraph_ids:
            p2 = pass2_map.get(pid)
            p1 = pass1_map.get(pid)
            if p2 and p2.topic_sentence != EXTRACTION_FAILED_MARKER:
                merged.append(p2)
            elif p1:
                merged.append(p1)
            else:
                logger.warning("Paragraph %s missing from both passes", pid)

        all_extractions = merged
        _progress("double_pass", "Double-pass merge complete")

    # ── Stage 3: Full coverage validation ──
    _progress("validation", "Running full coverage validation")
    coverage = validate_coverage(book, all_extractions)

    if config.double_pass:
        coverage.re_read_pass_completed = True

    if coverage.verification_status == "INCOMPLETE":
        missing_count = len(coverage.missing_paragraph_ids)
        _progress(
            "validation",
            f"ERROR: {missing_count} paragraphs missing: "
            f"{coverage.missing_paragraph_ids}",
        )
        raise RuntimeError(
            "Coverage validation failed "
            f"({coverage.processed_paragraph_count}/{coverage.total_paragraphs} processed). "
            "Ingestion aborted before writing final outputs. "
            "Fix provider/API settings and re-run with --resume."
        )
    _progress("validation", "COMPLETE: All paragraphs processed successfully")

    _progress(
        "validation",
        f"Status: {coverage.verification_status} "
        f"({coverage.processed_paragraph_count}/{coverage.total_paragraphs})",
    )

    # ── Stages 4/5/6: Secondary analysis, Concept/entity indexing, Pattern/findings detection ──
    # Resolve stage IDs from template: stage index 1 = logical/methodology,
    # index 2 = concepts/evidence, index 3 = patterns/findings.
    _stages = template.stages if template else []
    _s1_id = _stages[1]["id"] if len(_stages) > 1 else "logical_map"
    _s2_id = _stages[2]["id"] if len(_stages) > 2 else "concepts"
    _s3_id = _stages[3]["id"] if len(_stages) > 3 else "patterns"

    _s1_sys, _s1_usr = _stage_prompts(_s1_id)
    _s2_sys, _s2_usr = _stage_prompts(_s2_id)
    _s3_sys, _s3_usr = _stage_prompts(_s3_id)

    logical_map: dict[str, Any] = {}
    concept_data: dict[str, Any] = {}
    pattern_data: dict[str, Any] = {}
    swarm_results: dict[str, Any] | None = None

    if mode == "swarm":
        # ── Swarm mode: run multi-agent analysis ──
        _progress("analysis", f"Running swarm (multi-agent) analysis (domain: {domain})")
        from ppke.pipeline.swarm import SwarmOrchestrator
        swarm = SwarmOrchestrator(max_workers=config.llm.max_workers)
        swarm_results = swarm.run(
            client=client,
            extractions=all_extractions,
            book_title=book.title,
            book_author=book.author,
            progress_callback=progress_callback,
        )
        # Also run the standard analysis stages so output files are complete
        _progress(
            "analysis",
            f"Running [{_s1_id}, {_s2_id}, {_s3_id}] analysis stages in parallel "
            f"(domain: {domain})",
        )
    else:
        _progress(
            "analysis",
            f"Running [{_s1_id}, {_s2_id}, {_s3_id}] analysis stages in parallel "
            f"(domain: {domain})",
        )
    with ThreadPoolExecutor(max_workers=3) as analysis_executor:
        future_logical = analysis_executor.submit(
            build_logical_map, client, all_extractions, book.title, book.author,
            _s1_sys, _s1_usr,
        )
        future_concepts = analysis_executor.submit(
            build_concept_index, client, all_extractions, book.title, book.author,
            _s2_sys, _s2_usr,
        )
        future_patterns = analysis_executor.submit(
            detect_patterns, client, all_extractions, book.title, book.author,
            _s3_sys, _s3_usr,
        )

        try:
            logical_map = future_logical.result()
            _progress("logical_map", "Logical architecture complete")
        except Exception as e:
            logger.error("Logical map failed: %s", e)
            logical_map = {"error": str(e)}

        try:
            concept_data = future_concepts.result()
            _progress("concepts", "Concept index complete")
        except Exception as e:
            logger.error("Concept index failed: %s", e)
            concept_data = {"error": str(e)}

        try:
            pattern_data = future_patterns.result()
            _progress("patterns", "Pattern detection complete")
        except Exception as e:
            logger.error("Pattern detection failed: %s", e)
            pattern_data = {"error": str(e)}

    # ── Stage 7: Author model ──
    _progress("author_model", "Building author model")
    author_model = _build_author_model(
        client, book, logical_map, concept_data, pattern_data
    )

    # ── Stage 8: Write all files ──
    _progress("output", f"Writing files to {config.vault_path}")
    book_dir = write_all_book_files(
        vault_path=config.vault_path,
        book=book,
        extractions=all_extractions,
        logical_map=logical_map,
        concept_data=concept_data,
        author_model=author_model,
        coverage=coverage,
        human_operator=human_operator,
        pattern_data=pattern_data,
    )

    # Write swarm analysis results if applicable
    if swarm_results is not None:
        swarm_output_path = book_dir / "swarm_analysis.json"
        swarm_output_path.write_text(json.dumps(swarm_results, indent=2, default=str))
        _progress("output", f"Swarm analysis written to {swarm_output_path.name}")

    # Record processing mode in meta.yml
    meta_path = book_dir / "meta.yml"
    if meta_path.exists():
        try:
            meta = yaml.safe_load(meta_path.read_text()) or {}
            meta["processing_mode"] = mode
            if swarm_results and "_swarm_meta" in swarm_results:
                meta["swarm_meta"] = swarm_results["_swarm_meta"]
            meta_path.write_text(yaml.dump(meta, default_flow_style=False, sort_keys=False))
        except Exception as _e:
            logger.warning("Failed to update meta.yml with processing mode: %s", _e)

    # Write/update global vault files
    _progress("output", "Updating global vault files")
    write_global_files(config.vault_path, config)

    # ── Stage 9: Index into vector store (semantic search layer) ──
    if vector_store is not None and vector_store.available:
        _progress("vector_index", f"Indexing '{book.title}' into vector store")
        try:
            ext_path = book_dir / "extractions.json"
            ext_dicts: list[dict] = []
            if ext_path.exists():
                ext_dicts = json.loads(ext_path.read_text())
            indexed = vector_store.index_extractions(
                book_folder=book.folder_name,
                book_title=book.title,
                author=book.author,
                extractions=ext_dicts,
            )
            _progress("vector_index", f"Indexed {indexed} paragraphs into vector store")
        except Exception as _e:
            logger.warning("Vector store indexing failed (non-critical): %s", _e)

    # ── Stage 10: Update knowledge graph ──
    if knowledge_graph is not None:
        _progress("graph", f"Updating knowledge graph for '{book.title}'")
        try:
            ext_path = book_dir / "extractions.json"
            ext_dicts = []
            if ext_path.exists():
                ext_dicts = json.loads(ext_path.read_text())
            edges = knowledge_graph.add_book_extractions(
                book_folder=book.folder_name,
                book_title=book.title,
                author=book.author,
                extractions=ext_dicts,
            )
            knowledge_graph.save()
            _progress("graph", f"Knowledge graph updated ({edges} edges added)")
        except Exception as _e:
            logger.warning("Knowledge graph update failed (non-critical): %s", _e)

    # Clean up checkpoint file on success
    if cp_path.exists():
        cp_path.unlink()
        _progress("cleanup", "Checkpoint file removed (ingestion complete)")

    # ── Mark book complete in progress tracker ──
    if tracker is not None:
        tracker.complete_book(book.folder_name)

    # ── Log token usage summary ──
    try:
        usage = client.usage.summary()
        calls = int(usage.get("total_calls", 0))
        inp = int(usage.get("input_tokens", 0))
        out = int(usage.get("output_tokens", 0))
        total = int(usage.get("total_tokens", 0))
        cr = int(usage.get("cache_read_tokens", 0))
        cc = int(usage.get("cache_creation_tokens", 0))
        cache_info = (
            f" | Cache read: {cr:,} | Cache created: {cc:,}"
            if cr or cc else ""
        )
        _progress(
            "token_usage",
            f"Total API calls: {calls} | Input: {inp:,} | Output: {out:,} | "
            f"Total: {total:,} tokens{cache_info}",
        )
    except Exception as _ue:
        logger.debug("Could not log token usage summary: %s", _ue)

    _progress("complete", f"Book ingested: {book_dir}")
    return book_dir


def reread_chapters(
    book_dir: Path,
    chapter_numbers: list[int],
    config: Config,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    """Re-extract specific chapters from an already-ingested book.

    Reads the original source file, re-parses it, re-extracts only the
    requested chapters, merges with existing extractions, and rewrites
    all output files.

    Args:
        book_dir: Path to the book's folder in the vault.
        chapter_numbers: Chapter numbers to re-extract.
        config: PPKE configuration.
        progress_callback: Optional callable for progress updates.

    Returns:
        Path to the book directory.
    """
    import yaml

    from ppke.parser.markdown import parse_markdown_book

    def _progress(stage: str, detail: str = ""):
        if progress_callback:
            progress_callback(stage, detail)
        logger.info("[%s] %s", stage, detail)

    if not chapter_numbers:
        raise ValueError("chapter_numbers must not be empty")
    if any(n < 1 for n in chapter_numbers):
        raise ValueError(f"chapter_numbers must be positive integers, got {chapter_numbers}")

    # Load metadata
    meta_path = book_dir / "meta.yml"
    if not meta_path.exists():
        raise FileNotFoundError(f"No meta.yml found in {book_dir}")
    meta = yaml.safe_load(meta_path.read_text()) or {}

    source_path = meta.get("source_path")
    if not source_path:
        raise FileNotFoundError(
            "No source_path recorded in meta.yml. "
            "Re-read requires the original markdown file."
        )
    # Resolve to an absolute path and check the file exists.
    # We do NOT restrict to any specific directory because the source markdown
    # may legitimately live anywhere on the user's filesystem.  We do ensure
    # the resolved path is the same file (no symlink tricks pointing at /dev/*).
    source_resolved = Path(source_path).resolve()
    if not source_resolved.exists():
        raise FileNotFoundError(
            f"Source file not found: {source_path}. "
            "Re-read requires the original markdown file."
        )
    if not source_resolved.is_file():
        raise FileNotFoundError(
            f"Source path is not a regular file: {source_path}."
        )

    book_title = meta.get("title", "Unknown")
    author = meta.get("author", "Unknown")
    year = meta.get("year")

    _progress("re-read", f"Re-parsing source: {source_resolved}")
    book = parse_markdown_book(source_resolved, book_title, author, year)
    split_long_paragraphs(book, max_tokens=config.llm.max_paragraph_tokens)

    # Filter to requested chapters
    target_chapters = [
        ch for ch in book.chapters if ch.number in chapter_numbers
    ]
    if not target_chapters:
        _progress("re-read", f"No matching chapters found for: {chapter_numbers}")
        return book_dir

    _progress(
        "re-read",
        f"Re-extracting {len(target_chapters)} chapters: "
        f"{[ch.number for ch in target_chapters]}",
    )

    client = LLMClient(config.llm)

    # Load existing extractions from disk (no LLM calls for non-target chapters)
    _progress("re-read", "Loading existing extraction data from disk")
    saved_extractions = load_extractions_json(book_dir)
    saved_map = {ext.paragraph_id: ext for ext in saved_extractions}

    # Collect paragraph IDs from chapters being re-read
    reread_pids: set[str] = set()
    for ch in target_chapters:
        for p in ch.paragraphs:
            reread_pids.add(p.paragraph_id)

    # Re-extract only the target chapters via LLM
    new_extractions: list[ExtractionResult] = []
    for chapter in target_chapters:
        _progress(
            "re-read",
            f"Chapter {chapter.number:02d}: {chapter.title} "
            f"({chapter.paragraph_count} paragraphs)",
        )
        chapter_results = _extract_with_retry(
            client=client,
            chapter=chapter,
            book_title=book_title,
            author=author,
            batch_size=config.llm.paragraphs_per_batch,
            progress=_progress,
            model_override=config.llm.effective_small_model,
        )
        new_extractions.extend(chapter_results)

    # Merge: new results for re-read paragraphs, saved results for everything else
    new_map = {ext.paragraph_id: ext for ext in new_extractions}
    all_extractions: list[ExtractionResult] = []
    for pid in book.all_paragraph_ids:
        if pid in reread_pids:
            ext = new_map.get(pid)
        else:
            ext = saved_map.get(pid)
        if ext:
            all_extractions.append(ext)
        else:
            logger.warning(
                "Paragraph %s missing from both re-read results and saved data — "
                "it will be absent from final output. Run 'ppke re-read' again to recover.",
                pid,
            )

    from_disk_count = len(all_extractions) - len(new_extractions)
    _progress(
        "re-read",
        f"Merged: {len(new_extractions)} re-extracted + {from_disk_count} from disk",
    )

    # Re-run the analysis pipeline (parallel)
    _progress("re-read", "Re-running analysis pipeline")
    coverage = validate_coverage(book, all_extractions)
    coverage.re_read_pass_completed = True

    with ThreadPoolExecutor(max_workers=3) as analysis_executor:
        future_logical = analysis_executor.submit(
            build_logical_map, client, all_extractions, book_title, author
        )
        future_concepts = analysis_executor.submit(
            build_concept_index, client, all_extractions, book_title, author
        )
        future_patterns = analysis_executor.submit(
            detect_patterns, client, all_extractions, book_title, author
        )

        try:
            logical_map = future_logical.result()
        except Exception as e:
            logger.error("Logical map failed during re-read: %s", e)
            logical_map = {"error": str(e)}

        try:
            concept_data = future_concepts.result()
        except Exception as e:
            logger.error("Concept index failed during re-read: %s", e)
            concept_data = {"error": str(e)}

        try:
            pattern_data = future_patterns.result()
        except Exception as e:
            logger.error("Pattern detection failed during re-read: %s", e)
            pattern_data = {"error": str(e)}
    author_model = _build_author_model(
        client, book, logical_map, concept_data, pattern_data
    )

    _progress("re-read", "Writing updated files")
    write_all_book_files(
        vault_path=config.vault_path,
        book=book,
        extractions=all_extractions,
        logical_map=logical_map,
        concept_data=concept_data,
        author_model=author_model,
        coverage=coverage,
        human_operator=meta.get("human_operator", ""),
        pattern_data=pattern_data,
    )
    write_global_files(config.vault_path, config)

    _progress("re-read", f"Re-read complete for chapters {chapter_numbers}")
    return book_dir
