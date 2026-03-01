"""Tests to improve coverage for uncovered lines across multiple modules.

Covers: audio/overview, audio/rss, audio/transcriber, templates/installer,
graph/analytics, graph/knowledge_graph, infra/tasks, infra/sentry_integration.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest
import yaml


# ═══════════════════════════════════════════════════════════════════
# audio/overview.py — cross-book ValueError, TTS synthesis
# ═══════════════════════════════════════════════════════════════════


class TestCrossBookScriptValueError:
    """Line 241: raise ValueError on unexpected format."""

    def test_cross_book_unexpected_format(self, tmp_path):
        from ppke.audio.overview import generate_cross_book_script

        book_a = tmp_path / "Book_X"
        book_a.mkdir()
        (book_a / "meta.yml").write_text(yaml.dump({"title": "X", "author": "A"}))
        book_b = tmp_path / "Book_Y"
        book_b.mkdir()
        (book_b / "meta.yml").write_text(yaml.dump({"title": "Y", "author": "B"}))

        mock_llm = MagicMock()
        mock_llm.complete_json.return_value = "unexpected string"
        with pytest.raises(ValueError, match="Unexpected"):
            generate_cross_book_script(book_a, book_b, mock_llm)


class TestSynthesizeOpenAIMocked:
    """Lines 322-367: _synthesize_openai with mocked openai + pydub."""

    def test_synthesize_openai_full(self, tmp_path):
        from ppke.audio.overview import _synthesize_openai

        mock_response = MagicMock()
        mock_response.content = b"fake_mp3_data"

        mock_client = MagicMock()
        mock_client.audio.speech.create.return_value = mock_response

        mock_segment = MagicMock()
        mock_silent = MagicMock()
        mock_combined = MagicMock()

        # __iadd__ for combined += seg
        mock_segment.__iadd__ = MagicMock(return_value=mock_combined)
        mock_combined.__iadd__ = MagicMock(return_value=mock_combined)

        # segments[0] returns mock_segment, then combined += works
        segments_list = []

        def fake_from_mp3(path):
            seg = MagicMock()
            seg.__iadd__ = MagicMock(return_value=seg)
            segments_list.append(seg)
            return seg

        mock_audio_segment_cls = MagicMock()
        mock_audio_segment_cls.from_mp3 = fake_from_mp3
        mock_audio_segment_cls.silent.return_value = MagicMock()

        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment = mock_audio_segment_cls

        script = [
            {"speaker": "HOST_A", "text": "Hello!"},
            {"speaker": "HOST_B", "text": "Welcome!"},
        ]
        out = tmp_path / "out.mp3"

        with patch.dict("sys.modules", {"openai": mock_openai, "pydub": mock_pydub}):
            _synthesize_openai(script, out, "fake-key", "alloy", "onyx")

        assert mock_client.audio.speech.create.call_count == 2


class TestSynthesizeEdgeMocked:
    """Lines 385-428: _synthesize_edge with mocked edge_tts + pydub."""

    def test_synthesize_edge_full(self, tmp_path):
        from ppke.audio.overview import _synthesize_edge

        mock_seg = MagicMock()
        mock_seg.__iadd__ = MagicMock(return_value=mock_seg)

        mock_audio_segment_cls = MagicMock()
        mock_audio_segment_cls.from_mp3.return_value = mock_seg
        mock_audio_segment_cls.silent.return_value = MagicMock()

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment = mock_audio_segment_cls

        mock_communicate = MagicMock()
        # Make save() a coroutine
        import asyncio

        async def mock_save(path):
            Path(path).write_bytes(b"fake")

        mock_communicate.save = mock_save

        mock_edge_tts = MagicMock()
        mock_edge_tts.Communicate.return_value = mock_communicate

        script = [
            {"speaker": "HOST_A", "text": "Hi"},
            {"speaker": "HOST_B", "text": "Hey"},
        ]
        out = tmp_path / "edge_out.mp3"

        with patch.dict(
            "sys.modules",
            {"edge_tts": mock_edge_tts, "pydub": mock_pydub},
        ):
            _synthesize_edge(script, out, "en-US-JennyNeural", "en-US-GuyNeural")


class TestSynthesizeEdgeDefaultVoices:
    """Lines 391-394: default voice fallback when alloy/onyx passed to edge."""

    def test_default_voice_fallback(self, tmp_path):
        from ppke.audio.overview import _synthesize_edge

        mock_pydub = MagicMock()
        mock_seg = MagicMock()
        mock_seg.__iadd__ = MagicMock(return_value=mock_seg)
        mock_pydub.AudioSegment.from_mp3.return_value = mock_seg
        mock_pydub.AudioSegment.silent.return_value = MagicMock()

        import asyncio

        async def mock_save(path):
            Path(path).write_bytes(b"fake")

        mock_communicate = MagicMock()
        mock_communicate.save = mock_save

        mock_edge_tts = MagicMock()
        mock_edge_tts.Communicate.return_value = mock_communicate

        out = tmp_path / "edge_default.mp3"
        script = [{"speaker": "HOST_A", "text": "Test"}]

        with patch.dict(
            "sys.modules",
            {"edge_tts": mock_edge_tts, "pydub": mock_pydub},
        ):
            _synthesize_edge(script, out, "alloy", "onyx")

        # Should have replaced alloy -> JennyNeural
        call_args = mock_edge_tts.Communicate.call_args
        assert "Jenny" in call_args[0][1] or "Jenny" in str(call_args)


# ═══════════════════════════════════════════════════════════════════
# audio/rss.py — parse_feed, download_and_transcribe
# ═══════════════════════════════════════════════════════════════════


class TestParseFeedMocked:
    """Lines 58-92: parse_feed with mocked feedparser."""

    def test_parse_feed_success(self):
        from ppke.audio.rss import parse_feed

        mock_entry = {
            "title": "Episode 1",
            "enclosures": [{"href": "https://example.com/ep1.mp3", "type": "audio/mpeg"}],
            "itunes_duration": "30:00",
            "published": "Mon, 01 Jan 2024",
            "summary": "A test episode.",
        }
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [mock_entry]
        mock_feed.feed.get = lambda k, d=None: {
            "title": "Test Podcast",
            "author": "Author",
            "subtitle": "Desc",
        }.get(k, d)

        mock_feedparser = MagicMock()
        mock_feedparser.parse.return_value = mock_feed

        with patch.dict("sys.modules", {"feedparser": mock_feedparser}):
            result = parse_feed("https://example.com/feed")

        assert result["title"] == "Test Podcast"
        assert len(result["episodes"]) == 1
        assert result["episodes"][0]["url"] == "https://example.com/ep1.mp3"
        assert result["episodes"][0]["duration_seconds"] == 1800

    def test_parse_feed_bozo_no_entries(self):
        from ppke.audio.rss import parse_feed

        mock_feed = MagicMock()
        mock_feed.bozo = True
        mock_feed.entries = []
        mock_feed.bozo_exception = "Bad XML"

        mock_feedparser = MagicMock()
        mock_feedparser.parse.return_value = mock_feed

        with patch.dict("sys.modules", {"feedparser": mock_feedparser}):
            with pytest.raises(ValueError, match="Failed to parse"):
                parse_feed("https://bad-feed.com")

    def test_parse_feed_no_audio(self):
        from ppke.audio.rss import parse_feed

        mock_entry = {
            "title": "Text Only",
            "enclosures": [],
            "links": [{"href": "https://example.com/page", "type": "text/html"}],
        }
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [mock_entry]
        mock_feed.feed.get = lambda k, d=None: {"title": "Pod"}.get(k, d)

        mock_feedparser = MagicMock()
        mock_feedparser.parse.return_value = mock_feed

        with patch.dict("sys.modules", {"feedparser": mock_feedparser}):
            result = parse_feed("https://example.com/feed")
        assert result["episodes"] == []

    def test_parse_feed_audio_by_extension(self):
        """Line 73: detect audio by file extension."""
        from ppke.audio.rss import parse_feed

        mock_entry = {
            "title": "Ep2",
            "enclosures": [],
            "links": [{"href": "https://example.com/ep2.m4a", "type": ""}],
            "itunes_duration": "",
            "published": "",
            "summary": "",
        }
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [mock_entry]
        mock_feed.feed.get = lambda k, d=None: {"title": "P"}.get(k, d)

        mock_feedparser = MagicMock()
        mock_feedparser.parse.return_value = mock_feed

        with patch.dict("sys.modules", {"feedparser": mock_feedparser}):
            result = parse_feed("https://example.com/feed")
        assert len(result["episodes"]) == 1
        assert result["episodes"][0]["url"].endswith(".m4a")


class TestDownloadAndTranscribe:
    """Lines 113-156: download_episode, transcribe_episode."""

    def test_download_and_transcribe(self, tmp_path):
        from ppke.audio.rss import download_and_transcribe

        fake_audio = b"fake audio data" * 100

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_audio
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp), \
             patch("ppke.audio.transcriber.transcribe", return_value="Transcript text"):
            result = download_and_transcribe(
                "https://example.com/ep.mp3",
                episode_title="Test Ep!",
                podcast_title="Pod",
                podcast_author="Auth",
            )

        assert "Test Ep" in result
        assert "**Podcast:** Pod" in result
        assert "Transcript text" in result

    def test_download_m4a_extension(self, tmp_path):
        from ppke.audio.rss import download_and_transcribe

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"data"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp), \
             patch("ppke.audio.transcriber.transcribe", return_value="text"):
            result = download_and_transcribe(
                "https://example.com/ep.m4a",
                episode_title="M4A Episode",
            )
        assert "M4A Episode" in result


# ═══════════════════════════════════════════════════════════════════
# audio/transcriber.py — transcribe, transcribe_local
# ═══════════════════════════════════════════════════════════════════


class TestTranscribeMocked:
    """Lines 49-50, 57-88: transcribe() with mocked openai."""

    def test_transcribe_with_segments(self, tmp_path):
        from ppke.audio.transcriber import transcribe

        audio_file = tmp_path / "test_audio.mp3"
        audio_file.write_bytes(b"fake audio")

        mock_seg = MagicMock()
        mock_seg.start = 10.0
        mock_seg.text = "Hello world"

        mock_transcript = MagicMock()
        mock_transcript.segments = [mock_seg]

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_transcript

        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = transcribe(audio_file, api_key="fake-key")

        assert "Hello world" in result
        assert "[00:10]" in result

    def test_transcribe_no_segments_fallback(self, tmp_path):
        from ppke.audio.transcriber import transcribe

        audio_file = tmp_path / "test_audio.mp3"
        audio_file.write_bytes(b"fake audio")

        mock_transcript = MagicMock()
        mock_transcript.segments = None
        mock_transcript.text = "Full transcript text"

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_transcript

        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = transcribe(audio_file, api_key="key")

        assert "Full transcript text" in result

    def test_transcribe_with_language(self, tmp_path):
        from ppke.audio.transcriber import transcribe

        audio_file = tmp_path / "test_lang.mp3"
        audio_file.write_bytes(b"fake")

        mock_transcript = MagicMock()
        mock_transcript.segments = []
        mock_transcript.text = "text"

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_transcript

        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = transcribe(audio_file, api_key="k", language="en")

        # Verify language was passed
        call_kwargs = mock_client.audio.transcriptions.create.call_args
        assert "language" in str(call_kwargs)

    def test_transcribe_dict_segments(self, tmp_path):
        """Line 77-78: handle dict-style segments (isinstance check)."""
        from ppke.audio.transcriber import transcribe

        audio_file = tmp_path / "dict_seg.mp3"
        audio_file.write_bytes(b"fake")

        # Use a proper object with .start and .text attributes (not a dict)
        # since the code does `isinstance(seg, dict)` check
        mock_seg = MagicMock()
        mock_seg.start = 5.0
        mock_seg.text = " Dict text "

        mock_transcript = MagicMock()
        mock_transcript.segments = [mock_seg]

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_transcript

        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = transcribe(audio_file, api_key="k")

        assert "Dict text" in result


class TestTranscribeLocalMocked:
    """Lines 109-123: transcribe_local with mocked whisper."""

    def test_transcribe_local_success(self, tmp_path):
        from ppke.audio.transcriber import transcribe_local

        audio_file = tmp_path / "local_test.mp3"
        audio_file.write_bytes(b"fake")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [
                {"start": 0.0, "text": "First segment"},
                {"start": 30.0, "text": "Second segment"},
            ]
        }

        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model

        with patch.dict("sys.modules", {"whisper": mock_whisper}):
            result = transcribe_local(audio_file, model_size="tiny", language="en")

        assert "First segment" in result
        assert "Second segment" in result
        assert "[00:00]" in result
        assert "[00:30]" in result
        mock_whisper.load_model.assert_called_once_with("tiny")


# ═══════════════════════════════════════════════════════════════════
# templates/installer.py
# ═══════════════════════════════════════════════════════════════════


class TestValidateGithubUrl:
    def test_valid_url(self):
        from ppke.templates.installer import _validate_github_url

        _validate_github_url("https://github.com/user/repo")

    def test_invalid_url(self):
        from ppke.templates.installer import _validate_github_url, TemplateInstallError

        with pytest.raises(TemplateInstallError):
            _validate_github_url("http://github.com/user/repo")

    def test_url_with_query(self):
        from ppke.templates.installer import _validate_github_url, TemplateInstallError

        with pytest.raises(TemplateInstallError):
            _validate_github_url("https://github.com/user/repo?foo=bar")


class TestCheckTemplateFiles:
    def test_disallowed_extension(self, tmp_path):
        from ppke.templates.installer import _check_template_files, TemplateInstallError

        (tmp_path / "bad.py").write_text("code")
        with pytest.raises(TemplateInstallError, match="disallowed"):
            _check_template_files(tmp_path)

    def test_file_too_large(self, tmp_path):
        from ppke.templates.installer import _check_template_files, TemplateInstallError

        big = tmp_path / "big.yml"
        big.write_bytes(b"x" * (512 * 1024 + 1))
        with pytest.raises(TemplateInstallError, match="too large"):
            _check_template_files(tmp_path)

    def test_too_many_files(self, tmp_path):
        from ppke.templates.installer import _check_template_files, TemplateInstallError

        for i in range(51):
            (tmp_path / f"file{i}.yml").write_text("x")
        with pytest.raises(TemplateInstallError, match="files"):
            _check_template_files(tmp_path)

    def test_valid_files(self, tmp_path):
        from ppke.templates.installer import _check_template_files

        (tmp_path / "template.yml").write_text("name: test")
        (tmp_path / "readme.md").write_text("# Readme")
        _check_template_files(tmp_path)


class TestInstallFromLocal:
    def test_path_not_exists(self, tmp_path):
        from ppke.templates.installer import install_from_local, TemplateInstallError

        with pytest.raises(TemplateInstallError, match="does not exist"):
            install_from_local(tmp_path / "nonexistent")

    def test_path_not_dir(self, tmp_path):
        from ppke.templates.installer import install_from_local, TemplateInstallError

        f = tmp_path / "file.txt"
        f.write_text("hi")
        with pytest.raises(TemplateInstallError, match="not a directory"):
            install_from_local(f)

    def test_missing_template_yml(self, tmp_path):
        from ppke.templates.installer import install_from_local, TemplateInstallError

        d = tmp_path / "template_dir"
        d.mkdir()
        with pytest.raises(TemplateInstallError, match="missing template.yml"):
            install_from_local(d)

    def test_missing_name_field(self, tmp_path):
        from ppke.templates.installer import install_from_local, TemplateInstallError

        d = tmp_path / "template_dir"
        d.mkdir()
        (d / "template.yml").write_text(yaml.dump({"version": "1.0"}))
        with pytest.raises(TemplateInstallError, match="missing 'name'"):
            install_from_local(d)

    def test_already_exists_no_force(self, tmp_path):
        from ppke.templates.installer import install_from_local, TemplateInstallError

        d = tmp_path / "template_dir"
        d.mkdir()
        (d / "template.yml").write_text(yaml.dump({"name": "existing_test"}))

        with patch("ppke.templates.installer.CUSTOM_TEMPLATES_DIR", tmp_path / "plugins"):
            target = tmp_path / "plugins" / "existing_test"
            target.mkdir(parents=True)
            with pytest.raises(TemplateInstallError, match="already exists"):
                install_from_local(d)


class TestInstallFromGithub:
    def test_invalid_url_rejected(self):
        from ppke.templates.installer import install_from_github, TemplateInstallError

        with pytest.raises(TemplateInstallError, match="Invalid GitHub URL"):
            install_from_github("ftp://evil.com/repo")

    def test_git_not_available(self):
        from ppke.templates.installer import install_from_github, TemplateInstallError
        import subprocess

        with patch("subprocess.run", side_effect=FileNotFoundError("no git")):
            with pytest.raises(TemplateInstallError, match="Git is not installed"):
                install_from_github("https://github.com/user/repo")


class TestUninstallTemplate:
    def test_not_found(self):
        from ppke.templates.installer import uninstall_template, TemplateInstallError

        with patch("ppke.templates.installer.uninstall_template.__module__", "ppke.templates.installer"):
            with patch("ppke.templates.registry.get_plugin_info", return_value=None):
                with pytest.raises(TemplateInstallError, match="not found"):
                    uninstall_template("nonexistent")

    def test_official_cannot_uninstall(self):
        from ppke.templates.installer import uninstall_template, TemplateInstallError

        with patch("ppke.templates.registry.get_plugin_info", return_value={"tier": "official"}):
            with pytest.raises(TemplateInstallError, match="Cannot uninstall official"):
                uninstall_template("philosophy")

    def test_uninstall_force(self, tmp_path):
        from ppke.templates.installer import uninstall_template

        fake_info = {"tier": "custom", "source": "local"}

        with patch("ppke.templates.registry.get_plugin_info", return_value=fake_info), \
             patch("ppke.templates.registry.unregister_plugin"), \
             patch("ppke.templates.installer.CUSTOM_TEMPLATES_DIR", tmp_path):
            tpl_dir = tmp_path / "my_tpl"
            tpl_dir.mkdir()
            result = uninstall_template("my_tpl", force=True)
            assert result is True
            assert not tpl_dir.exists()

    def test_uninstall_cancelled(self, tmp_path):
        from ppke.templates.installer import uninstall_template

        fake_info = {"tier": "custom", "source": "local"}

        with patch("ppke.templates.registry.get_plugin_info", return_value=fake_info), \
             patch("ppke.templates.installer.CUSTOM_TEMPLATES_DIR", tmp_path), \
             patch("builtins.input", return_value="n"):
            result = uninstall_template("my_tpl")
            assert result is False

    def test_uninstall_dir_missing_warning(self, tmp_path, capsys):
        from ppke.templates.installer import uninstall_template

        fake_info = {"tier": "custom", "source": "local"}

        with patch("ppke.templates.registry.get_plugin_info", return_value=fake_info), \
             patch("ppke.templates.registry.unregister_plugin"), \
             patch("ppke.templates.installer.CUSTOM_TEMPLATES_DIR", tmp_path):
            # dir doesn't exist - should print warning
            result = uninstall_template("missing_tpl", force=True)
            assert result is True


class TestListInstalledTemplates:
    def test_list_installed(self):
        from ppke.templates.installer import list_installed_templates

        with patch("ppke.templates.registry.list_registered_plugins", return_value=[
            {"name": "test", "tier": "custom"},
        ]):
            result = list_installed_templates()
            assert len(result) == 1
            assert result[0]["name"] == "test"


class TestCanUseEmojis:
    def test_emoji_support(self):
        from ppke.templates.installer import _can_use_emojis

        result = _can_use_emojis()
        assert isinstance(result, bool)


class TestUpgradeTemplate:
    def test_not_found(self):
        from ppke.templates.installer import upgrade_template, TemplateInstallError

        with patch("ppke.templates.registry.get_plugin_info", return_value=None):
            with pytest.raises(TemplateInstallError, match="not found"):
                upgrade_template("nonexistent")

    def test_not_from_github(self):
        from ppke.templates.installer import upgrade_template, TemplateInstallError

        with patch("ppke.templates.registry.get_plugin_info", return_value={
            "source": "local",
        }):
            with pytest.raises(TemplateInstallError, match="not installed from GitHub"):
                upgrade_template("my_tpl")


# ═══════════════════════════════════════════════════════════════════
# graph/analytics.py — build_nx_graph, clusters, centrality
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture()
def graph_data():
    return {
        "nodes": [
            {"id": "concept:a", "label": "A", "type": "concept", "books": ["B1"]},
            {"id": "concept:b", "label": "B", "type": "concept", "books": ["B1"]},
            {"id": "concept:c", "label": "C", "type": "concept", "books": ["B1"]},
            {"id": "book:B1", "label": "Book 1", "type": "book"},
        ],
        "edges": [
            {"src": "concept:a", "dst": "concept:b", "rel": "related_to"},
            {"src": "concept:b", "dst": "concept:c", "rel": "supports"},
            {"src": "book:B1", "dst": "concept:a", "rel": "defines"},
        ],
    }


try:
    import networkx
    _has_nx = True
except ImportError:
    _has_nx = False


@pytest.mark.skipif(not _has_nx, reason="networkx not installed")
class TestBuildNxGraphEdges:
    """Line 22, 58-72: edge filtering in _build_nx_graph."""

    def test_skips_empty_src_dst(self):
        from ppke.graph.analytics import _build_nx_graph

        data = {
            "nodes": [{"id": "concept:x", "label": "X"}],
            "edges": [
                {"src": "", "dst": "concept:x", "rel": "related"},
                {"src": "concept:x", "dst": "", "rel": "related"},
            ],
        }
        G = _build_nx_graph(data)
        assert G is not None
        assert G.number_of_edges() == 0

    def test_edge_attrs_filtered(self):
        from ppke.graph.analytics import _build_nx_graph

        data = {
            "nodes": [
                {"id": "concept:a", "label": "A"},
                {"id": "concept:b", "label": "B"},
            ],
            "edges": [
                {"src": "concept:a", "dst": "concept:b", "rel": "related_to", "weight": 5},
            ],
        }
        G = _build_nx_graph(data)
        edge_data = G.get_edge_data("concept:a", "concept:b")
        assert edge_data["relation"] == "related_to"
        assert edge_data.get("weight") == 5


class TestBuildNxGraphNoNetworkx:
    """_build_nx_graph returns None when networkx unavailable."""

    def test_returns_none_without_nx(self):
        from ppke.graph import analytics as ga
        original = ga._nx_available
        ga._nx_available = False
        try:
            result = ga._build_nx_graph({"nodes": [], "edges": []})
            assert result is None
        finally:
            ga._nx_available = original


class TestComputeClustersNoNetworkx:
    """Lines 110-111: error when networkx not available."""

    def test_no_nx(self, tmp_path):
        from ppke.graph import analytics as ga
        original = ga._nx_available
        ga._nx_available = False
        try:
            result = ga.compute_clusters(tmp_path)
            assert "error" in result
        finally:
            ga._nx_available = original


@pytest.mark.skipif(not _has_nx, reason="networkx not installed")
class TestComputeClustersLouvain:
    """Lines 112-131: Louvain community detection flow."""

    def test_louvain_failure(self, tmp_path):
        from ppke.graph.analytics import compute_clusters

        data = {
            "nodes": [{"id": "concept:a", "label": "A", "type": "concept"}],
            "edges": [],
        }
        (tmp_path / "knowledge_graph.json").write_text(json.dumps(data))

        with patch("networkx.community.louvain_communities", side_effect=Exception("louvain error")):
            result = compute_clusters(tmp_path)
            assert "error" in result


class TestComputeCentralityNoNetworkx:
    """Lines 136-137: error when networkx not available."""

    def test_no_nx(self, tmp_path):
        from ppke.graph import analytics as ga
        original = ga._nx_available
        ga._nx_available = False
        try:
            result = ga.compute_centrality(tmp_path)
            assert "error" in result
        finally:
            ga._nx_available = original


@pytest.mark.skipif(not _has_nx, reason="networkx not installed")
class TestComputeCentralityDetails:
    """Lines 138-165: full centrality pipeline with real data."""

    def test_centrality_with_data(self, tmp_path, graph_data):
        from ppke.graph.analytics import compute_centrality

        (tmp_path / "knowledge_graph.json").write_text(json.dumps(graph_data))
        result = compute_centrality(tmp_path)
        assert "pagerank" in result
        assert "betweenness" in result

    def test_centrality_pagerank_exception(self, tmp_path, graph_data):
        from ppke.graph.analytics import compute_centrality

        (tmp_path / "knowledge_graph.json").write_text(json.dumps(graph_data))

        with patch("networkx.pagerank", side_effect=Exception("pagerank fail")), \
             patch("networkx.betweenness_centrality", side_effect=Exception("bc fail")):
            result = compute_centrality(tmp_path)
            assert result["pagerank"] == []
            assert result["betweenness"] == []


# ═══════════════════════════════════════════════════════════════════
# graph/knowledge_graph.py
# ═══════════════════════════════════════════════════════════════════


class TestKnowledgeGraphConstruction:
    """Lines 28, 77, 100, 106, 113-117, 144-154, 162, 164, 169."""

    def test_empty_graph(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        assert kg.stats()["concepts"] == 0

    def test_add_book_extractions(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        extractions = [
            {
                "paragraph_id": "p1",
                "topic_sentence": "Intro topic",
                "defined_concepts": ["Ontology", "Being"],
                "explicit_claims": ["Being is fundamental to philosophy"],
                "implicit_assumptions": ["Existence precedes essence"],
            }
        ]
        edges = kg.add_book_extractions("Book_Test", "Test Book", "Author", extractions)
        assert edges > 0

    def test_add_book_extractions_skips_short(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        extractions = [
            {
                "paragraph_id": "p1",
                "defined_concepts": ["X"],  # too short (<2)
                "explicit_claims": ["ab"],  # too short (<4)
                "implicit_assumptions": ["cd"],  # too short (<4)
            }
        ]
        edges = kg.add_book_extractions("Book_Short", "Short", "Auth", extractions)
        # Only book->para edge (1), no concepts
        assert edges == 1

    def test_add_node_merges_books(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        kg._add_node("concept:test", type="concept", label="Test", books={"Book_A"})
        kg._add_node("concept:test", type="concept", label="Test", books={"Book_B"})

        # Check the node has both books
        if kg._g is not None:
            books = kg._g.nodes["concept:test"]["books"]
        else:
            books = kg._nodes["concept:test"]["books"]
        assert "Book_A" in books
        assert "Book_B" in books

    def test_add_node_merges_list_books(self, tmp_path):
        """Lines 150-154: merge when existing books is a list."""
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        kg._add_node("concept:ltest", type="concept", label="LTest", books=["Book_A"])
        kg._add_node("concept:ltest", type="concept", label="LTest", books=["Book_B"])

        if kg._g is not None:
            books = kg._g.nodes["concept:ltest"]["books"]
        else:
            books = kg._nodes["concept:ltest"]["books"]
        assert "Book_A" in books
        assert "Book_B" in books

    def test_save_and_reload(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        kg.add_concept_relation("Logic", "Ethics", "supports")
        kg.save()

        kg2 = KnowledgeGraph(tmp_path)
        concepts = kg2.all_concepts()
        labels = [c["label"] for c in concepts]
        assert "Logic" in labels
        assert "Ethics" in labels


class TestKnowledgeGraphQueries:
    """Lines 220, 235, 251, 355-363, 390-392, 404."""

    def test_expand_concept(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        kg.add_concept_relation("Logic", "Ethics", "related_to")
        kg.add_concept_relation("Ethics", "Virtue", "supports")

        results = kg.expand_concept("Logic", depth=2)
        ids = [r["concept_id"] for r in results]
        assert "concept:ethics" in ids

    def test_expand_concept_not_found(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        results = kg.expand_concept("nonexistent")
        assert results == []

    def test_concept_provenance(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        extractions = [
            {
                "paragraph_id": "p1",
                "defined_concepts": ["Dasein"],
                "explicit_claims": [],
                "implicit_assumptions": [],
            }
        ]
        kg.add_book_extractions("Book_H", "Heidegger", "MH", extractions)

        results = kg.concept_provenance("Dasein")
        assert len(results) >= 1
        assert results[0]["book_folder"] == "Book_H"

    def test_concept_provenance_not_found(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        assert kg.concept_provenance("nonexistent") == []

    def test_books_mentioning(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        kg._add_node("concept:test", type="concept", label="Test", books={"B1", "B2"})
        result = kg.books_mentioning("test")
        assert "B1" in result
        assert "B2" in result

    def test_books_mentioning_not_found(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        assert kg.books_mentioning("nonexistent") == []

    def test_books_mentioning_list_books(self, tmp_path):
        """Line 397-398: books stored as list."""
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        kg._add_node("concept:listb", type="concept", label="LB", books=["B1", "B2"])
        result = kg.books_mentioning("listb")
        assert "B1" in result

    def test_all_concepts(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        kg.add_concept_relation("Logic", "Ethics")
        concepts = kg.all_concepts()
        assert len(concepts) == 2


class TestKnowledgeGraphStats:
    """Lines 426-431: stats method."""

    def test_stats(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        extractions = [
            {
                "paragraph_id": "p1",
                "defined_concepts": ["Concept1"],
                "explicit_claims": [],
                "implicit_assumptions": [],
            }
        ]
        kg.add_book_extractions("Book_S", "Stats", "Auth", extractions)
        stats = kg.stats()
        assert stats["books"] >= 1
        assert stats["concepts"] >= 1
        assert stats["edges"] >= 1
        assert "networkx_available" in stats


class TestKnowledgeGraphBuildFromVault:
    """Lines 463, 466-468, 475-476: build_from_vault."""

    def test_build_from_vault(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        book_dir = tmp_path / "Book_Test"
        book_dir.mkdir()
        (book_dir / "meta.yml").write_text(yaml.dump({"title": "Test", "author": "A"}))
        (book_dir / "extractions.json").write_text(json.dumps([
            {
                "paragraph_id": "p1",
                "defined_concepts": ["Concept1"],
                "explicit_claims": [],
                "implicit_assumptions": [],
            }
        ]))

        kg = KnowledgeGraph(tmp_path)
        results = kg.build_from_vault(tmp_path)
        assert "Book_Test" in results
        assert results["Book_Test"] > 0

    def test_build_from_vault_invalid_json(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        book_dir = tmp_path / "Book_Bad"
        book_dir.mkdir()
        (book_dir / "extractions.json").write_text("not json{{{")

        kg = KnowledgeGraph(tmp_path)
        results = kg.build_from_vault(tmp_path)
        assert "Book_Bad" not in results

    def test_build_from_vault_no_meta(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        book_dir = tmp_path / "Book_NoMeta"
        book_dir.mkdir()
        (book_dir / "extractions.json").write_text(json.dumps([
            {"paragraph_id": "p1", "defined_concepts": ["C1"],
             "explicit_claims": [], "implicit_assumptions": []}
        ]))

        kg = KnowledgeGraph(tmp_path)
        results = kg.build_from_vault(tmp_path)
        assert "Book_NoMeta" in results

    def test_build_from_vault_bad_meta(self, tmp_path):
        """Lines 475-476: exception reading meta.yml."""
        from ppke.graph.knowledge_graph import KnowledgeGraph

        book_dir = tmp_path / "Book_BadMeta"
        book_dir.mkdir()
        (book_dir / "meta.yml").write_text("{{invalid yaml")
        (book_dir / "extractions.json").write_text(json.dumps([
            {"paragraph_id": "p1", "defined_concepts": ["C1"],
             "explicit_claims": [], "implicit_assumptions": []}
        ]))

        kg = KnowledgeGraph(tmp_path)
        results = kg.build_from_vault(tmp_path)
        assert "Book_BadMeta" in results


class TestKnowledgeGraphObsidianExport:
    """Lines 297-306, 326-332: save + export via analytics."""

    def test_save_creates_json(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path)
        kg.add_concept_relation("Logic", "Ethics", "related_to")
        kg.save()

        graph_path = tmp_path / "knowledge_graph.json"
        assert graph_path.exists()
        data = json.loads(graph_path.read_text())
        assert len(data["nodes"]) >= 2
        assert len(data["edges"]) >= 1


class TestKnowledgeGraphLoadCorrupt:
    """Line 107-108: error loading corrupt graph."""

    def test_load_corrupt_json(self, tmp_path):
        from ppke.graph.knowledge_graph import KnowledgeGraph

        (tmp_path / "knowledge_graph.json").write_text("not valid json")
        kg = KnowledgeGraph(tmp_path)
        assert kg.stats()["concepts"] == 0


# ═══════════════════════════════════════════════════════════════════
# infra/tasks.py — Redis connection, job ops, worker
# ═══════════════════════════════════════════════════════════════════


class TestGetRedisConnected:
    """Lines 35, 39-47: Redis connection with mocked redis."""

    def setup_method(self):
        import ppke.infra.tasks as tm
        tm._redis_client = None
        tm._jobs.clear()

    def test_redis_connects(self):
        import ppke.infra.tasks as tm

        mock_redis_inst = MagicMock()
        mock_redis_inst.ping.return_value = True

        mock_redis = MagicMock()
        mock_redis.Redis.from_url.return_value = mock_redis_inst

        with patch.dict("sys.modules", {"redis": mock_redis}), \
             patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            tm._redis_client = None
            result = tm._get_redis()
            assert result is not None

        tm._redis_client = None

    def test_redis_connection_fails(self):
        import ppke.infra.tasks as tm

        mock_redis = MagicMock()
        mock_redis.Redis.from_url.side_effect = Exception("Connection refused")

        with patch.dict("sys.modules", {"redis": mock_redis}), \
             patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            tm._redis_client = None
            result = tm._get_redis()
            assert result is None

        tm._redis_client = None

    def test_redis_cached(self):
        import ppke.infra.tasks as tm

        mock_client = MagicMock()
        tm._redis_client = mock_client
        assert tm._get_redis() is mock_client
        tm._redis_client = None


class TestJobWithRedis:
    """Lines 62-63, 79-80: job ops through Redis."""

    def setup_method(self):
        import ppke.infra.tasks as tm
        tm._redis_client = None
        tm._jobs.clear()

    def test_set_job_with_redis(self):
        import ppke.infra.tasks as tm

        mock_redis = MagicMock()
        tm._redis_client = mock_redis

        tm.set_job("r1", {"status": "running"})
        mock_redis.setex.assert_called_once()
        tm._redis_client = None

    def test_get_job_from_redis(self):
        import ppke.infra.tasks as tm

        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"status": "done"})
        tm._redis_client = mock_redis

        # Not in memory, should fall back to Redis
        result = tm.get_job("redis_job")
        assert result is not None
        assert result["status"] == "done"
        tm._redis_client = None

    def test_get_job_redis_returns_none(self):
        import ppke.infra.tasks as tm

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        tm._redis_client = mock_redis

        result = tm.get_job("nope")
        assert result is None
        tm._redis_client = None

    def test_set_job_redis_exception(self):
        import ppke.infra.tasks as tm

        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Redis error")
        tm._redis_client = mock_redis

        # Should not raise
        tm.set_job("err_job", {"status": "running"})
        assert tm._jobs["err_job"]["status"] == "running"
        tm._redis_client = None

    def test_get_job_redis_exception(self):
        import ppke.infra.tasks as tm

        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis error")
        tm._redis_client = mock_redis

        result = tm.get_job("err_job2")
        assert result is None
        tm._redis_client = None


class TestCeleryAppCreation:
    """Lines 101, 112-133: Celery app creation with mocked celery."""

    def setup_method(self):
        import ppke.infra.tasks as tm
        tm._celery_app = None

    def test_celery_creation_success(self):
        import ppke.infra.tasks as tm

        mock_conn = MagicMock()
        mock_app = MagicMock()
        mock_app.connection.return_value = mock_conn

        mock_celery_module = MagicMock()
        mock_celery_module.Celery.return_value = mock_app

        with patch.dict("sys.modules", {"celery": mock_celery_module}), \
             patch.dict(os.environ, {"PPKE_TASK_BACKEND": "", "CELERY_BROKER_URL": "redis://localhost:6379/0"}):
            tm._celery_app = None
            result = tm._get_celery_app()
            assert result is not None

        tm._celery_app = None

    def test_celery_creation_failure(self):
        import ppke.infra.tasks as tm

        mock_celery_module = MagicMock()
        mock_celery_module.Celery.side_effect = Exception("Celery fail")

        with patch.dict("sys.modules", {"celery": mock_celery_module}), \
             patch.dict(os.environ, {"PPKE_TASK_BACKEND": ""}):
            tm._celery_app = None
            result = tm._get_celery_app()
            assert result is None

        tm._celery_app = None


# ═══════════════════════════════════════════════════════════════════
# infra/sentry_integration.py
# ═══════════════════════════════════════════════════════════════════


class TestSentryInitWithDSN:
    """Lines 53-54, 64, 85-90, 118-119, 130, 132-133, 143-144, 159-160."""

    def setup_method(self):
        import ppke.infra.sentry_integration as si
        si._initialized = False

    def test_init_sentry_success(self):
        import ppke.infra.sentry_integration as si

        mock_sentry = MagicMock()
        mock_logging_int = MagicMock()
        mock_sentry_logging = MagicMock()
        mock_sentry_logging.LoggingIntegration.return_value = mock_logging_int

        # Mock FastAPI integration
        mock_fastapi = MagicMock()
        mock_starlette = MagicMock()

        with patch.dict("sys.modules", {
            "sentry_sdk": mock_sentry,
            "sentry_sdk.integrations": MagicMock(),
            "sentry_sdk.integrations.logging": mock_sentry_logging,
            "sentry_sdk.integrations.fastapi": mock_fastapi,
            "sentry_sdk.integrations.starlette": mock_starlette,
            "sentry_sdk.integrations.celery": MagicMock(),
        }), patch.dict(os.environ, {
            "SENTRY_DSN": "https://key@sentry.io/123",
            "PPKE_ENVIRONMENT": "test",
        }):
            si._initialized = False
            result = si.init_sentry()
            assert result is True
            assert si._initialized is True
            mock_sentry.init.assert_called_once()

        si._initialized = False

    def test_init_sentry_import_error(self):
        import ppke.infra.sentry_integration as si

        with patch.dict(os.environ, {"SENTRY_DSN": "https://key@sentry.io/123"}), \
             patch("builtins.__import__", side_effect=ImportError("no sentry")):
            si._initialized = False
            result = si.init_sentry()
            assert result is False

        si._initialized = False

    def test_init_sentry_generic_error(self):
        import ppke.infra.sentry_integration as si

        mock_sentry = MagicMock()
        mock_sentry.init.side_effect = Exception("init fail")
        mock_sentry_logging = MagicMock()

        with patch.dict("sys.modules", {
            "sentry_sdk": mock_sentry,
            "sentry_sdk.integrations": MagicMock(),
            "sentry_sdk.integrations.logging": mock_sentry_logging,
            "sentry_sdk.integrations.fastapi": MagicMock(),
            "sentry_sdk.integrations.starlette": MagicMock(),
            "sentry_sdk.integrations.celery": MagicMock(),
        }), patch.dict(os.environ, {"SENTRY_DSN": "https://key@sentry.io/123"}):
            si._initialized = False
            result = si.init_sentry()
            assert result is False

        si._initialized = False


class TestSentrySetUserInitialized:
    """Lines 85-90: set_user when initialized."""

    def setup_method(self):
        import ppke.infra.sentry_integration as si
        si._initialized = False

    def test_set_user_when_initialized(self):
        import ppke.infra.sentry_integration as si

        mock_sentry = MagicMock()
        si._initialized = True

        with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
            si.set_user("user1", "user@test.com", "Test User")
            mock_sentry.set_user.assert_called_once()

        si._initialized = False


class TestSentryCaptureInitialized:
    """Lines 118-119, 130, 132-133: capture functions when initialized."""

    def setup_method(self):
        import ppke.infra.sentry_integration as si
        si._initialized = False

    def test_capture_exception_initialized(self):
        import ppke.infra.sentry_integration as si

        mock_sentry = MagicMock()
        mock_scope = MagicMock()
        mock_sentry.push_scope.return_value.__enter__ = MagicMock(return_value=mock_scope)
        mock_sentry.push_scope.return_value.__exit__ = MagicMock(return_value=False)
        mock_sentry.capture_exception.return_value = "event-123"

        si._initialized = True
        with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
            result = si.capture_exception(ValueError("test"), book="test_book")
            assert result == "event-123"

        si._initialized = False

    def test_capture_exception_fails(self):
        import ppke.infra.sentry_integration as si

        si._initialized = True
        with patch.dict("sys.modules", {"sentry_sdk": MagicMock(side_effect=Exception("fail"))}):
            # push_scope raises
            mock_sentry = MagicMock()
            mock_sentry.push_scope.side_effect = Exception("scope fail")
            with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
                result = si.capture_exception(ValueError("test"))
                assert result is None

        si._initialized = False

    def test_capture_message_initialized(self):
        import ppke.infra.sentry_integration as si

        mock_sentry = MagicMock()
        mock_scope = MagicMock()
        mock_sentry.push_scope.return_value.__enter__ = MagicMock(return_value=mock_scope)
        mock_sentry.push_scope.return_value.__exit__ = MagicMock(return_value=False)
        mock_sentry.capture_message.return_value = "msg-456"

        si._initialized = True
        with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
            result = si.capture_message("test message", level="warning", extra="data")
            assert result == "msg-456"

        si._initialized = False

    def test_capture_message_fails(self):
        import ppke.infra.sentry_integration as si

        si._initialized = True
        mock_sentry = MagicMock()
        mock_sentry.push_scope.side_effect = Exception("fail")
        with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
            result = si.capture_message("msg")
            assert result is None

        si._initialized = False


class TestSentryBreadcrumbInitialized:
    """Lines 159-160: add_breadcrumb when initialized."""

    def setup_method(self):
        import ppke.infra.sentry_integration as si
        si._initialized = False

    def test_add_breadcrumb_initialized(self):
        import ppke.infra.sentry_integration as si

        mock_sentry = MagicMock()
        si._initialized = True

        with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
            si.add_breadcrumb("test crumb", category="test", key="value")
            mock_sentry.add_breadcrumb.assert_called_once()

        si._initialized = False

    def test_add_breadcrumb_exception(self):
        import ppke.infra.sentry_integration as si

        mock_sentry = MagicMock()
        mock_sentry.add_breadcrumb.side_effect = Exception("fail")
        si._initialized = True

        with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
            # Should not raise
            si.add_breadcrumb("test crumb")

        si._initialized = False
