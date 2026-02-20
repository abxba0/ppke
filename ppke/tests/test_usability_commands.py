"""Tests for usability commands: cheat, doctor, notebook, menu, tui."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from ppke.cli import main, _append_to_notebook, _get_notebook_path, _NOTEBOOK_FILENAME
from ppke.config import Config, LLMConfig


# ── cheat command ──────────────────────────────────────────────────────────────


def test_cheat_displays_table():
    runner = CliRunner()
    result = runner.invoke(main, ["cheat"])
    assert result.exit_code == 0
    assert "PPKE Command Cheat Sheet" in result.output
    assert "ppke ingest" in result.output
    assert "ppke query" in result.output
    assert "ppke doctor" in result.output
    assert "ppke notebook" in result.output
    assert "ppke menu" in result.output
    assert "ppke tui" in result.output
    assert "ppke cheat" in result.output
    assert "Tip:" in result.output


def test_cheat_contains_all_commands():
    runner = CliRunner()
    result = runner.invoke(main, ["cheat"])
    assert result.exit_code == 0
    expected_commands = [
        "ppke init", "ppke ingest", "ppke parse", "ppke query",
        "ppke cross-query", "ppke re-read", "ppke config", "ppke list",
        "ppke stats", "ppke search", "ppke doctor", "ppke notebook",
        "ppke menu", "ppke tui", "ppke cheat",
    ]
    for cmd in expected_commands:
        assert cmd in result.output, f"Missing command: {cmd}"


# ── doctor command ─────────────────────────────────────────────────────────────


def test_doctor_all_ok(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    meta = {"title": "Test", "author": "Author", "verification_status": "COMPLETE"}
    (book_dir / "meta.yml").write_text(yaml.dump(meta))

    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.config.DEFAULT_CONFIG_PATH", tmp_path / "config.json"):
        # Create fake config file
        (tmp_path / "config.json").write_text("{}")
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="sk-test1234test"))
        mock_load.return_value = cfg
        result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0
    assert "OK" in result.output
    assert "API key set" in result.output


def test_doctor_missing_api_key(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path, llm=LLMConfig())
        mock_load.return_value = cfg
        result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0
    assert "API key missing" in result.output


def test_doctor_vault_missing(tmp_path):
    runner = CliRunner()
    missing_vault = tmp_path / "nonexistent"
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=missing_vault, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0
    assert "Vault directory not found" in result.output


def test_doctor_incomplete_book(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    meta = {"title": "Test", "author": "Author", "verification_status": "INCOMPLETE"}
    (book_dir / "meta.yml").write_text(yaml.dump(meta))

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0
    assert "Incomplete ingestion" in result.output


def test_doctor_pending_checkpoint(tmp_path):
    runner = CliRunner()
    (tmp_path / ".checkpoint_Book_Test_Author_2024.json").write_text("{}")

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0
    assert "Pending checkpoint" in result.output


def test_doctor_no_books(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0
    assert "No books ingested" in result.output


def test_doctor_book_no_meta(tmp_path):
    runner = CliRunner()
    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    # No meta.yml

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path, llm=LLMConfig(anthropic_api_key="key"))
        mock_load.return_value = cfg
        result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0
    assert "no meta.yml" in result.output


# ── notebook command ───────────────────────────────────────────────────────────


def test_notebook_no_file(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["notebook"])

    assert result.exit_code == 0
    assert "No research notebook found" in result.output


def test_notebook_view(tmp_path):
    runner = CliRunner()
    # Create a notebook file
    nb_path = tmp_path / _NOTEBOOK_FILENAME
    nb_path.write_text("# PPKE Research Notebook\n\n---\n\n## Entry\n\nContent\n")

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["notebook"])

    assert result.exit_code == 0
    assert "Research Notebook" in result.output


def test_notebook_clear(tmp_path):
    runner = CliRunner()
    nb_path = tmp_path / _NOTEBOOK_FILENAME
    nb_path.write_text("# content")

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["notebook", "--clear"])

    assert result.exit_code == 0
    assert "cleared" in result.output
    assert not nb_path.exists()


def test_notebook_clear_no_file(tmp_path):
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["notebook", "--clear"])

    assert result.exit_code == 0
    assert "No notebook to clear" in result.output


def test_notebook_tail(tmp_path):
    runner = CliRunner()
    nb_path = tmp_path / _NOTEBOOK_FILENAME
    entries = "# Header\n\n---\n\n## Entry 1\nContent1\n\n---\n\n## Entry 2\nContent2\n\n---\n\n## Entry 3\nContent3\n"
    nb_path.write_text(entries)

    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        result = runner.invoke(main, ["notebook", "--tail", "1"])

    assert result.exit_code == 0
    assert "Entry 3" in result.output
    assert "1 of 3" in result.output


def test_append_to_notebook_creates_file(tmp_path):
    _append_to_notebook(tmp_path, "What is Dasein?", "Being-there", book="Book_Test")
    nb_path = _get_notebook_path(tmp_path)
    assert nb_path.exists()
    content = nb_path.read_text()
    assert "Research Notebook" in content
    assert "What is Dasein?" in content
    assert "Being-there" in content
    assert "Book_Test" in content


def test_append_to_notebook_with_quotes(tmp_path):
    quotes = [
        {"paragraph_id": "{01}.p1", "quote": "Dasein is being-there"},
    ]
    _append_to_notebook(tmp_path, "Q?", "A.", quotes=quotes)
    content = _get_notebook_path(tmp_path).read_text()
    assert "{01}.p1" in content
    assert "Dasein is being-there" in content


def test_append_to_notebook_cross_query(tmp_path):
    _append_to_notebook(tmp_path, "How do they differ?", "They differ on X.")
    content = _get_notebook_path(tmp_path).read_text()
    assert "Cross-book query" in content


def test_append_to_notebook_appends(tmp_path):
    _append_to_notebook(tmp_path, "Q1?", "A1")
    _append_to_notebook(tmp_path, "Q2?", "A2")
    content = _get_notebook_path(tmp_path).read_text()
    assert "Q1?" in content
    assert "Q2?" in content


# ── menu command ───────────────────────────────────────────────────────────────


def test_menu_exit():
    runner = CliRunner()
    result = runner.invoke(main, ["menu"], input="0\n")
    assert result.exit_code == 0
    assert "Bye!" in result.output


def test_menu_invalid_choice():
    runner = CliRunner()
    result = runner.invoke(main, ["menu"], input="99\n")
    assert result.exit_code == 0
    assert "Invalid choice" in result.output


def test_menu_shows_actions():
    runner = CliRunner()
    result = runner.invoke(main, ["menu"], input="0\n")
    assert result.exit_code == 0
    assert "Ingest a book" in result.output
    assert "Query a single book" in result.output
    assert "Run doctor diagnostics" in result.output


def test_menu_list_books(tmp_path):
    """Menu option for 'list books' should execute without errors."""
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        # Select option 7 (List books), then confirm execution
        result = runner.invoke(main, ["menu"], input="7\ny\n")
    assert result.exit_code == 0
    assert "List books" in result.output


def test_menu_show_stats(tmp_path):
    """Menu option for 'stats' should execute without errors."""
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=tmp_path)
        mock_load.return_value = cfg
        # Select option 8 (Show statistics), then confirm
        result = runner.invoke(main, ["menu"], input="8\ny\n")
    assert result.exit_code == 0
    assert "Show statistics" in result.output


def test_menu_cheat_sheet():
    runner = CliRunner()
    # Select option 12 (Show cheat sheet), then confirm
    result = runner.invoke(main, ["menu"], input="12\ny\n")
    assert result.exit_code == 0
    assert "cheat sheet" in result.output.lower()


def test_menu_decline_execution():
    """Decline execution should not crash."""
    runner = CliRunner()
    with patch("ppke.config.Config.load") as mock_load:
        cfg = Config(vault_path=Path("/tmp"))
        mock_load.return_value = cfg
        # Select option 7, decline execution
        result = runner.invoke(main, ["menu"], input="7\nn\n")
    assert result.exit_code == 0


# ── tui module ─────────────────────────────────────────────────────────────────


def test_tui_list_books(tmp_path):
    from ppke.tui import _list_books

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    (book_dir / "meta.yml").write_text(
        yaml.dump({"title": "Test", "author": "Author"})
    )
    books = _list_books(tmp_path)
    assert len(books) == 1
    assert books[0]["title"] == "Test"
    assert books[0]["folder"] == "Book_Test_Author_2024"


def test_tui_list_books_empty(tmp_path):
    from ppke.tui import _list_books
    assert _list_books(tmp_path) == []


def test_tui_list_books_nonexistent(tmp_path):
    from ppke.tui import _list_books
    assert _list_books(tmp_path / "nonexistent") == []


def test_tui_quick_search(tmp_path):
    from ppke.tui import _quick_search

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    data = [
        {"paragraph_id": "{01}.p1", "original_text": "The concept of Dasein is central."},
        {"paragraph_id": "{01}.p2", "original_text": "Something else."},
    ]
    (book_dir / "extractions.json").write_text(json.dumps(data))

    hits = _quick_search(tmp_path, "Dasein")
    assert len(hits) == 1
    assert hits[0]["paragraph_id"] == "{01}.p1"
    assert "Dasein" in hits[0]["snippet"]


def test_tui_quick_search_no_results(tmp_path):
    from ppke.tui import _quick_search

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    data = [{"paragraph_id": "{01}.p1", "original_text": "Hello world."}]
    (book_dir / "extractions.json").write_text(json.dumps(data))

    hits = _quick_search(tmp_path, "Nonexistent")
    assert len(hits) == 0


def test_tui_quick_search_max_results(tmp_path):
    from ppke.tui import _quick_search

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    data = [
        {"paragraph_id": f"{{01}}.p{i}", "original_text": f"word {i}"}
        for i in range(1, 20)
    ]
    (book_dir / "extractions.json").write_text(json.dumps(data))

    hits = _quick_search(tmp_path, "word", max_results=3)
    assert len(hits) == 3


def test_tui_show_vault_stats(tmp_path):
    from ppke.tui import _show_vault_stats, _console

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    books = [{"title": "Test", "total_chapters": 3, "total_paragraphs": 10,
              "verification_status": "COMPLETE"}]

    console = _console()
    # Just ensure it doesn't crash
    _show_vault_stats(console, tmp_path, books)


def test_tui_show_book_detail(tmp_path):
    from ppke.tui import _show_book_detail, _console

    book_dir = tmp_path / "Book_Test_Author_2024"
    book_dir.mkdir()
    (book_dir / "meta.yml").write_text(
        yaml.dump({"title": "Test", "author": "Author", "verification_status": "COMPLETE"})
    )
    (book_dir / "03_Concept_Index.md").write_text("## Dasein\n\nDef\n## Freedom\n\nDef\n")

    book = {
        "folder": "Book_Test_Author_2024",
        "path": book_dir,
        "title": "Test",
        "author": "Author",
        "verification_status": "COMPLETE",
    }
    console = _console()
    _show_book_detail(console, book)


def test_tui_show_books_table(tmp_path):
    from ppke.tui import _show_books_table, _console

    books = [
        {"folder": "Book_A", "title": "Book A", "author": "A",
         "total_chapters": 5, "total_paragraphs": 50, "verification_status": "COMPLETE"},
        {"folder": "Book_B", "title": "Book B", "author": "B",
         "total_chapters": 3, "total_paragraphs": 20, "verification_status": "INCOMPLETE"},
    ]
    console = _console()
    _show_books_table(console, books)


def test_tui_dashboard_exit(tmp_path):
    """Dashboard should exit cleanly on choice 0."""
    from ppke.tui import run_dashboard

    cfg = Config(vault_path=tmp_path)
    with patch("click.prompt", return_value=0):
        run_dashboard(tmp_path, cfg)


def test_tui_dashboard_refresh(tmp_path):
    """Dashboard refresh + exit should work."""
    from ppke.tui import run_dashboard

    cfg = Config(vault_path=tmp_path)
    call_count = [0]

    def mock_prompt(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return 5  # Refresh
        return 0  # Exit

    with patch("click.prompt", side_effect=mock_prompt):
        run_dashboard(tmp_path, cfg)


def test_tui_command_launches():
    """ppke tui should invoke run_dashboard."""
    runner = CliRunner()
    with patch("ppke.tui.run_dashboard") as mock_run:
        with patch("ppke.config.Config.load") as mock_load:
            cfg = Config(vault_path=Path("/tmp"))
            mock_load.return_value = cfg
            result = runner.invoke(main, ["tui"])
    assert result.exit_code == 0
    mock_run.assert_called_once()
