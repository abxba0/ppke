"""Tests for the plugin marketplace module and API endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════
# templates/marketplace.py — unit tests
# ═══════════════════════════════════════════════════════════════════


class TestGetCatalog:
    def test_returns_seed_when_no_file(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import get_catalog
            catalog = get_catalog()
            assert "plugins" in catalog
            assert len(catalog["plugins"]) > 0

    def test_loads_from_file(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        fake_path.write_text(json.dumps({
            "plugins": {"test_plugin": {"name": "test_plugin", "version": "1.0.0", "author": "Test"}},
            "last_updated": "2025-01-01",
        }))
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import get_catalog
            catalog = get_catalog()
            assert "test_plugin" in catalog["plugins"]

    def test_returns_seed_on_invalid_json(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        fake_path.write_text("{{{bad json")
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import get_catalog
            catalog = get_catalog()
            assert len(catalog["plugins"]) > 0


class TestListMarketplacePlugins:
    def test_lists_all_plugins(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import list_marketplace_plugins
            result = list_marketplace_plugins()
            assert result["total"] > 0
            assert len(result["plugins"]) > 0
            assert "categories" in result
            assert result["page"] == 1

    def test_filter_by_category(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import list_marketplace_plugins
            result = list_marketplace_plugins(category="humanities")
            for p in result["plugins"]:
                assert p["category"] == "humanities"

    def test_search_by_name(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import list_marketplace_plugins
            result = list_marketplace_plugins(search="philosophy")
            assert any(p["name"] == "philosophy" for p in result["plugins"])

    def test_search_by_tag(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import list_marketplace_plugins
            result = list_marketplace_plugins(search="legal")
            assert any(p["name"] == "legal" for p in result["plugins"])

    def test_sort_by_name(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import list_marketplace_plugins
            result = list_marketplace_plugins(sort_by="name")
            names = [p["name"] for p in result["plugins"]]
            assert names == sorted(names)

    def test_sort_by_rating(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import list_marketplace_plugins
            result = list_marketplace_plugins(sort_by="rating")
            ratings = [p["average_rating"] for p in result["plugins"]]
            assert ratings == sorted(ratings, reverse=True)

    def test_pagination(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import list_marketplace_plugins
            result = list_marketplace_plugins(per_page=2, page=1)
            assert len(result["plugins"]) == 2
            assert result["total_pages"] >= 2

    def test_enriched_fields(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import list_marketplace_plugins
            result = list_marketplace_plugins()
            for p in result["plugins"]:
                assert "average_rating" in p
                assert "rating_count" in p


class TestGetMarketplacePlugin:
    def test_returns_existing(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import get_marketplace_plugin
            plugin = get_marketplace_plugin("philosophy")
            assert plugin is not None
            assert plugin["name"] == "philosophy"
            assert "average_rating" in plugin

    def test_returns_none_for_missing(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import get_marketplace_plugin
            assert get_marketplace_plugin("nonexistent_xyz") is None


class TestRatePlugin:
    def test_rate_plugin(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import rate_plugin
            result = rate_plugin("philosophy", 5)
            assert result is not None
            assert result["average_rating"] > 0

    def test_rate_nonexistent(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import rate_plugin
            assert rate_plugin("nonexistent_xyz", 3) is None

    def test_rate_invalid_value(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import rate_plugin
            with pytest.raises(ValueError, match="between 1 and 5"):
                rate_plugin("philosophy", 0)
            with pytest.raises(ValueError, match="between 1 and 5"):
                rate_plugin("philosophy", 6)


class TestSubmitPlugin:
    def test_submit_new(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import submit_plugin
            result = submit_plugin(
                name="test_domain",
                version="1.0.0",
                author="Tester",
                description="A test plugin",
                category="other",
                tags=["test"],
            )
            assert result["name"] == "test_domain"
            assert result["tier"] == "community"
            assert result["downloads"] == 0

    def test_submit_duplicate(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import submit_plugin
            with pytest.raises(ValueError, match="already exists"):
                submit_plugin("philosophy", "1.0.0", "Test", "Duplicate")

    def test_submit_with_github(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import submit_plugin
            result = submit_plugin(
                name="github_plugin",
                version="1.0.0",
                author="Tester",
                description="A GitHub plugin",
                source_url="https://github.com/user/repo",
            )
            assert "github:" in result["source"]


class TestIncrementDownloads:
    def test_increment(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import (
                increment_downloads, get_marketplace_plugin,
            )
            before = get_marketplace_plugin("philosophy")["downloads"]
            increment_downloads("philosophy")
            after = get_marketplace_plugin("philosophy")["downloads"]
            assert after == before + 1

    def test_increment_nonexistent(self, tmp_path):
        fake_path = tmp_path / "marketplace.json"
        with patch("ppke.templates.marketplace.MARKETPLACE_FILE", fake_path):
            from ppke.templates.marketplace import increment_downloads
            increment_downloads("no_such_plugin")  # no-op, no error


class TestAvgRating:
    def test_empty(self):
        from ppke.templates.marketplace import _avg_rating
        assert _avg_rating([]) == 0.0

    def test_normal(self):
        from ppke.templates.marketplace import _avg_rating
        assert _avg_rating([4, 5]) == 4.5

    def test_single(self):
        from ppke.templates.marketplace import _avg_rating
        assert _avg_rating([3]) == 3.0


# ═══════════════════════════════════════════════════════════════════
# Web API endpoint tests
# ═══════════════════════════════════════════════════════════════════


_FAKE_USER = {
    "id": "user-001",
    "email": "test@example.com",
    "name": "Test User",
    "role": "admin",
    "password_hash": "pbkdf2:salt:hash",
    "created_at": "2025-01-01T00:00:00",
}


@pytest.fixture()
def mp_client(tmp_path):
    """Create a test client with marketplace file patched to tmp_path."""
    from starlette.testclient import TestClient
    from ppke.web import app as app_module
    from ppke.auth import deps

    real_app = app_module.app

    real_app.dependency_overrides[deps.get_current_user] = lambda: _FAKE_USER
    real_app.dependency_overrides[deps.get_optional_user] = lambda: _FAKE_USER

    vault = tmp_path / "vault"
    vault.mkdir()
    mp_file = tmp_path / "marketplace.json"

    with patch.object(app_module, "_vault_path", return_value=vault), \
         patch.object(app_module, "_user_vault_path", return_value=vault), \
         patch.object(app_module, "_try_get_user", return_value=_FAKE_USER), \
         patch.object(app_module, "_get_db", return_value=MagicMock()), \
         patch("ppke.templates.marketplace.MARKETPLACE_FILE", mp_file):
        yield TestClient(real_app, raise_server_exceptions=False)

    real_app.dependency_overrides.clear()


class TestMarketplaceAPI:
    def test_marketplace_page(self, mp_client):
        resp = mp_client.get("/marketplace")
        assert resp.status_code == 200
        assert "Plugin Marketplace" in resp.text

    def test_api_list(self, mp_client):
        resp = mp_client.get("/api/marketplace/plugins")
        assert resp.status_code == 200
        data = resp.json()
        assert "plugins" in data
        assert data["total"] > 0

    def test_api_list_search(self, mp_client):
        resp = mp_client.get("/api/marketplace/plugins?q=philosophy")
        assert resp.status_code == 200
        data = resp.json()
        assert any(p["name"] == "philosophy" for p in data["plugins"])

    def test_api_list_category(self, mp_client):
        resp = mp_client.get("/api/marketplace/plugins?category=professional")
        assert resp.status_code == 200
        data = resp.json()
        for p in data["plugins"]:
            assert p["category"] == "professional"

    def test_api_detail(self, mp_client):
        resp = mp_client.get("/api/marketplace/plugins/philosophy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "philosophy"
        assert "average_rating" in data

    def test_api_detail_not_found(self, mp_client):
        resp = mp_client.get("/api/marketplace/plugins/nonexistent")
        assert resp.status_code == 404

    def test_api_rate(self, mp_client):
        resp = mp_client.post(
            "/api/marketplace/plugins/philosophy/rate",
            json={"rating": 4},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["average_rating"] > 0

    def test_api_rate_invalid(self, mp_client):
        resp = mp_client.post(
            "/api/marketplace/plugins/philosophy/rate",
            json={"rating": 10},
        )
        assert resp.status_code == 422

    def test_api_rate_not_found(self, mp_client):
        resp = mp_client.post(
            "/api/marketplace/plugins/nonexistent/rate",
            json={"rating": 3},
        )
        assert resp.status_code == 404

    def test_api_install_official(self, mp_client):
        resp = mp_client.post("/api/marketplace/plugins/philosophy/install")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "already_installed"

    def test_api_install_not_found(self, mp_client):
        resp = mp_client.post("/api/marketplace/plugins/nonexistent/install")
        assert resp.status_code == 404

    def test_api_submit(self, mp_client):
        resp = mp_client.post("/api/marketplace/submit", json={
            "name": "new_domain",
            "version": "1.0.0",
            "author": "Test Author",
            "description": "A new test plugin for testing purposes.",
            "category": "other",
            "tags": "test, domain",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new_domain"
        assert data["tier"] == "community"

    def test_api_submit_duplicate(self, mp_client):
        resp = mp_client.post("/api/marketplace/submit", json={
            "name": "philosophy",
            "version": "1.0.0",
            "author": "Duplicate",
            "description": "Duplicate plugin",
        })
        assert resp.status_code == 409

    def test_api_submit_invalid_name(self, mp_client):
        resp = mp_client.post("/api/marketplace/submit", json={
            "name": "Bad-Name!",
            "version": "1.0.0",
            "author": "Test",
            "description": "Invalid name",
        })
        assert resp.status_code == 422

    def test_api_submit_missing_fields(self, mp_client):
        resp = mp_client.post("/api/marketplace/submit", json={
            "name": "test",
        })
        assert resp.status_code == 422
