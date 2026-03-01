"""Extended web app tests — workspace, annotation, key management, audio API routes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from starlette.testclient import TestClient


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
    }
    (book / "meta.yml").write_text(yaml.dump(meta))
    (book / "01_Raw_Structure.md").write_text("# Chapter 1\n\nContent.")
    (book / "02_Logical_Map.md").write_text("# Logic\n- P1")
    (book / "03_Concept_Index.md").write_text("# Concepts\n- C1")
    (book / "extractions.json").write_text(json.dumps([{
        "paragraph_id": "{01}.{01}",
        "topic_sentence": "Topic",
        "defined_concepts": ["concept1"],
        "explicit_claims": [],
        "implicit_assumptions": [],
        "logical_steps": [],
    }]))
    return vault


@pytest.fixture()
def client(tmp_vault):
    from ppke.web import app as app_module
    from ppke.auth import deps

    real_app = app_module.app
    real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
    real_app.dependency_overrides[deps.get_optional_user] = lambda: _FAKE_USER

    with patch.object(app_module, "_vault_path", return_value=tmp_vault), \
         patch.object(app_module, "_user_vault_path", return_value=tmp_vault), \
         patch.object(app_module, "_try_get_user", new=_fake_get_optional_user()), \
         patch.object(app_module, "_get_db", return_value=MagicMock()):
        yield TestClient(real_app, raise_server_exceptions=False)

    real_app.dependency_overrides.clear()


class TestWorkspaceCreation:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_create_workspace(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.create_workspace.return_value = {"id": "ws-1", "name": "Test WS"}
        resp = client.post("/api/workspaces", json={"name": "Test WS"})
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_create_workspace_empty_name(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        resp = client.post("/api/workspaces", json={"name": ""})
        assert resp.status_code == 400


class TestWorkspaceMembers:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_list_members(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "admin"
        mock_auth_db.get_workspace_members.return_value = []
        resp = client.get("/api/workspaces/ws-1/members")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_list_members_not_member(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = None
        resp = client.get("/api/workspaces/ws-1/members")
        assert resp.status_code == 403


class TestInviteMembers:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_invite_success(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "admin"
        mock_auth_db.get_user_by_email.return_value = {"id": "target-user"}
        resp = client.post("/api/workspaces/ws-1/invite", json={"email": "t@t.com", "role": "viewer"})
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_invite_not_admin(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "viewer"
        resp = client.post("/api/workspaces/ws-1/invite", json={"email": "t@t.com"})
        assert resp.status_code == 403

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_invite_invalid_role(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "admin"
        resp = client.post("/api/workspaces/ws-1/invite", json={"email": "t@t.com", "role": "superadmin"})
        assert resp.status_code == 400

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_invite_user_not_found(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "admin"
        mock_auth_db.get_user_by_email.return_value = None
        resp = client.post("/api/workspaces/ws-1/invite", json={"email": "notfound@test.com"})
        assert resp.status_code == 404


class TestUpdateMemberRole:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_update_role_success(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "admin"
        resp = client.post("/api/workspaces/ws-1/members/member-1/role", json={"role": "editor"})
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_update_role_not_admin(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "editor"
        resp = client.post("/api/workspaces/ws-1/members/member-1/role", json={"role": "admin"})
        assert resp.status_code == 403


class TestRemoveMember:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_remove_success(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "admin"
        resp = client.delete("/api/workspaces/ws-1/members/other-member")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_remove_not_admin(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "viewer"
        resp = client.delete("/api/workspaces/ws-1/members/member-1")
        assert resp.status_code == 403

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_remove_self(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "admin"
        resp = client.delete("/api/workspaces/ws-1/members/user-001")
        assert resp.status_code == 400


class TestSharedBooks:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_share_book(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "admin"
        resp = client.post("/api/workspaces/ws-1/share", json={
            "book_folder": "Book_Test", "permissions": "read"
        })
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_get_shared_books(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.get_user_role_in_workspace.return_value = "admin"
        mock_auth_db.get_shared_books.return_value = []
        resp = client.get("/api/workspaces/ws-1/shared-books")
        assert resp.status_code == 200


class TestAnnotations:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_create_annotation(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.create_annotation.return_value = {"id": "ann-1"}
        resp = client.post("/api/annotations", json={
            "book_folder": "Book_Test",
            "paragraph_id": "{01}.{01}",
            "content": "My note",
            "annotation_type": "note",
        })
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_delete_annotation(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.delete_annotation.return_value = True
        resp = client.delete("/api/annotations/ann-1")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_delete_annotation_not_found(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.delete_annotation.return_value = False
        resp = client.delete("/api/annotations/nonexistent")
        assert resp.status_code == 404


class TestKeyManagement:
    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_store_key(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.store_api_key.return_value = {"id": "key-1"}
        resp = client.post("/api/keys", json={
            "provider": "openai",
            "api_key": "sk-test123",
        })
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_delete_key(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.delete_api_key.return_value = True
        resp = client.delete("/api/keys/key-1")
        assert resp.status_code == 200

    @patch("ppke.web.app._get_db")
    @patch("ppke.web.app.auth_db")
    def test_delete_key_not_found(self, mock_auth_db, mock_get_db, client):
        from ppke.auth import deps
        from ppke.web.app import app as real_app
        real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
        mock_auth_db.delete_api_key.return_value = False
        resp = client.delete("/api/keys/nonexistent")
        assert resp.status_code == 404


class TestSettingsUpdate:
    def test_update_settings(self, client):
        resp = client.post("/api/settings", data={
            "provider": "openai",
            "model": "gpt-4",
            "api_key": "",
            "default_domain": "philosophy",
            "vector_search": "true",
            "knowledge_graph": "true",
        })
        assert resp.status_code == 200


class TestAudioAPI:
    def test_serve_audio_not_found(self, client, tmp_vault):
        resp = client.get("/api/audio/Book_TestBook")
        assert resp.status_code == 404

    def test_audio_transcript_not_found(self, client, tmp_vault):
        resp = client.get("/api/audio/Book_TestBook/transcript")
        assert resp.status_code == 404

    def test_serve_audio_exists(self, client, tmp_vault):
        audio_dir = tmp_vault / "Book_TestBook"
        (audio_dir / "audio_overview.mp3").write_bytes(b"fake mp3 data")
        resp = client.get("/api/audio/Book_TestBook")
        assert resp.status_code == 200


class TestSearchAPI:
    def test_search(self, client, tmp_vault):
        resp = client.get("/api/search?q=test")
        assert resp.status_code == 200

    def test_search_with_book(self, client, tmp_vault):
        resp = client.get("/api/search?q=test&book=Book_TestBook")
        assert resp.status_code == 200


class TestSummaryGeneration:
    def test_get_summary_exists(self, client, tmp_vault):
        (tmp_vault / "Book_TestBook" / "summary.md").write_text("# Summary\n\nTest summary.")
        resp = client.get("/api/summary/Book_TestBook")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"

    def test_get_summary_missing(self, client, tmp_vault):
        resp = client.get("/api/summary/Book_TestBook")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_generated"
