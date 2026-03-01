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
# export/academic.py
# ═══════════════════════════════════════════════════════════════════


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
