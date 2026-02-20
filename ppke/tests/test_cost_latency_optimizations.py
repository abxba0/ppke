"""Tests for cost/latency optimizations: two-tier LLM, prompt caching,
parallel analysis, skip logic, citation stripping, and audit fixes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ppke.config import (
    Config,
    LLMConfig,
    PROVIDER_SMALL_MODEL_DEFAULTS,
)
from ppke.llm.client import LLMClient
from ppke.parser.models import (
    Book,
    Chapter,
    DepthLevel,
    ExtractionResult,
    Paragraph,
)
from ppke.pipeline.extractor import (
    extract_chapter,
    strip_citations,
)
from ppke.pipeline.orchestrator import _is_low_information, _is_skip_chapter, _extract_with_retry
from ppke.pipeline.validator import (
    LOW_INFORMATION_MARKER,
    validate_chapter_coverage,
    validate_coverage,
)


# ── Two-Tier LLM Architecture ──


class TestTwoTierLLM:
    def test_llm_config_small_model_default_none(self):
        cfg = LLMConfig()
        assert cfg.small_model is None

    def test_effective_small_model_uses_provider_default(self):
        cfg = LLMConfig(provider="anthropic")
        assert cfg.effective_small_model == PROVIDER_SMALL_MODEL_DEFAULTS["anthropic"]
        assert cfg.effective_small_model == "claude-3-haiku-20240307"

    def test_effective_small_model_openai(self):
        cfg = LLMConfig(provider="openai")
        assert cfg.effective_small_model == "gpt-4o-mini"

    def test_effective_small_model_deepseek(self):
        cfg = LLMConfig(provider="deepseek")
        assert cfg.effective_small_model == "deepseek-chat"

    def test_effective_small_model_gemini(self):
        cfg = LLMConfig(provider="gemini")
        assert cfg.effective_small_model == "gemini-1.5-flash"

    def test_effective_small_model_explicit_override(self):
        cfg = LLMConfig(provider="anthropic", small_model="claude-3-5-haiku-20241022")
        assert cfg.effective_small_model == "claude-3-5-haiku-20241022"

    def test_effective_small_model_unknown_provider_falls_back_to_model(self):
        cfg = LLMConfig(provider="unknown_provider", model="custom-model")
        assert cfg.effective_small_model == "custom-model"

    def test_config_save_load_small_model(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        cfg = Config(llm=LLMConfig(small_model="custom-small"))
        cfg.save(cfg_path)

        loaded = Config.load(cfg_path)
        assert loaded.llm.small_model == "custom-small"

    def test_config_save_load_no_small_model(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        cfg = Config(llm=LLMConfig())
        cfg.save(cfg_path)

        loaded = Config.load(cfg_path)
        assert loaded.llm.small_model is None

    def test_config_save_includes_null_small_model(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        cfg = Config(llm=LLMConfig())
        cfg.save(cfg_path)

        data = json.loads(cfg_path.read_text())
        assert "small_model" in data["llm"]
        assert data["llm"]["small_model"] is None


class TestModelOverride:
    def test_complete_passes_model_override(self):
        cfg = LLMConfig(provider="anthropic", model="main-model", anthropic_api_key="k")
        client = LLMClient(cfg)

        mock_content = MagicMock()
        mock_content.text = "response"
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_ant = MagicMock()
        mock_ant.messages.create.return_value = mock_response
        client._anthropic_client = mock_ant

        client.complete("sys", "usr", model_override="small-model")
        kwargs = mock_ant.messages.create.call_args[1]
        assert kwargs["model"] == "small-model"

    def test_complete_uses_default_model_when_no_override(self):
        cfg = LLMConfig(provider="anthropic", model="main-model", anthropic_api_key="k")
        client = LLMClient(cfg)

        mock_content = MagicMock()
        mock_content.text = "response"
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_ant = MagicMock()
        mock_ant.messages.create.return_value = mock_response
        client._anthropic_client = mock_ant

        client.complete("sys", "usr")
        kwargs = mock_ant.messages.create.call_args[1]
        assert kwargs["model"] == "main-model"

    def test_complete_json_passes_model_override(self):
        cfg = LLMConfig(provider="anthropic", model="main-model", anthropic_api_key="k")
        client = LLMClient(cfg)

        mock_content = MagicMock()
        mock_content.text = '{"key": "value"}'
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_ant = MagicMock()
        mock_ant.messages.create.return_value = mock_response
        client._anthropic_client = mock_ant

        result = client.complete_json("sys", "usr", model_override="cheap-model")
        assert result == {"key": "value"}
        kwargs = mock_ant.messages.create.call_args[1]
        assert kwargs["model"] == "cheap-model"

    def test_extract_chapter_passes_model_override(self):
        cfg = LLMConfig(provider="anthropic", model="main", anthropic_api_key="k")
        client = LLMClient(cfg)

        chapter = Chapter(number=1, title="Ch1")
        chapter.paragraphs = [
            Paragraph(chapter_number=1, paragraph_number=1, text="This is a substantive philosophical paragraph about existence.")
        ]

        mock_response = [{"paragraph_id": "{01}.p1", "topic_sentence": "Existence", "is_argument_carrying": True}]

        with patch.object(client, "complete_json", return_value=mock_response) as mock_cj:
            extract_chapter(client, chapter, "Book", "Author", model_override="small-model")
            mock_cj.assert_called_once()
            _, kwargs = mock_cj.call_args
            assert kwargs["model_override"] == "small-model"


# ── Prompt Caching ──


class TestPromptCaching:
    def test_anthropic_sends_structured_system_block(self):
        cfg = LLMConfig(provider="anthropic", anthropic_api_key="k")
        client = LLMClient(cfg)

        mock_content = MagicMock()
        mock_content.text = "response"
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_ant = MagicMock()
        mock_ant.messages.create.return_value = mock_response
        client._anthropic_client = mock_ant

        client.complete("system prompt text", "user prompt")
        kwargs = mock_ant.messages.create.call_args[1]

        system_block = kwargs["system"]
        assert isinstance(system_block, list)
        assert len(system_block) == 1
        assert system_block[0]["type"] == "text"
        assert system_block[0]["text"] == "system prompt text"
        assert system_block[0]["cache_control"] == {"type": "ephemeral"}


# ── Skip Logic (_is_low_information) ──


class TestLowInformation:
    def test_empty_string(self):
        assert _is_low_information("") is True

    def test_whitespace_only(self):
        assert _is_low_information("   ") is True

    def test_single_digit(self):
        assert _is_low_information("42") is True

    def test_roman_numeral(self):
        assert _is_low_information("xiv") is True
        assert _is_low_information("III") is True

    def test_short_single_word(self):
        assert _is_low_information("p.") is True
        assert _is_low_information("v") is True

    def test_boilerplate_prefix(self):
        assert _is_low_information("Copyright 2024 Publisher") is True
        assert _is_low_information("ISBN 978-0-123456-47-2") is True
        assert _is_low_information("Published by Oxford Press") is True
        assert _is_low_information("All rights reserved.") is True
        assert _is_low_information("Table of Contents") is True
        assert _is_low_information("About the author and works") is True

    def test_substantive_text(self):
        assert _is_low_information("The concept of being is central to Heidegger.") is False

    def test_multi_word_substantive(self):
        assert _is_low_information("Kant argues for the possibility of synthetic a priori judgments.") is False

    def test_single_word_always_low_info(self):
        # Any single word is low-information (≤ _LOW_INFO_MAX_WORDS=1)
        assert _is_low_information("Phenomenology") is True
        assert _is_low_information("Introduction") is True

    def test_extract_with_retry_skips_low_information(self):
        """Skip logic is in orchestrator's _extract_with_retry, not in extract_chapter."""
        cfg = LLMConfig(provider="anthropic", anthropic_api_key="k")
        client = LLMClient(cfg)

        chapter = Chapter(number=1, title="Ch1")
        chapter.paragraphs = [
            Paragraph(chapter_number=1, paragraph_number=1, text="42"),
            Paragraph(chapter_number=1, paragraph_number=2, text="This is a substantive paragraph about philosophy."),
        ]

        mock_response = [{"paragraph_id": "{01}.p2", "topic_sentence": "Philosophy", "is_argument_carrying": True}]

        with patch.object(client, "complete_json", return_value=mock_response):
            results = _extract_with_retry(
                client, chapter, "Book", "Author", batch_size=5, progress=None,
            )

        assert len(results) == 2
        low_info = [r for r in results if r.topic_sentence == "[LOW INFORMATION]"]
        assert len(low_info) == 1
        assert low_info[0].paragraph_id == "{01}.p1"

    def test_extract_with_retry_all_low_information(self):
        """When all paragraphs are low-info, no LLM calls should be made."""
        cfg = LLMConfig(provider="anthropic", anthropic_api_key="k")
        client = LLMClient(cfg)

        chapter = Chapter(number=1, title="Ch1")
        chapter.paragraphs = [
            Paragraph(chapter_number=1, paragraph_number=1, text="42"),
            Paragraph(chapter_number=1, paragraph_number=2, text="III"),
        ]

        with patch.object(client, "complete_json") as mock_cj:
            results = _extract_with_retry(
                client, chapter, "Book", "Author", batch_size=5, progress=None,
            )
            # No LLM calls should be made
            mock_cj.assert_not_called()

        assert len(results) == 2
        assert all(r.topic_sentence == "[LOW INFORMATION]" for r in results)


# ── Citation Stripping ──


class TestCitationStripping:
    def test_strip_footnote_markers(self):
        text = "Kant argues[^1] for synthetic a priori[^23] judgments."
        result = strip_citations(text)
        assert "[^" not in result
        assert "Kant argues" in result

    def test_strip_see_citations(self):
        text = "This is established (See Kant, 1781) in the literature."
        result = strip_citations(text)
        assert "(See Kant" not in result

    def test_strip_author_year(self):
        text = "As noted (Smith, 2020b) and (Hegel, 1807) earlier."
        result = strip_citations(text)
        assert "(Smith" not in result
        assert "(Hegel" not in result

    def test_strip_ibid(self):
        text = "As shown (ibid.) in the previous chapter."
        result = strip_citations(text)
        assert "(ibid" not in result

    def test_strip_numeric_refs(self):
        text = "According to [1] and [23] these findings hold."
        result = strip_citations(text)
        assert "[1]" not in result
        assert "[23]" not in result

    def test_preserves_prose(self):
        text = "The concept of Dasein is central to Being and Time."
        result = strip_citations(text)
        assert result == text

    def test_collapses_double_spaces(self):
        text = "First [^1] then [^2] finally."
        result = strip_citations(text)
        assert "  " not in result


# ── Stop Word Chapter Detection ──


class TestStopWordDetection:
    def test_bibliography_detected(self):
        assert _is_skip_chapter("Bibliography") is True

    def test_index_detected(self):
        assert _is_skip_chapter("Index") is True

    def test_appendix_detected(self):
        assert _is_skip_chapter("Appendix") is True

    def test_references_detected(self):
        assert _is_skip_chapter("References") is True

    def test_glossary_detected(self):
        assert _is_skip_chapter("Glossary") is True

    def test_case_insensitive(self):
        assert _is_skip_chapter("BIBLIOGRAPHY") is True
        assert _is_skip_chapter("bibliography") is True

    def test_normal_chapter_not_skipped(self):
        assert _is_skip_chapter("The Critique of Pure Reason") is False

    def test_whitespace_stripped(self):
        assert _is_skip_chapter("  Index  ") is True


# ── DepthLevel.SKIP ──


class TestDepthLevelSkip:
    def test_skip_value(self):
        assert DepthLevel.SKIP.value == "skip"

    def test_skip_in_extraction_result(self):
        result = ExtractionResult(
            paragraph_id="test", original_text="x",
            depth=DepthLevel.SKIP,
        )
        assert result.depth == DepthLevel.SKIP


# ── Validator: Low-information handling ──


class TestValidatorLowInfo:
    def test_low_info_counts_as_processed(self):
        book = Book(title="T", author="A")
        ch = Chapter(number=1, title="Ch1")
        ch.paragraphs = [
            Paragraph(chapter_number=1, paragraph_number=1, text="42"),
            Paragraph(chapter_number=1, paragraph_number=2, text="Substance."),
        ]
        book.chapters = [ch]

        results = [
            ExtractionResult(
                paragraph_id="{01}.p1", original_text="42",
                topic_sentence=LOW_INFORMATION_MARKER,
                depth=DepthLevel.SKIP,
            ),
            ExtractionResult(
                paragraph_id="{01}.p2", original_text="Substance.",
                topic_sentence="Substance discussion.",
                depth=DepthLevel.FULL,
            ),
        ]

        report = validate_coverage(book, results)
        assert report.verification_status == "COMPLETE"
        assert report.processed_paragraph_count == 2
        assert "Low-information paragraphs skipped: 1" in report.notes

    def test_chapter_coverage_low_info_counts_as_processed(self):
        pids = ["{01}.p1", "{01}.p2"]
        results = [
            ExtractionResult(
                paragraph_id="{01}.p1", original_text="42",
                topic_sentence=LOW_INFORMATION_MARKER,
            ),
            ExtractionResult(
                paragraph_id="{01}.p2", original_text="Real text.",
                topic_sentence="Topic sentence.",
            ),
        ]
        is_complete, missing = validate_chapter_coverage(1, pids, results)
        assert is_complete is True
        assert missing == []


# ── CLI: --small-model flag ──


class TestConfigSmallModelFlag:
    def test_config_show_displays_small_model(self, tmp_path):
        runner = CliRunner()
        cfg = Config(llm=LLMConfig(small_model="claude-3-haiku-20240307"))
        cfg_path = tmp_path / "config.json"
        cfg.save(cfg_path)

        from ppke.cli import main

        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["config", "--show"])
            assert result.exit_code == 0
            assert "claude-3-haiku-20240307" in result.output

    def test_config_show_auto_small_model(self, tmp_path):
        runner = CliRunner()
        cfg = Config(llm=LLMConfig())

        from ppke.cli import main

        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["config", "--show"])
            assert result.exit_code == 0
            assert "(default:" in result.output

    def test_config_set_small_model(self, tmp_path):
        runner = CliRunner()
        cfg = Config()
        cfg_path = tmp_path / "config.json"

        from ppke.cli import main

        with patch("ppke.cli.Config.load", return_value=cfg), \
             patch.object(cfg, "save"):
            result = runner.invoke(main, ["config", "--small-model", "gpt-4o-mini"])
            assert result.exit_code == 0
            assert cfg.llm.small_model == "gpt-4o-mini"


# ── Gemini model override ──


class TestGeminiModelOverride:
    def test_gemini_uses_fresh_model_on_override(self):
        cfg = LLMConfig(provider="gemini", model="gemini-1.5-pro", gemini_api_key="k")
        client = LLMClient(cfg)

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "response"
        mock_model.generate_content.return_value = mock_response
        client._gemini_client = mock_model

        with patch.dict("sys.modules", {"google.generativeai": MagicMock()}) as _:
            import google.generativeai as mock_genai
            mock_fresh = MagicMock()
            mock_fresh.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_fresh
            mock_genai.GenerationConfig.return_value = MagicMock()

            result = client.complete("sys", "usr", model_override="gemini-1.5-flash")
            assert result == "response"
            mock_genai.GenerativeModel.assert_called_with("gemini-1.5-flash")

    def test_gemini_uses_cached_model_without_override(self):
        cfg = LLMConfig(provider="gemini", model="gemini-1.5-pro", gemini_api_key="k")
        client = LLMClient(cfg)

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "response"
        mock_model.generate_content.return_value = mock_response
        client._gemini_client = mock_model

        with patch.dict("sys.modules", {"google.generativeai": MagicMock()}) as _:
            import google.generativeai as mock_genai
            mock_genai.GenerationConfig.return_value = MagicMock()

            result = client.complete("sys", "usr")
            assert result == "response"
            # Should use the cached model
            mock_model.generate_content.assert_called_once()
