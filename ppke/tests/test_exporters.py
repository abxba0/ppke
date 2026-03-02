"""Tests for ppke.export — PDF, ZIP, and academic tools."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import yaml


@pytest.fixture()
def book_dir(tmp_path):
    """Create a test book directory with all analysis files."""
    d = tmp_path / "Book_TestExport"
    d.mkdir()
    meta = {
        "title": "Export Test Book",
        "author": "Export Author",
        "year": 2025,
        "total_chapters": 5,
        "total_paragraphs": 50,
    }
    (d / "meta.yml").write_text(yaml.dump(meta))
    (d / "01_Raw_Structure.md").write_text("# Chapter 1\n\nContent here.\n\n## Section 1.1\n\nMore content.\n\n- Bullet one\n- Bullet two")
    (d / "02_Logical_Map.md").write_text("# Logical Map\n\n## Theme A\n\nThis is a substantial point about the logical structure.\n\n- Point A\n- Point B")
    (d / "03_Concept_Index.md").write_text("# Concepts\n\n- **Concept1**: definition\n- *Concept2*: definition\n- `Code`: definition")
    (d / "06_Patterns.md").write_text("# Patterns\n\n---\n\n- Pattern1 is a substantial pattern identified.\n- Pattern2 is another pattern.")
    (d / "summary.md").write_text("# Summary\n\nThis is the executive summary.\n\n- Key point one\n- Key point two\n\nThis is a longer paragraph that provides more detail about the findings.")
    (d / "study_guide.md").write_text("# Study Guide\n\n#### Topic 1\n\nStudy notes.\n\n```python\ncode block\n```")
    (d / "extractions.json").write_text(json.dumps([
        {
            "paragraph_id": "{01}.{01}",
            "topic_sentence": "First topic",
            "defined_concepts": ["concept1", "concept2"],
            "explicit_claims": ["This is a substantial claim about the topic."],
            "implicit_assumptions": ["This is a substantial underlying assumption."],
            "logical_steps": ["Step 1"],
        },
        {
            "paragraph_id": "{02}.{01}",
            "topic_sentence": "Second topic",
            "defined_concepts": ["concept3"],
            "explicit_claims": ["Another substantial claim about something else."],
            "implicit_assumptions": [],
            "logical_steps": [],
        },
    ]))
    return d


# ═══════════════════════════════════════════════════════════════════
# export/exporters.py
# ═══════════════════════════════════════════════════════════════════


class TestSharedHelpers:
    def test_load_meta_exists(self, book_dir):
        from ppke.export.exporters import _load_meta
        meta = _load_meta(book_dir)
        assert meta["title"] == "Export Test Book"

    def test_load_meta_missing(self, tmp_path):
        from ppke.export.exporters import _load_meta
        assert _load_meta(tmp_path) == {}

    def test_load_md_file(self, book_dir):
        from ppke.export.exporters import _load_md_file
        content = _load_md_file(book_dir, "summary.md")
        assert "Summary" in content

    def test_load_md_file_missing(self, tmp_path):
        from ppke.export.exporters import _load_md_file
        assert _load_md_file(tmp_path, "nonexistent.md") == ""

    def test_load_md_file_truncated(self, book_dir):
        from ppke.export.exporters import _load_md_file
        content = _load_md_file(book_dir, "summary.md", max_chars=10)
        assert len(content) == 10

    def test_load_extractions(self, book_dir):
        from ppke.export.exporters import _load_extractions
        exts = _load_extractions(book_dir)
        assert len(exts) == 2

    def test_load_extractions_missing(self, tmp_path):
        from ppke.export.exporters import _load_extractions
        assert _load_extractions(tmp_path) == []

    def test_load_extractions_invalid_json(self, tmp_path):
        from ppke.export.exporters import _load_extractions
        (tmp_path / "extractions.json").write_text("not json")
        assert _load_extractions(tmp_path) == []


class TestMdToHtml:
    def test_headings(self):
        from ppke.export.exporters import _md_to_simple_html
        html = _md_to_simple_html("# Title\n## Subtitle\n### Subsubtitle\n#### Minor")
        assert "<h1>" in html
        assert "<h2>" in html
        assert "<h3>" in html
        assert "<h4>" in html

    def test_bullets(self):
        from ppke.export.exporters import _md_to_simple_html
        html = _md_to_simple_html("- Item 1\n- Item 2\nParagraph after")
        assert "<ul>" in html
        assert "<li>" in html
        assert "</ul>" in html

    def test_code_blocks(self):
        from ppke.export.exporters import _md_to_simple_html
        html = _md_to_simple_html("```\ncode here\n```")
        assert "<pre" in html
        assert "code here" in html
        assert "</pre>" in html

    def test_horizontal_rule(self):
        from ppke.export.exporters import _md_to_simple_html
        html = _md_to_simple_html("---")
        assert "<hr>" in html

    def test_star_bullets(self):
        from ppke.export.exporters import _md_to_simple_html
        html = _md_to_simple_html("* Star item\n* Another")
        assert "<li>" in html

    def test_paragraph(self):
        from ppke.export.exporters import _md_to_simple_html
        html = _md_to_simple_html("Regular paragraph text")
        assert "<p>" in html

    def test_empty_lines(self):
        from ppke.export.exporters import _md_to_simple_html
        html = _md_to_simple_html("Line 1\n\nLine 2")
        assert html.count("") >= 0  # Just ensure no crash

    def test_unclosed_list(self):
        from ppke.export.exporters import _md_to_simple_html
        html = _md_to_simple_html("- Item 1\n- Item 2")
        assert "</ul>" in html

    def test_unclosed_code(self):
        from ppke.export.exporters import _md_to_simple_html
        html = _md_to_simple_html("```\nunclosed code")
        assert "</pre>" in html


class TestInline:
    def test_bold(self):
        from ppke.export.exporters import _inline
        assert "<strong>bold</strong>" in _inline("**bold**")

    def test_italic(self):
        from ppke.export.exporters import _inline
        assert "<em>italic</em>" in _inline("*italic*")

    def test_code(self):
        from ppke.export.exporters import _inline
        assert "<code>code</code>" in _inline("`code`")


class TestHtmlEscape:
    def test_escapes(self):
        from ppke.export.exporters import _html_escape
        assert _html_escape('<script>"test"&') == "&lt;script&gt;&quot;test&quot;&amp;"


class TestExportPdf:
    def test_pdf_fallback_html(self, book_dir):
        """Without weasyprint, should return HTML bytes."""
        from ppke.export.exporters import export_pdf
        result = export_pdf(book_dir)
        assert isinstance(result, bytes)
        html = result.decode("utf-8")
        assert "Export Test Book" in html
        assert "Export Author" in html

    def test_pdf_no_summary(self, tmp_path):
        """Should still work without optional files."""
        d = tmp_path / "Book_Minimal"
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": "Min", "author": "A"}))
        from ppke.export.exporters import export_pdf
        result = export_pdf(d)
        assert isinstance(result, bytes)


class TestExportDocx:
    def test_docx_raises_without_dependency(self, book_dir):
        """Without python-docx installed, should raise ImportError."""
        from ppke.export.exporters import export_docx
        with pytest.raises(ImportError):
            export_docx(book_dir)


class TestExportPptx:
    def test_pptx_raises_without_dependency(self, book_dir):
        """Without python-pptx installed, should raise ImportError."""
        from ppke.export.exporters import export_pptx
        with pytest.raises(ImportError):
            export_pptx(book_dir)


class TestExtractBullets:
    def test_extracts_bullets(self):
        from ppke.export.exporters import _extract_bullets
        md = "# Title\n\n- First bullet point here\n- Second bullet point here\n- Third bullet point"
        bullets = _extract_bullets(md, max_bullets=2)
        assert len(bullets) == 2
        assert "First bullet point" in bullets[0]

    def test_extracts_from_headings(self):
        from ppke.export.exporters import _extract_bullets
        md = "## Heading One Title\n\nSome text.\n\n## Heading Two Title\n\nMore text."
        bullets = _extract_bullets(md)
        assert len(bullets) >= 1

    def test_extracts_from_long_lines(self):
        from ppke.export.exporters import _extract_bullets
        md = "Short\n\nThis is a very long line that exceeds thirty characters and should be picked up."
        bullets = _extract_bullets(md)
        assert len(bullets) >= 1

    def test_cleans_inline_markdown(self):
        from ppke.export.exporters import _extract_bullets
        md = "- This has **bold** and *italic* and `code` formatting"
        bullets = _extract_bullets(md)
        assert "**" not in bullets[0]
        assert "*" not in bullets[0]

    def test_empty_text(self):
        from ppke.export.exporters import _extract_bullets
        assert _extract_bullets("") == []


class TestExportMarkdownZip:
    def test_zip_contents(self, book_dir):
        from ppke.export.exporters import export_markdown_zip
        result = export_markdown_zip(book_dir)
        assert isinstance(result, bytes)

        zf = zipfile.ZipFile(BytesIO(result))
        names = zf.namelist()
        assert any("meta.yml" in n for n in names)
        assert any("01_Raw_Structure.md" in n for n in names)
        assert any("summary.md" in n for n in names)
        assert any("extractions.json" in n for n in names)


# ═══════════════════════════════════════════════════════════════════
# export/exporters.py — LaTeX export
# ═══════════════════════════════════════════════════════════════════


class TestLatexEscape:
    def test_ampersand(self):
        from ppke.export.exporters import _latex_escape
        assert _latex_escape("A & B") == "A \\& B"

    def test_percent(self):
        from ppke.export.exporters import _latex_escape
        assert _latex_escape("100%") == "100\\%"

    def test_underscore(self):
        from ppke.export.exporters import _latex_escape
        assert _latex_escape("some_var") == "some\\_var"

    def test_dollar(self):
        from ppke.export.exporters import _latex_escape
        assert _latex_escape("$price") == "\\$price"

    def test_hash(self):
        from ppke.export.exporters import _latex_escape
        assert _latex_escape("#1") == "\\#1"


class TestInlineLatex:
    def test_bold(self):
        from ppke.export.exporters import _inline_latex
        result = _inline_latex("**bold text**")
        assert "\\textbf{bold text}" in result

    def test_italic(self):
        from ppke.export.exporters import _inline_latex
        result = _inline_latex("*italic text*")
        assert "\\textit{italic text}" in result

    def test_code(self):
        from ppke.export.exporters import _inline_latex
        result = _inline_latex("`code`")
        assert "\\texttt{code}" in result


class TestMdToLatex:
    def test_section_heading(self):
        from ppke.export.exporters import _md_to_latex
        result = _md_to_latex("# Title")
        assert "\\section{Title}" in result

    def test_subsection_heading(self):
        from ppke.export.exporters import _md_to_latex
        result = _md_to_latex("## Subtitle")
        assert "\\subsection{Subtitle}" in result

    def test_subsubsection_heading(self):
        from ppke.export.exporters import _md_to_latex
        result = _md_to_latex("### Sub")
        assert "\\subsubsection{Sub}" in result

    def test_paragraph_heading(self):
        from ppke.export.exporters import _md_to_latex
        result = _md_to_latex("#### Para")
        assert "\\paragraph{Para}" in result

    def test_itemize_list(self):
        from ppke.export.exporters import _md_to_latex
        result = _md_to_latex("- Item one\n- Item two")
        assert "\\begin{itemize}" in result
        assert "\\item Item one" in result
        assert "\\end{itemize}" in result

    def test_code_block(self):
        from ppke.export.exporters import _md_to_latex
        result = _md_to_latex("```\ncode here\n```")
        assert "\\begin{verbatim}" in result
        assert "code here" in result
        assert "\\end{verbatim}" in result

    def test_horizontal_rule(self):
        from ppke.export.exporters import _md_to_latex
        result = _md_to_latex("---")
        assert "\\hrule" in result

    def test_empty_line(self):
        from ppke.export.exporters import _md_to_latex
        result = _md_to_latex("Line 1\n\nLine 2")
        assert "Line 1" in result
        assert "Line 2" in result

    def test_unclosed_list(self):
        from ppke.export.exporters import _md_to_latex
        result = _md_to_latex("- Only item")
        assert "\\end{itemize}" in result

    def test_unclosed_code(self):
        from ppke.export.exporters import _md_to_latex
        result = _md_to_latex("```\nunclosed")
        assert "\\end{verbatim}" in result


class TestExportLatex:
    def test_returns_bytes(self, book_dir):
        from ppke.export.exporters import export_latex
        result = export_latex(book_dir)
        assert isinstance(result, bytes)

    def test_contains_document_structure(self, book_dir):
        from ppke.export.exporters import export_latex
        tex = export_latex(book_dir).decode("utf-8")
        assert "\\documentclass" in tex
        assert "\\begin{document}" in tex
        assert "\\end{document}" in tex
        assert "\\maketitle" in tex
        assert "\\tableofcontents" in tex

    def test_contains_metadata(self, book_dir):
        from ppke.export.exporters import export_latex
        tex = export_latex(book_dir).decode("utf-8")
        assert "Export Test Book" in tex
        assert "Export Author" in tex
        assert "2025" in tex

    def test_minimal_book(self, tmp_path):
        from ppke.export.exporters import export_latex
        d = tmp_path / "Book_Minimal"
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": "Min Book", "author": "A. Author"}))
        result = export_latex(d)
        assert b"\\documentclass" in result
        assert b"Min Book" in result

    def test_no_meta(self, tmp_path):
        from ppke.export.exporters import export_latex
        d = tmp_path / "Book_NoMeta"
        d.mkdir()
        result = export_latex(d)
        assert isinstance(result, bytes)
        assert b"\\documentclass" in result

    def test_today_date_when_no_year(self, tmp_path):
        from ppke.export.exporters import export_latex
        d = tmp_path / "Book_NoYear"
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": "No Year", "author": "Auth"}))
        tex = export_latex(d).decode("utf-8")
        assert "\\today" in tex

    def test_year_used_when_present(self, book_dir):
        from ppke.export.exporters import export_latex
        tex = export_latex(book_dir).decode("utf-8")
        assert "\\today" not in tex
        assert "2025" in tex


# ═══════════════════════════════════════════════════════════════════
# export/exporters.py — BibTeX export
# ═══════════════════════════════════════════════════════════════════


class TestMakeCiteKey:
    def test_basic(self):
        from ppke.export.exporters import _make_cite_key
        key = _make_cite_key({"author": "Smith, J.", "year": 2025})
        assert key == "Smith2025"

    def test_no_year(self):
        from ppke.export.exporters import _make_cite_key
        key = _make_cite_key({"author": "Doe"})
        assert key == "Doe"

    def test_no_author(self):
        from ppke.export.exporters import _make_cite_key
        key = _make_cite_key({"year": 2020})
        assert "Unknown" in key

    def test_space_separated_author(self):
        from ppke.export.exporters import _make_cite_key
        key = _make_cite_key({"author": "John Doe", "year": 2000})
        assert key.startswith("John")


class TestBibtexEscape:
    def test_backslash_left_as_is(self):
        from ppke.export.exporters import _bibtex_escape
        # Backslashes are intentionally left as-is (LaTeX commands)
        result = _bibtex_escape("a\\b")
        assert "a\\b" in result

    def test_braces(self):
        from ppke.export.exporters import _bibtex_escape
        result = _bibtex_escape("{test}")
        assert "\\{" in result
        assert "\\}" in result


class TestMetaToBibtexEntry:
    def test_basic_fields(self):
        from ppke.export.exporters import meta_to_bibtex_entry
        meta = {"title": "Test Book", "author": "Smith, J.", "year": 2025}
        entry = meta_to_bibtex_entry(meta)
        assert "@book{" in entry
        assert "title" in entry
        assert "Test Book" in entry
        assert "author" in entry
        assert "Smith" in entry
        assert "year" in entry
        assert "2025" in entry

    def test_custom_cite_key(self):
        from ppke.export.exporters import meta_to_bibtex_entry
        meta = {"title": "T", "author": "A", "year": 2020}
        entry = meta_to_bibtex_entry(meta, cite_key="CustomKey2020")
        assert "@book{CustomKey2020," in entry

    def test_optional_fields(self):
        from ppke.export.exporters import meta_to_bibtex_entry
        meta = {
            "title": "T",
            "author": "A",
            "year": 2020,
            "publisher": "Publisher Co",
            "isbn": "978-0-000-00000-0",
            "doi": "10.1234/test",
            "url": "https://example.com",
            "language": "English",
            "domain": "philosophy",
        }
        entry = meta_to_bibtex_entry(meta)
        assert "publisher" in entry
        assert "Publisher Co" in entry
        assert "isbn" in entry
        assert "doi" in entry
        assert "url" in entry
        assert "language" in entry
        assert "note" in entry
        assert "philosophy" in entry

    def test_empty_meta(self):
        from ppke.export.exporters import meta_to_bibtex_entry
        entry = meta_to_bibtex_entry({})
        assert "@book{" in entry


class TestExportBibtex:
    def test_returns_bytes(self, book_dir):
        from ppke.export.exporters import export_bibtex
        result = export_bibtex(book_dir)
        assert isinstance(result, bytes)

    def test_contains_book_entry(self, book_dir):
        from ppke.export.exporters import export_bibtex
        bib = export_bibtex(book_dir).decode("utf-8")
        assert "@book{" in bib
        assert "Export Test Book" in bib
        assert "Export Author" in bib

    def test_header_comment(self, book_dir):
        from ppke.export.exporters import export_bibtex
        bib = export_bibtex(book_dir).decode("utf-8")
        assert "% BibTeX export generated by PPKE" in bib

    def test_minimal_book(self, tmp_path):
        from ppke.export.exporters import export_bibtex
        d = tmp_path / "Book_Min"
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": "Minimal", "author": "Auth"}))
        result = export_bibtex(d)
        assert b"@book{" in result

    def test_no_meta(self, tmp_path):
        from ppke.export.exporters import export_bibtex
        d = tmp_path / "Book_NoMeta"
        d.mkdir()
        result = export_bibtex(d)
        assert isinstance(result, bytes)
        assert b"@book{" in result


# ═══════════════════════════════════════════════════════════════════
# export/academic.py — BibTeX bibliography export
# ═══════════════════════════════════════════════════════════════════


class TestExportBibliographyBibtex:
    def test_basic_export(self, tmp_path):
        from ppke.export.academic import export_bibliography_bibtex
        vault = tmp_path / "vault"
        vault.mkdir()
        b1 = vault / "Book_A"
        b1.mkdir()
        (b1 / "meta.yml").write_text(yaml.dump({"title": "Alpha", "author": "AA", "year": 2020}))
        b2 = vault / "Book_B"
        b2.mkdir()
        (b2 / "meta.yml").write_text(yaml.dump({"title": "Beta", "author": "BB", "year": 2021}))

        result = export_bibliography_bibtex(vault)
        assert "@book{" in result
        assert "Alpha" in result
        assert "Beta" in result
        assert "2 entries" in result

    def test_empty_vault(self, tmp_path):
        from ppke.export.academic import export_bibliography_bibtex
        vault = tmp_path / "empty"
        vault.mkdir()
        result = export_bibliography_bibtex(vault)
        assert "No books found" in result
        assert "0 entries" in result

    def test_nonexistent_vault(self):
        from ppke.export.academic import export_bibliography_bibtex
        from pathlib import Path
        result = export_bibliography_bibtex(Path("/nonexistent/path"))
        assert "0 entries" in result

    def test_specific_folders(self, tmp_path):
        from ppke.export.academic import export_bibliography_bibtex
        vault = tmp_path / "vault"
        vault.mkdir()
        b1 = vault / "Book_A"
        b1.mkdir()
        (b1 / "meta.yml").write_text(yaml.dump({"title": "Alpha", "author": "AA"}))
        b2 = vault / "Book_B"
        b2.mkdir()
        (b2 / "meta.yml").write_text(yaml.dump({"title": "Beta", "author": "BB"}))

        result = export_bibliography_bibtex(vault, book_folders=["Book_A"])
        assert "Alpha" in result
        assert "Beta" not in result

    def test_unique_cite_keys(self, tmp_path):
        from ppke.export.academic import export_bibliography_bibtex
        vault = tmp_path / "vault"
        vault.mkdir()
        # Two books with the same author and year → should get unique cite keys
        b1 = vault / "Book_A"
        b1.mkdir()
        (b1 / "meta.yml").write_text(yaml.dump({"title": "A1", "author": "Smith", "year": 2020}))
        b2 = vault / "Book_B"
        b2.mkdir()
        (b2 / "meta.yml").write_text(yaml.dump({"title": "A2", "author": "Smith", "year": 2020}))

        result = export_bibliography_bibtex(vault)
        # Both entries are present
        assert result.count("@book{") == 2
        # First entry uses the base key, second uses a numeric suffix
        assert "@book{Smith2020," in result
        assert "@book{Smith2020_2," in result


class TestCitations:
    def test_apa(self):
        from ppke.export.academic import format_citation_apa
        meta = {"author": "Smith, J.", "title": "Test Book", "year": 2025}
        result = format_citation_apa(meta)
        assert "Smith" in result
        assert "2025" in result
        assert "*Test Book*" in result

    def test_apa_defaults(self):
        from ppke.export.academic import format_citation_apa
        result = format_citation_apa({})
        assert "Unknown" in result
        assert "n.d." in result

    def test_mla(self):
        from ppke.export.academic import format_citation_mla
        meta = {"author": "Doe, J.", "title": "Research Paper", "year": 2024}
        result = format_citation_mla(meta)
        assert "Doe" in result
        assert "*Research Paper*" in result
        assert "2024" in result

    def test_mla_no_year(self):
        from ppke.export.academic import format_citation_mla
        result = format_citation_mla({"author": "A", "title": "T"})
        assert "A." in result

    def test_chicago(self):
        from ppke.export.academic import format_citation_chicago
        meta = {"author": "Adams", "title": "Hitchhiker", "year": 1979}
        result = format_citation_chicago(meta)
        assert "Adams" in result
        assert "*Hitchhiker*" in result

    def test_chicago_no_year(self):
        from ppke.export.academic import format_citation_chicago
        result = format_citation_chicago({"author": "A", "title": "T"})
        assert "A." in result


class TestBibliography:
    def test_generate_bibliography(self, tmp_path):
        from ppke.export.academic import generate_bibliography
        vault = tmp_path / "vault"
        vault.mkdir()
        b1 = vault / "Book_A"
        b1.mkdir()
        (b1 / "meta.yml").write_text(yaml.dump({"title": "Alpha", "author": "AA", "year": 2020}))
        b2 = vault / "Book_B"
        b2.mkdir()
        (b2 / "meta.yml").write_text(yaml.dump({"title": "Beta", "author": "BB", "year": 2021}))

        result = generate_bibliography(vault, "apa")
        assert "# Bibliography" in result
        assert "AA" in result
        assert "BB" in result
        assert "2 sources" in result

    def test_bibliography_mla(self, tmp_path):
        from ppke.export.academic import generate_bibliography
        vault = tmp_path / "vault"
        vault.mkdir()
        b = vault / "Book_X"
        b.mkdir()
        (b / "meta.yml").write_text(yaml.dump({"title": "X", "author": "Auth"}))
        result = generate_bibliography(vault, "mla")
        assert "MLA" in result

    def test_bibliography_chicago(self, tmp_path):
        from ppke.export.academic import generate_bibliography
        vault = tmp_path / "vault"
        vault.mkdir()
        b = vault / "Book_Y"
        b.mkdir()
        (b / "meta.yml").write_text(yaml.dump({"title": "Y", "author": "Auth", "year": 2020}))
        result = generate_bibliography(vault, "chicago")
        assert "Chicago" in result

    def test_bibliography_empty_vault(self, tmp_path):
        from ppke.export.academic import generate_bibliography
        vault = tmp_path / "empty"
        vault.mkdir()
        result = generate_bibliography(vault)
        assert "No books found" in result

    def test_bibliography_specific_folders(self, tmp_path):
        from ppke.export.academic import generate_bibliography
        vault = tmp_path / "vault"
        vault.mkdir()
        b1 = vault / "Book_A"
        b1.mkdir()
        (b1 / "meta.yml").write_text(yaml.dump({"title": "A", "author": "AA"}))
        b2 = vault / "Book_B"
        b2.mkdir()
        (b2 / "meta.yml").write_text(yaml.dump({"title": "B", "author": "BB"}))

        result = generate_bibliography(vault, book_folders=["Book_A"])
        assert "AA" in result
        assert "BB" not in result

    def test_bibliography_nonexistent_vault(self):
        from ppke.export.academic import generate_bibliography
        from pathlib import Path
        result = generate_bibliography(Path("/nonexistent/path"))
        assert "No books found" in result


class TestLiteratureReview:
    def test_no_books(self, tmp_path):
        from ppke.export.academic import generate_literature_review
        vault = tmp_path / "empty"
        vault.mkdir()
        result = generate_literature_review(vault, MagicMock())
        assert "No books available" in result

    def test_with_books(self, tmp_path):
        from ppke.export.academic import generate_literature_review
        from unittest.mock import MagicMock
        vault = tmp_path / "vault"
        vault.mkdir()
        b = vault / "Book_T"
        b.mkdir()
        (b / "meta.yml").write_text(yaml.dump({"title": "Test", "author": "Auth", "year": 2025}))
        (b / "summary.md").write_text("Summary content")
        (b / "03_Concept_Index.md").write_text("# Concepts\n\n- C1")
        (b / "02_Logical_Map.md").write_text("# Logic\n\n- L1")
        (b / "06_Patterns.md").write_text("# Patterns\n\n- P1")

        mock_llm = MagicMock()
        mock_llm.complete.return_value = "# Literature Review\n\n## Introduction\n\nTest review."
        result = generate_literature_review(vault, mock_llm)
        assert "Literature Review" in result


class TestArgumentMap:
    def test_generate_argument_map(self, book_dir):
        from ppke.export.academic import generate_argument_map
        result = generate_argument_map(book_dir)
        assert "nodes" in result
        assert "edges" in result
        assert "stats" in result
        assert result["title"] == "Export Test Book"
        assert len(result["nodes"]) > 0

    def test_argument_map_empty(self, tmp_path):
        from ppke.export.academic import generate_argument_map
        d = tmp_path / "Book_Empty"
        d.mkdir()
        result = generate_argument_map(d)
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_argument_map_to_markdown(self, book_dir):
        from ppke.export.academic import generate_argument_map, argument_map_to_markdown
        arg_map = generate_argument_map(book_dir)
        md = argument_map_to_markdown(arg_map)
        assert "# Argument Map" in md
        assert "Export Test Book" in md

    def test_argument_map_to_markdown_empty(self):
        from ppke.export.academic import argument_map_to_markdown
        md = argument_map_to_markdown({"title": "Empty", "nodes": [], "edges": [], "stats": {}})
        assert "# Argument Map: Empty" in md


# Import for MagicMock in test_with_books
from unittest.mock import MagicMock
