"""Tests for ppke.web.app — FastAPI routes and helpers.

Uses Starlette TestClient against the real FastAPI app with mocked
auth and database dependencies.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import yaml
from starlette.testclient import TestClient


# ── Fixtures ──

_FAKE_USER = {
    "id": "user-001",
    "email": "test@example.com",
    "name": "Test User",
    "role": "admin",
    "password_hash": "pbkdf2:salt:hash",
    "created_at": "2025-01-01T00:00:00",
}


def _fake_get_optional_user(user=_FAKE_USER):
    """Return a coroutine that returns the user."""
    async def _inner(request):
        return user
    return _inner


def _fake_get_current_user(user=_FAKE_USER):
    async def _inner(request):
        return user
    return _inner


@pytest.fixture()
def tmp_vault(tmp_path):
    """Create a temporary vault with one book."""
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
    (book / "extractions.json").write_text(json.dumps([
        {
            "paragraph_id": "{01}.{01}",
            "topic_sentence": "Test topic",
            "defined_concepts": ["concept1"],
            "explicit_claims": ["Claim one about something important enough"],
            "implicit_assumptions": ["Assumption about something important enough"],
            "logical_steps": ["Step 1", "Step 2"],
        }
    ]))
    return vault


@pytest.fixture()
def client(tmp_vault):
    """Create a test client with mocked auth dependencies."""
    from ppke.web import app as app_module
    from ppke.auth import deps

    real_app = app_module.app

    # Override auth dependencies
    real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
    real_app.dependency_overrides[deps.get_optional_user] = lambda: _FAKE_USER

    # Patch vault path and helper functions
    with patch.object(app_module, "_vault_path", return_value=tmp_vault), \
         patch.object(app_module, "_user_vault_path", return_value=tmp_vault), \
         patch.object(app_module, "_try_get_user", new=_fake_get_optional_user()), \
         patch.object(app_module, "_get_db", return_value=MagicMock()):

        yield TestClient(real_app, raise_server_exceptions=False)

    real_app.dependency_overrides.clear()


@pytest.fixture()
def unauth_client(tmp_vault):
    """Create a test client with NO authentication."""
    from ppke.web import app as app_module

    real_app = app_module.app
    real_app.dependency_overrides.clear()

    with patch.object(app_module, "_vault_path", return_value=tmp_vault), \
         patch.object(app_module, "_user_vault_path", return_value=tmp_vault), \
         patch.object(app_module, "_try_get_user", new=_fake_get_optional_user(None)):
        yield TestClient(real_app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════


class TestSafeFolder:
    def test_valid_folder(self):
        from ppke.web.app import _safe_folder
        assert _safe_folder("Book_Test") == "Book_Test"

    def test_valid_with_dots(self):
        from ppke.web.app import _safe_folder
        assert _safe_folder("Book_Test.v2") == "Book_Test.v2"

    def test_invalid_traversal(self):
        from ppke.web.app import _safe_folder
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _safe_folder("../etc/passwd")

    def test_invalid_slash(self):
        from ppke.web.app import _safe_folder
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _safe_folder("path/to/file")


class TestHelperFunctions:
    def test_load_book_meta_exists(self, tmp_vault):
        from ppke.web.app import _load_book_meta
        meta = _load_book_meta(tmp_vault / "Book_TestBook")
        assert meta["title"] == "Test Book"
        assert meta["author"] == "Test Author"

    def test_load_book_meta_missing(self, tmp_path):
        from ppke.web.app import _load_book_meta
        meta = _load_book_meta(tmp_path)
        assert meta["title"] == tmp_path.name

    def test_load_extractions(self, tmp_vault):
        from ppke.web.app import _load_extractions
        exts = _load_extractions(tmp_vault / "Book_TestBook")
        assert len(exts) == 1
        assert exts[0]["topic_sentence"] == "Test topic"

    def test_load_extractions_missing(self, tmp_path):
        from ppke.web.app import _load_extractions
        assert _load_extractions(tmp_path) == []

    def test_book_dirs(self, tmp_vault):
        from ppke.web.app import _book_dirs
        with patch("ppke.web.app._user_vault_path", return_value=tmp_vault):
            dirs = _book_dirs(_FAKE_USER)
        assert len(dirs) == 1
        assert dirs[0].name == "Book_TestBook"

    def test_book_dirs_empty(self, tmp_path):
        from ppke.web.app import _book_dirs
        empty = tmp_path / "empty"
        empty.mkdir()
        with patch("ppke.web.app._user_vault_path", return_value=empty):
            assert _book_dirs(_FAKE_USER) == []


class TestChatHistory:
    def test_load_history_empty(self, tmp_path):
        from ppke.web.app import _load_history
        assert _load_history(tmp_path) == []

    def test_save_and_load_history(self, tmp_path):
        from ppke.web.app import _save_history, _load_history
        msgs = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]
        _save_history(tmp_path, msgs)
        loaded = _load_history(tmp_path)
        assert len(loaded) == 2
        assert loaded[0]["content"] == "Hello"

    def test_save_history_caps_at_100(self, tmp_path):
        from ppke.web.app import _save_history, _load_history
        msgs = [{"role": "user", "content": f"msg-{i}"} for i in range(150)]
        _save_history(tmp_path, msgs)
        loaded = _load_history(tmp_path)
        assert len(loaded) == 100

    def test_history_context_block_empty(self):
        from ppke.web.app import _history_context_block
        assert _history_context_block([]) == ""

    def test_history_context_block_with_messages(self):
        from ppke.web.app import _history_context_block
        msgs = [
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": "Answer!"},
        ]
        block = _history_context_block(msgs)
        assert "User: Question?" in block
        assert "Assistant: Answer!" in block


class TestRagContextBlock:
    def test_rag_without_vectordb(self):
        from ppke.web.app import _rag_context_block
        config = MagicMock()
        config.vault_path = Path("/tmp/nonexistent")
        hits, block = _rag_context_block("folder", "question", config)
        assert hits == []
        assert block == ""


# ═══════════════════════════════════════════════════════════════════
# Route tests
# ═══════════════════════════════════════════════════════════════════


class TestUnauthenticatedRoutes:
    def test_login_page_unauth_redirect(self, unauth_client):
        resp = unauth_client.get("/", follow_redirects=False)
        assert resp.status_code in (303, 307, 302)

    def test_login_page_renders(self, unauth_client):
        resp = unauth_client.get("/login")
        assert resp.status_code == 200


class TestAuthRoutes:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_login_invalid_creds(self, mock_auth_db, mock_get_db, client):
        mock_auth_db.get_user_by_email.return_value = None
        resp = client.post("/auth/login", data={"email": "x@x.com", "password": "wrong"})
        assert resp.status_code in (401, 200)  # Template response with error

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_register_short_password(self, mock_auth_db, mock_get_db, client):
        resp = client.post("/auth/register", data={
            "name": "Test", "email": "t@t.com", "password": "short", "password_confirm": "short"
        })
        assert resp.status_code == 400

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_register_mismatch(self, mock_auth_db, mock_get_db, client):
        resp = client.post("/auth/register", data={
            "name": "Test", "email": "t@t.com", "password": "password123", "password_confirm": "different1"
        })
        assert resp.status_code == 400

    def test_oauth_unsupported(self, client):
        resp = client.get("/auth/oauth/twitter")
        assert resp.status_code == 400

    def test_oauth_google_not_configured(self, client):
        resp = client.get("/auth/oauth/google")
        assert resp.status_code == 501

    def test_oauth_callback_not_configured(self, client):
        resp = client.get("/auth/oauth/google/callback?code=test")
        assert resp.status_code == 501

    def test_logout(self, client):
        resp = client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 303


class TestAPIRoutes:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_api_list_books(self, mock_auth_db, mock_get_db, client):
        resp = client.get("/api/books")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_api_get_book(self, mock_auth_db, mock_get_db, client, tmp_vault):
        resp = client.get("/api/books/Book_TestBook")
        assert resp.status_code == 200

    def test_api_get_book_not_found(self, client):
        resp = client.get("/api/books/Book_Nonexistent")
        assert resp.status_code == 404

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_api_get_extractions(self, mock_auth_db, mock_get_db, client):
        resp = client.get("/api/books/Book_TestBook/extractions")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data or "extractions" in data or isinstance(data, list)

    def test_api_job_status_missing(self, client):
        resp = client.get("/api/jobs/nonexistent")
        assert resp.status_code == 404

    def test_api_stats(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200

    def test_api_config(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200

    def test_api_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_api_metrics(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_api_audio_presets(self, client):
        resp = client.get("/api/audio/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_api_history_empty(self, client, tmp_vault):
        resp = client.get("/api/history/Book_TestBook")
        assert resp.status_code == 200

    def test_api_clear_history(self, client, tmp_vault):
        resp = client.delete("/api/history/Book_TestBook")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_api_get_summary_missing(self, mock_auth_db, mock_get_db, client, tmp_vault):
        resp = client.get("/api/summary/Book_TestBook")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_api_get_study_guide_missing(self, mock_auth_db, mock_get_db, client, tmp_vault):
        resp = client.get("/api/study-guide/Book_TestBook")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_api_glossary(self, mock_auth_db, mock_get_db, client, tmp_vault):
        resp = client.get("/api/glossary/Book_TestBook")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_api_flashcards(self, mock_auth_db, mock_get_db, client, tmp_vault):
        resp = client.get("/api/flashcards/Book_TestBook")
        assert resp.status_code == 200


class TestExportRoutes:
    def test_export_pdf(self, client, tmp_vault):
        resp = client.get("/api/export/Book_TestBook/pdf")
        assert resp.status_code == 200

    def test_export_pdf_not_found(self, client):
        resp = client.get("/api/export/Book_Missing/pdf")
        assert resp.status_code == 404

    def test_export_zip(self, client, tmp_vault):
        resp = client.get("/api/export/Book_TestBook/zip")
        assert resp.status_code == 200


class TestBibliographyRoutes:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_bibliography_apa(self, mock_auth_db, mock_get_db, client, tmp_vault):
        resp = client.get("/api/bibliography?style=apa")
        assert resp.status_code == 200


class TestArgumentMapRoutes:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_argument_map(self, mock_auth_db, mock_get_db, client, tmp_vault):
        resp = client.get("/api/argument-map/Book_TestBook")
        assert resp.status_code == 200


class TestCostDashboard:
    def test_cost_dashboard_page(self, client):
        resp = client.get("/cost-dashboard")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_cost_dashboard_api(self, mock_auth_db, mock_get_db, client):
        mock_get_db.return_value = MagicMock()
        mock_auth_db.get_cost_by_book.return_value = []
        mock_auth_db.get_cost_by_provider.return_value = []
        mock_auth_db.get_cost_by_action.return_value = []
        mock_auth_db.get_cost_daily.return_value = []
        resp = client.get("/api/cost-dashboard")
        assert resp.status_code == 200


class TestWorkspaceRoutes:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_list_workspaces(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_workspaces.return_value = []
        resp = client.get("/api/workspaces")
        assert resp.status_code == 200


class TestValidationHandler:
    def test_validation_error(self, client):
        # Trigger a validation error by passing wrong types
        resp = client.post("/api/query")
        # Should get 422 with structured errors
        assert resp.status_code == 422


class TestExceptionHandler:
    def test_general_exception_handler(self, client):
        from ppke.web.app import general_exception_handler
        assert callable(general_exception_handler)


class TestHTMLPages:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_dashboard(self, mock_auth_db, mock_get_db, client, tmp_vault):
        mock_auth_db.get_user_workspaces.return_value = []
        mock_auth_db.get_shared_books.return_value = []
        resp = client.get("/")
        assert resp.status_code == 200

    def test_upload_page(self, client):
        resp = client.get("/upload")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_settings_page(self, mock_auth_db, mock_get_db, client):
        mock_auth_db.get_user_api_keys.return_value = []
        mock_auth_db.get_user_usage.return_value = {"total_tokens": 0, "total_cost": 0}
        resp = client.get("/settings")
        assert resp.status_code == 200

    def test_graph_page(self, client, tmp_vault):
        resp = client.get("/graph")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_workspaces_page(self, mock_auth_db, mock_get_db, client):
        mock_auth_db.get_user_workspaces.return_value = []
        mock_auth_db.get_activity_feed.return_value = []
        resp = client.get("/workspaces")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_notebook_view(self, mock_auth_db, mock_get_db, client, tmp_vault):
        mock_auth_db.get_annotations.return_value = []
        resp = client.get("/notebook/Book_TestBook")
        assert resp.status_code == 200

    def test_notebook_not_found(self, client):
        resp = client.get("/notebook/Book_Missing")
        assert resp.status_code == 404


class TestGraphAPI:
    def test_graph_data_no_graph(self, client, tmp_vault):
        resp = client.get("/api/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "links" in data

    def test_graph_data_with_json(self, client, tmp_vault):
        import json as _json
        graph = {
            "nodes": [
                {"id": "concept:test", "label": "Test", "type": "concept"},
                {"id": "book:Book_TestBook", "label": "Test Book", "type": "book"},
            ],
            "edges": [
                {"source": "book:Book_TestBook", "target": "concept:test", "relation": "defines"},
            ],
        }
        (tmp_vault / "knowledge_graph.json").write_text(_json.dumps(graph))
        resp = client.get("/api/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 2

    def test_graph_data_with_book_filter(self, client, tmp_vault):
        resp = client.get("/api/graph?book=Book_TestBook")
        assert resp.status_code == 200

    def test_graph_search(self, client, tmp_vault):
        resp = client.get("/api/graph/search?q=test")
        assert resp.status_code == 200

    def test_graph_clusters(self, client, tmp_vault):
        resp = client.get("/api/graph/clusters")
        assert resp.status_code == 200

    def test_graph_analytics(self, client, tmp_vault):
        resp = client.get("/api/graph/analytics")
        assert resp.status_code == 200

    def test_graph_path(self, client, tmp_vault):
        resp = client.get("/api/graph/path?source=a&target=b")
        assert resp.status_code == 200

    def test_graph_gaps(self, client, tmp_vault):
        resp = client.get("/api/graph/gaps")
        assert resp.status_code == 200

    def test_graph_contradictions(self, client, tmp_vault):
        resp = client.get("/api/graph/contradictions")
        assert resp.status_code == 200

    def test_graph_export_no_graph(self, client, tmp_vault):
        resp = client.get("/api/graph/export")
        assert resp.status_code == 404

    def test_graph_obsidian_export_no_graph(self, client, tmp_vault):
        resp = client.get("/api/graph/obsidian-export")
        assert resp.status_code == 404

    def test_graph_markdown_export_no_graph(self, client, tmp_vault):
        resp = client.get("/api/graph/markdown-export")
        assert resp.status_code == 404

    def test_graph_export_with_graph(self, client, tmp_vault):
        import json as _json
        graph = {"nodes": [{"id": "concept:x", "label": "X", "type": "concept"}], "edges": []}
        (tmp_vault / "knowledge_graph.json").write_text(_json.dumps(graph))
        resp = client.get("/api/graph/export")
        assert resp.status_code == 200

    def test_graph_obsidian_export_with_graph(self, client, tmp_vault):
        import json as _json
        graph = {"nodes": [{"id": "concept:x", "label": "X", "type": "concept"}], "edges": []}
        (tmp_vault / "knowledge_graph.json").write_text(_json.dumps(graph))
        resp = client.get("/api/graph/obsidian-export")
        assert resp.status_code == 200

    def test_graph_markdown_export_with_graph(self, client, tmp_vault):
        import json as _json
        graph = {"nodes": [{"id": "concept:x", "label": "X", "type": "concept"}], "edges": []}
        (tmp_vault / "knowledge_graph.json").write_text(_json.dumps(graph))
        resp = client.get("/api/graph/markdown-export")
        assert resp.status_code == 200


class TestExportRoutesExtended:
    def test_export_docx(self, client, tmp_vault):
        resp = client.get("/api/export/Book_TestBook/docx")
        # Should fail with ImportError (no python-docx installed)
        assert resp.status_code == 500

    def test_export_pptx(self, client, tmp_vault):
        resp = client.get("/api/export/Book_TestBook/pptx")
        # Should fail with ImportError (no python-pptx installed)
        assert resp.status_code == 500

    def test_export_zip_content(self, client, tmp_vault):
        resp = client.get("/api/export/Book_TestBook/zip")
        assert resp.status_code == 200
        # Verify it's a valid zip
        import zipfile as _zf
        from io import BytesIO
        zf = _zf.ZipFile(BytesIO(resp.content))
        assert len(zf.namelist()) > 0


class TestSettingsAPI:
    def test_api_config(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "provider" in data or "llm" in data

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_api_update_settings(self, mock_auth_db, mock_get_db, client):
        resp = client.post("/api/settings", data={
            "provider": "openai",
            "model": "gpt-4",
        })
        assert resp.status_code in (200, 422)


class TestLiteratureReviewRoutes:
    def test_get_literature_review_not_generated(self, client, tmp_vault):
        resp = client.get("/api/literature-review")
        assert resp.status_code == 200


class TestAnnotationsRoutes:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_get_annotations(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_annotations.return_value = []
        resp = client.get("/api/annotations/Book_TestBook")
        assert resp.status_code == 200


class TestActivityRoutes:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_activity_feed(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_activity_feed.return_value = []
        resp = client.get("/api/activity")
        assert resp.status_code == 200


class TestKeysRoutes:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_list_keys(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_api_keys.return_value = []
        resp = client.get("/api/keys")
        assert resp.status_code == 200


class TestUsageRoutes:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_get_usage(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_usage.return_value = {"total_tokens": 0, "total_cost": 0}
        resp = client.get("/api/usage")
        assert resp.status_code == 200


class TestJobAPI:
    def test_job_status_found(self, client):
        from ppke.infra.tasks import create_job
        job_id = create_job(extra={"stage": "Testing"})
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stage"] == "Testing"
