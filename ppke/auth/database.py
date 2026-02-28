"""SQLite database layer for users, workspaces, and collaboration.

Uses stdlib sqlite3 — no ORM dependency. Tables are created on first
connection if they don't exist (auto-migrate).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path.home() / ".ppke" / "ppke.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db(path: Path | None = None) -> sqlite3.Connection:
    """Open (or create) the PPKE database and ensure all tables exist."""
    path = path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id          TEXT PRIMARY KEY,
        email       TEXT UNIQUE NOT NULL,
        name        TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL DEFAULT '',
        oauth_provider TEXT DEFAULT NULL,
        oauth_id    TEXT DEFAULT NULL,
        role        TEXT NOT NULL DEFAULT 'user',
        is_active   INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS workspaces (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        slug        TEXT UNIQUE NOT NULL,
        owner_id    TEXT NOT NULL REFERENCES users(id),
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS workspace_members (
        id          TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role        TEXT NOT NULL DEFAULT 'viewer',
        invited_by  TEXT REFERENCES users(id),
        created_at  TEXT NOT NULL,
        UNIQUE(workspace_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS shared_books (
        id          TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        book_folder TEXT NOT NULL,
        shared_by   TEXT NOT NULL REFERENCES users(id),
        permissions TEXT NOT NULL DEFAULT 'view',
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS annotations (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
        book_folder TEXT NOT NULL,
        paragraph_id TEXT NOT NULL DEFAULT '',
        content     TEXT NOT NULL,
        annotation_type TEXT NOT NULL DEFAULT 'note',
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS activity_log (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        workspace_id TEXT REFERENCES workspaces(id),
        action      TEXT NOT NULL,
        target_type TEXT NOT NULL DEFAULT '',
        target_id   TEXT NOT NULL DEFAULT '',
        details     TEXT DEFAULT NULL,
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS api_keys (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        provider    TEXT NOT NULL,
        encrypted_key TEXT NOT NULL,
        label       TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS usage_records (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        workspace_id TEXT REFERENCES workspaces(id),
        action      TEXT NOT NULL,
        tokens_used INTEGER NOT NULL DEFAULT 0,
        cost_usd    REAL NOT NULL DEFAULT 0.0,
        provider    TEXT NOT NULL DEFAULT '',
        model       TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_wm_workspace ON workspace_members(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_wm_user ON workspace_members(user_id);
    CREATE INDEX IF NOT EXISTS idx_annotations_book ON annotations(book_folder);
    CREATE INDEX IF NOT EXISTS idx_annotations_user ON annotations(user_id);
    CREATE INDEX IF NOT EXISTS idx_activity_workspace ON activity_log(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id);
    CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_records(user_id);
    CREATE INDEX IF NOT EXISTS idx_shared_books_ws ON shared_books(workspace_id);
    """)
    conn.commit()


# ── User CRUD ──


def create_user(
    conn: sqlite3.Connection,
    email: str,
    name: str,
    password_hash: str,
    role: str = "user",
    oauth_provider: str | None = None,
    oauth_id: str | None = None,
) -> dict[str, Any]:
    now = _utcnow()
    user_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, oauth_provider, oauth_id, role, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, email.lower().strip(), name, password_hash, oauth_provider, oauth_id, role, now, now),
    )
    conn.commit()

    # Auto-create personal workspace
    ws = create_workspace(conn, f"{name}'s Workspace", f"personal-{user_id[:8]}", user_id)

    return {"id": user_id, "email": email.lower().strip(), "name": name, "role": role,
            "workspace_id": ws["id"], "created_at": now}


def get_user_by_email(conn: sqlite3.Connection, email: str) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (email.lower().strip(),)).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn: sqlite3.Connection, user_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_oauth(conn: sqlite3.Connection, provider: str, oauth_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM users WHERE oauth_provider = ? AND oauth_id = ? AND is_active = 1",
        (provider, oauth_id),
    ).fetchone()
    return dict(row) if row else None


# ── Workspace CRUD ──


def create_workspace(conn: sqlite3.Connection, name: str, slug: str, owner_id: str) -> dict:
    now = _utcnow()
    ws_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO workspaces (id, name, slug, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (ws_id, name, slug, owner_id, now, now),
    )
    # Owner is automatically an admin member
    conn.execute(
        "INSERT INTO workspace_members (id, workspace_id, user_id, role, created_at) VALUES (?, ?, ?, 'admin', ?)",
        (str(uuid.uuid4()), ws_id, owner_id, now),
    )
    conn.commit()
    return {"id": ws_id, "name": name, "slug": slug, "owner_id": owner_id}


def get_user_workspaces(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT w.*, wm.role as member_role FROM workspaces w "
        "JOIN workspace_members wm ON w.id = wm.workspace_id "
        "WHERE wm.user_id = ? ORDER BY w.created_at",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_workspace_by_id(conn: sqlite3.Connection, ws_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    return dict(row) if row else None


def get_workspace_members(conn: sqlite3.Connection, ws_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT wm.*, u.email, u.name FROM workspace_members wm "
        "JOIN users u ON wm.user_id = u.id WHERE wm.workspace_id = ?",
        (ws_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_workspace_member(
    conn: sqlite3.Connection, ws_id: str, user_id: str, role: str = "viewer", invited_by: str | None = None
) -> dict:
    now = _utcnow()
    mem_id = str(uuid.uuid4())
    conn.execute(
        "INSERT OR IGNORE INTO workspace_members (id, workspace_id, user_id, role, invited_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (mem_id, ws_id, user_id, role, invited_by, now),
    )
    conn.commit()
    return {"id": mem_id, "workspace_id": ws_id, "user_id": user_id, "role": role}


def update_member_role(conn: sqlite3.Connection, ws_id: str, user_id: str, new_role: str) -> bool:
    cur = conn.execute(
        "UPDATE workspace_members SET role = ? WHERE workspace_id = ? AND user_id = ?",
        (new_role, ws_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def remove_workspace_member(conn: sqlite3.Connection, ws_id: str, user_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
        (ws_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def get_user_role_in_workspace(conn: sqlite3.Connection, ws_id: str, user_id: str) -> str | None:
    row = conn.execute(
        "SELECT role FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
        (ws_id, user_id),
    ).fetchone()
    return row["role"] if row else None


# ── Shared Books ──


def share_book(conn: sqlite3.Connection, ws_id: str, book_folder: str, shared_by: str, permissions: str = "view") -> dict:
    now = _utcnow()
    share_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO shared_books (id, workspace_id, book_folder, shared_by, permissions, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (share_id, ws_id, book_folder, shared_by, permissions, now),
    )
    conn.commit()
    return {"id": share_id, "workspace_id": ws_id, "book_folder": book_folder}


def get_shared_books(conn: sqlite3.Connection, ws_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT sb.*, u.name as shared_by_name FROM shared_books sb "
        "JOIN users u ON sb.shared_by = u.id WHERE sb.workspace_id = ?",
        (ws_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Annotations ──


def create_annotation(
    conn: sqlite3.Connection,
    user_id: str,
    book_folder: str,
    paragraph_id: str,
    content: str,
    annotation_type: str = "note",
    workspace_id: str | None = None,
) -> dict:
    now = _utcnow()
    ann_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO annotations (id, user_id, workspace_id, book_folder, paragraph_id, content, annotation_type, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ann_id, user_id, workspace_id, book_folder, paragraph_id, content, annotation_type, now, now),
    )
    conn.commit()
    return {"id": ann_id, "user_id": user_id, "book_folder": book_folder, "paragraph_id": paragraph_id,
            "content": content, "type": annotation_type, "created_at": now}


def get_annotations(conn: sqlite3.Connection, book_folder: str, user_id: str | None = None, workspace_id: str | None = None) -> list[dict]:
    query = "SELECT a.*, u.name as user_name FROM annotations a JOIN users u ON a.user_id = u.id WHERE a.book_folder = ?"
    params: list[Any] = [book_folder]
    if user_id:
        query += " AND a.user_id = ?"
        params.append(user_id)
    if workspace_id:
        query += " AND a.workspace_id = ?"
        params.append(workspace_id)
    query += " ORDER BY a.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def delete_annotation(conn: sqlite3.Connection, ann_id: str, user_id: str) -> bool:
    cur = conn.execute("DELETE FROM annotations WHERE id = ? AND user_id = ?", (ann_id, user_id))
    conn.commit()
    return cur.rowcount > 0


# ── Activity Log ──


def log_activity(
    conn: sqlite3.Connection,
    user_id: str,
    action: str,
    target_type: str = "",
    target_id: str = "",
    details: str | None = None,
    workspace_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO activity_log (id, user_id, workspace_id, action, target_type, target_id, details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, workspace_id, action, target_type, target_id, details, _utcnow()),
    )
    conn.commit()


def get_activity_feed(conn: sqlite3.Connection, workspace_id: str | None = None, user_id: str | None = None, limit: int = 50) -> list[dict]:
    query = "SELECT al.*, u.name as user_name FROM activity_log al JOIN users u ON al.user_id = u.id WHERE 1=1"
    params: list[Any] = []
    if workspace_id:
        query += " AND al.workspace_id = ?"
        params.append(workspace_id)
    if user_id:
        query += " AND al.user_id = ?"
        params.append(user_id)
    query += " ORDER BY al.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# ── API Keys ──


def store_api_key(conn: sqlite3.Connection, user_id: str, provider: str, encrypted_key: str, label: str = "") -> dict:
    key_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO api_keys (id, user_id, provider, encrypted_key, label, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (key_id, user_id, provider, encrypted_key, label, _utcnow()),
    )
    conn.commit()
    return {"id": key_id, "provider": provider, "label": label}


def get_user_api_keys(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, provider, label, created_at FROM api_keys WHERE user_id = ?", (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_api_key(conn: sqlite3.Connection, user_id: str, provider: str) -> str | None:
    row = conn.execute(
        "SELECT encrypted_key FROM api_keys WHERE user_id = ? AND provider = ? ORDER BY created_at DESC LIMIT 1",
        (user_id, provider),
    ).fetchone()
    return row["encrypted_key"] if row else None


def delete_api_key(conn: sqlite3.Connection, key_id: str, user_id: str) -> bool:
    cur = conn.execute("DELETE FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user_id))
    conn.commit()
    return cur.rowcount > 0


# ── Usage Records ──


def record_usage(
    conn: sqlite3.Connection,
    user_id: str,
    action: str,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
    provider: str = "",
    model: str = "",
    workspace_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO usage_records (id, user_id, workspace_id, action, tokens_used, cost_usd, provider, model, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, workspace_id, action, tokens_used, cost_usd, provider, model, _utcnow()),
    )
    conn.commit()


def get_user_usage(conn: sqlite3.Connection, user_id: str, days: int = 30) -> dict:
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(tokens_used), 0) as total_tokens, COALESCE(SUM(cost_usd), 0.0) as total_cost, "
        "COUNT(*) as total_requests FROM usage_records WHERE user_id = ? AND created_at >= ?",
        (user_id, cutoff),
    ).fetchone()
    return dict(row) if row else {"total_tokens": 0, "total_cost": 0.0, "total_requests": 0}
