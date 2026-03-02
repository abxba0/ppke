"""Tests for ppke.audio — overview, rss, transcriber modules."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ═══════════════════════════════════════════════════════════════════
# audio/transcriber.py
# ═══════════════════════════════════════════════════════════════════


class TestFormatTimestamp:
    def test_seconds_only(self):
        from ppke.audio.transcriber import _format_timestamp
        assert _format_timestamp(45) == "00:45"

    def test_minutes_and_seconds(self):
        from ppke.audio.transcriber import _format_timestamp
        assert _format_timestamp(125) == "02:05"

    def test_hours(self):
        from ppke.audio.transcriber import _format_timestamp
        assert _format_timestamp(3661) == "01:01:01"

    def test_zero(self):
        from ppke.audio.transcriber import _format_timestamp
        assert _format_timestamp(0) == "00:00"

    def test_fractional(self):
        from ppke.audio.transcriber import _format_timestamp
        assert _format_timestamp(90.5) == "01:30"


class TestTranscribe:
    def test_requires_openai_api_key(self, tmp_path):
        """openai is installed but no API key, so it should raise OpenAIError."""
        from ppke.audio.transcriber import transcribe
        f = tmp_path / "test.mp3"
        f.write_bytes(b"fake audio")
        import os
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with pytest.raises(Exception):  # OpenAIError
                transcribe(f)
        finally:
            if old_key is not None:
                os.environ["OPENAI_API_KEY"] = old_key

    def test_transcribe_local_requires_whisper(self, tmp_path):
        from ppke.audio.transcriber import transcribe_local
        f = tmp_path / "test.mp3"
        f.write_bytes(b"fake audio")
        with pytest.raises(ImportError):
            transcribe_local(f)


# ═══════════════════════════════════════════════════════════════════
# audio/overview.py
# ═══════════════════════════════════════════════════════════════════


class TestVoicePresets:
    def test_presets_exist(self):
        from ppke.audio.overview import VOICE_PRESETS
        assert "natural" in VOICE_PRESETS
        assert "classic" in VOICE_PRESETS
        assert "professional" in VOICE_PRESETS

    def test_preset_structure(self):
        from ppke.audio.overview import VOICE_PRESETS
        for name, preset in VOICE_PRESETS.items():
            assert "provider" in preset
            assert "voice_a" in preset
            assert "voice_b" in preset
            assert "label" in preset


class TestLengthPresets:
    def test_presets(self):
        from ppke.audio.overview import LENGTH_PRESETS
        assert "short" in LENGTH_PRESETS
        assert "medium" in LENGTH_PRESETS
        assert "long" in LENGTH_PRESETS
        assert LENGTH_PRESETS["short"]["words"] < LENGTH_PRESETS["medium"]["words"]


class TestScriptToTranscript:
    def test_basic(self):
        from ppke.audio.overview import script_to_transcript
        script = [
            {"speaker": "HOST_A", "text": "Hello everyone!"},
            {"speaker": "HOST_B", "text": "Welcome to the show."},
        ]
        result = script_to_transcript(script)
        assert "Host A" in result
        assert "Host B" in result
        assert "Hello everyone!" in result

    def test_empty_script(self):
        from ppke.audio.overview import script_to_transcript
        result = script_to_transcript([])
        assert "# Audio Overview Transcript" in result


class TestGenerateScript:
    def test_generate_script(self, tmp_path):
        from ppke.audio.overview import generate_script
        book = tmp_path / "Book_Test"
        book.mkdir()
        (book / "meta.yml").write_text(yaml.dump({"title": "Test", "author": "Auth"}))
        (book / "03_Concept_Index.md").write_text("# Concepts\n- C1")
        (book / "02_Logical_Map.md").write_text("# Logic\n- L1")
        (book / "06_Patterns.md").write_text("# Patterns\n- P1")

        mock_llm = MagicMock()
        mock_llm.complete_json.return_value = [
            {"speaker": "HOST_A", "text": "Hello!"},
            {"speaker": "HOST_B", "text": "Hi!"},
        ]
        result = generate_script(book, mock_llm)
        assert len(result) == 2
        assert result[0]["speaker"] == "HOST_A"

    def test_generate_script_with_topic(self, tmp_path):
        from ppke.audio.overview import generate_script
        book = tmp_path / "Book_T2"
        book.mkdir()
        (book / "meta.yml").write_text(yaml.dump({"title": "T2", "author": "A"}))

        mock_llm = MagicMock()
        mock_llm.complete_json.return_value = [{"speaker": "HOST_A", "text": "Topic!"}]
        result = generate_script(book, mock_llm, topic="Ethics", length="short")
        assert len(result) == 1

    def test_generate_script_dict_response(self, tmp_path):
        from ppke.audio.overview import generate_script
        book = tmp_path / "Book_T3"
        book.mkdir()
        (book / "meta.yml").write_text(yaml.dump({"title": "T3", "author": "A"}))

        mock_llm = MagicMock()
        mock_llm.complete_json.return_value = {"script": [{"speaker": "HOST_A", "text": "Test"}]}
        result = generate_script(book, mock_llm)
        assert len(result) == 1

    def test_generate_script_bad_format(self, tmp_path):
        from ppke.audio.overview import generate_script
        book = tmp_path / "Book_T4"
        book.mkdir()
        (book / "meta.yml").write_text(yaml.dump({"title": "T4", "author": "A"}))

        mock_llm = MagicMock()
        mock_llm.complete_json.return_value = "not a list or dict"
        with pytest.raises(ValueError, match="Unexpected"):
            generate_script(book, mock_llm)


class TestGenerateCrossBookScript:
    def test_cross_book_script(self, tmp_path):
        from ppke.audio.overview import generate_cross_book_script
        book_a = tmp_path / "Book_A"
        book_a.mkdir()
        (book_a / "meta.yml").write_text(yaml.dump({"title": "A", "author": "AuthA"}))
        (book_a / "03_Concept_Index.md").write_text("# C")
        (book_a / "02_Logical_Map.md").write_text("# L")

        book_b = tmp_path / "Book_B"
        book_b.mkdir()
        (book_b / "meta.yml").write_text(yaml.dump({"title": "B", "author": "AuthB"}))
        (book_b / "03_Concept_Index.md").write_text("# C2")
        (book_b / "02_Logical_Map.md").write_text("# L2")

        mock_llm = MagicMock()
        mock_llm.complete_json.return_value = [
            {"speaker": "HOST_A", "text": "Compare!"},
            {"speaker": "HOST_B", "text": "Contrast!"},
        ]
        result = generate_cross_book_script(book_a, book_b, mock_llm)
        assert len(result) == 2

    def test_cross_book_dict_response(self, tmp_path):
        from ppke.audio.overview import generate_cross_book_script
        book_a = tmp_path / "Book_A2"
        book_a.mkdir()
        (book_a / "meta.yml").write_text(yaml.dump({"title": "A2", "author": "A"}))
        book_b = tmp_path / "Book_B2"
        book_b.mkdir()
        (book_b / "meta.yml").write_text(yaml.dump({"title": "B2", "author": "B"}))

        mock_llm = MagicMock()
        mock_llm.complete_json.return_value = {"script": [{"speaker": "HOST_A", "text": "T"}]}
        result = generate_cross_book_script(book_a, book_b, mock_llm, length="long")
        assert len(result) == 1


class TestSynthesizeAudio:
    def test_unsupported_provider(self, tmp_path):
        from ppke.audio.overview import synthesize_audio
        with pytest.raises(ValueError, match="Unsupported"):
            synthesize_audio([], tmp_path / "out.mp3", provider="unknown")

    def test_openai_requires_openai(self, tmp_path):
        from ppke.audio.overview import synthesize_audio
        with pytest.raises(ImportError):
            synthesize_audio(
                [{"speaker": "HOST_A", "text": "Hello"}],
                tmp_path / "out.mp3",
                provider="openai",
            )

    def test_edge_requires_edge_tts(self, tmp_path):
        from ppke.audio.overview import synthesize_audio
        with pytest.raises(ImportError):
            synthesize_audio(
                [{"speaker": "HOST_A", "text": "Hello"}],
                tmp_path / "out.mp3",
                provider="edge",
            )

    def test_synthesize_from_preset(self, tmp_path):
        from ppke.audio.overview import synthesize_from_preset
        # Should try "natural" preset which uses edge, and fail without edge-tts
        with pytest.raises(ImportError):
            synthesize_from_preset(
                [{"speaker": "HOST_A", "text": "Hello"}],
                tmp_path / "out.mp3",
                preset_name="natural",
            )


# ═══════════════════════════════════════════════════════════════════
# audio/rss.py
# ═══════════════════════════════════════════════════════════════════


class TestParseDuration:
    def test_hms(self):
        from ppke.audio.rss import _parse_duration
        assert _parse_duration("1:30:45") == 5445

    def test_ms(self):
        from ppke.audio.rss import _parse_duration
        assert _parse_duration("30:45") == 1845

    def test_seconds_only(self):
        from ppke.audio.rss import _parse_duration
        assert _parse_duration("120") == 120

    def test_empty(self):
        from ppke.audio.rss import _parse_duration
        assert _parse_duration("") is None

    def test_invalid(self):
        from ppke.audio.rss import _parse_duration
        assert _parse_duration("abc") is None


class TestParseFeed:
    def test_requires_feedparser(self):
        from ppke.audio.rss import parse_feed
        with pytest.raises(ImportError):
            parse_feed("https://example.com/feed")


class TestDownloadAndTranscribe:
    def test_function_exists(self):
        from ppke.audio.rss import download_and_transcribe
        assert callable(download_and_transcribe)


# ═══════════════════════════════════════════════════════════════════
# audio/diarization.py
# ═══════════════════════════════════════════════════════════════════


class TestFormatTs:
    def test_seconds(self):
        from ppke.audio.diarization import _format_ts
        assert _format_ts(45) == "00:45"

    def test_minutes(self):
        from ppke.audio.diarization import _format_ts
        assert _format_ts(125) == "02:05"

    def test_hours(self):
        from ppke.audio.diarization import _format_ts
        assert _format_ts(3661) == "01:01:01"


class TestDiarize:
    def test_requires_pyannote(self, tmp_path):
        from ppke.audio.diarization import diarize
        f = tmp_path / "test.wav"
        f.write_bytes(b"fake audio")
        with pytest.raises(ImportError, match="pyannote"):
            diarize(f, hf_token="fake")

    def test_requires_hf_token(self, tmp_path, monkeypatch):
        from ppke.audio.diarization import diarize
        monkeypatch.delenv("HF_TOKEN", raising=False)
        f = tmp_path / "test.wav"
        f.write_bytes(b"fake audio")
        # Mock pyannote so ImportError is not raised
        mock_pipeline = MagicMock()
        with patch.dict("sys.modules", {"pyannote": MagicMock(), "pyannote.audio": mock_pipeline}):
            with pytest.raises(ValueError, match="Hugging Face token"):
                diarize(f)


class TestMergeTranscriptionDiarization:
    def test_basic_merge(self):
        from ppke.audio.diarization import merge_transcription_diarization
        transcript = [
            {"start": 0.0, "end": 5.0, "text": "Hello world"},
            {"start": 5.0, "end": 10.0, "text": "How are you"},
        ]
        diar = [
            {"speaker": "SPEAKER_00", "start": 0.0, "end": 6.0},
            {"speaker": "SPEAKER_01", "start": 6.0, "end": 12.0},
        ]
        merged = merge_transcription_diarization(transcript, diar)
        assert len(merged) == 2
        assert merged[0]["speaker"] == "SPEAKER_00"
        assert merged[0]["text"] == "Hello world"
        assert merged[1]["speaker"] == "SPEAKER_01"

    def test_empty_diarization(self):
        from ppke.audio.diarization import merge_transcription_diarization
        transcript = [{"start": 0.0, "end": 5.0, "text": "Hi"}]
        merged = merge_transcription_diarization(transcript, [])
        assert merged[0]["speaker"] == "UNKNOWN"

    def test_does_not_mutate(self):
        from ppke.audio.diarization import merge_transcription_diarization
        transcript = [{"start": 0.0, "end": 5.0, "text": "Hi"}]
        diar = [{"speaker": "S1", "start": 0.0, "end": 5.0}]
        merge_transcription_diarization(transcript, diar)
        assert "speaker" not in transcript[0]


class TestFormatDiarizedTranscript:
    def test_basic_format(self):
        from ppke.audio.diarization import format_diarized_transcript
        segments = [
            {"speaker": "SPEAKER_00", "start": 0.0, "text": "Hello"},
            {"speaker": "SPEAKER_01", "start": 5.0, "text": "Hi there"},
        ]
        result = format_diarized_transcript(segments, title="Test")
        assert "# Test" in result
        assert "Speaker 1" in result
        assert "Speaker 2" in result
        assert "Hello" in result
        assert "Hi there" in result

    def test_empty_segments(self):
        from ppke.audio.diarization import format_diarized_transcript
        result = format_diarized_transcript([])
        assert "# Diarized Transcript" in result

    def test_with_source(self):
        from ppke.audio.diarization import format_diarized_transcript
        result = format_diarized_transcript([], source="audio.mp3")
        assert "audio.mp3" in result


class TestDiarizationPersistence:
    def test_save_and_load(self, tmp_path):
        from ppke.audio.diarization import save_diarization, load_diarization
        segments = [
            {"speaker": "S1", "start": 0.0, "end": 5.0},
            {"speaker": "S2", "start": 5.0, "end": 10.0},
        ]
        path = tmp_path / "diarization.json"
        save_diarization(segments, path)
        loaded = load_diarization(path)
        assert loaded == segments
