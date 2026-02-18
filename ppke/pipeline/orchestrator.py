"""Master Controller - orchestrates the full book ingestion pipeline."""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from ppke.config import Config
from ppke.llm.client import LLMClient
from ppke.llm.prompts import AUTHOR_MODEL_SYSTEM, AUTHOR_MODEL_USER
from ppke.output.writer import load_extractions_json, write_all_book_files, write_global_files
from ppke.parser.markdown import split_long_paragraphs
from ppke.parser.models import Book, Chapter, CoverageReport, ExtractionResult
from ppke.pipeline.concepts import build_concept_index
from ppke.pipeline.extractor import extract_chapter
from ppke.pipeline.logical_map import build_logical_map
from ppke.pipeline.patterns import detect_patterns
from ppke.pipeline.validator import (
    EXTRACTION_FAILED_MARKER,
    validate_chapter_coverage,
    validate_coverage,
)

logger = logging.getLogger(__name__)

_progress_lock = threading.Lock()

ProgressCallback = Callable[[str, str], None]


# ── Checkpoint support ──


def _checkpoint_path(vault_path: Path, book_folder: str) -> Path:
    """Return path for the in-progress checkpoint file."""
    return vault_path / f".checkpoint_{book_folder}.json"


def _save_checkpoint(
    path: Path,
    completed_indices: list[int],
    extractions: list[ExtractionResult],
) -> None:
    """Save extraction checkpoint after each chapter completes."""
    data = {
        "completed_chapter_indices": completed_indices,
        "extractions": [
            {
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
                "is_argument_carrying": ext.depth.value == "full",
                "depth": ext.depth.value,
            }
            for ext in extractions
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(',', ':')))


def _load_checkpoint(
    path: Path,
) -> tuple[list[int], list[ExtractionResult]] | None:
    """Load checkpoint if it exists. Returns (completed_indices, extractions) or None."""
    if not path.exists():
        return None
    try:
        from ppke.parser.models import DepthLevel

        data = json.loads(path.read_text())
        completed = data.get("completed_chapter_indices", [])
        extractions = []
        for item in data.get("extractions", []):
            depth_str = item.get("depth", "LIGHT")
            try:
                depth = DepthLevel(depth_str)
            except ValueError:
                depth = DepthLevel.LIGHT
            extractions.append(ExtractionResult(
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
                depth=depth,
            ))
        return completed, extractions
    except Exception as e:
        logger.error(
            "Checkpoint file %s is corrupt or unreadable (%s). "
            "Starting extraction from scratch. The corrupted checkpoint will be "
            "overwritten once the first chapter completes.",
            path, e,
        )
        return None


def _build_author_model(
    client: LLMClient,
    book: Book,
    logical_map: dict[str, Any],
    concept_data: dict[str, Any],
    pattern_data: dict[str, Any],
) -> dict[str, Any]:
    """Build author model from all analysis results."""
    user_prompt = AUTHOR_MODEL_USER.format(
        book_title=book.title,
        author=book.author,
        logical_map_json=json.dumps(logical_map, separators=(',', ':')),
        concept_index_json=json.dumps(concept_data, separators=(',', ':')),
        patterns_json=json.dumps(pattern_data, separators=(',', ':')),
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
) -> list[ExtractionResult]:
    """Extract a chapter with automatic retry for missing/failed paragraphs.

    First pass extracts all paragraphs. If any are missing or failed,
    a re-read pass re-extracts only the missing ones from raw text.
    """
    results = extract_chapter(
        client=client,
        chapter=chapter,
        book_title=book_title,
        author=author,
        batch_size=batch_size,
    )

    # Check for missing or failed extractions
    is_complete, missing = validate_chapter_coverage(
        chapter.number,
        [p.paragraph_id for p in chapter.paragraphs],
        results,
    )

    if is_complete:
        return results

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
        p for p in chapter.paragraphs if p.paragraph_id in missing_set
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
        )
        results.extend(retry_results)

    return results


def ingest_book(
    book: Book,
    config: Config,
    progress_callback: ProgressCallback | None = None,
    human_operator: str = "",
    resume: bool = False,
) -> Path:
    """Run the full ingestion pipeline for a book.

    Pipeline stages (QUALITY_MAX mode):
    1. Structural extraction (per chapter, batched)
       - Per-chapter coverage validation with automatic re-read retry
       - Checkpoint saved after each chapter (resumable on failure)
    2. Optional double-pass: re-extract entire book if config.double_pass is True
    3. Full coverage validation
    4. Logical architecture building
    5. Concept indexing
    6. Pattern detection
    7. Author model generation
    8. Write all output files (per-book + global vault files)

    Args:
        book: Parsed Book object.
        config: PPKE configuration.
        progress_callback: Optional callable(stage_name, detail) for progress updates.
        human_operator: Name of the human operator for meta.yml versioning.
        resume: If True, resume from last checkpoint instead of starting fresh.

    Returns:
        Path to the book's output directory.
    """
    client = LLMClient(config.llm)

    def _progress(stage: str, detail: str = ""):
        with _progress_lock:
            if progress_callback:
                progress_callback(stage, detail)
            logger.info("[%s] %s", stage, detail)

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
                future = executor.submit(
                    _extract_with_retry,
                    client=client,
                    chapter=chapter,
                    book_title=book.title,
                    author=book.author,
                    batch_size=config.llm.paragraphs_per_batch,
                    progress=_progress,
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
        for idx in range(len(book.chapters)):
            for p in book.chapters[idx].paragraphs:
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
            chapter_results = _extract_with_retry(
                client=client,
                chapter=chapter,
                book_title=book.title,
                author=book.author,
                batch_size=config.llm.paragraphs_per_batch,
                progress=_progress,
            )
            all_extractions.extend(chapter_results)
            completed_indices.append(idx)
            _save_checkpoint(cp_path, completed_indices, all_extractions)
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
            chapter_results = extract_chapter(
                client=client,
                chapter=chapter,
                book_title=book.title,
                author=book.author,
                batch_size=config.llm.paragraphs_per_batch,
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

    if coverage.verification_status == "INCOMPLETE":
        _progress(
            "validation",
            f"WARNING: {len(coverage.missing_paragraph_ids)} paragraphs missing: "
            f"{coverage.missing_paragraph_ids}",
        )
    else:
        _progress("validation", "COMPLETE: All paragraphs processed successfully")

    _progress(
        "validation",
        f"Status: {coverage.verification_status} "
        f"({coverage.processed_paragraph_count}/{coverage.total_paragraphs})",
    )

    if config.double_pass:
        coverage.re_read_pass_completed = True

    # ── Stage 4: Logical architecture ──
    _progress("logical_map", "Building logical architecture")
    logical_map = build_logical_map(client, all_extractions, book.title, book.author)

    # ── Stage 5: Concept indexing ──
    _progress("concepts", "Building concept index")
    concept_data = build_concept_index(
        client, all_extractions, book.title, book.author
    )

    # ── Stage 6: Pattern detection ──
    _progress("patterns", "Detecting patterns and tensions")
    pattern_data = detect_patterns(client, all_extractions, book.title, book.author)

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

    # Write/update global vault files
    _progress("output", "Updating global vault files")
    write_global_files(config.vault_path, config)

    # Clean up checkpoint file on success
    if cp_path.exists():
        cp_path.unlink()
        _progress("cleanup", "Checkpoint file removed (ingestion complete)")

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

    # Load metadata
    meta_path = book_dir / "meta.yml"
    if not meta_path.exists():
        raise FileNotFoundError(f"No meta.yml found in {book_dir}")
    meta = yaml.safe_load(meta_path.read_text()) or {}

    source_path = meta.get("source_path")
    if not source_path or not Path(source_path).exists():
        raise FileNotFoundError(
            f"Source file not found: {source_path}. "
            "Re-read requires the original markdown file."
        )

    book_title = meta.get("title", "Unknown")
    author = meta.get("author", "Unknown")
    year = meta.get("year")

    _progress("re-read", f"Re-parsing source: {source_path}")
    book = parse_markdown_book(source_path, book_title, author, year)
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

    # Re-run the analysis pipeline
    _progress("re-read", "Re-running analysis pipeline")
    coverage = validate_coverage(book, all_extractions)
    coverage.re_read_pass_completed = True

    logical_map = build_logical_map(client, all_extractions, book_title, author)
    concept_data = build_concept_index(client, all_extractions, book_title, author)
    pattern_data = detect_patterns(client, all_extractions, book_title, author)
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
