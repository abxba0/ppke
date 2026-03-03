"""Compatibility adapter for the data layer.

Allows the existing ``auth_db.func(conn, arg1, arg2, ...)`` call pattern
in app.py to work *unchanged* regardless of backend.

**Local backend**: ``conn`` is the real ``DBConnection`` and functions in
``ppke.auth.database`` are called directly (the classic path).

**Supabase backend**: ``conn`` is a thin ``SupabaseConnShim`` whose
``__getattr__`` returns bound methods on the ``SupabaseDataBackend``,
so ``auth_db.func(conn, arg1)`` becomes ``conn.func(arg1)`` — no raw
SQL involved.

Usage in app.py stays identical::

    conn = _get_db()                          # returns shim or real conn
    user = auth_db.get_user_by_email(conn, email)  # works for both
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SupabaseConnShim:
    """Pretends to be a DB connection for call-site compatibility.

    When ``auth_db.func(conn, ...)`` is called and AUTH_BACKEND=supabase,
    ``conn`` is this shim.  The actual ``auth_db`` module-level functions
    are monkey-patched (see ``patch_auth_db()``) so that instead of doing
    ``conn.execute(sql, ...)`` they call ``conn._backend.func(...)`` which
    routes through the Supabase PostgREST backend.
    """

    def __init__(self, data_backend: Any) -> None:
        self._backend = data_backend
        self.backend = "supabase"        # Satisfy the few `conn.backend` checks

    def __getattr__(self, name: str) -> Any:
        # Forward attribute lookups to the Supabase data backend
        return getattr(self._backend, name)


# ---------------------------------------------------------------------------
# Monkey-patch registry
# ---------------------------------------------------------------------------
# Each function wraps a specific ``auth_db.func(conn, ...)`` so that
# when conn is a SupabaseConnShim it calls the matching method on the
# SupabaseDataBackend, otherwise falls back to the original function.

_originals: dict[str, Any] = {}
_patched = False


def patch_auth_db() -> None:
    """Replace ``ppke.auth.database`` public functions with shim-aware wrappers.

    Only applied once.  The wrappers detect whether ``conn`` is a real
    DBConnection or a SupabaseConnShim and route accordingly.
    """
    global _patched
    if _patched:
        return
    _patched = True

    from ppke.auth import database as auth_db

    # List of (function_name, positional_arg_names_after_conn)
    _functions = [
        "get_user_by_email",
        "get_user_by_id",
        "get_user_by_oauth",
        "create_user",
        "create_workspace",
        "get_user_workspaces",
        "get_workspace_by_id",
        "get_workspace_members",
        "add_workspace_member",
        "update_member_role",
        "remove_workspace_member",
        "get_user_role_in_workspace",
        "share_book",
        "get_shared_books",
        "create_annotation",
        "get_annotations",
        "delete_annotation",
        "log_activity",
        "get_activity_feed",
        "store_api_key",
        "get_user_api_keys",
        "get_api_key",
        "delete_api_key",
        "record_usage",
        "get_user_usage",
        "get_cost_by_book",
        "get_cost_by_provider",
        "get_cost_by_action",
        "get_cost_daily",
        "create_invite",
        "get_workspace_invites",
        "get_invites_for_email",
        "accept_invite",
        "accept_invite_by_token",
        "decline_invite",
        "revoke_invite",
        "auto_accept_pending_invites",
    ]

    for fn_name in _functions:
        original = getattr(auth_db, fn_name, None)
        if original is None:
            continue
        _originals[fn_name] = original
        _make_wrapper(auth_db, fn_name, original)

    logger.info("auth_db functions patched for backend compatibility")


def _make_wrapper(module: Any, fn_name: str, original: Any) -> None:
    """Create and install one wrapper function."""

    def wrapper(conn_or_shim, *args, **kwargs):
        if isinstance(conn_or_shim, SupabaseConnShim):
            # Route to SupabaseDataBackend method
            method = getattr(conn_or_shim._backend, fn_name)
            return method(*args, **kwargs)
        # Original path — real DBConnection
        return original(conn_or_shim, *args, **kwargs)

    wrapper.__name__ = fn_name
    wrapper.__doc__ = original.__doc__
    setattr(module, fn_name, wrapper)
