"""Supabase auth + data backend.

Uses Supabase Auth for registration, login, and OAuth (GitHub / Google),
and the Supabase PostgREST API for all CRUD operations.

Required env vars (``~/.ppke/.env`` or environment):
    SUPABASE_URL        — e.g. https://xyzxyz.supabase.co
    SUPABASE_ANON_KEY   — public anon key from Supabase dashboard

Optional:
    SUPABASE_SERVICE_KEY — service-role key (enables admin user lookups)

OAuth providers (GitHub, Google) must be enabled in the Supabase dashboard
under Authentication → Providers.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Lazy Supabase client singleton
# ---------------------------------------------------------------------------
_client: Any = None
_service_client: Any = None


def _load_supabase_env() -> tuple[str, str]:
    """Load SUPABASE_URL / SUPABASE_ANON_KEY from env or ~/.ppke/.env."""
    try:
        from ppke.config import _load_env_file
        for k, v in _load_env_file().items():
            os.environ.setdefault(k, v)
    except Exception:
        pass
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set. "
            "Add them to ~/.ppke/.env or your environment."
        )
    return url, key


def _get_client():
    """Get or create the Supabase client (anon key)."""
    global _client
    if _client is not None:
        return _client
    from supabase import create_client
    url, key = _load_supabase_env()
    _client = create_client(url, key)
    logger.info("Supabase client created for %s", url)
    return _client


def _get_service_client():
    """Get a service-role client for admin operations (optional)."""
    global _service_client
    if _service_client is not None:
        return _service_client
    try:
        from ppke.config import _load_env_file
        for k, v in _load_env_file().items():
            os.environ.setdefault(k, v)
    except Exception:
        pass
    skey = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not skey:
        return None
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "").strip()
    _service_client = create_client(url, skey)
    return _service_client


# ---------------------------------------------------------------------------
# Auth backend
# ---------------------------------------------------------------------------

class SupabaseAuthBackend:
    """Supabase GoTrue-based authentication."""

    def sign_up(self, email: str, password: str, name: str) -> dict[str, Any]:
        client = _get_client()
        resp = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"name": name}},
        })
        if not resp.user:
            raise ValueError("Registration failed — check Supabase dashboard for details")
        user_dict = _supabase_user_to_dict(resp.user)

        token = resp.session.access_token if resp.session else ""
        refresh = resp.session.refresh_token if resp.session else ""

        return {
            "user": user_dict,
            "token": token,
            "refresh_token": refresh,
        }

    def sign_in(self, email: str, password: str) -> dict[str, Any]:
        client = _get_client()
        resp = client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        if not resp.user or not resp.session:
            raise ValueError("Invalid email or password")
        user_dict = _supabase_user_to_dict(resp.user)
        return {
            "user": user_dict,
            "token": resp.session.access_token,
            "refresh_token": resp.session.refresh_token,
        }

    def sign_out(self, token: str) -> None:
        try:
            client = _get_client()
            client.auth.sign_out()
        except Exception:
            pass

    def get_user_from_token(self, token: str) -> dict[str, Any] | None:
        """Verify a Supabase JWT and return user dict."""
        try:
            client = _get_client()
            resp = client.auth.get_user(token)
            if resp and resp.user:
                return _supabase_user_to_dict(resp.user)
        except Exception as exc:
            logger.debug("Supabase token verification failed: %s", exc)
        return None

    def get_oauth_url(
        self,
        provider: str,
        redirect_url: str,
        *,
        scopes: str | None = None,
    ) -> str:
        """Get Supabase OAuth redirect URL for the given provider."""
        client = _get_client()
        opts: dict[str, Any] = {"redirect_to": redirect_url}
        if scopes:
            opts["scopes"] = scopes
        resp = client.auth.sign_in_with_oauth({
            "provider": provider,
            "options": opts,
        })
        return resp.url

    def exchange_oauth_code(self, code: str) -> dict[str, Any]:
        """Exchange an auth code from the OAuth callback for a session."""
        client = _get_client()
        resp = client.auth.exchange_code_for_session({"auth_code": code})
        if not resp.user or not resp.session:
            raise ValueError("OAuth code exchange failed")
        user_dict = _supabase_user_to_dict(resp.user)
        return {
            "user": user_dict,
            "token": resp.session.access_token,
            "refresh_token": resp.session.refresh_token,
        }

    def refresh_session(self, refresh_token: str) -> dict[str, Any] | None:
        """Refresh an expired session using the refresh token."""
        try:
            client = _get_client()
            resp = client.auth.refresh_session(refresh_token)
            if resp.session and resp.user:
                return {
                    "user": _supabase_user_to_dict(resp.user),
                    "token": resp.session.access_token,
                    "refresh_token": resp.session.refresh_token,
                }
        except Exception as exc:
            logger.debug("Session refresh failed: %s", exc)
        return None


def _supabase_user_to_dict(user) -> dict[str, Any]:
    """Normalise a Supabase User object into the dict shape the app expects."""
    meta = user.user_metadata or {}
    return {
        "id": user.id,
        "email": user.email or "",
        "name": meta.get("name", meta.get("full_name", (user.email or "").split("@")[0])),
        "role": "user",
        "is_active": 1,
        "created_at": user.created_at.isoformat() if user.created_at else _utcnow(),
        "updated_at": (user.updated_at.isoformat() if user.updated_at else _utcnow()),
        "oauth_provider": (user.app_metadata or {}).get("provider"),
        "oauth_id": user.id,  # Supabase uses its own user id
        "password_hash": "",  # Not exposed by Supabase
    }


# ---------------------------------------------------------------------------
# Data backend — PostgREST wrapper
# ---------------------------------------------------------------------------

class SupabaseDataBackend:
    """CRUD layer using Supabase PostgREST (auto-generated REST API).

    Tables are expected to exist in the Supabase database — run the SQL
    migration from ``ppke/auth/supabase_schema.sql`` in the Supabase
    SQL editor to create them.
    """

    def _table(self, name: str):
        return _get_client().table(name)

    def _service_table(self, name: str):
        """Use service-role client if available (bypasses RLS)."""
        sc = _get_service_client()
        if sc:
            return sc.table(name)
        return self._table(name)

    # -- users -----------------------------------------------------------

    def get_user_by_id(self, user_id: str) -> dict | None:
        resp = self._service_table("profiles").select("*").eq("id", user_id).maybe_single().execute()
        return _profile_to_user(resp.data) if resp.data else None

    def get_user_by_email(self, email: str) -> dict | None:
        resp = (self._service_table("profiles")
                .select("*")
                .eq("email", email.lower().strip())
                .maybe_single()
                .execute())
        return _profile_to_user(resp.data) if resp.data else None

    def get_user_by_oauth(self, provider: str, oauth_id: str) -> dict | None:
        resp = (self._service_table("profiles")
                .select("*")
                .eq("oauth_provider", provider)
                .eq("oauth_id", oauth_id)
                .maybe_single()
                .execute())
        return _profile_to_user(resp.data) if resp.data else None

    def create_user(
        self, email: str, name: str, password_hash: str,
        role: str = "user", oauth_provider: str | None = None,
        oauth_id: str | None = None,
    ) -> dict:
        """Insert a profile row.

        Note: with Supabase Auth the ``auth.users`` row is created by
        GoTrue (sign_up / OAuth).  This method creates the *profiles*
        row which holds app-specific fields.  A DB trigger can also do
        this automatically.
        """
        now = _utcnow()
        user_id = oauth_id or str(uuid.uuid4())
        data = {
            "id": user_id,
            "email": email.lower().strip(),
            "name": name,
            "password_hash": password_hash,
            "oauth_provider": oauth_provider,
            "oauth_id": oauth_id,
            "role": role,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        self._service_table("profiles").upsert(data).execute()

        # Auto-create personal workspace
        ws = self.create_workspace(f"{name}'s Workspace", f"personal-{user_id[:8]}", user_id)
        return {**data, "workspace_id": ws["id"]}

    def ensure_profile(self, user_dict: dict) -> dict:
        """Make sure a profiles row exists for a Supabase Auth user.

        Called after OAuth or email sign-up so the rest of the app has
        a profiles row to query.
        """
        existing = self.get_user_by_id(user_dict["id"])
        if existing:
            return existing
        return self.create_user(
            email=user_dict["email"],
            name=user_dict.get("name", user_dict["email"].split("@")[0]),
            password_hash="",
            oauth_provider=user_dict.get("oauth_provider"),
            oauth_id=user_dict["id"],
        )

    # -- workspaces ------------------------------------------------------

    def create_workspace(self, name: str, slug: str, owner_id: str) -> dict:
        now = _utcnow()
        ws_id = str(uuid.uuid4())
        self._service_table("workspaces").insert({
            "id": ws_id, "name": name, "slug": slug,
            "owner_id": owner_id, "created_at": now, "updated_at": now,
        }).execute()
        # Owner is admin
        self._service_table("workspace_members").insert({
            "id": str(uuid.uuid4()), "workspace_id": ws_id,
            "user_id": owner_id, "role": "admin", "created_at": now,
        }).execute()
        return {"id": ws_id, "name": name, "slug": slug, "owner_id": owner_id}

    def get_user_workspaces(self, user_id: str) -> list[dict]:
        resp = (self._service_table("workspace_members")
                .select("workspace_id, role, workspaces(*)")
                .eq("user_id", user_id)
                .order("created_at")
                .execute())
        results = []
        for row in (resp.data or []):
            ws = row.get("workspaces", {})
            if ws:
                results.append({**ws, "member_role": row["role"]})
        return results

    def get_workspace_by_id(self, ws_id: str) -> dict | None:
        resp = (self._service_table("workspaces")
                .select("*").eq("id", ws_id)
                .maybe_single().execute())
        return resp.data

    def get_workspace_members(self, ws_id: str) -> list[dict]:
        resp = (self._service_table("workspace_members")
                .select("*, profiles(email, name)")
                .eq("workspace_id", ws_id)
                .execute())
        results = []
        for row in (resp.data or []):
            profile = row.pop("profiles", {}) or {}
            row["email"] = profile.get("email", "")
            row["name"] = profile.get("name", "")
            results.append(row)
        return results

    def add_workspace_member(
        self, ws_id: str, user_id: str, role: str = "viewer",
        invited_by: str | None = None,
    ) -> dict:
        now = _utcnow()
        mem_id = str(uuid.uuid4())
        self._service_table("workspace_members").upsert({
            "id": mem_id, "workspace_id": ws_id, "user_id": user_id,
            "role": role, "invited_by": invited_by, "created_at": now,
        }, on_conflict="workspace_id,user_id").execute()
        return {"id": mem_id, "workspace_id": ws_id, "user_id": user_id, "role": role}

    def update_member_role(self, ws_id: str, user_id: str, new_role: str) -> bool:
        resp = (self._service_table("workspace_members")
                .update({"role": new_role})
                .eq("workspace_id", ws_id)
                .eq("user_id", user_id)
                .execute())
        return len(resp.data or []) > 0

    def remove_workspace_member(self, ws_id: str, user_id: str) -> bool:
        resp = (self._service_table("workspace_members")
                .delete()
                .eq("workspace_id", ws_id)
                .eq("user_id", user_id)
                .execute())
        return len(resp.data or []) > 0

    def get_user_role_in_workspace(self, ws_id: str, user_id: str) -> str | None:
        resp = (self._service_table("workspace_members")
                .select("role")
                .eq("workspace_id", ws_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute())
        return resp.data["role"] if resp.data else None

    # -- shared books ----------------------------------------------------

    def share_book(
        self, ws_id: str, book_folder: str, shared_by: str,
        permissions: str = "view",
    ) -> dict:
        now = _utcnow()
        share_id = str(uuid.uuid4())
        self._service_table("shared_books").insert({
            "id": share_id, "workspace_id": ws_id, "book_folder": book_folder,
            "shared_by": shared_by, "permissions": permissions, "created_at": now,
        }).execute()
        return {"id": share_id, "workspace_id": ws_id, "book_folder": book_folder, "permissions": permissions}

    def get_shared_books(self, ws_id: str) -> list[dict]:
        resp = (self._service_table("shared_books")
                .select("*, profiles!shared_by(name)")
                .eq("workspace_id", ws_id)
                .execute())
        results = []
        for row in (resp.data or []):
            p = row.pop("profiles", {}) or {}
            row["shared_by_name"] = p.get("name", "")
            results.append(row)
        return results

    def get_shared_book_by_id(self, share_id: str, ws_id: str) -> dict | None:
        resp = (self._service_table("shared_books")
                .select("*")
                .eq("id", share_id)
                .eq("workspace_id", ws_id)
                .maybe_single()
                .execute())
        return resp.data

    def update_shared_book_permissions(self, share_id: str, ws_id: str, new_permissions: str) -> bool:
        resp = (self._service_table("shared_books")
                .update({"permissions": new_permissions})
                .eq("id", share_id)
                .eq("workspace_id", ws_id)
                .execute())
        return len(resp.data or []) > 0

    def delete_shared_book(self, share_id: str, ws_id: str) -> bool:
        resp = (self._service_table("shared_books")
                .delete()
                .eq("id", share_id)
                .eq("workspace_id", ws_id)
                .execute())
        return len(resp.data or []) > 0

    # -- annotations -----------------------------------------------------

    def create_annotation(
        self, user_id: str, book_folder: str, paragraph_id: str,
        content: str, annotation_type: str = "note",
        workspace_id: str | None = None,
    ) -> dict:
        now = _utcnow()
        ann_id = str(uuid.uuid4())
        data = {
            "id": ann_id, "user_id": user_id, "workspace_id": workspace_id,
            "book_folder": book_folder, "paragraph_id": paragraph_id,
            "content": content, "annotation_type": annotation_type,
            "created_at": now, "updated_at": now,
        }
        self._service_table("annotations").insert(data).execute()
        return {
            "id": ann_id, "user_id": user_id, "book_folder": book_folder,
            "paragraph_id": paragraph_id, "content": content,
            "type": annotation_type, "created_at": now,
        }

    def get_annotations(
        self, book_folder: str, user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict]:
        q = (self._service_table("annotations")
             .select("*, profiles!user_id(name)")
             .eq("book_folder", book_folder))
        if user_id:
            q = q.eq("user_id", user_id)
        if workspace_id:
            q = q.eq("workspace_id", workspace_id)
        resp = q.order("created_at").execute()
        results = []
        for row in (resp.data or []):
            p = row.pop("profiles", {}) or {}
            row["user_name"] = p.get("name", "")
            results.append(row)
        return results

    def delete_annotation(self, ann_id: str, user_id: str) -> bool:
        resp = (self._service_table("annotations")
                .delete()
                .eq("id", ann_id)
                .eq("user_id", user_id)
                .execute())
        return len(resp.data or []) > 0

    # -- activity --------------------------------------------------------

    def log_activity(
        self, user_id: str, action: str,
        target_type: str = "", target_id: str = "",
        workspace_id: str | None = None, details: str | None = None,
    ) -> None:
        try:
            self._service_table("activity_log").insert({
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "workspace_id": workspace_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "details": details,
                "created_at": _utcnow(),
            }).execute()
        except Exception as exc:
            logger.debug("Failed to log activity: %s", exc)

    def get_activity_feed(
        self, workspace_id: str | None = None,
        user_id: str | None = None, limit: int = 50,
    ) -> list[dict]:
        q = (self._service_table("activity_log")
             .select("*, profiles!user_id(name)"))
        if workspace_id:
            q = q.eq("workspace_id", workspace_id)
        if user_id:
            q = q.eq("user_id", user_id)
        resp = q.order("created_at", desc=True).limit(limit).execute()
        results = []
        for row in (resp.data or []):
            p = row.pop("profiles", {}) or {}
            row["user_name"] = p.get("name", "")
            results.append(row)
        return results

    # -- api keys --------------------------------------------------------

    def store_api_key(
        self, user_id: str, provider: str,
        encrypted_key: str, label: str = "",
    ) -> dict:
        now = _utcnow()
        key_id = str(uuid.uuid4())
        data = {
            "id": key_id, "user_id": user_id, "provider": provider,
            "encrypted_key": encrypted_key, "label": label, "created_at": now,
        }
        self._service_table("api_keys").insert(data).execute()
        return data

    def get_user_api_keys(self, user_id: str) -> list[dict]:
        resp = (self._service_table("api_keys")
                .select("*").eq("user_id", user_id)
                .execute())
        return resp.data or []

    def get_api_key(self, user_id: str, provider: str) -> str | None:
        resp = (self._service_table("api_keys")
                .select("encrypted_key")
                .eq("user_id", user_id)
                .eq("provider", provider)
                .maybe_single()
                .execute())
        return resp.data["encrypted_key"] if resp.data else None

    def delete_api_key(self, key_id: str, user_id: str) -> bool:
        resp = (self._service_table("api_keys")
                .delete()
                .eq("id", key_id)
                .eq("user_id", user_id)
                .execute())
        return len(resp.data or []) > 0

    # -- usage / cost ----------------------------------------------------

    def record_usage(
        self, user_id: str, action: str,
        tokens_used: int = 0, cost_usd: float = 0.0,
        provider: str = "", model: str = "",
        book_folder: str = "", workspace_id: str | None = None,
    ) -> dict:
        now = _utcnow()
        rec_id = str(uuid.uuid4())
        data = {
            "id": rec_id, "user_id": user_id, "workspace_id": workspace_id,
            "action": action, "tokens_used": tokens_used, "cost_usd": cost_usd,
            "provider": provider, "model": model, "book_folder": book_folder,
            "created_at": now,
        }
        self._service_table("usage_records").insert(data).execute()
        return data

    def get_user_usage(self, user_id: str, days: int = 30) -> dict:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = (self._service_table("usage_records")
                .select("tokens_used, cost_usd")
                .eq("user_id", user_id)
                .gte("created_at", since)
                .execute())
        rows = resp.data or []
        return {
            "total_tokens": sum(r.get("tokens_used", 0) for r in rows),
            "total_cost_usd": round(sum(r.get("cost_usd", 0) for r in rows), 6),
            "request_count": len(rows),
        }

    def get_cost_by_book(self, user_id: str, days: int = 30) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = (self._service_table("usage_records")
                .select("book_folder, tokens_used, cost_usd")
                .eq("user_id", user_id)
                .gte("created_at", since)
                .execute())
        buckets: dict[str, dict] = {}
        for r in (resp.data or []):
            bf = r.get("book_folder", "")
            if bf not in buckets:
                buckets[bf] = {"book_folder": bf, "tokens": 0, "cost_usd": 0.0, "requests": 0}
            buckets[bf]["tokens"] += r.get("tokens_used", 0)
            buckets[bf]["cost_usd"] += r.get("cost_usd", 0)
            buckets[bf]["requests"] += 1
        return list(buckets.values())

    def get_cost_by_provider(self, user_id: str, days: int = 30) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = (self._service_table("usage_records")
                .select("provider, tokens_used, cost_usd")
                .eq("user_id", user_id)
                .gte("created_at", since)
                .execute())
        buckets: dict[str, dict] = {}
        for r in (resp.data or []):
            p = r.get("provider", "")
            if p not in buckets:
                buckets[p] = {"provider": p, "tokens": 0, "cost_usd": 0.0, "requests": 0}
            buckets[p]["tokens"] += r.get("tokens_used", 0)
            buckets[p]["cost_usd"] += r.get("cost_usd", 0)
            buckets[p]["requests"] += 1
        return list(buckets.values())

    def get_cost_by_action(self, user_id: str, days: int = 30) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = (self._service_table("usage_records")
                .select("action, tokens_used, cost_usd")
                .eq("user_id", user_id)
                .gte("created_at", since)
                .execute())
        buckets: dict[str, dict] = {}
        for r in (resp.data or []):
            a = r.get("action", "")
            if a not in buckets:
                buckets[a] = {"action": a, "tokens": 0, "cost_usd": 0.0, "requests": 0}
            buckets[a]["tokens"] += r.get("tokens_used", 0)
            buckets[a]["cost_usd"] += r.get("cost_usd", 0)
            buckets[a]["requests"] += 1
        return list(buckets.values())

    def get_cost_daily(self, user_id: str, days: int = 30) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = (self._service_table("usage_records")
                .select("created_at, tokens_used, cost_usd")
                .eq("user_id", user_id)
                .gte("created_at", since)
                .execute())
        buckets: dict[str, dict] = {}
        for r in (resp.data or []):
            day = r.get("created_at", "")[:10]
            if day not in buckets:
                buckets[day] = {"date": day, "tokens": 0, "cost_usd": 0.0, "requests": 0}
            buckets[day]["tokens"] += r.get("tokens_used", 0)
            buckets[day]["cost_usd"] += r.get("cost_usd", 0)
            buckets[day]["requests"] += 1
        return sorted(buckets.values(), key=lambda x: x["date"])

    # -- invites ---------------------------------------------------------

    def create_invite(
        self, ws_id: str, email: str, role: str, invited_by: str,
    ) -> dict:
        email = email.lower().strip()
        now = _utcnow()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        token = secrets.token_urlsafe(32)

        # Check existing membership
        existing = self.get_user_by_email(email)
        if existing:
            er = self.get_user_role_in_workspace(ws_id, existing["id"])
            if er:
                raise ValueError(f"{email} is already a member of this workspace")

        # Check for existing pending invite
        resp = (self._service_table("workspace_invites")
                .select("id")
                .eq("workspace_id", ws_id)
                .eq("email", email)
                .eq("status", "pending")
                .maybe_single()
                .execute())
        if resp.data:
            inv_id = resp.data["id"]
            self._service_table("workspace_invites").update({
                "role": role, "invited_by": invited_by,
                "token": token, "expires_at": expires_at,
            }).eq("id", inv_id).execute()
            return {
                "id": inv_id, "workspace_id": ws_id, "email": email,
                "role": role, "token": token, "status": "pending",
                "expires_at": expires_at,
            }

        invite_id = str(uuid.uuid4())
        data = {
            "id": invite_id, "workspace_id": ws_id, "email": email,
            "role": role, "invited_by": invited_by, "status": "pending",
            "token": token, "created_at": now, "expires_at": expires_at,
        }
        self._service_table("workspace_invites").insert(data).execute()
        return data

    def get_workspace_invites(self, workspace_id: str) -> list[dict]:
        resp = (self._service_table("workspace_invites")
                .select("*, profiles!invited_by(name)")
                .eq("workspace_id", workspace_id)
                .eq("status", "pending")
                .order("created_at", desc=True)
                .execute())
        results = []
        for row in (resp.data or []):
            p = row.pop("profiles", {}) or {}
            row["invited_by_name"] = p.get("name", "")
            results.append(row)
        return results

    def get_invites_for_email(self, email: str) -> list[dict]:
        email = email.lower().strip()
        resp = (self._service_table("workspace_invites")
                .select("*, workspaces(name), profiles!invited_by(name)")
                .eq("email", email)
                .eq("status", "pending")
                .order("created_at", desc=True)
                .execute())
        results = []
        for row in (resp.data or []):
            ws = row.pop("workspaces", {}) or {}
            p = row.pop("profiles", {}) or {}
            row["workspace_name"] = ws.get("name", "")
            row["invited_by_name"] = p.get("name", "")
            results.append(row)
        return results

    def accept_invite(self, invite_id: str, user_id: str) -> dict | None:
        resp = (self._service_table("workspace_invites")
                .select("*")
                .eq("id", invite_id)
                .eq("status", "pending")
                .maybe_single()
                .execute())
        invite = resp.data
        if not invite:
            return None
        if invite["expires_at"] < _utcnow():
            (self._service_table("workspace_invites")
             .update({"status": "expired"})
             .eq("id", invite_id).execute())
            return None
        self.add_workspace_member(
            invite["workspace_id"], user_id, invite["role"],
            invited_by=invite["invited_by"],
        )
        (self._service_table("workspace_invites")
         .update({"status": "accepted", "accepted_at": _utcnow()})
         .eq("id", invite_id).execute())
        return invite

    def accept_invite_by_token(self, token: str, user_id: str) -> dict | None:
        resp = (self._service_table("workspace_invites")
                .select("*")
                .eq("token", token)
                .eq("status", "pending")
                .maybe_single()
                .execute())
        if not resp.data:
            return None
        return self.accept_invite(resp.data["id"], user_id)

    def decline_invite(self, invite_id: str) -> bool:
        resp = (self._service_table("workspace_invites")
                .update({"status": "declined"})
                .eq("id", invite_id)
                .eq("status", "pending")
                .execute())
        return len(resp.data or []) > 0

    def revoke_invite(self, invite_id: str) -> bool:
        resp = (self._service_table("workspace_invites")
                .update({"status": "revoked"})
                .eq("id", invite_id)
                .eq("status", "pending")
                .execute())
        return len(resp.data or []) > 0

    def auto_accept_pending_invites(self, user_id: str, email: str) -> list[dict]:
        invites = self.get_invites_for_email(email)
        accepted = []
        for inv in invites:
            if inv.get("expires_at", "") >= _utcnow():
                result = self.accept_invite(inv["id"], user_id)
                if result:
                    accepted.append(result)
        return accepted


def _profile_to_user(row: dict | None) -> dict | None:
    """Normalise a profiles row to the user dict shape."""
    if not row:
        return None
    return {
        "id": row.get("id", ""),
        "email": row.get("email", ""),
        "name": row.get("name", ""),
        "role": row.get("role", "user"),
        "is_active": row.get("is_active", True),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
        "password_hash": row.get("password_hash", ""),
        "oauth_provider": row.get("oauth_provider"),
        "oauth_id": row.get("oauth_id"),
    }
