"""CLI entry point for PPKE."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from ppke import __version__
from ppke.config import Config


def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(version=__version__)
def main():
    """PPKE - Personal Philosophical Knowledge Engine.

    A CLI tool for structured philosophical book analysis.
    """
    pass


@main.command()
@click.argument("filepath", type=click.Path(exists=True, path_type=Path))
@click.option("--title", required=True, help="Book title")
@click.option("--author", required=True, help="Book author")
@click.option("--year", default=None, help="Publication year")
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai"]),
    default=None,
    help="LLM provider (overrides config)",
)
@click.option("--model", default=None, help="Model name (overrides config)")
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output vault path (overrides config)",
)
@click.option("--batch-size", type=int, default=None, help="Paragraphs per LLM batch")
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def ingest(
    filepath: Path,
    title: str,
    author: str,
    year: str | None,
    provider: str | None,
    model: str | None,
    vault_path: Path | None,
    batch_size: int | None,
    verbose: bool,
):
    """Ingest a markdown book into the knowledge base.

    Runs the full pipeline: parse → extract → validate → analyze → write.

    Example:
        ppke ingest book.md --title "Being and Time" --author "Heidegger" --year 1927
    """
    _setup_logging(verbose)

    config = Config.load()

    # Apply CLI overrides
    if provider:
        config.llm.provider = provider
    if model:
        config.llm.model = model
    if vault_path:
        config.vault_path = vault_path
    if batch_size:
        config.llm.paragraphs_per_batch = batch_size

    # Validate API key
    if not config.llm.active_api_key:
        provider_name = config.llm.provider
        env_var = (
            "ANTHROPIC_API_KEY" if provider_name == "anthropic" else "OPENAI_API_KEY"
        )
        click.echo(
            f"Error: No API key found for {provider_name}. "
            f"Set {env_var} environment variable.",
            err=True,
        )
        sys.exit(1)

    # Parse the book
    click.echo(f"Parsing {filepath}...")
    from ppke.parser.markdown import parse_markdown_book

    book = parse_markdown_book(filepath, title, author, year)
    click.echo(
        f"Parsed: {len(book.chapters)} chapters, {book.total_paragraphs} paragraphs"
    )

    # Run pipeline
    click.echo("Starting ingestion pipeline...")

    def progress_callback(stage: str, detail: str):
        click.echo(f"  [{stage}] {detail}")

    from ppke.pipeline.orchestrator import ingest_book

    book_dir = ingest_book(book, config, progress_callback=progress_callback)

    click.echo(f"\nDone! Output written to: {book_dir}")


@main.command()
@click.argument("filepath", type=click.Path(exists=True, path_type=Path))
@click.option("--title", default="Untitled", help="Book title for display")
@click.option("--author", default="Unknown", help="Book author for display")
def parse(filepath: Path, title: str, author: str):
    """Parse a markdown book and show its structure (no LLM calls).

    Useful for verifying chapter/paragraph detection before ingestion.

    Example:
        ppke parse book.md --title "Being and Time" --author "Heidegger"
    """
    from ppke.parser.markdown import parse_markdown_book

    book = parse_markdown_book(filepath, title, author)

    click.echo(f"Book: {book.title} by {book.author}")
    click.echo(f"Chapters: {len(book.chapters)}")
    click.echo(f"Total paragraphs: {book.total_paragraphs}")
    click.echo()

    for chapter in book.chapters:
        click.echo(f"  Chapter {chapter.number:02d}: {chapter.title}")
        click.echo(f"    Paragraphs: {chapter.paragraph_count}")
        if chapter.paragraphs:
            first = chapter.paragraphs[0]
            preview = first.text[:80] + "..." if len(first.text) > 80 else first.text
            click.echo(f"    First: [{first.paragraph_id}] {preview}")
        click.echo()


@main.command()
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai"]),
    default=None,
    help="LLM provider",
)
@click.option("--model", default=None, help="Model name")
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output vault path",
)
@click.option("--batch-size", type=int, default=None, help="Paragraphs per LLM batch")
@click.option("--show", is_flag=True, help="Show current config")
def config(
    provider: str | None,
    model: str | None,
    vault_path: Path | None,
    batch_size: int | None,
    show: bool,
):
    """View or update PPKE configuration.

    Examples:
        ppke config --show
        ppke config --provider anthropic --model claude-sonnet-4-20250514
        ppke config --vault-path ~/my-vault/KnowledgeBase
    """
    cfg = Config.load()

    if show or (not provider and not model and not vault_path and not batch_size):
        click.echo(f"Provider:     {cfg.llm.provider}")
        click.echo(f"Model:        {cfg.llm.model}")
        click.echo(f"Vault path:   {cfg.vault_path}")
        click.echo(f"Batch size:   {cfg.llm.paragraphs_per_batch}")
        click.echo(f"Selective:    {cfg.selective_depth}")
        click.echo(f"API key set:  {'yes' if cfg.llm.active_api_key else 'no'}")
        return

    if provider:
        cfg.llm.provider = provider
    if model:
        cfg.llm.model = model
    if vault_path:
        cfg.vault_path = vault_path
    if batch_size:
        cfg.llm.paragraphs_per_batch = batch_size

    cfg.save()
    click.echo("Configuration saved.")


if __name__ == "__main__":
    main()
