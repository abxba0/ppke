"""Tests for ppke.converter — registry, format converters, OCR, URL, YouTube."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════
# converter/registry.py
# ═══════════════════════════════════════════════════════════════════


class TestRegistry:
    def test_supported_extensions(self):
        from ppke.converter.registry import SUPPORTED_EXTENSIONS
        assert ".md" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".csv" in SUPPORTED_EXTENSIONS
        assert ".tex" in SUPPORTED_EXTENSIONS
        assert ".zip" in SUPPORTED_EXTENSIONS

    def test_register_decorator(self):
        from ppke.converter.registry import _CONVERTERS
        # .md should be registered
        assert ".md" in _CONVERTERS
        assert ".txt" in _CONVERTERS

    def test_convert_markdown(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "test.md"
        f.write_text("# Hello\n\nWorld")
        result = convert_to_markdown(f)
        assert "Hello" in result
        assert "World" in result

    def test_convert_text(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "notes.txt"
        f.write_text("Some plain text content.")
        result = convert_to_markdown(f)
        assert "# Notes" in result or "# notes" in result.lower()
        assert "Some plain text content." in result

    def test_convert_unsupported(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "test.xyz"
        f.write_text("data")
        with pytest.raises(ValueError, match="Unsupported"):
            convert_to_markdown(f)

    def test_convert_csv(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "data.csv"
        with open(f, "w", newline="") as csvf:
            writer = csv.writer(csvf)
            writer.writerow(["Name", "Age", "City"])
            writer.writerow(["Alice", "30", "NYC"])
            writer.writerow(["Bob", "25", "LA"])
        result = convert_to_markdown(f)
        assert "| Name |" in result
        assert "Alice" in result
        assert "Bob" in result

    def test_convert_csv_empty(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "empty.csv"
        f.write_text("")
        result = convert_to_markdown(f)
        assert "empty" in result.lower()

    def test_convert_csv_pipe_escaping(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "pipe.csv"
        with open(f, "w", newline="") as csvf:
            writer = csv.writer(csvf)
            writer.writerow(["Header"])
            writer.writerow(["value|with|pipes"])
        result = convert_to_markdown(f)
        assert "\\|" in result

    def test_convert_pdf_requires_fitz(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        with pytest.raises(ImportError):
            convert_to_markdown(f)

    def test_convert_docx_requires_docx(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "test.docx"
        f.write_bytes(b"fake docx")
        with pytest.raises((ImportError, Exception)):
            convert_to_markdown(f)

    def test_convert_epub_requires_ebooklib(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "test.epub"
        f.write_bytes(b"fake epub")
        with pytest.raises((ImportError, Exception)):
            convert_to_markdown(f)

    def test_convert_html_requires_bs4(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "test.html"
        f.write_text("<html><body>Hello</body></html>")
        with pytest.raises(ImportError):
            convert_to_markdown(f)

    def test_convert_excel_requires_openpyxl(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "test.xlsx"
        f.write_bytes(b"fake xlsx")
        with pytest.raises((ImportError, Exception)):
            convert_to_markdown(f)

    def test_convert_pptx_requires_pptx(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "test.pptx"
        f.write_bytes(b"fake pptx")
        with pytest.raises((ImportError, Exception)):
            convert_to_markdown(f)


class TestLatexConverter:
    def test_latex_regex_fallback(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "paper.tex"
        f.write_text(r"""
\documentclass{article}
\begin{document}
\section{Introduction}
This is the \emph{introduction} with \textbf{bold} text.
\subsection{Background}
Background content.
\end{document}
""")
        result = convert_to_markdown(f)
        assert "Introduction" in result
        assert "introduction" in result
        assert "bold" in result

    def test_latex_no_document(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown
        f = tmp_path / "fragment.tex"
        f.write_text(r"\section{Hello} Some content with \textit{emphasis}.")
        result = convert_to_markdown(f)
        assert "Hello" in result
        assert "emphasis" in result


class TestZipConverter:
    def test_zip_with_supported_files(self, tmp_path):
        import zipfile
        from ppke.converter.registry import convert_to_markdown
        zpath = tmp_path / "archive.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("readme.md", "# Hello\n\nTest content.")
            zf.writestr("notes.txt", "Plain text.")
        result = convert_to_markdown(zpath)
        assert "Hello" in result
        assert "Plain text." in result

    def test_zip_no_supported_files(self, tmp_path):
        import zipfile
        from ppke.converter.registry import convert_to_markdown
        zpath = tmp_path / "empty.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("binary.dat", "binary data")
        with pytest.raises(ValueError, match="no supported files"):
            convert_to_markdown(zpath)

    def test_zip_skips_hidden_files(self, tmp_path):
        import zipfile
        from ppke.converter.registry import convert_to_markdown
        zpath = tmp_path / "test.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr(".hidden.md", "# Hidden")
            zf.writestr("visible.md", "# Visible")
        result = convert_to_markdown(zpath)
        assert "Visible" in result


# ═══════════════════════════════════════════════════════════════════
# converter/zotero.py
# ═══════════════════════════════════════════════════════════════════


class TestZoteroConverter:
    def test_bibtex_basic(self, tmp_path):
        from ppke.converter.zotero import parse_zotero_file, entries_to_markdown
        f = tmp_path / "refs.bib"
        f.write_text("""@article{smith2020,
  author = {John Smith and Jane Doe},
  title = {A Study on Knowledge Engines},
  journal = {Journal of AI},
  year = {2020},
  volume = {15},
  pages = {100--120},
  doi = {10.1234/jai.2020.001}
}

@book{jones2019,
  author = {Bob Jones},
  title = {Introduction to NLP},
  publisher = {Academic Press},
  year = {2019}
}
""")
        entries = parse_zotero_file(f)
        assert len(entries) == 2
        assert entries[0]["title"] == "A Study on Knowledge Engines"
        assert entries[0]["author"] == "John Smith and Jane Doe"
        assert entries[0]["year"] == "2020"
        assert entries[1]["title"] == "Introduction to NLP"
        md = entries_to_markdown(entries)
        assert "A Study on Knowledge Engines" in md
        assert "Introduction to NLP" in md
        assert "2 entries" in md

    def test_bibtex_via_registry(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown, SUPPORTED_EXTENSIONS
        assert ".bib" in SUPPORTED_EXTENSIONS
        f = tmp_path / "test.bib"
        f.write_text('@article{k1, author={Alice}, title={Test Title}, year={2021}}')
        result = convert_to_markdown(f)
        assert "Test Title" in result
        assert "Alice" in result

    def test_csl_json(self, tmp_path):
        import json
        from ppke.converter.zotero import parse_zotero_file
        f = tmp_path / "refs.json"
        data = [
            {
                "id": "smith2020",
                "type": "article-journal",
                "title": "Machine Learning Review",
                "author": [{"family": "Smith", "given": "John"}],
                "issued": {"date-parts": [[2020]]},
                "container-title": "AI Journal",
                "DOI": "10.5678/ai.2020"
            },
            {
                "id": "doe2019",
                "type": "book",
                "title": "Data Science Handbook",
                "author": [{"family": "Doe", "given": "Jane"}],
                "issued": {"date-parts": [[2019]]},
                "publisher": "Tech Press"
            }
        ]
        f.write_text(json.dumps(data))
        entries = parse_zotero_file(f)
        assert len(entries) == 2
        assert entries[0]["title"] == "Machine Learning Review"
        assert entries[0]["author"] == "John Smith"
        assert entries[0]["year"] == "2020"

    def test_rdf_basic(self, tmp_path):
        from ppke.converter.zotero import parse_zotero_file
        f = tmp_path / "library.rdf"
        f.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         xmlns:dcterms="http://purl.org/dc/terms/"
         xmlns:bib="http://purl.org/net/biblio#"
         xmlns:foaf="http://xmlns.com/foaf/0.1/">
  <bib:Article>
    <dc:title>RDF Test Article</dc:title>
    <dc:date>2021</dc:date>
    <bib:authors>
      <rdf:Seq>
        <rdf:li>
          <foaf:Person>
            <foaf:surname>Brown</foaf:surname>
            <foaf:givenName>Charlie</foaf:givenName>
          </foaf:Person>
        </rdf:li>
      </rdf:Seq>
    </bib:authors>
  </bib:Article>
</rdf:RDF>""")
        entries = parse_zotero_file(f)
        assert len(entries) == 1
        assert entries[0]["title"] == "RDF Test Article"
        assert "Charlie Brown" in entries[0]["author"]

    def test_rdf_via_registry(self, tmp_path):
        from ppke.converter.registry import convert_to_markdown, SUPPORTED_EXTENSIONS
        assert ".rdf" in SUPPORTED_EXTENSIONS
        f = tmp_path / "lib.rdf"
        f.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         xmlns:bib="http://purl.org/net/biblio#">
  <bib:Book>
    <dc:title>RDF Book Test</dc:title>
    <dc:date>2022</dc:date>
  </bib:Book>
</rdf:RDF>""")
        result = convert_to_markdown(f)
        assert "RDF Book Test" in result

    def test_deduplication(self):
        from ppke.converter.zotero import deduplicate_entries
        entries = [
            {"title": "Same Title", "author": "Same Author"},
            {"title": "Same Title", "author": "Same Author"},
            {"title": "Different Title", "author": "Other Author"},
        ]
        unique = deduplicate_entries(entries)
        assert len(unique) == 2

    def test_empty_bibtex(self, tmp_path):
        from ppke.converter.zotero import parse_zotero_file, entries_to_markdown
        f = tmp_path / "empty.bib"
        f.write_text("% This is a comment\n")
        entries = parse_zotero_file(f)
        assert len(entries) == 0
        md = entries_to_markdown(entries)
        assert "No entries found" in md

    def test_detect_format(self, tmp_path):
        from ppke.converter.zotero import detect_format
        assert detect_format(tmp_path / "refs.bib") == "bibtex"
        assert detect_format(tmp_path / "refs.json") == "csl-json"
        assert detect_format(tmp_path / "refs.rdf") == "rdf"
        unknown = tmp_path / "refs.xyz"
        unknown.write_text("random data that is not bib json or xml")
        with pytest.raises(ValueError, match="Cannot detect"):
            detect_format(unknown)

    def test_bibtex_with_abstract(self, tmp_path):
        from ppke.converter.zotero import parse_zotero_file, entries_to_markdown
        f = tmp_path / "abs.bib"
        f.write_text("""@article{k1,
  title = {Paper With Abstract},
  author = {Test Author},
  year = {2023},
  abstract = {This is the abstract of the paper.}
}
""")
        entries = parse_zotero_file(f)
        assert entries[0]["abstract"] == "This is the abstract of the paper."
        md = entries_to_markdown(entries)
        assert "Abstract" in md

    def test_supported_extensions_include_bib_rdf(self):
        from ppke.converter.registry import SUPPORTED_EXTENSIONS
        assert ".bib" in SUPPORTED_EXTENSIONS
        assert ".rdf" in SUPPORTED_EXTENSIONS


# ═══════════════════════════════════════════════════════════════════
# converter/ocr.py
# ═══════════════════════════════════════════════════════════════════


class TestOCR:
    def test_ocr_import_error(self, tmp_path):
        """OCR should raise ImportError when pytesseract is not installed."""
        f = tmp_path / "scan.png"
        f.write_bytes(b"fake image data")
        from ppke.converter.registry import convert_to_markdown
        with pytest.raises((ImportError, Exception)):
            convert_to_markdown(f)


# ═══════════════════════════════════════════════════════════════════
# converter/url.py
# ═══════════════════════════════════════════════════════════════════


class TestURLConverter:
    def test_is_youtube_url_positive(self):
        from ppke.converter.url import is_youtube_url
        assert is_youtube_url("https://www.youtube.com/watch?v=abc123")
        assert is_youtube_url("https://youtu.be/abc123")
        assert is_youtube_url("https://youtube.com/shorts/abc123")

    def test_is_youtube_url_negative(self):
        from ppke.converter.url import is_youtube_url
        assert not is_youtube_url("https://example.com/article")
        assert not is_youtube_url("https://vimeo.com/123")

    def test_url_title(self):
        from ppke.converter.url import _url_title
        assert _url_title("https://example.com/my-article-about-python") == "My Article About Python"

    def test_url_title_no_path(self):
        from ppke.converter.url import _url_title
        result = _url_title("https://example.com/")
        assert isinstance(result, str)

    def test_convert_url_requires_trafilatura(self):
        from ppke.converter.url import convert_url
        with pytest.raises(ImportError):
            convert_url("https://example.com/test")

    def test_convert_url_auto_https(self):
        from ppke.converter.url import convert_url
        with pytest.raises(ImportError):
            convert_url("example.com/test")

    def test_fallback_scrape_requires_deps(self):
        from ppke.converter.url import _fallback_scrape
        with pytest.raises(ImportError):
            _fallback_scrape("https://example.com")


# ═══════════════════════════════════════════════════════════════════
# converter/youtube.py
# ═══════════════════════════════════════════════════════════════════


class TestYouTubeConverter:
    def test_convert_youtube_requires_ytdlp(self):
        from ppke.converter.youtube import convert_youtube
        with pytest.raises(ImportError):
            convert_youtube("https://www.youtube.com/watch?v=test")

    def test_duration_filter_allowed(self):
        from ppke.converter.youtube import _duration_filter
        assert _duration_filter({"duration": 600}, incomplete=False) is None

    def test_duration_filter_rejected(self):
        from ppke.converter.youtube import _duration_filter
        result = _duration_filter({"duration": 8000}, incomplete=False)
        assert result is not None
        assert "2-hour" in result

    def test_duration_filter_no_duration(self):
        from ppke.converter.youtube import _duration_filter
        assert _duration_filter({}, incomplete=False) is None

    def test_fmt_duration_short(self):
        from ppke.converter.youtube import _fmt_duration
        assert _fmt_duration(125) == "2:05"

    def test_fmt_duration_with_hours(self):
        from ppke.converter.youtube import _fmt_duration
        assert _fmt_duration(3661) == "1:01:01"

    def test_fmt_duration_none(self):
        from ppke.converter.youtube import _fmt_duration
        assert _fmt_duration(None) == ""

    def test_fmt_duration_zero(self):
        from ppke.converter.youtube import _fmt_duration
        assert _fmt_duration(0) == ""

    def test_strip_first_heading(self):
        from ppke.converter.youtube import _strip_first_heading
        md = "# My Title\n\nContent here.\n\nMore content."
        result = _strip_first_heading(md)
        assert "# My Title" not in result
        assert "Content here." in result

    def test_strip_first_heading_no_heading(self):
        from ppke.converter.youtube import _strip_first_heading
        md = "No heading here.\n\nJust content."
        assert _strip_first_heading(md) == md
