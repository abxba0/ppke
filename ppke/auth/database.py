"""Database layer for users, workspaces, and collaboration.

Supports SQLite (default, single-user) and PostgreSQL (multi-user).
Auto-detects backend from DATABASE_URL environment variable.
Tables are created on first connection if they don't exist (auto-migrate).

Environment variables:
    DATABASE_URL — PostgreSQL URL (e.g. postgresql://user:pass@host:5432/ppke)
                   If unset, falls back to SQLite at ~/.ppke/ppke.db
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".ppke" / "ppke.db"

# ── Database backend detection ──

_pg_pool: Any = None
_db_backend: str | None = None


def _detect_backend() -> str:
    """Detect whether to use PostgreSQL or SQLite."""
    global _db_backend
    if _db_backend is not None:
        return _db_backend
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith(("postgresql://", "postgres://")):
        _db_backend = "postgresql"
    else:
        _db_backend = "sqlite"
    return _db_backend


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Connection wrapper for unified API ──


class DBConnection:
    """Unified database connection wrapper for SQLite and PostgreSQL.

    Provides a consistent interface so all CRUD functions work unchanged
    regardless of the underlying database engine.
    """

    def __init__(self, conn: Any, backend: str):
        self._conn = conn
        self.backend = backend
        self._cursor: Any = None

    def execute(self, sql: str, params: tuple | list = ()) -> Any:
        """Execute a query, transparently converting ? to %s for PostgreSQL."""
        if self.backend == "postgresql":
            sql = sql.replace("?", "%s")
            # PostgreSQL doesn't support INSERT OR IGNORE — use ON CONFLICT DO NOTHING
            sql = sql.replace("INSERT OR IGNORE", "INSERT")
            if "INSERT" in sql and "ON CONFLICT" not in sql and "DO NOTHING" not in sql:
                # For workspace_members UNIQUE constraint
                pass
            cursor = self._conn.cursor()
            try:
                cursor.execute(sql, tuple(params))
            except Exception as exc:
                # Handle unique constraint violations gracefully
                err_str = str(exc).lower()
                if "duplicate key" in err_str or "unique constraint" in err_str:
                    self._conn.rollback()
                    # Return a cursor-like object with rowcount=0
                    return _EmptyResult()
                raise
            return cursor
        else:
            return self._conn.execute(sql, params)

    def executescript(self, sql: str) -> None:
        """Execute multiple statements (for table creation)."""
        if self.backend == "postgresql":
            cursor = self._conn.cursor()
            cursor.execute(sql)
            self._conn.commit()
        else:
            self._conn.executescript(sql)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    @property
    def row_factory(self):
        if self.backend == "sqlite":
            return self._conn.row_factory
        return None

    @row_factory.setter
    def row_factory(self, value: Any):
        if self.backend == "sqlite":
            self._conn.row_factory = value


class _EmptyResult:
    """Dummy cursor result for ignored duplicate inserts."""
    rowcount = 0

    def fetchone(self):
        return None

    def fetchall(self):
        return []


# ── PostgreSQL support ──


def _get_pg_connection() -> DBConnection:
    """Create a PostgreSQL connection using psycopg2."""
    global _pg_pool
    db_url = os.environ.get("DATABASE_URL", "")

    if _pg_pool is None:
        try:
            import psycopg2
            import psycopg2.extras
            import psycopg2.pool

            _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=db_url,
            )
            logger.info("PostgreSQL connection pool created")
        except Exception as exc:
            logger.error("PostgreSQL connection failed: %s", exc)
            raise

    raw_conn = _pg_pool.getconn()

    # Use RealDictCursor for dict-like row access
    import psycopg2.extras
    raw_conn.cursor_factory = psycopg2.extras.RealDictCursor
    raw_conn.autocommit = False

    return DBConnection(raw_conn, "postgresql")


def _return_pg_connection(wrapper: DBConnection) -> None:
    """Return a PostgreSQL connection to the pool."""
    global _pg_pool
    if _pg_pool and wrapper.backend == "postgresql":
        try:
            _pg_pool.putconn(wrapper._conn)
        except Exception:
            pass


# ── Table creation ──


_SQLITE_SCHEMA = """
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
        book_folder TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS workspace_invites (
        id          TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        email       TEXT NOT NULL,
        role        TEXT NOT NULL DEFAULT 'viewer',
        invited_by  TEXT NOT NULL REFERENCES users(id),
        status      TEXT NOT NULL DEFAULT 'pending',
        token       TEXT UNIQUE NOT NULL,
        created_at  TEXT NOT NULL,
        expires_at  TEXT NOT NULL,
        accepted_at TEXT DEFAULT NULL,
        UNIQUE(workspace_id, email)
    );

    CREATE INDEX IF NOT EXISTS idx_wm_workspace ON workspace_members(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_wm_user ON workspace_members(user_id);
    CREATE INDEX IF NOT EXISTS idx_annotations_book ON annotations(book_folder);
    CREATE INDEX IF NOT EXISTS idx_annotations_user ON annotations(user_id);
    CREATE INDEX IF NOT EXISTS idx_activity_workspace ON activity_log(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id);
    CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_records(user_id);
    CREATE INDEX IF NOT EXISTS idx_usage_book ON usage_records(book_folder);
    CREATE INDEX IF NOT EXISTS idx_shared_books_ws ON shared_books(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_invites_email ON workspace_invites(email);
    CREATE INDEX IF NOT EXISTS idx_invites_token ON workspace_invites(token);
    CREATE INDEX IF NOT EXISTS idx_invites_ws ON workspace_invites(workspace_id);
"""

_PG_SCHEMA = """
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
        book_folder TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS workspace_invites (
        id          TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        email       TEXT NOT NULL,
        role        TEXT NOT NULL DEFAULT 'viewer',
        invited_by  TEXT NOT NULL REFERENCES users(id),
        status      TEXT NOT NULL DEFAULT 'pending',
        token       TEXT UNIQUE NOT NULL,
        created_at  TEXT NOT NULL,
        expires_at  TEXT NOT NULL,
        accepted_at TEXT DEFAULT NULL,
        UNIQUE(workspace_id, email)
    );

    CREATE INDEX IF NOT EXISTS idx_wm_workspace ON workspace_members(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_wm_user ON workspace_members(user_id);
    CREATE INDEX IF NOT EXISTS idx_annotations_book ON annotations(book_folder);
    CREATE INDEX IF NOT EXISTS idx_annotations_user ON annotations(user_id);
    CREATE INDEX IF NOT EXISTS idx_activity_workspace ON activity_log(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id);
    CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_records(user_id);
    CREATE INDEX IF NOT EXISTS idx_usage_book ON usage_records(book_folder);
    CREATE INDEX IF NOT EXISTS idx_shared_books_ws ON shared_books(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_invites_email ON workspace_invites(email);
    CREATE INDEX IF NOT EXISTS idx_invites_token ON workspace_invites(token);
    CREATE INDEX IF NOT EXISTS idx_invites_ws ON workspace_invites(workspace_id);
"""


def _create_tables(conn: DBConnection) -> None:
    if conn.backend == "postgresql":
        conn.executescript(_PG_SCHEMA)
    else:
        conn.executescript(_SQLITE_SCHEMA)
    conn.commit()


# ── Public connection factory ──


def get_db(path: Path | None = None) -> DBConnection:
    """Open (or create) the PPKE database and ensure all tables exist.

    Uses PostgreSQL when DATABASE_URL is set, otherwise SQLite.
    """
    backend = _detect_backend()

    if backend == "postgresql":
        conn = _get_pg_connection()
        _create_tables(conn)
        return conn

    # SQLite path
    path = path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(path), check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA foreign_keys=ON")
    conn = DBConnection(raw, "sqlite")
    _create_tables(conn)
    return conn


def get_db_backend() -> str:
    """Return 'postgresql' or 'sqlite'."""
    return _detect_backend()


# ── User CRUD ──


def _row_to_dict(row: Any) -> dict | None:
    """Convert a database row to a dict regardless of backend."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def _rows_to_dicts(rows: Any) -> list[dict]:
    """Convert a list of rows to dicts."""
    return [_row_to_dict(r) for r in rows]


def create_user(
    conn: Any,
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


def get_user_by_email(conn: Any, email: str) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (email.lower().strip(),)).fetchone()
    return _row_to_dict(row)


def get_user_by_id(conn: Any, user_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)).fetchone()
    return _row_to_dict(row)


def get_user_by_oauth(conn: Any, provider: str, oauth_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM users WHERE oauth_provider = ? AND oauth_id = ? AND is_active = 1",
        (provider, oauth_id),
    ).fetchone()
    return _row_to_dict(row)


# ── Workspace CRUD ──


def create_workspace(conn: Any, name: str, slug: str, owner_id: str) -> dict:
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


def get_user_workspaces(conn: Any, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT w.*, wm.role as member_role FROM workspaces w "
        "JOIN workspace_members wm ON w.id = wm.workspace_id "
        "WHERE wm.user_id = ? ORDER BY w.created_at",
        (user_id,),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_workspace_by_id(conn: Any, ws_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    return _row_to_dict(row)


def get_workspace_members(conn: Any, ws_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT wm.*, u.email, u.name FROM workspace_members wm "
        "JOIN users u ON wm.user_id = u.id WHERE wm.workspace_id = ?",
        (ws_id,),
    ).fetchall()
    return _rows_to_dicts(rows)


def add_workspace_member(
    conn: Any, ws_id: str, user_id: str, role: str = "viewer", invited_by: str | None = None
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


def update_member_role(conn: Any, ws_id: str, user_id: str, new_role: str) -> bool:
    cur = conn.execute(
        "UPDATE workspace_members SET role = ? WHERE workspace_id = ? AND user_id = ?",
        (new_role, ws_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def remove_workspace_member(conn: Any, ws_id: str, user_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
        (ws_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def get_user_role_in_workspace(conn: Any, ws_id: str, user_id: str) -> str | None:
    row = conn.execute(
        "SELECT role FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
        (ws_id, user_id),
    ).fetchone()
    if row is None:
        return None
    r = _row_to_dict(row)
    return r["role"] if r else None


# ── Shared Books ──


def share_book(conn: Any, ws_id: str, book_folder: str, shared_by: str, permissions: str = "view") -> dict:
    now = _utcnow()
    share_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO shared_books (id, workspace_id, book_folder, shared_by, permissions, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (share_id, ws_id, book_folder, shared_by, permissions, now),
    )
    conn.commit()
    return {"id": share_id, "workspace_id": ws_id, "book_folder": book_folder}


def get_shared_books(conn: Any, ws_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT sb.*, u.name as shared_by_name FROM shared_books sb "
        "JOIN users u ON sb.shared_by = u.id WHERE sb.workspace_id = ?",
        (ws_id,),
    ).fetchall()
    return _rows_to_dicts(rows)


# ── Annotations ──


def create_annotation(
    conn: Any,
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


def get_annotations(conn: Any, book_folder: str, user_id: str | None = None, workspace_id: str | None = None) -> list[dict]:
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
    return _rows_to_dicts(rows)


def delete_annotation(conn: Any, ann_id: str, user_id: str) -> bool:
    cur = conn.execute("DELETE FROM annotations WHERE id = ? AND user_id = ?", (ann_id, user_id))
    conn.commit()
    return cur.rowcount > 0


# ── Activity Log ──


def log_activity(
    conn: Any,
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


def get_activity_feed(conn: Any, workspace_id: str | None = None, user_id: str | None = None, limit: int = 50) -> list[dict]:
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
    return _rows_to_dicts(rows)


# ── API Keys ──


def store_api_key(conn: Any, user_id: str, provider: str, encrypted_key: str, label: str = "") -> dict:
    key_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO api_keys (id, user_id, provider, encrypted_key, label, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (key_id, user_id, provider, encrypted_key, label, _utcnow()),
    )
    conn.commit()
    return {"id": key_id, "provider": provider, "label": label}


def get_user_api_keys(conn: Any, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, provider, label, created_at FROM api_keys WHERE user_id = ?", (user_id,)
    ).fetchall()
    return _rows_to_dicts(rows)


def get_api_key(conn: Any, user_id: str, provider: str) -> str | None:
    row = conn.execute(
        "SELECT encrypted_key FROM api_keys WHERE user_id = ? AND provider = ? ORDER BY created_at DESC LIMIT 1",
        (user_id, provider),
    ).fetchone()
    if row is None:
        return None
    r = _row_to_dict(row)
    return r["encrypted_key"] if r else None


def delete_api_key(conn: Any, key_id: str, user_id: str) -> bool:
    cur = conn.execute("DELETE FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user_id))
    conn.commit()
    return cur.rowcount > 0


# ── Usage Records ──


def record_usage(
    conn: Any,
    user_id: str,
    action: str,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
    provider: str = "",
    model: str = "",
    workspace_id: str | None = None,
    book_folder: str = "",
) -> None:
    conn.execute(
        "INSERT INTO usage_records (id, user_id, workspace_id, action, tokens_used, cost_usd, provider, model, book_folder, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, workspace_id, action, tokens_used, cost_usd, provider, model, book_folder, _utcnow()),
    )
    conn.commit()


def get_user_usage(conn: Any, user_id: str, days: int = 30) -> dict:
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(tokens_used), 0) as total_tokens, COALESCE(SUM(cost_usd), 0.0) as total_cost, "
        "COUNT(*) as total_requests FROM usage_records WHERE user_id = ? AND created_at >= ?",
        (user_id, cutoff),
    ).fetchone()
    r = _row_to_dict(row)
    return r if r else {"total_tokens": 0, "total_cost": 0.0, "total_requests": 0}


# ── Cost Dashboard Queries ──


def get_cost_by_book(conn: Any, user_id: str, days: int = 30) -> list[dict]:
    """Get per-book LLM token usage and cost for the cost dashboard."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT book_folder, "
        "COALESCE(SUM(tokens_used), 0) as total_tokens, "
        "COALESCE(SUM(cost_usd), 0.0) as total_cost, "
        "COUNT(*) as request_count, "
        "MAX(created_at) as last_used "
        "FROM usage_records "
        "WHERE user_id = ? AND created_at >= ? AND book_folder != '' "
        "GROUP BY book_folder "
        "ORDER BY total_cost DESC",
        (user_id, cutoff),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_cost_by_provider(conn: Any, user_id: str, days: int = 30) -> list[dict]:
    """Get per-provider cost breakdown."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT provider, model, "
        "COALESCE(SUM(tokens_used), 0) as total_tokens, "
        "COALESCE(SUM(cost_usd), 0.0) as total_cost, "
        "COUNT(*) as request_count "
        "FROM usage_records "
        "WHERE user_id = ? AND created_at >= ? AND provider != '' "
        "GROUP BY provider, model "
        "ORDER BY total_cost DESC",
        (user_id, cutoff),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_cost_by_action(conn: Any, user_id: str, days: int = 30) -> list[dict]:
    """Get per-action type cost breakdown."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT action, "
        "COALESCE(SUM(tokens_used), 0) as total_tokens, "
        "COALESCE(SUM(cost_usd), 0.0) as total_cost, "
        "COUNT(*) as request_count "
        "FROM usage_records "
        "WHERE user_id = ? AND created_at >= ? "
        "GROUP BY action "
        "ORDER BY total_cost DESC",
        (user_id, cutoff),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_cost_daily(conn: Any, user_id: str, days: int = 30) -> list[dict]:
    """Get daily cost time series for charts."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    # Use substr to group by date (YYYY-MM-DD from ISO timestamp)
    rows = conn.execute(
        "SELECT substr(created_at, 1, 10) as date, "
        "COALESCE(SUM(tokens_used), 0) as total_tokens, "
        "COALESCE(SUM(cost_usd), 0.0) as total_cost, "
        "COUNT(*) as request_count "
        "FROM usage_records "
        "WHERE user_id = ? AND created_at >= ? "
        "GROUP BY substr(created_at, 1, 10) "
        "ORDER BY date",
        (user_id, cutoff),
    ).fetchall()
    return _rows_to_dicts(rows)


# ── Workspace Invites ──


def create_invite(
    conn: Any,
    workspace_id: str,
    email: str,
    role: str,
    invited_by: str,
    expires_days: int = 7,
) -> dict:
    """Create a workspace invite for an email address.

    Works for both existing and not-yet-registered users.
    If the user already exists and is already a member, raises ValueError.
    """
    import secrets
    from datetime import timedelta

    email = email.lower().strip()
    now = _utcnow()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
    token = secrets.token_urlsafe(32)
    invite_id = str(uuid.uuid4())

    # Check if user is already a member
    existing_user = get_user_by_email(conn, email)
    if existing_user:
        existing_role = get_user_role_in_workspace(conn, workspace_id, existing_user["id"])
        if existing_role:
            raise ValueError(f"{email} is already a member of this workspace")

    # Check for existing pending invite (update it instead)
    existing_invite = conn.execute(
        "SELECT id FROM workspace_invites WHERE workspace_id = ? AND email = ? AND status = 'pending'",
        (workspace_id, email),
    ).fetchone()
    if existing_invite:
        row = _row_to_dict(existing_invite)
        conn.execute(
            "UPDATE workspace_invites SET role = ?, invited_by = ?, token = ?, expires_at = ? WHERE id = ?",
            (role, invited_by, token, expires_at, row["id"]),
        )
        conn.commit()
        return {"id": row["id"], "workspace_id": workspace_id, "email": email,
                "role": role, "token": token, "status": "pending", "expires_at": expires_at}

    conn.execute(
        "INSERT INTO workspace_invites (id, workspace_id, email, role, invited_by, status, token, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
        (invite_id, workspace_id, email, role, invited_by, token, now, expires_at),
    )
    conn.commit()
    return {"id": invite_id, "workspace_id": workspace_id, "email": email,
            "role": role, "token": token, "status": "pending", "expires_at": expires_at}


def get_workspace_invites(conn: Any, workspace_id: str) -> list[dict]:
    """List all pending invites for a workspace."""
    rows = conn.execute(
        "SELECT wi.*, u.name as invited_by_name FROM workspace_invites wi "
        "JOIN users u ON wi.invited_by = u.id "
        "WHERE wi.workspace_id = ? AND wi.status = 'pending' "
        "ORDER BY wi.created_at DESC",
        (workspace_id,),
    ).fetchall()
    return _rows_to_dicts(rows)


def get_invites_for_email(conn: Any, email: str) -> list[dict]:
    """List all pending invites for an email address (for the accept/decline UI)."""
    email = email.lower().strip()
    rows = conn.execute(
        "SELECT wi.*, w.name as workspace_name, u.name as invited_by_name "
        "FROM workspace_invites wi "
        "JOIN workspaces w ON wi.workspace_id = w.id "
        "JOIN users u ON wi.invited_by = u.id "
        "WHERE wi.email = ? AND wi.status = 'pending' "
        "ORDER BY wi.created_at DESC",
        (email,),
    ).fetchall()
    return _rows_to_dicts(rows)


def accept_invite(conn: Any, invite_id: str, user_id: str) -> dict | None:
    """Accept a pending invite — adds user as workspace member."""
    row = conn.execute(
        "SELECT * FROM workspace_invites WHERE id = ? AND status = 'pending'",
        (invite_id,),
    ).fetchone()
    invite = _row_to_dict(row)
    if not invite:
        return None

    # Check not expired
    if invite["expires_at"] < _utcnow():
        conn.execute("UPDATE workspace_invites SET status = 'expired' WHERE id = ?", (invite_id,))
        conn.commit()
        return None

    # Add as member
    add_workspace_member(conn, invite["workspace_id"], user_id, invite["role"], invited_by=invite["invited_by"])

    # Mark invite accepted
    conn.execute(
        "UPDATE workspace_invites SET status = 'accepted', accepted_at = ? WHERE id = ?",
        (_utcnow(), invite_id),
    )
    conn.commit()
    return invite


def accept_invite_by_token(conn: Any, token: str, user_id: str) -> dict | None:
    """Accept invite using the invite token (from email link)."""
    row = conn.execute(
        "SELECT * FROM workspace_invites WHERE token = ? AND status = 'pending'",
        (token,),
    ).fetchone()
    invite = _row_to_dict(row)
    if not invite:
        return None
    return accept_invite(conn, invite["id"], user_id)


def decline_invite(conn: Any, invite_id: str) -> bool:
    """Decline a pending invite."""
    cur = conn.execute(
        "UPDATE workspace_invites SET status = 'declined' WHERE id = ? AND status = 'pending'",
        (invite_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def revoke_invite(conn: Any, invite_id: str) -> bool:
    """Revoke (cancel) a pending invite (admin action)."""
    cur = conn.execute(
        "UPDATE workspace_invites SET status = 'revoked' WHERE id = ? AND status = 'pending'",
        (invite_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def auto_accept_pending_invites(conn: Any, user_id: str, email: str) -> list[dict]:
    """Auto-accept all pending non-expired invites for a newly registered user."""
    invites = get_invites_for_email(conn, email)
    accepted = []
    for inv in invites:
        if inv["expires_at"] >= _utcnow():
            result = accept_invite(conn, inv["id"], user_id)
            if result:
                accepted.append(result)
    return accepted
