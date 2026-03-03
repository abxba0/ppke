"""Local auth + data backend — wraps the existing database.py / jwt_auth.py.

This is the default backend: SQLite or self-hosted PostgreSQL with
custom JWT tokens.  It simply delegates to the existing module-level
functions so that all current behaviour is preserved unchanged.
"""

from __future__ import annotations

from typing import Any

from ppke.auth import database as _db
from ppke.auth import jwt_auth as _jwt


class LocalAuthBackend:
    """Password + JWT auth using the existing local database."""

    def __init__(self) -> None:
        self._conn = _db.get_db()

    # -- password auth ---------------------------------------------------

    def sign_up(self, email: str, password: str, name: str) -> dict[str, Any]:
        pw_hash = _jwt.hash_password(password)
        user = _db.create_user(self._conn, email, name, pw_hash)
        token = _jwt.create_token(user["id"], user["email"])
        return {"user": user, "token": token}

    def sign_in(self, email: str, password: str) -> dict[str, Any]:
        user = _db.get_user_by_email(self._conn, email)
        if not user:
            raise ValueError("Invalid email or password")
        if not _jwt.verify_password(password, user.get("password_hash", "")):
            raise ValueError("Invalid email or password")
        token = _jwt.create_token(user["id"], user["email"])
        return {"user": user, "token": token}

    def sign_out(self, token: str) -> None:
        # Local JWT tokens are stateless — nothing to revoke server-side
        pass

    # -- token verification ----------------------------------------------

    def get_user_from_token(self, token: str) -> dict[str, Any] | None:
        payload = _jwt.decode_token(token)
        if not payload:
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        return _db.get_user_by_id(self._conn, user_id)

    # -- OAuth -----------------------------------------------------------
    # Local backend keeps the manual OAuth flow already in app.py.
    # These return the *redirect URL* and exchange the code using httpx,
    # exactly as `_oauth_exchange_code` / `_oauth_get_userinfo` do today.

    def get_oauth_url(
        self,
        provider: str,
        redirect_url: str,
        *,
        scopes: str | None = None,
    ) -> str:
        # Delegated to app.py route handler (unchanged)
        raise NotImplementedError("Local backend uses app.py OAuth routes directly")

    def exchange_oauth_code(self, code: str) -> dict[str, Any]:
        raise NotImplementedError("Local backend uses app.py OAuth routes directly")


class LocalDataBackend:
    """Data layer using the existing database.py functions."""

    def __init__(self) -> None:
        self._conn = _db.get_db()

    @property
    def conn(self):
        """Expose raw connection for migration compatibility."""
        return self._conn

    # -- users -----------------------------------------------------------

    def get_user_by_id(self, user_id: str) -> dict | None:
        return _db.get_user_by_id(self._conn, user_id)

    def get_user_by_email(self, email: str) -> dict | None:
        return _db.get_user_by_email(self._conn, email)

    def get_user_by_oauth(self, provider: str, oauth_id: str) -> dict | None:
        return _db.get_user_by_oauth(self._conn, provider, oauth_id)

    def create_user(
        self, email: str, name: str, password_hash: str,
        role: str = "user", oauth_provider: str | None = None,
        oauth_id: str | None = None,
    ) -> dict:
        return _db.create_user(
            self._conn, email, name, password_hash,
            role=role, oauth_provider=oauth_provider, oauth_id=oauth_id,
        )

    # -- workspaces ------------------------------------------------------

    def create_workspace(self, name: str, slug: str, owner_id: str) -> dict:
        return _db.create_workspace(self._conn, name, slug, owner_id)

    def get_user_workspaces(self, user_id: str) -> list[dict]:
        return _db.get_user_workspaces(self._conn, user_id)

    def get_workspace_by_id(self, ws_id: str) -> dict | None:
        return _db.get_workspace_by_id(self._conn, ws_id)

    def get_workspace_members(self, ws_id: str) -> list[dict]:
        return _db.get_workspace_members(self._conn, ws_id)

    def add_workspace_member(
        self, ws_id: str, user_id: str, role: str = "viewer",
        invited_by: str | None = None,
    ) -> dict:
        return _db.add_workspace_member(self._conn, ws_id, user_id, role, invited_by)

    def update_member_role(self, ws_id: str, user_id: str, new_role: str) -> bool:
        return _db.update_member_role(self._conn, ws_id, user_id, new_role)

    def remove_workspace_member(self, ws_id: str, user_id: str) -> bool:
        return _db.remove_workspace_member(self._conn, ws_id, user_id)

    def get_user_role_in_workspace(self, ws_id: str, user_id: str) -> str | None:
        return _db.get_user_role_in_workspace(self._conn, ws_id, user_id)

    # -- shared books ----------------------------------------------------

    def share_book(
        self, ws_id: str, book_folder: str, shared_by: str,
        permissions: str = "view",
    ) -> dict:
        return _db.share_book(self._conn, ws_id, book_folder, shared_by, permissions)

    def get_shared_books(self, ws_id: str) -> list[dict]:
        return _db.get_shared_books(self._conn, ws_id)

    # -- annotations -----------------------------------------------------

    def create_annotation(
        self, user_id: str, book_folder: str, paragraph_id: str,
        content: str, annotation_type: str = "note",
        workspace_id: str | None = None,
    ) -> dict:
        return _db.create_annotation(
            self._conn, user_id, book_folder, paragraph_id,
            content, annotation_type, workspace_id,
        )

    def get_annotations(
        self, book_folder: str, user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict]:
        return _db.get_annotations(self._conn, book_folder, user_id, workspace_id)

    def delete_annotation(self, ann_id: str, user_id: str) -> bool:
        return _db.delete_annotation(self._conn, ann_id, user_id)

    # -- activity --------------------------------------------------------

    def log_activity(
        self, user_id: str, action: str,
        target_type: str = "", target_id: str = "",
        workspace_id: str | None = None, details: str | None = None,
    ) -> None:
        _db.log_activity(
            self._conn, user_id, action, target_type, target_id,
            workspace_id, details,
        )

    def get_activity_feed(
        self, workspace_id: str | None = None,
        user_id: str | None = None, limit: int = 50,
    ) -> list[dict]:
        return _db.get_activity_feed(self._conn, workspace_id, user_id, limit)

    # -- api keys --------------------------------------------------------

    def store_api_key(
        self, user_id: str, provider: str,
        encrypted_key: str, label: str = "",
    ) -> dict:
        return _db.store_api_key(self._conn, user_id, provider, encrypted_key, label)

    def get_user_api_keys(self, user_id: str) -> list[dict]:
        return _db.get_user_api_keys(self._conn, user_id)

    def get_api_key(self, user_id: str, provider: str) -> str | None:
        return _db.get_api_key(self._conn, user_id, provider)

    def delete_api_key(self, key_id: str, user_id: str) -> bool:
        return _db.delete_api_key(self._conn, key_id, user_id)

    # -- usage / cost ----------------------------------------------------

    def record_usage(
        self, user_id: str, action: str,
        tokens_used: int = 0, cost_usd: float = 0.0,
        provider: str = "", model: str = "",
        book_folder: str = "", workspace_id: str | None = None,
    ) -> dict:
        return _db.record_usage(
            self._conn, user_id, action, tokens_used, cost_usd,
            provider, model, book_folder, workspace_id,
        )

    def get_user_usage(self, user_id: str, days: int = 30) -> dict:
        return _db.get_user_usage(self._conn, user_id, days)

    def get_cost_by_book(self, user_id: str, days: int = 30) -> list[dict]:
        return _db.get_cost_by_book(self._conn, user_id, days)

    def get_cost_by_provider(self, user_id: str, days: int = 30) -> list[dict]:
        return _db.get_cost_by_provider(self._conn, user_id, days)

    def get_cost_by_action(self, user_id: str, days: int = 30) -> list[dict]:
        return _db.get_cost_by_action(self._conn, user_id, days)

    def get_cost_daily(self, user_id: str, days: int = 30) -> list[dict]:
        return _db.get_cost_daily(self._conn, user_id, days)

    # -- invites ---------------------------------------------------------

    def create_invite(self, ws_id: str, email: str, role: str,
                      invited_by: str) -> dict:
        return _db.create_invite(self._conn, ws_id, email, role, invited_by)

    def get_workspace_invites(self, workspace_id: str) -> list[dict]:
        return _db.get_workspace_invites(self._conn, workspace_id)

    def get_invites_for_email(self, email: str) -> list[dict]:
        return _db.get_invites_for_email(self._conn, email)

    def accept_invite(self, invite_id: str, user_id: str) -> dict | None:
        return _db.accept_invite(self._conn, invite_id, user_id)

    def accept_invite_by_token(self, token: str, user_id: str) -> dict | None:
        return _db.accept_invite_by_token(self._conn, token, user_id)

    def decline_invite(self, invite_id: str) -> bool:
        return _db.decline_invite(self._conn, invite_id)

    def revoke_invite(self, invite_id: str) -> bool:
        return _db.revoke_invite(self._conn, invite_id)

    def auto_accept_pending_invites(self, user_id: str, email: str) -> list[dict]:
        return _db.auto_accept_pending_invites(self._conn, user_id, email)
