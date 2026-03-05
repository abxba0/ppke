"""Tests for GitHub PR ingestion — converter, CLI command, and web endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════
# converter/github_pr.py
# ═══════════════════════════════════════════════════════════════════


class TestGitHubPRUrlDetection:
    """Test URL parsing and detection for GitHub PR URLs."""

    def test_valid_pr_url(self):
        from ppke.converter.github_pr import is_github_pr_url
        assert is_github_pr_url("https://github.com/owner/repo/pull/123")

    def test_valid_pr_url_with_www(self):
        from ppke.converter.github_pr import is_github_pr_url
        assert is_github_pr_url("https://www.github.com/owner/repo/pull/456")

    def test_valid_pr_url_http(self):
        from ppke.converter.github_pr import is_github_pr_url
        assert is_github_pr_url("http://github.com/owner/repo/pull/1")

    def test_invalid_url_not_pr(self):
        from ppke.converter.github_pr import is_github_pr_url
        assert not is_github_pr_url("https://github.com/owner/repo")

    def test_invalid_url_issue(self):
        from ppke.converter.github_pr import is_github_pr_url
        assert not is_github_pr_url("https://github.com/owner/repo/issues/123")

    def test_invalid_url_random(self):
        from ppke.converter.github_pr import is_github_pr_url
        assert not is_github_pr_url("https://example.com/some/page")

    def test_empty_string(self):
        from ppke.converter.github_pr import is_github_pr_url
        assert not is_github_pr_url("")

    def test_parse_valid_url(self):
        from ppke.converter.github_pr import parse_pr_url
        owner, repo, number = parse_pr_url("https://github.com/my-org/my-repo/pull/42")
        assert owner == "my-org"
        assert repo == "my-repo"
        assert number == 42

    def test_parse_invalid_url(self):
        from ppke.converter.github_pr import parse_pr_url
        with pytest.raises(ValueError, match="Not a valid GitHub PR URL"):
            parse_pr_url("https://example.com/not/a/pr")

    def test_parse_url_with_whitespace(self):
        from ppke.converter.github_pr import parse_pr_url
        owner, repo, number = parse_pr_url("  https://github.com/owner/repo/pull/99  ")
        assert owner == "owner"
        assert repo == "repo"
        assert number == 99


class TestGitHubPRConverter:
    """Test the Markdown conversion from PR data."""

    def _mock_pr_data(self):
        return {
            "pr": {
                "title": "Add login feature",
                "body": "This PR adds a login form with validation.",
                "user": {"login": "testdev"},
                "state": "open",
                "created_at": "2025-01-15T10:00:00Z",
                "updated_at": "2025-01-16T12:00:00Z",
                "base": {"ref": "main"},
                "head": {"ref": "feature/login"},
                "additions": 120,
                "deletions": 30,
                "changed_files": 5,
                "labels": [{"name": "enhancement"}, {"name": "frontend"}],
                "merged": False,
            },
            "diff": "diff --git a/src/login.py b/src/login.py\n+def login():\n+    pass",
            "files": [
                {
                    "filename": "src/login.py",
                    "status": "added",
                    "additions": 50,
                    "deletions": 0,
                },
                {
                    "filename": "tests/test_login.py",
                    "status": "added",
                    "additions": 70,
                    "deletions": 0,
                },
            ],
            "comments": [
                {
                    "user": {"login": "reviewer1"},
                    "body": "Looks good! Please add input validation.",
                    "created_at": "2025-01-15T14:00:00Z",
                },
            ],
            "reviews": [
                {
                    "user": {"login": "reviewer2"},
                    "state": "CHANGES_REQUESTED",
                    "body": "Need to sanitize input fields.",
                    "submitted_at": "2025-01-15T15:00:00Z",
                },
            ],
        }

    @patch("ppke.converter.github_pr.fetch_pr_data")
    def test_convert_produces_markdown(self, mock_fetch):
        from ppke.converter.github_pr import convert_github_pr
        mock_fetch.return_value = self._mock_pr_data()

        result = convert_github_pr("https://github.com/owner/repo/pull/1")

        assert "# PR #1: Add login feature" in result
        assert "@testdev" in result
        assert "open" in result
        assert "feature/login" in result
        assert "main" in result
        assert "## Description" in result
        assert "login form" in result
        assert "## Changed Files" in result
        assert "`src/login.py`" in result
        assert "## Code Changes (Diff)" in result
        assert "```diff" in result
        assert "## Code Reviews" in result
        assert "CHANGES_REQUESTED" in result
        assert "## Discussion" in result
        assert "reviewer1" in result

    @patch("ppke.converter.github_pr.fetch_pr_data")
    def test_convert_without_comments(self, mock_fetch):
        from ppke.converter.github_pr import convert_github_pr
        data = self._mock_pr_data()
        data["comments"] = []
        data["reviews"] = []
        mock_fetch.return_value = data

        result = convert_github_pr(
            "https://github.com/owner/repo/pull/1",
            include_comments=False,
            include_reviews=False,
        )

        assert "# PR #1:" in result
        assert "## Discussion" not in result
        assert "## Code Reviews" not in result

    @patch("ppke.converter.github_pr.fetch_pr_data")
    def test_convert_merged_pr(self, mock_fetch):
        from ppke.converter.github_pr import convert_github_pr
        data = self._mock_pr_data()
        data["pr"]["merged"] = True
        mock_fetch.return_value = data

        result = convert_github_pr("https://github.com/owner/repo/pull/1")
        assert "Merged" in result

    @patch("ppke.converter.github_pr.fetch_pr_data")
    def test_convert_labels(self, mock_fetch):
        from ppke.converter.github_pr import convert_github_pr
        mock_fetch.return_value = self._mock_pr_data()

        result = convert_github_pr("https://github.com/owner/repo/pull/1")
        assert "enhancement" in result
        assert "frontend" in result

    @patch("ppke.converter.github_pr.fetch_pr_data")
    def test_convert_empty_body(self, mock_fetch):
        from ppke.converter.github_pr import convert_github_pr
        data = self._mock_pr_data()
        data["pr"]["body"] = ""
        mock_fetch.return_value = data

        result = convert_github_pr("https://github.com/owner/repo/pull/1")
        assert "No description provided" in result


class TestFormatHelpers:
    """Test internal formatting helpers."""

    def test_format_diff_truncation(self):
        from ppke.converter.github_pr import _format_diff_section
        long_diff = "\n".join([f"+line {i}" for i in range(1000)])
        result = _format_diff_section(long_diff, max_lines=100)
        assert "truncated" in result
        assert "```diff" in result

    def test_format_diff_short(self):
        from ppke.converter.github_pr import _format_diff_section
        result = _format_diff_section("+line 1\n+line 2")
        assert "```diff" in result
        assert "truncated" not in result

    def test_format_files_table_empty(self):
        from ppke.converter.github_pr import _format_files_table
        result = _format_files_table([])
        assert "No file changes" in result

    def test_format_files_table(self):
        from ppke.converter.github_pr import _format_files_table
        result = _format_files_table([
            {"filename": "main.py", "status": "modified", "additions": 10, "deletions": 5}
        ])
        assert "`main.py`" in result
        assert "+10" in result
        assert "-5" in result

    def test_format_comments_empty(self):
        from ppke.converter.github_pr import _format_comments
        result = _format_comments([])
        assert "No comments" in result

    def test_format_reviews_empty(self):
        from ppke.converter.github_pr import _format_reviews
        result = _format_reviews([])
        assert "No reviews" in result

    def test_format_reviews_approved(self):
        from ppke.converter.github_pr import _format_reviews
        result = _format_reviews([{
            "user": {"login": "dev"},
            "state": "APPROVED",
            "body": "Ship it!",
            "submitted_at": "2025-01-01T00:00:00Z",
        }])
        assert "✅" in result
        assert "APPROVED" in result
        assert "Ship it!" in result


class TestGitHubHeaders:
    """Test API header construction."""

    def test_headers_without_token(self):
        from ppke.converter.github_pr import _github_headers
        with patch.dict("os.environ", {}, clear=True):
            headers = _github_headers(token=None)
            assert "Authorization" not in headers
            assert "Accept" in headers
            assert "User-Agent" in headers

    def test_headers_with_token(self):
        from ppke.converter.github_pr import _github_headers
        headers = _github_headers(token="ghp_test123")
        assert headers["Authorization"] == "token ghp_test123"

    def test_headers_from_env(self):
        from ppke.converter.github_pr import _github_headers
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_env_token"}):
            headers = _github_headers(token=None)
            assert headers["Authorization"] == "token ghp_env_token"


# ═══════════════════════════════════════════════════════════════════
# gh_pr domain template
# ═══════════════════════════════════════════════════════════════════


class TestGhPrTemplate:
    """Test that the gh_pr template loads correctly."""

    def test_template_loads(self):
        from ppke.templates.loader import load_template
        template = load_template("gh_pr")
        assert template.name == "gh_pr"
        assert template.version == "1.0.0"
        assert template.tier == "official"
        assert len(template.stages) == 4
        assert template.stages[0]["id"] == "extraction"

    def test_template_in_discover(self):
        from ppke.templates.loader import discover_templates
        templates = discover_templates()
        assert "gh_pr" in templates

    def test_template_prompts(self):
        from ppke.templates.loader import load_template
        template = load_template("gh_pr")
        assert "extraction" in template.prompts
        assert "logical_map" in template.prompts
        assert "concepts" in template.prompts
        assert "patterns" in template.prompts

    def test_template_schema(self):
        from ppke.templates.loader import load_template
        template = load_template("gh_pr")
        assert template.schema.get("extraction_model") is not None


# ═══════════════════════════════════════════════════════════════════
# CLI command: ingest-pr
# ═══════════════════════════════════════════════════════════════════


class TestIngestPRCommand:
    """Test the CLI ingest-pr command."""

    def test_command_exists(self):
        from click.testing import CliRunner
        from ppke.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["ingest-pr", "--help"])
        assert result.exit_code == 0
        assert "GitHub Pull Request" in result.output
        assert "--token" in result.output
        assert "--no-comments" in result.output
        assert "--no-reviews" in result.output

    def test_invalid_url(self):
        from click.testing import CliRunner
        from ppke.cli import main
        runner = CliRunner()
        result = runner.invoke(main, [
            "ingest-pr", "https://example.com/not/a/pr"
        ])
        assert result.exit_code != 0
        assert "Not a valid GitHub PR URL" in result.output


# ═══════════════════════════════════════════════════════════════════
# Web API: /api/import-github-pr and /api/github/webhook
# ═══════════════════════════════════════════════════════════════════


_FAKE_USER = {
    "id": "user-001",
    "email": "test@example.com",
    "name": "Test User",
    "role": "admin",
    "password_hash": "pbkdf2:salt:hash",
    "created_at": "2025-01-01T00:00:00",
}


class TestWebGitHubPRImport:
    """Test the /api/import-github-pr endpoint."""

    @pytest.fixture()
    def client(self, tmp_path):
        """Create a test client with mocked config."""
        import os
        os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

        with patch("ppke.web.app._try_get_user", return_value=_FAKE_USER), \
             patch("ppke.web.app._user_vault_path", return_value=tmp_path / "vault"), \
             patch("ppke.web.app.run_task") as mock_run, \
             patch("ppke.web.app.create_job", return_value="test-job"):
            (tmp_path / "vault" / ".uploads").mkdir(parents=True, exist_ok=True)
            from starlette.testclient import TestClient
            from ppke.web.app import app
            yield TestClient(app)

    def test_invalid_url_rejected(self, client):
        resp = client.post("/api/import-github-pr", data={
            "url": "https://example.com/not/a/pr",
        })
        assert resp.status_code == 400

    def test_valid_url_accepted(self, client):
        resp = client.post("/api/import-github-pr", data={
            "url": "https://github.com/owner/repo/pull/123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_type"] == "github_pr"
        assert "job_id" in data


class TestWebGitHubWebhook:
    """Test the /api/github/webhook endpoint."""

    @pytest.fixture()
    def client(self, tmp_path):
        """Create a test client with mocked config."""
        import os
        os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

        with patch("ppke.web.app.run_task") as mock_run, \
             patch("ppke.web.app.create_job", return_value="wh-job"), \
             patch("ppke.web.app._get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.vault_path = tmp_path / "vault"
            mock_cfg.enable_vector_search = False
            mock_cfg.enable_knowledge_graph = False
            mock_config.return_value = mock_cfg
            (tmp_path / "vault" / ".uploads").mkdir(parents=True, exist_ok=True)
            from starlette.testclient import TestClient
            from ppke.web.app import app
            yield TestClient(app)

    def test_ping_event(self, client):
        resp = client.post(
            "/api/github/webhook",
            json={"zen": "test"},
            headers={"X-GitHub-Event": "ping"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pong"

    def test_non_pr_event_ignored(self, client):
        resp = client.post(
            "/api/github/webhook",
            json={"action": "created"},
            headers={"X-GitHub-Event": "issue_comment"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_pr_closed_ignored(self, client):
        resp = client.post(
            "/api/github/webhook",
            json={"action": "closed", "pull_request": {}},
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_pr_opened_accepted(self, client):
        resp = client.post(
            "/api/github/webhook",
            json={
                "action": "opened",
                "pull_request": {
                    "html_url": "https://github.com/owner/repo/pull/42",
                    "title": "Test PR",
                    "user": {"login": "author"},
                    "number": 42,
                },
            },
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_type"] == "github_webhook"
        assert data["pr_number"] == 42
        assert "job_id" in data

    def test_webhook_signature_verification(self, tmp_path):
        """Test webhook signature verification when secret is set."""
        import os
        os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

        secret = "test-webhook-secret"

        with patch("ppke.web.app.run_task"), \
             patch("ppke.web.app.create_job", return_value="wh-job"), \
             patch("ppke.web.app._get_config") as mock_config, \
             patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": secret}):
            mock_cfg = MagicMock()
            mock_cfg.vault_path = tmp_path / "vault"
            mock_cfg.enable_vector_search = False
            mock_cfg.enable_knowledge_graph = False
            mock_config.return_value = mock_cfg
            (tmp_path / "vault" / ".uploads").mkdir(parents=True, exist_ok=True)

            from starlette.testclient import TestClient
            from ppke.web.app import app
            client = TestClient(app)

            payload = json.dumps({
                "action": "opened",
                "pull_request": {
                    "html_url": "https://github.com/owner/repo/pull/1",
                    "title": "Test",
                    "user": {"login": "dev"},
                    "number": 1,
                },
            }).encode()

            # Correct signature
            sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

            resp = client.post(
                "/api/github/webhook",
                content=payload,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
            assert resp.status_code == 200

            # Invalid signature
            resp = client.post(
                "/api/github/webhook",
                content=payload,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": "sha256=invalid",
                    "Content-Type": "application/json",
                },
            )
            assert resp.status_code == 403
