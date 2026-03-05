"""FastAPI application — main web server for PPKE.

Phase 1 complete: dark mode, markdown chat, SSE streaming, toasts,
keyboard shortcuts, settings page, error middleware, path traversal
protection, mobile responsive.

Phase 2 complete: URL/YouTube import, .tex/.csv/.xlsx/.zip converters,
hybrid OCR with confidence scoring, multi-file upload.

Phase 7 complete: JWT auth, OAuth (Google/GitHub), multi-tenant workspaces,
per-user vault isolation, collaboration (shared notebooks, annotations,
activity feed), access control (roles, API keys, usage quotas).

Phase 8 complete: Docker, Celery task queue, PostgreSQL, Redis caching,
S3/GCS storage, structured logging, Prometheus metrics, Sentry error
tracking, cost dashboard.

Run with:
    ppke serve
    uvicorn ppke.web.app:app --reload
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, Depends
from typing import List as TypingList
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ppke.config import Config, SUPPORTED_PROVIDERS, PROVIDER_ENV_VARS
from ppke.auth.deps import get_current_user, get_optional_user, get_user_vault_path, _get_db
from ppke.auth.jwt_auth import hash_password, verify_password, create_token
from ppke.auth import database as auth_db
from ppke.auth.factory import get_auth_backend, get_data_backend, is_supabase

# ── Infrastructure initialization (Phase 8) ──
from ppke.infra.logging_config import configure_logging, RequestLoggingMiddleware
from ppke.infra.metrics import MetricsMiddleware, generate_metrics, record_ingestion
from ppke.infra.sentry_integration import init_sentry, capture_exception
from ppke.infra.tasks import create_job, run_task, get_job, update_job
from ppke.infra.cache import get_cache, cache_key

# Configure structured logging before anything else
configure_logging()

# Initialize Sentry error tracking
init_sentry()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="PPKE — Personal & Professional Knowledge Engine",
    version="3.0.0",
    description="Web interface for structured knowledge extraction from documents.",
)

# ── Middleware stack (Phase 8) ──
# Order matters: outermost middleware runs first
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# ── Static files & templates ──

_WEB_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=_WEB_DIR / "templates")


# ── Error handling middleware ──


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,  # pylint: disable=unused-argument
    exc: RequestValidationError,
):
    """Return clean validation errors instead of 422 blobs."""
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append(f"{field}: {error['msg']}")
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": errors},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all error handler for unhandled exceptions."""
    logger.exception("Unhandled error: %s", exc)
    capture_exception(exc, path=str(request.url), method=request.method)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}"},
    )


# ── Path traversal protection ──

# Only allow alphanumerics, underscores, hyphens, dots in folder names
_SAFE_FOLDER_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def _safe_folder(folder: str) -> str:
    """Validate folder name to prevent path traversal attacks."""
    if not _SAFE_FOLDER_RE.match(folder) or ".." in folder:
        raise HTTPException(400, "Invalid folder name")
    return folder


# ── Helper functions ──


def _get_config() -> Config:
    return Config.load()


def _vault_path() -> Path:
    """Global vault path (fallback for unauthenticated/legacy mode)."""
    return _get_config().vault_path


def _user_vault_path(user: dict | None) -> Path:
    """Get vault path — per-user if authenticated, else global fallback."""
    if user:
        return get_user_vault_path(user)
    return _vault_path()


def _book_dirs(user: dict | None = None) -> list[Path]:
    vault = _user_vault_path(user)
    if not vault.exists():
        return []
    return sorted(
        [d for d in vault.iterdir() if d.is_dir() and d.name.startswith("Book_")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


# ── Auth-aware helper: get user from request or None ──


async def _try_get_user(request: Request) -> dict | None:
    """Try to get user from request, return None if not authenticated."""
    try:
        return await get_optional_user(request)
    except Exception:
        return None


def _load_book_meta(book_dir: Path) -> dict[str, Any]:
    import yaml

    meta_path = book_dir / "meta.yml"
    if meta_path.exists():
        return yaml.safe_load(meta_path.read_text()) or {}
    return {"title": book_dir.name, "author": "Unknown"}


def _load_extractions(book_dir: Path) -> list[dict]:
    path = book_dir / "extractions.json"
    if path.exists():
        return json.loads(path.read_text())
    return []


# ── Chat history helpers ──

def _load_history(book_dir: Path) -> list[dict]:
    """Load per-book chat history (list of {role, content, ts} dicts)."""
    path = book_dir / "chat_history.json"
    if path.exists():
        try:
            return json.loads(path.read_text()) or []
        except Exception:
            return []
    return []


def _save_history(book_dir: Path, messages: list[dict]) -> None:
    """Persist chat history, capping at 100 messages to bound file size."""
    if len(messages) > 100:
        messages = messages[-100:]
    (book_dir / "chat_history.json").write_text(
        json.dumps(messages, indent=2, ensure_ascii=False)
    )


def _history_context_block(history: list[dict], max_turns: int = 6) -> str:
    """Format last N history turns as a context block for the LLM prompt."""
    if not history:
        return ""
    turns = history[-(max_turns * 2):]
    lines = ["CONVERSATION HISTORY (most recent exchanges):"]
    for msg in turns:
        role = msg.get("role", "user").capitalize()
        content = (msg.get("content") or "")[:600]
        lines.append(f"{role}: {content}")
    return "\n".join(lines) + "\n\n---\n\n"


def _rag_context_block(
    folder: str, question: str, config: Any, n_results: int = 5,
    *, use_hybrid: bool = False,
) -> tuple[list[dict], str]:
    """Run search and return (hits, formatted context block).

    When *use_hybrid* is ``True`` the function uses the hybrid search engine
    (full-text + vector combined).  Otherwise it falls back to the original
    vector-only search.  Returns ([], "") gracefully when no results are found.
    """
    try:
        if use_hybrid:
            from ppke.search import hybrid_search

            hits = hybrid_search(
                config.vault_path,
                question,
                book_filter=folder,
                n_results=n_results,
            )
        else:
            from ppke.vectordb.store import VectorStore

            store = VectorStore(config.vault_path)
            if not store.available:
                return [], ""
            hits = store.search(question, n_results=n_results, book_filter=folder)

        if not hits:
            return [], ""
        label = "hybrid" if use_hybrid else "vector"
        lines = [f"SEMANTICALLY RELEVANT PASSAGES ({label} search):"]
        for h in hits:
            lines.append(f"  [{h['paragraph_id']}] {h['document'][:280]}")
        return hits, "\n".join(lines) + "\n\n"
    except Exception as exc:
        logger.debug("RAG search skipped: %s", exc)
        return [], ""


# ── Authentication routes ──


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = await _try_get_user(request)
    next_url = request.query_params.get("next", "")
    if user:
        if next_url:
            return RedirectResponse(next_url, status_code=303)
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "next": next_url, "oauth_providers": _get_available_oauth_providers()})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = await _try_get_user(request)
    next_url = request.query_params.get("next", "")
    if user:
        if next_url:
            return RedirectResponse(next_url, status_code=303)
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("register.html", {"request": request, "error": None, "next": next_url, "oauth_providers": _get_available_oauth_providers()})


@app.post("/auth/login")
async def auth_login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("")):
    try:
        auth = get_auth_backend()
        result = auth.sign_in(email, password)
    except (ValueError, Exception) as exc:
        return templates.TemplateResponse("login.html", {
            "request": request, "error": str(exc) or "Invalid email or password", "next": next,
            "oauth_providers": _get_available_oauth_providers(),
        }, status_code=401)

    user = result["user"]
    token = result["token"]

    conn = _get_db()
    auth_db.log_activity(conn, user["id"], "signed in")

    # Auto-accept any pending workspace invites
    accepted = auth_db.auto_accept_pending_invites(conn, user["id"], user["email"])
    redirect_url = next if next else "/"
    response = RedirectResponse(redirect_url, status_code=303)
    response.set_cookie(
        "ppke_token", token, httponly=True, samesite="lax", max_age=72 * 3600
    )
    return response


@app.post("/auth/register")
async def auth_register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    next: str = Form(""),
):
    if len(password) < 8:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Password must be at least 8 characters", "next": next,
            "oauth_providers": _get_available_oauth_providers(),
        }, status_code=400)

    if password != password_confirm:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Passwords do not match", "next": next,
            "oauth_providers": _get_available_oauth_providers(),
        }, status_code=400)

    try:
        auth = get_auth_backend()
        result = auth.sign_up(email, password, name)
    except (ValueError, Exception) as exc:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": str(exc) or "Registration failed", "next": next,
            "oauth_providers": _get_available_oauth_providers(),
        }, status_code=400)

    user = result["user"]
    token = result["token"]

    conn = _get_db()
    auth_db.log_activity(conn, user["id"], "created account")

    # Auto-accept any pending workspace invites for this email
    accepted = auth_db.auto_accept_pending_invites(conn, user["id"], email)
    if accepted:
        auth_db.log_activity(conn, user["id"], f"auto-joined {len(accepted)} workspace(s) from pending invites")

    redirect_url = next if next else "/"
    response = RedirectResponse(redirect_url, status_code=303)
    response.set_cookie(
        "ppke_token", token, httponly=True, samesite="lax", max_age=72 * 3600
    )
    return response


@app.get("/auth/logout")
async def auth_logout(request: Request):
    user = await _try_get_user(request)
    if user:
        conn = _get_db()
        auth_db.log_activity(conn, user["id"], "signed out")
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("ppke_token")
    return response


_OAUTH_CONFIGS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scope": "openid email profile",
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
    },
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scope": "read:user user:email",
        "client_id_env": "GITHUB_CLIENT_ID",
        "client_secret_env": "GITHUB_CLIENT_SECRET",
    },
}


def _get_oauth_credentials(provider: str) -> tuple[str, str] | None:
    """Return (client_id, client_secret) from env vars or ~/.ppke/.env, or None if not configured."""
    from ppke.config import _load_env_file
    cfg = _OAUTH_CONFIGS[provider]
    dot_env = _load_env_file()
    client_id = (os.environ.get(cfg["client_id_env"], "") or dot_env.get(cfg["client_id_env"], "")).strip()
    client_secret = (os.environ.get(cfg["client_secret_env"], "") or dot_env.get(cfg["client_secret_env"], "")).strip()
    if client_id and client_secret:
        return client_id, client_secret
    return None


def _get_available_oauth_providers() -> list[str]:
    """Return list of OAuth providers that have credentials configured."""
    if is_supabase():
        return list(_OAUTH_CONFIGS.keys())
    return [p for p in _OAUTH_CONFIGS if _get_oauth_credentials(p) is not None]


def _cli_oauth_success_html(name: str, email: str, jwt_token: str) -> str:
    """Return the HTML success page shown after CLI OAuth callback."""
    return f"""<!DOCTYPE html>
<html><head><title>PPKE — Login Successful</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0;
         display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
  .card {{ background: #16213e; padding: 2rem 3rem; border-radius: 12px; text-align: center; max-width: 500px; }}
  h2 {{ color: #4ecca3; }}
  code {{ background: #0f3460; padding: 4px 8px; border-radius: 4px; word-break: break-all; font-size: 0.85em; }}
  .token-box {{ background: #0f3460; padding: 12px; border-radius: 8px; margin: 1rem 0; word-break: break-all;
                font-family: monospace; font-size: 0.8em; max-height: 120px; overflow-y: auto; }}
  .hint {{ color: #888; font-size: 0.85em; margin-top: 1rem; }}
</style></head>
<body><div class="card">
  <h2>✓ Logged in as {name}</h2>
  <p>Your CLI token is below. It has been saved automatically if your CLI is waiting.</p>
  <div class="token-box">{jwt_token}</div>
  <p class="hint">You can close this tab and return to your terminal.</p>
</div>
<script>
  // Post the token to the CLI's local listener if running
  fetch('http://127.0.0.1:19283/callback', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{token: '{jwt_token}', email: '{email}', name: '{name}'}})
  }}).catch(() => {{}});
</script></body></html>"""


def _oauth_exchange_code(provider: str, code: str, redirect_uri: str) -> dict:
    """Exchange an authorization code for an access token using stdlib urllib."""
    cfg = _OAUTH_CONFIGS[provider]
    creds = _get_oauth_credentials(provider)
    if not creds:
        raise HTTPException(501, f"OAuth {provider} not configured")
    client_id, client_secret = creds

    data = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request(cfg["token_url"], data=data, method="POST")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _oauth_get_userinfo(provider: str, access_token: str) -> dict:
    """Fetch user profile from the OAuth provider using stdlib urllib."""
    cfg = _OAUTH_CONFIGS[provider]
    req = urllib.request.Request(cfg["userinfo_url"])
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        user_info = json.loads(resp.read())

    # For GitHub, email may not be in the profile response — fetch from /user/emails
    if provider == "github" and not user_info.get("email"):
        emails_req = urllib.request.Request("https://api.github.com/user/emails")
        emails_req.add_header("Authorization", f"Bearer {access_token}")
        emails_req.add_header("Accept", "application/json")
        with urllib.request.urlopen(emails_req, timeout=10) as resp:
            emails = json.loads(resp.read())
        primary = next((e["email"] for e in emails if e.get("primary")), None)
        if primary:
            user_info["email"] = primary

    return user_info


@app.get("/auth/oauth/{provider}")
async def auth_oauth_start(provider: str, request: Request):
    """Start OAuth flow — redirect to provider's authorization page."""
    if provider not in _OAUTH_CONFIGS:
        raise HTTPException(400, "Unsupported OAuth provider")

    redirect_uri = str(request.base_url).rstrip("/") + f"/auth/oauth/{provider}/callback"

    # Supabase: delegate OAuth to Supabase Auth (GoTrue)
    if is_supabase():
        try:
            auth = get_auth_backend()
            result = auth.get_oauth_url(provider, redirect_uri)
            return RedirectResponse(result["url"], status_code=302)
        except Exception as exc:
            logger.error("Supabase OAuth start failed: %s", exc)
            raise HTTPException(502, f"OAuth start failed: {exc}") from exc

    # Local backend: manual OAuth flow
    creds = _get_oauth_credentials(provider)
    if not creds:
        # Browser request: redirect back to login with a friendly error message
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            error_msg = (
                f"OAuth with {provider} is not configured. "
                f"Set {provider.upper()}_CLIENT_ID and {provider.upper()}_CLIENT_SECRET in ~/.ppke/.env and restart the server."
            )
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": error_msg, "next": "", "oauth_providers": _get_available_oauth_providers()},
                status_code=501,
            )
        raise HTTPException(
            501,
            f"OAuth with {provider} requires configuration. "
            f"Set {provider.upper()}_CLIENT_ID and {provider.upper()}_CLIENT_SECRET in ~/.ppke/.env",
        )
    client_id, _ = creds
    cfg = _OAUTH_CONFIGS[provider]

    state = secrets.token_urlsafe(32)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": cfg["scope"],
        "state": state,
        "response_type": "code",
    }
    auth_url = cfg["auth_url"] + "?" + urlencode(params)

    response = RedirectResponse(auth_url, status_code=302)
    is_secure = str(request.base_url).startswith("https")
    response.set_cookie(
        "ppke_oauth_state", state, httponly=True, samesite="lax", max_age=600,
        secure=is_secure,
    )
    return response


@app.get("/auth/oauth/{provider}/callback")
async def auth_oauth_callback(
    provider: str,
    request: Request,
    code: str = Query(...),
    state: str = Query(""),
):
    """Handle OAuth callback — exchange code for token and create/login user."""
    if provider not in _OAUTH_CONFIGS:
        raise HTTPException(400, "Unsupported OAuth provider")

    # ── Supabase backend: exchange code via GoTrue ──
    if is_supabase():
        try:
            auth = get_auth_backend()
            result = auth.exchange_oauth_code(code)
        except Exception as exc:
            logger.error("Supabase OAuth callback failed: %s", exc)
            raise HTTPException(502, f"OAuth login failed: {exc}") from exc

        user = result["user"]
        token = result["token"]

        conn = _get_db()
        auth_db.log_activity(conn, user["id"], f"signed in via {provider} OAuth")

        # Auto-accept pending invites
        email = user.get("email", "")
        if email:
            accepted = auth_db.auto_accept_pending_invites(conn, user["id"], email)
            if accepted:
                auth_db.log_activity(conn, user["id"], f"auto-joined {len(accepted)} workspace(s) from pending invites")

        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            "ppke_token", token, httponly=True, samesite="lax", max_age=72 * 3600,
        )
        return response

    # ── Local backend: manual OAuth exchange ──
    creds = _get_oauth_credentials(provider)
    if not creds:
        raise HTTPException(501, f"OAuth {provider} not configured")

    # CSRF: verify state matches cookie
    expected_state = request.cookies.get("ppke_oauth_state", "")
    if not state or not expected_state or state != expected_state:
        raise HTTPException(400, "Invalid OAuth state — possible CSRF. Please try again.")

    redirect_uri = str(request.base_url).rstrip("/") + f"/auth/oauth/{provider}/callback"

    try:
        token_data = _oauth_exchange_code(provider, code, redirect_uri)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("OAuth token exchange failed for %s: %s", provider, exc)
        raise HTTPException(502, "Failed to exchange authorization code") from exc

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(502, "OAuth provider did not return an access token")

    try:
        user_info = _oauth_get_userinfo(provider, access_token)
    except Exception as exc:
        logger.error("OAuth userinfo fetch failed for %s: %s", provider, exc)
        raise HTTPException(502, "Failed to fetch user profile from OAuth provider") from exc

    # Normalize user fields across providers
    if provider == "google":
        oauth_id = str(user_info.get("id", ""))
        email = user_info.get("email", "")
        name = user_info.get("name", email.split("@")[0])
    else:  # github
        oauth_id = str(user_info.get("id", ""))
        email = user_info.get("email", "")
        name = user_info.get("name") or user_info.get("login", email.split("@")[0])

    if not email or not oauth_id:
        raise HTTPException(400, "Could not retrieve email from OAuth provider")

    conn = _get_db()

    # Try to find existing OAuth user
    user = auth_db.get_user_by_oauth(conn, provider, oauth_id)
    if not user:
        # Check if a user with this email already exists (link accounts)
        user = auth_db.get_user_by_email(conn, email)
    if not user:
        # Create new user (no password for OAuth-only accounts)
        user = auth_db.create_user(
            conn, email, name, password_hash="", oauth_provider=provider, oauth_id=oauth_id,
        )
        auth_db.log_activity(conn, user["id"], f"created account via {provider} OAuth")
    else:
        auth_db.log_activity(conn, user["id"], f"signed in via {provider} OAuth")

    jwt_token = create_token(user["id"], user["email"])
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        "ppke_token", jwt_token, httponly=True, samesite="lax", max_age=72 * 3600,
    )
    response.delete_cookie("ppke_oauth_state")
    return response


# ── JSON API auth endpoints (for CLI / programmatic access) ──


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    """JSON-based login — returns a JWT token for CLI/programmatic use."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Request body must be JSON with 'email' and 'password'")
    email = body.get("email", "").strip()
    password = body.get("password", "")
    if not email or not password:
        raise HTTPException(400, "Both 'email' and 'password' are required")

    try:
        auth = get_auth_backend()
        result = auth.sign_in(email, password)
    except ValueError as exc:
        raise HTTPException(401, str(exc))
    except Exception as exc:
        logger.error("API login failed: %s", exc)
        raise HTTPException(401, "Invalid email or password")

    user = result["user"]
    token = result["token"]
    conn = _get_db()
    auth_db.log_activity(conn, user["id"], "signed in via API")
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}}
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}}


@app.post("/api/auth/register")
async def api_auth_register(request: Request):
    """JSON-based registration — returns a JWT token for CLI/programmatic use."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Request body must be JSON")
    email = body.get("email", "").strip()
    name = body.get("name", "").strip()
    password = body.get("password", "")
    if not email or not password:
        raise HTTPException(400, "'email' and 'password' are required")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if not name:
        name = email.split("@")[0]

    try:
        auth = get_auth_backend()
        result = auth.sign_up(email, password, name)
    except (ValueError, Exception) as exc:
        raise HTTPException(400, str(exc) or "Registration failed")

    user = result["user"]
    token = result["token"]
    conn = _get_db()
    auth_db.log_activity(conn, user["id"], "created account via API")
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}}


@app.get("/api/auth/oauth/{provider}/cli")
async def api_auth_oauth_cli_start(provider: str, request: Request):
    """Start OAuth flow for CLI — returns the authorization URL to open in a browser."""
    if provider not in _OAUTH_CONFIGS:
        raise HTTPException(400, "Unsupported OAuth provider")

    redirect_uri = str(request.base_url).rstrip("/") + f"/auth/oauth/{provider}/callback/cli"

    # Supabase: use built-in GoTrue OAuth
    if is_supabase():
        try:
            auth = get_auth_backend()
            result = auth.get_oauth_url(provider, redirect_uri)
            return {"auth_url": result["url"], "state": "supabase-managed"}
        except Exception as exc:
            raise HTTPException(502, f"OAuth start failed: {exc}") from exc

    # Local backend: manual OAuth
    creds = _get_oauth_credentials(provider)
    if not creds:
        raise HTTPException(
            501,
            f"OAuth with {provider} requires configuration. "
            f"Set {provider.upper()}_CLIENT_ID and {provider.upper()}_CLIENT_SECRET in ~/.ppke/.env",
        )
    client_id, _ = creds
    cfg = _OAUTH_CONFIGS[provider]

    state = secrets.token_urlsafe(32)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": cfg["scope"],
        "state": state,
        "response_type": "code",
    }
    auth_url = cfg["auth_url"] + "?" + urlencode(params)
    return {"auth_url": auth_url, "state": state}


@app.get("/auth/oauth/{provider}/callback/cli", response_class=HTMLResponse)
async def auth_oauth_callback_cli(
    provider: str,
    request: Request,
    code: str = Query(...),
    state: str = Query(""),
):
    """Handle OAuth callback for CLI — shows the token on a success page."""
    if provider not in _OAUTH_CONFIGS:
        raise HTTPException(400, "Unsupported OAuth provider")

    # ── Supabase backend: exchange code via GoTrue ──
    if is_supabase():
        try:
            auth = get_auth_backend()
            result = auth.exchange_oauth_code(code)
        except Exception as exc:
            logger.error("Supabase CLI OAuth callback failed: %s", exc)
            raise HTTPException(502, f"OAuth login failed: {exc}") from exc

        user = result["user"]
        jwt_token = result["token"]
        name = user.get("name", "")
        email = user.get("email", "")

        conn = _get_db()
        auth_db.log_activity(conn, user["id"], f"signed in via {provider} OAuth (CLI)")

        # Auto-accept pending invites
        if email:
            accepted = auth_db.auto_accept_pending_invites(conn, user["id"], email)
            if accepted:
                auth_db.log_activity(conn, user["id"], f"auto-joined {len(accepted)} workspace(s) from pending invites")

        return _cli_oauth_success_html(name, email, jwt_token)

    # ── Local backend: manual OAuth exchange ──
    creds = _get_oauth_credentials(provider)
    if not creds:
        raise HTTPException(501, f"OAuth {provider} not configured")

    redirect_uri = str(request.base_url).rstrip("/") + f"/auth/oauth/{provider}/callback/cli"

    try:
        token_data = _oauth_exchange_code(provider, code, redirect_uri)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("OAuth token exchange failed for %s: %s", provider, exc)
        raise HTTPException(502, "Failed to exchange authorization code") from exc

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(502, "OAuth provider did not return an access token")

    try:
        user_info = _oauth_get_userinfo(provider, access_token)
    except Exception as exc:
        logger.error("OAuth userinfo fetch failed for %s: %s", provider, exc)
        raise HTTPException(502, "Failed to fetch user profile from OAuth provider") from exc

    # Normalize user fields
    if provider == "google":
        oauth_id = str(user_info.get("id", ""))
        email = user_info.get("email", "")
        name = user_info.get("name", email.split("@")[0])
    else:  # github
        oauth_id = str(user_info.get("id", ""))
        email = user_info.get("email", "")
        name = user_info.get("name") or user_info.get("login", email.split("@")[0])

    if not email or not oauth_id:
        raise HTTPException(400, "Could not retrieve email from OAuth provider")

    conn = _get_db()
    user = auth_db.get_user_by_oauth(conn, provider, oauth_id)
    if not user:
        user = auth_db.get_user_by_email(conn, email)
    if not user:
        user = auth_db.create_user(
            conn, email, name, password_hash="", oauth_provider=provider, oauth_id=oauth_id,
        )
        auth_db.log_activity(conn, user["id"], f"created account via {provider} OAuth (CLI)")
    else:
        auth_db.log_activity(conn, user["id"], f"signed in via {provider} OAuth (CLI)")

    jwt_token = create_token(user["id"], user["email"])

    return _cli_oauth_success_html(name, email, jwt_token)


@app.get("/api/auth/me")
async def api_auth_me(user: dict = Depends(get_current_user)):
    """Return current authenticated user info."""
    conn = _get_db()
    workspaces = auth_db.get_user_workspaces(conn, user["id"])
    usage = auth_db.get_user_usage(conn, user["id"])
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "workspaces": [{"id": w["id"], "name": w["name"], "role": w["member_role"]} for w in workspaces],
        "usage": usage,
    }


# ── HTML pages ──


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await _try_get_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    books = []
    for d in _book_dirs(user):
        meta = _load_book_meta(d)
        books.append({
            "folder": d.name,
            "title": meta.get("title", d.name),
            "author": meta.get("author", "Unknown"),
            "year": meta.get("year", ""),
            "chapters": meta.get("total_chapters", "?"),
            "paragraphs": meta.get("total_paragraphs", "?"),
            "status": meta.get("verification_status", "UNKNOWN"),
            "date": meta.get("ingest_date", ""),
        })

    # Include shared books from workspaces
    conn = _get_db()
    workspaces = auth_db.get_user_workspaces(conn, user["id"])
    shared_books = []
    for ws in workspaces:
        for sb in auth_db.get_shared_books(conn, ws["id"]):
            shared_books.append({
                "folder": sb["book_folder"],
                "workspace": ws["name"],
                "shared_by": sb.get("shared_by_name", ""),
                "permissions": sb["permissions"],
            })

    config = _get_config()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "books": books,
        "total_books": len(books),
        "vault_path": str(_user_vault_path(user)),
        "provider": config.llm.provider,
        "model": config.llm.model,
        "user": user,
        "shared_books": shared_books,
    })


@app.get("/notebook/{folder}", response_class=HTMLResponse)
async def notebook_view(request: Request, folder: str):
    user = await _try_get_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    meta = _load_book_meta(book_dir)

    files = {}
    for fname in ["01_Raw_Structure.md", "02_Logical_Map.md", "03_Concept_Index.md",
                   "06_Patterns.md", "05_Coverage_Report.md"]:
        fpath = book_dir / fname
        files[fname] = fpath.read_text() if fpath.exists() else ""

    extractions = _load_extractions(book_dir)

    chapters = []
    seen = set()
    for ext in extractions:
        pid = ext.get("paragraph_id", "")
        ch_num = pid.split(".")[0].strip("{}") if "." in pid else "00"
        if ch_num not in seen:
            seen.add(ch_num)
            chapters.append({"number": ch_num, "topic": ext.get("topic_sentence", "")[:80]})

    # Load annotations for this book
    conn = _get_db()
    annotations = auth_db.get_annotations(conn, folder, user_id=user["id"])

    return templates.TemplateResponse("notebook.html", {
        "request": request,
        "folder": folder,
        "meta": meta,
        "files": files,
        "chapters": chapters,
        "extractions": extractions[:20],
        "total_extractions": len(extractions),
        "user": user,
        "annotations": annotations,
    })


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    user = await _try_get_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    from ppke.converter import SUPPORTED_EXTENSIONS

    return templates.TemplateResponse("upload.html", {
        "request": request,
        "supported_formats": sorted(SUPPORTED_EXTENSIONS),
        "user": user,
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = await _try_get_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    config = _get_config()

    # Load user's API keys
    conn = _get_db()
    user_api_keys = auth_db.get_user_api_keys(conn, user["id"])
    usage = auth_db.get_user_usage(conn, user["id"])

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "config": {
            "vault_path": str(_user_vault_path(user)),
            "provider": config.llm.provider,
            "model": config.llm.model,
            "default_domain": config.default_domain or "philosophy",
            "processing_mode": config.processing_mode or "linear",
            "has_api_key": bool(config.llm.active_api_key),
            "vector_search": config.enable_vector_search,
            "knowledge_graph": config.enable_knowledge_graph,
        },
        "providers": SUPPORTED_PROVIDERS,
        "user": user,
        "user_api_keys": user_api_keys,
        "usage": usage,
    })


@app.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    user = await _try_get_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    books = []
    for d in _book_dirs(user):
        meta = _load_book_meta(d)
        books.append({"folder": d.name, "title": meta.get("title", d.name)})
    return templates.TemplateResponse("graph.html", {"request": request, "books": books, "user": user})


@app.get("/workspaces", response_class=HTMLResponse)
async def workspaces_page(request: Request):
    user = await _try_get_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    conn = _get_db()
    workspaces = auth_db.get_user_workspaces(conn, user["id"])
    activity = auth_db.get_activity_feed(conn, user_id=user["id"], limit=20)
    return templates.TemplateResponse("workspaces.html", {
        "request": request,
        "user": user,
        "workspaces": workspaces,
        "activity": activity,
    })


# ── REST API endpoints ──


@app.get("/api/books")
async def api_list_books(request: Request):
    user = await _try_get_user(request)
    books = []
    for d in _book_dirs(user):
        meta = _load_book_meta(d)
        books.append({
            "folder": d.name,
            "title": meta.get("title", d.name),
            "author": meta.get("author", "Unknown"),
            "year": meta.get("year"),
            "total_chapters": meta.get("total_chapters", 0),
            "total_paragraphs": meta.get("total_paragraphs", 0),
            "verification_status": meta.get("verification_status", "UNKNOWN"),
            "ingest_date": meta.get("ingest_date", ""),
        })
    return books


@app.get("/api/books/{folder}")
async def api_get_book(request: Request, folder: str):
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    meta = _load_book_meta(book_dir)
    extractions = _load_extractions(book_dir)

    return {
        "folder": folder,
        "meta": meta,
        "total_extractions": len(extractions),
        "files": [f.name for f in book_dir.iterdir() if f.is_file()],
    }


@app.get("/api/books/{folder}/extractions")
async def api_get_extractions(
    request: Request,
    folder: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    extractions = _load_extractions(book_dir)
    return {
        "total": len(extractions),
        "offset": offset,
        "limit": limit,
        "items": extractions[offset : offset + limit],
    }


@app.post("/api/query")
async def api_query(
    request: Request,
    book: str = Form(...),
    question: str = Form(...),
):
    """Query a single book with conversation history and RAG context."""
    user = await _try_get_user(request)
    book = _safe_folder(book)
    from ppke.llm.client import LLMClient
    from ppke.llm.prompts import SINGLE_BOOK_QUERY_SYSTEM, SINGLE_BOOK_QUERY_USER

    config = _get_config()
    book_dir = _user_vault_path(user) / book
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {book}")

    meta = _load_book_meta(book_dir)
    raw_path = book_dir / "01_Raw_Structure.md"
    logical_path = book_dir / "02_Logical_Map.md"
    concept_path = book_dir / "03_Concept_Index.md"

    history = _load_history(book_dir)
    rag_hits, rag_block = _rag_context_block(book, question, config)

    base_prompt = SINGLE_BOOK_QUERY_USER.format(
        book_title=meta.get("title", "Unknown"),
        author=meta.get("author", "Unknown"),
        question=question,
        raw_structure=raw_path.read_text()[:8000] if raw_path.exists() else "N/A",
        logical_map=logical_path.read_text()[:4000] if logical_path.exists() else "N/A",
        concept_index=concept_path.read_text()[:4000] if concept_path.exists() else "N/A",
    )
    user_prompt = (
        _history_context_block(history)
        + rag_block
        + base_prompt
        + '\n\nAlso include "follow_up_questions":["Q?","Q?","Q?"] — '
          "3 concise follow-up questions a reader might ask next."
    )

    client = LLMClient(config.llm)
    result = client.complete_json(SINGLE_BOOK_QUERY_SYSTEM, user_prompt)

    # Persist to chat history
    ts = datetime.now().isoformat()
    history.append({"role": "user", "content": question, "ts": ts})
    history.append({
        "role": "assistant",
        "content": result.get("answer", ""),
        "ts": ts,
        "sources": len(rag_hits),
    })
    _save_history(book_dir, history)

    result["rag_sources"] = len(rag_hits)
    return result


@app.get("/api/query/stream")
async def api_query_stream(
    request: Request,
    book: str = Query(...),
    question: str = Query(...),
):
    """SSE streaming endpoint for book queries with history and RAG.

    Returns server-sent events for:
      - ``token``       — answer tokens (word chunks)
      - ``quotes``      — verbatim quotes from the book
      - ``confidence``  — high / medium / low
      - ``suggestions`` — 3 follow-up question strings
      - ``sources``     — number of RAG paragraph hits used
      - ``[DONE]``      — stream terminator
    """
    user = await _try_get_user(request)
    book = _safe_folder(book)
    from ppke.llm.client import LLMClient
    from ppke.llm.prompts import SINGLE_BOOK_QUERY_SYSTEM, SINGLE_BOOK_QUERY_USER

    config = _get_config()
    book_dir = _user_vault_path(user) / book
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {book}")

    meta = _load_book_meta(book_dir)
    raw_path = book_dir / "01_Raw_Structure.md"
    logical_path = book_dir / "02_Logical_Map.md"
    concept_path = book_dir / "03_Concept_Index.md"

    history = _load_history(book_dir)
    rag_hits, rag_block = _rag_context_block(book, question, config)

    base_prompt = SINGLE_BOOK_QUERY_USER.format(
        book_title=meta.get("title", "Unknown"),
        author=meta.get("author", "Unknown"),
        question=question,
        raw_structure=raw_path.read_text()[:8000] if raw_path.exists() else "N/A",
        logical_map=logical_path.read_text()[:4000] if logical_path.exists() else "N/A",
        concept_index=concept_path.read_text()[:4000] if concept_path.exists() else "N/A",
    )
    user_prompt = (
        _history_context_block(history)
        + rag_block
        + base_prompt
        + '\n\nAlso include "follow_up_questions":["Q?","Q?","Q?"] — '
          "3 concise follow-up questions a reader might ask next."
    )

    async def event_generator():
        try:
            client = LLMClient(config.llm)

            if hasattr(client, 'complete_stream'):
                for token in client.complete_stream(SINGLE_BOOK_QUERY_SYSTEM, user_prompt):
                    yield f"data: {json.dumps({'token': token})}\n\n"
            else:
                result = client.complete_json(SINGLE_BOOK_QUERY_SYSTEM, user_prompt)
                answer = result.get("answer", "No answer generated.")
                # Simulate streaming by chunking 3 words at a time
                words = answer.split(" ")
                chunk: list[str] = []
                for word in words:
                    chunk.append(word)
                    if len(chunk) >= 3:
                        yield f"data: {json.dumps({'token': ' '.join(chunk) + ' '})}\n\n"
                        chunk = []
                if chunk:
                    yield f"data: {json.dumps({'token': ' '.join(chunk)})}\n\n"

                # Rich metadata events
                quotes = result.get("verbatim_quotes", [])
                if quotes:
                    yield f"data: {json.dumps({'quotes': quotes})}\n\n"
                confidence = result.get("confidence")
                if confidence:
                    yield f"data: {json.dumps({'confidence': confidence})}\n\n"
                suggestions = result.get("follow_up_questions", [])
                if suggestions:
                    yield f"data: {json.dumps({'suggestions': suggestions})}\n\n"

                # Persist to history
                ts = datetime.now().isoformat()
                history.append({"role": "user", "content": question, "ts": ts})
                history.append({
                    "role": "assistant",
                    "content": answer,
                    "ts": ts,
                    "sources": len(rag_hits),
                })
                _save_history(book_dir, history)

            # Always send RAG source count
            if rag_hits:
                yield f"data: {json.dumps({'sources': len(rag_hits)})}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("SSE query failed")
            yield f"data: {json.dumps({'token': f'Error: {e}'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/cross-query")
async def api_cross_query(request: Request, question: str = Form(...)):
    user = await _try_get_user(request)
    from ppke.llm.client import LLMClient
    from ppke.pipeline.synthesizer import cross_book_synthesis

    config = _get_config()
    client = LLMClient(config.llm)
    result = cross_book_synthesis(client, _user_vault_path(user), question)
    return result


@app.get("/api/search")
async def api_search(
    request: Request,
    q: str = Query(..., min_length=1),
    book: str | None = None,
    mode: str = Query("fulltext", regex="^(fulltext|hybrid)$"),
):
    user = await _try_get_user(request)

    if mode == "hybrid":
        from ppke.search import hybrid_search

        vault = _user_vault_path(user)
        hits = hybrid_search(
            vault, q, book_filter=book, n_results=100
        )
        results = [
            {
                "book": h.get("book_title", h["book_folder"]),
                "folder": h["book_folder"],
                "paragraph_id": h["paragraph_id"],
                "topic": "",
                "snippet": (h.get("document", "")[:180] + "...")
                if len(h.get("document", "")) > 180
                else h.get("document", ""),
                "score": h.get("score", 0),
                "source": h.get("source", "hybrid"),
            }
            for h in hits
        ]
        return {"query": q, "mode": "hybrid", "total": len(results), "results": results}

    # Default: full-text search (original behaviour)
    results = []
    query_lower = q.lower()

    for d in _book_dirs(user):
        if book and d.name != book:
            continue

        meta = _load_book_meta(d)
        extractions = _load_extractions(d)

        for ext in extractions:
            searchable = " ".join([
                ext.get("original_text", ""),
                ext.get("topic_sentence", ""),
                " ".join(ext.get("explicit_claims", [])),
                " ".join(ext.get("defined_concepts", [])),
            ]).lower()

            if query_lower in searchable:
                idx = searchable.find(query_lower)
                start = max(0, idx - 60)
                end = min(len(searchable), idx + len(query_lower) + 60)
                snippet = ("..." if start > 0 else "") + searchable[start:end] + ("..." if end < len(searchable) else "")

                results.append({
                    "book": meta.get("title", d.name),
                    "folder": d.name,
                    "paragraph_id": ext.get("paragraph_id", "?"),
                    "topic": ext.get("topic_sentence", ""),
                    "snippet": snippet,
                })

        if len(results) >= 100:
            break

    return {"query": q, "mode": "fulltext", "total": len(results), "results": results}


@app.post("/api/upload")
async def api_upload(
    request: Request,
    files: TypingList[UploadFile] = File(...),
    title: str = Form(...),
    author: str = Form(...),
    year: str = Form(""),
    domain: str = Form("philosophy"),
    mode: str = Form("linear"),
):
    """Upload and ingest one or more documents.

    Accepts a list of files.  Each file gets its own background ingestion job.
    Returns ``{"jobs": [...]}`` so the UI can poll each independently.
    """
    user = await _try_get_user(request)
    from ppke.converter import convert_to_markdown

    config = _get_config()
    vault = _user_vault_path(user)
    upload_dir = vault / ".uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    job_ids: list[str] = []

    for file in files:
        safe_filename = re.sub(r"[^\w\.\-]", "_", file.filename or "upload")
        temp_path = upload_dir / safe_filename

        content = await file.read()
        temp_path.write_bytes(content)

        try:
            markdown_text = convert_to_markdown(temp_path)
        except (ValueError, ImportError) as e:
            temp_path.unlink(missing_ok=True)
            raise HTTPException(400, str(e)) from e

        # Use the original (unsuffixed) stem so we don't duplicate extensions
        md_path = upload_dir / f"{temp_path.stem}.md"
        md_path.write_text(markdown_text)

        # Per-file title: use provided title for single uploads; append filename for batch
        file_title = title if len(files) == 1 else f"{title} — {temp_path.stem}"

        job_id = create_job(extra={"filename": safe_filename})
        job_ids.append(job_id)

        def _run_ingest(
            jid=job_id,
            tp=temp_path,
            mp=md_path,
            ftitle=file_title,
            ingest_mode=mode,
        ):
            _start = time.time()
            try:
                from ppke.parser.markdown import parse_markdown_book
                from ppke.pipeline.orchestrator import ingest_book
                from ppke.progress.tracker import ProgressTracker
                from ppke.vectordb.store import VectorStore
                from ppke.graph.knowledge_graph import KnowledgeGraph

                book = parse_markdown_book(mp, ftitle, author, year or None)
                update_job(jid, stage=f"Parsed: {len(book.chapters)} chapters", progress=10)

                tracker = ProgressTracker()
                vector_store = VectorStore(vault) if config.enable_vector_search else None
                knowledge_graph = KnowledgeGraph(vault) if config.enable_knowledge_graph else None

                # Override config vault_path for per-user isolation
                config.vault_path = vault

                def progress_cb(stage: str, detail: str):
                    update_job(jid, stage=f"[{stage}] {detail}")

                book_dir = ingest_book(
                    book, config,
                    domain=domain,
                    progress_callback=progress_cb,
                    tracker=tracker,
                    vector_store=vector_store,
                    knowledge_graph=knowledge_graph,
                    mode=ingest_mode,
                )

                folder_name = book_dir.name if hasattr(book_dir, "name") else str(book_dir)
                update_job(jid, status="completed", progress=100,
                           book_folder=folder_name, stage="Ingestion complete!")
                record_ingestion("file_upload", "completed", time.time() - _start)

            except Exception as e:
                logger.exception("Ingestion failed for job %s", jid)
                update_job(jid, status="failed", error=str(e), stage=f"Failed: {e}")
                capture_exception(e, job_id=jid)
                record_ingestion("file_upload", "failed", time.time() - _start)
            finally:
                tp.unlink(missing_ok=True)
                mp.unlink(missing_ok=True)

        run_task(_run_ingest, job_id=job_id)

    # Backwards-compatible: single file → return {job_id, status}
    # Multiple files → return {jobs: [...], status}
    if len(job_ids) == 1:
        return {"job_id": job_ids[0], "status": "running"}
    return {"jobs": job_ids, "status": "running", "count": len(job_ids)}


@app.post("/api/import-url")
async def api_import_url(
    request: Request,
    url: str = Form(...),
    title: str = Form(""),
    author: str = Form(""),
    year: str = Form(""),
    domain: str = Form("philosophy"),
    mode: str = Form("linear"),
):
    """Import a web page or YouTube video URL and ingest it.

    Detects YouTube URLs automatically and uses yt-dlp + Whisper.
    All other URLs are scraped with trafilatura.

    Returns ``{"job_id": ..., "status": "running"}``.
    """
    user = await _try_get_user(request)
    # Basic URL validation
    url = url.strip()
    if not url.startswith(("http://", "https://", "www.")):
        raise HTTPException(400, "Please provide a valid URL starting with http:// or https://")

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    from ppke.converter.url import is_youtube_url

    is_yt = is_youtube_url(url)

    config = _get_config()
    vault = _user_vault_path(user)
    upload_dir = vault / ".uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    source_type = "youtube" if is_yt else "web"
    job_id = create_job(extra={"url": url, "source_type": source_type})

    def _run_url_ingest():
        _start = time.time()
        md_path: Path | None = None
        try:
            update_job(job_id, stage="Downloading content...", progress=5)

            if is_yt:
                from ppke.converter.youtube import convert_youtube
                markdown_text = convert_youtube(url)
            else:
                from ppke.converter.url import convert_url
                markdown_text = convert_url(url)

            update_job(job_id, stage="Content extracted — starting ingestion...", progress=20)

            # Derive title from Markdown h1 if not provided
            ingest_title = title.strip()
            if not ingest_title:
                for line in markdown_text.splitlines():
                    if line.startswith("# "):
                        ingest_title = line[2:].strip()
                        break
                if not ingest_title:
                    from urllib.parse import urlparse
                    ingest_title = urlparse(url).netloc or "Imported Article"

            ingest_author = author.strip() or "Web Import"

            # Write to temp .md file
            safe_stem = re.sub(r"[^\w\-]", "_", ingest_title)[:60]
            md_path = upload_dir / f"{safe_stem}_{job_id}.md"
            md_path.write_text(markdown_text)

            from ppke.parser.markdown import parse_markdown_book
            from ppke.pipeline.orchestrator import ingest_book
            from ppke.progress.tracker import ProgressTracker
            from ppke.vectordb.store import VectorStore
            from ppke.graph.knowledge_graph import KnowledgeGraph

            book = parse_markdown_book(md_path, ingest_title, ingest_author, year or None)
            update_job(job_id, stage=f"Parsed: {len(book.chapters)} chapters", progress=30)

            tracker = ProgressTracker()
            vector_store = VectorStore(vault) if config.enable_vector_search else None
            knowledge_graph = KnowledgeGraph(vault) if config.enable_knowledge_graph else None

            # Override config vault_path for per-user isolation
            config.vault_path = vault

            def progress_cb(stage: str, detail: str):
                update_job(job_id, stage=f"[{stage}] {detail}")

            book_dir = ingest_book(
                book, config,
                domain=domain,
                progress_callback=progress_cb,
                tracker=tracker,
                vector_store=vector_store,
                knowledge_graph=knowledge_graph,
                mode=mode,
            )

            folder_name = book_dir.name if hasattr(book_dir, "name") else str(book_dir)
            update_job(job_id, status="completed", progress=100,
                       book_folder=folder_name, stage="Ingestion complete!")
            record_ingestion(source_type, "completed", time.time() - _start)

        except Exception as e:
            logger.exception("URL ingestion failed for job %s (url=%s)", job_id, url)
            update_job(job_id, status="failed", error=str(e), stage=f"Failed: {e}")
            capture_exception(e, job_id=job_id, url=url)
            record_ingestion(source_type, "failed", time.time() - _start)
        finally:
            if md_path is not None:
                md_path.unlink(missing_ok=True)

    run_task(_run_url_ingest, job_id=job_id)

    return {"job_id": job_id, "status": "running", "source_type": source_type}


@app.post("/api/import-github-pr")
async def api_import_github_pr(
    request: Request,
    url: str = Form(...),
    title: str = Form(""),
    author: str = Form(""),
    domain: str = Form("gh_pr"),
    token: str = Form(""),
    mode: str = Form("linear"),
):
    """Import a GitHub Pull Request URL and ingest it.

    Fetches PR metadata, diff, comments, and reviews via the GitHub API,
    converts to Markdown, and runs the full analysis pipeline.

    Returns ``{"job_id": ..., "status": "running"}``.
    """
    user = await _try_get_user(request)

    url = url.strip()
    from ppke.converter.github_pr import is_github_pr_url

    if not is_github_pr_url(url):
        raise HTTPException(
            400,
            "Please provide a valid GitHub PR URL "
            "(e.g., https://github.com/owner/repo/pull/123)",
        )

    gh_token = token.strip() or os.environ.get("GITHUB_TOKEN") or None

    config = _get_config()
    vault = _user_vault_path(user)
    upload_dir = vault / ".uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    job_id = create_job(extra={"url": url, "source_type": "github_pr"})

    def _run_pr_ingest():
        _start = time.time()
        md_path: Path | None = None
        try:
            update_job(job_id, stage="Fetching PR from GitHub...", progress=5)

            from ppke.converter.github_pr import convert_github_pr, parse_pr_url

            markdown_text = convert_github_pr(url, token=gh_token)

            update_job(job_id, stage="PR fetched — starting analysis...", progress=20)

            _, _, pr_number = parse_pr_url(url)

            ingest_title = title.strip()
            if not ingest_title:
                for line in markdown_text.splitlines():
                    if line.startswith("# "):
                        ingest_title = line[2:].strip()
                        break
                if not ingest_title:
                    ingest_title = f"PR #{pr_number}"

            ingest_author = author.strip() or "GitHub PR"

            safe_stem = re.sub(r"[^\w\-]", "_", ingest_title)[:60]
            md_path = upload_dir / f"{safe_stem}_{job_id}.md"
            md_path.write_text(markdown_text)

            from ppke.parser.markdown import parse_markdown_book
            from ppke.pipeline.orchestrator import ingest_book
            from ppke.progress.tracker import ProgressTracker
            from ppke.vectordb.store import VectorStore
            from ppke.graph.knowledge_graph import KnowledgeGraph

            book = parse_markdown_book(md_path, ingest_title, ingest_author)
            update_job(job_id, stage=f"Parsed: {len(book.chapters)} chapters", progress=30)

            tracker = ProgressTracker()
            vector_store = VectorStore(vault) if config.enable_vector_search else None
            knowledge_graph = KnowledgeGraph(vault) if config.enable_knowledge_graph else None

            config.vault_path = vault

            def progress_cb(stage: str, detail: str):
                update_job(job_id, stage=f"[{stage}] {detail}")

            book_dir = ingest_book(
                book, config,
                domain=domain,
                progress_callback=progress_cb,
                tracker=tracker,
                vector_store=vector_store,
                knowledge_graph=knowledge_graph,
                mode=mode,
            )

            folder_name = book_dir.name if hasattr(book_dir, "name") else str(book_dir)
            update_job(job_id, status="completed", progress=100,
                       book_folder=folder_name, stage="PR analysis complete!")
            record_ingestion("github_pr", "completed", time.time() - _start)

        except Exception as e:
            logger.exception("GitHub PR ingestion failed for job %s (url=%s)", job_id, url)
            update_job(job_id, status="failed", error=str(e), stage=f"Failed: {e}")
            capture_exception(e, job_id=job_id, url=url)
            record_ingestion("github_pr", "failed", time.time() - _start)
        finally:
            if md_path is not None:
                md_path.unlink(missing_ok=True)

    run_task(_run_pr_ingest, job_id=job_id)

    return {"job_id": job_id, "status": "running", "source_type": "github_pr"}


@app.post("/api/github/webhook")
async def api_github_webhook(request: Request):
    """GitHub webhook endpoint for automatic PR ingestion.

    Register this URL as a webhook in your GitHub repository settings.
    Supports ``pull_request`` events (opened, synchronize, reopened).

    Optionally verify webhook signatures by setting ``GITHUB_WEBHOOK_SECRET``
    environment variable.

    Returns ``{"job_id": ..., "status": "running"}`` on success.
    """
    # Verify webhook signature if secret is configured
    webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if webhook_secret:
        import hashlib
        import hmac

        signature = request.headers.get("X-Hub-Signature-256", "")
        body = await request.body()
        expected = "sha256=" + hmac.new(
            webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(403, "Invalid webhook signature")
        payload = json.loads(body)
    else:
        payload = await request.json()

    # Only process pull_request events
    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return {"status": "pong"}

    if event != "pull_request":
        return {"status": "ignored", "reason": f"Event '{event}' not handled"}

    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"Action '{action}' not handled"}

    pr = payload.get("pull_request", {})
    pr_url = pr.get("html_url", "")

    if not pr_url:
        raise HTTPException(400, "Missing pull_request.html_url in payload")

    from ppke.converter.github_pr import is_github_pr_url

    if not is_github_pr_url(pr_url):
        raise HTTPException(400, f"Invalid PR URL in payload: {pr_url}")

    gh_token = os.environ.get("GITHUB_TOKEN")
    config = _get_config()
    vault = config.vault_path
    upload_dir = vault / ".uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    pr_title = pr.get("title", "Untitled PR")
    pr_author = pr.get("user", {}).get("login", "unknown")
    pr_number = pr.get("number", 0)

    job_id = create_job(extra={
        "url": pr_url,
        "source_type": "github_webhook",
        "pr_number": pr_number,
        "action": action,
    })

    def _run_webhook_ingest():
        _start = time.time()
        md_path: Path | None = None
        try:
            update_job(job_id, stage="Fetching PR from GitHub...", progress=5)

            from ppke.converter.github_pr import convert_github_pr

            markdown_text = convert_github_pr(pr_url, token=gh_token)

            update_job(job_id, stage="PR fetched — starting analysis...", progress=20)

            safe_stem = re.sub(r"[^\w\-]", "_", pr_title)[:60]
            md_path = upload_dir / f"{safe_stem}_{job_id}.md"
            md_path.write_text(markdown_text)

            from ppke.parser.markdown import parse_markdown_book
            from ppke.pipeline.orchestrator import ingest_book
            from ppke.progress.tracker import ProgressTracker
            from ppke.vectordb.store import VectorStore
            from ppke.graph.knowledge_graph import KnowledgeGraph

            book = parse_markdown_book(md_path, pr_title, pr_author)
            update_job(job_id, stage=f"Parsed: {len(book.chapters)} chapters", progress=30)

            tracker = ProgressTracker()
            vector_store = VectorStore(vault) if config.enable_vector_search else None
            knowledge_graph = KnowledgeGraph(vault) if config.enable_knowledge_graph else None

            config.vault_path = vault

            def progress_cb(stage: str, detail: str):
                update_job(job_id, stage=f"[{stage}] {detail}")

            book_dir = ingest_book(
                book, config,
                domain="gh_pr",
                progress_callback=progress_cb,
                tracker=tracker,
                vector_store=vector_store,
                knowledge_graph=knowledge_graph,
            )

            folder_name = book_dir.name if hasattr(book_dir, "name") else str(book_dir)
            update_job(job_id, status="completed", progress=100,
                       book_folder=folder_name, stage="Webhook PR analysis complete!")
            record_ingestion("github_webhook", "completed", time.time() - _start)

        except Exception as e:
            logger.exception("Webhook PR ingestion failed for job %s (url=%s)", job_id, pr_url)
            update_job(job_id, status="failed", error=str(e), stage=f"Failed: {e}")
            capture_exception(e, job_id=job_id, url=pr_url)
            record_ingestion("github_webhook", "failed", time.time() - _start)
        finally:
            if md_path is not None:
                md_path.unlink(missing_ok=True)

    run_task(_run_webhook_ingest, job_id=job_id)

    return {"job_id": job_id, "status": "running", "source_type": "github_webhook",
            "pr_number": pr_number}


@app.post("/api/import-zotero")
async def api_import_zotero(
    request: Request,
    file: UploadFile = File(...),
    domain: str = Form("philosophy"),
    mode: str = Form("linear"),
):
    """Import a Zotero export file (.bib, .json, or .rdf).

    Parses bibliographic entries, deduplicates, converts to Markdown,
    and starts a background ingestion job.

    Returns ``{"job_id": ..., "status": "running", "entries": N}``.
    """
    user = await _try_get_user(request)
    config = _get_config()
    vault = _user_vault_path(user)
    upload_dir = vault / ".uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = re.sub(r"[^\w\.\-]", "_", Path(file.filename or "zotero_import").name)
    # Prevent path traversal via dot sequences
    safe_filename = safe_filename.lstrip(".")
    if not safe_filename:
        safe_filename = "zotero_import"
    temp_path = upload_dir / safe_filename
    content = await file.read()
    temp_path.write_bytes(content)

    # Parse and convert
    try:
        from ppke.converter.zotero import parse_zotero_file, deduplicate_entries, entries_to_markdown

        entries = parse_zotero_file(temp_path)
        entries = deduplicate_entries(entries)
        if not entries:
            temp_path.unlink(missing_ok=True)
            raise HTTPException(400, "No bibliographic entries found in the uploaded file.")

        source_name = temp_path.stem.replace("_", " ").replace("-", " ").title()
        markdown_text = entries_to_markdown(entries, source_name=source_name)
    except ValueError as e:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(400, str(e)) from e

    entry_count = len(entries)

    # Derive title and author from first entry or filename
    ingest_title = source_name
    ingest_author = entries[0].get("author", "Zotero Import") if entries else "Zotero Import"

    md_path = upload_dir / f"{temp_path.stem}_zotero.md"
    md_path.write_text(markdown_text)

    job_id = create_job(extra={"filename": safe_filename, "source_type": "zotero", "entries": entry_count})

    def _run_zotero_ingest(jid=job_id, tp=temp_path, mp=md_path):
        _start = time.time()
        try:
            from ppke.parser.markdown import parse_markdown_book
            from ppke.pipeline.orchestrator import ingest_book
            from ppke.progress.tracker import ProgressTracker
            from ppke.vectordb.store import VectorStore
            from ppke.graph.knowledge_graph import KnowledgeGraph

            book = parse_markdown_book(mp, ingest_title, ingest_author, None)
            update_job(jid, stage=f"Parsed: {entry_count} Zotero entries", progress=20)

            tracker = ProgressTracker()
            vector_store = VectorStore(vault) if config.enable_vector_search else None
            knowledge_graph = KnowledgeGraph(vault) if config.enable_knowledge_graph else None

            config.vault_path = vault

            def progress_cb(stage: str, detail: str):
                update_job(jid, stage=f"[{stage}] {detail}")

            book_dir = ingest_book(
                book, config,
                domain=domain,
                progress_callback=progress_cb,
                tracker=tracker,
                vector_store=vector_store,
                knowledge_graph=knowledge_graph,
                mode=mode,
            )

            folder_name = book_dir.name if hasattr(book_dir, "name") else str(book_dir)
            update_job(jid, status="completed", progress=100,
                       book_folder=folder_name, stage="Ingestion complete!")
            record_ingestion("zotero", "completed", time.time() - _start)

        except Exception as e:
            logger.exception("Zotero ingestion failed for job %s", jid)
            update_job(jid, status="failed", error=str(e), stage=f"Failed: {e}")
            capture_exception(e, job_id=jid)
            record_ingestion("zotero", "failed", time.time() - _start)
        finally:
            tp.unlink(missing_ok=True)
            mp.unlink(missing_ok=True)

    run_task(_run_zotero_ingest, job_id=job_id)

    return {"job_id": job_id, "status": "running", "source_type": "zotero", "entries": entry_count}


@app.get("/api/jobs/{job_id}")
async def api_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    return job


@app.get("/api/stats")
async def api_stats(request: Request):
    user = await _try_get_user(request)
    user_id = user["id"] if user else "anon"

    # Check cache first
    cache = get_cache()
    ck = cache_key("stats", user_id)
    cached = cache.get(ck)
    if cached:
        from ppke.infra.metrics import record_cache_hit
        record_cache_hit()
        return cached

    from ppke.infra.metrics import record_cache_miss
    record_cache_miss()

    books = _book_dirs(user)
    total_chapters = 0
    total_paragraphs = 0
    total_concepts = 0

    for d in books:
        meta = _load_book_meta(d)
        total_chapters += meta.get("total_chapters", 0)
        total_paragraphs += meta.get("total_paragraphs", 0)
        extractions = _load_extractions(d)
        for ext in extractions:
            total_concepts += len(ext.get("defined_concepts", []))

    result = {
        "total_books": len(books),
        "total_chapters": total_chapters,
        "total_paragraphs": total_paragraphs,
        "total_concepts": total_concepts,
        "vault_path": str(_user_vault_path(user)),
    }
    cache.set(ck, result, ttl=60)
    return result


@app.get("/api/graph")
async def api_graph_data(request: Request, book: str | None = None):
    user = await _try_get_user(request)
    vault = _user_vault_path(user)
    graph_path = vault / "knowledge_graph.json"

    if graph_path.exists():
        data = json.loads(graph_path.read_text())
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        if book:
            relevant_ids = set()
            for edge in edges:
                src = edge.get("src") or edge.get("source", "")
                dst = edge.get("dst") or edge.get("target", "")
                if book in src or book in dst:
                    relevant_ids.add(src)
                    relevant_ids.add(dst)
            nodes = [n for n in nodes if n["id"] in relevant_ids]
            edges = [e for e in edges
                     if (e.get("src") or e.get("source", "")) in relevant_ids
                     and (e.get("dst") or e.get("target", "")) in relevant_ids]

        d3_nodes = []
        for n in nodes:
            node_type = n.get("type", "concept")
            d3_nodes.append({
                "id": n["id"], "label": n.get("label", n["id"]),
                "type": node_type,
                "group": {"concept": 1, "book": 2, "paragraph": 3}.get(node_type, 1),
                "size": n.get("weight", 1),
            })
        d3_links = [{"source": e.get("src") or e.get("source"),
                      "target": e.get("dst") or e.get("target"),
                      "relation": e.get("rel") or e.get("relation", "related_to")}
                     for e in edges]
        return {"nodes": d3_nodes, "links": d3_links}

    # Fallback: build from extractions
    nodes_map: dict[str, dict] = {}
    links: list[dict] = []

    for d in _book_dirs():
        if book and d.name != book:
            continue
        meta = _load_book_meta(d)
        book_id = f"book:{d.name}"
        nodes_map[book_id] = {
            "id": book_id, "label": meta.get("title", d.name),
            "type": "book", "group": 2, "size": 5,
        }
        extractions = _load_extractions(d)
        for ext in extractions:
            concepts = ext.get("defined_concepts", [])
            for concept in concepts:
                c_id = f"concept:{concept.lower().strip()}"
                if c_id not in nodes_map:
                    nodes_map[c_id] = {
                        "id": c_id, "label": concept, "type": "concept", "group": 1, "size": 1,
                    }
                else:
                    nodes_map[c_id]["size"] = nodes_map[c_id].get("size", 1) + 1
                links.append({"source": book_id, "target": c_id, "relation": "defines"})
            for i, c1 in enumerate(concepts):
                for c2 in concepts[i + 1:]:
                    links.append({
                        "source": f"concept:{c1.lower().strip()}",
                        "target": f"concept:{c2.lower().strip()}",
                        "relation": "related_to",
                    })

    return {"nodes": list(nodes_map.values()), "links": links}


@app.post("/api/audio-overview")
async def api_generate_audio_overview(
    request: Request,
    folder: str = Form(...),
    tts_provider: str = Form("edge"),
    voice_preset: str = Form("natural"),
    length: str = Form("medium"),
    topic: str = Form(""),
):
    """Generate a podcast-style audio overview with voice/length/topic options."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    from ppke.audio.overview import (
        VOICE_PRESETS,
        generate_script,
        synthesize_from_preset,
        synthesize_audio,
    )
    from ppke.llm.client import LLMClient

    config = _get_config()
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    client = LLMClient(config.llm)

    try:
        script = generate_script(
            book_dir,
            client,
            length=length,
            topic=topic.strip() or None,
        )
    except Exception as e:
        raise HTTPException(500, f"Script generation failed: {e}") from e

    script_path = book_dir / "audio_script.json"
    script_path.write_text(json.dumps(script, indent=2))

    audio_path = book_dir / "audio_overview.mp3"
    try:
        if voice_preset in VOICE_PRESETS:
            synthesize_from_preset(script, audio_path, voice_preset)
        else:
            synthesize_audio(script, audio_path, provider=tts_provider)
    except Exception as e:
        raise HTTPException(500, f"Audio synthesis failed: {e}") from e

    return {
        "status": "completed",
        "audio_path": str(audio_path),
        "script": script,
    }


@app.post("/api/audio-overview/cross-book")
async def api_generate_cross_book_audio(
    request: Request,
    folder_a: str = Form(...),
    folder_b: str = Form(...),
    voice_preset: str = Form("natural"),
    length: str = Form("medium"),
):
    """Generate a comparative podcast episode for two books."""
    user = await _try_get_user(request)
    folder_a = _safe_folder(folder_a)
    folder_b = _safe_folder(folder_b)
    from ppke.audio.overview import (
        VOICE_PRESETS,
        generate_cross_book_script,
        synthesize_from_preset,
    )
    from ppke.llm.client import LLMClient

    config = _get_config()
    vault = _user_vault_path(user)
    book_dir_a = vault / folder_a
    book_dir_b = vault / folder_b
    if not book_dir_a.exists():
        raise HTTPException(404, f"Book not found: {folder_a}")
    if not book_dir_b.exists():
        raise HTTPException(404, f"Book not found: {folder_b}")

    client = LLMClient(config.llm)

    try:
        script = generate_cross_book_script(book_dir_a, book_dir_b, client, length=length)
    except Exception as e:
        raise HTTPException(500, f"Cross-book script generation failed: {e}") from e

    # Save to first book's directory
    out_dir = book_dir_a
    script_path = out_dir / "cross_book_script.json"
    script_path.write_text(json.dumps(script, indent=2))

    audio_path = out_dir / "cross_book_audio.mp3"
    try:
        synthesize_from_preset(script, audio_path, voice_preset)
    except Exception as e:
        raise HTTPException(500, f"Audio synthesis failed: {e}") from e

    return {
        "status": "completed",
        "audio_path": str(audio_path),
        "script": script,
        "folder": folder_a,
    }


@app.get("/api/audio/{folder}/transcript")
async def api_audio_transcript(request: Request, folder: str):
    """Return the audio script as a readable Markdown transcript."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    script_path = book_dir / "audio_script.json"
    if not script_path.exists():
        raise HTTPException(404, "No audio script found — generate an audio overview first")

    from ppke.audio.overview import script_to_transcript

    script = json.loads(script_path.read_text())
    return {"transcript": script_to_transcript(script), "turns": len(script)}


@app.get("/api/audio/presets")
async def api_audio_presets():
    """Return available voice presets and length options."""
    from ppke.audio.overview import VOICE_PRESETS, LENGTH_PRESETS

    return {
        "voices": {k: {"label": v["label"], "provider": v["provider"]} for k, v in VOICE_PRESETS.items()},
        "lengths": {k: v["label"] for k, v in LENGTH_PRESETS.items()},
    }


@app.post("/api/import-rss")
async def api_import_rss(
    rss_url: str = Form(...),
    max_episodes: int = Form(3),
    domain: str = Form("philosophy"),
):
    """Import podcast episodes from an RSS feed.

    Parses the feed, downloads the most recent audio episodes, transcribes
    them via Whisper, and ingests each as a separate book.
    """
    from ppke.audio.rss import parse_feed

    try:
        feed_info = parse_feed(rss_url, max_episodes=min(max_episodes, 5))
    except Exception as e:
        raise HTTPException(400, f"Failed to parse RSS feed: {e}") from e

    if not feed_info["episodes"]:
        raise HTTPException(400, "No audio episodes found in this RSS feed")

    # Start background jobs for each episode
    job_ids: list[str] = []
    for ep in feed_info["episodes"]:
        job_id = _start_rss_episode_job(
            ep, feed_info["title"], feed_info["author"], domain
        )
        job_ids.append(job_id)

    return {
        "status": "queued",
        "podcast": feed_info["title"],
        "episodes": len(feed_info["episodes"]),
        "jobs": job_ids,
    }


def _start_rss_episode_job(
    episode: dict, podcast_title: str, podcast_author: str,
    domain: str,  # pylint: disable=unused-argument
) -> str:
    """Start a background ingestion job for one podcast episode."""
    job_id = create_job(extra={"stage": "Downloading episode..."})

    def _worker():
        _start = time.time()
        try:
            from ppke.audio.rss import download_and_transcribe

            update_job(job_id, stage=f"Downloading: {episode['title'][:40]}...", progress=10)

            markdown = download_and_transcribe(
                episode["url"],
                episode_title=episode["title"],
                podcast_title=podcast_title,
                podcast_author=podcast_author,
            )

            update_job(job_id, stage="Transcription complete — starting ingestion...", progress=50)

            # Create book from markdown
            from ppke.parser.markdown import parse_markdown_text

            config = _get_config()
            book = parse_markdown_text(markdown, episode["title"], podcast_author)
            book.title = episode["title"]
            book.author = podcast_author

            # Run ingestion
            from ppke.pipeline.orchestrator import ingest_book

            folder = ingest_book(
                book, config,
                progress_callback=lambda p, s: (
                    update_job(job_id, progress=50 + int(p * 0.5), stage=s)
                ),
            )

            update_job(job_id, status="completed", progress=100, stage="Done", book_folder=folder)
            record_ingestion("rss_episode", "completed", time.time() - _start)
        except Exception as exc:
            logger.exception("RSS episode ingestion failed: %s", exc)
            update_job(job_id, status="failed", stage=str(exc), error=str(exc))
            capture_exception(exc, job_id=job_id)
            record_ingestion("rss_episode", "failed", time.time() - _start)

    run_task(_worker, job_id=job_id)
    return job_id


@app.post("/api/audio/upload-recording")
async def api_upload_recording(
    recording: UploadFile = File(...),
    title: str = Form("Voice Recording"),
    author: str = Form("User"),
    domain: str = Form("philosophy"),  # pylint: disable=unused-argument
):
    """Accept a browser audio recording (WebM/MP3 blob), transcribe, and ingest."""
    import tempfile

    # Save uploaded blob to temp file
    suffix = ".webm" if "webm" in (recording.content_type or "") else ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await recording.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    job_id = create_job(extra={"stage": "Transcribing recording..."})

    def _worker():
        _start = time.time()
        try:
            from ppke.audio.transcriber import transcribe

            update_job(job_id, progress=10)
            markdown = transcribe(tmp_path)

            update_job(job_id, stage="Transcription complete — starting ingestion...", progress=50)

            # Clean up temp file
            try:
                tmp_path.unlink()
            except OSError:
                pass

            from ppke.parser.markdown import parse_markdown_text

            config = _get_config()
            book = parse_markdown_text(f"# {title}\n\n**Author:** {author}\n\n---\n\n{markdown}", title, author)
            book.title = title
            book.author = author

            from ppke.pipeline.orchestrator import ingest_book

            folder = ingest_book(
                book, config,
                progress_callback=lambda p, s: (
                    update_job(job_id, progress=50 + int(p * 0.5), stage=s)
                ),
            )

            update_job(job_id, status="completed", progress=100, stage="Done", book_folder=folder)
            record_ingestion("recording", "completed", time.time() - _start)
        except Exception as exc:
            logger.exception("Recording ingestion failed: %s", exc)
            update_job(job_id, status="failed", stage=str(exc), error=str(exc))
            capture_exception(exc, job_id=job_id)
            record_ingestion("recording", "failed", time.time() - _start)
            try:
                tmp_path.unlink()
            except OSError:
                pass

    run_task(_worker, job_id=job_id)
    return {"job_id": job_id, "status": "running"}


@app.get("/api/audio/{folder}")
async def api_serve_audio(request: Request, folder: str):
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    audio_path = _user_vault_path(user) / folder / "audio_overview.mp3"
    if not audio_path.exists():
        raise HTTPException(404, "Audio overview not generated yet")

    def iterfile():
        with open(audio_path, "rb") as f:
            yield from f

    return StreamingResponse(iterfile(), media_type="audio/mpeg")


# ── Speaker diarization endpoints ────────────────────────────────────


@app.post("/api/audio/diarize")
async def api_diarize_audio(
    request: Request,
    audio: UploadFile = File(...),
    num_speakers: int | None = Form(None),
    min_speakers: int | None = Form(None),
    max_speakers: int | None = Form(None),
    folder: str | None = Form(None),
):
    """Run speaker diarization on an uploaded audio file.

    Optionally provide *folder* to associate results with an existing book.
    Returns a job ID; poll ``/api/jobs/{job_id}`` for status.
    """
    import tempfile

    suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    job_id = create_job(extra={"stage": "Running speaker diarization..."})

    safe = _safe_folder(folder) if folder else None

    def _worker():
        _start = time.time()
        try:
            from ppke.audio.diarization import diarize, save_diarization

            update_job(job_id, progress=10, stage="Loading diarization pipeline...")
            segments = diarize(
                tmp_path,
                num_speakers=num_speakers,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
            update_job(job_id, progress=80, stage="Saving results...")

            # Persist to book folder when provided
            if safe:
                vault = _get_config().get("vault_path", "vault")
                book_dir = Path(vault) / safe
                if book_dir.is_dir():
                    save_diarization(segments, book_dir / "diarization.json")

            update_job(
                job_id,
                status="completed",
                progress=100,
                stage="Done",
                result={
                    "segments": segments,
                    "num_speakers": len({s["speaker"] for s in segments}),
                    "num_segments": len(segments),
                },
            )
            record_ingestion("diarization", "completed", time.time() - _start)
        except Exception as exc:
            logger.exception("Diarization failed: %s", exc)
            update_job(job_id, status="failed", stage=str(exc), error=str(exc))
            capture_exception(exc, job_id=job_id)
            record_ingestion("diarization", "failed", time.time() - _start)
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    run_task(_worker, job_id=job_id)
    return {"job_id": job_id, "status": "running"}


@app.get("/api/audio/{folder}/diarization")
async def api_get_diarization(request: Request, folder: str):
    """Return saved diarization results for a book folder."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    diar_path = _user_vault_path(user) / folder / "diarization.json"
    if not diar_path.exists():
        raise HTTPException(404, "No diarization results found — run diarization first")

    from ppke.audio.diarization import load_diarization, format_diarized_transcript

    segments = load_diarization(diar_path)
    transcript = format_diarized_transcript(segments, title=folder.replace("_", " ").title())
    return {
        "segments": segments,
        "transcript": transcript,
        "num_speakers": len({s["speaker"] for s in segments}),
        "num_segments": len(segments),
    }


@app.put("/api/audio/{folder}/diarization")
async def api_update_diarization(request: Request, folder: str):
    """Update (edit) diarization results for a book folder.

    Expects a JSON body with ``{"segments": [...]}``.
    """
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.is_dir():
        raise HTTPException(404, "Book folder not found")

    body = await request.json()
    segments = body.get("segments")
    if not isinstance(segments, list):
        raise HTTPException(400, "Request body must contain a 'segments' list")

    from ppke.audio.diarization import save_diarization, format_diarized_transcript

    save_diarization(segments, book_dir / "diarization.json")
    transcript = format_diarized_transcript(segments, title=folder.replace("_", " ").title())
    return {
        "segments": segments,
        "transcript": transcript,
        "num_speakers": len({s["speaker"] for s in segments}),
        "num_segments": len(segments),
    }


@app.get("/api/config")
async def api_config(request: Request):
    user = await _try_get_user(request)
    config = _get_config()
    return {
        "vault_path": str(_user_vault_path(user)),
        "provider": config.llm.provider,
        "model": config.llm.model,
        "small_model": config.llm.effective_small_model,
        "default_domain": config.default_domain,
        "vector_search": config.enable_vector_search,
        "knowledge_graph": config.enable_knowledge_graph,
        "has_api_key": bool(config.llm.active_api_key),
    }


@app.post("/api/settings")
async def api_update_settings(
    provider: str = Form(...),
    model: str = Form(...),
    api_key: str = Form(""),
    default_domain: str = Form("philosophy"),
    processing_mode: str = Form("linear"),
    vector_search: bool = Form(False),
    knowledge_graph: bool = Form(False),
):
    """Update PPKE configuration via the web UI."""
    from ppke.config import save_env_file

    config = _get_config()
    config.llm.provider = provider
    config.llm.model = model
    config.default_domain = default_domain
    config.processing_mode = processing_mode
    config.enable_vector_search = vector_search
    config.enable_knowledge_graph = knowledge_graph
    config.save()

    # Save API key if provided
    if api_key.strip():
        env_var = PROVIDER_ENV_VARS.get(provider, "API_KEY")
        save_env_file({env_var: api_key.strip()})

    return {"status": "ok", "message": "Settings saved"}


# ── Chat history endpoints ──


@app.get("/api/history/{folder}")
async def api_get_history(request: Request, folder: str):
    """Return the full chat history for a book as a list of messages."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")
    return {"folder": folder, "messages": _load_history(book_dir)}


@app.delete("/api/history/{folder}")
async def api_clear_history(request: Request, folder: str):
    """Delete the chat history for a book."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    path = book_dir / "chat_history.json"
    if path.exists():
        path.unlink()
    return {"status": "cleared", "folder": folder}


# ── Content generation endpoints ──


@app.get("/api/summary/{folder}")
async def api_get_summary(request: Request, folder: str):
    """Return cached executive summary, or ``{status: not_generated}``."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    path = book_dir / "summary.md"
    if not path.exists():
        return {"status": "not_generated", "content": None}
    return {"status": "ready", "content": path.read_text()}


@app.post("/api/summary/{folder}")
async def api_generate_summary(request: Request, folder: str):
    """Generate and cache a one-page executive summary for a book."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    from ppke.llm.client import LLMClient

    config = _get_config()
    meta = _load_book_meta(book_dir)
    raw_path = book_dir / "01_Raw_Structure.md"
    logical_path = book_dir / "02_Logical_Map.md"
    concept_path = book_dir / "03_Concept_Index.md"

    system = (
        "You are an expert academic summarizer. "
        "Write clear, structured Markdown. Be concise and precise."
    )
    user = f"""Write a one-page executive summary of "{meta.get('title', 'Unknown')}" by {meta.get('author', 'Unknown')}.

Use this Markdown structure exactly:
# Executive Summary: {meta.get('title', 'Unknown')}
*{meta.get('author', 'Unknown')}{f", {meta.get('year')}" if meta.get('year') else ""}*

## Core Thesis
[1–2 sentences stating the central argument]

## Key Arguments
[3–5 bullet points — the main argumentative moves]

## Central Concepts
[3–5 bullet points — key terms and their meanings in this work]

## Critical Insights
[2–3 bullets — surprising, counter-intuitive, or especially original claims]

## Significance
[Why this work matters — intellectual, historical, or practical impact]

---
SOURCE MATERIAL:

Raw structure (first 6000 chars):
{raw_path.read_text()[:6000] if raw_path.exists() else "N/A"}

Logical map (first 3000 chars):
{logical_path.read_text()[:3000] if logical_path.exists() else "N/A"}

Concept index (first 2000 chars):
{concept_path.read_text()[:2000] if concept_path.exists() else "N/A"}"""

    client = LLMClient(config.llm)
    content = client.complete(system, user)

    summary_path = book_dir / "summary.md"
    summary_path.write_text(content)
    return {"status": "ready", "content": content}


@app.post("/api/study-guide/{folder}")
async def api_generate_study_guide(request: Request, folder: str):
    """Generate and cache a chapter-by-chapter study guide."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    path = book_dir / "study_guide.md"
    if path.exists():
        return {"status": "ready", "content": path.read_text()}

    from ppke.llm.client import LLMClient

    config = _get_config()
    meta = _load_book_meta(book_dir)
    extractions = _load_extractions(book_dir)

    # Group extractions by chapter
    chapters: dict[str, list[dict]] = {}
    for ext in extractions:
        pid = ext.get("paragraph_id", "")
        ch = pid.split(".")[0].strip("{}") if "." in pid else "00"
        chapters.setdefault(ch, []).append(ext)

    chapter_summaries = []
    for ch_num in sorted(chapters.keys())[:20]:  # cap at 20 chapters
        paras = chapters[ch_num]
        claims = []
        concepts = []
        for p in paras[:10]:
            claims.extend(p.get("explicit_claims", [])[:2])
            concepts.extend(p.get("defined_concepts", [])[:2])
        chapter_summaries.append(
            f"Chapter {ch_num}: {len(paras)} paragraphs | "
            f"Claims: {'; '.join(claims[:3])} | "
            f"Concepts: {', '.join(list(dict.fromkeys(concepts))[:5])}"
        )

    system = "You are an academic study guide writer. Write clear, student-friendly Markdown."
    user = f"""Write a study guide for "{meta.get('title', 'Unknown')}" by {meta.get('author', 'Unknown')}.

Chapter data:
{chr(10).join(chapter_summaries)}

For each chapter produce:
## Chapter [N]: [Inferred Title]
**Key Claims:** [bullet list]
**Defined Concepts:** [bullet list with brief definitions]
**Discussion Questions:** [2–3 questions]
**Important Quotes to Find:** [describe what to look for]

End with a ## Review section with 5 essay questions spanning the whole work."""

    client = LLMClient(config.llm)
    content = client.complete(system, user)

    path.write_text(content)
    return {"status": "ready", "content": content}


@app.get("/api/study-guide/{folder}")
async def api_get_study_guide(request: Request, folder: str):
    """Return cached study guide, or ``{status: not_generated}``."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    path = book_dir / "study_guide.md"
    if not path.exists():
        return {"status": "not_generated", "content": None}
    return {"status": "ready", "content": path.read_text()}


@app.get("/api/glossary/{folder}")
async def api_get_glossary(request: Request, folder: str):
    """Return an auto-generated glossary from concept extraction data.

    No LLM call required — builds from ``extractions.json`` directly.
    Returns ``{"terms": [{"concept": str, "definition": str, "paragraph_id": str}]}``.
    """
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    extractions = _load_extractions(book_dir)
    terms: dict[str, dict] = {}

    for ext in extractions:
        pid = ext.get("paragraph_id", "?")
        original = ext.get("original_text", "")
        for concept in ext.get("defined_concepts", []):
            key = concept.lower().strip()
            if key in terms:
                continue  # keep first definition only
            # Try to find a sentence in original_text that defines this concept
            definition = ""
            for sentence in original.split(". "):
                if concept.lower() in sentence.lower():
                    definition = sentence.strip().rstrip(".") + "."
                    break
            terms[key] = {
                "concept": concept,
                "definition": definition or f"Defined/discussed in paragraph {pid}.",
                "paragraph_id": pid,
            }

    sorted_terms = sorted(terms.values(), key=lambda t: t["concept"].lower())
    return {"folder": folder, "total": len(sorted_terms), "terms": sorted_terms}


@app.get("/api/flashcards/{folder}")
async def api_get_flashcards(request: Request, folder: str):
    """Return Anki-importable flashcards as a TSV download.

    Each card is:  Front (concept) → Back (definition + paragraph ID).
    The ``Content-Disposition`` header triggers browser download.
    """
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    meta = _load_book_meta(book_dir)
    extractions = _load_extractions(book_dir)

    lines: list[str] = []
    seen: set[str] = set()
    for ext in extractions:
        pid = ext.get("paragraph_id", "?")
        original = ext.get("original_text", "")
        for concept in ext.get("defined_concepts", []):
            key = concept.lower().strip()
            if key in seen:
                continue
            seen.add(key)
            # Find a defining sentence
            definition = ""
            for sentence in original.split(". "):
                if concept.lower() in sentence.lower():
                    definition = sentence.strip().rstrip(".")
                    break
            if not definition:
                definition = f"See paragraph {pid}"
            front = concept.replace("\t", " ").replace("\n", " ")
            back = f"{definition} [{pid}]".replace("\t", " ").replace("\n", " ")
            source = meta.get("title", folder).replace("\t", " ")
            lines.append(f"{front}\t{back}\t{source}")

    tsv_content = "\n".join(lines)
    safe_title = re.sub(r"[^\w\-]", "_", meta.get("title", folder))
    filename = f"{safe_title}_flashcards.tsv"

    from fastapi.responses import Response

    return Response(
        content=tsv_content,
        media_type="text/tab-separated-values",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Knowledge Graph analytics endpoints ──


@app.get("/api/graph/search")
async def api_graph_search(request: Request, q: str = Query(..., min_length=1)):
    """Fuzzy-search nodes by label. Returns top 15 matches."""
    user = await _try_get_user(request)
    from ppke.graph.analytics import search_nodes

    return {"results": search_nodes(_user_vault_path(user), q)}


@app.get("/api/graph/clusters")
async def api_graph_clusters(request: Request):
    """Run Louvain community detection.  Returns ``{node_id: cluster_id}``."""
    user = await _try_get_user(request)
    from ppke.graph.analytics import compute_clusters

    return compute_clusters(_user_vault_path(user))


@app.get("/api/graph/analytics")
async def api_graph_analytics(request: Request):
    """PageRank + betweenness centrality for top concepts."""
    user = await _try_get_user(request)
    from ppke.graph.analytics import compute_centrality

    return compute_centrality(_user_vault_path(user))


@app.get("/api/graph/path")
async def api_graph_path(request: Request, source: str = Query(...), target: str = Query(...)):
    """Shortest undirected path between two node IDs."""
    user = await _try_get_user(request)
    from ppke.graph.analytics import find_shortest_path

    return find_shortest_path(_user_vault_path(user), source, target)


@app.get("/api/graph/gaps")
async def api_graph_gaps(request: Request):
    """Concepts in 2+ books but with no concept-to-concept edges."""
    user = await _try_get_user(request)
    from ppke.graph.analytics import detect_gaps

    return detect_gaps(_user_vault_path(user))


@app.get("/api/graph/contradictions")
async def api_graph_contradictions(request: Request):
    """All 'contradicts' edges in the graph."""
    user = await _try_get_user(request)
    from ppke.graph.analytics import detect_contradictions

    return detect_contradictions(_user_vault_path(user))


@app.get("/api/graph/export")
async def api_graph_export(request: Request):
    """Download the knowledge graph as JSON."""
    user = await _try_get_user(request)
    vault = _user_vault_path(user)
    graph_path = vault / "knowledge_graph.json"
    if not graph_path.exists():
        raise HTTPException(404, "No knowledge graph found")
    from fastapi.responses import Response

    return Response(
        content=graph_path.read_bytes(),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="knowledge_graph.json"'},
    )


@app.get("/api/graph/obsidian-export")
async def api_graph_obsidian_export(request: Request):
    """Download an Obsidian vault ZIP with ``[[wikilinks]]`` per concept."""
    user = await _try_get_user(request)
    from ppke.graph.analytics import obsidian_vault_zip
    from fastapi.responses import Response

    data = obsidian_vault_zip(_user_vault_path(user))
    if not data:
        raise HTTPException(404, "No knowledge graph found or no concepts to export")

    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="ppke_obsidian_vault.zip"'},
    )


@app.get("/api/graph/markdown-export")
async def api_graph_markdown_export(request: Request):
    """Download interlinked Markdown concept files as ZIP."""
    user = await _try_get_user(request)
    from ppke.graph.analytics import markdown_export_zip
    from fastapi.responses import Response

    data = markdown_export_zip(_user_vault_path(user))
    if not data:
        raise HTTPException(404, "No knowledge graph found")

    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="ppke_concepts.zip"'},
    )


# ── Graph temporal view endpoints ──


@app.get("/api/graph/temporal-range")
async def api_graph_temporal_range(request: Request):
    """Return min/max year and all unique years in the knowledge graph."""
    user = await _try_get_user(request)
    from ppke.graph.analytics import get_temporal_range

    return get_temporal_range(_user_vault_path(user))


@app.get("/api/graph/temporal")
async def api_graph_temporal(
    request: Request,
    min_year: int | None = Query(None),
    max_year: int | None = Query(None),
):
    """Return graph data filtered by year range for temporal view."""
    user = await _try_get_user(request)
    from ppke.graph.analytics import filter_graph_by_year

    result = filter_graph_by_year(
        _user_vault_path(user),
        min_year=min_year,
        max_year=max_year,
    )

    # Convert to D3-friendly format
    d3_nodes = []
    for n in result.get("nodes", []):
        node_type = n.get("type", "concept")
        d3_nodes.append({
            "id": n["id"], "label": n.get("label", n["id"]),
            "type": node_type,
            "group": {"concept": 1, "book": 2, "paragraph": 3}.get(node_type, 1),
            "size": n.get("weight", 1),
            "year": n.get("year"),
        })
    d3_links = [
        {
            "source": e.get("src") or e.get("source"),
            "target": e.get("dst") or e.get("target"),
            "relation": e.get("rel") or e.get("relation", "related_to"),
            "year": e.get("year"),
        }
        for e in result.get("edges", [])
    ]
    return {"nodes": d3_nodes, "links": d3_links, "range": result.get("range", {})}


# ── PDF table detection endpoint ──


@app.post("/api/extract-tables")
async def api_extract_tables(
    request: Request,
    file: UploadFile = File(...),
):
    """Extract tables from an uploaded PDF and return them as Markdown."""
    user = await _try_get_user(request)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported for table extraction")

    import tempfile
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(content)

    try:
        from ppke.converter.table_detect import extract_tables_from_pdf, tables_to_markdown

        tables = extract_tables_from_pdf(tmp_path)
        md = tables_to_markdown(tables)
        return {
            "tables": len(tables),
            "markdown": md,
            "details": [
                {"page": t["page"] + 1, "rows": len(t["rows"]), "markdown": t["markdown"]}
                for t in tables
            ],
        }
    finally:
        tmp_path.unlink(missing_ok=True)


# ── PDF chapter detection endpoint ──


@app.post("/api/detect-chapters")
async def api_detect_chapters(
    request: Request,
    file: UploadFile = File(...),
):
    """Detect chapters from a PDF's TOC/bookmarks and return the structure."""
    user = await _try_get_user(request)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported for chapter detection")

    import tempfile
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(content)

    try:
        from ppke.converter.chapter_detect import extract_toc, split_pdf_by_toc, toc_to_markdown

        toc = extract_toc(tmp_path)
        chapters = split_pdf_by_toc(tmp_path, max_level=3, include_text=False)
        toc_md = toc_to_markdown(toc)
        return {
            "toc_entries": len(toc),
            "chapters": len(chapters),
            "toc": toc,
            "chapter_ranges": [
                {"title": c["title"], "level": c["level"],
                 "start_page": c["start_page"], "end_page": c["end_page"]}
                for c in chapters
            ],
            "toc_markdown": toc_md,
        }
    finally:
        tmp_path.unlink(missing_ok=True)


# ── Video import endpoint ──


@app.post("/api/import-video")
async def api_import_video(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    year: str = Form(""),
    domain: str = Form("philosophy"),
    generate_summary: bool = Form(False),
):
    """Import a lecture video file — extract audio, transcribe, and ingest.

    Optionally generates a structured summary of the video content.

    Returns ``{"job_id": ..., "status": "running"}``.
    """
    user = await _try_get_user(request)
    from ppke.converter.video import VIDEO_EXTENSIONS

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in VIDEO_EXTENSIONS and ext not in {".mp4", ".webm"}:
        raise HTTPException(
            400,
            f"Unsupported video format: {ext}. "
            f"Supported: {', '.join(sorted(VIDEO_EXTENSIONS | {'.mp4', '.webm'}))}"
        )

    config = _get_config()
    vault = _user_vault_path(user)
    upload_dir = vault / ".uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = re.sub(r"[^\w\.\-]", "_", file.filename)
    temp_path = upload_dir / safe_filename

    content = await file.read()
    temp_path.write_bytes(content)

    ingest_title = title.strip() or temp_path.stem.replace("_", " ").replace("-", " ").title()
    ingest_author = author.strip() or "Video Import"

    job_id = create_job(extra={"filename": safe_filename, "source_type": "video"})

    def _run_video_ingest():
        _start = time.time()
        md_path: Path | None = None
        try:
            update_job(job_id, stage="Extracting audio from video...", progress=5)

            from ppke.converter.video import convert_video

            markdown_text = convert_video(temp_path)

            update_job(job_id, stage="Transcript extracted — starting ingestion...", progress=30)

            # Optionally generate summary
            if generate_summary:
                try:
                    update_job(job_id, stage="Generating video summary...", progress=40)
                    from ppke.converter.video_summary import generate_video_summary

                    summary = generate_video_summary(
                        markdown_text, title=ingest_title,
                    )
                    if summary.get("markdown"):
                        markdown_text += "\n\n---\n\n" + summary["markdown"]
                except Exception as exc:
                    logger.warning("Video summary generation failed: %s", exc)

            safe_stem = re.sub(r"[^\w\-]", "_", ingest_title)[:60]
            md_path = upload_dir / f"{safe_stem}_{job_id}.md"
            md_path.write_text(markdown_text)

            from ppke.parser.markdown import parse_markdown_book
            from ppke.pipeline.orchestrator import ingest_book
            from ppke.progress.tracker import ProgressTracker
            from ppke.vectordb.store import VectorStore
            from ppke.graph.knowledge_graph import KnowledgeGraph

            book = parse_markdown_book(md_path, ingest_title, ingest_author, year or None)
            update_job(job_id, stage=f"Parsed: {len(book.chapters)} chapters", progress=50)

            tracker = ProgressTracker()
            vector_store = VectorStore(vault) if config.enable_vector_search else None
            knowledge_graph = KnowledgeGraph(vault) if config.enable_knowledge_graph else None
            config.vault_path = vault

            def progress_cb(stage: str, detail: str):
                update_job(job_id, stage=f"[{stage}] {detail}")

            book_dir = ingest_book(
                book, config,
                domain=domain,
                progress_callback=progress_cb,
                tracker=tracker,
                vector_store=vector_store,
                knowledge_graph=knowledge_graph,
            )

            folder_name = book_dir.name if hasattr(book_dir, "name") else str(book_dir)
            update_job(job_id, status="completed", progress=100,
                       book_folder=folder_name, stage="Video ingestion complete!")
            record_ingestion("video", "completed", time.time() - _start)

        except Exception as e:
            logger.exception("Video ingestion failed for job %s", job_id)
            update_job(job_id, status="failed", error=str(e), stage=f"Failed: {e}")
            capture_exception(e, job_id=job_id)
            record_ingestion("video", "failed", time.time() - _start)
        finally:
            temp_path.unlink(missing_ok=True)
            if md_path is not None:
                md_path.unlink(missing_ok=True)

    run_task(_run_video_ingest, job_id=job_id)

    return {"job_id": job_id, "status": "running", "source_type": "video"}


# ── Video summary endpoint ──


@app.post("/api/video-summary/{folder}")
async def api_video_summary(request: Request, folder: str):
    """Generate a structured summary from a book's transcript content."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    vault = _user_vault_path(user)
    book_dir = vault / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    # Load the book's markdown content
    md_path = book_dir / "content.md"
    if not md_path.exists():
        # Try to find any .md file
        md_files = list(book_dir.glob("*.md"))
        if md_files:
            md_path = md_files[0]
        else:
            raise HTTPException(404, "No content found for summary generation")

    transcript = md_path.read_text()
    meta = _load_book_meta(book_dir)
    title = meta.get("title", folder)

    from ppke.converter.video_summary import generate_video_summary

    summary = generate_video_summary(transcript, title=title)

    # Cache the summary
    summary_path = book_dir / "video_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    return summary


@app.get("/api/video-summary/{folder}")
async def api_get_video_summary(request: Request, folder: str):
    """Retrieve a cached video summary."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    vault = _user_vault_path(user)
    book_dir = vault / folder
    summary_path = book_dir / "video_summary.json"
    if not summary_path.exists():
        raise HTTPException(404, "No video summary found — generate one first")
    return json.loads(summary_path.read_text())


# ── Obsidian / PKM sync endpoints ──

_BLOCKED_PREFIXES = ("/etc", "/usr", "/var", "/sys", "/proc", "/dev", "/boot", "/sbin", "/bin")


def _validate_sync_path(raw: str) -> Path:
    """Resolve and validate an Obsidian vault target path.

    Rejects system-critical directories to prevent accidental or
    malicious writes outside of user-controlled locations.
    """
    resolved = Path(raw).resolve()
    resolved_str = str(resolved)
    for prefix in _BLOCKED_PREFIXES:
        if resolved_str == prefix or resolved_str.startswith(prefix + "/"):
            raise HTTPException(400, f"Sync target must not be under {prefix}")
    return resolved


@app.post("/api/sync/obsidian")
async def api_sync_obsidian(request: Request):
    """Trigger an Obsidian vault sync (two-way by default)."""
    user = await _try_get_user(request)
    vault = _user_vault_path(user)

    try:
        body = await request.json()
    except Exception:
        body = {}
    target = body.get("vault_path", "")
    direction = body.get("direction", "full")  # full | to_vault | from_vault

    if not target:
        raise HTTPException(400, "vault_path is required")

    target_path = _validate_sync_path(target)

    from ppke.export.obsidian_sync import ObsidianSyncEngine

    engine = ObsidianSyncEngine(vault, target_path)

    if direction == "to_vault":
        result = engine.sync_to_vault()
    elif direction == "from_vault":
        result = engine.sync_from_vault()
    else:
        result = engine.full_sync()

    return result


@app.get("/api/sync/obsidian/status")
async def api_sync_obsidian_status(request: Request, vault_path: str = Query(...)):
    """Get sync status for a configured Obsidian vault."""
    user = await _try_get_user(request)
    ppke_vault = _user_vault_path(user)

    target_path = _validate_sync_path(vault_path)

    from ppke.export.obsidian_sync import ObsidianSyncEngine

    engine = ObsidianSyncEngine(ppke_vault, target_path)
    return engine.get_status()


# ── Export endpoints (Phase 6) ──


@app.get("/api/export/{folder}/pdf")
async def api_export_pdf(request: Request, folder: str):
    """Export a book's analysis as a typeset PDF report."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    from ppke.export.exporters import export_pdf

    try:
        pdf_bytes = export_pdf(book_dir)
    except ImportError as e:
        raise HTTPException(500, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"PDF export failed: {e}") from e

    meta = _load_book_meta(book_dir)
    safe_title = re.sub(r"[^\w\-]", "_", meta.get("title", folder))
    # Detect if weasyprint was available (real PDF) or fallback (HTML)
    is_pdf = pdf_bytes[:5] == b"%PDF-"
    media_type = "application/pdf" if is_pdf else "text/html"
    ext = ".pdf" if is_pdf else ".html"

    from fastapi.responses import Response

    return Response(
        content=pdf_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_title}_report{ext}"'},
    )


@app.get("/api/export/{folder}/docx")
async def api_export_docx(request: Request, folder: str):
    """Export a book's analysis as a Word document."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    from ppke.export.exporters import export_docx

    try:
        docx_bytes = export_docx(book_dir)
    except ImportError as e:
        raise HTTPException(500, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"DOCX export failed: {e}") from e

    meta = _load_book_meta(book_dir)
    safe_title = re.sub(r"[^\w\-]", "_", meta.get("title", folder))

    from fastapi.responses import Response

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}_report.docx"'},
    )


@app.get("/api/export/{folder}/pptx")
async def api_export_pptx(request: Request, folder: str):
    """Export a book's key concepts as a PowerPoint slide deck."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    from ppke.export.exporters import export_pptx

    try:
        pptx_bytes = export_pptx(book_dir)
    except ImportError as e:
        raise HTTPException(500, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"PPTX export failed: {e}") from e

    meta = _load_book_meta(book_dir)
    safe_title = re.sub(r"[^\w\-]", "_", meta.get("title", folder))

    from fastapi.responses import Response

    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}_slides.pptx"'},
    )


@app.get("/api/export/{folder}/zip")
async def api_export_zip(request: Request, folder: str):
    """Download the entire notebook as a ZIP archive."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    from ppke.export.exporters import export_markdown_zip

    zip_bytes = export_markdown_zip(book_dir)

    meta = _load_book_meta(book_dir)
    safe_title = re.sub(r"[^\w\-]", "_", meta.get("title", folder))

    from fastapi.responses import Response

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}_notebook.zip"'},
    )


@app.get("/api/export/{folder}/tex")
async def api_export_latex(request: Request, folder: str):
    """Export a book's analysis as a LaTeX (.tex) document."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    from ppke.export.exporters import export_latex

    try:
        tex_bytes = export_latex(book_dir)
    except Exception as e:
        raise HTTPException(500, f"LaTeX export failed: {e}") from e

    meta = _load_book_meta(book_dir)
    safe_title = re.sub(r"[^\w\-]", "_", meta.get("title", folder))

    from fastapi.responses import Response

    return Response(
        content=tex_bytes,
        media_type="application/x-latex",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}_report.tex"'},
    )


@app.get("/api/export/{folder}/bib")
async def api_export_bibtex(request: Request, folder: str):
    """Export a book's metadata as a BibTeX (.bib) entry."""
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    from ppke.export.exporters import export_bibtex

    try:
        bib_bytes = export_bibtex(book_dir)
    except Exception as e:
        raise HTTPException(500, f"BibTeX export failed: {e}") from e

    meta = _load_book_meta(book_dir)
    safe_title = re.sub(r"[^\w\-]", "_", meta.get("title", folder))

    from fastapi.responses import Response

    return Response(
        content=bib_bytes,
        media_type="application/x-bibtex",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.bib"'},
    )


# ── Academic tools endpoints (Phase 6) ──


@app.get("/api/bibliography")
async def api_bibliography(
    request: Request,
    style: str = Query("apa"),
    books: str = Query(""),
):
    """Generate a formatted bibliography from all or selected books.

    Parameters:
    - style: ``apa``, ``mla``, or ``chicago``
    - books: comma-separated book folder names (empty = all books)
    """
    user = await _try_get_user(request)
    from ppke.export.academic import generate_bibliography

    vault = _user_vault_path(user)
    book_folders = [b.strip() for b in books.split(",") if b.strip()] or None
    content = generate_bibliography(vault, style=style, book_folders=book_folders)
    return {"style": style, "content": content}


@app.get("/api/bibliography/bib")
async def api_bibliography_bibtex(
    request: Request,
    books: str = Query(""),
):
    """Export all (or selected) books as a BibTeX bibliography file.

    Parameters:
    - books: comma-separated book folder names (empty = all books)
    """
    user = await _try_get_user(request)
    from ppke.export.academic import export_bibliography_bibtex

    vault = _user_vault_path(user)
    book_folders = [b.strip() for b in books.split(",") if b.strip()] or None
    bib_content = export_bibliography_bibtex(vault, book_folders=book_folders)

    from fastapi.responses import Response

    return Response(
        content=bib_content.encode("utf-8"),
        media_type="application/x-bibtex",
        headers={"Content-Disposition": 'attachment; filename="bibliography.bib"'},
    )


@app.get("/api/literature-review")
async def api_get_literature_review(request: Request):
    """Return cached literature review if available."""
    user = await _try_get_user(request)
    vault = _user_vault_path(user)
    path = vault / "literature_review.md"
    if not path.exists():
        return {"status": "not_generated", "content": None}
    return {"status": "ready", "content": path.read_text()}


@app.post("/api/literature-review")
async def api_generate_literature_review(
    request: Request,
    books: str = Form(""),
):
    """Generate a cross-book literature review via LLM.

    Parameters:
    - books: comma-separated book folder names (empty = all books)
    """
    user = await _try_get_user(request)
    from ppke.export.academic import generate_literature_review
    from ppke.llm.client import LLMClient

    config = _get_config()
    vault = _user_vault_path(user)
    client = LLMClient(config.llm)
    book_folders = [b.strip() for b in books.split(",") if b.strip()] or None

    try:
        content = generate_literature_review(vault, client, book_folders=book_folders)
    except Exception as e:
        raise HTTPException(500, f"Literature review generation failed: {e}") from e

    # Cache the result
    review_path = vault / "literature_review.md"
    review_path.write_text(content)

    return {"status": "ready", "content": content}


@app.get("/api/argument-map/{folder}")
async def api_argument_map(request: Request, folder: str):
    """Generate an argument map from a book's extraction data.

    Returns structured nodes + edges for interactive diagram rendering,
    plus a Markdown summary.
    """
    user = await _try_get_user(request)
    folder = _safe_folder(folder)
    book_dir = _user_vault_path(user) / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    from ppke.export.academic import generate_argument_map, argument_map_to_markdown

    arg_map = generate_argument_map(book_dir)
    markdown = argument_map_to_markdown(arg_map)

    return {
        "folder": folder,
        "nodes": arg_map["nodes"],
        "edges": arg_map["edges"],
        "stats": arg_map["stats"],
        "markdown": markdown,
    }


@app.get("/api/health")
async def api_health():
    """Health check endpoint with dependency status."""
    import os
    checks: dict[str, str] = {}

    # Database check
    try:
        conn = _get_db()
        conn.execute("SELECT 1").fetchone()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # Redis check
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        try:
            cache = get_cache()
            if hasattr(cache, "client"):
                cache.client.ping()
                checks["redis"] = "ok"
            else:
                checks["redis"] = "memory_fallback"
        except Exception as exc:
            checks["redis"] = f"error: {exc}"
    else:
        checks["redis"] = "not_configured"

    # Vector store check
    try:
        from ppke.vectordb.store import VectorStore  # pylint: disable=unused-import
        checks["vector_store"] = "available"
    except ImportError:
        checks["vector_store"] = "not_installed"

    # LLM provider check
    config = _get_config()
    checks["llm_provider"] = config.llm.provider
    checks["llm_api_key"] = "configured" if config.llm.active_api_key else "not_set"

    overall = "ok" if checks.get("database") == "ok" else "degraded"

    return {
        "status": overall,
        "version": "3.0.0",
        "checks": checks,
        "database_backend": os.environ.get("DATABASE_URL", "sqlite").split("://")[0] if "://" in os.environ.get("DATABASE_URL", "") else "sqlite",
    }


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(generate_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")


# ── Cost Dashboard (Phase 8) ──


@app.get("/cost-dashboard", response_class=HTMLResponse)
async def page_cost_dashboard(request: Request):
    """Cost dashboard page for per-book LLM token usage tracking."""
    user = await _try_get_user(request)
    return templates.TemplateResponse("cost_dashboard.html", {
        "request": request,
        "user": user,
    })


@app.get("/api/cost-dashboard")
async def api_cost_dashboard(
    request: Request,
    days: int = Query(30, ge=1, le=365),
):
    """Return cost dashboard data: per-book, per-provider, per-action, daily."""
    user = await _try_get_user(request)
    if not user:
        raise HTTPException(401, "Authentication required")

    conn = _get_db()
    summary = auth_db.get_user_usage(conn, user["id"], days=days)
    by_book = auth_db.get_cost_by_book(conn, user["id"], days=days)
    by_provider = auth_db.get_cost_by_provider(conn, user["id"], days=days)
    by_action = auth_db.get_cost_by_action(conn, user["id"], days=days)
    daily = auth_db.get_cost_daily(conn, user["id"], days=days)

    return {
        "summary": summary,
        "by_book": by_book,
        "by_provider": by_provider,
        "by_action": by_action,
        "daily": daily,
        "period_days": days,
    }


# ── Workspace & Collaboration endpoints (Phase 7) ──


@app.get("/api/workspaces")
async def api_list_workspaces(user: dict = Depends(get_current_user)):
    """List all workspaces the current user belongs to."""
    conn = _get_db()
    workspaces = auth_db.get_user_workspaces(conn, user["id"])
    return workspaces


@app.post("/api/workspaces")
async def api_create_workspace(request: Request, user: dict = Depends(get_current_user)):
    """Create a new workspace."""
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "Workspace name is required")

    slug = re.sub(r"[^a-z0-9\-]", "-", name.lower())[:40]

    conn = _get_db()
    ws = auth_db.create_workspace(conn, name, f"{slug}-{str(uuid.uuid4())[:6]}", user["id"])
    auth_db.log_activity(conn, user["id"], "created workspace", "workspace", ws["id"])
    return ws


@app.get("/api/workspaces/{ws_id}/members")
async def api_workspace_members(ws_id: str, user: dict = Depends(get_current_user)):
    """List members of a workspace."""
    conn = _get_db()
    role = auth_db.get_user_role_in_workspace(conn, ws_id, user["id"])
    if not role:
        raise HTTPException(403, "Not a member of this workspace")
    return auth_db.get_workspace_members(conn, ws_id)


@app.post("/api/workspaces/{ws_id}/invite")
async def api_invite_member(request: Request, ws_id: str, user: dict = Depends(get_current_user)):
    """Invite a user to a workspace by email.

    Works for both registered and unregistered users:
    - Registered users: added immediately as members
    - Unregistered users: a pending invite is created; auto-accepted on registration
    """
    conn = _get_db()
    role = auth_db.get_user_role_in_workspace(conn, ws_id, user["id"])
    if role not in ("admin", "editor"):
        raise HTTPException(403, "Only admins and editors can invite members")

    body = await request.json()
    email = body.get("email", "").strip().lower()
    invite_role = body.get("role", "viewer")
    if not email:
        raise HTTPException(400, "Email is required")
    if invite_role not in ("viewer", "editor", "admin"):
        raise HTTPException(400, "Invalid role — must be viewer, editor, or admin")

    try:
        invite = auth_db.create_invite(conn, ws_id, email, invite_role, user["id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    ws = auth_db.get_workspace_by_id(conn, ws_id)
    ws_name = ws["name"] if ws else "workspace"
    base_url = str(request.base_url).rstrip("/")
    invite_url = f"{base_url}/invite/{invite['token']}"

    # If the user exists, auto-accept immediately
    target_user = auth_db.get_user_by_email(conn, email)
    if target_user:
        auth_db.accept_invite(conn, invite["id"], target_user["id"])
        auth_db.log_activity(conn, user["id"], f"added {email} as {invite_role}", "workspace", ws_id)
        # Still email them so they know they were added
        try:
            from ppke.infra.email import send_invite_email
            send_invite_email(
                to_email=email,
                inviter_name=user.get("name", "A team member"),
                workspace_name=ws_name,
                role=invite_role,
                invite_url=invite_url,
            )
        except Exception:
            pass
        return {"status": "ok", "message": f"Added {email} as {invite_role}", "immediate": True}

    # Pending invite for unregistered user — send email
    auth_db.log_activity(conn, user["id"], f"invited {email} as {invite_role} (pending)", "workspace", ws_id)
    email_sent = False
    try:
        from ppke.infra.email import send_invite_email
        email_sent = send_invite_email(
            to_email=email,
            inviter_name=user.get("name", "A team member"),
            workspace_name=ws_name,
            role=invite_role,
            invite_url=invite_url,
        )
    except Exception:
        pass

    if email_sent:
        msg = f"Invitation emailed to {email}. They'll be added as {invite_role} when they accept."
    else:
        msg = f"Invite created for {email} — share the link below (email delivery not configured)."

    return {
        "status": "ok",
        "message": msg,
        "email_sent": email_sent,
        "immediate": False,
        "invite_id": invite["id"],
        "invite_url": f"/invite/{invite['token']}",
    }


@app.get("/api/workspaces/{ws_id}/invites")
async def api_workspace_invites(ws_id: str, user: dict = Depends(get_current_user)):
    """List pending invites for a workspace."""
    conn = _get_db()
    role = auth_db.get_user_role_in_workspace(conn, ws_id, user["id"])
    if not role:
        raise HTTPException(403, "Not a member of this workspace")
    return auth_db.get_workspace_invites(conn, ws_id)


@app.delete("/api/workspaces/{ws_id}/invites/{invite_id}")
async def api_revoke_invite(ws_id: str, invite_id: str, user: dict = Depends(get_current_user)):
    """Revoke a pending invite (admin/editor only)."""
    conn = _get_db()
    role = auth_db.get_user_role_in_workspace(conn, ws_id, user["id"])
    if role not in ("admin", "editor"):
        raise HTTPException(403, "Only admins and editors can revoke invites")
    if not auth_db.revoke_invite(conn, invite_id):
        raise HTTPException(404, "Invite not found or already accepted")
    return {"status": "ok"}


@app.get("/api/auth/invites")
async def api_my_invites(user: dict = Depends(get_current_user)):
    """List pending invites for the current user."""
    conn = _get_db()
    return auth_db.get_invites_for_email(conn, user["email"])


@app.post("/api/auth/invites/{invite_id}/accept")
async def api_accept_invite(invite_id: str, user: dict = Depends(get_current_user)):
    """Accept a pending workspace invite."""
    conn = _get_db()
    result = auth_db.accept_invite(conn, invite_id, user["id"])
    if not result:
        raise HTTPException(404, "Invite not found, expired, or already handled")
    auth_db.log_activity(conn, user["id"], "accepted workspace invite", "workspace", result["workspace_id"])
    return {"status": "ok", "workspace_id": result["workspace_id"]}


@app.post("/api/auth/invites/{invite_id}/decline")
async def api_decline_invite(invite_id: str, user: dict = Depends(get_current_user)):
    """Decline a pending workspace invite."""
    conn = _get_db()
    if not auth_db.decline_invite(conn, invite_id):
        raise HTTPException(404, "Invite not found or already handled")
    return {"status": "ok"}


@app.get("/invite/{token}", response_class=HTMLResponse)
async def invite_landing(token: str, request: Request):
    """Landing page for invite links — prompts login/register then auto-accepts."""
    conn = _get_db()
    row = conn.execute(
        "SELECT wi.*, w.name as workspace_name, u.name as invited_by_name "
        "FROM workspace_invites wi "
        "JOIN workspaces w ON wi.workspace_id = w.id "
        "JOIN users u ON wi.invited_by = u.id "
        "WHERE wi.token = ?",
        (token,),
    ).fetchone()
    invite = auth_db._row_to_dict(row)
    if not invite or invite["status"] != "pending":
        return HTMLResponse(
            "<html><body style='font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;background:#1a1a2e;color:#e0e0e0'>"
            "<div style='text-align:center'><h2>Invite not found or expired</h2>"
            "<a href='/login' style='color:#4ecca3'>Go to Login</a></div></body></html>"
        )

    # If user is logged in, accept immediately
    user = await _try_get_user(request)
    if user:
        result = auth_db.accept_invite_by_token(conn, token, user["id"])
        if result:
            return RedirectResponse(f"/workspaces", status_code=303)

    # Not logged in — show invite info and link to register/login
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><title>Workspace Invite — PPKE</title>
<style>
body {{ font-family: system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0;
       display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
.card {{ background: #16213e; padding: 2.5rem; border-radius: 16px; text-align: center; max-width: 440px; width: 90%; }}
h2 {{ color: #4ecca3; margin-bottom: 0.5rem; }}
.ws-name {{ font-size: 1.3em; color: #fff; font-weight: 700; margin: 0.5rem 0; }}
.role {{ display: inline-block; background: #0f3460; color: #4ecca3; padding: 4px 12px; border-radius: 20px;
         font-size: 0.85em; font-weight: 600; margin: 0.5rem 0; }}
.invited-by {{ color: #888; font-size: 0.9em; margin-bottom: 1.5rem; }}
.btns {{ display: flex; gap: 12px; justify-content: center; margin-top: 1.5rem; }}
.btn {{ padding: 10px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 0.95em; }}
.btn-primary {{ background: #4ecca3; color: #1a1a2e; }}
.btn-secondary {{ background: #0f3460; color: #e0e0e0; }}
</style></head>
<body><div class="card">
  <h2>You're invited!</h2>
  <div class="ws-name">{invite['workspace_name']}</div>
  <div class="role">{invite['role']}</div>
  <div class="invited-by">Invited by {invite['invited_by_name']}</div>
  <p>Sign in or create an account to join this workspace.</p>
  <div class="btns">
    <a href="/login?next=/invite/{token}" class="btn btn-primary">Sign In</a>
    <a href="/register?next=/invite/{token}" class="btn btn-secondary">Create Account</a>
  </div>
</div></body></html>""")


@app.post("/api/workspaces/{ws_id}/members/{member_id}/role")
async def api_update_member_role(
    request: Request, ws_id: str, member_id: str, user: dict = Depends(get_current_user)
):
    """Update a member's role in a workspace (admin only)."""
    conn = _get_db()
    role = auth_db.get_user_role_in_workspace(conn, ws_id, user["id"])
    if role != "admin":
        raise HTTPException(403, "Only admins can change roles")

    body = await request.json()
    new_role = body.get("role", "viewer")
    auth_db.update_member_role(conn, ws_id, member_id, new_role)
    return {"status": "ok"}


@app.delete("/api/workspaces/{ws_id}/members/{member_id}")
async def api_remove_member(ws_id: str, member_id: str, user: dict = Depends(get_current_user)):
    """Remove a member from a workspace (admin only)."""
    conn = _get_db()
    role = auth_db.get_user_role_in_workspace(conn, ws_id, user["id"])
    if role != "admin":
        raise HTTPException(403, "Only admins can remove members")
    if member_id == user["id"]:
        raise HTTPException(400, "Cannot remove yourself — transfer ownership first")
    auth_db.remove_workspace_member(conn, ws_id, member_id)
    return {"status": "ok"}


# ── Shared Books ──


@app.post("/api/workspaces/{ws_id}/share")
async def api_share_book(request: Request, ws_id: str, user: dict = Depends(get_current_user)):
    """Share a book with a workspace."""
    conn = _get_db()
    role = auth_db.get_user_role_in_workspace(conn, ws_id, user["id"])
    if not role or role == "viewer":
        raise HTTPException(403, "Viewers cannot share books")

    body = await request.json()
    book_folder = body.get("book_folder", "").strip()
    permissions = body.get("permissions", "view")

    if not book_folder:
        raise HTTPException(400, "book_folder is required")

    share = auth_db.share_book(conn, ws_id, book_folder, user["id"], permissions)
    auth_db.log_activity(conn, user["id"], f"shared book {book_folder}", "book", book_folder, workspace_id=ws_id)
    return share


@app.get("/api/workspaces/{ws_id}/shared-books")
async def api_shared_books(ws_id: str, user: dict = Depends(get_current_user)):
    """List books shared in a workspace."""
    conn = _get_db()
    role = auth_db.get_user_role_in_workspace(conn, ws_id, user["id"])
    if not role:
        raise HTTPException(403, "Not a member of this workspace")
    return auth_db.get_shared_books(conn, ws_id)


# ── Annotations ──


@app.post("/api/annotations")
async def api_create_annotation(request: Request, user: dict = Depends(get_current_user)):
    """Create a personal annotation on a paragraph."""
    body = await request.json()
    book_folder = body.get("book_folder", "").strip()
    paragraph_id = body.get("paragraph_id", "").strip()
    content = body.get("content", "").strip()
    annotation_type = body.get("type", "note")

    if not book_folder or not content:
        raise HTTPException(400, "book_folder and content are required")

    conn = _get_db()
    ann = auth_db.create_annotation(
        conn, user["id"], book_folder, paragraph_id, content, annotation_type
    )
    auth_db.log_activity(conn, user["id"], "added annotation", "book", book_folder)
    return ann


@app.get("/api/annotations/{folder}")
async def api_get_annotations(folder: str, user: dict = Depends(get_current_user)):
    """Get all annotations for a book (user's own)."""
    folder = _safe_folder(folder)
    conn = _get_db()
    return auth_db.get_annotations(conn, folder, user_id=user["id"])


@app.delete("/api/annotations/{ann_id}")
async def api_delete_annotation(ann_id: str, user: dict = Depends(get_current_user)):
    """Delete one of the user's annotations."""
    conn = _get_db()
    deleted = auth_db.delete_annotation(conn, ann_id, user["id"])
    if not deleted:
        raise HTTPException(404, "Annotation not found or not yours")
    return {"status": "deleted"}


# ── Activity Feed ──


@app.get("/api/activity")
async def api_activity_feed(
    workspace_id: str = Query(""),
    user: dict = Depends(get_current_user),
):
    """Recent activity across user's scope."""
    conn = _get_db()
    if workspace_id:
        role = auth_db.get_user_role_in_workspace(conn, workspace_id, user["id"])
        if not role:
            raise HTTPException(403, "Not a member of this workspace")
        return auth_db.get_activity_feed(conn, workspace_id=workspace_id, limit=50)
    return auth_db.get_activity_feed(conn, user_id=user["id"], limit=50)


# ── API Key Management ──


@app.post("/api/keys")
async def api_store_key(request: Request, user: dict = Depends(get_current_user)):
    """Store a per-user LLM API key."""
    body = await request.json()
    provider = body.get("provider", "").strip()
    api_key = body.get("api_key", "").strip()
    label = body.get("label", "")

    if not provider or not api_key:
        raise HTTPException(400, "provider and api_key are required")
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"Unsupported provider: {provider}")

    conn = _get_db()
    # Simple obfuscation — in production use encryption (Fernet, etc.)
    import base64
    encoded = base64.b64encode(api_key.encode()).decode()
    result = auth_db.store_api_key(conn, user["id"], provider, encoded, label)
    auth_db.log_activity(conn, user["id"], f"added API key for {provider}", "api_key", result["id"])
    return result


@app.get("/api/keys")
async def api_list_keys(user: dict = Depends(get_current_user)):
    """List user's API keys (without the key values)."""
    conn = _get_db()
    return auth_db.get_user_api_keys(conn, user["id"])


@app.delete("/api/keys/{key_id}")
async def api_delete_key(key_id: str, user: dict = Depends(get_current_user)):
    """Delete a stored API key."""
    conn = _get_db()
    deleted = auth_db.delete_api_key(conn, key_id, user["id"])
    if not deleted:
        raise HTTPException(404, "API key not found")
    return {"status": "deleted"}


# ── Usage Tracking ──


@app.get("/api/usage")
async def api_get_usage(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    """Get the current user's LLM usage summary."""
    conn = _get_db()
    return auth_db.get_user_usage(conn, user["id"], days=days)


# ── Plugin Marketplace ──


@app.get("/marketplace", response_class=HTMLResponse)
async def marketplace_page(request: Request):
    """Render the plugin marketplace UI."""
    user = await _try_get_user(request)
    from ppke.templates.marketplace import list_marketplace_plugins

    result = list_marketplace_plugins()
    return templates.TemplateResponse("marketplace.html", {
        "request": request,
        "user": user,
        "plugins": result["plugins"],
        "categories": result["categories"],
        "total": result["total"],
    })


@app.get("/api/marketplace/plugins")
async def api_marketplace_list(
    category: str | None = Query(None),
    search: str | None = Query(None, alias="q"),
    sort_by: str = Query("downloads"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List and search marketplace plugins."""
    from ppke.templates.marketplace import list_marketplace_plugins

    return list_marketplace_plugins(
        category=category,
        search=search,
        sort_by=sort_by,
        page=page,
        per_page=per_page,
    )


@app.get("/api/marketplace/plugins/{name}")
async def api_marketplace_detail(name: str):
    """Get details for a single marketplace plugin."""
    from ppke.templates.marketplace import get_marketplace_plugin

    plugin = get_marketplace_plugin(name)
    if plugin is None:
        raise HTTPException(404, f"Plugin '{name}' not found")
    return plugin


@app.post("/api/marketplace/plugins/{name}/rate")
async def api_marketplace_rate(
    name: str,
    request: Request,
):
    """Rate a marketplace plugin (1-5 stars)."""
    body = await request.json()
    rating = body.get("rating")
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        raise HTTPException(422, "rating must be an integer between 1 and 5")

    from ppke.templates.marketplace import rate_plugin

    result = rate_plugin(name, rating)
    if result is None:
        raise HTTPException(404, f"Plugin '{name}' not found")
    return result


@app.post("/api/marketplace/plugins/{name}/install")
async def api_marketplace_install(name: str):
    """Install a plugin from the marketplace (official plugins are bundled)."""
    from ppke.templates.marketplace import get_marketplace_plugin, increment_downloads

    plugin = get_marketplace_plugin(name)
    if plugin is None:
        raise HTTPException(404, f"Plugin '{name}' not found")

    # Official plugins are already bundled; just bump the counter
    if plugin.get("tier") == "official":
        increment_downloads(name)
        return {"status": "already_installed", "plugin": name, "message": "Official plugin is bundled with PPKE"}

    # Community plugins with a GitHub source can be installed
    source = plugin.get("source", "")
    if source.startswith("github:"):
        from ppke.templates.installer import install_from_github, TemplateInstallError

        github_url = source.replace("github:", "")
        try:
            install_from_github(github_url, force=True)
            increment_downloads(name)
            return {"status": "installed", "plugin": name}
        except TemplateInstallError as exc:
            raise HTTPException(400, str(exc)) from exc

    increment_downloads(name)
    return {"status": "registered", "plugin": name, "message": "Plugin registered locally"}


@app.post("/api/marketplace/submit")
async def api_marketplace_submit(request: Request):
    """Submit a new plugin to the marketplace."""
    body = await request.json()

    required = ["name", "version", "author", "description"]
    for field in required:
        if not body.get(field):
            raise HTTPException(422, f"Missing required field: {field}")

    import re
    if not re.fullmatch(r'[a-z_]+', body["name"]):
        raise HTTPException(422, "Plugin name must be lowercase letters and underscores only")
    if not re.fullmatch(r'\d+\.\d+\.\d+', body["version"]):
        raise HTTPException(422, "Version must be semantic (e.g. 1.0.0)")

    from ppke.templates.marketplace import submit_plugin

    raw_tags = body.get("tags", [])
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = raw_tags

    try:
        plugin = submit_plugin(
            name=body["name"],
            version=body["version"],
            author=body["author"],
            description=body["description"],
            category=body.get("category", "other"),
            tags=tags,
            source_url=body.get("source_url"),
        )
        return plugin
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
