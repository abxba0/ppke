"""Backend protocol definitions for pluggable auth and data layers.

The application communicates with auth and data through these protocols.
Concrete implementations live in:
  - ``ppke.auth.database`` + ``ppke.auth.jwt_auth`` (local / self-hosted)
  - ``ppke.auth.supabase_backend`` (Supabase hosted)

Switch backends by setting ``AUTH_BACKEND=supabase`` in ``~/.ppke/.env``
or environment.  Default is ``"local"``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Auth backend — handles authentication, tokens, OAuth
# ---------------------------------------------------------------------------

@runtime_checkable
class AuthBackend(Protocol):
    """Minimal contract for an authentication backend."""

    # -- password auth --
    def sign_up(self, email: str, password: str, name: str) -> dict[str, Any]:
        """Register a new user.  Returns ``{"user": {...}, "token": "..."}``."""
        ...

    def sign_in(self, email: str, password: str) -> dict[str, Any]:
        """Authenticate with email/password.
        Returns ``{"user": {...}, "token": "..."}``."""
        ...

    def sign_out(self, token: str) -> None:
        """Invalidate a session/token."""
        ...

    # -- token verification --
    def get_user_from_token(self, token: str) -> dict[str, Any] | None:
        """Decode/verify a token and return the user dict, or None."""
        ...

    # -- OAuth --
    def get_oauth_url(
        self,
        provider: str,
        redirect_url: str,
        *,
        scopes: str | None = None,
    ) -> str:
        """Return the URL the browser should be redirected to."""
        ...

    def exchange_oauth_code(
        self,
        code: str,
    ) -> dict[str, Any]:
        """Exchange an OAuth code for session.
        Returns ``{"user": {...}, "token": "...", "refresh_token": "..."}``."""
        ...


# ---------------------------------------------------------------------------
# Data backend — CRUD for workspaces, books, invites, etc.
# ---------------------------------------------------------------------------

@runtime_checkable
class DataBackend(Protocol):
    """Contract for the application data layer.

    Every method receives *no* raw connection object so that implementations
    can manage their own connection pool (Supabase client, pg pool, sqlite).
    """

    # -- users --
    def get_user_by_id(self, user_id: str) -> dict | None: ...
    def get_user_by_email(self, email: str) -> dict | None: ...
    def get_user_by_oauth(self, provider: str, oauth_id: str) -> dict | None: ...
    def create_user(
        self, email: str, name: str, password_hash: str,
        role: str = "user", oauth_provider: str | None = None,
        oauth_id: str | None = None,
    ) -> dict: ...

    # -- workspaces --
    def create_workspace(self, name: str, slug: str, owner_id: str) -> dict: ...
    def get_user_workspaces(self, user_id: str) -> list[dict]: ...
    def get_workspace_by_id(self, ws_id: str) -> dict | None: ...
    def get_workspace_members(self, ws_id: str) -> list[dict]: ...
    def add_workspace_member(
        self, ws_id: str, user_id: str, role: str = "viewer",
        invited_by: str | None = None,
    ) -> dict: ...
    def update_member_role(self, ws_id: str, user_id: str, new_role: str) -> bool: ...
    def remove_workspace_member(self, ws_id: str, user_id: str) -> bool: ...
    def get_user_role_in_workspace(self, ws_id: str, user_id: str) -> str | None: ...

    # -- shared books --
    def share_book(self, ws_id: str, book_folder: str, shared_by: str,
                   permissions: str = "view") -> dict: ...
    def get_shared_books(self, ws_id: str) -> list[dict]: ...
    def get_shared_book_by_id(self, share_id: str, ws_id: str) -> dict | None: ...
    def update_shared_book_permissions(self, share_id: str, ws_id: str, new_permissions: str) -> bool: ...
    def delete_shared_book(self, share_id: str, ws_id: str) -> bool: ...

    # -- annotations --
    def create_annotation(
        self, user_id: str, book_folder: str, paragraph_id: str,
        content: str, annotation_type: str = "note",
        workspace_id: str | None = None,
    ) -> dict: ...
    def get_annotations(
        self, book_folder: str, user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict]: ...
    def delete_annotation(self, ann_id: str, user_id: str) -> bool: ...

    # -- activity --
    def log_activity(
        self, user_id: str, action: str,
        target_type: str = "", target_id: str = "",
        workspace_id: str | None = None, details: str | None = None,
    ) -> None: ...
    def get_activity_feed(
        self, workspace_id: str | None = None,
        user_id: str | None = None, limit: int = 50,
    ) -> list[dict]: ...

    # -- api keys --
    def store_api_key(self, user_id: str, provider: str,
                      encrypted_key: str, label: str = "") -> dict: ...
    def get_user_api_keys(self, user_id: str) -> list[dict]: ...
    def get_api_key(self, user_id: str, provider: str) -> str | None: ...
    def delete_api_key(self, key_id: str, user_id: str) -> bool: ...

    # -- usage/cost --
    def record_usage(self, user_id: str, action: str,
                     tokens_used: int = 0, cost_usd: float = 0.0,
                     provider: str = "", model: str = "",
                     book_folder: str = "",
                     workspace_id: str | None = None) -> dict: ...
    def get_user_usage(self, user_id: str, days: int = 30) -> dict: ...
    def get_cost_by_book(self, user_id: str, days: int = 30) -> list[dict]: ...
    def get_cost_by_provider(self, user_id: str, days: int = 30) -> list[dict]: ...
    def get_cost_by_action(self, user_id: str, days: int = 30) -> list[dict]: ...
    def get_cost_daily(self, user_id: str, days: int = 30) -> list[dict]: ...

    # -- invites --
    def create_invite(self, ws_id: str, email: str, role: str,
                      invited_by: str) -> dict: ...
    def get_workspace_invites(self, workspace_id: str) -> list[dict]: ...
    def get_invites_for_email(self, email: str) -> list[dict]: ...
    def accept_invite(self, invite_id: str, user_id: str) -> dict | None: ...
    def accept_invite_by_token(self, token: str, user_id: str) -> dict | None: ...
    def decline_invite(self, invite_id: str) -> bool: ...
    def revoke_invite(self, invite_id: str) -> bool: ...
    def auto_accept_pending_invites(self, user_id: str, email: str) -> list[dict]: ...
