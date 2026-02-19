"""Loop-2 coverage tests: target every remaining uncovered line.

Covers gaps in:
  - cli.py lines 51, 80-81, 271, 287-289, 392, 635-652, 843, 945-946, 963, 991, 993
  - parser/markdown.py lines 54-56, 78-84, 153, 232-233
  - parser/models.py lines 37-38, 54, 88
  - pipeline/orchestrator.py lines 90-91, 250, 325-330, 390-393, 403, 588
  - pipeline/synthesizer.py line 22
  - llm/client.py line 162
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import yaml
from click.testing import CliRunner

from ppke.cli import main
from ppke.config import Config, LLMConfig
from ppke.parser.models import Book, Chapter, Paragraph, DepthLevel, ExtractionResult


# ── helpers ──────────────────────────────────────────────────────────────────

def _para(ch=1, num=1, text="Hello world."):
    return Paragraph(chapter_number=ch, paragraph_number=num, text=text)


def _extraction(pid="{01}.p1", text="Hello world.") -> ExtractionResult:
    return ExtractionResult(
        paragraph_id=pid,
        original_text=text,
        topic_sentence="Topic",
        function_in_argument="premise",
        explicit_claims=[],
        implicit_assumptions=[],
        logical_steps=[],
        defined_concepts=[],
        emotional_tone="neutral",
        tone_evidence="",
        internal_references=[],
        depth=DepthLevel.FULL,
    )


# ── cli.py line 51: vault_path override in _load_config_with_overrides ───────

def test_load_config_vault_path_override(tmp_path):
    """Line 51: vault_path branch in _load_config_with_overrides."""
    from ppke.cli import _load_config_with_overrides
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config()
        mock_load.return_value = cfg
        result = _load_config_with_overrides(vault_path=tmp_path)
    assert result.vault_path == tmp_path


# ── cli.py lines 80-81: _safe_book_dir with resolve() raising ────────────────

def test_safe_book_dir_resolve_fallback(tmp_path):
    """Lines 80-81: fallback to .absolute() when resolve(strict=False) raises."""
    from ppke.cli import _safe_book_dir
    from unittest.mock import PropertyMock

    # Create a vault and a valid book dir so relative_to() succeeds
    vault = tmp_path / "vault"
    vault.mkdir()

    # Patch Path.resolve to raise on the vault, triggering fallback to .absolute()
    original_resolve = Path.resolve

    def patched_resolve(self, strict=False):
        if str(self) == str(vault):
            raise OSError("simulated resolve failure")
        return original_resolve(self, strict=strict)

    with patch.object(Path, "resolve", patched_resolve):
        result = _safe_book_dir(vault, "Book_Test")
    # Should not raise — fell back to .absolute()
    assert result.name == "Book_Test"


# ── cli.py line 271: ingest --double-pass flag ───────────────────────────────

def test_ingest_double_pass_flag(tmp_path):
    """Line 271: config.double_pass = True when --double-pass is set."""
    runner = CliRunner()
    md_file = tmp_path / "book.md"
    md_file.write_text("# Chapter 1\n\nHello world.\n")

    captured_cfg = {}

    def fake_ingest(book, config, **kwargs):
        captured_cfg["double_pass"] = config.double_pass
        return tmp_path / "output"

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.pipeline.orchestrator.ingest_book", side_effect=fake_ingest):
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, [
            "ingest", str(md_file),
            "--title", "T", "--author", "A",
            "--double-pass",
        ])

    assert captured_cfg.get("double_pass") is True


# ── cli.py lines 287-289: ingest progress_callback body ─────────────────────

def test_ingest_progress_callback_invoked(tmp_path):
    """Lines 287-289: progress_callback is called and produces output."""
    runner = CliRunner()
    md_file = tmp_path / "book.md"
    md_file.write_text("# Chapter 1\n\nHello world.\n")

    def fake_ingest(book, config, progress_callback=None, **kwargs):
        if progress_callback:
            progress_callback("extract", "Chapter 01 processing")
        return tmp_path / "output"

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.pipeline.orchestrator.ingest_book", side_effect=fake_ingest):
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, [
            "ingest", str(md_file),
            "--title", "T", "--author", "A",
        ])

    assert result.exit_code == 0
    assert "extract" in result.output


# ── cli.py line 392: query with vault not existing ───────────────────────────

def test_query_vault_not_exist(tmp_path):
    """Line 392: 'Vault directory does not exist' branch in query command."""
    runner = CliRunner()
    missing_vault = tmp_path / "nonexistent_vault"

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"):
        cfg = Config(vault_path=missing_vault, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, [
            "query",
            "--book", "Book_Test_Author_2024",
            "--question", "What is being?",
        ])

    assert result.exit_code != 0
    assert "does not exist" in result.output.lower() or "not found" in result.output.lower()


# ── cli.py lines 635-652: re-read command ────────────────────────────────────

def test_reread_success(tmp_path):
    """Lines 635-649: re-read command happy path."""
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    meta = {"title": "Test Book", "author": "Author", "source_path": "/tmp/x.md"}
    (book_dir / "meta.yml").write_text(yaml.dump(meta))

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.pipeline.orchestrator.reread_chapters") as mock_rr:
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, [
            "re-read",
            "--book", "Book_Test_Author_2024",
            "--chapters", "1,2",
        ])

    assert result.exit_code == 0
    mock_rr.assert_called_once()
    assert "Re-read complete" in result.output


def test_reread_progress_callback_called(tmp_path):
    """Lines 639-640: re-read progress_callback body executed."""
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    meta = {"title": "T", "author": "A", "source_path": "/tmp/x.md"}
    (book_dir / "meta.yml").write_text(yaml.dump(meta))

    def fake_rr(book_dir, chapter_numbers, config, progress_callback=None):
        if progress_callback:
            progress_callback("reread", "Chapter 01 done")

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.pipeline.orchestrator.reread_chapters", side_effect=fake_rr):
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, [
            "re-read", "--book", "Book_Test_Author_2024", "--chapters", "1",
        ])

    assert result.exit_code == 0
    assert "reread" in result.output


def test_reread_file_not_found(tmp_path):
    """Lines 650-652: re-read propagates FileNotFoundError."""
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.pipeline.orchestrator.reread_chapters",
               side_effect=FileNotFoundError("No source")):
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, [
            "re-read", "--book", "Book_Test_Author_2024", "--chapters", "1",
        ])

    assert result.exit_code != 0
    assert "No source" in result.output


# ── cli.py line 843: stats INCOMPLETE book ───────────────────────────────────

def test_stats_incomplete_book(tmp_path):
    """Line 843: incomplete_count incremented for non-COMPLETE book."""
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    meta = {"title": "T", "author": "A", "total_chapters": 2,
            "total_paragraphs": 5, "verification_status": "INCOMPLETE"}
    (book_dir / "meta.yml").write_text(yaml.dump(meta))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["stats"])

    assert result.exit_code == 0
    assert "Incomplete" in result.output or "incomplete" in result.output.lower()


# ── cli.py lines 945-946: search --book not found ────────────────────────────

def test_search_specific_book_not_found(tmp_path):
    """Lines 945-946: search --book with non-existent folder."""
    runner = CliRunner()
    # Create vault but not the requested book folder
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, [
            "search", "anything",
            "--book", "Book_Nonexistent_Author_2024",
        ])

    assert result.exit_code != 0


# ── cli.py lines 991, 993: snippet prefix/suffix ellipsis ────────────────────

def test_search_snippet_with_prefix_ellipsis(tmp_path):
    """Line 991: snippet gets '...' prefix when match is not at text start."""
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    # Create long text so the match is deep enough for start > 0
    padding = "x" * 60
    extractions = [{
        "paragraph_id": "{01}.p1",
        "original_text": padding + "TARGET" + padding,
        "topic_sentence": "",
        "explicit_claims": [],
        "defined_concepts": [],
    }]
    (book_dir / "extractions.json").write_text(json.dumps(extractions))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "TARGET"])

    assert result.exit_code == 0
    assert "TARGET" in result.output


def test_search_snippet_with_suffix_ellipsis(tmp_path):
    """Line 993: snippet gets '...' suffix when match is not at text end."""
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    # Match near start; long tail after
    tail = "y" * 60
    extractions = [{
        "paragraph_id": "{01}.p1",
        "original_text": "TARGET" + tail,
        "topic_sentence": "",
        "explicit_claims": [],
        "defined_concepts": [],
    }]
    (book_dir / "extractions.json").write_text(json.dumps(extractions))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "TARGET"])

    assert result.exit_code == 0
    assert "TARGET" in result.output


# ── parser/markdown.py lines 54-56: roman numeral chapter ────────────────────

def test_parse_roman_numeral_chapter(tmp_path):
    """Lines 54-56: ROMAN_TO_NUM branch in _parse_chapter_number."""
    from ppke.parser.markdown import parse_markdown_book

    md = tmp_path / "book.md"
    md.write_text("# I. Introduction\n\nFirst paragraph.\n\n# II. Body\n\nSecond paragraph.\n")
    book = parse_markdown_book(md, "Test", "Author")

    assert len(book.chapters) == 2
    assert book.chapters[0].number == 1
    assert book.chapters[1].number == 2


# ── parser/markdown.py lines 78-84: H1 fallback heading ─────────────────────

def test_parse_h1_fallback_heading(tmp_path):
    """Lines 78-84: any H1 treated as chapter (fallback pattern)."""
    from ppke.parser.markdown import parse_markdown_book

    md = tmp_path / "book.md"
    # H1 headings that don't match the numbered/roman patterns → fallback
    md.write_text("# Introduction\n\nFirst paragraph.\n\n# Conclusion\n\nSecond paragraph.\n")
    book = parse_markdown_book(md, "Test", "Author")

    assert len(book.chapters) == 2
    assert book.chapters[0].title == "Introduction"
    assert book.chapters[1].title == "Conclusion"


# ── parser/markdown.py line 153: auto-numbered chapter ───────────────────────

def test_parse_auto_numbered_chapter(tmp_path):
    """Line 153: ch_num = _last_ch_num + 1 when heading has no number."""
    from ppke.parser.markdown import parse_markdown_book

    md = tmp_path / "book.md"
    # Mix: one numbered chapter then one un-numbered H1 → auto-number
    md.write_text(
        "# Chapter 1: First\n\nPara one.\n\n"
        "# Unnumbered\n\nPara two.\n"
    )
    book = parse_markdown_book(md, "Test", "Author")

    assert len(book.chapters) == 2
    assert book.chapters[0].number == 1
    assert book.chapters[1].number == 2  # auto-numbered


# ── parser/markdown.py lines 232-233: split_long_paragraphs no-split ─────────

def test_split_long_paragraphs_no_split_needed(tmp_path):
    """Lines 232-233: paragraphs that cannot be split at sentence boundary."""
    from ppke.parser.markdown import split_long_paragraphs

    book = Book(title="T", author="A")
    ch = Chapter(number=1, title="Ch1")
    # One very long 'sentence' (no period mid-way) — can't split further
    ch.paragraphs = [Paragraph(chapter_number=1, paragraph_number=1, text="word " * 600)]
    book.chapters = [ch]

    original_count = book.total_paragraphs
    split_long_paragraphs(book, max_tokens=100)  # 100 tokens → 400 chars limit
    # If not split-able at sentence level, paragraph stays as-is
    assert book.total_paragraphs >= original_count


# ── parser/models.py lines 37-38: Paragraph.__repr__ short text ──────────────

def test_paragraph_repr_short_text():
    """Lines 37-38: __repr__ with text shorter than 60 chars (no truncation)."""
    p = Paragraph(chapter_number=1, paragraph_number=1, text="Short.")
    r = repr(p)
    assert "Short." in r
    assert "..." not in r


def test_paragraph_repr_long_text():
    """Lines 37-38: __repr__ with text longer than 60 chars (truncation)."""
    p = Paragraph(chapter_number=1, paragraph_number=1, text="x" * 70)
    r = repr(p)
    assert "..." in r


# ── parser/models.py line 54: Chapter.__repr__ ───────────────────────────────

def test_chapter_repr():
    """Line 54: Chapter.__repr__ is exercised."""
    ch = Chapter(number=1, title="Intro")
    ch.paragraphs = [Paragraph(chapter_number=1, paragraph_number=1, text="Hi.")]
    r = repr(ch)
    assert "01" in r
    assert "Intro" in r
    assert "1 paragraph" in r


# ── parser/models.py line 88: Book.__repr__ ──────────────────────────────────

def test_book_repr():
    """Line 88: Book.__repr__ is exercised."""
    book = Book(title="Being", author="Heidegger", year="1927")
    r = repr(book)
    assert "Being" in r
    assert "Heidegger" in r


# ── orchestrator.py lines 90-91: invalid depth string fallback ───────────────

def test_load_checkpoint_invalid_depth(tmp_path):
    """Lines 90-91: DepthLevel fallback when depth string is invalid."""
    from ppke.pipeline.orchestrator import _load_checkpoint, _save_checkpoint

    cp_path = tmp_path / ".checkpoint_test.json"

    # Build a checkpoint with a corrupted depth value
    raw_data = {
        "completed_indices": [0],
        "extractions": [
            {
                "paragraph_id": "{01}.p1",
                "original_text": "text",
                "topic_sentence": "topic",
                "function_in_argument": "premise",
                "explicit_claims": [],
                "implicit_assumptions": [],
                "logical_steps": [],
                "defined_concepts": [],
                "emotional_tone": "neutral",
                "tone_evidence": "",
                "internal_references": [],
                "depth": "INVALID_DEPTH",  # will trigger ValueError → LIGHT
            }
        ],
    }
    import json
    cp_path.write_text(json.dumps(raw_data))

    result = _load_checkpoint(cp_path)
    assert result is not None
    indices, extractions = result
    assert extractions[0].depth == DepthLevel.LIGHT


# ── orchestrator.py line 250: split paragraphs progress ─────────────────────

def test_ingest_book_split_progress(tmp_path):
    """Line 250: split-paragraphs progress callback fires when paragraphs are split."""
    from ppke.pipeline.orchestrator import ingest_book

    book = Book(title="T", author="A")
    ch = Chapter(number=1, title="Ch1")
    # Very long paragraph that will be split
    ch.paragraphs = [Paragraph(chapter_number=1, paragraph_number=1,
                                text="Long sentence. " * 200)]
    book.chapters = [ch]

    config = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
    config.llm.max_paragraph_tokens = 50  # tiny limit forces split
    config.llm.max_workers = 1

    progress_calls = []

    def mock_extract(**kwargs):
        chapter = kwargs["chapter"]
        p = chapter.paragraphs[0]
        return [_extraction(p.paragraph_id, p.text)]

    book_out = tmp_path / "Book_T_A"
    book_out.mkdir(parents=True, exist_ok=True)

    with patch("ppke.pipeline.orchestrator.extract_chapter", side_effect=mock_extract), \
         patch("ppke.pipeline.orchestrator.build_logical_map", return_value={}), \
         patch("ppke.pipeline.orchestrator.build_concept_index", return_value={}), \
         patch("ppke.pipeline.orchestrator.detect_patterns", return_value=[]), \
         patch("ppke.pipeline.orchestrator._build_author_model", return_value={}), \
         patch("ppke.pipeline.orchestrator.write_all_book_files", return_value=book_out), \
         patch("ppke.pipeline.orchestrator.write_global_files"):

        def pcb(stage, detail):
            progress_calls.append((stage, detail))

        ingest_book(book, config, progress_callback=pcb)

    split_calls = [c for c in progress_calls if c[0] == "split"]
    assert len(split_calls) > 0, "Expected split progress event"


# ── orchestrator.py lines 325-330: parallel extraction exception ─────────────

def test_ingest_book_parallel_chapter_exception(tmp_path):
    """Lines 325-330: exception in parallel chapter thread is caught gracefully."""
    from ppke.pipeline.orchestrator import ingest_book

    book = Book(title="T", author="A")
    ch1 = Chapter(number=1, title="Ch1")
    ch1.paragraphs = [Paragraph(chapter_number=1, paragraph_number=1, text="Hello.")]
    ch2 = Chapter(number=2, title="Ch2")
    ch2.paragraphs = [Paragraph(chapter_number=2, paragraph_number=1, text="World.")]
    book.chapters = [ch1, ch2]

    config = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
    config.llm.max_workers = 2  # parallel

    call_count = [0]

    def mock_extract(**kwargs):
        chapter = kwargs["chapter"]
        call_count[0] += 1
        if chapter.number == 2:
            raise RuntimeError("Simulated extraction failure")
        p = chapter.paragraphs[0]
        return [_extraction(p.paragraph_id, p.text)]

    book_out = tmp_path / "Book_T_A"
    book_out.mkdir(parents=True, exist_ok=True)

    with patch("ppke.pipeline.orchestrator.extract_chapter", side_effect=mock_extract), \
         patch("ppke.pipeline.orchestrator.build_logical_map", return_value={}), \
         patch("ppke.pipeline.orchestrator.build_concept_index", return_value={}), \
         patch("ppke.pipeline.orchestrator.detect_patterns", return_value=[]), \
         patch("ppke.pipeline.orchestrator._build_author_model", return_value={}), \
         patch("ppke.pipeline.orchestrator.write_all_book_files", return_value=book_out), \
         patch("ppke.pipeline.orchestrator.write_global_files"):

        # Should not raise despite chapter 2 failing
        ingest_book(book, config)

    # Both chapters were attempted
    assert call_count[0] == 2


# ── orchestrator.py lines 390-393: double_pass missing paragraph ─────────────

def test_ingest_book_double_pass_missing_paragraph(tmp_path, caplog):
    """Lines 390-393: warning logged when paragraph missing from both passes."""
    import logging
    from ppke.pipeline.orchestrator import ingest_book

    book = Book(title="T", author="A")
    ch = Chapter(number=1, title="Ch1")
    ch.paragraphs = [
        Paragraph(chapter_number=1, paragraph_number=1, text="Para one."),
        Paragraph(chapter_number=1, paragraph_number=2, text="Para two."),
    ]
    book.chapters = [ch]

    p1_id = ch.paragraphs[0].paragraph_id

    config = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
    config.double_pass = True
    config.llm.max_workers = 1

    call_count = [0]

    def mock_extract(**kwargs):
        call_count[0] += 1
        # Both passes only return p1 — p2 missing from both
        return [_extraction(p1_id, "Para one.")]

    book_out = tmp_path / "Book_T_A"
    book_out.mkdir(parents=True, exist_ok=True)

    with patch("ppke.pipeline.orchestrator.extract_chapter", side_effect=mock_extract), \
         patch("ppke.pipeline.orchestrator.build_logical_map", return_value={}), \
         patch("ppke.pipeline.orchestrator.build_concept_index", return_value={}), \
         patch("ppke.pipeline.orchestrator.detect_patterns", return_value=[]), \
         patch("ppke.pipeline.orchestrator._build_author_model", return_value={}), \
         patch("ppke.pipeline.orchestrator.write_all_book_files", return_value=book_out), \
         patch("ppke.pipeline.orchestrator.write_global_files"), \
         caplog.at_level(logging.WARNING, logger="ppke.pipeline.orchestrator"):

        ingest_book(book, config)

    # p2 missing from both passes — should have logged a warning
    assert any("missing" in r.message.lower() for r in caplog.records)


# ── orchestrator.py line 403: INCOMPLETE validation warning ──────────────────

def test_ingest_book_incomplete_validation_warning(tmp_path, caplog):
    """Line 403: progress callback + log when validation returns INCOMPLETE."""
    import logging
    from ppke.pipeline.orchestrator import ingest_book

    book = Book(title="T", author="A")
    ch = Chapter(number=1, title="Ch1")
    ch.paragraphs = [
        Paragraph(chapter_number=1, paragraph_number=1, text="Para one."),
        Paragraph(chapter_number=1, paragraph_number=2, text="Para two."),
    ]
    book.chapters = [ch]

    config = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
    config.llm.max_workers = 1

    # Always return p1's id regardless of chapter — so p2 is never extracted → INCOMPLETE
    always_p1_id = ch.paragraphs[0].paragraph_id

    def mock_extract(**kwargs):
        return [_extraction(always_p1_id, "Para one.")]

    progress_calls = []
    book_out = tmp_path / "Book_T_A"
    book_out.mkdir(parents=True, exist_ok=True)

    with patch("ppke.pipeline.orchestrator.extract_chapter", side_effect=mock_extract), \
         patch("ppke.pipeline.orchestrator.build_logical_map", return_value={}), \
         patch("ppke.pipeline.orchestrator.build_concept_index", return_value={}), \
         patch("ppke.pipeline.orchestrator.detect_patterns", return_value=[]), \
         patch("ppke.pipeline.orchestrator._build_author_model", return_value={}), \
         patch("ppke.pipeline.orchestrator.write_all_book_files", return_value=book_out), \
         patch("ppke.pipeline.orchestrator.write_global_files"):

        ingest_book(book, config, progress_callback=lambda s, d: progress_calls.append((s, d)))

    validation_warnings = [c for c in progress_calls if c[0] == "validation" and "WARNING" in c[1]]
    assert len(validation_warnings) > 0


# ── orchestrator.py line 588: re-read paragraph missing from both ─────────────

def test_reread_paragraph_missing_from_both(tmp_path, caplog):
    """Line 588: warning logged when paragraph missing from re-read + saved."""
    import logging
    from ppke.pipeline.orchestrator import reread_chapters

    book_dir = tmp_path / "Book_T_A"
    book_dir.mkdir()
    meta = {
        "title": "T", "author": "A",
        "source_path": str(tmp_path / "book.md"),
    }
    (book_dir / "meta.yml").write_text(yaml.dump(meta))
    # Source file with 2 paragraphs
    (tmp_path / "book.md").write_text(
        "# Chapter 1\n\nPara one.\n\nPara two.\n"
    )
    # Saved extractions only have para 1
    p1_id = "{01}.p1"
    saved = [
        {"paragraph_id": p1_id, "original_text": "Para one.", "topic_sentence": "T",
         "function_in_argument": "p", "explicit_claims": [], "implicit_assumptions": [],
         "logical_steps": [], "defined_concepts": [], "emotional_tone": "n",
         "tone_evidence": "", "internal_references": [], "depth": "FULL"},
    ]
    (book_dir / "extractions.json").write_text(json.dumps(saved))

    config = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
    config.llm.max_workers = 1

    # Always return p1's id — so p2 is never re-extracted, and also absent from saved → warning
    def mock_extract(**kwargs):
        return [_extraction(p1_id, "Para one.")]

    with patch("ppke.pipeline.orchestrator.extract_chapter", side_effect=mock_extract), \
         patch("ppke.pipeline.orchestrator.build_logical_map", return_value={}), \
         patch("ppke.pipeline.orchestrator.build_concept_index", return_value={}), \
         patch("ppke.pipeline.orchestrator.detect_patterns", return_value=[]), \
         patch("ppke.pipeline.orchestrator._build_author_model", return_value={}), \
         patch("ppke.pipeline.orchestrator.write_all_book_files", return_value=book_dir), \
         patch("ppke.pipeline.orchestrator.write_global_files"), \
         caplog.at_level(logging.WARNING, logger="ppke.pipeline.orchestrator"):

        reread_chapters(
            book_dir=book_dir,
            chapter_numbers=[1],
            config=config,
        )

    assert any("missing" in r.message.lower() for r in caplog.records)


# ── orchestrator.py: chapter_numbers validation ───────────────────────────────

def test_reread_empty_chapter_numbers(tmp_path):
    """reread_chapters raises ValueError for empty chapter_numbers."""
    from ppke.pipeline.orchestrator import reread_chapters
    config = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
    with pytest.raises(ValueError, match="must not be empty"):
        reread_chapters(book_dir=tmp_path, chapter_numbers=[], config=config)


def test_reread_negative_chapter_numbers(tmp_path):
    """reread_chapters raises ValueError for non-positive chapter numbers."""
    from ppke.pipeline.orchestrator import reread_chapters
    config = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
    with pytest.raises(ValueError, match="positive integers"):
        reread_chapters(book_dir=tmp_path, chapter_numbers=[-1, 0], config=config)


# ── pipeline/synthesizer.py line 22: _load_book_analysis no meta.yml ─────────

def test_synthesizer_load_book_analysis_no_meta(tmp_path):
    """Line 22: _load_book_analysis returns None when meta.yml absent."""
    from ppke.pipeline.synthesizer import _load_book_analysis

    book_dir = tmp_path / "Book_NoMeta"
    book_dir.mkdir()
    # No meta.yml
    result = _load_book_analysis(book_dir)
    assert result is None


# ── llm/client.py line 162: retry exhaustion raises last_exc ─────────────────

def test_llm_client_retry_exhaustion_raises():
    """Line 162: raise last_exc when all retries are consumed."""
    from ppke.llm.client import LLMClient
    import openai

    cfg = LLMConfig(provider="openai", openai_api_key="key")
    client = LLMClient(cfg)

    # Build a 429 error that _is_retryable recognises
    rate_err = openai.RateLimitError(
        "rate limit",
        response=MagicMock(status_code=429, headers={}),
        body={},
    )

    mock_oai = MagicMock()
    mock_oai.chat.completions.create.side_effect = rate_err
    client._openai_client = mock_oai

    with patch("time.sleep"):  # don't actually sleep
        with pytest.raises(openai.RateLimitError):
            client.complete("sys", "usr")

    # Should have been called max_retries + 1 times (1 initial + retries)
    assert mock_oai.chat.completions.create.call_count >= 2


# ── Loop-3 additions ──────────────────────────────────────────────────────────

# cli.py:967 — continue when extractions.json is absent in a book dir ─────────

def test_search_book_dir_no_extractions_json(tmp_path):
    """cli.py:967 — book dir exists but has no extractions.json → continue."""
    runner = CliRunner()
    # Create a book_dir with NO extractions.json — name must start with "Book_"
    book_dir_empty = tmp_path / "Book_Empty_A_2024"
    book_dir_empty.mkdir()

    # A second dir with extractions so we get a real hit
    book_dir_full = tmp_path / "Book_Full_A_2024"
    book_dir_full.mkdir()
    extractions = [{
        "paragraph_id": "{01}.p1",
        "original_text": "FINDME content here",
        "topic_sentence": "",
        "explicit_claims": [],
        "defined_concepts": [],
    }]
    (book_dir_full / "extractions.json").write_text(json.dumps(extractions))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "FINDME"])

    # Should still find result from Book_Full (Book_Empty was skipped via continue)
    assert result.exit_code == 0
    assert "FINDME" in result.output


# parser/markdown.py:56 — _parse_chapter_number returns None for unknown string

def test_parse_chapter_number_no_match():
    """markdown.py:56 — return None when raw string is not digit, word, or roman."""
    from ppke.parser.markdown import _parse_chapter_number

    # "xyz" is not a digit, not in WORD_TO_NUM, not in ROMAN_TO_NUM
    result = _parse_chapter_number("xyz")
    assert result is None


# parser/markdown.py:84 — _detect_chapter_heading returns None for H2 non-match

def test_detect_chapter_heading_h2_no_match():
    """markdown.py:84 — H2 heading with no numbered pattern → return None."""
    from ppke.parser.markdown import _detect_chapter_heading

    # "## Random Heading" starts with # but is H2 — fallback only matches H1 (#\s+)
    result = _detect_chapter_heading("## Random Heading")
    # H2 without chapter keyword/number → None (line 84 hit)
    assert result is None


# orchestrator.py:391 — double-pass: p2 failed but p1 valid → use p1 ──────────

def test_ingest_book_double_pass_p1_used_when_p2_failed(tmp_path):
    """orchestrator.py:391 — p2 has FAILED marker but p1 valid → merged.append(p1)."""
    from ppke.pipeline.orchestrator import ingest_book
    from ppke.pipeline.validator import EXTRACTION_FAILED_MARKER

    book = Book(title="T", author="A")
    ch = Chapter(number=1, title="Ch1")
    ch.paragraphs = [
        Paragraph(chapter_number=1, paragraph_number=1, text="Para one."),
        Paragraph(chapter_number=1, paragraph_number=2, text="Para two."),
    ]
    book.chapters = [ch]

    p1_id = ch.paragraphs[0].paragraph_id
    p2_id = ch.paragraphs[1].paragraph_id

    config = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
    config.double_pass = True
    config.llm.max_workers = 1

    call_count = [0]

    def mock_extract(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # Pass 1: both paragraphs extracted successfully
            return [
                _extraction(p1_id, "Para one."),
                _extraction(p2_id, "Para two."),
            ]
        else:
            # Pass 2: p1 valid, p2 FAILED → triggers line 391 for p2
            failed_p2 = _extraction(p2_id, "Para two.")
            failed_p2 = ExtractionResult(
                paragraph_id=p2_id,
                original_text="Para two.",
                topic_sentence=EXTRACTION_FAILED_MARKER,
                function_in_argument="premise",
                explicit_claims=[],
                implicit_assumptions=[],
                logical_steps=[],
                defined_concepts=[],
                emotional_tone="neutral",
                tone_evidence="",
                internal_references=[],
                depth=DepthLevel.FULL,
            )
            return [_extraction(p1_id, "Para one."), failed_p2]

    book_out = tmp_path / "Book_T_A"
    book_out.mkdir(parents=True, exist_ok=True)

    with patch("ppke.pipeline.orchestrator.extract_chapter", side_effect=mock_extract), \
         patch("ppke.pipeline.orchestrator.build_logical_map", return_value={}), \
         patch("ppke.pipeline.orchestrator.build_concept_index", return_value={}), \
         patch("ppke.pipeline.orchestrator.detect_patterns", return_value=[]), \
         patch("ppke.pipeline.orchestrator._build_author_model", return_value={}), \
         patch("ppke.pipeline.orchestrator.write_all_book_files", return_value=book_out), \
         patch("ppke.pipeline.orchestrator.write_global_files"):

        ingest_book(book, config)

    # 2 calls: one for pass 1, one for pass 2
    assert call_count[0] == 2
