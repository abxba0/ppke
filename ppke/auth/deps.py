"""FastAPI dependencies for authentication and authorization.

Provides Depends()-compatible functions for extracting the current user
from JWT tokens (cookie or Authorization header), and role-based access
control helpers.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, HTTPException, Request

from ppke.auth.database import get_db, get_user_by_id, get_user_role_in_workspace
from ppke.auth.jwt_auth import decode_token

logger = logging.getLogger(__name__)

# Module-level database connection (lazy singleton)
_db_conn = None


def _get_db():
    global _db_conn
    if _db_conn is None:
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

    payload = decode_token(token)
    if not payload:
        if "text/html" in request.headers.get("accept", ""):
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    conn = _get_db()
    user = get_user_by_id(conn, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def get_optional_user(request: Request) -> dict[str, Any] | None:
    """Like get_current_user but returns None instead of raising."""
    token = _extract_token(request)
    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    conn = _get_db()
    return get_user_by_id(conn, user_id)


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

        conn = _get_db()
        user_role = get_user_role_in_workspace(conn, ws_id, user["id"])
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
