"""Zotero import — parse BibTeX (.bib), CSL JSON, and Zotero RDF (.rdf) to Markdown.

Supports the three most common Zotero export formats.  Each parser
extracts bibliographic entries into a uniform intermediate dict and then
renders them as a Markdown document suitable for the PPKE ingestion
pipeline.

No external dependencies are required — uses only the Python standard
library (``re``, ``json``, ``xml.etree.ElementTree``).
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Intermediate representation
# ------------------------------------------------------------------

def _entry_to_dict(
    *,
    entry_type: str = "",
    cite_key: str = "",
    title: str = "",
    author: str = "",
    year: str = "",
    abstract: str = "",
    journal: str = "",
    volume: str = "",
    number: str = "",
    pages: str = "",
    publisher: str = "",
    doi: str = "",
    url: str = "",
    isbn: str = "",
    keywords: str = "",
    note: str = "",
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return a normalised bibliographic entry dict."""
    d: dict[str, str] = {}
    if entry_type:
        d["type"] = entry_type
    if cite_key:
        d["cite_key"] = cite_key
    if title:
        d["title"] = title
    if author:
        d["author"] = author
    if year:
        d["year"] = year
    if abstract:
        d["abstract"] = abstract
    if journal:
        d["journal"] = journal
    if volume:
        d["volume"] = volume
    if number:
        d["number"] = number
    if pages:
        d["pages"] = pages
    if publisher:
        d["publisher"] = publisher
    if doi:
        d["doi"] = doi
    if url:
        d["url"] = url
    if isbn:
        d["isbn"] = isbn
    if keywords:
        d["keywords"] = keywords
    if note:
        d["note"] = note
    if extra:
        d.update(extra)
    return d


# ------------------------------------------------------------------
# BibTeX parser
# ------------------------------------------------------------------

# Matches @type{key, ... } blocks (greedy-safe because we track braces).
_ENTRY_RE = re.compile(r"@(\w+)\s*\{", re.IGNORECASE)


def _parse_bibtex_entries(text: str) -> list[dict[str, str]]:
    """Parse BibTeX text into a list of entry dicts."""
    entries: list[dict[str, str]] = []
    pos = 0
    while pos < len(text):
        m = _ENTRY_RE.search(text, pos)
        if m is None:
            break
        entry_type = m.group(1).lower()
        start = m.end()  # just after the opening '{'

        # Find the matching closing brace
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start:i - 1]
        pos = i

        # Skip preamble / comment / string
        if entry_type in ("preamble", "comment", "string"):
            continue

        # Extract cite key (everything before the first comma)
        comma_idx = body.find(",")
        if comma_idx == -1:
            continue
        cite_key = body[:comma_idx].strip()
        fields_text = body[comma_idx + 1:]

        fields = _parse_bibtex_fields(fields_text)
        entries.append(
            _entry_to_dict(
                entry_type=entry_type,
                cite_key=cite_key,
                title=fields.get("title", ""),
                author=fields.get("author", ""),
                year=fields.get("year", fields.get("date", "")),
                abstract=fields.get("abstract", ""),
                journal=fields.get("journal", fields.get("journaltitle", "")),
                volume=fields.get("volume", ""),
                number=fields.get("number", ""),
                pages=fields.get("pages", ""),
                publisher=fields.get("publisher", ""),
                doi=fields.get("doi", ""),
                url=fields.get("url", ""),
                isbn=fields.get("isbn", ""),
                keywords=fields.get("keywords", ""),
                note=fields.get("note", fields.get("annote", "")),
            )
        )

    return entries


def _parse_bibtex_fields(text: str) -> dict[str, str]:
    """Extract key = {value} or key = "value" pairs from a BibTeX body."""
    fields: dict[str, str] = {}
    i = 0
    length = len(text)
    while i < length:
        # Skip whitespace and commas
        while i < length and text[i] in " \t\n\r,":
            i += 1
        if i >= length:
            break

        # Read field name
        eq = text.find("=", i)
        if eq == -1:
            break
        key = text[i:eq].strip().lower()
        i = eq + 1

        # Skip whitespace
        while i < length and text[i] in " \t\n\r":
            i += 1
        if i >= length:
            break

        # Read value
        if text[i] == "{":
            # Brace-delimited value
            depth = 1
            start = i + 1
            i += 1
            while i < length and depth > 0:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1
            value = text[start:i - 1]
        elif text[i] == '"':
            # Quote-delimited value
            start = i + 1
            i += 1
            while i < length and text[i] != '"':
                i += 1
            value = text[start:i]
            i += 1  # skip closing quote
        else:
            # Bare value (number or macro)
            start = i
            while i < length and text[i] not in ",} \t\n\r":
                i += 1
            value = text[start:i]

        # Clean up LaTeX artefacts
        value = _clean_latex(value)
        if key:
            fields[key] = value

    return fields


def _clean_latex(text: str) -> str:
    """Remove common LaTeX formatting from a BibTeX value."""
    text = re.sub(r"\\['\"`^~.=]?\{(\w)\}", r"\1", text)  # accented chars
    text = re.sub(r"\{([^}]*)\}", r"\1", text)  # remove braces
    text = re.sub(r"\\(text\w+|emph|it|bf)\{([^}]*)\}", r"\2", text)
    text = re.sub(r"\\&", "&", text)
    text = re.sub(r"~", " ", text)
    text = re.sub(r"--", "–", text)
    return text.strip()


# ------------------------------------------------------------------
# CSL JSON parser
# ------------------------------------------------------------------


def _parse_csl_json(text: str) -> list[dict[str, str]]:
    """Parse CSL JSON (array of items) into entry dicts."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if isinstance(data, dict):
        # Zotero sometimes wraps items in {"items": [...]}
        data = data.get("items", [data])
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of bibliographic items")

    entries: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        # Authors
        authors: list[str] = []
        for a in item.get("author", []):
            parts: list[str] = []
            if a.get("family"):
                parts.append(a["family"])
            if a.get("given"):
                parts.insert(0, a["given"])
            if parts:
                authors.append(" ".join(parts))
            elif a.get("literal"):
                authors.append(a["literal"])
        author_str = "; ".join(authors)

        # Year / date
        year = ""
        issued = item.get("issued", {})
        if isinstance(issued, dict):
            date_parts = issued.get("date-parts", [[]])
            if date_parts and date_parts[0]:
                year = str(date_parts[0][0])
        if not year:
            year = str(item.get("year", ""))

        entries.append(
            _entry_to_dict(
                entry_type=item.get("type", ""),
                cite_key=item.get("id", item.get("citation-key", "")),
                title=item.get("title", ""),
                author=author_str,
                year=year,
                abstract=item.get("abstract", ""),
                journal=item.get("container-title", ""),
                volume=str(item.get("volume", "")),
                number=str(item.get("issue", item.get("number", ""))),
                pages=item.get("page", ""),
                publisher=item.get("publisher", ""),
                doi=item.get("DOI", ""),
                url=item.get("URL", ""),
                isbn=item.get("ISBN", ""),
                keywords="; ".join(item.get("keyword", item.get("keywords", "")) if isinstance(item.get("keyword", item.get("keywords", "")), list) else [item.get("keyword", item.get("keywords", ""))]),
                note=item.get("note", ""),
            )
        )

    return entries


# ------------------------------------------------------------------
# Zotero RDF parser
# ------------------------------------------------------------------

_RDF_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "z": "http://www.zotero.org/namespaces/export#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "bib": "http://purl.org/net/biblio#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "prism": "http://prismstandard.org/namespaces/1.2/basic/",
}


def _text(el: ET.Element | None) -> str:
    """Return stripped text content or empty string."""
    return (el.text or "").strip() if el is not None else ""


def _parse_rdf(text: str) -> list[dict[str, str]]:
    """Parse Zotero RDF/XML into entry dicts."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML/RDF: {exc}") from exc

    entries: list[dict[str, str]] = []

    # Zotero RDF exports items as bib:* elements inside rdf:RDF
    for item in root:
        tag = item.tag
        # Strip namespace
        if "}" in tag:
            tag = tag.split("}", 1)[1]

        # Extract fields using Dublin Core / Zotero namespaces
        title = _text(item.find("dc:title", _RDF_NS))
        if not title:
            # Try without namespace
            title = _text(item.find("title"))
        if not title:
            continue  # skip items without a title

        # Authors
        authors: list[str] = []
        for creator in item.findall("bib:authors/rdf:Seq/rdf:li/foaf:Person", _RDF_NS):
            surname = _text(creator.find("foaf:surname", _RDF_NS))
            given = _text(creator.find("foaf:givenName", _RDF_NS))
            if surname or given:
                authors.append(f"{given} {surname}".strip())
        # Fallback: dc:creator
        if not authors:
            for c in item.findall("dc:creator", _RDF_NS):
                if c.text and c.text.strip():
                    authors.append(c.text.strip())
        author_str = "; ".join(authors)

        year = _text(item.find("dc:date", _RDF_NS))
        if year and len(year) >= 4:
            year = year[:4]

        abstract = _text(item.find("dcterms:abstract", _RDF_NS))
        journal = _text(item.find("dcterms:isPartOf/bib:Journal/dc:title", _RDF_NS))
        volume = _text(item.find("prism:volume", _RDF_NS))
        pages = _text(item.find("bib:pages", _RDF_NS))
        publisher = _text(item.find("dc:publisher", _RDF_NS))
        doi = _text(item.find("dc:identifier", _RDF_NS))
        url = item.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
        isbn = _text(item.find("dc:identifier[@scheme='ISBN']", _RDF_NS)) if item.find("dc:identifier[@scheme='ISBN']", _RDF_NS) is not None else ""

        entry_type = tag.lower() if tag else ""

        entries.append(
            _entry_to_dict(
                entry_type=entry_type,
                title=title,
                author=author_str,
                year=year,
                abstract=abstract,
                journal=journal,
                volume=volume,
                pages=pages,
                publisher=publisher,
                doi=doi,
                url=url,
                isbn=isbn,
            )
        )

    return entries


# ------------------------------------------------------------------
# Format detection + unified parsing
# ------------------------------------------------------------------


def detect_format(path: Path) -> str:
    """Detect Zotero export format from file extension and content.

    Returns one of ``"bibtex"``, ``"csl-json"``, or ``"rdf"``.
    Raises ``ValueError`` for unrecognised formats.
    """
    ext = path.suffix.lower()
    if ext == ".bib":
        return "bibtex"
    if ext == ".rdf":
        return "rdf"
    if ext == ".json":
        return "csl-json"

    # Sniff content
    content = path.read_text(encoding="utf-8", errors="replace")[:500]
    if content.lstrip().startswith("@"):
        return "bibtex"
    if content.lstrip().startswith(("[", "{")):
        return "csl-json"
    if content.lstrip().startswith("<"):
        return "rdf"

    raise ValueError(
        f"Cannot detect Zotero format for '{path.name}'. "
        "Supported: .bib (BibTeX), .json (CSL JSON), .rdf (Zotero RDF)"
    )


def parse_zotero_file(path: Path) -> list[dict[str, str]]:
    """Parse a Zotero export file and return a list of entry dicts.

    Auto-detects format from extension / content.
    """
    fmt = detect_format(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    if fmt == "bibtex":
        return _parse_bibtex_entries(text)
    elif fmt == "csl-json":
        return _parse_csl_json(text)
    elif fmt == "rdf":
        return _parse_rdf(text)
    else:
        raise ValueError(f"Unsupported format: {fmt}")


# ------------------------------------------------------------------
# Deduplication
# ------------------------------------------------------------------


def deduplicate_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove duplicate entries based on title + author normalisation."""
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for entry in entries:
        key = (
            re.sub(r"\s+", " ", entry.get("title", "")).strip().lower()
            + "|"
            + re.sub(r"\s+", " ", entry.get("author", "")).strip().lower()
        )
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


# ------------------------------------------------------------------
# Markdown rendering
# ------------------------------------------------------------------


def entries_to_markdown(entries: list[dict[str, str]], *, source_name: str = "Zotero Library") -> str:
    """Render a list of bibliographic entries as a Markdown document."""
    if not entries:
        return f"# {source_name}\n\n*(No entries found)*"

    lines: list[str] = [f"# {source_name}", ""]
    lines.append(f"*{len(entries)} entries imported from Zotero.*\n")

    for i, entry in enumerate(entries, 1):
        title = entry.get("title", "Untitled")
        lines.append(f"## {i}. {title}")
        lines.append("")

        # Metadata table
        meta_fields = [
            ("Author", "author"),
            ("Year", "year"),
            ("Type", "type"),
            ("Journal", "journal"),
            ("Volume", "volume"),
            ("Number", "number"),
            ("Pages", "pages"),
            ("Publisher", "publisher"),
            ("DOI", "doi"),
            ("URL", "url"),
            ("ISBN", "isbn"),
            ("Keywords", "keywords"),
            ("Cite Key", "cite_key"),
        ]
        for label, key in meta_fields:
            val = entry.get(key, "")
            if val:
                lines.append(f"- **{label}:** {val}")

        if entry.get("abstract"):
            lines.append("")
            lines.append(f"**Abstract:** {entry['abstract']}")

        if entry.get("note"):
            lines.append("")
            lines.append(f"**Notes:** {entry['note']}")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------------------
# High-level API (used by registry converters)
# ------------------------------------------------------------------


def convert_zotero_file(path: Path) -> str:
    """Parse a Zotero export file and return Markdown.

    This is the main entry point used by ``@register`` in the converter
    registry.
    """
    entries = parse_zotero_file(path)
    entries = deduplicate_entries(entries)
    source_name = path.stem.replace("_", " ").replace("-", " ").title()
    logger.info("Parsed %d entries from %s", len(entries), path.name)
    return entries_to_markdown(entries, source_name=source_name)
