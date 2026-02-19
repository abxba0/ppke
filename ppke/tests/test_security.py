"""Security tests: path traversal protection, input validation."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ppke.cli import _safe_book_dir, main


# ── _safe_book_dir: path traversal prevention ──


def test_safe_book_dir_valid(tmp_path):
    """A plain book folder name should resolve inside the vault."""
    book_dir = _safe_book_dir(tmp_path, "Book_Test_Author_2024")
    assert str(book_dir).startswith(str(tmp_path.resolve()))


def test_safe_book_dir_traversal_blocked(tmp_path):
    """../  traversal must be rejected with sys.exit(1)."""
    runner = CliRunner()
    # Directly test _safe_book_dir raises SystemExit via click.echo + sys.exit
    with pytest.raises(SystemExit) as exc_info:
        _safe_book_dir(tmp_path, "../../../etc")
    assert exc_info.value.code == 1


def test_safe_book_dir_absolute_path_blocked(tmp_path):
    """An absolute path outside the vault must be rejected."""
    with pytest.raises(SystemExit) as exc_info:
        _safe_book_dir(tmp_path, "/etc/passwd")
    assert exc_info.value.code == 1


def test_safe_book_dir_double_dot_in_name_blocked(tmp_path):
    """Names containing .. segments must not escape the vault."""
    with pytest.raises(SystemExit) as exc_info:
        _safe_book_dir(tmp_path, "Book/../../secret")
    assert exc_info.value.code == 1


def test_safe_book_dir_normal_subfolder_allowed(tmp_path):
    """A normal single-level folder name should be allowed (even if it doesn't exist yet)."""
    result = _safe_book_dir(tmp_path, "Book_Being_and_Time_Heidegger_1927")
    assert result == (tmp_path.resolve() / "Book_Being_and_Time_Heidegger_1927")


# ── CLI: batch-size validation ──


def test_ingest_rejects_batch_size_zero(tmp_path):
    """--batch-size 0 must be rejected by the CLI."""
    runner = CliRunner()
    # Create a minimal markdown file
    md = tmp_path / "book.md"
    md.write_text("# Chapter 1\n\nHello world.")

    result = runner.invoke(
        main,
        [
            "ingest",
            str(md),
            "--title", "Test",
            "--author", "Author",
            "--batch-size", "0",
        ],
    )
    assert result.exit_code != 0
    assert "invalid" in result.output.lower() or "error" in result.output.lower() or result.exit_code == 2


def test_ingest_rejects_batch_size_negative(tmp_path):
    """--batch-size -1 must be rejected by the CLI."""
    runner = CliRunner()
    md = tmp_path / "book.md"
    md.write_text("# Chapter 1\n\nHello world.")

    result = runner.invoke(
        main,
        [
            "ingest",
            str(md),
            "--title", "Test",
            "--author", "Author",
            "--batch-size", "-1",
        ],
    )
    assert result.exit_code != 0


def test_config_rejects_batch_size_zero():
    """ppke config --batch-size 0 must be rejected."""
    runner = CliRunner()
    result = runner.invoke(main, ["config", "--batch-size", "0"])
    assert result.exit_code != 0


def test_config_accepts_batch_size_one():
    """ppke config --batch-size 1 must be accepted (min valid value)."""
    runner = CliRunner()
    # We only check Click validation passes; actual config write may fail in test env
    # Exit code 0 means Click accepted the argument
    with patch("ppke.config.Config.load") as mock_load, \
         patch("ppke.config.Config.save"):
        from ppke.config import Config, LLMConfig
        cfg = Config(llm=LLMConfig())
        mock_load.return_value = cfg
        result = runner.invoke(main, ["config", "--batch-size", "1"])
    # Should NOT be exit code 2 (Click usage error)
    assert result.exit_code != 2


# ── source_path validation in reread_chapters ──


def test_reread_rejects_nonexistent_source(tmp_path):
    """reread_chapters must raise FileNotFoundError for missing source files."""
    from ppke.pipeline.orchestrator import reread_chapters
    from ppke.config import Config

    book_dir = tmp_path / "Book_Test"
    book_dir.mkdir()

    # meta.yml pointing to a non-existent file
    import yaml
    meta = {
        "title": "Test",
        "author": "Author",
        "source_path": str(tmp_path / "nonexistent.md"),
    }
    (book_dir / "meta.yml").write_text(yaml.dump(meta))

    config = Config(vault_path=tmp_path)
    with pytest.raises(FileNotFoundError, match="Source file not found"):
        reread_chapters(
            book_dir=book_dir,
            chapter_numbers=[1],
            config=config,
        )


def test_reread_rejects_directory_as_source(tmp_path):
    """reread_chapters must raise FileNotFoundError if source_path is a directory."""
    from ppke.pipeline.orchestrator import reread_chapters
    from ppke.config import Config

    book_dir = tmp_path / "Book_Test"
    book_dir.mkdir()

    # A directory, not a file
    dir_path = tmp_path / "not_a_file"
    dir_path.mkdir()

    import yaml
    meta = {
        "title": "Test",
        "author": "Author",
        "source_path": str(dir_path),
    }
    (book_dir / "meta.yml").write_text(yaml.dump(meta))

    config = Config(vault_path=tmp_path)
    with pytest.raises(FileNotFoundError, match="not a regular file"):
        reread_chapters(
            book_dir=book_dir,
            chapter_numbers=[1],
            config=config,
        )
