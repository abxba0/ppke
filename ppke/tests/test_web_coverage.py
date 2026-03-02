"""Additional tests for ppke.web.app — covering uncovered routes.

Targets uncovered lines in web/app.py: auth flows, api_query, streaming,
upload, import-url, summary, study-guide, audio, RSS, export, stats, graph.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import yaml
from starlette.testclient import TestClient


# ── Shared fixtures ──

_FAKE_USER = {
    "id": "user-001",
    "email": "test@example.com",
    "name": "Test User",
    "role": "admin",
    "password_hash": "pbkdf2:salt:hash",
    "created_at": "2025-01-01T00:00:00",
}


def _fake_get_optional_user(user=_FAKE_USER):
    async def _inner(request):
        return user
    return _inner


@pytest.fixture()
def tmp_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    book = vault / "Book_TestBook"
    book.mkdir()
    meta = {
        "title": "Test Book",
        "author": "Test Author",
        "year": 2025,
        "total_chapters": 3,
        "total_paragraphs": 30,
        "verification_status": "VERIFIED",
        "ingest_date": "2025-01-01",
    }
    (book / "meta.yml").write_text(yaml.dump(meta))
    (book / "01_Raw_Structure.md").write_text("# Chapter 1\n\nSome content.")
    (book / "02_Logical_Map.md").write_text("# Logical Map\n\n- Point A\n- Point B")
    (book / "03_Concept_Index.md").write_text("# Concepts\n\n- Concept1\n- Concept2")
    (book / "06_Patterns.md").write_text("# Patterns\n\n- Pattern1")
    (book / "extractions.json").write_text(json.dumps([{
        "paragraph_id": "{01}.{01}",
        "topic_sentence": "Test topic",
        "defined_concepts": ["concept1"],
        "explicit_claims": ["Claim one about something important enough"],
        "implicit_assumptions": ["Assumption about something important enough"],
        "logical_steps": ["Step 1", "Step 2"],
    }]))
    return vault


def _make_mock_db():
    db = MagicMock()
    return db


@pytest.fixture()
def client(tmp_vault):
    from ppke.web import app as app_module
    from ppke.auth import deps

    real_app = app_module.app
    real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
    real_app.dependency_overrides[deps.get_optional_user] = lambda: _FAKE_USER

    mock_db = _make_mock_db()

    with patch.object(app_module, "_vault_path", return_value=tmp_vault), \
         patch.object(app_module, "_user_vault_path", return_value=tmp_vault), \
         patch.object(app_module, "_try_get_user", new=_fake_get_optional_user()), \
         patch.object(app_module, "_get_db", return_value=mock_db):
        yield TestClient(real_app, raise_server_exceptions=False)

    real_app.dependency_overrides.clear()


# ── Error handler tests ──


class TestErrorHandlers:
    def test_general_exception_handler(self, tmp_vault):
        """Lines 98-100: general_exception_handler catches unhandled errors."""
        from ppke.web import app as app_module
        from ppke.auth import deps

        real_app = app_module.app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        real_app.dependency_overrides[deps.get_optional_user] = lambda: _FAKE_USER

        # Use a cache mock that always misses, so _book_dirs is reached
        cache_mock = MagicMock()
        cache_mock.get.return_value = None

        with patch.object(app_module, "_vault_path", return_value=tmp_vault), \
             patch.object(app_module, "_user_vault_path", return_value=tmp_vault), \
             patch.object(app_module, "_try_get_user", new=_fake_get_optional_user()), \
             patch.object(app_module, "_get_db", return_value=MagicMock()), \
             patch("ppke.web.app.get_cache", return_value=cache_mock), \
             patch.object(app_module, "_book_dirs", side_effect=RuntimeError("boom")):
            tc = TestClient(real_app, raise_server_exceptions=False)
            resp = tc.get("/api/stats")
            assert resp.status_code == 500

        real_app.dependency_overrides.clear()


# ── Auth login success ──


class TestAuthLoginSuccess:
    def test_login_sets_cookie(self, tmp_vault):
        """Lines 265-271: successful login sets ppke_token cookie."""
        from ppke.web import app as app_module
        from ppke.auth import deps

        real_app = app_module.app
        real_app.dependency_overrides.clear()

        fake_user = {**_FAKE_USER, "password_hash": "hashed"}
        mock_db = MagicMock()

        with patch.object(app_module, "_vault_path", return_value=tmp_vault), \
             patch.object(app_module, "_user_vault_path", return_value=tmp_vault), \
             patch.object(app_module, "_try_get_user", new=_fake_get_optional_user(None)), \
             patch.object(app_module, "_get_db", return_value=mock_db), \
             patch("ppke.web.app.auth_db") as mock_auth_db, \
             patch("ppke.web.app.verify_password", return_value=True), \
             patch("ppke.web.app.create_token", return_value="fake-jwt-token"):
            mock_auth_db.get_user_by_email.return_value = fake_user
            mock_auth_db.log_activity = MagicMock()

            tc = TestClient(real_app, raise_server_exceptions=False)
            resp = tc.post(
                "/auth/login",
                data={"email": "test@example.com", "password": "password123"},
                follow_redirects=False,
            )
            assert resp.status_code == 303
            assert "ppke_token" in resp.headers.get("set-cookie", "")

        real_app.dependency_overrides.clear()


# ── Auth register success ──


class TestAuthRegisterSuccess:
    def test_register_creates_user_and_sets_cookie(self, tmp_vault):
        """Lines 292-308: successful registration."""
        from ppke.web import app as app_module
        from ppke.auth import deps

        real_app = app_module.app
        real_app.dependency_overrides.clear()

        mock_db = MagicMock()
        new_user = {**_FAKE_USER, "id": "new-user-id"}

        with patch.object(app_module, "_vault_path", return_value=tmp_vault), \
             patch.object(app_module, "_user_vault_path", return_value=tmp_vault), \
             patch.object(app_module, "_try_get_user", new=_fake_get_optional_user(None)), \
             patch.object(app_module, "_get_db", return_value=mock_db), \
             patch("ppke.web.app.auth_db") as mock_auth_db, \
             patch("ppke.web.app.hash_password", return_value="hashed-pw"), \
             patch("ppke.web.app.create_token", return_value="new-jwt-token"):
            mock_auth_db.get_user_by_email.return_value = None
            mock_auth_db.create_user.return_value = new_user
            mock_auth_db.log_activity = MagicMock()

            tc = TestClient(real_app, raise_server_exceptions=False)
            resp = tc.post(
                "/auth/register",
                data={
                    "name": "New User",
                    "email": "new@example.com",
                    "password": "password123",
                    "password_confirm": "password123",
                },
                follow_redirects=False,
            )
            assert resp.status_code == 303
            assert "ppke_token" in resp.headers.get("set-cookie", "")
            mock_auth_db.create_user.assert_called_once()

        real_app.dependency_overrides.clear()


# ── api_auth_me ──


class TestApiAuthMe:
    def test_returns_user_info(self, tmp_vault):
        """Lines 346-349: api_auth_me with DB calls."""
        from ppke.web import app as app_module
        from ppke.auth import deps

        real_app = app_module.app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER

        mock_db = MagicMock()

        with patch.object(app_module, "_get_db", return_value=mock_db), \
             patch("ppke.web.app.auth_db") as mock_auth_db:
            mock_auth_db.get_user_workspaces.return_value = [
                {"id": "ws-1", "name": "Workspace 1", "member_role": "admin"}
            ]
            mock_auth_db.get_user_usage.return_value = {"queries": 10}

            tc = TestClient(real_app, raise_server_exceptions=False)
            resp = tc.get("/api/auth/me")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == "user-001"
            assert data["email"] == "test@example.com"
            assert len(data["workspaces"]) == 1
            assert data["usage"]["queries"] == 10

        real_app.dependency_overrides.clear()


# ── Dashboard with shared books ──


class TestDashboardSharedBooks:
    def test_dashboard_includes_shared_books(self, tmp_vault):
        """Lines 387-388: dashboard loads shared books from workspaces."""
        from ppke.web import app as app_module
        from ppke.auth import deps

        real_app = app_module.app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        real_app.dependency_overrides[deps.get_optional_user] = lambda: _FAKE_USER

        mock_db = MagicMock()

        with patch.object(app_module, "_vault_path", return_value=tmp_vault), \
             patch.object(app_module, "_user_vault_path", return_value=tmp_vault), \
             patch.object(app_module, "_try_get_user", new=_fake_get_optional_user()), \
             patch.object(app_module, "_get_db", return_value=mock_db), \
             patch("ppke.web.app.auth_db") as mock_auth_db:
            mock_auth_db.get_user_workspaces.return_value = [
                {"id": "ws-1", "name": "Team WS", "member_role": "editor"}
            ]
            mock_auth_db.get_shared_books.return_value = [
                {"book_folder": "Book_Shared", "shared_by_name": "Alice", "permissions": "read"}
            ]

            tc = TestClient(real_app, raise_server_exceptions=False)
            resp = tc.get("/")
            assert resp.status_code == 200

        real_app.dependency_overrides.clear()


# ── api_query ──


class TestApiQuery:
    def test_query_returns_answer(self, client, tmp_vault):
        """Lines 597-646: api_query calls LLMClient.complete_json."""
        mock_result = {
            "answer": "The book discusses philosophy.",
            "verbatim_quotes": ["quote1"],
            "confidence": "high",
            "follow_up_questions": ["Q1?", "Q2?", "Q3?"],
        }
        with patch("ppke.llm.client.LLMClient") as MockLLM, \
             patch("ppke.web.app._rag_context_block", return_value=([], "")):
            MockLLM.return_value.complete_json.return_value = mock_result
            resp = client.post(
                "/api/query",
                data={"book": "Book_TestBook", "question": "What is it about?"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "The book discusses philosophy."
        assert data["rag_sources"] == 0

    def test_query_with_rag_hits(self, client, tmp_vault):
        """Lines 225-234: RAG search block."""
        mock_result = {
            "answer": "Answer with RAG.",
            "verbatim_quotes": [],
            "confidence": "high",
            "follow_up_questions": [],
        }
        rag_hits = [{"paragraph_id": "{01}.{01}", "document": "RAG content here"}]
        with patch("ppke.llm.client.LLMClient") as MockLLM, \
             patch("ppke.web.app._rag_context_block", return_value=(rag_hits, "RAG BLOCK")):
            MockLLM.return_value.complete_json.return_value = mock_result
            resp = client.post(
                "/api/query",
                data={"book": "Book_TestBook", "question": "Tell me more"},
            )
        assert resp.status_code == 200
        assert resp.json()["rag_sources"] == 1


# ── api_query_stream ──


class TestApiQueryStream:
    def test_stream_returns_sse_events(self, client, tmp_vault):
        """Lines 665-753: SSE streaming endpoint."""
        mock_result = {
            "answer": "Streaming answer from LLM.",
            "verbatim_quotes": ["a quote"],
            "confidence": "high",
            "follow_up_questions": ["Q1?"],
        }
        with patch("ppke.llm.client.LLMClient") as MockLLM, \
             patch("ppke.web.app._rag_context_block", return_value=([], "")):
            mock_client = MockLLM.return_value
            mock_client.complete_json.return_value = mock_result
            # No complete_stream to trigger fallback chunking
            del mock_client.complete_stream

            resp = client.get(
                "/api/query/stream",
                params={"book": "Book_TestBook", "question": "What is this?"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "data:" in body
        assert "[DONE]" in body


# ── api_upload ──


class TestApiUpload:
    def test_upload_single_file(self, client, tmp_vault):
        """Lines 831-920: file upload with convert_to_markdown."""
        with patch("ppke.converter.convert_to_markdown", return_value="# Uploaded\n\nContent"), \
             patch("ppke.web.app.create_job", return_value="job-upload-1"), \
             patch("ppke.web.app.run_task"):
            resp = client.post(
                "/api/upload",
                files=[("files", ("test.pdf", b"fake pdf content", "application/pdf"))],
                data={"title": "Test Upload", "author": "Author", "year": "2025", "domain": "philosophy"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job-upload-1"
        assert data["status"] == "running"

    def test_upload_multiple_files(self, client, tmp_vault):
        """Multiple files return jobs list."""
        with patch("ppke.converter.convert_to_markdown", return_value="# Content"), \
             patch("ppke.web.app.create_job", side_effect=["job-1", "job-2"]), \
             patch("ppke.web.app.run_task"):
            resp = client.post(
                "/api/upload",
                files=[
                    ("files", ("a.pdf", b"content a", "application/pdf")),
                    ("files", ("b.pdf", b"content b", "application/pdf")),
                ],
                data={"title": "Batch", "author": "Author"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["jobs"]) == 2


# ── api_import_url ──


class TestApiImportUrl:
    def test_import_web_url(self, client, tmp_vault):
        """Lines 939-1037: URL import (non-YouTube)."""
        with patch("ppke.converter.url.is_youtube_url", return_value=False), \
             patch("ppke.web.app.create_job", return_value="job-url-1"), \
             patch("ppke.web.app.run_task"):
            resp = client.post(
                "/api/import-url",
                data={"url": "https://example.com/article", "title": "Article", "author": "Auth"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job-url-1"
        assert data["source_type"] == "web"

    def test_import_youtube_url(self, client, tmp_vault):
        """YouTube URL detected properly."""
        with patch("ppke.converter.url.is_youtube_url", return_value=True), \
             patch("ppke.web.app.create_job", return_value="job-yt-1"), \
             patch("ppke.web.app.run_task"):
            resp = client.post(
                "/api/import-url",
                data={"url": "https://www.youtube.com/watch?v=abc123"},
            )
        assert resp.status_code == 200
        assert resp.json()["source_type"] == "youtube"

    def test_import_bad_url(self, client):
        """Invalid URL returns 400."""
        resp = client.post("/api/import-url", data={"url": "not-a-url"})
        assert resp.status_code == 400


# ── api_import_zotero ──


class TestApiImportZotero:
    def test_import_bibtex(self, client, tmp_vault):
        """Zotero BibTeX import parses and starts ingestion."""
        bib_content = b'@article{k1, author={Alice}, title={Test Paper}, year={2023}}'
        with patch("ppke.web.app.create_job", return_value="job-zot-1"), \
             patch("ppke.web.app.run_task"):
            resp = client.post(
                "/api/import-zotero",
                files={"file": ("refs.bib", bib_content, "application/x-bibtex")},
                data={"domain": "science"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job-zot-1"
        assert data["source_type"] == "zotero"
        assert data["entries"] == 1

    def test_import_empty_file(self, client, tmp_vault):
        """Empty Zotero file returns 400."""
        with patch("ppke.web.app.create_job", return_value="job-zot-2"), \
             patch("ppke.web.app.run_task"):
            resp = client.post(
                "/api/import-zotero",
                files={"file": ("empty.bib", b"% comment only\n", "application/x-bibtex")},
                data={"domain": "philosophy"},
            )
        assert resp.status_code == 400


# ── api_generate_summary ──


class TestApiGenerateSummary:
    def test_generate_summary(self, client, tmp_vault):
        """Lines 1560-1616: generates summary with LLM."""
        with patch("ppke.llm.client.LLMClient") as MockLLM:
            MockLLM.return_value.complete.return_value = "# Summary\n\nGreat book."
            resp = client.post("/api/summary/Book_TestBook")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert "Summary" in data["content"]
        # Check file was written
        assert (tmp_vault / "Book_TestBook" / "summary.md").exists()


# ── api_generate_study_guide ──


class TestApiGenerateStudyGuide:
    def test_generate_study_guide(self, client, tmp_vault):
        """Lines 1622-1679: generates study guide with LLM."""
        with patch("ppke.llm.client.LLMClient") as MockLLM:
            MockLLM.return_value.complete.return_value = "# Study Guide\n\nChapter 1..."
            resp = client.post("/api/study-guide/Book_TestBook")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert "Study Guide" in data["content"]

    def test_study_guide_cached(self, client, tmp_vault):
        """Returns cached guide if it already exists."""
        guide_path = tmp_vault / "Book_TestBook" / "study_guide.md"
        guide_path.write_text("# Cached Guide")
        resp = client.post("/api/study-guide/Book_TestBook")
        assert resp.status_code == 200
        assert resp.json()["content"] == "# Cached Guide"


# ── Export PDF / DOCX ──


class TestExportPdfDocx:
    def test_export_pdf(self, client, tmp_vault):
        """Lines 1911-1914: PDF export."""
        with patch("ppke.export.exporters.export_pdf", return_value=b"%PDF-fake"):
            resp = client.get("/api/export/Book_TestBook/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"

    def test_export_pdf_html_fallback(self, client, tmp_vault):
        """PDF export falls back to HTML when not real PDF."""
        with patch("ppke.export.exporters.export_pdf", return_value=b"<html>report</html>"):
            resp = client.get("/api/export/Book_TestBook/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/html; charset=utf-8"

    def test_export_pdf_import_error(self, client, tmp_vault):
        """PDF export handles ImportError."""
        with patch("ppke.export.exporters.export_pdf", side_effect=ImportError("no weasyprint")):
            resp = client.get("/api/export/Book_TestBook/pdf")
        assert resp.status_code == 500

    def test_export_docx(self, client, tmp_vault):
        """Lines 1939, 1947-1955: DOCX export."""
        with patch("ppke.export.exporters.export_docx", return_value=b"PK\x03\x04fake-docx"):
            resp = client.get("/api/export/Book_TestBook/docx")
        assert resp.status_code == 200
        assert "wordprocessingml" in resp.headers["content-type"]

    def test_export_docx_error(self, client, tmp_vault):
        """DOCX export handles general exception."""
        with patch("ppke.export.exporters.export_docx", side_effect=RuntimeError("fail")):
            resp = client.get("/api/export/Book_TestBook/docx")
        assert resp.status_code == 500


# ── Audio overview generation ──


class TestAudioOverview:
    def test_generate_audio_overview(self, client, tmp_vault):
        """Lines 1174-1213: audio overview generation."""
        mock_script = [{"speaker": "host", "text": "Welcome to the overview."}]
        with patch("ppke.llm.client.LLMClient") as MockLLM, \
             patch("ppke.audio.overview.generate_script", return_value=mock_script), \
             patch("ppke.audio.overview.VOICE_PRESETS", {"natural": {"label": "Natural", "provider": "edge"}}), \
             patch("ppke.audio.overview.synthesize_from_preset") as mock_synth:
            resp = client.post(
                "/api/audio-overview",
                data={"folder": "Book_TestBook", "voice_preset": "natural"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["script"] == mock_script


# ── Cross-book audio ──


class TestCrossBookAudio:
    def test_generate_cross_book_audio(self, tmp_vault):
        """Lines 1229-1266: cross-book audio generation."""
        # Create second book
        book_b = tmp_vault / "Book_SecondBook"
        book_b.mkdir()
        meta_b = {"title": "Second Book", "author": "Author B", "year": 2024}
        (book_b / "meta.yml").write_text(yaml.dump(meta_b))

        from ppke.web import app as app_module
        from ppke.auth import deps

        real_app = app_module.app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        real_app.dependency_overrides[deps.get_optional_user] = lambda: _FAKE_USER

        mock_script = [{"speaker": "host", "text": "Comparing books."}]
        with patch.object(app_module, "_vault_path", return_value=tmp_vault), \
             patch.object(app_module, "_user_vault_path", return_value=tmp_vault), \
             patch.object(app_module, "_try_get_user", new=_fake_get_optional_user()), \
             patch.object(app_module, "_get_db", return_value=MagicMock()), \
             patch("ppke.llm.client.LLMClient"), \
             patch("ppke.audio.overview.generate_cross_book_script", return_value=mock_script), \
             patch("ppke.audio.overview.synthesize_from_preset"):
            tc = TestClient(real_app, raise_server_exceptions=False)
            resp = tc.post(
                "/api/audio-overview/cross-book",
                data={"folder_a": "Book_TestBook", "folder_b": "Book_SecondBook"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["folder"] == "Book_TestBook"

        real_app.dependency_overrides.clear()


# ── RSS import ──


class TestRssImport:
    def test_import_rss(self):
        """Lines 1312-1330: RSS import endpoint."""
        from ppke.web import app as app_module
        from ppke.auth import deps

        real_app = app_module.app

        feed_info = {
            "title": "Test Podcast",
            "author": "Podcaster",
            "episodes": [
                {"title": "Ep 1", "url": "https://example.com/ep1.mp3"},
            ],
        }

        with patch("ppke.audio.rss.parse_feed", return_value=feed_info), \
             patch("ppke.web.app._start_rss_episode_job", return_value="job-rss-1"):
            tc = TestClient(real_app, raise_server_exceptions=False)
            resp = tc.post(
                "/api/import-rss",
                data={"rss_url": "https://example.com/feed.xml", "max_episodes": "2"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["podcast"] == "Test Podcast"
        assert len(data["jobs"]) == 1

    def test_import_rss_no_episodes(self):
        """RSS with no episodes returns 400."""
        from ppke.web import app as app_module

        real_app = app_module.app
        feed_info = {"title": "Empty Pod", "author": "X", "episodes": []}

        with patch("ppke.audio.rss.parse_feed", return_value=feed_info):
            tc = TestClient(real_app, raise_server_exceptions=False)
            resp = tc.post(
                "/api/import-rss",
                data={"rss_url": "https://example.com/feed.xml"},
            )
        assert resp.status_code == 400


# ── Upload recording ──


class TestUploadRecording:
    def test_upload_recording(self):
        """Lines 1398-1454: audio recording upload."""
        from ppke.web import app as app_module

        real_app = app_module.app

        with patch("ppke.web.app.create_job", return_value="job-rec-1"), \
             patch("ppke.web.app.run_task"):
            tc = TestClient(real_app, raise_server_exceptions=False)
            resp = tc.post(
                "/api/audio/upload-recording",
                files=[("recording", ("recording.webm", b"fake audio", "audio/webm"))],
                data={"title": "My Recording", "author": "Me"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job-rec-1"
        assert data["status"] == "running"


# ── Stats endpoint ──


class TestApiStats:
    def test_stats_returns_counts(self, client, tmp_vault):
        """Lines 1058-1060: stats endpoint with cache miss."""
        with patch("ppke.web.app.get_cache") as mock_cache:
            mock_cache.return_value.get.return_value = None
            resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_books"] == 1
        assert data["total_chapters"] == 3
        assert data["total_concepts"] == 1

    def test_stats_cache_hit(self, client, tmp_vault):
        """Lines 1058-1060: stats with cache hit."""
        cached_data = {"total_books": 5, "total_chapters": 10,
                       "total_paragraphs": 100, "total_concepts": 50,
                       "vault_path": "/cached"}
        with patch("ppke.web.app.get_cache") as mock_cache:
            mock_cache.return_value.get.return_value = cached_data
            resp = client.get("/api/stats")
        assert resp.status_code == 200
        assert resp.json()["total_books"] == 5


# ── Graph data endpoint ──


class TestApiGraphData:
    def test_graph_from_knowledge_graph_json(self, client, tmp_vault):
        """Lines 1101-1109: graph data with book filter."""
        graph_data = {
            "nodes": [
                {"id": "concept:a", "label": "A", "type": "concept"},
                {"id": "concept:b", "label": "B", "type": "concept"},
            ],
            "edges": [
                {"src": "concept:a", "dst": "concept:b", "rel": "related_to"},
            ],
        }
        (tmp_vault / "knowledge_graph.json").write_text(json.dumps(graph_data))
        resp = client.get("/api/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 2

    def test_graph_with_book_filter(self, client, tmp_vault):
        """Graph filtered by book name."""
        graph_data = {
            "nodes": [
                {"id": "Book_TestBook:ch1", "label": "Ch1", "type": "paragraph"},
                {"id": "other:node", "label": "Other", "type": "concept"},
            ],
            "edges": [
                {"src": "Book_TestBook:ch1", "dst": "other:node", "rel": "defines"},
            ],
        }
        (tmp_vault / "knowledge_graph.json").write_text(json.dumps(graph_data))
        resp = client.get("/api/graph", params={"book": "Book_TestBook"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 2
        assert len(data["links"]) == 1


# ── RAG context block ──


class TestRagContextBlock:
    def test_rag_context_block_with_hits(self, tmp_vault):
        """Lines 225-234: _rag_context_block returns formatted block."""
        from ppke.web.app import _rag_context_block

        mock_config = MagicMock()
        mock_config.vault_path = tmp_vault
        mock_hits = [
            {"paragraph_id": "{01}.{01}", "document": "Some relevant text from the book"},
        ]

        with patch("ppke.vectordb.store.VectorStore") as MockVS:
            mock_store = MockVS.return_value
            mock_store.available = True
            mock_store.search.return_value = mock_hits
            hits, block = _rag_context_block("Book_TestBook", "question?", mock_config)

        assert len(hits) == 1
        assert "SEMANTICALLY RELEVANT PASSAGES" in block

    def test_rag_context_block_unavailable(self, tmp_vault):
        """RAG gracefully returns empty when unavailable."""
        from ppke.web.app import _rag_context_block

        mock_config = MagicMock()
        mock_config.vault_path = tmp_vault

        with patch("ppke.vectordb.store.VectorStore") as MockVS:
            mock_store = MockVS.return_value
            mock_store.available = False
            hits, block = _rag_context_block("Book_TestBook", "q?", mock_config)

        assert hits == []
        assert block == ""

    def test_rag_context_block_exception(self, tmp_vault):
        """RAG gracefully handles exceptions."""
        from ppke.web.app import _rag_context_block

        mock_config = MagicMock()
        mock_config.vault_path = tmp_vault

        with patch("ppke.vectordb.store.VectorStore", side_effect=RuntimeError("no chroma")):
            hits, block = _rag_context_block("Book_TestBook", "q?", mock_config)

        assert hits == []
        assert block == ""


# ── _start_rss_episode_job ──


class TestStartRssEpisodeJob:
    def test_starts_job(self):
        """Lines 1342-1387: _start_rss_episode_job creates and runs background job."""
        from ppke.web.app import _start_rss_episode_job

        episode = {"title": "Episode 1", "url": "https://example.com/ep1.mp3"}

        with patch("ppke.web.app.create_job", return_value="job-rss-ep-1"), \
             patch("ppke.web.app.run_task") as mock_run:
            job_id = _start_rss_episode_job(episode, "Podcast", "Author", "philosophy")

        assert job_id == "job-rss-ep-1"
        mock_run.assert_called_once()
