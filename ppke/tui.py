"""Terminal dashboard for PPKE (ppke tui command)."""

from __future__ import annotations

import json
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from ppke.config import Config


def _console() -> Console:
    return Console()


def _list_books(vault_path: Path) -> list[dict]:
    """List books in the vault with metadata."""
    books = []
    if not vault_path.exists():
        return books
    for d in sorted(vault_path.iterdir()):
        if not d.is_dir() or not d.name.startswith("Book_"):
            continue
        meta_path = d / "meta.yml"
        info = {"folder": d.name, "path": d}
        if meta_path.exists():
            meta = yaml.safe_load(meta_path.read_text()) or {}
            info.update(meta)
        books.append(info)
    return books


def _show_book_detail(console: Console, book: dict):
    """Show detailed information about a single book."""
    path = book["path"]
    title = book.get("title", book["folder"])
    author = book.get("author", "Unknown")
    _status = book.get("verification_status", "?")

    console.print()
    console.print(Rule(f"[bold]{title}[/bold] by {author}"))
    console.print()

    # Meta info
    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column("Key", style="bold")
    info_table.add_column("Value")
    for key in ["title", "author", "year", "total_chapters", "total_paragraphs",
                "verification_status", "ingest_date", "ingest_mode"]:
        if key in book:
            info_table.add_row(f"{key}:", str(book[key]))
    console.print(Panel(info_table, title="[bold]Book Metadata[/bold]", border_style="blue"))

    # Show available files
    files_table = Table(show_header=True, border_style="dim")
    files_table.add_column("File", style="cyan")
    files_table.add_column("Size", justify="right")
    files_table.add_column("Status")

    expected_files = [
        "meta.yml", "01_Raw_Structure.md", "02_Logical_Map.md",
        "03_Concept_Index.md", "04_Author_Model.md", "05_Coverage_Report.md",
        "06_Patterns.md", "extractions.json",
    ]
    for fname in expected_files:
        fpath = path / fname
        if fpath.exists():
            size = f"{fpath.stat().st_size:,} bytes"
            files_table.add_row(fname, size, Text("exists", style="green"))
        else:
            files_table.add_row(fname, "-", Text("missing", style="red"))

    console.print(files_table)

    # Quick concept summary
    concept_path = path / "03_Concept_Index.md"
    if concept_path.exists():
        import re
        concepts = re.findall(r"^## (.+)$", concept_path.read_text(), re.MULTILINE)
        if concepts:
            console.print()
            console.print(f"[bold]Concepts ({len(concepts)}):[/bold] " + ", ".join(concepts[:10]))
            if len(concepts) > 10:
                console.print(f"  ... and {len(concepts) - 10} more")


def _show_books_table(console: Console, books: list[dict]):
    """Display a summary table of all books."""
    table = Table(title="Books in Vault", border_style="blue")
    table.add_column("#", width=4, style="dim", justify="right")
    table.add_column("Title", width=35)
    table.add_column("Author", width=20)
    table.add_column("Chapters", justify="right", width=8)
    table.add_column("Paragraphs", justify="right", width=10)
    table.add_column("Status", width=12)

    for i, b in enumerate(books, 1):
        title = b.get("title", b["folder"])
        if len(title) > 35:
            title = title[:32] + "..."
        author = b.get("author", "?")
        if len(author) > 20:
            author = author[:17] + "..."
        chs = str(b.get("total_chapters", "?"))
        paras = str(b.get("total_paragraphs", "?"))
        status = b.get("verification_status", "?")
        style = "green" if status == "COMPLETE" else "red" if status == "INCOMPLETE" else "dim"
        table.add_row(str(i), title, author, chs, paras, Text(status, style=style))

    console.print(table)


def _quick_search(vault_path: Path, query: str, max_results: int = 10) -> list[dict]:
    """Perform a quick local text search across all books."""
    hits = []
    query_lower = query.lower()
    for d in sorted(vault_path.iterdir()):
        if not d.is_dir() or not d.name.startswith("Book_"):
            continue
        ext_path = d / "extractions.json"
        if not ext_path.exists():
            continue
        try:
            data = json.loads(ext_path.read_text())
        except Exception:
            continue
        for item in data:
            text = item.get("original_text", "")
            if query_lower in text.lower():
                idx = text.lower().index(query_lower)
                start = max(0, idx - 30)
                end = min(len(text), idx + len(query) + 30)
                snippet = text[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(text):
                    snippet = snippet + "..."
                hits.append({
                    "book": d.name,
                    "paragraph_id": item.get("paragraph_id", "?"),
                    "snippet": snippet,
                })
                if len(hits) >= max_results:
                    return hits
    return hits


def run_dashboard(vault_path: Path, config: Config):
    """Main TUI loop."""
    console = _console()
    books = _list_books(vault_path)

    while True:
        console.print()
        console.print(Rule("[bold blue]PPKE Terminal Dashboard[/bold blue]"))
        console.print()
        console.print(f"  Vault: {vault_path}")
        console.print(f"  Books: {len(books)}    Provider: {config.llm.provider}")
        console.print()

        console.print("  [bold]Actions:[/bold]")
        console.print("    [cyan]1[/cyan]. Browse books")
        console.print("    [cyan]2[/cyan]. View book details")
        console.print("    [cyan]3[/cyan]. Quick search")
        console.print("    [cyan]4[/cyan]. Vault statistics")
        console.print("    [cyan]5[/cyan]. Refresh")
        console.print("    [cyan]0[/cyan]. Exit")
        console.print()

        choice = click.prompt("Select", type=int, default=0)

        if choice == 0:
            console.print("Exiting dashboard.")
            break
        if choice == 1:
            if not books:
                console.print("[yellow]No books found in vault.[/yellow]")
            else:
                _show_books_table(console, books)
        elif choice == 2:
            if not books:
                console.print("[yellow]No books found in vault.[/yellow]")
                continue
            _show_books_table(console, books)
            console.print()
            idx = click.prompt("Book number (0 to cancel)", type=int, default=0)
            if 1 <= idx <= len(books):
                _show_book_detail(console, books[idx - 1])
            elif idx != 0:
                console.print("[red]Invalid selection.[/red]")
        elif choice == 3:
            query = click.prompt("Search text")
            hits = _quick_search(vault_path, query)
            if not hits:
                console.print(f'[yellow]No results for "{query}".[/yellow]')
            else:
                result_table = Table(
                    title=f'Search: "{query}" ({len(hits)} hits)',
                    border_style="dim",
                )
                result_table.add_column("Book", style="cyan", width=30)
                result_table.add_column("Para ID", width=12)
                result_table.add_column("Snippet")
                for h in hits:
                    result_table.add_row(h["book"], h["paragraph_id"], h["snippet"])
                console.print(result_table)
        elif choice == 4:
            _show_vault_stats(console, vault_path, books)
        elif choice == 5:
            books = _list_books(vault_path)
            console.print("[green]Refreshed.[/green]")
        else:
            console.print("[red]Invalid choice.[/red]")


def _show_vault_stats(console: Console, vault_path: Path, books: list[dict]):
    """Show vault-wide statistics in the TUI."""
    total_chapters = 0
    total_paragraphs = 0
    complete = 0
    incomplete = 0

    for b in books:
        total_chapters += b.get("total_chapters", 0)
        total_paragraphs += b.get("total_paragraphs", 0)
        if b.get("verification_status") == "COMPLETE":
            complete += 1
        else:
            incomplete += 1

    stats_table = Table(show_header=False, box=None, padding=(0, 1))
    stats_table.add_column("Key", style="bold")
    stats_table.add_column("Value", justify="right")
    stats_table.add_row("Books:", str(len(books)))
    stats_table.add_row("Chapters:", str(total_chapters))
    stats_table.add_row("Paragraphs:", str(total_paragraphs))
    stats_table.add_row("Complete:", str(complete))
    stats_table.add_row("Incomplete:", str(incomplete))
    stats_table.add_row("Vault:", str(vault_path))

    console.print(Panel(stats_table, title="[bold]Vault Statistics[/bold]", border_style="green"))
