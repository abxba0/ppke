"""Comprehensive tests to boost overall coverage past 90%.

Covers: pipeline (extractor, logical_map, concepts, patterns, synthesizer,
orchestrator), output writer, CLI commands (list, stats, search, query,
cross-query, config), and LLM client (anthropic / openai paths).
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
from ppke.llm.client import LLMClient
from ppke.parser.models import (
    Book,
    Chapter,
    CoverageReport,
    DepthLevel,
    ExtractionResult,
    Paragraph,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_book(title="Test Book", author="Author", year="2024") -> Book:
    book = Book(title=title, author=author, year=year)
    ch = Chapter(number=1, title="Introduction")
    ch.paragraphs = [
        Paragraph(chapter_number=1, paragraph_number=1, text="Hello world."),
        Paragraph(chapter_number=1, paragraph_number=2, text="Second paragraph."),
    ]
    book.chapters = [ch]
    return book


def _make_extraction(pid="{01}.p1", text="Hello world.") -> ExtractionResult:
    return ExtractionResult(
        paragraph_id=pid,
        original_text=text,
        topic_sentence="A topic",
        function_in_argument="premise",
        explicit_claims=["Claim A"],
        implicit_assumptions=["Assumption B"],
        logical_steps=["Step 1"],
        defined_concepts=["Concept X"],
        emotional_tone="neutral",
        tone_evidence="evidence text",
        internal_references=["ref1"],
        depth=DepthLevel.FULL,
    )


def _make_coverage() -> CoverageReport:
    return CoverageReport(
        total_chapters=1,
        total_paragraphs=2,
        processed_paragraph_count=2,
        verification_status="COMPLETE",
        ingest_date="2024-01-01",
    )


# ── LLMClient: Anthropic path ─────────────────────────────────────────────────


def test_complete_anthropic_returns_text():
    cfg = LLMConfig(provider="anthropic", anthropic_api_key="ant-key")
    client = LLMClient(cfg)

    mock_content = MagicMock()
    mock_content.text = "Anthropic response"
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_ant = MagicMock()
    mock_ant.messages.create.return_value = mock_response
    client._anthropic_client = mock_ant

    result = client.complete("sys", "usr")
    assert result == "Anthropic response"
    mock_ant.messages.create.assert_called_once()
    kwargs = mock_ant.messages.create.call_args[1]
    assert kwargs["model"] == cfg.model
    # system prompt is now passed as a cache_control block for prompt caching
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][0]["text"] == "sys"
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["messages"][0]["content"] == "usr"


def test_get_anthropic_lazy_init():
    cfg = LLMConfig(provider="anthropic", anthropic_api_key="ant-key")
    client = LLMClient(cfg)
    mock_ant_instance = MagicMock()

    with patch("anthropic.Anthropic", return_value=mock_ant_instance):
        r1 = client._get_anthropic()
        r2 = client._get_anthropic()
    assert r1 is r2 is mock_ant_instance


def test_complete_openai_returns_text():
    cfg = LLMConfig(provider="openai", openai_api_key="oai-key")
    client = LLMClient(cfg)

    mock_msg = MagicMock()
    mock_msg.content = "OpenAI response"
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    mock_oai = MagicMock()
    mock_oai.chat.completions.create.return_value = mock_resp
    client._openai_client = mock_oai

    result = client.complete("sys", "usr")
    assert result == "OpenAI response"


def test_complete_openai_json_mode():
    cfg = LLMConfig(provider="openai", openai_api_key="oai-key")
    client = LLMClient(cfg)

    mock_msg = MagicMock()
    mock_msg.content = '{"key": "val"}'
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    mock_oai = MagicMock()
    mock_oai.chat.completions.create.return_value = mock_resp
    client._openai_client = mock_oai

    result = client.complete("sys", "usr", response_format="json")
    assert result == '{"key": "val"}'
    kwargs = mock_oai.chat.completions.create.call_args[1]
    assert kwargs["response_format"] == {"type": "json_object"}


def test_complete_openai_empty_content_raises():
    cfg = LLMConfig(provider="openai", openai_api_key="oai-key")
    client = LLMClient(cfg)

    mock_msg = MagicMock()
    mock_msg.content = None
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    mock_oai = MagicMock()
    mock_oai.chat.completions.create.return_value = mock_resp
    client._openai_client = mock_oai

    with pytest.raises(ValueError, match="OpenAI returned empty content"):
        client.complete("sys", "usr")


def test_get_openai_lazy_init():
    cfg = LLMConfig(provider="openai", openai_api_key="oai-key")
    client = LLMClient(cfg)
    mock_oai_instance = MagicMock()

    with patch("openai.OpenAI", return_value=mock_oai_instance):
        r1 = client._get_openai()
        r2 = client._get_openai()
    assert r1 is r2 is mock_oai_instance


def test_complete_json_anthropic_path():
    """Anthropic uses text mode (not json mode) for complete_json."""
    cfg = LLMConfig(provider="anthropic", anthropic_api_key="ant-key")
    client = LLMClient(cfg)

    mock_content = MagicMock()
    mock_content.text = '{"answer": 42}'
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_ant = MagicMock()
    mock_ant.messages.create.return_value = mock_response
    client._anthropic_client = mock_ant

    result = client.complete_json("sys", "usr")
    assert result == {"answer": 42}


def test_retry_exhausted_raises_last_exception(monkeypatch):
    """When all retries fail, the last exception is raised."""
    monkeypatch.setattr("time.sleep", lambda s: None)
    cfg = LLMConfig(provider="openai", openai_api_key="oai-key")
    client = LLMClient(cfg)

    exc = Exception("429 rate limit")
    mock_oai = MagicMock()
    mock_oai.chat.completions.create.side_effect = exc
    client._openai_client = mock_oai

    with pytest.raises(Exception, match="429 rate limit"):
        client.complete("sys", "usr")

    # Should have been called 5 times (1 initial + 4 retries)
    assert mock_oai.chat.completions.create.call_count == 5


# ── Output Writer ─────────────────────────────────────────────────────────────


def test_write_meta_yml(tmp_path):
    from ppke.output.writer import write_meta_yml
    book = _make_book()
    coverage = _make_coverage()
    path = write_meta_yml(tmp_path, book, coverage, human_operator="tester")
    assert path.exists()
    meta = yaml.safe_load(path.read_text())
    assert meta["title"] == "Test Book"
    assert meta["author"] == "Author"
    assert meta["human_operator"] == "tester"
    assert meta["verification_status"] == "COMPLETE"


def test_write_meta_yml_no_operator(tmp_path):
    from ppke.output.writer import write_meta_yml
    book = _make_book()
    coverage = _make_coverage()
    path = write_meta_yml(tmp_path, book, coverage)
    meta = yaml.safe_load(path.read_text())
    assert meta["human_operator"] == "unspecified"


def test_write_raw_structure(tmp_path):
    from ppke.output.writer import write_raw_structure
    book = _make_book()
    extractions = [
        _make_extraction("{01}.p1", "Hello world."),
        _make_extraction("{01}.p2", "Second paragraph."),
    ]
    path = write_raw_structure(tmp_path, book, extractions)
    assert path.exists()
    content = path.read_text()
    assert "Raw Structure: Test Book" in content
    assert "Hello world." in content
    assert "Second paragraph." in content
    assert "Claim A" in content
    assert "Assumption B" in content
    assert "Concept X" in content
    assert "Step 1" in content
    assert "neutral" in content
    assert "ref1" in content


def test_write_raw_structure_no_extraction(tmp_path):
    from ppke.output.writer import write_raw_structure
    book = _make_book()
    path = write_raw_structure(tmp_path, book, [])
    content = path.read_text()
    assert "Hello world." in content  # original text still present


def test_write_logical_map(tmp_path):
    from ppke.output.writer import write_logical_map
    book = _make_book()
    logical_map = {
        "central_thesis": {
            "claim": "Being is primary",
            "paragraph_ids": ["{01}.p1"],
            "evidence": "Direct evidence",
        },
        "argument_threads": [
            {
                "name": "Ontological Thread",
                "premises": [
                    {"claim": "Premise A", "paragraph_ids": ["{01}.p1"], "is_inference": False},
                    {"claim": "Inference B", "paragraph_ids": ["{01}.p2"], "is_inference": True},
                ],
                "conclusion": {"claim": "Therefore C", "paragraph_ids": ["{01}.p2"]},
                "logical_issues": ["Potential circular argument"],
            }
        ],
        "key_assumptions": [
            {"assumption": "Reality is structured", "depends_on": ["{01}.p1"]},
        ],
    }
    path = write_logical_map(tmp_path, book, logical_map)
    assert path.exists()
    content = path.read_text()
    assert "Being is primary" in content
    assert "Ontological Thread" in content
    assert "[INFERENCE]" in content
    assert "Potential circular argument" in content
    assert "Reality is structured" in content


def test_write_logical_map_empty(tmp_path):
    from ppke.output.writer import write_logical_map
    book = _make_book()
    path = write_logical_map(tmp_path, book, {"central_thesis": {}, "argument_threads": []})
    assert path.exists()


def test_write_concept_index(tmp_path):
    from ppke.output.writer import write_concept_index
    book = _make_book()
    concept_data = {
        "concepts": [
            {
                "name": "Dasein",
                "definition": "Being-there",
                "occurrences": [
                    {"paragraph_id": "{01}.p1", "quote": "dasein quote", "usage_context": "intro"}
                ],
                "semantic_shifts": [
                    {"from_id": "{01}.p1", "to_id": "{01}.p2", "description": "shift desc"}
                ],
                "related_concepts": ["Being", "Time"],
            }
        ]
    }
    path = write_concept_index(tmp_path, book, concept_data)
    assert path.exists()
    content = path.read_text()
    assert "Dasein" in content
    assert "Being-there" in content
    assert "dasein quote" in content
    assert "shift desc" in content
    assert "Being" in content


def test_write_author_model(tmp_path):
    from ppke.output.writer import write_author_model
    book = _make_book()
    author_model = {
        "ontology": {
            "description": "Realist ontology",
            "evidence": [{"paragraph_id": "{01}.p1", "quote": "evidence here"}],
        },
        "epistemology": {"description": "Empiricist", "evidence": []},
        "core_tensions": [
            {
                "tension": "Freedom vs Determinism",
                "evidence": [{"paragraph_id": "{01}.p1", "quote": "free quote"}],
            }
        ],
    }
    path = write_author_model(tmp_path, book, author_model)
    assert path.exists()
    content = path.read_text()
    assert "Realist ontology" in content
    assert "evidence here" in content
    assert "Freedom vs Determinism" in content


def test_write_coverage_report(tmp_path):
    from ppke.output.writer import write_coverage_report
    coverage = CoverageReport(
        total_chapters=3,
        total_paragraphs=10,
        processed_paragraph_count=10,
        verification_status="COMPLETE",
        ingest_date="2024-01-01",
        missing_paragraph_ids=[],
        re_read_pass_completed=True,
        notes="All good",
    )
    path = write_coverage_report(tmp_path, coverage)
    assert path.exists()
    content = path.read_text()
    assert "total_chapters" in content
    assert "COMPLETE" in content
    assert "All good" in content


def test_save_and_load_extractions_json(tmp_path):
    from ppke.output.writer import _save_extractions_json, load_extractions_json

    extractions = [
        _make_extraction("{01}.p1", "Hello"),
        ExtractionResult(
            paragraph_id="{01}.p2",
            original_text="World",
            topic_sentence="topic",
            depth=DepthLevel.LIGHT,
        ),
    ]
    _save_extractions_json(tmp_path, extractions)
    loaded = load_extractions_json(tmp_path)
    assert len(loaded) == 2
    assert loaded[0].paragraph_id == "{01}.p1"
    assert loaded[0].depth == DepthLevel.FULL
    assert loaded[1].depth == DepthLevel.LIGHT


def test_load_extractions_json_missing_file(tmp_path):
    from ppke.output.writer import load_extractions_json
    result = load_extractions_json(tmp_path)
    assert result == []


def test_load_extractions_json_invalid_depth(tmp_path):
    from ppke.output.writer import load_extractions_json
    data = [{"paragraph_id": "{01}.p1", "original_text": "x",
              "topic_sentence": "", "depth": "INVALID"}]
    (tmp_path / "extractions.json").write_text(json.dumps(data))
    result = load_extractions_json(tmp_path)
    assert result[0].depth == DepthLevel.LIGHT  # falls back to LIGHT


def test_write_global_files(tmp_path):
    from ppke.output.writer import write_global_files

    # Create a book dir with required files
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    (book_dir / "meta.yml").write_text(
        yaml.dump({"title": "Test", "author": "Author", "verification_status": "COMPLETE"})
    )
    (book_dir / "03_Concept_Index.md").write_text("# Concept Index: Test\n## Dasein\n\nDef\n")
    (book_dir / "05_Coverage_Report.md").write_text("- verification_status: COMPLETE\n")

    cfg = Config(vault_path=tmp_path, llm=LLMConfig(provider="anthropic"))
    write_global_files(tmp_path, cfg)

    assert (tmp_path / "00_PROJECT_SETTINGS.md").exists()
    assert (tmp_path / "MASTER_CONCEPT_INDEX.md").exists()
    assert (tmp_path / "QA_RESULTS.md").exists()
    assert (tmp_path / "PLAYBOOK.md").exists()

    settings = (tmp_path / "00_PROJECT_SETTINGS.md").read_text()
    assert "anthropic" in settings

    master = (tmp_path / "MASTER_CONCEPT_INDEX.md").read_text()
    assert "Book_Test_Author_2024" in master


def test_write_global_files_incomplete_book(tmp_path):
    from ppke.output.writer import write_global_files

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    # No meta.yml or coverage report
    (book_dir / "some_file.txt").write_text("data")

    cfg = Config(vault_path=tmp_path, llm=LLMConfig())
    write_global_files(tmp_path, cfg)

    qa = (tmp_path / "QA_RESULTS.md").read_text()
    assert "NO COVERAGE REPORT FOUND" in qa or "INCOMPLETE" in qa


def test_write_global_files_no_meta_yml(tmp_path):
    from ppke.output.writer import write_global_files

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    # No meta.yml — should still run without error

    cfg = Config(vault_path=tmp_path, llm=LLMConfig())
    write_global_files(tmp_path, cfg)
    settings = (tmp_path / "00_PROJECT_SETTINGS.md").read_text()
    assert "(no meta.yml)" in settings


# ── Pipeline: Extractor ───────────────────────────────────────────────────────


def test_paragraphs_to_json():
    from ppke.pipeline.extractor import _paragraphs_to_json
    paras = [
        Paragraph(chapter_number=1, paragraph_number=1, text="Hello"),
        Paragraph(chapter_number=1, paragraph_number=2, text="World"),
    ]
    result = json.loads(_paragraphs_to_json(paras))
    assert len(result) == 2
    assert result[0]["paragraph_id"] == "{01}.p1"
    assert result[0]["text"] == "Hello"


def test_parse_extraction_response():
    from ppke.pipeline.extractor import _parse_extraction_response
    paras = [Paragraph(chapter_number=1, paragraph_number=1, text="Hello")]
    raw = [{
        "paragraph_id": "{01}.p1",
        "topic_sentence": "A topic",
        "function_in_argument": "premise",
        "explicit_claims": ["Claim"],
        "is_argument_carrying": True,
    }]
    results = _parse_extraction_response(raw, paras)
    assert len(results) == 1
    assert results[0].paragraph_id == "{01}.p1"
    assert results[0].depth == DepthLevel.FULL
    assert results[0].original_text == "Hello"
    assert paras[0].depth == DepthLevel.FULL


def test_parse_extraction_response_unknown_paragraph():
    from ppke.pipeline.extractor import _parse_extraction_response
    raw = [{"paragraph_id": "UNKNOWN", "topic_sentence": "x"}]
    results = _parse_extraction_response(raw, [])
    assert len(results) == 1
    assert results[0].original_text == ""  # no para found


def test_extract_chapter_success():
    from ppke.pipeline.extractor import extract_chapter

    ch = Chapter(number=1, title="Intro")
    ch.paragraphs = [Paragraph(chapter_number=1, paragraph_number=1, text="Text")]

    mock_client = MagicMock()
    mock_client.complete_json.return_value = [{
        "paragraph_id": "{01}.p1",
        "topic_sentence": "Topic",
        "is_argument_carrying": True,
    }]

    results = extract_chapter(mock_client, ch, "Book", "Author", batch_size=5)
    assert len(results) == 1
    assert results[0].topic_sentence == "Topic"


def test_extract_chapter_with_paragraphs_wrapper():
    """Response wrapped in {'paragraphs': [...]} should be unwrapped."""
    from ppke.pipeline.extractor import extract_chapter

    ch = Chapter(number=1, title="Intro")
    ch.paragraphs = [Paragraph(chapter_number=1, paragraph_number=1, text="Text")]

    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "paragraphs": [{"paragraph_id": "{01}.p1", "topic_sentence": "T"}]
    }

    results = extract_chapter(mock_client, ch, "Book", "Author")
    assert len(results) == 1


def test_extract_chapter_non_list_response():
    """Non-list, non-dict response is wrapped in a list."""
    from ppke.pipeline.extractor import extract_chapter

    ch = Chapter(number=1, title="Intro")
    ch.paragraphs = [Paragraph(chapter_number=1, paragraph_number=1, text="Text")]

    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "paragraph_id": "{01}.p1",
        "topic_sentence": "T"
    }

    results = extract_chapter(mock_client, ch, "Book", "Author")
    assert len(results) == 1


def test_extract_chapter_failure_creates_fallback():
    """When LLM call fails, fallback ExtractionResult is created."""
    from ppke.pipeline.extractor import extract_chapter

    ch = Chapter(number=1, title="Intro")
    ch.paragraphs = [Paragraph(chapter_number=1, paragraph_number=1, text="Text")]

    mock_client = MagicMock()
    mock_client.complete_json.side_effect = ValueError("LLM error")

    results = extract_chapter(mock_client, ch, "Book", "Author")
    assert len(results) == 1
    assert "[EXTRACTION FAILED]" in results[0].topic_sentence


def test_extract_chapter_batching():
    """Large chapters should be batched correctly."""
    from ppke.pipeline.extractor import extract_chapter

    ch = Chapter(number=1, title="Intro")
    ch.paragraphs = [
        Paragraph(chapter_number=1, paragraph_number=i, text=f"Para {i}")
        for i in range(1, 8)  # 7 paragraphs
    ]

    mock_client = MagicMock()

    def make_response(paras):
        return [{"paragraph_id": p.paragraph_id, "topic_sentence": "T"} for p in paras]

    call_count = [0]

    def side_effect(system, user):
        call_count[0] += 1
        return make_response([])  # simplified

    mock_client.complete_json.side_effect = [
        [{"paragraph_id": p.paragraph_id, "topic_sentence": "T"} for p in ch.paragraphs[:3]],
        [{"paragraph_id": p.paragraph_id, "topic_sentence": "T"} for p in ch.paragraphs[3:6]],
        [{"paragraph_id": p.paragraph_id, "topic_sentence": "T"} for p in ch.paragraphs[6:]],
    ]

    results = extract_chapter(mock_client, ch, "Book", "Author", batch_size=3)
    assert mock_client.complete_json.call_count == 3


# ── Pipeline: Logical Map ─────────────────────────────────────────────────────


def test_extraction_to_summary_omits_empty():
    from ppke.pipeline.logical_map import _extraction_to_summary
    ext = ExtractionResult(paragraph_id="{01}.p1", original_text="")
    result = json.loads(_extraction_to_summary([ext]))
    assert len(result) == 1
    assert "paragraph_id" in result[0]
    # empty fields omitted
    assert "topic_sentence" not in result[0]


def test_extraction_to_summary_includes_fields():
    from ppke.pipeline.logical_map import _extraction_to_summary
    ext = _make_extraction()
    result = json.loads(_extraction_to_summary([ext]))
    assert result[0]["topic_sentence"] == "A topic"
    assert result[0]["claims"] == ["Claim A"]
    assert result[0]["concepts"] == ["Concept X"]


def test_build_logical_map_success():
    from ppke.pipeline.logical_map import build_logical_map
    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "central_thesis": {"claim": "Main claim", "paragraph_ids": ["{01}.p1"]},
        "argument_threads": [],
    }
    result = build_logical_map(mock_client, [_make_extraction()], "Book", "Author")
    assert result["central_thesis"]["claim"] == "Main claim"


def test_build_logical_map_failure_returns_error_dict():
    from ppke.pipeline.logical_map import build_logical_map
    mock_client = MagicMock()
    mock_client.complete_json.side_effect = ValueError("API error")
    result = build_logical_map(mock_client, [_make_extraction()], "Book", "Author")
    assert "error" in result
    assert result["central_thesis"]["claim"] == "[ANALYSIS FAILED]"


# ── Pipeline: Concept Indexer ─────────────────────────────────────────────────


def test_extraction_to_concept_input_skips_empty():
    from ppke.pipeline.concepts import _extraction_to_concept_input
    # Paragraph with no concepts or claims should be skipped
    ext = ExtractionResult(paragraph_id="{01}.p1", original_text="text")
    result = json.loads(_extraction_to_concept_input([ext]))
    assert result == []


def test_extraction_to_concept_input_includes_relevant():
    from ppke.pipeline.concepts import _extraction_to_concept_input
    ext = _make_extraction()
    result = json.loads(_extraction_to_concept_input([ext]))
    assert len(result) == 1
    assert result[0]["concepts"] == ["Concept X"]
    assert result[0]["claims"] == ["Claim A"]


def test_merge_concept_results_merges_duplicates():
    from ppke.pipeline.concepts import _merge_concept_results
    results = [
        {"concepts": [{"name": "Dasein", "definition": "short", "occurrences": [{"pid": "1"}],
                       "semantic_shifts": [], "related_concepts": ["Being"]}]},
        {"concepts": [{"name": "Dasein", "definition": "longer definition here",
                       "occurrences": [{"pid": "2"}],
                       "semantic_shifts": [{"shift": "x"}], "related_concepts": ["Being", "Time"]}]},
    ]
    merged = _merge_concept_results(results)
    assert len(merged["concepts"]) == 1
    dasein = merged["concepts"][0]
    assert len(dasein["occurrences"]) == 2
    assert dasein["definition"] == "longer definition here"
    assert "Time" in dasein["related_concepts"]
    assert len(dasein["related_concepts"]) == 2  # deduped


def test_build_concept_index_no_relevant_paragraphs():
    from ppke.pipeline.concepts import build_concept_index
    # Extraction with no concepts or claims
    ext = ExtractionResult(paragraph_id="{01}.p1", original_text="text")
    mock_client = MagicMock()
    result = build_concept_index(mock_client, [ext], "Book", "Author")
    assert result == {"concepts": []}
    mock_client.complete_json.assert_not_called()


def test_build_concept_index_success():
    from ppke.pipeline.concepts import build_concept_index
    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "concepts": [{"name": "Dasein", "definition": "Being-there",
                      "occurrences": [], "semantic_shifts": [], "related_concepts": []}]
    }
    result = build_concept_index(mock_client, [_make_extraction()], "Book", "Author")
    assert len(result["concepts"]) == 1


def test_build_concept_index_failure():
    from ppke.pipeline.concepts import build_concept_index
    mock_client = MagicMock()
    mock_client.complete_json.side_effect = ValueError("LLM error")
    result = build_concept_index(mock_client, [_make_extraction()], "Book", "Author")
    assert "error" in result


# ── Pipeline: Pattern Detector ────────────────────────────────────────────────


def test_extraction_to_pattern_input():
    from ppke.pipeline.patterns import _extraction_to_pattern_input
    ext = _make_extraction()
    result = json.loads(_extraction_to_pattern_input([ext]))
    assert result[0]["tone"] == "neutral"
    assert result[0]["claims"] == ["Claim A"]
    assert result[0]["function"] == "premise"


def test_extraction_to_pattern_input_omits_empty_fields():
    from ppke.pipeline.patterns import _extraction_to_pattern_input
    ext = ExtractionResult(paragraph_id="{01}.p1", original_text="text")
    result = json.loads(_extraction_to_pattern_input([ext]))
    assert "tone" not in result[0]
    assert "claims" not in result[0]


def test_merge_pattern_results():
    from ppke.pipeline.patterns import _merge_pattern_results
    results = [
        {"patterns": [{"type": "metaphor", "description": "A"}]},
        {"patterns": [{"type": "contradiction", "description": "B"}]},
    ]
    merged = _merge_pattern_results(results)
    assert len(merged["patterns"]) == 2


def test_detect_patterns_empty_extractions():
    from ppke.pipeline.patterns import detect_patterns
    mock_client = MagicMock()
    result = detect_patterns(mock_client, [], "Book", "Author")
    assert result == {"patterns": []}
    mock_client.complete_json.assert_not_called()


def test_detect_patterns_success():
    from ppke.pipeline.patterns import detect_patterns
    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "patterns": [{"type": "metaphor", "description": "Light/dark"}]
    }
    result = detect_patterns(mock_client, [_make_extraction()], "Book", "Author")
    assert len(result["patterns"]) == 1


def test_detect_patterns_failure():
    from ppke.pipeline.patterns import detect_patterns
    mock_client = MagicMock()
    mock_client.complete_json.side_effect = ValueError("LLM error")
    result = detect_patterns(mock_client, [_make_extraction()], "Book", "Author")
    assert "error" in result


def test_detect_patterns_chunking():
    from ppke.pipeline.patterns import detect_patterns
    """35 extractions should produce 2 chunks."""
    extractions = [
        ExtractionResult(paragraph_id=f"{{01}}.p{i}", original_text=f"para {i}")
        for i in range(1, 36)
    ]
    mock_client = MagicMock()
    mock_client.complete_json.return_value = {"patterns": []}
    detect_patterns(mock_client, extractions, "Book", "Author")
    assert mock_client.complete_json.call_count == 2


# ── Pipeline: Synthesizer ─────────────────────────────────────────────────────


def test_discover_books_empty_vault(tmp_path):
    from ppke.pipeline.synthesizer import discover_books
    result = discover_books(tmp_path)
    assert result == []


def test_discover_books_nonexistent_vault(tmp_path):
    from ppke.pipeline.synthesizer import discover_books
    result = discover_books(tmp_path / "nonexistent")
    assert result == []


def test_discover_books_finds_books(tmp_path):
    from ppke.pipeline.synthesizer import discover_books
    for name, title in [("Book_A_Author_2020", "Book A"), ("Book_B_Author_2021", "Book B")]:
        d = tmp_path / name
        d.mkdir()
        (d / "meta.yml").write_text(
            yaml.dump({"title": title, "author": "Author"})
        )
    result = discover_books(tmp_path)
    assert len(result) == 2
    titles = {r["title"] for r in result}
    assert "Book A" in titles
    assert "Book B" in titles


def test_discover_books_loads_analysis_files(tmp_path):
    from ppke.pipeline.synthesizer import discover_books
    d = tmp_path / "Book_Test_Author_2024"
    d.mkdir()
    (d / "meta.yml").write_text(yaml.dump({"title": "T", "author": "A"}))
    (d / "02_Logical_Map.md").write_text("logical content")
    (d / "03_Concept_Index.md").write_text("concept content")
    (d / "04_Author_Model.md").write_text("author content")
    result = discover_books(tmp_path)
    assert result[0]["logical_map"] == "logical content"
    assert result[0]["concept_index"] == "concept content"
    assert result[0]["author_model"] == "author content"


def test_cross_book_synthesis_too_few_books(tmp_path):
    from ppke.pipeline.synthesizer import cross_book_synthesis
    mock_client = MagicMock()
    # Only 1 book
    d = tmp_path / "Book_Test_Author_2024"
    d.mkdir()
    (d / "meta.yml").write_text(yaml.dump({"title": "T", "author": "A"}))

    result = cross_book_synthesis(mock_client, tmp_path)
    assert "error" in result
    assert "Need at least 2" in result["error"]


def test_cross_book_synthesis_success(tmp_path):
    from ppke.pipeline.synthesizer import cross_book_synthesis

    for name in ["Book_A_Author_2020", "Book_B_Author_2021"]:
        d = tmp_path / name
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": name, "author": "A"}))
        (d / "03_Concept_Index.md").write_text("concepts")
        (d / "02_Logical_Map.md").write_text("map")
        (d / "04_Author_Model.md").write_text("model")

    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "comparisons": [],
        "cross_links": [],
        "overall_synthesis": "They agree on X",
    }

    result = cross_book_synthesis(mock_client, tmp_path, question="How do they differ?")
    assert result["overall_synthesis"] == "They agree on X"


def test_cross_book_synthesis_llm_failure(tmp_path):
    from ppke.pipeline.synthesizer import cross_book_synthesis

    for name in ["Book_A_Author_2020", "Book_B_Author_2021"]:
        d = tmp_path / name
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": name, "author": "A"}))

    mock_client = MagicMock()
    mock_client.complete_json.side_effect = ValueError("LLM error")

    result = cross_book_synthesis(mock_client, tmp_path)
    assert "error" in result


# ── CLI: list command ─────────────────────────────────────────────────────────


def test_list_command_no_books(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        tmp_path.mkdir(exist_ok=True)
        result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "No books ingested" in result.output


def test_list_command_with_books(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    meta = {"title": "Test Book", "author": "Test Author", "year": 2024,
            "total_chapters": 3, "total_paragraphs": 15, "verification_status": "COMPLETE"}
    (book_dir / "meta.yml").write_text(yaml.dump(meta))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["list"])

    assert result.exit_code == 0
    assert "Test Book" in result.output
    assert "COMPLETE" in result.output


def test_list_command_vault_missing(tmp_path):
    runner = CliRunner()
    missing = tmp_path / "nonexistent_vault"
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=missing)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["list"])
    assert result.exit_code != 0


def test_list_command_book_without_meta(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    # No meta.yml

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["list"])

    assert result.exit_code == 0
    assert "Book_Test_Author_2024" in result.output


# ── CLI: stats command ────────────────────────────────────────────────────────


def test_stats_command(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    meta = {"title": "T", "author": "A", "total_chapters": 2,
            "total_paragraphs": 5, "verification_status": "COMPLETE"}
    (book_dir / "meta.yml").write_text(yaml.dump(meta))
    (book_dir / "05_Coverage_Report.md").write_text(
        "- **processed_paragraphs_count:** 5\n"
    )
    (book_dir / "03_Concept_Index.md").write_text("## Concept1\n\n## Concept2\n")
    (book_dir / "06_Patterns.md").write_text("### 1. Pattern A\n### 2. Pattern B\n")

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["stats"])

    assert result.exit_code == 0
    assert "Books:" in result.output
    assert "Concepts:" in result.output


def test_stats_command_vault_missing(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path / "missing")
        mock_load.return_value = cfg
        result = runner.invoke(main, ["stats"])
    assert result.exit_code != 0


def test_stats_command_with_checkpoints(tmp_path):
    runner = CliRunner()
    # Create a checkpoint file in the vault
    (tmp_path / ".checkpoint_Book_Test_Author_2024.json").write_text("{}")

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["stats"])
    assert result.exit_code == 0
    assert "checkpoint" in result.output.lower()


def test_stats_fallback_coverage_format(tmp_path):
    """Test stats with YAML-style processed_paragraphs_count format."""
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    meta = {"total_chapters": 1, "total_paragraphs": 3, "verification_status": "COMPLETE"}
    (book_dir / "meta.yml").write_text(yaml.dump(meta))
    # YAML style (no bold)
    (book_dir / "05_Coverage_Report.md").write_text(
        "processed_paragraphs_count: 3\n"
    )

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["stats"])
    assert result.exit_code == 0


# ── CLI: search command ───────────────────────────────────────────────────────


def test_search_command_finds_result(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    extractions = [{
        "paragraph_id": "{01}.p1",
        "original_text": "The concept of Dasein is central.",
        "topic_sentence": "Introduction",
        "explicit_claims": [],
        "defined_concepts": ["Dasein"],
    }]
    (book_dir / "extractions.json").write_text(json.dumps(extractions))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "Dasein"])

    assert result.exit_code == 0
    assert "Dasein" in result.output


def test_search_command_no_results(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    extractions = [{"paragraph_id": "{01}.p1", "original_text": "Hello",
                    "topic_sentence": "", "explicit_claims": [], "defined_concepts": []}]
    (book_dir / "extractions.json").write_text(json.dumps(extractions))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "Nonexistent"])

    assert result.exit_code == 0
    assert "No results" in result.output


def test_search_command_vault_missing(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path / "missing")
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "anything"])
    assert result.exit_code != 0


def test_search_command_specific_book(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    extractions = [{"paragraph_id": "{01}.p1", "original_text": "Freedom is key.",
                    "topic_sentence": "freedom", "explicit_claims": [], "defined_concepts": []}]
    (book_dir / "extractions.json").write_text(json.dumps(extractions))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "Freedom",
                                      "--book", "Book_Test_Author_2024"])

    assert result.exit_code == 0
    assert "Freedom" in result.output


def test_search_command_no_books(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "anything"])
    assert result.exit_code == 0
    assert "No books found" in result.output


def test_search_finds_in_topic(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    extractions = [{"paragraph_id": "{01}.p1", "original_text": "unrelated",
                    "topic_sentence": "freedom of will", "explicit_claims": [],
                    "defined_concepts": []}]
    (book_dir / "extractions.json").write_text(json.dumps(extractions))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "freedom"])
    assert result.exit_code == 0
    assert "freedom" in result.output.lower()


def test_search_finds_in_claims(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    extractions = [{"paragraph_id": "{01}.p1", "original_text": "unrelated",
                    "topic_sentence": "something else",
                    "explicit_claims": ["existence precedes essence"],
                    "defined_concepts": []}]
    (book_dir / "extractions.json").write_text(json.dumps(extractions))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "existence"])
    assert result.exit_code == 0
    assert "existence" in result.output.lower()


def test_search_max_results(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    extractions = [
        {"paragraph_id": f"{{01}}.p{i}", "original_text": f"the word {i}",
         "topic_sentence": "word", "explicit_claims": [], "defined_concepts": []}
        for i in range(1, 20)
    ]
    (book_dir / "extractions.json").write_text(json.dumps(extractions))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "word", "--max-results", "3"])
    assert result.exit_code == 0
    assert "showing first 3" in result.output


def test_search_corrupted_extractions(tmp_path):
    """Corrupted extractions.json should be silently skipped."""
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    (book_dir / "extractions.json").write_text("not valid json{{{")

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["search", "anything"])
    assert result.exit_code == 0


# ── CLI: cross-query command ──────────────────────────────────────────────────


def test_cross_query_too_few_books(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    (book_dir / "meta.yml").write_text(yaml.dump({"title": "T", "author": "A"}))

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"):
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, ["cross-query", "--question", "How?"])
    assert result.exit_code != 0


def test_cross_query_success(tmp_path):
    runner = CliRunner()
    for name in ["Book_A_Author_2020", "Book_B_Author_2021"]:
        d = tmp_path / name
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": name, "author": "A"}))

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.pipeline.synthesizer.cross_book_synthesis") as mock_synth:
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        mock_synth.return_value = {
            "comparisons": [
                {"dimension": "Ontology", "description": "Desc",
                 "per_book": [{"book_folder": "Book_A", "position": "Pos A"}],
                 "tensions": ["Tension 1"]}
            ],
            "cross_links": [
                {"concept": "Freedom", "relationship": "contrasts", "books": ["A", "B"],
                 "description": "They differ"}
            ],
            "overall_synthesis": "General synthesis here",
        }
        result = runner.invoke(main, ["cross-query", "--question", "How do they differ?"])

    assert result.exit_code == 0
    assert "Ontology" in result.output
    assert "General synthesis here" in result.output


def test_cross_query_error_from_synthesis(tmp_path):
    runner = CliRunner()
    for name in ["Book_A_Author_2020", "Book_B_Author_2021"]:
        d = tmp_path / name
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": name, "author": "A"}))

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.pipeline.synthesizer.cross_book_synthesis") as mock_synth:
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        mock_synth.return_value = {"error": "LLM failed"}
        result = runner.invoke(main, ["cross-query", "--question", "How?"])
    assert result.exit_code != 0


# ── CLI: config --show ────────────────────────────────────────────────────────


def test_config_show(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(provider="deepseek", deepseek_api_key="k"))
        mock_load.return_value = cfg
        result = runner.invoke(main, ["config", "--show"])
    assert result.exit_code == 0
    assert "deepseek" in result.output
    assert "API key set" in result.output
    assert "yes" in result.output


def test_config_update_model(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.config.Config.save") as mock_save:
        cfg = Config(llm=LLMConfig())
        mock_load.return_value = cfg
        result = runner.invoke(main, ["config", "--model", "gpt-4-turbo"])
    assert result.exit_code == 0
    assert mock_save.called


def test_config_update_vault_path(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.config.Config.save"):
        cfg = Config(llm=LLMConfig())
        mock_load.return_value = cfg
        result = runner.invoke(main, ["config", "--vault-path", str(tmp_path)])
    assert result.exit_code == 0


# ── CLI: parse command ────────────────────────────────────────────────────────


def test_parse_command(tmp_path):
    runner = CliRunner()
    md = tmp_path / "book.md"
    md.write_text("# Chapter 1\n\nHello world.\n\n# Chapter 2\n\nSecond chapter.")

    result = runner.invoke(main, ["parse", str(md),
                                  "--title", "Test Book", "--author", "Author"])
    assert result.exit_code == 0
    assert "Test Book" in result.output
    assert "Chapters: 2" in result.output


def test_parse_command_single_chapter(tmp_path):
    runner = CliRunner()
    md = tmp_path / "book.md"
    md.write_text("Just some text.\n\nAnother paragraph.")

    result = runner.invoke(main, ["parse", str(md)])
    assert result.exit_code == 0


# ── CLI: query command errors ─────────────────────────────────────────────────


def test_query_book_not_found(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"):
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
        mock_load.return_value = cfg
        tmp_path.mkdir(exist_ok=True)
        result = runner.invoke(main, ["query",
                                      "--book", "Book_Nonexistent",
                                      "--question", "What?"])
    assert result.exit_code != 0


def test_query_llm_error(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    (book_dir / "meta.yml").write_text(yaml.dump({"title": "T", "author": "A"}))

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.llm.client.LLMClient.complete_json") as mock_cj:
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
        mock_load.return_value = cfg
        mock_cj.side_effect = ValueError("LLM Error")
        result = runner.invoke(main, ["query",
                                      "--book", "Book_Test_Author_2024",
                                      "--question", "What?"])
    assert result.exit_code != 0


# ── CLI: re-read command ──────────────────────────────────────────────────────


def test_reread_invalid_chapter_numbers(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test"
    book_dir.mkdir()

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"):
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
        mock_load.return_value = cfg
        result = runner.invoke(main, ["re-read",
                                      "--book", "Book_Test",
                                      "--chapters", "a,b,c"])
    assert result.exit_code != 0


def test_reread_book_not_found(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"):
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="k"))
        mock_load.return_value = cfg
        result = runner.invoke(main, ["re-read",
                                      "--book", "Book_Nonexistent",
                                      "--chapters", "1"])
    assert result.exit_code != 0


# ── CLI: main (first run behavior) ────────────────────────────────────────────


def test_main_shows_help_when_configured():
    runner = CliRunner()
    with patch("ppke.cli.is_first_run", return_value=False):
        result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "Usage:" in result.output or "PPKE" in result.output


def test_main_runs_init_on_first_run():
    runner = CliRunner()
    with patch("ppke.cli.is_first_run", return_value=True), \
         patch("ppke.cli.save_env_file"), \
         patch("ppke.config.Config.save"), \
         patch("ppke.config.Config.load", return_value=Config()):
        result = runner.invoke(main, [],
                               input="anthropic\nclaude-sonnet-4-20250514\nsk-test\n/tmp/vault\n5\n")
    assert result.exit_code == 0
    assert "Setup" in result.output
