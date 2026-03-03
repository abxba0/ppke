"""FastAPI dependencies for authentication and authorization.

Provides Depends()-compatible functions for extracting the current user
from JWT tokens (cookie or Authorization header), and role-based access
control helpers.

Supports two backends (selected via ``AUTH_BACKEND`` env var):
  - ``local`` (default): SQLite/PostgreSQL + custom JWT
  - ``supabase``: Supabase Auth + PostgREST
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, HTTPException, Request

from ppke.auth.factory import get_auth_backend, get_data_backend, is_supabase
from ppke.auth.compat import SupabaseConnShim, patch_auth_db

logger = logging.getLogger(__name__)

# ── Legacy shim — kept so existing `from ppke.auth.deps import _get_db` works
_db_conn = None


def _get_db():
    """Return a raw DB connection (local) or the SupabaseConnShim (supabase).

    Either way, ``auth_db.func(conn, ...)`` works unchanged because the
    compat layer detects the shim and routes to the Supabase backend.
    """
    global _db_conn
    if _db_conn is None:
        if is_supabase():
            patch_auth_db()
            _db_conn = SupabaseConnShim(get_data_backend())
        else:
            from ppke.auth.database import get_db
            _db_conn = get_db()
    return _db_conn


def _extract_token(request: Request) -> str | None:
    """Extract JWT from cookie or Authorization header."""
    # 1. Check cookie
    token = request.cookies.get("ppke_token")
    if token:
        return token

    # 2. Check Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    return None


async def get_current_user(request: Request) -> dict[str, Any]:
    """Extract and validate the current user from JWT token.

    Raises 401 if no valid token is found.
    """
    token = _extract_token(request)
    if not token:
        # For page requests, redirect to login
        if "text/html" in request.headers.get("accept", ""):
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth = get_auth_backend()
    user = auth.get_user_from_token(token)
    if not user:
        if "text/html" in request.headers.get("accept", ""):
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # For Supabase, ensure a profiles row exists
    if is_supabase():
        data = get_data_backend()
        user = data.ensure_profile(user)

    return user


async def get_optional_user(request: Request) -> dict[str, Any] | None:
    """Like get_current_user but returns None instead of raising."""
    token = _extract_token(request)
    if not token:
        return None

    auth = get_auth_backend()
    user = auth.get_user_from_token(token)
    if not user:
        return None

    if is_supabase():
        data = get_data_backend()
        user = data.ensure_profile(user)

    return user


def require_role(min_role: str):
    """Dependency factory: require minimum workspace role.

    Role hierarchy: admin > editor > viewer
    """
    role_levels = {"viewer": 0, "editor": 1, "admin": 2}

    async def _checker(
        request: Request,
        user: dict = Depends(get_current_user),
    ) -> dict:
        ws_id = request.query_params.get("workspace_id") or request.path_params.get("workspace_id")
        if not ws_id:
            # No workspace context — only check user is authenticated
            return user

        data = get_data_backend()
        user_role = data.get_user_role_in_workspace(ws_id, user["id"])
        if user_role is None:
            raise HTTPException(status_code=403, detail="Not a member of this workspace")

        if role_levels.get(user_role, 0) < role_levels.get(min_role, 0):
            raise HTTPException(status_code=403, detail=f"Requires {min_role} role, you have {user_role}")

        user["workspace_role"] = user_role
        return user

    return _checker


def get_user_vault_path(user: dict) -> Path:
    """Get the vault path for a specific user.

    Multi-tenant isolation: each user gets their own vault directory.
    """
    base = Path.home() / ".ppke" / "vaults"
    user_vault = base / user["id"]
    user_vault.mkdir(parents=True, exist_ok=True)
    return user_vault
