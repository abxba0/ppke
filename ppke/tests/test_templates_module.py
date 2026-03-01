"""Tests for ppke.templates — registry, installer, loader."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════
# templates/registry.py
# ═══════════════════════════════════════════════════════════════════


class TestRegistryGetRegistry:
    def test_no_file(self, tmp_path):
        fake_path = tmp_path / "nonexistent.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", fake_path):
            from ppke.templates.registry import get_registry
            result = get_registry()
            assert result == {"plugins": {}, "last_updated": None}

    def test_valid_file(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        reg_file.write_text(json.dumps({
            "plugins": {"test": {"name": "test", "tier": "custom"}},
            "last_updated": "2025-01-01",
        }))
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import get_registry
            result = get_registry()
            assert "test" in result["plugins"]

    def test_invalid_json(self, tmp_path):
        reg_file = tmp_path / "bad.json"
        reg_file.write_text("not valid json{{{")
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import get_registry
            result = get_registry()
            assert result == {"plugins": {}, "last_updated": None}


class TestRegisterPlugin:
    def test_register_new_plugin(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import register_plugin, get_registry
            register_plugin("philosophy", "official", "2.0.0", "bundled", "Core Team", "Philosophy domain")
            reg = get_registry()
            assert "philosophy" in reg["plugins"]
            assert reg["plugins"]["philosophy"]["version"] == "2.0.0"
            assert reg["plugins"]["philosophy"]["author"] == "Core Team"

    def test_register_without_optional(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import register_plugin, get_registry
            register_plugin("minimal", "custom", "1.0.0", "manual")
            reg = get_registry()
            assert reg["plugins"]["minimal"]["author"] == "Unknown"
            assert reg["plugins"]["minimal"]["description"] == ""


class TestUnregisterPlugin:
    def test_unregister_existing(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import register_plugin, unregister_plugin, get_registry
            register_plugin("toremove", "custom", "1.0.0", "manual")
            result = unregister_plugin("toremove")
            assert result is True
            reg = get_registry()
            assert "toremove" not in reg["plugins"]

    def test_unregister_nonexistent(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import unregister_plugin
            result = unregister_plugin("nonexistent")
            assert result is False


class TestGetPluginInfo:
    def test_existing(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import register_plugin, get_plugin_info
            register_plugin("testplugin", "official", "1.0.0", "bundled")
            info = get_plugin_info("testplugin")
            assert info is not None
            assert info["tier"] == "official"

    def test_nonexistent(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import get_plugin_info
            assert get_plugin_info("missing") is None


class TestListRegisteredPlugins:
    def test_list_empty(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import list_registered_plugins
            assert list_registered_plugins() == []

    def test_list_with_plugins(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import register_plugin, list_registered_plugins
            register_plugin("a", "official", "1.0", "bundled")
            register_plugin("b", "custom", "1.0", "manual")
            plugins = list_registered_plugins()
            assert len(plugins) == 2


class TestRegistryStats:
    def test_stats_empty(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import get_registry_stats
            stats = get_registry_stats()
            assert stats["total"] == 0
            assert stats["official"] == 0
            assert stats["custom"] == 0

    def test_stats_with_plugins(self, tmp_path):
        reg_file = tmp_path / "reg.json"
        with patch("ppke.templates.registry.REGISTRY_FILE", reg_file):
            from ppke.templates.registry import register_plugin, get_registry_stats
            register_plugin("a", "official", "1.0", "bundled")
            register_plugin("b", "custom", "1.0", "manual")
            register_plugin("c", "official", "1.0", "bundled")
            stats = get_registry_stats()
            assert stats["total"] == 3
            assert stats["official"] == 2
            assert stats["custom"] == 1


# ═══════════════════════════════════════════════════════════════════
# templates/installer.py
# ═══════════════════════════════════════════════════════════════════


class TestInstaller:
    def test_can_use_emojis(self):
        from ppke.templates.installer import _can_use_emojis
        result = _can_use_emojis()
        assert isinstance(result, bool)

    def test_print_with_emojis(self, capsys):
        from ppke.templates.installer import _print
        _print("Test message")
        captured = capsys.readouterr()
        assert "Test" in captured.out

    def test_print_emoji_replacement(self, capsys):
        from ppke.templates.installer import _print
        with patch("ppke.templates.installer._USE_EMOJIS", False):
            _print("📥 Cloning repo")
            captured = capsys.readouterr()
            assert "[CLONE]" in captured.out

    def test_install_error_class(self):
        from ppke.templates.installer import TemplateInstallError
        err = TemplateInstallError("test error")
        assert str(err) == "test error"
        assert isinstance(err, Exception)
