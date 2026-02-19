"""CLI entry point for PPKE."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from ppke import __version__
from ppke.config import (
    Config,
    PROVIDER_DEFAULTS,
    PROVIDER_ENV_VARS,
    SUPPORTED_PROVIDERS,
    is_first_run,
    save_env_file,
)


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
        env_var = PROVIDER_ENV_VARS.get(provider_name, "API_KEY")
        click.echo(
            f"Error: No API key found for {provider_name}. "
            f"Set {env_var} environment variable.",
            err=True,
        )
        sys.exit(1)


def _safe_book_dir(vault_path: Path, book: str) -> Path:
    """Resolve book folder within vault, preventing path traversal.

    Ensures the resolved path is a direct child of vault_path (not a
    symlink escape or ``../`` traversal).  Exits with an error if the
    book name is not safe.
    """
    # Resolve vault_path to an absolute canonical path first.
    try:
        vault_abs = vault_path.resolve(strict=False)
    except Exception:
        vault_abs = vault_path.absolute()

    candidate = (vault_abs / book).resolve(strict=False)

    try:
        candidate.relative_to(vault_abs)
    except ValueError:
        click.echo(
            f"Error: Book name '{book}' is not a valid folder name inside the vault.",
            err=True,
        )
        sys.exit(1)

    return candidate


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.pass_context
def main(ctx):
    """PPKE - Personal Philosophical Knowledge Engine.

    A CLI tool for structured philosophical book analysis.
    """
    if ctx.invoked_subcommand is None:
        if is_first_run():
            click.echo("Welcome to PPKE! It looks like this is your first time.")
            click.echo("Running setup wizard...\n")
            ctx.invoke(init)
        else:
            click.echo(ctx.get_help())


# ── init command ──


@main.command()
def init():
    """First-time setup wizard.

    Walks you through configuring your LLM provider, API keys,
    and knowledge base location. Secrets are stored in ~/.ppke/.env
    (permissions 600) and never committed to git.

    Example:
        ppke init
    """
    click.echo("=" * 50)
    click.echo("  PPKE Setup Wizard")
    click.echo("=" * 50)
    click.echo()

    # 1. Choose provider
    click.echo("Supported providers: " + ", ".join(SUPPORTED_PROVIDERS))
    provider = click.prompt(
        "LLM provider",
        type=click.Choice(SUPPORTED_PROVIDERS, case_sensitive=False),
        default="anthropic",
    )

    # 2. Choose model
    default_model = PROVIDER_DEFAULTS[provider]
    click.echo(f"\nDefault model: {default_model}")
    model = click.prompt("Model name", default=default_model)

    # 3. API key for chosen provider
    env_vars: dict[str, str] = {}
    env_var_name = PROVIDER_ENV_VARS[provider]
    _PROVIDER_KEY_URLS = {
        "anthropic": "https://console.anthropic.com/settings/keys",
        "openai": "https://platform.openai.com/api-keys",
        "deepseek": "https://platform.deepseek.com/api_keys",
        "gemini": "https://aistudio.google.com/app/apikey",
        "openrouter": "https://openrouter.ai/keys",
    }
    click.echo(f"\nYou need a {provider} API key.")
    url = _PROVIDER_KEY_URLS.get(provider)
    if url:
        click.echo(f"Get one at: {url}")
    key = click.prompt(env_var_name, hide_input=True)
    env_vars[env_var_name] = key

    # 5. Vault path
    default_vault = str(Path.home() / "KnowledgeBase")
    click.echo(f"\nKnowledge base directory (default: {default_vault})")
    vault_path = click.prompt("Vault path", default=default_vault)

    # 6. Batch size
    batch_size = click.prompt(
        "\nParagraphs per LLM batch",
        type=click.IntRange(min=1),
        default=5,
    )

    # Save secrets to .env file
    click.echo("\nSaving API keys to ~/.ppke/.env ...")
    save_env_file(env_vars)

    # Save config
    click.echo("Saving configuration to ~/.ppke/config.json ...")
    cfg = Config(
        vault_path=Path(vault_path),
        llm=Config.load().llm,
    )
    cfg.llm.provider = provider
    cfg.llm.model = model
    cfg.llm.paragraphs_per_batch = batch_size
    cfg.save()

    # Create vault directory
    vault = Path(vault_path)
    vault.mkdir(parents=True, exist_ok=True)

    click.echo()
    click.echo("=" * 50)
    click.echo("  Setup complete!")
    click.echo("=" * 50)
    click.echo()
    click.echo("Your configuration:")
    click.echo(f"  Provider:    {provider}")
    click.echo(f"  Model:       {model}")
    click.echo(f"  Vault:       {vault_path}")
    click.echo(f"  Batch size:  {batch_size}")
    click.echo(f"  Secrets:     ~/.ppke/.env (chmod 600)")
    click.echo()
    click.echo("Next steps:")
    click.echo("  ppke ingest book.md --title 'Book Title' --author 'Author Name'")
    click.echo("  ppke config --show")
    click.echo("  ppke --help")


# ── ingest command ──


@main.command()
@click.argument("filepath", type=click.Path(exists=True, path_type=Path))
@click.option("--title", required=True, help="Book title")
@click.option("--author", required=True, help="Book author")
@click.option("--year", default=None, help="Publication year")
@click.option(
    "--provider",
    type=click.Choice(SUPPORTED_PROVIDERS),
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
@click.option("--batch-size", type=click.IntRange(min=1), default=None, help="Paragraphs per LLM batch (min 1)")
@click.option("--operator", default="", help="Human operator name for versioning")
@click.option("--double-pass", is_flag=True, help="Enable double-pass extraction")
@click.option("--resume", is_flag=True, help="Resume from last checkpoint if a previous run failed")
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
    resume: bool,
    verbose: bool,
):
    """Ingest a markdown book into the knowledge base.

    Runs the full pipeline: parse -> extract -> validate -> analyze -> write.
    Use --resume to continue from where a previous ingestion failed.

    Examples:
        ppke ingest book.md --title "Being and Time" --author "Heidegger" --year 1927
        ppke ingest book.md --title "Being and Time" --author "Heidegger" --resume
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
        resume=resume,
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
    type=click.Choice(SUPPORTED_PROVIDERS),
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

    book_dir = _safe_book_dir(config.vault_path, book)
    if not book_dir.exists():
        click.echo(f"Error: Book folder not found: {book_dir}", err=True)
        if config.vault_path.exists():
            click.echo("Available books:", err=True)
            for d in sorted(config.vault_path.iterdir()):
                if d.is_dir() and d.name.startswith("Book_"):
                    click.echo(f"  {d.name}", err=True)
        else:
            click.echo(f"Vault directory does not exist: {config.vault_path}", err=True)
        sys.exit(1)

    # Load analysis files
    import yaml
    from ppke.llm.client import LLMClient
    from ppke.llm.prompts import SINGLE_BOOK_QUERY_SYSTEM, SINGLE_BOOK_QUERY_USER

    meta_path = book_dir / "meta.yml"
    meta = (yaml.safe_load(meta_path.read_text()) or {}) if meta_path.exists() else {}

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
    type=click.Choice(SUPPORTED_PROVIDERS),
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


# ── re-read command ──


@main.command("re-read")
@click.option("--book", required=True, help="Book folder name")
@click.option(
    "--chapters",
    required=True,
    help="Comma-separated chapter numbers to re-scan (e.g. '1,3,5')",
)
@click.option(
    "--provider",
    type=click.Choice(SUPPORTED_PROVIDERS),
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
def re_read(
    book: str,
    chapters: str,
    provider: str | None,
    model: str | None,
    vault_path: Path | None,
    verbose: bool,
):
    """Interactive re-read: re-extract specific chapters from an ingested book.

    Re-parses the original source file, re-extracts the specified chapters,
    and updates all output files with the new results.

    Examples:
        ppke re-read --book "Book_Being_and_Time_Heidegger_1927" --chapters "1,3"
        ppke re-read --book "Book_Republic_Plato" --chapters "5"
    """
    _setup_logging(verbose)

    config = _load_config_with_overrides(provider, model, vault_path)
    _require_api_key(config)

    book_dir = _safe_book_dir(config.vault_path, book)
    if not book_dir.exists():
        click.echo(f"Error: Book folder not found: {book_dir}", err=True)
        sys.exit(1)

    # Parse chapter numbers
    try:
        chapter_numbers = [int(c.strip()) for c in chapters.split(",")]
    except ValueError:
        click.echo("Error: --chapters must be comma-separated integers.", err=True)
        sys.exit(1)

    click.echo(f"Re-reading chapters {chapter_numbers} from {book}")

    def progress_callback(stage: str, detail: str):
        click.echo(f"  [{stage}] {detail}")

    from ppke.pipeline.orchestrator import reread_chapters

    try:
        reread_chapters(
            book_dir=book_dir,
            chapter_numbers=chapter_numbers,
            config=config,
            progress_callback=progress_callback,
        )
        click.echo(f"\nRe-read complete! Updated files in: {book_dir}")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ── config command ──


@main.command()
@click.option(
    "--provider",
    type=click.Choice(SUPPORTED_PROVIDERS),
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
@click.option("--batch-size", type=click.IntRange(min=1), default=None, help="Paragraphs per LLM batch (min 1)")
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
        click.echo(f"Max para tokens: {cfg.llm.max_paragraph_tokens}")
        click.echo(f"Max workers:  {cfg.llm.max_workers}")
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


# ── list command ──


@main.command("list")
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path",
)
def list_books(vault_path: Path | None):
    """List all ingested books in the knowledge base.

    Shows title, author, year, chapters, paragraphs, and verification status.

    Example:
        ppke list
    """
    import yaml

    cfg = Config.load()
    vp = vault_path or cfg.vault_path

    if not vp.exists():
        click.echo(f"Vault not found: {vp}", err=True)
        sys.exit(1)

    book_dirs = sorted(
        d for d in vp.iterdir() if d.is_dir() and d.name.startswith("Book_")
    )
    if not book_dirs:
        click.echo("No books ingested yet.")
        click.echo(f"Vault: {vp}")
        return

    click.echo(f"{'#':<4} {'Title':<35} {'Author':<20} {'Year':<6} {'Ch':<5} {'Para':<6} {'Status'}")
    click.echo("-" * 100)

    for i, bd in enumerate(book_dirs, 1):
        meta_path = bd / "meta.yml"
        if meta_path.exists():
            meta = yaml.safe_load(meta_path.read_text()) or {}
            title = meta.get("title", "?")
            author = meta.get("author", "?")
            year = str(meta.get("year", ""))
            chapters = str(meta.get("total_chapters", "?"))
            paragraphs = str(meta.get("total_paragraphs", "?"))
            status = meta.get("verification_status", "?")
        else:
            title = bd.name
            author = year = "?"
            chapters = paragraphs = status = "?"

        # Truncate long titles/authors
        title_disp = (title[:32] + "...") if len(title) > 35 else title
        author_disp = (author[:17] + "...") if len(author) > 20 else author
        click.echo(
            f"{i:<4} {title_disp:<35} {author_disp:<20} {year:<6} "
            f"{chapters:<5} {paragraphs:<6} {status}"
        )

    click.echo(f"\nTotal: {len(book_dirs)} book(s) in {vp}")


# ── stats command ──


@main.command()
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path",
)
def stats(vault_path: Path | None):
    """Show vault-wide statistics.

    Displays total books, chapters, paragraphs, concepts, patterns,
    and overall coverage status.

    Example:
        ppke stats
    """
    import re

    import yaml

    cfg = Config.load()
    vp = vault_path or cfg.vault_path

    if not vp.exists():
        click.echo(f"Vault not found: {vp}", err=True)
        sys.exit(1)

    book_dirs = sorted(
        d for d in vp.iterdir() if d.is_dir() and d.name.startswith("Book_")
    )

    total_books = len(book_dirs)
    total_chapters = 0
    total_paragraphs = 0
    total_processed = 0
    total_concepts = 0
    total_patterns = 0
    complete_count = 0
    incomplete_count = 0

    for bd in book_dirs:
        meta_path = bd / "meta.yml"
        if meta_path.exists():
            meta = yaml.safe_load(meta_path.read_text()) or {}
            total_chapters += meta.get("total_chapters", 0)
            total_paragraphs += meta.get("total_paragraphs", 0)
            if meta.get("verification_status") == "COMPLETE":
                complete_count += 1
            else:
                incomplete_count += 1

        # Count processed paragraphs from coverage report
        report_path = bd / "05_Coverage_Report.md"
        if report_path.exists():
            content = report_path.read_text()
            # Primary: bold-formatted markdown  "**processed_paragraphs_count:** 42"
            match = re.search(r"processed_paragraphs_count:\*\*\s*(\d+)", content)
            if not match:
                # Fallback: YAML-style  "processed_paragraphs_count: 42"
                # Anchored to end-of-line so we don't match stray numbers later.
                match = re.search(r"processed_paragraphs_count[:\s]+(\d+)\s*$",
                                  content, re.MULTILINE)
            if match:
                total_processed += int(match.group(1))

        # Count concepts
        concept_path = bd / "03_Concept_Index.md"
        if concept_path.exists():
            total_concepts += len(
                re.findall(r"^## .+$", concept_path.read_text(), re.MULTILINE)
            )

        # Count patterns
        pattern_path = bd / "06_Patterns.md"
        if pattern_path.exists():
            total_patterns += len(
                re.findall(r"^### \d+\.", pattern_path.read_text(), re.MULTILINE)
            )

    click.echo("=" * 40)
    click.echo("  PPKE Vault Statistics")
    click.echo("=" * 40)
    click.echo()
    click.echo(f"  Books:           {total_books}")
    click.echo(f"  Chapters:        {total_chapters}")
    click.echo(f"  Paragraphs:      {total_paragraphs}")
    click.echo(f"  Processed:       {total_processed}")
    click.echo(f"  Concepts:        {total_concepts}")
    click.echo(f"  Patterns:        {total_patterns}")
    click.echo()
    click.echo(f"  Complete:        {complete_count}")
    click.echo(f"  Incomplete:      {incomplete_count}")
    coverage_pct = (
        f"{total_processed / total_paragraphs * 100:.1f}%"
        if total_paragraphs > 0
        else "N/A"
    )
    click.echo(f"  Coverage:        {coverage_pct}")
    click.echo()
    click.echo(f"  Vault:           {vp}")

    # Check for pending checkpoints
    checkpoints = list(vp.glob(".checkpoint_*.json"))
    if checkpoints:
        click.echo()
        click.echo(f"  Pending checkpoints: {len(checkpoints)}")
        for cp in checkpoints:
            book_name = cp.stem.replace(".checkpoint_", "")
            click.echo(f"    - {book_name} (use --resume to continue)")


# ── search command ──


@main.command()
@click.argument("text")
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path",
)
@click.option("--book", default=None, help="Limit search to a specific book folder")
@click.option(
    "--max-results", type=int, default=20, help="Maximum results to show (default: 20)"
)
def search(text: str, vault_path: Path | None, book: str | None, max_results: int):
    """Search across all extracted paragraphs (no LLM, local text search).

    Searches the original text and extracted topic sentences in all ingested
    books. Case-insensitive.

    Examples:
        ppke search "Dasein"
        ppke search "free will" --book "Book_Being_and_Time_Heidegger_1927"
        ppke search "dialectic" --max-results 50
    """
    import json as _json

    cfg = Config.load()
    vp = vault_path or cfg.vault_path

    if not vp.exists():
        click.echo(f"Vault not found: {vp}", err=True)
        sys.exit(1)

    # Determine which book dirs to search
    if book:
        book_dir = _safe_book_dir(vp, book)
        if not book_dir.exists():
            click.echo(f"Error: Book folder not found: {book_dir}", err=True)
            sys.exit(1)
        search_dirs = [book_dir]
    else:
        search_dirs = sorted(
            d for d in vp.iterdir() if d.is_dir() and d.name.startswith("Book_")
        )

    if not search_dirs:
        click.echo("No books found to search.")
        return

    query_lower = text.lower()
    hits: list[tuple[str, str, str, str]] = []  # (book, pid, field, snippet)

    for bd in search_dirs:
        ext_path = bd / "extractions.json"
        if not ext_path.exists():
            continue
        try:
            data = _json.loads(ext_path.read_text())
        except Exception:
            continue

        for item in data:
            pid = item.get("paragraph_id", "?")
            original = item.get("original_text", "")
            topic = item.get("topic_sentence", "")
            claims = " ".join(item.get("explicit_claims", []))
            concepts = " ".join(item.get("defined_concepts", []))

            # Search across multiple fields
            for field_name, field_text in [
                ("text", original),
                ("topic", topic),
                ("claim", claims),
                ("concept", concepts),
            ]:
                field_lower = field_text.lower()
                if query_lower in field_lower:
                    # Build a snippet around the match (use cached lowercase)
                    idx = field_lower.index(query_lower)
                    start = max(0, idx - 40)
                    end = min(len(field_text), idx + len(text) + 40)
                    snippet = field_text[start:end]
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(field_text):
                        snippet = snippet + "..."
                    hits.append((bd.name, pid, field_name, snippet))
                    break  # One hit per paragraph

            if len(hits) >= max_results:
                break
        if len(hits) >= max_results:
            break

    if not hits:
        click.echo(f'No results found for "{text}".')
        return

    click.echo(f'Search results for "{text}" ({len(hits)} hits):\n')
    for book_name, pid, field, snippet in hits:
        click.echo(f"  [{book_name}] {pid} ({field})")
        click.echo(f"    {snippet}")
        click.echo()

    if len(hits) >= max_results:
        click.echo(f"(showing first {max_results} results, use --max-results for more)")


if __name__ == "__main__":
    main()
