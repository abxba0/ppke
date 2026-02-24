"""Async Orchestrator for PPKE - asyncio-based pipeline for maximum throughput.

Refactors the extraction pipeline to use ``asyncio`` so that LLM calls, disk
I/O, and analysis stages run truly in parallel across chapters and books.

Design philosophy:
- The existing synchronous LLM clients and file writers run inside
  ``loop.run_in_executor`` so they benefit from async scheduling immediately,
  without requiring a full rewrite of every subsystem.
- Chapter extraction tasks are scheduled concurrently with asyncio.gather,
  bounded by a configurable semaphore (maps to ``config.llm.max_workers``).
- Analysis stages (logical map, concept index, pattern detection) run
  concurrently via asyncio.gather after extraction completes.
- Fully compatible with the existing Config, Book, and ExtractionResult types.
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

from ppke.config import Config
from ppke.llm.client import LLMClient
from ppke.llm.prompts import AUTHOR_MODEL_SYSTEM, AUTHOR_MODEL_USER
from ppke.output.writer import write_all_book_files, write_global_files
from ppke.parser.markdown import split_long_paragraphs
from ppke.parser.models import Book, Chapter, ExtractionResult
from ppke.pipeline.concepts import build_concept_index
from ppke.pipeline.extractor import extract_chapter
from ppke.pipeline.logical_map import build_logical_map
from ppke.pipeline.orchestrator import (
    _checkpoint_path,
    _extract_with_retry,
    _is_skip_chapter,
    _load_checkpoint,
    _save_checkpoint,
)
from ppke.pipeline.patterns import detect_patterns
from ppke.pipeline.validator import validate_coverage

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str], None]


# ── Internal helpers ──


async def _run_sync(executor: ThreadPoolExecutor, fn, *args):
    """Run a blocking function in the thread-pool executor, awaiting the result."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, fn, *args)


async def _extract_chapter_async(
    executor: ThreadPoolExecutor,
    semaphore: asyncio.Semaphore,
    client: LLMClient,
    chapter: Chapter,
    book_title: str,
    author: str,
    batch_size: int,
    model_override: Optional[str],
    progress: Optional[ProgressCallback],
    cp_path: Path,
    completed_indices: list[int],
    all_extractions: list[ExtractionResult],
    chapter_idx: int,
) -> list[ExtractionResult]:
    """Extract a single chapter asynchronously, bounded by the semaphore."""
    async with semaphore:
        if progress:
            progress(
                "extraction",
                f"Chapter {chapter.number:02d}: {chapter.title} "
                f"({chapter.paragraph_count} paragraphs)",
            )
        results: list[ExtractionResult] = await _run_sync(
            executor,
            _extract_with_retry,
            client,
            chapter,
            book_title,
            author,
            batch_size,
            progress,
            model_override,
        )
        # Update shared state under asyncio's cooperative multitasking (no lock needed)
        completed_indices.append(chapter_idx)
        all_extractions.extend(results)
        await _run_sync(executor, _save_checkpoint, cp_path, completed_indices, all_extractions)
        if progress:
            progress("extraction", f"Chapter {chapter.number:02d} complete (checkpoint saved)")
        return results


# ── Public API ──


async def ingest_book_async(
    book: Book,
    config: Config,
    domain: str = "philosophy",
    progress_callback: Optional[ProgressCallback] = None,
    human_operator: str = "",
    resume: bool = False,
) -> Path:
    """Async version of the full book ingestion pipeline.

    Pipeline stages:
    1. Load domain template (prompts + skip_chapters)
    2. Sub-paragraph splitting (sync, fast)
    3. Checkpoint load / resume
    4. Concurrent chapter extraction via asyncio.gather + semaphore
    5. Optional double-pass verification
    6. Coverage validation
    7. Concurrent analysis: stage-2/3/4 with template prompts
    8. Author model generation
    9. Write all output files

    Args:
        book: Parsed Book object.
        config: PPKE configuration (max_workers controls concurrency level).
        domain: Domain template name to use for prompts and skip_chapters.
        progress_callback: Optional callable(stage, detail) for progress updates.
        human_operator: Name for meta.yml versioning.
        resume: If True, resume from existing checkpoint.

    Returns:
        Path to the book's output directory in the vault.
    """
    # ── Load domain template ──
    from ppke.templates.loader import load_template
    try:
        template = load_template(domain)
        logger.info("Loaded domain template: %s v%s", template.name, template.version)
    except Exception as _te:
        logger.warning(
            "Failed to load template '%s' (%s) — falling back to defaults", domain, _te
        )
        template = None

    def _stage_prompts(stage_id: str) -> tuple[Optional[str], Optional[str]]:
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

    extra_skip: Optional[frozenset] = None
    if template is not None and template.skip_chapters:
        extra_skip = frozenset(s.strip().lower() for s in template.skip_chapters)

    _stages = template.stages if template else []
    _s1_id = _stages[1]["id"] if len(_stages) > 1 else "logical_map"
    _s2_id = _stages[2]["id"] if len(_stages) > 2 else "concepts"
    _s3_id = _stages[3]["id"] if len(_stages) > 3 else "patterns"
    _s1_sys, _s1_usr = _stage_prompts(_s1_id)
    _s2_sys, _s2_usr = _stage_prompts(_s2_id)
    _s3_sys, _s3_usr = _stage_prompts(_s3_id)

    def _progress(stage: str, detail: str = "") -> None:
        if progress_callback:
            progress_callback(stage, detail)
        logger.info("[%s] %s", stage, detail)

    # ── Stage 0: Sub-paragraph splitting (sync) ──
    split_before = book.total_paragraphs
    split_long_paragraphs(book, max_tokens=config.llm.max_paragraph_tokens)
    split_after = book.total_paragraphs
    if split_after > split_before:
        _progress(
            "split",
            f"Split long paragraphs: {split_before} -> {split_after} "
            f"({split_after - split_before} sub-paragraphs created)",
        )

    # ── Checkpoint ──
    cp_path = _checkpoint_path(config.vault_path, book.folder_name)
    completed_indices: list[int] = []
    all_extractions: list[ExtractionResult] = []

    if resume:
        checkpoint = _load_checkpoint(cp_path)
        if checkpoint is not None:
            completed_indices, all_extractions = checkpoint
            _progress(
                "resume",
                f"Resuming: {len(completed_indices)}/{len(book.chapters)} chapters done "
                f"({len(all_extractions)} paragraphs)",
            )
        else:
            _progress("resume", "No valid checkpoint found, starting fresh")

    # ── Stage 1: Concurrent chapter extraction ──
    remaining = [
        (idx, book.chapters[idx])
        for idx in range(len(book.chapters))
        if idx not in set(completed_indices)
    ]
    max_workers = max(1, config.llm.max_workers)
    semaphore = asyncio.Semaphore(max_workers)
    client = LLMClient(config.llm)

    _progress(
        "extraction",
        f"Async extraction: {len(remaining)}/{len(book.chapters)} chapters "
        f"({max_workers} concurrent workers)",
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        extraction_tasks = [
            _extract_chapter_async(
                executor=executor,
                semaphore=semaphore,
                client=client,
                chapter=chapter,
                book_title=book.title,
                author=book.author,
                batch_size=config.llm.paragraphs_per_batch,
                model_override=config.llm.effective_small_model,
                progress=_progress,
                cp_path=cp_path,
                completed_indices=completed_indices,
                all_extractions=all_extractions,
                chapter_idx=idx,
            )
            for idx, chapter in remaining
        ]

        if extraction_tasks:
            await asyncio.gather(*extraction_tasks, return_exceptions=True)

    # Re-order extractions to match book chapter order
    ext_map: dict[str, ExtractionResult] = {e.paragraph_id: e for e in all_extractions}
    all_extractions = []
    for chapter in book.chapters:
        for p in chapter.paragraphs:
            if p.paragraph_id in ext_map:
                all_extractions.append(ext_map[p.paragraph_id])

    # ── Stage 2: Double-pass (if enabled) ──
    if config.double_pass:
        _progress("double_pass", "Pass 2: Re-extracting all chapters for verification")
        pass2_extractions: list[ExtractionResult] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:

            async def _double_pass_chapter(chapter: Chapter) -> list[ExtractionResult]:
                async with semaphore:
                    _progress("double_pass", f"Pass 2 — Chapter {chapter.number:02d}")
                    return await _run_sync(
                        executor,
                        extract_chapter,
                        client,
                        chapter,
                        book.title,
                        book.author,
                        config.llm.paragraphs_per_batch,
                        config.llm.effective_small_model,
                    )

            dp_results = await asyncio.gather(
                *[_double_pass_chapter(ch) for ch in book.chapters],
                return_exceptions=True,
            )

        for result in dp_results:
            if isinstance(result, list):
                pass2_extractions.extend(result)

        from ppke.pipeline.validator import EXTRACTION_FAILED_MARKER

        p1_map = {r.paragraph_id: r for r in all_extractions}
        p2_map = {r.paragraph_id: r for r in pass2_extractions}
        merged: list[ExtractionResult] = []
        for pid in book.all_paragraph_ids:
            p2 = p2_map.get(pid)
            p1 = p1_map.get(pid)
            if p2 and p2.topic_sentence != EXTRACTION_FAILED_MARKER:
                merged.append(p2)
            elif p1:
                merged.append(p1)
            else:
                logger.warning("Paragraph %s missing from both passes", pid)
        all_extractions = merged
        _progress("double_pass", "Double-pass merge complete")

    # ── Stage 3: Coverage validation ──
    _progress("validation", "Running coverage validation")
    coverage = validate_coverage(book, all_extractions)
    if config.double_pass:
        coverage.re_read_pass_completed = True

    if coverage.verification_status == "INCOMPLETE":
        missing_count = len(coverage.missing_paragraph_ids)
        _progress("validation", f"ERROR: {missing_count} paragraphs missing")
        raise RuntimeError(
            f"Coverage validation failed "
            f"({coverage.processed_paragraph_count}/{coverage.total_paragraphs} processed). "
            "Re-run with --resume."
        )
    _progress(
        "validation",
        f"COMPLETE: {coverage.processed_paragraph_count}/{coverage.total_paragraphs}",
    )

    # ── Stages 4/5/6: Concurrent analysis with template prompts ──
    _progress(
        "analysis",
        f"Running [{_s1_id}, {_s2_id}, {_s3_id}] stages concurrently (domain: {domain})",
    )

    logical_map: dict[str, Any] = {}
    concept_data: dict[str, Any] = {}
    pattern_data: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=3) as analysis_executor:

        async def _logical() -> dict:
            return await _run_sync(
                analysis_executor, build_logical_map, client, all_extractions,
                book.title, book.author, _s1_sys, _s1_usr,
            )

        async def _concepts() -> dict:
            return await _run_sync(
                analysis_executor, build_concept_index, client, all_extractions,
                book.title, book.author, _s2_sys, _s2_usr,
            )

        async def _patterns() -> dict:
            return await _run_sync(
                analysis_executor, detect_patterns, client, all_extractions,
                book.title, book.author, _s3_sys, _s3_usr,
            )

        lm_result, co_result, pa_result = await asyncio.gather(
            _logical(), _concepts(), _patterns(), return_exceptions=True
        )

    logical_map = lm_result if isinstance(lm_result, dict) else {"error": str(lm_result)}
    concept_data = co_result if isinstance(co_result, dict) else {"error": str(co_result)}
    pattern_data = pa_result if isinstance(pa_result, dict) else {"error": str(pa_result)}

    _progress("analysis", "Analysis stages complete")

    # ── Stage 7: Author model ──
    _progress("author_model", "Building author model")
    user_prompt = AUTHOR_MODEL_USER.format(
        book_title=book.title,
        author=book.author,
        logical_map_json=json.dumps(logical_map, separators=(",", ":")),
        concept_index_json=json.dumps(concept_data, separators=(",", ":")),
        patterns_json=json.dumps(pattern_data, separators=(",", ":")),
    )
    try:
        author_model: dict[str, Any] = client.complete_json(AUTHOR_MODEL_SYSTEM, user_prompt)
    except Exception as e:
        logger.error("Author model failed: %s", e)
        author_model = {"error": str(e)}

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
    write_global_files(config.vault_path, config)

    # Clean up checkpoint
    if cp_path.exists():
        cp_path.unlink()
        _progress("cleanup", "Checkpoint removed")

    _progress("complete", f"Book ingested: {book_dir}")
    return book_dir


def run_ingest_async(
    book: Book,
    config: Config,
    progress_callback: Optional[ProgressCallback] = None,
    human_operator: str = "",
    resume: bool = False,
) -> Path:
    """Synchronous entry point that runs the async pipeline via asyncio.run().

    Use this when you are in a synchronous context (e.g. CLI command handler)
    and want to benefit from the async pipeline without managing the event loop
    yourself.
    """
    return asyncio.run(
        ingest_book_async(
            book=book,
            config=config,
            progress_callback=progress_callback,
            human_operator=human_operator,
            resume=resume,
        )
    )
