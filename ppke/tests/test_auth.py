"""Tests for ppke.auth — JWT auth, password hashing, and dependencies."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ═══════════════════════════════════════════════════════════════════
# jwt_auth tests
# ═══════════════════════════════════════════════════════════════════


class TestPasswordHashing:
    def test_hash_and_verify_pbkdf2(self):
        from ppke.auth.jwt_auth import hash_password, verify_password
        hashed = hash_password("mypassword123")
        assert hashed.startswith("pbkdf2:")
        assert verify_password("mypassword123", hashed)

    def test_verify_wrong_password(self):
        from ppke.auth.jwt_auth import hash_password, verify_password
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_verify_bcrypt_fallback_returns_false(self):
        from ppke.auth.jwt_auth import verify_password
        # When bcrypt isn't installed and hash doesn't match pbkdf2 format
        assert not verify_password("test", "notpbkdf2hash")


class TestGetSecret:
    def test_secret_generation(self, tmp_path):
        from ppke.auth.jwt_auth import _get_secret, _SECRET_PATH
        secret_path = tmp_path / ".jwt_secret"
        with patch("ppke.auth.jwt_auth._SECRET_PATH", secret_path):
            secret = _get_secret()
            assert len(secret) == 64  # 32 bytes hex = 64 chars
            # Second call should return same secret
            assert _get_secret() == secret

    def test_secret_from_file(self, tmp_path):
        from ppke.auth.jwt_auth import _get_secret
        secret_path = tmp_path / ".jwt_secret"
        secret_path.write_text("mysecret123")
        with patch("ppke.auth.jwt_auth._SECRET_PATH", secret_path):
            assert _get_secret() == "mysecret123"


class TestTokens:
    def test_create_and_decode_hmac_token(self):
        from ppke.auth.jwt_auth import create_token, decode_token
        # Since jwt library may fail, this will likely use HMAC fallback
        token = create_token("user-123", "user@example.com")
        assert isinstance(token, str)
        assert len(token) > 10

        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["email"] == "user@example.com"

    def test_create_token_with_extra(self):
        from ppke.auth.jwt_auth import create_token, decode_token
        token = create_token("user-456", "u@e.com", extra={"workspace": "ws-1"})
        assert isinstance(token, str)

    def test_decode_invalid_token(self):
        from ppke.auth.jwt_auth import decode_token
        assert decode_token("not.a.valid.token") is None

    def test_decode_empty_token(self):
        from ppke.auth.jwt_auth import decode_token
        assert decode_token("") is None

    def test_hmac_token_expired(self):
        from ppke.auth.jwt_auth import _decode_hmac_token, _hmac_token
        import base64, json as _json, hmac as _hmac, hashlib
        from datetime import datetime, timezone, timedelta
        from ppke.auth.jwt_auth import _get_secret

        # Create an expired token manually
        payload = {
            "user_id": "u1",
            "email": "e@e.com",
            "exp": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }
        raw = _json.dumps(payload, sort_keys=True)
        sig = _hmac.new(_get_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
        token = base64.urlsafe_b64encode(f"{raw}|{sig}".encode()).decode()
        result = _decode_hmac_token(token)
        assert result is None

    def test_hmac_token_bad_signature(self):
        from ppke.auth.jwt_auth import _decode_hmac_token
        import base64
        token = base64.urlsafe_b64encode(b'{"user_id":"a","email":"b","exp":"2099-01-01T00:00:00"}|badsig').decode()
        result = _decode_hmac_token(token)
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# deps tests
# ═══════════════════════════════════════════════════════════════════


class TestExtractToken:
    def test_extract_from_cookie(self):
        from ppke.auth.deps import _extract_token
        request = MagicMock()
        request.cookies = {"ppke_token": "test-token"}
        request.headers = {}
        assert _extract_token(request) == "test-token"

    def test_extract_from_bearer(self):
        from ppke.auth.deps import _extract_token
        request = MagicMock()
        request.cookies = {}
        request.headers = {"Authorization": "Bearer my-jwt"}
        assert _extract_token(request) == "my-jwt"

    def test_extract_no_token(self):
        from ppke.auth.deps import _extract_token
        request = MagicMock()
        request.cookies = {}
        request.headers = {"Authorization": "", "accept": "text/html"}
        assert _extract_token(request) is None


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_no_token_raises_401(self):
        from ppke.auth.deps import get_current_user
        from fastapi import HTTPException
        request = MagicMock()
        request.cookies = {}
        request.headers = {"accept": "application/json", "Authorization": ""}
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_token_html_redirect(self):
        from ppke.auth.deps import get_current_user
        from fastapi import HTTPException
        request = MagicMock()
        request.cookies = {}
        request.headers = {"accept": "text/html", "Authorization": ""}
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 303

    @pytest.mark.asyncio
    @patch("ppke.auth.deps.decode_token", return_value={"sub": "user-1"})
    @patch("ppke.auth.deps._get_db")
    @patch("ppke.auth.deps.get_user_by_id", return_value={"id": "user-1", "name": "Test"})
    async def test_valid_token_returns_user(self, mock_get_user, mock_db, mock_decode):
        from ppke.auth.deps import get_current_user
        request = MagicMock()
        request.cookies = {"ppke_token": "valid-token"}
        request.headers = {}
        user = await get_current_user(request)
        assert user["id"] == "user-1"

    @pytest.mark.asyncio
    @patch("ppke.auth.deps.decode_token", return_value=None)
    async def test_invalid_token_raises(self, mock_decode):
        from ppke.auth.deps import get_current_user
        from fastapi import HTTPException
        request = MagicMock()
        request.cookies = {"ppke_token": "bad-token"}
        request.headers = {"accept": "application/json"}
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("ppke.auth.deps.decode_token", return_value={"sub": "user-gone"})
    @patch("ppke.auth.deps._get_db")
    @patch("ppke.auth.deps.get_user_by_id", return_value=None)
    async def test_user_not_found(self, mock_get_user, mock_db, mock_decode):
        from ppke.auth.deps import get_current_user
        from fastapi import HTTPException
        request = MagicMock()
        request.cookies = {"ppke_token": "orphan-token"}
        request.headers = {"accept": "application/json"}
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401


class TestGetOptionalUser:
    @pytest.mark.asyncio
    async def test_no_token_returns_none(self):
        from ppke.auth.deps import get_optional_user
        request = MagicMock()
        request.cookies = {}
        request.headers = {"Authorization": ""}
        result = await get_optional_user(request)
        assert result is None

    @pytest.mark.asyncio
    @patch("ppke.auth.deps.decode_token", return_value=None)
    async def test_invalid_token_returns_none(self, mock_decode):
        from ppke.auth.deps import get_optional_user
        request = MagicMock()
        request.cookies = {"ppke_token": "bad"}
        request.headers = {}
        result = await get_optional_user(request)
        assert result is None

    @pytest.mark.asyncio
    @patch("ppke.auth.deps.decode_token", return_value={})
    async def test_no_sub_returns_none(self, mock_decode):
        from ppke.auth.deps import get_optional_user
        request = MagicMock()
        request.cookies = {"ppke_token": "nosub"}
        request.headers = {}
        result = await get_optional_user(request)
        assert result is None


class TestRequireRole:
    @pytest.mark.asyncio
    async def test_no_workspace_context_passes(self):
        from ppke.auth.deps import require_role
        checker = require_role("editor")
        request = MagicMock()
        request.query_params = {}
        request.path_params = {}
        user = {"id": "u1", "name": "Test"}
        result = await checker(request, user)
        assert result["id"] == "u1"

    @pytest.mark.asyncio
    @patch("ppke.auth.deps._get_db")
    @patch("ppke.auth.deps.get_user_role_in_workspace", return_value=None)
    async def test_not_a_member_raises_403(self, mock_role, mock_db):
        from ppke.auth.deps import require_role
        from fastapi import HTTPException
        checker = require_role("editor")
        request = MagicMock()
        request.query_params = {"workspace_id": "ws-1"}
        request.path_params = {}
        user = {"id": "u1"}
        with pytest.raises(HTTPException) as exc_info:
            await checker(request, user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("ppke.auth.deps._get_db")
    @patch("ppke.auth.deps.get_user_role_in_workspace", return_value="viewer")
    async def test_insufficient_role_raises_403(self, mock_role, mock_db):
        from ppke.auth.deps import require_role
        from fastapi import HTTPException
        checker = require_role("admin")
        request = MagicMock()
        request.query_params = {"workspace_id": "ws-1"}
        request.path_params = {}
        user = {"id": "u1"}
        with pytest.raises(HTTPException) as exc_info:
            await checker(request, user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("ppke.auth.deps._get_db")
    @patch("ppke.auth.deps.get_user_role_in_workspace", return_value="admin")
    async def test_sufficient_role_passes(self, mock_role, mock_db):
        from ppke.auth.deps import require_role
        checker = require_role("editor")
        request = MagicMock()
        request.query_params = {"workspace_id": "ws-1"}
        request.path_params = {}
        user = {"id": "u1"}
        result = await checker(request, user)
        assert result["workspace_role"] == "admin"


class TestGetUserVaultPath:
    def test_creates_vault_dir(self, tmp_path):
        from ppke.auth.deps import get_user_vault_path
        with patch("ppke.auth.deps.Path.home", return_value=tmp_path):
            path = get_user_vault_path({"id": "test-user-123"})
        assert path.exists()
        assert "test-user-123" in str(path)
