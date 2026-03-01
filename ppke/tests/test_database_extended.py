"""Extended tests for ppke.auth.database — workspace, annotation, API key, cost queries."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def db_conn(tmp_path):
    """Create a real SQLite database with the full schema."""
    from ppke.auth.database import get_db
    db_path = tmp_path / "test.db"
    conn = get_db(db_path)
    return conn


class TestWorkspaces:
    def test_create_workspace(self, db_conn):
        from ppke.auth.database import create_workspace, create_user
        user = create_user(db_conn, "test@test.com", "Test", "hash")
        ws = create_workspace(db_conn, "My Workspace", "my-workspace", user["id"])
        assert ws["name"] == "My Workspace"

    def test_get_user_workspaces(self, db_conn):
        from ppke.auth.database import create_workspace, create_user, get_user_workspaces
        user = create_user(db_conn, "ws@test.com", "WS User", "hash")
        create_workspace(db_conn, "WS1", "ws1", user["id"])
        create_workspace(db_conn, "WS2", "ws2", user["id"])
        workspaces = get_user_workspaces(db_conn, user["id"])
        assert len(workspaces) >= 2

    def test_get_workspace_members(self, db_conn):
        from ppke.auth.database import create_workspace, create_user, get_workspace_members
        user = create_user(db_conn, "mem@test.com", "Mem User", "hash")
        ws = create_workspace(db_conn, "Members WS", "members-ws", user["id"])
        members = get_workspace_members(db_conn, ws["id"])
        assert len(members) >= 1

    def test_add_workspace_member(self, db_conn):
        from ppke.auth.database import (
            create_workspace, create_user, add_workspace_member,
            get_workspace_members
        )
        owner = create_user(db_conn, "own@test.com", "Owner", "hash")
        member = create_user(db_conn, "new@test.com", "New", "hash")
        ws = create_workspace(db_conn, "Team", "team", owner["id"])
        add_workspace_member(db_conn, ws["id"], member["id"], "editor", invited_by=owner["id"])
        members = get_workspace_members(db_conn, ws["id"])
        assert len(members) >= 2

    def test_get_user_role_in_workspace(self, db_conn):
        from ppke.auth.database import (
            create_workspace, create_user, get_user_role_in_workspace
        )
        user = create_user(db_conn, "role@test.com", "Role User", "hash")
        ws = create_workspace(db_conn, "Role WS", "role-ws", user["id"])
        role = get_user_role_in_workspace(db_conn, ws["id"], user["id"])
        assert role == "admin"

    def test_get_user_role_not_member(self, db_conn):
        from ppke.auth.database import (
            create_workspace, create_user, get_user_role_in_workspace
        )
        user1 = create_user(db_conn, "u1@test.com", "U1", "hash")
        user2 = create_user(db_conn, "u2@test.com", "U2", "hash")
        ws = create_workspace(db_conn, "Priv", "priv", user1["id"])
        role = get_user_role_in_workspace(db_conn, ws["id"], user2["id"])
        assert role is None

    def test_update_member_role(self, db_conn):
        from ppke.auth.database import (
            create_workspace, create_user, add_workspace_member,
            update_member_role, get_user_role_in_workspace
        )
        owner = create_user(db_conn, "up1@test.com", "Owner", "hash")
        member = create_user(db_conn, "up2@test.com", "Mem", "hash")
        ws = create_workspace(db_conn, "Upgrade", "upgrade", owner["id"])
        add_workspace_member(db_conn, ws["id"], member["id"], "viewer")
        update_member_role(db_conn, ws["id"], member["id"], "admin")
        role = get_user_role_in_workspace(db_conn, ws["id"], member["id"])
        assert role == "admin"

    def test_remove_workspace_member(self, db_conn):
        from ppke.auth.database import (
            create_workspace, create_user, add_workspace_member,
            remove_workspace_member, get_user_role_in_workspace
        )
        owner = create_user(db_conn, "rm1@test.com", "Owner", "hash")
        member = create_user(db_conn, "rm2@test.com", "Mem", "hash")
        ws = create_workspace(db_conn, "Removal", "removal", owner["id"])
        add_workspace_member(db_conn, ws["id"], member["id"], "viewer")
        remove_workspace_member(db_conn, ws["id"], member["id"])
        role = get_user_role_in_workspace(db_conn, ws["id"], member["id"])
        assert role is None


class TestSharedBooks:
    def test_share_and_get_books(self, db_conn):
        from ppke.auth.database import (
            create_workspace, create_user, share_book,
            get_shared_books
        )
        user = create_user(db_conn, "share@test.com", "Sharer", "hash")
        ws = create_workspace(db_conn, "Share WS", "share-ws", user["id"])
        share_book(db_conn, ws["id"], "Book_Test", user["id"], "read")
        books = get_shared_books(db_conn, ws["id"])
        assert len(books) >= 1
        assert books[0]["book_folder"] == "Book_Test"


class TestAnnotations:
    def test_create_and_get_annotations(self, db_conn):
        from ppke.auth.database import (
            create_user, create_annotation, get_annotations
        )
        user = create_user(db_conn, "ann@test.com", "Ann User", "hash")
        ann = create_annotation(
            db_conn, user["id"], "Book_Test", "{01}.{01}",
            "My note", "note"
        )
        assert ann is not None
        annotations = get_annotations(db_conn, "Book_Test", user_id=user["id"])
        assert len(annotations) >= 1

    def test_delete_annotation(self, db_conn):
        from ppke.auth.database import (
            create_user, create_annotation, delete_annotation, get_annotations
        )
        user = create_user(db_conn, "del@test.com", "Del User", "hash")
        ann = create_annotation(
            db_conn, user["id"], "Book_Test", "{01}.{01}",
            "To delete", "note"
        )
        result = delete_annotation(db_conn, ann["id"], user["id"])
        assert result is True

    def test_delete_nonexistent_annotation(self, db_conn):
        from ppke.auth.database import delete_annotation
        result = delete_annotation(db_conn, "nonexistent-id", "user-1")
        assert result is False


class TestAPIKeys:
    def test_store_and_get_keys(self, db_conn):
        from ppke.auth.database import (
            create_user, store_api_key, get_user_api_keys
        )
        user = create_user(db_conn, "key@test.com", "Key User", "hash")
        store_api_key(db_conn, user["id"], "openai", "sk-test123")
        keys = get_user_api_keys(db_conn, user["id"])
        assert len(keys) >= 1

    def test_delete_api_key(self, db_conn):
        from ppke.auth.database import (
            create_user, store_api_key, delete_api_key, get_user_api_keys
        )
        user = create_user(db_conn, "dkey@test.com", "DKey User", "hash")
        key = store_api_key(db_conn, user["id"], "openai", "sk-test456")
        result = delete_api_key(db_conn, key["id"], user["id"])
        assert result is True

    def test_delete_nonexistent_key(self, db_conn):
        from ppke.auth.database import delete_api_key
        result = delete_api_key(db_conn, "nonexistent", "user-1")
        assert result is False


class TestActivityLog:
    def test_log_and_get_activity(self, db_conn):
        from ppke.auth.database import (
            create_user, log_activity, get_activity_feed
        )
        user = create_user(db_conn, "act@test.com", "Act User", "hash")
        log_activity(db_conn, user["id"], "test action", "book", "Book_Test")
        feed = get_activity_feed(db_conn, user_id=user["id"])
        assert len(feed) >= 1
        assert feed[0]["action"] == "test action"


class TestUsageTracking:
    def test_record_and_get_usage(self, db_conn):
        from ppke.auth.database import (
            create_user, record_usage, get_user_usage
        )
        user = create_user(db_conn, "usage@test.com", "Usage User", "hash")
        record_usage(db_conn, user["id"], action="query", tokens_used=100, cost_usd=0.05, provider="openai", model="gpt-4")
        usage = get_user_usage(db_conn, user["id"])
        assert usage is not None


class TestCostQueries:
    def test_cost_by_book(self, db_conn):
        from ppke.auth.database import (
            create_user, record_usage, get_cost_by_book
        )
        user = create_user(db_conn, "cost1@test.com", "Cost1", "hash")
        record_usage(db_conn, user["id"], action="query", tokens_used=100, cost_usd=0.05, provider="openai", model="gpt-4", book_folder="Book_A")
        result = get_cost_by_book(db_conn, user["id"])
        assert isinstance(result, list)

    def test_cost_by_provider(self, db_conn):
        from ppke.auth.database import (
            create_user, record_usage, get_cost_by_provider
        )
        user = create_user(db_conn, "cost2@test.com", "Cost2", "hash")
        record_usage(db_conn, user["id"], action="query", tokens_used=100, cost_usd=0.05, provider="openai", model="gpt-4")
        result = get_cost_by_provider(db_conn, user["id"])
        assert isinstance(result, list)

    def test_cost_by_action(self, db_conn):
        from ppke.auth.database import (
            create_user, record_usage, get_cost_by_action
        )
        user = create_user(db_conn, "cost3@test.com", "Cost3", "hash")
        record_usage(db_conn, user["id"], action="query", tokens_used=100, cost_usd=0.05, provider="openai", model="gpt-4")
        result = get_cost_by_action(db_conn, user["id"])
        assert isinstance(result, list)

    def test_cost_daily(self, db_conn):
        from ppke.auth.database import (
            create_user, record_usage, get_cost_daily
        )
        user = create_user(db_conn, "cost4@test.com", "Cost4", "hash")
        record_usage(db_conn, user["id"], action="query", tokens_used=100, cost_usd=0.05, provider="openai", model="gpt-4")
        result = get_cost_daily(db_conn, user["id"])
        assert isinstance(result, list)


class TestDBConnectionWrapper:
    def test_detect_backend_sqlite(self):
        from ppke.auth.database import _detect_backend
        # Reset cached value to force re-detection
        import ppke.auth.database as db_mod
        old = db_mod._db_backend
        db_mod._db_backend = None
        try:
            import os
            os.environ.pop("DATABASE_URL", None)
            result = _detect_backend()
            assert result == "sqlite"
        finally:
            db_mod._db_backend = old

    def test_db_connection_execute(self, db_conn):
        # db_conn is already a DBConnection from get_db()
        result = db_conn.execute("SELECT 1")
        assert result is not None

    def test_db_connection_commit(self, db_conn):
        db_conn.commit()  # Should not raise

    def test_db_connection_rollback(self, db_conn):
        db_conn.rollback()  # Should not raise
