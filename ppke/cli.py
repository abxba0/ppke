"""CLI entry point for PPKE."""

from __future__ import annotations

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


def _load_config_with_overrides(
    provider: str | None = None,
    model: str | None = None,
    vault_path: Path | None = None,
    batch_size: int | None = None,
) -> Config:
    """Load config and apply CLI overrides."""
    config = Config.load()
    if provider:
        config.llm.provider = provider
    if model:
        config.llm.model = model
    if vault_path:
        config.vault_path = vault_path
    if batch_size:
        config.llm.paragraphs_per_batch = batch_size
    return config


def _require_api_key(config: Config):
    """Exit with error if API key is missing."""
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


@click.group()
@click.version_option(version=__version__)
def main():
    """PPKE - Personal Philosophical Knowledge Engine.

    A CLI tool for structured philosophical book analysis.
    """
    pass


# ── ingest command ──


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
@click.option("--operator", default="", help="Human operator name for versioning")
@click.option("--double-pass", is_flag=True, help="Enable double-pass extraction")
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
    operator: str,
    double_pass: bool,
    verbose: bool,
):
    """Ingest a markdown book into the knowledge base.

    Runs the full pipeline: parse -> extract -> validate -> analyze -> write.

    Example:
        ppke ingest book.md --title "Being and Time" --author "Heidegger" --year 1927
    """
    _setup_logging(verbose)

    config = _load_config_with_overrides(provider, model, vault_path, batch_size)
    if double_pass:
        config.double_pass = True
    _require_api_key(config)

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

    book_dir = ingest_book(
        book, config,
        progress_callback=progress_callback,
        human_operator=operator,
    )

    click.echo(f"\nDone! Output written to: {book_dir}")


# ── parse command ──


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


# ── query command (single book) ──


@main.command()
@click.option("--book", required=True, help="Book folder name (e.g. Book_Title_Author_YYYY)")
@click.option("--question", required=True, help="Question to answer from the book")
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
    help="Vault path",
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def query(
    book: str,
    question: str,
    provider: str | None,
    model: str | None,
    vault_path: Path | None,
    verbose: bool,
):
    """Query a single encoded book.

    Retrieves relevant paragraphs, reconstructs logical chains,
    and provides a structured answer with verbatim evidence.

    Example:
        ppke query --book "Book_Being_and_Time_Heidegger_1927" \\
                   --question "What is Dasein?"
    """
    _setup_logging(verbose)

    config = _load_config_with_overrides(provider, model, vault_path)
    _require_api_key(config)

    book_dir = config.vault_path / book
    if not book_dir.exists():
        click.echo(f"Error: Book folder not found: {book_dir}", err=True)
        click.echo("Available books:", err=True)
        for d in sorted(config.vault_path.iterdir()):
            if d.is_dir() and d.name.startswith("Book_"):
                click.echo(f"  {d.name}", err=True)
        sys.exit(1)

    # Load analysis files
    import yaml
    from ppke.llm.client import LLMClient
    from ppke.llm.prompts import SINGLE_BOOK_QUERY_SYSTEM, SINGLE_BOOK_QUERY_USER

    meta_path = book_dir / "meta.yml"
    meta = yaml.safe_load(meta_path.read_text()) if meta_path.exists() else {}

    book_title = meta.get("title", "Unknown")
    author_name = meta.get("author", "Unknown")

    raw_path = book_dir / "01_Raw_Structure.md"
    logical_path = book_dir / "02_Logical_Map.md"
    concept_path = book_dir / "03_Concept_Index.md"

    raw_structure = raw_path.read_text() if raw_path.exists() else "N/A"
    logical_map = logical_path.read_text() if logical_path.exists() else "N/A"
    concept_index = concept_path.read_text() if concept_path.exists() else "N/A"

    click.echo(f"Querying: {book_title} by {author_name}")
    click.echo(f"Question: {question}")
    click.echo()

    client = LLMClient(config.llm)
    user_prompt = SINGLE_BOOK_QUERY_USER.format(
        book_title=book_title,
        author=author_name,
        question=question,
        raw_structure=raw_structure,
        logical_map=logical_map,
        concept_index=concept_index,
    )

    try:
        result = client.complete_json(SINGLE_BOOK_QUERY_SYSTEM, user_prompt)

        click.echo("## Answer")
        click.echo(result.get("answer", "No answer generated."))
        click.echo()

        quotes = result.get("verbatim_quotes", [])
        if quotes:
            click.echo("## Evidence")
            for q in quotes:
                click.echo(f"  [{q.get('paragraph_id', '?')}] \"{q.get('quote', '')}\"")
            click.echo()

        chain = result.get("logical_chain", [])
        if chain:
            click.echo("## Logical Chain")
            for step in chain:
                inference = " [INFERENCE]" if step.get("is_inference") else ""
                click.echo(
                    f"  {step.get('step', '?')}. {step.get('claim', '')}{inference} "
                    f"({step.get('paragraph_id', '?')})"
                )
            click.echo()

        click.echo(f"Confidence: {result.get('confidence', 'unknown')}")

    except Exception as e:
        click.echo(f"Error: Query failed: {e}", err=True)
        sys.exit(1)


# ── cross-query command ──


@main.command("cross-query")
@click.option("--question", required=True, help="Question to answer across books")
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
    help="Vault path",
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def cross_query(
    question: str,
    provider: str | None,
    model: str | None,
    vault_path: Path | None,
    verbose: bool,
):
    """Query across all encoded books.

    Compares concept definitions, argument structures, and author models
    across the entire knowledge base.

    Example:
        ppke cross-query --question "How do these authors differ on free will?"
    """
    _setup_logging(verbose)

    config = _load_config_with_overrides(provider, model, vault_path)
    _require_api_key(config)

    from ppke.pipeline.synthesizer import cross_book_synthesis, discover_books

    books = discover_books(config.vault_path)
    if len(books) < 2:
        click.echo(
            f"Error: Need at least 2 encoded books. Found {len(books)}.",
            err=True,
        )
        sys.exit(1)

    click.echo(f"Cross-querying {len(books)} books:")
    for b in books:
        click.echo(f"  - {b['title']} by {b['author']} ({b['folder']})")
    click.echo(f"Question: {question}")
    click.echo()

    from ppke.llm.client import LLMClient

    client = LLMClient(config.llm)
    result = cross_book_synthesis(client, config.vault_path, question)

    if "error" in result:
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    # Display comparisons
    comparisons = result.get("comparisons", [])
    if comparisons:
        click.echo("## Comparisons")
        for comp in comparisons:
            click.echo(f"\n### {comp.get('dimension', 'Unknown')}")
            click.echo(comp.get("description", ""))
            per_book = comp.get("per_book", [])
            for pb in per_book:
                click.echo(f"  [{pb.get('book_folder', '?')}] {pb.get('position', '')}")
            tensions = comp.get("tensions", [])
            if tensions:
                click.echo("  Tensions:")
                for t in tensions:
                    click.echo(f"    - {t}")
        click.echo()

    # Display cross-links
    links = result.get("cross_links", [])
    if links:
        click.echo("## Cross-Links")
        for link in links:
            click.echo(
                f"  {link.get('concept', '?')}: "
                f"{link.get('relationship', '?')} across "
                f"{', '.join(link.get('books', []))}"
            )
            click.echo(f"    {link.get('description', '')}")
        click.echo()

    overall = result.get("overall_synthesis", "")
    if overall:
        click.echo("## Synthesis")
        click.echo(overall)


# ── config command ──


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
        click.echo(f"Double pass:  {cfg.double_pass}")
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
