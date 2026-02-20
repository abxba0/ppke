"""Tests for the pipeline orchestrator - covering ingest_book, reread_chapters,
_build_author_model, and _extract_with_retry.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import yaml

from click.testing import CliRunner

from ppke.cli import main
from ppke.config import Config, LLMConfig
from ppke.parser.models import (
    Book,
    Chapter,
    CoverageReport,
    DepthLevel,
    ExtractionResult,
    Paragraph,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_book(n_chapters=1, n_para_each=2) -> Book:
    book = Book(title="Test Book", author="Author", year="2024")
    for ci in range(1, n_chapters + 1):
        ch = Chapter(number=ci, title=f"Chapter {ci}")
        ch.paragraphs = [
            Paragraph(chapter_number=ci, paragraph_number=pi, text=f"Ch{ci} Para {pi}")
            for pi in range(1, n_para_each + 1)
        ]
        book.chapters.append(ch)
    return book


def _make_extraction(pid, text="text") -> ExtractionResult:
    return ExtractionResult(
        paragraph_id=pid,
        original_text=text,
        topic_sentence="topic",
        depth=DepthLevel.FULL,
    )


def _make_extractions_for_book(book: Book) -> list[ExtractionResult]:
    return [
        _make_extraction(p.paragraph_id, p.text)
        for ch in book.chapters
        for p in ch.paragraphs
    ]


# ── _build_author_model ───────────────────────────────────────────────────────


def test_build_author_model_success():
    from ppke.pipeline.orchestrator import _build_author_model

    book = _make_book()
    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "ontology": {"description": "Realist", "evidence": []},
        "epistemology": {"description": "Empiricist", "evidence": []},
    }

    result = _build_author_model(
        mock_client, book,
        logical_map={"central_thesis": {}},
        concept_data={"concepts": []},
        pattern_data={"patterns": []},
    )
    assert result["ontology"]["description"] == "Realist"


def test_build_author_model_failure():
    from ppke.pipeline.orchestrator import _build_author_model

    book = _make_book()
    mock_client = MagicMock()
    mock_client.complete_json.side_effect = ValueError("LLM error")

    result = _build_author_model(
        mock_client, book,
        logical_map={}, concept_data={}, pattern_data={},
    )
    assert "error" in result


# ── _extract_with_retry ───────────────────────────────────────────────────────


def test_extract_with_retry_complete_on_first_pass():
    from ppke.pipeline.orchestrator import _extract_with_retry

    ch = Chapter(number=1, title="Intro")
    ch.paragraphs = [Paragraph(chapter_number=1, paragraph_number=1, text="This is substantive text.")]

    mock_client = MagicMock()
    with patch("ppke.pipeline.orchestrator.extract_chapter") as mock_extract, \
         patch("ppke.pipeline.orchestrator.validate_chapter_coverage") as mock_validate:

        mock_extract.return_value = [_make_extraction("{01}.p1")]
        mock_validate.return_value = (True, [])

        results = _extract_with_retry(
            client=mock_client, chapter=ch,
            book_title="Book", author="Author",
            batch_size=5, progress=None,
        )

    assert len(results) == 1
    mock_extract.assert_called_once()


def test_extract_with_retry_incomplete_triggers_reread():
    from ppke.pipeline.orchestrator import _extract_with_retry

    ch = Chapter(number=1, title="Intro")
    ch.paragraphs = [
        Paragraph(chapter_number=1, paragraph_number=1, text="Text 1"),
        Paragraph(chapter_number=1, paragraph_number=2, text="Text 2"),
    ]

    mock_client = MagicMock()
    progress_calls = []

    def progress(stage, detail):
        progress_calls.append((stage, detail))

    first_pass = [_make_extraction("{01}.p1")]
    retry_pass = [_make_extraction("{01}.p2")]

    with patch("ppke.pipeline.orchestrator.extract_chapter") as mock_extract, \
         patch("ppke.pipeline.orchestrator.validate_chapter_coverage") as mock_validate:

        mock_extract.side_effect = [first_pass, retry_pass]
        mock_validate.return_value = (False, ["{01}.p2"])

        results = _extract_with_retry(
            client=mock_client, chapter=ch,
            book_title="Book", author="Author",
            batch_size=5, progress=progress,
        )

    assert len(results) == 2
    assert mock_extract.call_count == 2
    assert any("re-read" in s for s, _ in progress_calls)


def test_extract_with_retry_with_progress_callback():
    from ppke.pipeline.orchestrator import _extract_with_retry

    ch = Chapter(number=1, title="Intro")
    ch.paragraphs = [Paragraph(chapter_number=1, paragraph_number=1, text="Substantive paragraph text here.")]

    mock_client = MagicMock()
    progress_log = []

    with patch("ppke.pipeline.orchestrator.extract_chapter") as mock_extract, \
         patch("ppke.pipeline.orchestrator.validate_chapter_coverage") as mock_validate:
        mock_extract.return_value = [_make_extraction("{01}.p1")]
        mock_validate.return_value = (True, [])

        _extract_with_retry(
            client=mock_client, chapter=ch,
            book_title="Book", author="Author",
            batch_size=5, progress=lambda s, d: progress_log.append(s),
        )

    # No re-read progress emitted when complete
    assert "re-read" not in progress_log


# ── ingest_book (full pipeline, mocked LLM) ───────────────────────────────────


def _mock_complete_json(results_by_call: list):
    """Returns side_effect values in order."""
    calls = iter(results_by_call)

    def side_effect(system, user):
        return next(calls)

    return side_effect


def test_ingest_book_sequential(tmp_path):
    """Test ingest_book with a 1-chapter book (sequential path)."""
    from ppke.pipeline.orchestrator import ingest_book

    book = _make_book(n_chapters=1, n_para_each=1)
    extractions = _make_extractions_for_book(book)

    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key", max_workers=1),
    )

    progress_log = []

    with patch("ppke.pipeline.orchestrator.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.side_effect = [
            # Extraction: list of para extractions
            [{"paragraph_id": "{01}.p1", "topic_sentence": "T", "is_argument_carrying": True}],
            # Logical map
            {"central_thesis": {"claim": "Main", "paragraph_ids": []}, "argument_threads": []},
            # Concept index
            {"concepts": []},
            # Pattern detection
            {"patterns": []},
            # Author model
            {"ontology": {"description": "D"}},
        ]

        book_dir = ingest_book(
            book, cfg,
            progress_callback=lambda s, d: progress_log.append(s),
        )

    assert book_dir.exists()
    assert (book_dir / "meta.yml").exists()
    assert (book_dir / "01_Raw_Structure.md").exists()


def test_ingest_book_aborts_on_incomplete_coverage(tmp_path):
    """Ingestion must fail-fast when coverage is INCOMPLETE."""
    from ppke.pipeline.orchestrator import ingest_book

    book = _make_book(n_chapters=1, n_para_each=1)
    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key", max_workers=1),
    )

    incomplete = CoverageReport(
        total_chapters=1,
        total_paragraphs=1,
        processed_paragraph_count=0,
        missing_paragraph_ids=["{01}.p1"],
        verification_status="INCOMPLETE",
        ingest_date="2026-02-19",
    )

    with patch("ppke.pipeline.orchestrator.LLMClient") as MockClient, \
         patch("ppke.pipeline.orchestrator.validate_coverage", return_value=incomplete), \
         patch("ppke.pipeline.orchestrator.write_all_book_files") as mock_write:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.return_value = [
            {"paragraph_id": "{01}.p1", "topic_sentence": "T", "is_argument_carrying": True}
        ]

        with pytest.raises(RuntimeError, match="Coverage validation failed"):
            ingest_book(book, cfg)

    mock_write.assert_not_called()


def test_ingest_cli_returns_click_error_on_pipeline_failure(tmp_path):
    """CLI should report ingestion failures as clean Click errors."""
    runner = CliRunner()
    src = tmp_path / "book.md"
    src.write_text("# Chapter 1\n\nSample paragraph.")

    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key"),
    )

    mock_book = _make_book(n_chapters=1, n_para_each=1)

    with patch("ppke.config.Config.load", return_value=cfg), \
         patch("ppke.parser.markdown.parse_markdown_book", return_value=mock_book), \
         patch("ppke.pipeline.orchestrator.ingest_book", side_effect=RuntimeError("Coverage validation failed")):
        result = runner.invoke(
            main,
            ["ingest", str(src), "--title", "T", "--author", "A"],
        )

    assert result.exit_code != 0
    assert "Error: Ingestion failed: Coverage validation failed" in result.output


def test_ingest_book_with_resume_and_checkpoint(tmp_path):
    """Test ingest_book with --resume flag loading an existing checkpoint."""
    from ppke.pipeline.orchestrator import ingest_book, _save_checkpoint, _checkpoint_path

    book = _make_book(n_chapters=1, n_para_each=1)
    extractions = _make_extractions_for_book(book)

    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key", max_workers=1),
    )

    # Save a checkpoint showing chapter 0 already done
    cp_path = _checkpoint_path(tmp_path, book.folder_name)
    _save_checkpoint(cp_path, [0], extractions)

    with patch("ppke.pipeline.orchestrator.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.side_effect = [
            # logical map (extraction is skipped, loaded from checkpoint)
            {"central_thesis": {"claim": "Main", "paragraph_ids": []}, "argument_threads": []},
            # concept index
            {"concepts": []},
            # pattern detection
            {"patterns": []},
            # author model
            {"ontology": {"description": "D"}},
        ]

        book_dir = ingest_book(book, cfg, resume=True)

    assert book_dir.exists()
    # Checkpoint should be deleted on success
    assert not cp_path.exists()


def test_ingest_book_cleans_up_checkpoint_on_success(tmp_path):
    """Checkpoint file should be removed after successful ingestion."""
    from ppke.pipeline.orchestrator import ingest_book, _checkpoint_path

    book = _make_book(n_chapters=1, n_para_each=1)
    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key", max_workers=1),
    )

    with patch("ppke.pipeline.orchestrator.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.side_effect = [
            [{"paragraph_id": "{01}.p1", "topic_sentence": "T"}],
            {"central_thesis": {}, "argument_threads": []},
            {"concepts": []},
            {"patterns": []},
            {"ontology": {}},
        ]
        ingest_book(book, cfg)

    cp_path = _checkpoint_path(tmp_path, book.folder_name)
    assert not cp_path.exists()


def test_ingest_book_with_double_pass(tmp_path):
    """Test ingest_book with double_pass enabled."""
    from ppke.pipeline.orchestrator import ingest_book

    book = _make_book(n_chapters=1, n_para_each=1)
    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key", max_workers=1),
        double_pass=True,
    )

    with patch("ppke.pipeline.orchestrator.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.side_effect = [
            # Pass 1 extraction
            [{"paragraph_id": "{01}.p1", "topic_sentence": "T", "is_argument_carrying": True}],
            # Pass 2 extraction
            [{"paragraph_id": "{01}.p1", "topic_sentence": "T2", "is_argument_carrying": True}],
            # logical map
            {"central_thesis": {}, "argument_threads": []},
            # concepts
            {"concepts": []},
            # patterns
            {"patterns": []},
            # author model
            {},
        ]

        book_dir = ingest_book(book, cfg)

    assert book_dir.exists()
    coverage_report = (book_dir / "05_Coverage_Report.md").read_text()
    assert "yes" in coverage_report  # re_read_pass_completed


def test_ingest_book_parallel(tmp_path):
    """Test ingest_book with 2 chapters and max_workers=2 (parallel path)."""
    from ppke.pipeline.orchestrator import ingest_book

    book = _make_book(n_chapters=2, n_para_each=1)
    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key", max_workers=2),
    )

    with patch("ppke.pipeline.orchestrator._extract_with_retry") as mock_retry, \
         patch("ppke.pipeline.orchestrator.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        # Return extraction results for each chapter
        mock_retry.side_effect = [
            [_make_extraction("{01}.p1")],
            [_make_extraction("{02}.p1")],
        ]

        mock_client.complete_json.side_effect = [
            {"central_thesis": {}, "argument_threads": []},
            {"concepts": []},
            {"patterns": []},
            {},
        ]

        book_dir = ingest_book(book, cfg)

    assert book_dir.exists()


def test_ingest_book_resume_with_corrupt_checkpoint(tmp_path):
    """Corrupt checkpoint during resume should start fresh."""
    from ppke.pipeline.orchestrator import ingest_book, _checkpoint_path

    book = _make_book(n_chapters=1, n_para_each=1)
    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key", max_workers=1),
    )

    # Write corrupt checkpoint
    cp_path = _checkpoint_path(tmp_path, book.folder_name)
    cp_path.write_text("not valid json{{{")

    with patch("ppke.pipeline.orchestrator.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.side_effect = [
            [{"paragraph_id": "{01}.p1", "topic_sentence": "T"}],
            {"central_thesis": {}, "argument_threads": []},
            {"concepts": []},
            {"patterns": []},
            {},
        ]
        book_dir = ingest_book(book, cfg, resume=True)

    assert book_dir.exists()


def test_ingest_book_resume_no_checkpoint(tmp_path):
    """Resume with no checkpoint should behave like a normal run."""
    from ppke.pipeline.orchestrator import ingest_book

    book = _make_book(n_chapters=1, n_para_each=1)
    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key", max_workers=1),
    )

    with patch("ppke.pipeline.orchestrator.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.side_effect = [
            [{"paragraph_id": "{01}.p1", "topic_sentence": "T"}],
            {"central_thesis": {}, "argument_threads": []},
            {"concepts": []},
            {"patterns": []},
            {},
        ]
        book_dir = ingest_book(book, cfg, resume=True)

    assert book_dir.exists()


def test_ingest_book_with_progress_callback(tmp_path):
    """Progress callback should be called during ingestion."""
    from ppke.pipeline.orchestrator import ingest_book

    book = _make_book(n_chapters=1, n_para_each=1)
    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key", max_workers=1),
    )
    stages = []

    def progress(stage, detail):
        stages.append(stage)

    with patch("ppke.pipeline.orchestrator.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.side_effect = [
            [{"paragraph_id": "{01}.p1", "topic_sentence": "T"}],
            {"central_thesis": {}, "argument_threads": []},
            {"concepts": []},
            {"patterns": []},
            {},
        ]
        ingest_book(book, cfg, progress_callback=progress)

    assert "extraction" in stages
    assert "validation" in stages
    assert "complete" in stages


# ── reread_chapters ───────────────────────────────────────────────────────────


def test_reread_chapters_success(tmp_path):
    from ppke.pipeline.orchestrator import reread_chapters

    # Set up book dir with meta.yml pointing to a real markdown file
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()

    source_md = tmp_path / "book.md"
    source_md.write_text("# Chapter 1\n\nHello world.\n\n# Chapter 2\n\nSecond chapter.")

    meta = {
        "title": "Test Book",
        "author": "Author",
        "year": 2024,
        "source_path": str(source_md),
        "human_operator": "tester",
    }
    (book_dir / "meta.yml").write_text(yaml.dump(meta))

    # Create existing extractions.json
    existing_extractions = [
        {"paragraph_id": "{01}.p1", "original_text": "Hello world.",
         "topic_sentence": "old topic", "depth": "full"},
        {"paragraph_id": "{02}.p1", "original_text": "Second chapter.",
         "topic_sentence": "second", "depth": "light"},
    ]
    (book_dir / "extractions.json").write_text(json.dumps(existing_extractions))

    cfg = Config(
        vault_path=tmp_path,
        llm=LLMConfig(provider="anthropic", anthropic_api_key="key", max_workers=1),
    )

    with patch("ppke.pipeline.orchestrator.LLMClient") as MockClient, \
         patch("ppke.pipeline.orchestrator._extract_with_retry") as mock_retry:
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        # Returns re-extracted result for chapter 1
        mock_retry.return_value = [
            ExtractionResult(paragraph_id="{01}.p1", original_text="Hello world.",
                             topic_sentence="new topic", depth=DepthLevel.FULL)
        ]

        mock_client.complete_json.side_effect = [
            {"central_thesis": {}, "argument_threads": []},
            {"concepts": []},
            {"patterns": []},
            {},
        ]

        result = reread_chapters(
            book_dir=book_dir,
            chapter_numbers=[1],
            config=cfg,
            progress_callback=lambda s, d: None,
        )

    assert result == book_dir


def test_reread_chapters_no_matching_chapters(tmp_path):
    """When no matching chapters exist, should return book_dir without error."""
    from ppke.pipeline.orchestrator import reread_chapters

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()

    source_md = tmp_path / "book.md"
    source_md.write_text("# Chapter 1\n\nHello world.")

    meta = {"title": "Test", "author": "Author", "source_path": str(source_md)}
    (book_dir / "meta.yml").write_text(yaml.dump(meta))

    cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))

    result = reread_chapters(
        book_dir=book_dir,
        chapter_numbers=[99],  # Chapter 99 doesn't exist
        config=cfg,
    )
    assert result == book_dir


def test_reread_chapters_missing_meta(tmp_path):
    from ppke.pipeline.orchestrator import reread_chapters

    book_dir = tmp_path / "Book_Test"
    book_dir.mkdir()
    # No meta.yml

    cfg = Config(vault_path=tmp_path, llm=LLMConfig())
    with pytest.raises(FileNotFoundError, match="No meta.yml"):
        reread_chapters(book_dir=book_dir, chapter_numbers=[1], config=cfg)


def test_reread_chapters_missing_source_path_in_meta(tmp_path):
    from ppke.pipeline.orchestrator import reread_chapters

    book_dir = tmp_path / "Book_Test"
    book_dir.mkdir()
    (book_dir / "meta.yml").write_text(yaml.dump({"title": "T", "author": "A"}))

    cfg = Config(vault_path=tmp_path, llm=LLMConfig())
    with pytest.raises(FileNotFoundError, match="No source_path"):
        reread_chapters(book_dir=book_dir, chapter_numbers=[1], config=cfg)


# ── Writer: deduplicate_concepts (lines 500-521) ──────────────────────────────


def test_deduplicate_concepts_success(tmp_path):
    from ppke.output.writer import _deduplicate_concepts

    concepts_by_book = {
        "Book_A": ["Dasein", "Being"],
        "Book_B": ["Dasein", "Time"],
    }

    cfg = Config(vault_path=tmp_path, llm=LLMConfig(provider="anthropic", anthropic_api_key="k"))

    with patch("ppke.llm.client.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.return_value = {
            "groups": [
                {
                    "canonical_name": "Dasein",
                    "members": [
                        {"book_folder": "Book_A", "concept_name": "Dasein", "reason": "same"},
                        {"book_folder": "Book_B", "concept_name": "Dasein", "reason": "same"},
                    ]
                }
            ]
        }
        result = _deduplicate_concepts(concepts_by_book, cfg)

    assert len(result) == 1
    assert result[0]["canonical_name"] == "Dasein"


def test_deduplicate_concepts_single_member_filtered(tmp_path):
    """Groups with < 2 members should be filtered out."""
    from ppke.output.writer import _deduplicate_concepts

    concepts_by_book = {"Book_A": ["Dasein"], "Book_B": ["Being"]}
    cfg = Config(vault_path=tmp_path, llm=LLMConfig(provider="anthropic", anthropic_api_key="k"))

    with patch("ppke.llm.client.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.return_value = {
            "groups": [
                {"canonical_name": "Dasein", "members": [{"book_folder": "Book_A"}]}
            ]
        }
        result = _deduplicate_concepts(concepts_by_book, cfg)

    assert result == []


def test_deduplicate_concepts_failure_returns_empty(tmp_path):
    """LLM error should return empty list (graceful degradation)."""
    from ppke.output.writer import _deduplicate_concepts

    concepts_by_book = {"Book_A": ["Dasein"], "Book_B": ["Dasein"]}
    cfg = Config(vault_path=tmp_path, llm=LLMConfig(provider="anthropic", anthropic_api_key="k"))

    with patch("ppke.llm.client.LLMClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.complete_json.side_effect = ValueError("LLM error")
        result = _deduplicate_concepts(concepts_by_book, cfg)

    assert result == []


def test_write_global_files_with_dedup(tmp_path):
    """write_global_files calls dedup when 2+ books have concepts."""
    from ppke.output.writer import write_global_files

    for name in ["Book_A_Author_2020", "Book_B_Author_2021"]:
        d = tmp_path / name
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": name, "author": "A",
                                                "verification_status": "COMPLETE"}))
        (d / "03_Concept_Index.md").write_text(f"# Concept Index: {name}\n## Dasein\n\nDef\n")
        (d / "05_Coverage_Report.md").write_text("- verification_status: COMPLETE\n")

    cfg = Config(vault_path=tmp_path, llm=LLMConfig(provider="anthropic", anthropic_api_key="key"))

    with patch("ppke.output.writer._deduplicate_concepts") as mock_dedup:
        mock_dedup.return_value = [
            {
                "canonical_name": "Dasein",
                "members": [
                    {"book_folder": "Book_A_Author_2020", "concept_name": "Dasein", "reason": "same"},
                    {"book_folder": "Book_B_Author_2021", "concept_name": "Dasein", "reason": "same"},
                ]
            }
        ]
        write_global_files(tmp_path, cfg)
        mock_dedup.assert_called_once()

    master = (tmp_path / "MASTER_CONCEPT_INDEX.md").read_text()
    assert "Semantic Groups" in master
    assert "Dasein" in master


def test_write_global_files_qa_incomplete(tmp_path):
    """QA_RESULTS.md should show INCOMPLETE if a coverage report has INCOMPLETE."""
    from ppke.output.writer import write_global_files

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    (book_dir / "meta.yml").write_text(yaml.dump({"title": "T", "author": "A",
                                                   "verification_status": "INCOMPLETE"}))
    (book_dir / "05_Coverage_Report.md").write_text(
        "- verification_status: INCOMPLETE\n- missing: [{01}.p2]\n"
    )

    cfg = Config(vault_path=tmp_path, llm=LLMConfig())
    write_global_files(tmp_path, cfg)

    qa = (tmp_path / "QA_RESULTS.md").read_text()
    assert "INCOMPLETE" in qa


# ── CLI: query with full output ───────────────────────────────────────────────


def test_query_full_output(tmp_path):
    """Test that all query output sections are rendered."""
    from click.testing import CliRunner
    runner = CliRunner()

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    (book_dir / "meta.yml").write_text(yaml.dump({"title": "T", "author": "A"}))
    (book_dir / "01_Raw_Structure.md").write_text("raw")
    (book_dir / "02_Logical_Map.md").write_text("map")
    (book_dir / "03_Concept_Index.md").write_text("concepts")

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.llm.client.LLMClient.complete_json") as mock_cj:
        from ppke.config import Config, LLMConfig
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
        mock_load.return_value = cfg
        mock_cj.return_value = {
            "answer": "Being is the question",
            "verbatim_quotes": [
                {"paragraph_id": "{01}.p1", "quote": "the question of being"}
            ],
            "logical_chain": [
                {"step": 1, "claim": "Being is asked", "paragraph_id": "{01}.p1",
                 "is_inference": False},
                {"step": 2, "claim": "Dasein asks", "paragraph_id": "{01}.p2",
                 "is_inference": True},
            ],
            "confidence": "high",
        }
        result = runner.invoke(
            main,
            ["query", "--book", "Book_Test_Author_2024", "--question", "What is being?"],
        )

    assert result.exit_code == 0
    assert "Being is the question" in result.output
    assert "Evidence" in result.output
    assert "Logical Chain" in result.output
    assert "[INFERENCE]" in result.output
    assert "high" in result.output


def test_query_no_books_in_vault(tmp_path):
    """If no books are in vault, query should show available book list."""
    from click.testing import CliRunner
    runner = CliRunner()
    tmp_path.mkdir(exist_ok=True)

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"):
        from ppke.config import Config, LLMConfig
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
        mock_load.return_value = cfg

        result = runner.invoke(
            main,
            ["query", "--book", "Book_Nonexistent", "--question", "What?"],
        )

    assert result.exit_code != 0


def test_query_vault_has_books_shows_available(tmp_path):
    """If book not found but vault has books, list them in error."""
    from click.testing import CliRunner
    runner = CliRunner()

    # Create a book dir so the vault isn't empty
    book_dir = tmp_path / "Book_Existing_Author_2024"
    book_dir.mkdir()

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"):
        from ppke.config import Config, LLMConfig
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
        mock_load.return_value = cfg

        result = runner.invoke(
            main,
            ["query", "--book", "Book_Nonexistent", "--question", "What?"],
        )

    assert result.exit_code != 0
    # Should show available books
    assert "Book_Existing_Author_2024" in result.output


# ── CLI: load_config_with_overrides ──────────────────────────────────────────


def test_load_config_with_overrides():
    from ppke.cli import _load_config_with_overrides
    with patch("ppke.config.Config.load") as mock_load:
        from ppke.config import Config, LLMConfig
        cfg = Config(llm=LLMConfig(provider="anthropic"))
        mock_load.return_value = cfg

        result = _load_config_with_overrides(
            provider="deepseek",
            model="deepseek-chat",
            vault_path=None,
            batch_size=3,
        )

    assert result.llm.provider == "deepseek"
    assert result.llm.model == "deepseek-chat"
    assert result.llm.paragraphs_per_batch == 3
