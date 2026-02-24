"""CLI entry point for PPKE."""

from __future__ import annotations

import logging
import sys
from io import StringIO as _SIO
from pathlib import Path

import click
from rich.console import Console as _RichConsole
from rich.markup import escape as _escape
from rich.panel import Panel as _Panel
from rich.rule import Rule as _Rule
from rich.table import Table as _Table
from rich.text import Text as _Text

from ppke import __version__
from ppke.config import (
    Config,
    PROVIDER_DEFAULTS,
    PROVIDER_ENV_VARS,
    SUPPORTED_PROVIDERS,
    is_first_run,
    save_env_file,
)

# URLs where users can obtain API keys for each provider
_PROVIDER_KEY_URLS: dict[str, str] = {
    "anthropic": "https://console.anthropic.com/settings/keys",
    "openai": "https://platform.openai.com/api-keys",
    "deepseek": "https://platform.deepseek.com/api_keys",
    "gemini": "https://aistudio.google.com/app/apikey",
    "openrouter": "https://openrouter.ai/keys",
}


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


def _render(renderable, width: int = 110) -> str:
    """Render a Rich renderable to a plain/colored string for click.echo."""
    is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    buf = _SIO()
    c = _RichConsole(file=buf, no_color=not is_tty, width=width, highlight=False)
    c.print(renderable)
    return buf.getvalue().rstrip("\n")


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


_BUILTIN_DOMAINS = ["philosophy", "science", "legal"]
_DOMAIN_DESCRIPTIONS = {
    "philosophy": "Argument mapping, concept tracking, logical architecture",
    "science": "Methodology analysis, evidence mapping, findings synthesis",
    "legal": "Case law analysis, statutory interpretation, legal reasoning",
    "custom": "Install your own template with: ppke template install <source>",
}


@main.command()
def init():
    """First-time setup wizard.

    Walks you through configuring your LLM provider, API keys,
    knowledge base location, and default domain template. Secrets are
    stored in ~/.ppke/.env (permissions 600) and never committed to git.

    Example:
        ppke init
    """
    click.echo(_render(_Rule("[bold blue]PPKE Setup Wizard[/bold blue]")))
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
    click.echo(f"\nYou need a {provider} API key.")
    url = _PROVIDER_KEY_URLS.get(provider)
    if url:
        click.echo(f"Get one at: {url}")
    key = click.prompt(env_var_name, hide_input=True)
    env_vars[env_var_name] = key

    # 4. Vault path
    default_vault = str(Path.home() / "KnowledgeBase")
    click.echo(f"\nKnowledge base directory (default: {default_vault})")
    vault_path = click.prompt("Vault path", default=default_vault)

    # 5. Batch size
    batch_size = click.prompt(
        "\nParagraphs per LLM batch",
        type=click.IntRange(min=1),
        default=5,
    )

    # 6. Domain / template selection
    click.echo("\nAvailable domain templates:")
    for name, desc in _DOMAIN_DESCRIPTIONS.items():
        marker = " (built-in)" if name in _BUILTIN_DOMAINS else ""
        click.echo(f"  {name}{marker}: {desc}")
    domain_choices = _BUILTIN_DOMAINS + ["custom"]
    domain = click.prompt(
        "\nDefault domain template",
        type=click.Choice(domain_choices, case_sensitive=False),
        default="philosophy",
    )

    # For custom domains: ask for the name and remind user to install it
    if domain == "custom":
        custom_name = click.prompt(
            "Custom domain name (the template you plan to install)",
            default="custom",
        )
        domain = custom_name
        click.echo(
            f"\nNote: '{domain}' is not a built-in template. Install it before ingesting:\n"
            "  ppke template install https://github.com/<user>/ppke-template-<name>\n"
            "  ppke template install ./path/to/template/"
        )

    # 7. Vector search
    click.echo(
        "\nVector search (ChromaDB) enables fast semantic lookup over all extractions."
        "\nRequires: pip install 'ppke[vector]'"
    )
    enable_vector_search = click.confirm("Enable vector search?", default=True)

    # 8. Knowledge graph
    click.echo(
        "\nKnowledge graph (NetworkX) enables concept-level graph traversal and cross-book reasoning."
        "\nRequires: pip install networkx  (or pip install 'ppke[graph]')"
    )
    enable_knowledge_graph = click.confirm("Enable knowledge graph?", default=True)

    # 9. Async ingest
    click.echo(
        "\nAsync ingestion runs LLM calls, disk I/O, and analysis stages concurrently"
        "\nfor maximum throughput on large books. Uses asyncio under the hood."
    )
    async_ingest = click.confirm("Enable async ingestion?", default=False)

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
    cfg.default_domain = domain
    cfg.enable_vector_search = enable_vector_search
    cfg.enable_knowledge_graph = enable_knowledge_graph
    cfg.async_ingest = async_ingest
    cfg.save()

    # Create vault directory
    vault = Path(vault_path)
    vault.mkdir(parents=True, exist_ok=True)

    cfg_table = _Table(show_header=False, box=None, padding=(0, 1))
    cfg_table.add_column("Key", style="bold cyan")
    cfg_table.add_column("Value")
    cfg_table.add_row("Provider:", provider)
    cfg_table.add_row("Model:", model)
    cfg_table.add_row("Vault:", vault_path)
    cfg_table.add_row("Batch size:", str(batch_size))
    cfg_table.add_row("Default domain:", domain)
    cfg_table.add_row("Vector search:", "enabled" if enable_vector_search else "disabled")
    cfg_table.add_row("Knowledge graph:", "enabled" if enable_knowledge_graph else "disabled")
    cfg_table.add_row("Async ingest:", "enabled" if async_ingest else "disabled (sync)")
    cfg_table.add_row("Secrets:", "~/.ppke/.env (chmod 600)")
    click.echo()
    click.echo(_render(_Panel(cfg_table, title="[bold green]Setup complete![/bold green]", border_style="green")))
    click.echo()
    click.echo(_render(_Rule("Next steps")))
    click.echo(f"  ppke ingest book.md --title 'Book Title' --author 'Author Name' --domain {domain}")
    click.echo("  ppke list-domains")
    click.echo("  ppke config --show")
    click.echo("  ppke --help")


# ── list-domains command ──


@main.command("list-domains")
def list_domains():
    """List all available domain templates.

    Shows both official (Tier 1) and custom (Tier 2) domain templates
    with their versions and descriptions.

    Example:
        ppke list-domains
    """
    from ppke.templates import list_templates

    console = _RichConsole()

    try:
        templates = list_templates()

        if not templates:
            console.print("[yellow]No domain templates found.[/yellow]")
            console.print("\nTemplates should be located in:")
            console.print("  - Official: ppke/templates/official/")
            console.print("  - Custom: ~/.ppke/plugins/")
            return

        console.print("\n[bold cyan]Available Domain Templates[/bold cyan]\n")

        # Group by tier
        official = [(name, tier, desc) for name, tier, desc in templates if tier == 'official']
        custom = [(name, tier, desc) for name, tier, desc in templates if tier == 'custom']
        errors = [(name, tier, desc) for name, tier, desc in templates if tier == 'error']

        # Display official templates
        if official:
            console.print("[bold green]Official Templates (Tier 1)[/bold green]")
            for name, tier, desc in official:
                console.print(f"  [cyan]{name:20s}[/cyan] {desc}")
            console.print()

        # Display custom templates
        if custom:
            console.print("[bold yellow]Custom Templates (Tier 2)[/bold yellow]")
            for name, tier, desc in custom:
                console.print(f"  [yellow]{name:20s}[/yellow] {desc}")
            console.print()

        # Display errors
        if errors:
            console.print("[bold red]Failed to Load[/bold red]")
            for name, tier, desc in errors:
                console.print(f"  [red]{name:20s}[/red] {desc}")
            console.print()

        console.print(f"[dim]Total: {len(templates)} template(s)[/dim]")
        console.print("\n[dim]Usage: ppke ingest book.md --domain <name> ...[/dim]\n")

    except Exception as e:
        console.print(f"[red]Error listing templates: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


# ── ingest command ──


@main.command()
@click.argument("filepath", type=click.Path(exists=True, path_type=Path))
@click.option("--title", required=True, help="Book title")
@click.option("--author", required=True, help="Book author")
@click.option("--year", default=None, help="Publication year")
@click.option("--domain", default=None, help="Domain template (overrides config default_domain)")
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
    domain: str | None,
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
        ppke ingest book.md --title "Being and Time" --author "Heidegger" --domain science
        ppke ingest book.md --title "Being and Time" --author "Heidegger" --resume
    """
    _setup_logging(verbose)

    config = _load_config_with_overrides(provider, model, vault_path, batch_size)
    if double_pass:
        config.double_pass = True
    # Resolve domain: CLI flag > config default_domain > "philosophy"
    domain = domain or config.default_domain or "philosophy"
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
        stage_t = _Text(f"[{stage}]", style="bold cyan")
        line = _Text.assemble(stage_t, " ", detail)
        click.echo("  " + _render(line))

    from ppke.progress.tracker import ProgressTracker
    from ppke.vectordb.store import VectorStore
    from ppke.graph.knowledge_graph import KnowledgeGraph

    tracker = ProgressTracker()
    vector_store = VectorStore(config.vault_path) if config.enable_vector_search else None
    knowledge_graph = KnowledgeGraph(config.vault_path) if config.enable_knowledge_graph else None

    try:
        if config.async_ingest:
            import asyncio
            from ppke.pipeline.async_orchestrator import ingest_book_async
            book_dir = asyncio.run(
                ingest_book_async(
                    book, config,
                    progress_callback=progress_callback,
                    human_operator=operator,
                    resume=resume,
                )
            )
        else:
            from ppke.pipeline.orchestrator import ingest_book
            book_dir = ingest_book(
                book, config,
                progress_callback=progress_callback,
                human_operator=operator,
                resume=resume,
                tracker=tracker,
                vector_store=vector_store,
                knowledge_graph=knowledge_graph,
            )
    except Exception as e:
        if tracker.get_book(book.folder_name):
            tracker.fail_book(book.folder_name, str(e))
        raise click.ClickException(f"Ingestion failed: {e}") from e

    click.echo(_render(_Text(f"\nDone! Output written to: {book_dir}", style="bold green")))


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

    table = _Table(title="Chapter Breakdown", border_style="dim")
    table.add_column("Ch#", style="cyan", width=5, justify="right")
    table.add_column("Title")
    table.add_column("Paras", justify="right", width=6)
    table.add_column("First Paragraph Preview")
    for chapter in book.chapters:
        preview = ""
        if chapter.paragraphs:
            p = chapter.paragraphs[0].text
            preview = (p[:70] + "...") if len(p) > 70 else p
        table.add_row(f"{chapter.number:02d}", chapter.title, str(chapter.paragraph_count), preview)
    click.echo(_render(table))


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

        answer = result.get("answer", "No answer generated.")
        click.echo(_render(_Panel(answer, title="[bold blue]Answer[/bold blue]", border_style="blue")))
        click.echo()

        quotes = result.get("verbatim_quotes", [])
        if quotes:
            evid_table = _Table(title="Evidence", border_style="dim", show_header=True)
            evid_table.add_column("Para ID", style="cyan", width=14)
            evid_table.add_column("Quote")
            for q in quotes:
                evid_table.add_row(q.get("paragraph_id", "?"), f"\"{q.get('quote', '')}\"")
            click.echo(_render(evid_table))
            click.echo()

        chain = result.get("logical_chain", [])
        if chain:
            chain_table = _Table(title="Logical Chain", border_style="dim", show_header=True)
            chain_table.add_column("#", width=3)
            chain_table.add_column("Claim")
            chain_table.add_column("Para ID", style="cyan", width=14)
            chain_table.add_column("Note", width=12)
            for step in chain:
                note = _escape("[INFERENCE]") if step.get("is_inference") else ""
                chain_table.add_row(
                    str(step.get("step", "?")),
                    step.get("claim", ""),
                    step.get("paragraph_id", "?"),
                    note,
                )
            click.echo(_render(chain_table))
            click.echo()

        conf = result.get("confidence", "unknown")
        conf_style = {"high": "bold green", "medium": "yellow", "low": "red"}.get(conf, "dim")
        click.echo(_render(_Text(f"Confidence: {conf}", style=conf_style)))

        # Log to research notebook
        try:
            _append_to_notebook(
                config.vault_path, question, answer,
                book=book, quotes=quotes,
            )
        except Exception:
            pass  # non-critical

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
        click.echo(_render(_Rule("[bold]Comparisons[/bold]")))
        for comp in comparisons:
            dim = comp.get("dimension", "Unknown")
            comp_table = _Table(title=dim, border_style="dim", show_header=True)
            comp_table.add_column("Book", style="cyan", width=25)
            comp_table.add_column("Position")
            for pb in comp.get("per_book", []):
                comp_table.add_row(pb.get("book_folder", "?"), pb.get("position", ""))
            click.echo(_render(comp_table))
            tensions = comp.get("tensions", [])
            if tensions:
                click.echo("  Tensions: " + " | ".join(tensions))
        click.echo()

    # Display cross-links
    links = result.get("cross_links", [])
    if links:
        click.echo(_render(_Rule("[bold]Cross-Links[/bold]")))
        links_table = _Table(border_style="dim", show_header=True)
        links_table.add_column("Concept", style="cyan", width=18)
        links_table.add_column("Relationship", width=14)
        links_table.add_column("Books", width=20)
        links_table.add_column("Description")
        for link in links:
            links_table.add_row(
                link.get("concept", "?"),
                link.get("relationship", "?"),
                ", ".join(link.get("books", [])),
                link.get("description", ""),
            )
        click.echo(_render(links_table))
        click.echo()

    overall = result.get("overall_synthesis", "")
    if overall:
        click.echo(_render(_Panel(overall, title="[bold]Synthesis[/bold]", border_style="green")))

    # Log to research notebook
    try:
        summary = overall or "See comparisons above."
        _append_to_notebook(config.vault_path, question, summary)
    except Exception:
        pass  # non-critical


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
        stage_t = _Text(f"[{stage}]", style="bold cyan")
        line = _Text.assemble(stage_t, " ", detail)
        click.echo("  " + _render(line))

    from ppke.pipeline.orchestrator import reread_chapters

    try:
        reread_chapters(
            book_dir=book_dir,
            chapter_numbers=chapter_numbers,
            config=config,
            progress_callback=progress_callback,
        )
        click.echo(_render(_Text(f"\nRe-read complete! Updated files in: {book_dir}", style="bold green")))
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
@click.option("--model", default=None, help="Model name (main model for analysis stages)")
@click.option("--small-model", default=None, help="Small/cheap model for extraction (Skill 1); defaults per provider")
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
    small_model: str | None,
    vault_path: Path | None,
    batch_size: int | None,
    show: bool,
):
    """View or update PPKE configuration.

    Examples:
        ppke config --show
        ppke config --provider anthropic --model claude-sonnet-4-20250514
        ppke config --small-model claude-3-haiku-20240307
        ppke config --vault-path ~/my-vault/KnowledgeBase
    """
    cfg = Config.load()

    if show or (not provider and not model and not small_model and not vault_path and not batch_size):
        tbl = _Table(show_header=False, box=None, padding=(0, 1))
        tbl.add_column("Setting", style="bold")
        tbl.add_column("Value")
        tbl.add_row("Provider:", cfg.llm.provider)
        tbl.add_row("Model:", cfg.llm.model)
        tbl.add_row("Small model:", cfg.llm.small_model or f"(default: {cfg.llm.effective_small_model})")
        tbl.add_row("Vault path:", str(cfg.vault_path))
        tbl.add_row("Batch size:", str(cfg.llm.paragraphs_per_batch))
        tbl.add_row("Max para tokens:", str(cfg.llm.max_paragraph_tokens))
        tbl.add_row("Max workers:", str(cfg.llm.max_workers))
        tbl.add_row("Selective:", str(cfg.selective_depth))
        tbl.add_row("Double pass:", str(cfg.double_pass))
        tbl.add_row("Default domain:", cfg.default_domain)
        tbl.add_row("Vector search:", "enabled" if cfg.enable_vector_search else "disabled")
        tbl.add_row("Knowledge graph:", "enabled" if cfg.enable_knowledge_graph else "disabled")
        tbl.add_row("Async ingest:", "enabled" if cfg.async_ingest else "disabled (sync)")
        api_key_val = "yes" if cfg.llm.active_api_key else "no"
        tbl.add_row("API key set:", api_key_val)
        click.echo(_render(_Panel(tbl, title="[bold]PPKE Configuration[/bold]")))
        return

    if provider:
        cfg.llm.provider = provider
    if model:
        cfg.llm.model = model
    if small_model:
        cfg.llm.small_model = small_model
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

    table = _Table(title=f"Knowledge Base — {vp}", border_style="blue")
    table.add_column("#", width=4, style="dim", justify="right")
    table.add_column("Title", width=35)
    table.add_column("Author", width=20)
    table.add_column("Year", width=6)
    table.add_column("Ch", justify="right", width=4)
    table.add_column("Para", justify="right", width=6)
    table.add_column("Status", width=12)

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

        title_disp = (title[:32] + "...") if len(title) > 35 else title
        author_disp = (author[:17] + "...") if len(author) > 20 else author
        status_style = "green" if status == "COMPLETE" else "red" if status == "INCOMPLETE" else "dim"
        table.add_row(
            str(i), title_disp, author_disp, year, chapters, paragraphs,
            _Text(status, style=status_style),
        )

    click.echo(_render(table))
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

    coverage_pct = (
        f"{total_processed / total_paragraphs * 100:.1f}%"
        if total_paragraphs > 0
        else "N/A"
    )

    stats_tbl = _Table(show_header=False, box=None, padding=(0, 1))
    stats_tbl.add_column("Key", style="bold")
    stats_tbl.add_column("Value", justify="right")
    stats_tbl.add_row("Books:", str(total_books))
    stats_tbl.add_row("Chapters:", str(total_chapters))
    stats_tbl.add_row("Paragraphs:", str(total_paragraphs))
    stats_tbl.add_row("Processed:", str(total_processed))
    stats_tbl.add_row("Concepts:", str(total_concepts))
    stats_tbl.add_row("Patterns:", str(total_patterns))
    stats_tbl.add_row("", "")
    stats_tbl.add_row("Complete:", str(complete_count))
    stats_tbl.add_row("Incomplete:", str(incomplete_count))
    stats_tbl.add_row("Coverage:", coverage_pct)
    stats_tbl.add_row("", "")
    stats_tbl.add_row("Vault:", str(vp))
    click.echo(_render(_Panel(stats_tbl, title="[bold]PPKE Vault Statistics[/bold]")))

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

    result_table = _Table(
        title=f'Search: "{_escape(text)}" — {len(hits)} hit(s)',
        border_style="dim",
        show_header=True,
    )
    result_table.add_column("Book / Para ID", style="cyan", width=30)
    result_table.add_column("Field", width=8)
    result_table.add_column("Snippet")
    for book_name, pid, field, snippet in hits:
        result_table.add_row(f"{book_name}\n{pid}", field, snippet)
    click.echo(_render(result_table))

    if len(hits) >= max_results:
        click.echo(f"(showing first {max_results} results, use --max-results for more)")


# ── cheat command ──


@main.command()
def cheat():
    """Print a quick-reference cheat sheet for all PPKE CLI commands.

    Displays a formatted table with command syntax, description, and examples.

    Example:
        ppke cheat
    """
    table = _Table(title="PPKE Command Cheat Sheet", border_style="blue", show_lines=True)
    table.add_column("Command", style="bold cyan", width=18)
    table.add_column("Description", width=38)
    table.add_column("Example", style="dim", width=50)

    commands = [
        ("ppke init", "First-time setup wizard", "ppke init"),
        ("ppke ingest", "Ingest a markdown book into the KB", 'ppke ingest book.md --title "Being and Time" --author "Heidegger"'),
        ("ppke async-ingest", "Async ingestion (asyncio pipeline)", 'ppke async-ingest book.md --title "Critique" --author "Kant"'),
        ("ppke parse", "Preview chapter/paragraph structure", 'ppke parse book.md --title "Republic" --author "Plato"'),
        ("ppke query", "Query a single encoded book", 'ppke query --book "Book_Republic_Plato" --question "What is justice?"'),
        ("ppke cross-query", "Query across all books", 'ppke cross-query --question "How do they differ on free will?"'),
        ("ppke re-read", "Re-extract specific chapters", 'ppke re-read --book "Book_Republic_Plato" --chapters "1,3"'),
        ("ppke config", "View or update configuration", "ppke config --show"),
        ("ppke status", "Show ingestion progress dashboard", "ppke status"),
        ("ppke list", "List all ingested books", "ppke list"),
        ("ppke stats", "Show vault-wide statistics", "ppke stats"),
        ("ppke search", "Local text search (no LLM)", 'ppke search "Dasein" --max-results 10'),
        ("ppke vector-search", "Semantic search via vector DB", 'ppke vector-search "nature of consciousness"'),
        ("ppke graph-query", "Query the knowledge graph", 'ppke graph-query "Dasein" --depth 2'),
        ("ppke graph-stats", "Knowledge graph statistics", "ppke graph-stats"),
        ("ppke graph-build", "Build/rebuild knowledge graph", "ppke graph-build"),
        ("ppke doctor", "Run diagnostic checks on setup", "ppke doctor"),
        ("ppke notebook", "View or manage research log", "ppke notebook"),
        ("ppke menu", "Interactive guided command menu", "ppke menu"),
        ("ppke tui", "Launch terminal dashboard", "ppke tui"),
        ("ppke cheat", "Show this cheat sheet", "ppke cheat"),
    ]

    for cmd, desc, example in commands:
        table.add_row(cmd, desc, example)

    click.echo(_render(table, width=120))
    click.echo()
    click.echo("  Tip: Use --help on any command for full options, e.g. ppke ingest --help")


# ── doctor command ──


@main.command()
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path to check",
)
def doctor(vault_path: Path | None):
    """Run diagnostic checks on your PPKE setup.

    Checks API key presence, vault directory accessibility, and flags
    any incomplete ingestions or pending checkpoints.

    Example:
        ppke doctor
    """
    import yaml

    cfg = Config.load()
    vp = vault_path or cfg.vault_path

    issues: list[str] = []
    ok: list[str] = []

    # 1. Check config file
    from ppke.config import DEFAULT_CONFIG_PATH
    if DEFAULT_CONFIG_PATH.exists():
        ok.append("Config file found: ~/.ppke/config.json")
    else:
        issues.append("Config file missing. Run 'ppke init' to create one.")

    # 2. Check API key
    provider = cfg.llm.provider
    env_var = PROVIDER_ENV_VARS.get(provider, "API_KEY")
    if cfg.llm.active_api_key:
        key = cfg.llm.active_api_key
        masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "***"
        ok.append(f"API key set for {provider}: {masked}")
    else:
        issues.append(f"API key missing for {provider}. Set {env_var} or run 'ppke init'.")

    # 3. Check vault directory
    if vp.exists() and vp.is_dir():
        ok.append(f"Vault directory accessible: {vp}")
    elif vp.exists():
        issues.append(f"Vault path exists but is not a directory: {vp}")
    else:
        issues.append(f"Vault directory not found: {vp}. Create it or run 'ppke init'.")

    # 4. Check ingested books
    incomplete_books: list[str] = []
    complete_count = 0
    if vp.exists():
        book_dirs = sorted(
            d for d in vp.iterdir() if d.is_dir() and d.name.startswith("Book_")
        )
        for bd in book_dirs:
            meta_path = bd / "meta.yml"
            if meta_path.exists():
                meta = yaml.safe_load(meta_path.read_text()) or {}
                status = meta.get("verification_status", "UNKNOWN")
                if status != "COMPLETE":
                    incomplete_books.append(f"{bd.name} (status: {status})")
                else:
                    complete_count += 1
            else:
                incomplete_books.append(f"{bd.name} (no meta.yml)")

        if book_dirs:
            ok.append(f"Books found: {len(book_dirs)} ({complete_count} complete)")
        else:
            issues.append("No books ingested yet. Run 'ppke ingest' to add a book.")

        if incomplete_books:
            for ib in incomplete_books:
                issues.append(f"Incomplete ingestion: {ib}")

        # 5. Check pending checkpoints
        checkpoints = list(vp.glob(".checkpoint_*.json"))
        if checkpoints:
            for cp in checkpoints:
                book_name = cp.stem.replace(".checkpoint_", "")
                issues.append(
                    f"Pending checkpoint: {book_name} (use 'ppke ingest --resume' to continue)"
                )
        else:
            ok.append("No pending checkpoints.")

    # 6. Check provider/model config
    ok.append(f"Provider: {cfg.llm.provider}, Model: {cfg.llm.model}")

    # Display results
    result_table = _Table(show_header=False, box=None, padding=(0, 1))
    result_table.add_column("Icon", width=3)
    result_table.add_column("Detail")

    for item in ok:
        result_table.add_row(
            _Text("OK", style="bold green"),
            item,
        )
    for item in issues:
        result_table.add_row(
            _Text("!!", style="bold red"),
            item,
        )

    title_style = "bold green" if not issues else "bold yellow"
    title_text = "All checks passed!" if not issues else f"{len(issues)} issue(s) found"
    click.echo(_render(_Panel(result_table, title=f"[{title_style}]PPKE Doctor — {title_text}[/{title_style}]", border_style="blue")))


# ── notebook command ──


_NOTEBOOK_FILENAME = "RESEARCH_NOTEBOOK.md"


def _get_notebook_path(vault_path: Path) -> Path:
    """Return the path to the research notebook in the vault."""
    return vault_path / _NOTEBOOK_FILENAME


def _append_to_notebook(
    vault_path: Path,
    question: str,
    answer: str,
    book: str | None = None,
    quotes: list[dict] | None = None,
):
    """Append a query/answer entry to the research notebook."""
    import datetime

    notebook_path = _get_notebook_path(vault_path)

    if not notebook_path.exists():
        header = (
            "# PPKE Research Notebook\n\n"
            "Auto-generated research log. Each entry records a query, "
            "its answer, and supporting evidence.\n\n---\n\n"
        )
        notebook_path.write_text(header)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scope = f"Book: {book}" if book else "Cross-book query"

    entry_lines = [
        f"## [{timestamp}] {scope}\n",
        f"**Question:** {question}\n",
        f"**Answer:**\n\n{answer}\n",
    ]

    if quotes:
        entry_lines.append("**Evidence:**\n")
        for q in quotes:
            pid = q.get("paragraph_id", "?")
            quote_text = q.get("quote", "")
            entry_lines.append(f"- `{pid}`: \"{quote_text}\"\n")

    entry_lines.append("\n---\n\n")

    with open(notebook_path, "a") as f:
        f.writelines(entry_lines)


@main.command()
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path",
)
@click.option("--tail", type=int, default=None, help="Show last N entries")
@click.option("--clear", is_flag=True, help="Delete the notebook file")
def notebook(vault_path: Path | None, tail: int | None, clear: bool):
    """View or manage the research notebook (query/answer log).

    The notebook is automatically updated when you run queries. Use this
    command to view, tail, or clear your research history.

    Examples:
        ppke notebook
        ppke notebook --tail 5
        ppke notebook --clear
    """
    cfg = Config.load()
    vp = vault_path or cfg.vault_path
    nb_path = _get_notebook_path(vp)

    if clear:
        if nb_path.exists():
            nb_path.unlink()
            click.echo("Research notebook cleared.")
        else:
            click.echo("No notebook to clear.")
        return

    if not nb_path.exists():
        click.echo("No research notebook found yet.")
        click.echo("Run a query or cross-query to start logging entries.")
        click.echo(f"  Notebook location: {nb_path}")
        return

    content = nb_path.read_text()

    if tail is not None:
        # Split by entries (separated by ---) and take the last N
        entries = [e.strip() for e in content.split("---") if e.strip()]
        # First entry is the header
        header = entries[0] if entries else ""
        data_entries = entries[1:] if len(entries) > 1 else []
        shown = data_entries[-tail:] if tail < len(data_entries) else data_entries
        click.echo(f"Showing last {len(shown)} of {len(data_entries)} entries:\n")
        for entry in shown:
            click.echo(entry)
            click.echo("\n---\n")
    else:
        click.echo(content)

    click.echo(f"\nNotebook: {nb_path}")
    click.echo(f"Size: {nb_path.stat().st_size:,} bytes")


# ── menu command ──


@main.command()
def menu():
    """Interactive guided menu for running PPKE commands.

    Presents a numbered menu of actions, prompts for arguments,
    shows the equivalent CLI command, and optionally executes it.

    Example:
        ppke menu
    """
    click.echo(_render(_Rule("[bold blue]PPKE Interactive Menu[/bold blue]")))
    click.echo()

    actions = [
        ("Ingest a book", "ingest"),
        ("Parse a book (dry run)", "parse"),
        ("Query a single book", "query"),
        ("Cross-query all books", "cross-query"),
        ("Re-read chapters", "re-read"),
        ("Search paragraphs", "search"),
        ("List books", "list"),
        ("Show statistics", "stats"),
        ("Run doctor diagnostics", "doctor"),
        ("View research notebook", "notebook"),
        ("Show configuration", "config"),
        ("Show cheat sheet", "cheat"),
    ]

    for i, (label, _) in enumerate(actions, 1):
        click.echo(f"  {i:2d}. {label}")
    click.echo(f"   0. Exit")
    click.echo()

    choice = click.prompt("Select an action", type=int)
    if choice == 0:
        click.echo("Bye!")
        return

    if choice < 1 or choice > len(actions):
        click.echo("Invalid choice.")
        return

    label, cmd = actions[choice - 1]
    click.echo()
    click.echo(f"Selected: {label}")
    click.echo()

    # Build command based on selection
    parts = ["ppke", cmd]

    if cmd == "ingest":
        filepath = click.prompt("Path to markdown file")
        title = click.prompt("Book title")
        author = click.prompt("Book author")
        year = click.prompt("Publication year (optional, press Enter to skip)", default="", show_default=False)
        resume = click.confirm("Resume from checkpoint?", default=False)
        double_pass = click.confirm("Enable double-pass extraction?", default=False)

        parts.extend([filepath, "--title", f'"{title}"', "--author", f'"{author}"'])
        if year:
            parts.extend(["--year", year])
        if resume:
            parts.append("--resume")
        if double_pass:
            parts.append("--double-pass")

    elif cmd == "parse":
        filepath = click.prompt("Path to markdown file")
        title = click.prompt("Book title", default="Untitled")
        author = click.prompt("Author", default="Unknown")
        parts.extend([filepath, "--title", f'"{title}"', "--author", f'"{author}"'])

    elif cmd == "query":
        book = click.prompt("Book folder name")
        question = click.prompt("Question")
        parts.extend(["--book", f'"{book}"', "--question", f'"{question}"'])

    elif cmd == "cross-query":
        question = click.prompt("Question")
        parts.extend(["--question", f'"{question}"'])

    elif cmd == "re-read":
        book = click.prompt("Book folder name")
        chapters = click.prompt("Chapter numbers (comma-separated)")
        parts.extend(["--book", f'"{book}"', "--chapters", f'"{chapters}"'])

    elif cmd == "search":
        text = click.prompt("Search text")
        max_results = click.prompt("Max results", type=int, default=20)
        parts.extend([f'"{text}"', "--max-results", str(max_results)])

    # Commands that need no arguments: list, stats, doctor, notebook, config, cheat

    click.echo()
    full_cmd = " ".join(parts)
    click.echo(_render(_Panel(full_cmd, title="[bold]Command[/bold]", border_style="cyan")))
    click.echo()

    if click.confirm("Execute this command now?", default=True):
        click.echo()
        # Invoke the appropriate subcommand via Click's context
        ctx = click.get_current_context()
        try:
            ctx.invoke(main.commands[cmd])
        except (SystemExit, click.ClickException):
            pass
        except TypeError:
            # Command requires arguments we can't pass via ctx.invoke easily
            # Fall back to suggesting manual execution
            click.echo("This command requires arguments. Please run it manually:")
            click.echo(f"  {full_cmd}")


# ── tui command ──


@main.command()
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path",
)
def tui(vault_path: Path | None):
    """Launch an interactive terminal dashboard.

    Browse books, view summaries, stats, and run quick searches
    from a rich terminal interface.

    Example:
        ppke tui
    """
    from ppke.tui import run_dashboard

    cfg = Config.load()
    vp = vault_path or cfg.vault_path

    run_dashboard(vp, cfg)


# ── status command ──


@main.command()
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path",
)
@click.option("--clear-done", is_flag=True, help="Remove completed books from the tracker")
def status(vault_path: Path | None, clear_done: bool):
    """Show ingestion progress for all tracked books.

    Displays a live dashboard of queued, in-progress, completed, and failed
    ingestion jobs with chapter and paragraph completion percentages.

    Examples:
        ppke status
        ppke status --clear-done
    """
    from ppke.progress.tracker import ProgressTracker

    tracker = ProgressTracker()

    if clear_done:
        removed = tracker.clear_completed()
        click.echo(f"Removed {removed} completed book(s) from progress tracker.")
        return

    summary = tracker.summary()
    all_books = tracker.get_all()

    if not all_books:
        click.echo("No ingestion jobs tracked yet.")
        click.echo("Run 'ppke ingest' to start tracking progress.")
        return

    # Summary panel
    sum_tbl = _Table(show_header=False, box=None, padding=(0, 1))
    sum_tbl.add_column("Key", style="bold")
    sum_tbl.add_column("Value", justify="right")
    sum_tbl.add_row("Total jobs:", str(summary["total"]))
    sum_tbl.add_row("Queued:", str(summary["queued"]))
    sum_tbl.add_row("In progress:", str(summary["in_progress"]))
    sum_tbl.add_row("Complete:", str(summary["complete"]))
    sum_tbl.add_row("Failed:", str(summary["failed"]))
    sum_tbl.add_row("", "")
    ch_pct = (
        f"{summary['completed_chapters'] / summary['total_chapters'] * 100:.1f}%"
        if summary["total_chapters"] > 0 else "N/A"
    )
    sum_tbl.add_row("Chapters:", f"{summary['completed_chapters']}/{summary['total_chapters']} ({ch_pct})")
    para_pct = (
        f"{summary['completed_paragraphs'] / summary['total_paragraphs'] * 100:.1f}%"
        if summary["total_paragraphs"] > 0 else "N/A"
    )
    sum_tbl.add_row("Paragraphs:", f"{summary['completed_paragraphs']}/{summary['total_paragraphs']} ({para_pct})")
    click.echo(_render(_Panel(sum_tbl, title="[bold]PPKE Ingestion Progress[/bold]")))
    click.echo()

    # Per-book table
    book_tbl = _Table(title="Books", border_style="blue", show_header=True)
    book_tbl.add_column("Book", width=32)
    book_tbl.add_column("Author", width=18)
    book_tbl.add_column("Status", width=12)
    book_tbl.add_column("Chapters", justify="right", width=12)
    book_tbl.add_column("Paragraphs", justify="right", width=14)
    book_tbl.add_column("Current Chapter", width=28)

    status_styles = {
        "complete": "bold green",
        "in_progress": "bold cyan",
        "queued": "dim",
        "failed": "bold red",
    }

    for bp in sorted(all_books.values(), key=lambda b: b.started_at or ""):
        style = status_styles.get(bp.status, "dim")
        ch_str = f"{bp.completed_chapters}/{bp.total_chapters}"
        para_str = f"{bp.completed_paragraphs}/{bp.total_paragraphs}"
        current = bp.current_chapter or ("-" if bp.status != "failed" else (bp.error or "error")[:28])
        book_tbl.add_row(
            (bp.title[:29] + "...") if len(bp.title) > 32 else bp.title,
            (bp.author[:15] + "...") if len(bp.author) > 18 else bp.author,
            _Text(bp.status, style=style),
            ch_str,
            para_str,
            current,
        )

    click.echo(_render(book_tbl))
    click.echo()
    click.echo("  Tip: Use 'ppke status --clear-done' to remove completed entries.")


# ── vector-search command ──


@main.command("vector-search")
@click.argument("query")
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path",
)
@click.option("--book", default=None, help="Restrict search to a specific book folder")
@click.option(
    "--n-results", type=int, default=10, help="Number of results to return (default: 10)"
)
@click.option("--rebuild", is_flag=True, help="Rebuild the entire vector index from scratch")
def vector_search(
    query: str,
    vault_path: Path | None,
    book: str | None,
    n_results: int,
    rebuild: bool,
):
    """Semantic (vector) search across all indexed paragraphs.

    Uses ChromaDB embeddings for millisecond concept recall without any LLM
    calls. Finds paragraphs semantically similar to the query even when
    exact keywords do not match.

    Requires: pip install chromadb  (or: pip install "ppke[vector]")

    Examples:
        ppke vector-search "the nature of consciousness"
        ppke vector-search "free will" --book "Book_Republic_Plato"
        ppke vector-search "time" --n-results 20
        ppke vector-search "" --rebuild   # rebuild the index
    """
    cfg = Config.load()
    vp = vault_path or cfg.vault_path

    from ppke.vectordb.store import VectorStore

    store = VectorStore(vp)

    if not store.available:
        click.echo(
            "Vector search unavailable: chromadb is not installed.\n"
            "Install it with:  pip install chromadb\n"
            "Or:               pip install 'ppke[vector]'",
            err=True,
        )
        sys.exit(1)

    if rebuild:
        click.echo("Rebuilding vector index from vault...")
        results = store.rebuild_index(vp)
        total = sum(results.values())
        click.echo(f"Rebuilt index: {len(results)} books, {total} vectors.")
        if not query:
            return

    if not query:
        click.echo(f"Vector store contains {store.count()} indexed vectors.")
        return

    if book:
        book_filter = _safe_book_dir(vp, book).name
    else:
        book_filter = None

    hits = store.search(query, n_results=n_results, book_filter=book_filter)

    if not hits:
        click.echo(f'No vector search results for "{query}".')
        if store.count() == 0:
            click.echo(
                "Hint: The vector index is empty. "
                "Run 'ppke vector-search --rebuild' or re-ingest your books."
            )
        return

    result_tbl = _Table(
        title=f'Vector Search: "{_escape(query)}" — {len(hits)} result(s)',
        border_style="dim",
        show_header=True,
    )
    result_tbl.add_column("Book / Para ID", style="cyan", width=30)
    result_tbl.add_column("Dist", width=7, justify="right")
    result_tbl.add_column("Snippet")
    for hit in hits:
        snippet = hit["document"]
        if len(snippet) > 90:
            snippet = snippet[:90] + "..."
        result_tbl.add_row(
            f"{hit['book_folder']}\n{hit['paragraph_id']}",
            str(hit["distance"]),
            snippet,
        )
    click.echo(_render(result_tbl))


# ── async-ingest command ──


@main.command("async-ingest")
@click.argument("filepath", type=click.Path(exists=True, path_type=Path))
@click.option("--title", required=True, help="Book title")
@click.option("--author", required=True, help="Book author")
@click.option("--year", default=None, help="Publication year")
@click.option("--domain", default=None, help="Domain template (overrides config default_domain)")
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
@click.option("--batch-size", type=click.IntRange(min=1), default=None, help="Paragraphs per LLM batch")
@click.option("--operator", default="", help="Human operator name for versioning")
@click.option("--double-pass", is_flag=True, help="Enable double-pass extraction")
@click.option("--resume", is_flag=True, help="Resume from last checkpoint")
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def async_ingest(
    filepath: Path,
    title: str,
    author: str,
    year: str | None,
    domain: str | None,
    provider: str | None,
    model: str | None,
    vault_path: Path | None,
    batch_size: int | None,
    operator: str,
    double_pass: bool,
    resume: bool,
    verbose: bool,
):
    """Ingest a book using the async (asyncio-based) pipeline.

    Same as 'ppke ingest' but uses asyncio.gather for concurrent chapter
    extraction and analysis stages, maximising throughput on large books.
    Integrates with the progress tracker, vector store, and knowledge graph.

    Examples:
        ppke async-ingest book.md --title "Being and Time" --author "Heidegger"
        ppke async-ingest book.md --title "Republic" --author "Plato" --resume
    """
    _setup_logging(verbose)

    config = _load_config_with_overrides(provider, model, vault_path, batch_size)
    if double_pass:
        config.double_pass = True
    # Resolve domain: CLI flag > config default_domain > "philosophy"
    domain = domain or config.default_domain or "philosophy"
    _require_api_key(config)

    click.echo(f"Parsing {filepath}...")
    from ppke.parser.markdown import parse_markdown_book

    book = parse_markdown_book(filepath, title, author, year)
    click.echo(
        f"Parsed: {len(book.chapters)} chapters, {book.total_paragraphs} paragraphs"
    )

    click.echo("Starting async ingestion pipeline...")

    def progress_callback(stage: str, detail: str):
        stage_t = _Text(f"[{stage}]", style="bold cyan")
        line = _Text.assemble(stage_t, " ", detail)
        click.echo("  " + _render(line))

    from ppke.pipeline.async_orchestrator import run_ingest_async
    from ppke.progress.tracker import ProgressTracker
    from ppke.vectordb.store import VectorStore
    from ppke.graph.knowledge_graph import KnowledgeGraph

    tracker = ProgressTracker()
    vector_store = VectorStore(config.vault_path)
    kg = KnowledgeGraph(config.vault_path)

    try:
        book_dir = run_ingest_async(
            book=book,
            config=config,
            progress_callback=progress_callback,
            human_operator=operator,
            resume=resume,
        )
        # Post-ingestion: update vector store and graph
        import json as _json
        ext_path = book_dir / "extractions.json"
        ext_dicts = []
        if ext_path.exists():
            ext_dicts = _json.loads(ext_path.read_text())

        tracker.register_book(book.folder_name, title, author,
                               total_chapters=len(book.chapters),
                               total_paragraphs=book.total_paragraphs)
        tracker.complete_book(book.folder_name)

        if vector_store.available and ext_dicts:
            indexed = vector_store.index_extractions(book.folder_name, title, author, ext_dicts)
            click.echo(f"  Indexed {indexed} paragraphs into vector store.")

        if ext_dicts:
            edges = kg.add_book_extractions(book.folder_name, title, author, ext_dicts)
            kg.save()
            click.echo(f"  Knowledge graph updated ({edges} edges added).")

    except Exception as e:
        raise click.ClickException(f"Async ingestion failed: {e}") from e

    click.echo(_render(_Text(f"\nDone! Output written to: {book_dir}", style="bold green")))


# ── graph-query command ──


@main.command("graph-query")
@click.argument("concept")
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path",
)
@click.option("--depth", type=int, default=2, help="Graph traversal depth (default: 2)")
@click.option("--provenance", is_flag=True, help="Show per-paragraph provenance instead of concept expansion")
def graph_query(concept: str, vault_path: Path | None, depth: int, provenance: bool):
    """Query the knowledge graph for a concept.

    Without --provenance: expands *concept* to all related concepts within
    *depth* hops, showing which books mention each.

    With --provenance: shows every book and paragraph that mentions *concept*
    directly.

    Examples:
        ppke graph-query "Dasein"
        ppke graph-query "free will" --depth 3
        ppke graph-query "consciousness" --provenance
    """
    cfg = Config.load()
    vp = vault_path or cfg.vault_path

    from ppke.graph.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph(vp)

    if kg.stats()["concepts"] == 0:
        click.echo(
            "Knowledge graph is empty. "
            "Run 'ppke graph-build' to build it from your vault.",
            err=True,
        )
        sys.exit(1)

    if provenance:
        results = kg.concept_provenance(concept)
        if not results:
            click.echo(f'No provenance found for concept: "{concept}"')
            return

        prov_tbl = _Table(
            title=f'Provenance: "{_escape(concept)}" — {len(results)} paragraph(s)',
            border_style="blue",
        )
        prov_tbl.add_column("Book", style="cyan", width=35)
        prov_tbl.add_column("Paragraph ID", width=16)
        prov_tbl.add_column("Relation", width=14)
        for r in results:
            prov_tbl.add_row(r["book_folder"], r["paragraph_id"], r["relation"])
        click.echo(_render(prov_tbl))
    else:
        books = kg.books_mentioning(concept)
        if books:
            click.echo(f'Books mentioning "{concept}": {", ".join(books)}')
            click.echo()

        results = kg.expand_concept(concept, depth=depth)
        if not results:
            click.echo(f'No related concepts found for: "{concept}"')
            return

        exp_tbl = _Table(
            title=f'Concept expansion: "{_escape(concept)}" (depth={depth}) — {len(results)} result(s)',
            border_style="green",
        )
        exp_tbl.add_column("Related Concept", style="cyan", width=30)
        exp_tbl.add_column("Relation", width=16)
        exp_tbl.add_column("Books", width=40)
        for r in results:
            exp_tbl.add_row(
                r["label"],
                r["relation"],
                ", ".join(r["books"][:3]) + ("…" if len(r["books"]) > 3 else ""),
            )
        click.echo(_render(exp_tbl))


# ── graph-stats command ──


@main.command("graph-stats")
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path",
)
def graph_stats(vault_path: Path | None):
    """Show knowledge graph statistics.

    Displays node/edge counts broken down by type (books, concepts, paragraphs).

    Example:
        ppke graph-stats
    """
    cfg = Config.load()
    vp = vault_path or cfg.vault_path

    from ppke.graph.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph(vp)
    s = kg.stats()

    tbl = _Table(show_header=False, box=None, padding=(0, 1))
    tbl.add_column("Key", style="bold")
    tbl.add_column("Value", justify="right")
    tbl.add_row("Books:", str(s["books"]))
    tbl.add_row("Concepts:", str(s["concepts"]))
    tbl.add_row("Paragraphs:", str(s["paragraphs"]))
    tbl.add_row("Edges:", str(s["edges"]))
    if s["networkx_available"]:
        tbl.add_row("Connected components:", str(s["weakly_connected_components"]))
    tbl.add_row("", "")
    tbl.add_row("NetworkX available:", "yes" if s["networkx_available"] else "no (install: pip install networkx)")
    tbl.add_row("Graph file:", str(vp / "knowledge_graph.json"))
    click.echo(_render(_Panel(tbl, title="[bold]PPKE Knowledge Graph Statistics[/bold]")))


# ── graph-build command ──


@main.command("graph-build")
@click.option(
    "--vault-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Vault path",
)
@click.option("--reset", is_flag=True, help="Delete existing graph before rebuilding")
def graph_build(vault_path: Path | None, reset: bool):
    """Build or rebuild the knowledge graph from all vault books.

    Reads every extractions.json in the vault and constructs the concept-level
    graph. Run this once after first ingestion, or after major re-reads.

    Examples:
        ppke graph-build
        ppke graph-build --reset   # rebuild from scratch
    """
    cfg = Config.load()
    vp = vault_path or cfg.vault_path

    if not vp.exists():
        click.echo(f"Vault not found: {vp}", err=True)
        sys.exit(1)

    from ppke.graph.knowledge_graph import KnowledgeGraph

    if reset:
        graph_file = vp / "knowledge_graph.json"
        if graph_file.exists():
            graph_file.unlink()
            click.echo("Existing graph deleted.")
        kg = KnowledgeGraph(vp)
    else:
        kg = KnowledgeGraph(vp)

    click.echo("Building knowledge graph from vault...")
    results = kg.build_from_vault(vp)
    kg.save()

    total_edges = sum(results.values())
    tbl = _Table(title="Knowledge Graph Build Results", border_style="green")
    tbl.add_column("Book", style="cyan")
    tbl.add_column("Edges Added", justify="right", width=12)
    for book_folder, edges in sorted(results.items()):
        tbl.add_row(book_folder, str(edges))
    click.echo(_render(tbl))
    click.echo()

    s = kg.stats()
    click.echo(
        f"Graph saved to {vp / 'knowledge_graph.json'} — "
        f"{s['concepts']} concepts, {s['edges']} total edges across {s['books']} books."
    )


# ── validate-plugin command ──


@main.command("validate-plugin")
@click.argument('plugin_path', type=click.Path(exists=True, path_type=Path))
def validate_plugin(plugin_path: Path):
    """Validate a custom plugin structure and security.

    Checks:
    - Required files present (template.yml, schema.yml, prompts.yml)
    - YAML syntax is valid
    - Schema fields are correctly typed
    - No security issues (dangerous code patterns)
    - Prompts are well-formed

    Examples:
        ppke validate-plugin ~/.ppke/plugins/my_domain
        ppke validate-plugin ./my_custom_plugin/
    """
    from ppke.templates.loader import load_template
    from ppke.templates.validator import validate_template

    plugin_dir = plugin_path.resolve()
    plugin_name = plugin_dir.name

    click.echo(f"Validating plugin: {plugin_name}")
    click.echo(f"Location: {plugin_dir}\n")

    try:
        # Attempt to load template
        template = load_template(plugin_name)

        # Basic validation passed
        click.echo(f"OK - Plugin '{plugin_name}' loaded successfully\n")

        # Show metadata
        click.echo("Plugin Metadata:")
        click.echo(f"  Name:        {template.name}")
        click.echo(f"  Version:     {template.version}")
        click.echo(f"  Tier:        {template.tier}")
        click.echo(f"  Author:      {template.author}")
        click.echo(f"  Description: {template.description}")
        click.echo(f"  Stages:      {len(template.stages)}")
        click.echo(f"  Prompts:     {len(template.prompts)}")
        click.echo()

        # Validate structure (raises ValueError if invalid, prints warnings)
        validate_template(template)

        click.echo()
        click.echo("OK - Validation complete!")

    except FileNotFoundError as e:
        click.echo(f"ERROR: Plugin validation failed: {e}", err=True)
        click.echo("\nMake sure the plugin directory contains:")
        click.echo("  - template.yml")
        click.echo("  - schema.yml")
        click.echo("  - prompts.yml")
        sys.exit(1)
    except Exception as e:
        click.echo(f"ERROR: Plugin validation failed: {e}", err=True)
        sys.exit(1)


# ── promote-plugin command ──


@main.command("promote-plugin")
@click.argument('plugin_name')
@click.option('--force', is_flag=True, help='Skip confirmation prompt')
def promote_plugin(plugin_name: str, force: bool):
    """Promote a Tier 2 (custom) plugin to Tier 1 (official).

    This command is for maintainers only. It moves a custom plugin from
    ~/.ppke/plugins/ to ppke/templates/official/ and updates the registry.

    Prerequisites:
    - Plugin exists in ~/.ppke/plugins/
    - Plugin passes validation
    - Plugin tier is 'custom' in template.yml

    Examples:
        ppke promote-plugin scientific_research
        ppke promote-plugin my_domain --force
    """
    import shutil
    from ppke.templates.loader import load_template
    from ppke.templates.registry import register_plugin

    # Determine paths
    from pathlib import Path
    custom_path = Path.home() / ".ppke" / "plugins" / plugin_name
    official_path = Path(__file__).parent / "templates" / "official" / plugin_name

    # Check if plugin exists in custom
    if not custom_path.exists():
        click.echo(f"ERROR: Plugin '{plugin_name}' not found in custom plugins", err=True)
        click.echo(f"Expected location: {custom_path}")
        sys.exit(1)

    # Load and validate
    try:
        template = load_template(plugin_name)
    except Exception as e:
        click.echo(f"ERROR: Failed to load plugin: {e}", err=True)
        sys.exit(1)

    # Check tier
    if template.tier != 'custom':
        click.echo(f"ERROR: Plugin tier is '{template.tier}', expected 'custom'", err=True)
        click.echo("Promotion is only for Tier 2 (custom) plugins.")
        sys.exit(1)

    # Check if already exists in official
    if official_path.exists():
        click.echo(f"ERROR: Plugin already exists in official templates: {official_path}", err=True)
        sys.exit(1)

    # Confirm
    if not force:
        click.echo(f"About to promote '{plugin_name}' to Tier 1 (official):")
        click.echo(f"  From: {custom_path}")
        click.echo(f"  To: {official_path}")
        click.echo()
        if not click.confirm("Continue with promotion?"):
            click.echo("Cancelled.")
            return

    # Copy to official
    try:
        shutil.copytree(custom_path, official_path)
        click.echo(f"OK - Copied plugin to: {official_path}")
    except Exception as e:
        click.echo(f"ERROR: Failed to copy plugin: {e}", err=True)
        sys.exit(1)

    # Update template.yml tier field
    template_yml = official_path / "template.yml"
    if template_yml.exists():
        content = template_yml.read_text()
        updated_content = content.replace("tier: custom", "tier: official")
        template_yml.write_text(updated_content)
        click.echo("OK - Updated tier to 'official' in template.yml")

    # Update registry
    register_plugin(
        name=template.name,
        tier='official',
        version=template.version,
        source='promoted',
        author=template.author,
        description=template.description
    )
    click.echo("OK - Updated plugin registry")

    click.echo()
    click.echo(f"OK - Successfully promoted '{plugin_name}' to Tier 1 (official)!")
    click.echo(f"Plugin is now available as an official template at: {official_path}")


# ── template command group ──


@main.group("template")
def template():
    """
    Manage PPKE templates (install, uninstall, upgrade).

    Templates extend PPKE with domain-specific analysis capabilities.
    """
    pass


@template.command("install")
@click.argument("source")
@click.option("--force", is_flag=True, help="Overwrite existing template")
def template_install(source: str, force: bool):
    """
    Install a template from GitHub or local path.

    SOURCE can be:
    - GitHub URL: https://github.com/user/ppke-template-name
    - Local path: ./my-template/ or ~/templates/my-template/

    Examples:
        ppke template install https://github.com/user/ppke-template-legal
        ppke template install ./my-custom-template/
        ppke template install ~/Downloads/scientific-template/ --force
    """
    from ppke.templates.installer import (
        install_from_github,
        install_from_local,
        TemplateInstallError
    )

    try:
        # Determine if source is GitHub URL or local path
        if source.startswith('http://') or source.startswith('https://'):
            # GitHub URL
            template_name = install_from_github(source, force=force)
        else:
            # Local path
            local_path = Path(source).expanduser().resolve()
            template_name = install_from_local(local_path, force=force)

        # Success message already printed by installer module

    except TemplateInstallError as e:
        click.echo(f"\nInstallation failed: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\nUnexpected error: {e}", err=True)
        sys.exit(1)


@template.command("uninstall")
@click.argument("template_name")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def template_uninstall(template_name: str, force: bool):
    """
    Uninstall a custom template.

    Official templates cannot be uninstalled.

    Examples:
        ppke template uninstall my_domain
        ppke template uninstall scientific_research --force
    """
    from ppke.templates.installer import uninstall_template, TemplateInstallError

    try:
        success = uninstall_template(template_name, force=force)
        # Success message already printed by uninstall_template function
    except TemplateInstallError as e:
        click.echo(f"\nUninstallation failed: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\nUnexpected error: {e}", err=True)
        sys.exit(1)


@template.command("upgrade")
@click.argument("template_name")
def template_upgrade(template_name: str):
    """
    Upgrade an installed template to the latest version.

    Only works for templates installed from GitHub.
    For locally-installed templates, reinstall with --force.

    Examples:
        ppke template upgrade legal
        ppke template upgrade my_domain
    """
    from ppke.templates.installer import upgrade_template, TemplateInstallError

    try:
        upgrade_template(template_name)
    except TemplateInstallError as e:
        click.echo(f"\n❌ Upgrade failed: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n❌ Unexpected error: {e}", err=True)
        sys.exit(1)


@template.command("list")
def template_list():
    """
    List all installed templates with metadata.

    Shows:
    - Template name
    - Version
    - Tier (official/custom)
    - Installation source
    - Author

    Examples:
        ppke template list
    """
    from ppke.templates.installer import list_installed_templates

    templates = list_installed_templates()

    if not templates:
        click.echo("No templates installed.")
        return

    # Group by tier
    official = [t for t in templates if t['tier'] == 'official']
    custom = [t for t in templates if t['tier'] == 'custom']

    # Display official templates
    if official:
        click.echo("\nOfficial Templates (Tier 1):")
        click.echo("-" * 80)
        for t in official:
            click.echo(f"  {t['name']:<20} v{t['version']:<10} by {t['author']}")
            if t['description']:
                click.echo(f"    {t['description']}")
            click.echo()

    # Display custom templates
    if custom:
        click.echo("\nCustom Templates (Tier 2):")
        click.echo("-" * 80)
        for t in custom:
            source = t.get('source', 'unknown')
            click.echo(f"  {t['name']:<20} v{t['version']:<10} by {t['author']}")
            if t['description']:
                click.echo(f"    {t['description']}")
            click.echo(f"    Source: {source}")
            click.echo()

    click.echo(f"\nTotal: {len(templates)} templates ({len(official)} official, {len(custom)} custom)")


if __name__ == "__main__":  # pragma: no cover
    main()
