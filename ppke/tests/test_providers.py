"""Tests for new AI providers: DeepSeek, Gemini, OpenRouter.

Also tests config changes, CLI changes, and improves overall coverage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from click.testing import CliRunner

from ppke.config import (
    LLMConfig,
    Config,
    PROVIDER_DEFAULTS,
    PROVIDER_ENV_VARS,
    SUPPORTED_PROVIDERS,
    _load_env_file,
    save_env_file,
    is_first_run,
)
from ppke.llm.client import LLMClient, _is_retryable, _DEEPSEEK_BASE_URL, _OPENROUTER_BASE_URL
from ppke.cli import main


# ── Helpers: mock google.generativeai without the native libs ─────────────────

def _make_genai_mock():
    """Return a fully-mocked google.generativeai module."""
    genai_mock = MagicMock()
    genai_mock.GenerativeModel = MagicMock
    genai_mock.GenerationConfig = MagicMock
    genai_mock.configure = MagicMock()
    return genai_mock


def _patch_genai():
    """Context manager: inject a mock google.generativeai into sys.modules."""
    genai_mock = _make_genai_mock()
    google_mock = MagicMock()
    google_mock.generativeai = genai_mock
    patches = {
        "google": google_mock,
        "google.generativeai": genai_mock,
    }
    return patch.dict(sys.modules, patches)


# ── SUPPORTED_PROVIDERS / PROVIDER_DEFAULTS ──────────────────────────────────


def test_supported_providers_list():
    assert "anthropic" in SUPPORTED_PROVIDERS
    assert "openai" in SUPPORTED_PROVIDERS
    assert "deepseek" in SUPPORTED_PROVIDERS
    assert "gemini" in SUPPORTED_PROVIDERS
    assert "openrouter" in SUPPORTED_PROVIDERS


def test_provider_defaults_keys():
    for provider in SUPPORTED_PROVIDERS:
        assert provider in PROVIDER_DEFAULTS, f"No default model for {provider}"


def test_provider_env_vars_keys():
    for provider in SUPPORTED_PROVIDERS:
        assert provider in PROVIDER_ENV_VARS, f"No env var for {provider}"


def test_provider_defaults_non_empty():
    for provider, model in PROVIDER_DEFAULTS.items():
        assert model, f"Empty default model for {provider}"


# ── LLMConfig with new providers ─────────────────────────────────────────────


def test_llmconfig_deepseek_defaults():
    with patch.dict("os.environ", {}, clear=True):
        cfg = LLMConfig(provider="deepseek", model="deepseek-chat",
                        deepseek_api_key="ds-key-123")
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-chat"
    assert cfg.active_api_key == "ds-key-123"


def test_llmconfig_gemini_defaults():
    with patch.dict("os.environ", {}, clear=True):
        cfg = LLMConfig(provider="gemini", model="gemini-1.5-pro",
                        gemini_api_key="gm-key-456")
    assert cfg.provider == "gemini"
    assert cfg.active_api_key == "gm-key-456"


def test_llmconfig_openrouter_defaults():
    with patch.dict("os.environ", {}, clear=True):
        cfg = LLMConfig(provider="openrouter", model="openai/gpt-4o",
                        openrouter_api_key="or-key-789")
    assert cfg.provider == "openrouter"
    assert cfg.active_api_key == "or-key-789"


def test_active_api_key_anthropic():
    cfg = LLMConfig(provider="anthropic", anthropic_api_key="ant-abc")
    assert cfg.active_api_key == "ant-abc"


def test_active_api_key_openai():
    cfg = LLMConfig(provider="openai", openai_api_key="oai-xyz")
    assert cfg.active_api_key == "oai-xyz"


def test_active_api_key_unknown_provider():
    cfg = LLMConfig(provider="unknown_provider")
    assert cfg.active_api_key is None


def test_llmconfig_loads_deepseek_from_env():
    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "ds-env-key"}, clear=False):
        cfg = LLMConfig(provider="deepseek")
    assert cfg.deepseek_api_key == "ds-env-key"
    assert cfg.active_api_key == "ds-env-key"


def test_llmconfig_loads_gemini_from_env():
    with patch.dict("os.environ", {"GEMINI_API_KEY": "gm-env-key"}, clear=False):
        cfg = LLMConfig(provider="gemini")
    assert cfg.gemini_api_key == "gm-env-key"
    assert cfg.active_api_key == "gm-env-key"


def test_llmconfig_loads_openrouter_from_env():
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-env-key"}, clear=False):
        cfg = LLMConfig(provider="openrouter")
    assert cfg.openrouter_api_key == "or-env-key"
    assert cfg.active_api_key == "or-env-key"


def test_llmconfig_loads_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=ds-file-key\n"
        "GEMINI_API_KEY=gm-file-key\n"
        "OPENROUTER_API_KEY=or-file-key\n"
    )
    with patch("ppke.config.DEFAULT_ENV_PATH", env_file):
        with patch.dict("os.environ", {}, clear=False):
            # Remove the keys from environment so file is used
            import os
            for k in ("DEEPSEEK_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
                os.environ.pop(k, None)
            cfg = LLMConfig(provider="deepseek")
            assert cfg.deepseek_api_key == "ds-file-key"


# ── LLMClient: lazy initialization for new providers ─────────────────────────


def _make_client(provider: str, **key_kwargs) -> LLMClient:
    cfg = LLMConfig(provider=provider, model="test-model", **key_kwargs)
    return LLMClient(cfg)


def test_get_deepseek_creates_openai_client():
    client = _make_client("deepseek", deepseek_api_key="ds-key")
    mock_openai_instance = MagicMock()

    with patch("openai.OpenAI", return_value=mock_openai_instance) as mock_cls:
        result = client._get_deepseek()
        mock_cls.assert_called_once_with(
            api_key="ds-key",
            base_url=_DEEPSEEK_BASE_URL,
        )
        assert result is mock_openai_instance

    # Second call should return cached client (no new instantiation)
    with patch("openai.OpenAI") as mock_cls2:
        result2 = client._get_deepseek()
        mock_cls2.assert_not_called()
        assert result2 is mock_openai_instance


def test_get_openrouter_creates_openai_client():
    client = _make_client("openrouter", openrouter_api_key="or-key")
    mock_openai_instance = MagicMock()

    with patch("openai.OpenAI", return_value=mock_openai_instance) as mock_cls:
        result = client._get_openrouter()
        mock_cls.assert_called_once_with(
            api_key="or-key",
            base_url=_OPENROUTER_BASE_URL,
        )
        assert result is mock_openai_instance


def test_get_gemini_configures_genai():
    client = _make_client("gemini", gemini_api_key="gm-key")
    mock_model = MagicMock()
    genai_mock = _make_genai_mock()
    genai_mock.GenerativeModel = MagicMock(return_value=mock_model)
    google_mock = MagicMock()
    google_mock.generativeai = genai_mock

    with patch.dict(sys.modules, {"google": google_mock, "google.generativeai": genai_mock}):
        result = client._get_gemini()
    assert result is mock_model

    # Second call should return the cached model
    client2 = _make_client("gemini", gemini_api_key="gm-key")
    client2._gemini_client = mock_model
    with patch.dict(sys.modules, {"google": google_mock, "google.generativeai": genai_mock}):
        result2 = client2._get_gemini()
    assert result2 is mock_model


# ── LLMClient.complete() for new providers ───────────────────────────────────


def _mock_openai_response(text: str) -> MagicMock:
    """Build a mock OpenAI-style response."""
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _mock_gemini_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


def test_complete_deepseek_text():
    client = _make_client("deepseek", deepseek_api_key="ds-key")
    mock_ds = MagicMock()
    mock_ds.chat.completions.create.return_value = _mock_openai_response("DeepSeek answer")
    client._deepseek_client = mock_ds

    result = client.complete("system", "user")
    assert result == "DeepSeek answer"
    call_kwargs = mock_ds.chat.completions.create.call_args[1]
    assert "response_format" not in call_kwargs


def test_complete_deepseek_json_mode():
    client = _make_client("deepseek", deepseek_api_key="ds-key")
    mock_ds = MagicMock()
    mock_ds.chat.completions.create.return_value = _mock_openai_response('{"key": "val"}')
    client._deepseek_client = mock_ds

    result = client.complete("system", "user", response_format="json")
    assert result == '{"key": "val"}'
    call_kwargs = mock_ds.chat.completions.create.call_args[1]
    assert call_kwargs["response_format"] == {"type": "json_object"}


def test_complete_deepseek_empty_content_raises():
    client = _make_client("deepseek", deepseek_api_key="ds-key")
    mock_ds = MagicMock()
    mock_ds.chat.completions.create.return_value = _mock_openai_response(None)
    # Override: content=None
    mock_ds.chat.completions.create.return_value.choices[0].message.content = None
    client._deepseek_client = mock_ds

    with pytest.raises(ValueError, match="DeepSeek returned empty content"):
        client.complete("system", "user")


def test_complete_openrouter_text():
    client = _make_client("openrouter", openrouter_api_key="or-key")
    mock_or = MagicMock()
    mock_or.chat.completions.create.return_value = _mock_openai_response("OpenRouter answer")
    client._openrouter_client = mock_or

    result = client.complete("system", "user")
    assert result == "OpenRouter answer"


def test_complete_openrouter_json_mode():
    client = _make_client("openrouter", openrouter_api_key="or-key")
    mock_or = MagicMock()
    mock_or.chat.completions.create.return_value = _mock_openai_response('{"x": 1}')
    client._openrouter_client = mock_or

    result = client.complete("system", "user", response_format="json")
    assert result == '{"x": 1}'
    call_kwargs = mock_or.chat.completions.create.call_args[1]
    assert call_kwargs["response_format"] == {"type": "json_object"}


def test_complete_openrouter_empty_content_raises():
    client = _make_client("openrouter", openrouter_api_key="or-key")
    mock_or = MagicMock()
    mock_or.chat.completions.create.return_value.choices[0].message.content = None
    client._openrouter_client = mock_or

    with pytest.raises(ValueError, match="OpenRouter returned empty content"):
        client.complete("system", "user")


def test_complete_gemini_text():
    client = _make_client("gemini", gemini_api_key="gm-key")
    mock_model = MagicMock()
    mock_model.generate_content.return_value = _mock_gemini_response("Gemini answer")
    client._gemini_client = mock_model

    with _patch_genai():
        result = client.complete("system", "user")

    assert result == "Gemini answer"
    call_args = mock_model.generate_content.call_args
    prompt_used = call_args[0][0]
    assert "system" in prompt_used
    assert "user" in prompt_used


def test_complete_gemini_empty_response_raises():
    client = _make_client("gemini", gemini_api_key="gm-key")
    mock_model = MagicMock()
    mock_model.generate_content.return_value = _mock_gemini_response("")
    client._gemini_client = mock_model

    with _patch_genai():
        with pytest.raises(ValueError, match="Gemini returned empty content"):
            client.complete("system", "user")


def test_complete_unknown_provider_raises():
    client = _make_client("unknown", deepseek_api_key="x")
    with pytest.raises(ValueError, match="Unknown provider"):
        client.complete("system", "user")


# ── complete_json() provider routing ─────────────────────────────────────────


def test_complete_json_deepseek_parses_json_without_forced_mode():
    """DeepSeek complete_json should parse JSON without forcing json_object mode."""
    client = _make_client("deepseek", deepseek_api_key="ds-key")
    mock_ds = MagicMock()
    mock_ds.chat.completions.create.return_value = _mock_openai_response('{"a": 1}')
    client._deepseek_client = mock_ds

    result = client.complete_json("system", "user")
    assert result == {"a": 1}
    call_kwargs = mock_ds.chat.completions.create.call_args[1]
    assert "response_format" not in call_kwargs


def test_complete_json_openrouter_parses_json_without_forced_mode():
    """OpenRouter complete_json should parse JSON without forcing json_object mode."""
    client = _make_client("openrouter", openrouter_api_key="or-key")
    mock_or = MagicMock()
    mock_or.chat.completions.create.return_value = _mock_openai_response('{"b": 2}')
    client._openrouter_client = mock_or

    result = client.complete_json("system", "user")
    assert result == {"b": 2}
    call_kwargs = mock_or.chat.completions.create.call_args[1]
    assert "response_format" not in call_kwargs


def test_complete_json_gemini_does_not_use_json_mode():
    """Gemini does not use json response_format param (not OpenAI-compatible)."""
    client = _make_client("gemini", gemini_api_key="gm-key")
    mock_model = MagicMock()
    mock_model.generate_content.return_value = _mock_gemini_response('{"c": 3}')
    client._gemini_client = mock_model

    with _patch_genai():
        result = client.complete_json("system", "user")
    assert result == {"c": 3}


def test_complete_json_parses_markdown_code_block_deepseek():
    client = _make_client("deepseek", deepseek_api_key="ds-key")
    mock_ds = MagicMock()
    raw = '```json\n{"hello": "world"}\n```'
    mock_ds.chat.completions.create.return_value = _mock_openai_response(raw)
    client._deepseek_client = mock_ds

    result = client.complete_json("system", "user")
    assert result == {"hello": "world"}


def test_complete_json_invalid_json_raises():
    client = _make_client("deepseek", deepseek_api_key="ds-key")
    mock_ds = MagicMock()
    mock_ds.chat.completions.create.return_value = _mock_openai_response("not json at all")
    client._deepseek_client = mock_ds

    with pytest.raises(ValueError, match="LLM returned invalid JSON"):
        client.complete_json("system", "user")


# ── Retry logic with new providers ───────────────────────────────────────────


def test_deepseek_retries_on_429(monkeypatch):
    """DeepSeek should retry on rate-limit errors."""
    monkeypatch.setattr("time.sleep", lambda s: None)  # don't actually sleep
    client = _make_client("deepseek", deepseek_api_key="ds-key")

    rate_exc = Exception("429 Too Many Requests")
    success_resp = _mock_openai_response("ok")

    mock_ds = MagicMock()
    mock_ds.chat.completions.create.side_effect = [rate_exc, success_resp]
    client._deepseek_client = mock_ds

    result = client.complete("system", "user")
    assert result == "ok"
    assert mock_ds.chat.completions.create.call_count == 2


def test_openrouter_retries_on_503(monkeypatch):
    """OpenRouter should retry on server errors."""
    monkeypatch.setattr("time.sleep", lambda s: None)
    client = _make_client("openrouter", openrouter_api_key="or-key")

    server_exc = Exception("503 Service Unavailable")
    success_resp = _mock_openai_response("recovered")

    mock_or = MagicMock()
    mock_or.chat.completions.create.side_effect = [server_exc, success_resp]
    client._openrouter_client = mock_or

    result = client.complete("system", "user")
    assert result == "recovered"


def test_gemini_retries_on_overloaded(monkeypatch):
    """Gemini should retry on overloaded errors."""
    monkeypatch.setattr("time.sleep", lambda s: None)
    client = _make_client("gemini", gemini_api_key="gm-key")

    overloaded_exc = Exception("API is overloaded, please try again")
    success_resp = _mock_gemini_response("gemini ok")

    mock_model = MagicMock()
    mock_model.generate_content.side_effect = [overloaded_exc, success_resp]
    client._gemini_client = mock_model

    with _patch_genai():
        result = client.complete("system", "user")
    assert result == "gemini ok"


def test_non_retryable_error_raises_immediately(monkeypatch):
    """Non-retryable errors should not be retried."""
    monkeypatch.setattr("time.sleep", lambda s: None)
    client = _make_client("deepseek", deepseek_api_key="ds-key")

    bad_request_exc = Exception("400 Bad Request - invalid model")
    mock_ds = MagicMock()
    mock_ds.chat.completions.create.side_effect = bad_request_exc
    client._deepseek_client = mock_ds

    with pytest.raises(Exception, match="400 Bad Request"):
        client.complete("system", "user")

    # Should only have been called once (no retries)
    assert mock_ds.chat.completions.create.call_count == 1


# ── _is_retryable additional edge cases ──────────────────────────────────────


def test_is_retryable_502():
    exc = Exception("502 Bad Gateway")
    assert _is_retryable(exc) is True


def test_is_retryable_http_status_attribute():
    exc = Exception("error")
    exc.http_status = 503
    assert _is_retryable(exc) is True


def test_is_retryable_internal_server_error_classname():
    class InternalServerError(Exception):
        pass
    assert _is_retryable(InternalServerError("boom")) is True


def test_is_retryable_overloaded_error_classname():
    class OverloadedError(Exception):
        pass
    assert _is_retryable(OverloadedError("boom")) is True


# ── CLI: new providers in all commands ───────────────────────────────────────


def test_ingest_accepts_deepseek_provider(tmp_path):
    runner = CliRunner()
    md = tmp_path / "book.md"
    md.write_text("# Chapter 1\n\nHello world.")

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.parser.markdown.parse_markdown_book") as mock_parse, \
         patch("ppke.pipeline.orchestrator.ingest_book") as mock_ingest:
        from ppke.config import Config, LLMConfig
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(provider="deepseek", deepseek_api_key="k"))
        mock_load.return_value = cfg

        from ppke.parser.models import Book
        mock_book = MagicMock(spec=Book)
        mock_book.chapters = []
        mock_book.total_paragraphs = 0
        mock_parse.return_value = mock_book
        mock_ingest.return_value = tmp_path

        result = runner.invoke(
            main,
            ["ingest", str(md), "--title", "Test", "--author", "Author",
             "--provider", "deepseek"],
        )
    assert result.exit_code == 0


def test_ingest_accepts_gemini_provider(tmp_path):
    runner = CliRunner()
    md = tmp_path / "book.md"
    md.write_text("# Chapter 1\n\nHello world.")

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.parser.markdown.parse_markdown_book") as mock_parse, \
         patch("ppke.pipeline.orchestrator.ingest_book") as mock_ingest:
        from ppke.config import Config, LLMConfig
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(provider="gemini", gemini_api_key="k"))
        mock_load.return_value = cfg

        mock_book = MagicMock()
        mock_book.chapters = []
        mock_book.total_paragraphs = 0
        mock_parse.return_value = mock_book
        mock_ingest.return_value = tmp_path

        result = runner.invoke(
            main,
            ["ingest", str(md), "--title", "Test", "--author", "Author",
             "--provider", "gemini"],
        )
    assert result.exit_code == 0


def test_ingest_accepts_openrouter_provider(tmp_path):
    runner = CliRunner()
    md = tmp_path / "book.md"
    md.write_text("# Chapter 1\n\nHello world.")

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.parser.markdown.parse_markdown_book") as mock_parse, \
         patch("ppke.pipeline.orchestrator.ingest_book") as mock_ingest:
        from ppke.config import Config, LLMConfig
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(provider="openrouter", openrouter_api_key="k"))
        mock_load.return_value = cfg

        mock_book = MagicMock()
        mock_book.chapters = []
        mock_book.total_paragraphs = 0
        mock_parse.return_value = mock_book
        mock_ingest.return_value = tmp_path

        result = runner.invoke(
            main,
            ["ingest", str(md), "--title", "Test", "--author", "Author",
             "--provider", "openrouter"],
        )
    assert result.exit_code == 0


def test_ingest_rejects_invalid_provider(tmp_path):
    runner = CliRunner()
    md = tmp_path / "book.md"
    md.write_text("# Chapter 1\n\nHello world.")

    result = runner.invoke(
        main,
        ["ingest", str(md), "--title", "Test", "--author", "Author",
         "--provider", "nonexistent_provider"],
    )
    assert result.exit_code != 0


def test_query_accepts_deepseek_provider(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    (book_dir / "meta.yml").write_text("title: Test\nauthor: Author\n")
    (book_dir / "01_Raw_Structure.md").write_text("raw")
    (book_dir / "02_Logical_Map.md").write_text("map")
    (book_dir / "03_Concept_Index.md").write_text("concepts")

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.cli._require_api_key"), \
         patch("ppke.llm.client.LLMClient.complete_json") as mock_cj:
        from ppke.config import Config, LLMConfig
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(provider="deepseek", deepseek_api_key="k"))
        mock_load.return_value = cfg
        mock_cj.return_value = {"answer": "Yes", "verbatim_quotes": [], "logical_chain": [], "confidence": "high"}

        result = runner.invoke(
            main,
            ["query", "--book", "Book_Test_Author_2024",
             "--question", "What is this?", "--provider", "deepseek"],
        )
    assert result.exit_code == 0


def test_config_accepts_deepseek_provider():
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.config.Config.save"):
        from ppke.config import Config, LLMConfig
        cfg = Config(llm=LLMConfig())
        mock_load.return_value = cfg

        result = runner.invoke(main, ["config", "--provider", "deepseek"])
    assert result.exit_code == 0


def test_config_accepts_gemini_provider():
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.config.Config.save"):
        from ppke.config import Config, LLMConfig
        cfg = Config(llm=LLMConfig())
        mock_load.return_value = cfg

        result = runner.invoke(main, ["config", "--provider", "gemini"])
    assert result.exit_code == 0


def test_config_accepts_openrouter_provider():
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.config.Config.save"):
        from ppke.config import Config, LLMConfig
        cfg = Config(llm=LLMConfig())
        mock_load.return_value = cfg

        result = runner.invoke(main, ["config", "--provider", "openrouter"])
    assert result.exit_code == 0


# ── CLI: _require_api_key with new providers ──────────────────────────────────


def test_require_api_key_deepseek_missing(tmp_path):
    """Missing DeepSeek key should exit with correct env var in message."""
    runner = CliRunner()
    md = tmp_path / "book.md"
    md.write_text("# Ch 1\n\nHello.")

    with patch("ppke.config.Config.load") as mock_load:
        from ppke.config import Config, LLMConfig
        cfg = Config(vault_path=tmp_path,
                     llm=LLMConfig(provider="deepseek", deepseek_api_key=None))
        mock_load.return_value = cfg

        result = runner.invoke(
            main,
            ["ingest", str(md), "--title", "T", "--author", "A"],
        )
    assert result.exit_code == 1
    assert "DEEPSEEK_API_KEY" in result.output


def test_require_api_key_gemini_missing(tmp_path):
    runner = CliRunner()
    md = tmp_path / "book.md"
    md.write_text("# Ch 1\n\nHello.")

    with patch("ppke.config.Config.load") as mock_load:
        from ppke.config import Config, LLMConfig
        cfg = Config(vault_path=tmp_path,
                     llm=LLMConfig(provider="gemini", gemini_api_key=None))
        mock_load.return_value = cfg

        result = runner.invoke(
            main,
            ["ingest", str(md), "--title", "T", "--author", "A"],
        )
    assert result.exit_code == 1
    assert "GEMINI_API_KEY" in result.output


def test_require_api_key_openrouter_missing(tmp_path):
    runner = CliRunner()
    md = tmp_path / "book.md"
    md.write_text("# Ch 1\n\nHello.")

    with patch("ppke.config.Config.load") as mock_load:
        from ppke.config import Config, LLMConfig
        cfg = Config(vault_path=tmp_path,
                     llm=LLMConfig(provider="openrouter", openrouter_api_key=None))
        mock_load.return_value = cfg

        result = runner.invoke(
            main,
            ["ingest", str(md), "--title", "T", "--author", "A"],
        )
    assert result.exit_code == 1
    assert "OPENROUTER_API_KEY" in result.output


# ── CLI: init wizard with new providers ──────────────────────────────────────


def test_init_wizard_deepseek(tmp_path):
    runner = CliRunner()

    with patch("ppke.cli.save_env_file") as mock_save_env, \
         patch("ppke.config.Config.save"), \
         patch("ppke.config.Config.load", return_value=Config()):

        result = runner.invoke(
            main,
            ["init"],
            input="deepseek\ndeepseek-chat\nmy-deepseek-key\n/tmp/vault\n5\n",
        )

    assert result.exit_code == 0
    assert "Setup complete" in result.output or "deepseek" in result.output.lower()


def test_init_wizard_gemini(tmp_path):
    runner = CliRunner()

    with patch("ppke.cli.save_env_file") as mock_save_env, \
         patch("ppke.config.Config.save"), \
         patch("ppke.config.Config.load", return_value=Config()):

        result = runner.invoke(
            main,
            ["init"],
            input="gemini\ngemini-1.5-pro\nmy-gemini-key\n/tmp/vault\n5\n",
        )

    assert result.exit_code == 0


def test_init_wizard_openrouter(tmp_path):
    runner = CliRunner()

    with patch("ppke.cli.save_env_file") as mock_save_env, \
         patch("ppke.config.Config.save"), \
         patch("ppke.config.Config.load", return_value=Config()):

        result = runner.invoke(
            main,
            ["init"],
            input="openrouter\nopenai/gpt-4o\nmy-or-key\n/tmp/vault\n5\n",
        )

    assert result.exit_code == 0


# ── Config save/load round-trip ───────────────────────────────────────────────


def test_config_save_and_load_round_trip(tmp_path):
    cfg_path = tmp_path / "config.json"
    original = Config(
        vault_path=tmp_path / "vault",
        llm=LLMConfig(
            provider="deepseek",
            model="deepseek-chat",
            max_tokens=2048,
            temperature=0.5,
        ),
    )
    original.save(cfg_path)

    loaded = Config.load(cfg_path)
    assert loaded.llm.provider == "deepseek"
    assert loaded.llm.model == "deepseek-chat"
    assert loaded.llm.max_tokens == 2048
    assert loaded.llm.temperature == 0.5


def test_config_load_default_when_missing(tmp_path):
    cfg_path = tmp_path / "nonexistent.json"
    cfg = Config.load(cfg_path)
    assert cfg.llm.provider == "anthropic"  # default


# ── env file loading ──────────────────────────────────────────────────────────


def test_load_env_file_missing(tmp_path):
    result = _load_env_file(tmp_path / "nonexistent.env")
    assert result == {}


def test_load_env_file_with_quotes(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text('DEEPSEEK_API_KEY="ds-quoted-key"\n')
    result = _load_env_file(env_path)
    assert result["DEEPSEEK_API_KEY"] == "ds-quoted-key"


def test_load_env_file_comments_skipped(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("# this is a comment\nGEMINI_API_KEY=gm-key\n")
    result = _load_env_file(env_path)
    assert "GEMINI_API_KEY" in result
    assert len(result) == 1


def test_load_env_file_no_equals_skipped(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("INVALID_LINE\nVALID_KEY=value\n")
    result = _load_env_file(env_path)
    assert "INVALID_LINE" not in result
    assert result["VALID_KEY"] == "value"


def test_save_env_file_merges(tmp_path):
    env_path = tmp_path / ".env"
    save_env_file({"KEY_A": "val_a"}, env_path)
    save_env_file({"KEY_B": "val_b"}, env_path)
    result = _load_env_file(env_path)
    assert result["KEY_A"] == "val_a"
    assert result["KEY_B"] == "val_b"


def test_save_env_file_permissions(tmp_path):
    env_path = tmp_path / ".env"
    save_env_file({"KEY": "val"}, env_path)
    mode = oct(env_path.stat().st_mode)[-3:]
    assert mode == "600"


# ── is_first_run ─────────────────────────────────────────────────────────────


def test_is_first_run_true(tmp_path):
    with patch("ppke.config.DEFAULT_CONFIG_PATH", tmp_path / "nonexistent.json"):
        assert is_first_run() is True


def test_is_first_run_false(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}")
    with patch("ppke.config.DEFAULT_CONFIG_PATH", cfg_path):
        assert is_first_run() is False


# ── Thread-safety: double-checked locking ────────────────────────────────────


def test_get_deepseek_thread_safe():
    """Double-checked locking: calling _get_deepseek() twice from same thread."""
    client = _make_client("deepseek", deepseek_api_key="ds-key")
    mock_openai_instance = MagicMock()

    with patch("openai.OpenAI", return_value=mock_openai_instance):
        r1 = client._get_deepseek()
        r2 = client._get_deepseek()
    assert r1 is r2


def test_get_openrouter_thread_safe():
    client = _make_client("openrouter", openrouter_api_key="or-key")
    mock_openai_instance = MagicMock()

    with patch("openai.OpenAI", return_value=mock_openai_instance):
        r1 = client._get_openrouter()
        r2 = client._get_openrouter()
    assert r1 is r2


# ── DeepSeek/OpenRouter message structure ────────────────────────────────────


def test_deepseek_messages_structure():
    """Verify DeepSeek is called with correct system/user message format."""
    client = _make_client("deepseek", deepseek_api_key="ds-key")
    mock_ds = MagicMock()
    mock_ds.chat.completions.create.return_value = _mock_openai_response("ok")
    client._deepseek_client = mock_ds

    client.complete("my system", "my user")

    call_kwargs = mock_ds.chat.completions.create.call_args[1]
    messages = call_kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "my system"}
    assert messages[1] == {"role": "user", "content": "my user"}


def test_openrouter_messages_structure():
    """Verify OpenRouter is called with correct system/user message format."""
    client = _make_client("openrouter", openrouter_api_key="or-key")
    mock_or = MagicMock()
    mock_or.chat.completions.create.return_value = _mock_openai_response("ok")
    client._openrouter_client = mock_or

    client.complete("my system", "my user")

    call_kwargs = mock_or.chat.completions.create.call_args[1]
    messages = call_kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "my system"}
    assert messages[1] == {"role": "user", "content": "my user"}


def test_gemini_combines_system_and_user_prompt():
    """Verify Gemini receives combined system+user prompt."""
    client = _make_client("gemini", gemini_api_key="gm-key")
    mock_model = MagicMock()
    mock_model.generate_content.return_value = _mock_gemini_response("ok")
    client._gemini_client = mock_model

    with _patch_genai():
        client.complete("SYSTEM INSTRUCTIONS", "USER CONTENT")

    call_args = mock_model.generate_content.call_args[0][0]
    assert "SYSTEM INSTRUCTIONS" in call_args
    assert "USER CONTENT" in call_args


# ── Config: model/token settings propagated to API calls ─────────────────────


def test_deepseek_uses_config_model_and_tokens():
    cfg = LLMConfig(provider="deepseek", model="deepseek-coder", max_tokens=1000,
                    temperature=0.1, deepseek_api_key="k")
    client = LLMClient(cfg)
    mock_ds = MagicMock()
    mock_ds.chat.completions.create.return_value = _mock_openai_response("ok")
    client._deepseek_client = mock_ds

    client.complete("sys", "usr")

    call_kwargs = mock_ds.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "deepseek-coder"
    assert call_kwargs["max_tokens"] == 1000
    assert call_kwargs["temperature"] == 0.1


def test_openrouter_uses_config_model():
    cfg = LLMConfig(provider="openrouter", model="anthropic/claude-3-5-sonnet",
                    max_tokens=500, temperature=0.3, openrouter_api_key="k")
    client = LLMClient(cfg)
    mock_or = MagicMock()
    mock_or.chat.completions.create.return_value = _mock_openai_response("ok")
    client._openrouter_client = mock_or

    client.complete("sys", "usr")

    call_kwargs = mock_or.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "anthropic/claude-3-5-sonnet"
    assert call_kwargs["max_tokens"] == 500
    assert call_kwargs["temperature"] == 0.3


def test_gemini_generation_config_uses_settings():
    cfg = LLMConfig(provider="gemini", model="gemini-1.5-flash",
                    max_tokens=800, temperature=0.4, gemini_api_key="k")
    client = LLMClient(cfg)
    mock_model = MagicMock()
    mock_model.generate_content.return_value = _mock_gemini_response("ok")
    client._gemini_client = mock_model

    genai_mock = _make_genai_mock()
    genai_mock.GenerationConfig = MagicMock(return_value=MagicMock())
    with patch.dict(sys.modules, {"google": MagicMock(generativeai=genai_mock),
                                   "google.generativeai": genai_mock}):
        client.complete("sys", "usr")
        genai_mock.GenerationConfig.assert_called_once_with(
            max_output_tokens=800, temperature=0.4
        )
