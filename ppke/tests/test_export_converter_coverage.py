"""Coverage tests for exporters.py, registry.py, ocr.py, url.py, youtube.py.

Mocks all external dependencies so no actual PDF rendering, OCR, web scraping,
or video downloading occurs.
"""

from __future__ import annotations

import json
import sys
import types
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import yaml


# ── Shared fixture ──


@pytest.fixture()
def book_dir(tmp_path):
    d = tmp_path / "Book_Cov"
    d.mkdir()
    meta = {
        "title": "Coverage Book",
        "author": "Cov Author",
        "year": 2025,
        "total_chapters": 3,
        "total_paragraphs": 30,
    }
    (d / "meta.yml").write_text(yaml.dump(meta))
    (d / "01_Raw_Structure.md").write_text("# Ch1\n\n- bullet one\n- bullet two")
    (d / "02_Logical_Map.md").write_text(
        "# Logical\n\n- This is a substantial logical point here\n- Another substantial logical point"
    )
    (d / "03_Concept_Index.md").write_text("# Concepts\n\n- **C1**: def")
    (d / "06_Patterns.md").write_text(
        "# Patterns\n\n- Pattern one is a substantial finding\n- Pattern two is substantial too"
    )
    (d / "summary.md").write_text(
        "# Summary\n\n- Key point one is substantial text\n- Key point two is substantial"
    )
    (d / "study_guide.md").write_text(
        "# Study\n\n#### Topic1\n\nNotes.\n\n---\n\n- study bullet one text\n\n**bold** and *italic* and `code`"
    )
    (d / "extractions.json").write_text(
        json.dumps(
            [
                {
                    "defined_concepts": ["concept1", "concept2"],
                    "explicit_claims": ["This is a substantial claim about the topic."],
                },
                {
                    "defined_concepts": ["concept3"],
                    "explicit_claims": ["Another substantial claim about something else."],
                },
            ]
        )
    )
    return d


# ═══════════════════════════════════════════════════════════════════
# exporters.py — PDF with weasyprint
# ═══════════════════════════════════════════════════════════════════


class TestExportPdfWeasyprint:
    def test_pdf_with_weasyprint(self, book_dir):
        mock_wp = MagicMock()
        mock_wp.HTML.return_value.write_pdf.return_value = b"%PDF-fake"
        with patch.dict(sys.modules, {"weasyprint": mock_wp}):
            from ppke.export.exporters import export_pdf
            result = export_pdf(book_dir)
        assert result == b"%PDF-fake"
        mock_wp.HTML.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# exporters.py — DOCX export (lines 289-408)
# ═══════════════════════════════════════════════════════════════════


def _make_docx_mocks():
    """Build mock modules for python-docx."""
    mock_docx_mod = types.ModuleType("docx")
    mock_shared = types.ModuleType("docx.shared")
    mock_enum_text = types.ModuleType("docx.enum.text")

    mock_shared.Pt = lambda x: x
    mock_shared.Inches = lambda x: x
    mock_shared.RGBColor = lambda r, g, b: (r, g, b)
    mock_enum_text.WD_ALIGN_PARAGRAPH = MagicMock()
    mock_enum_text.WD_ALIGN_PARAGRAPH.CENTER = 1

    mock_doc_instance = MagicMock()
    mock_docx_mod.Document = MagicMock(return_value=mock_doc_instance)

    mock_docx_mod.shared = mock_shared
    mock_docx_mod.enum = MagicMock()
    mock_docx_mod.enum.text = mock_enum_text

    return {
        "docx": mock_docx_mod,
        "docx.shared": mock_shared,
        "docx.enum": mock_docx_mod.enum,
        "docx.enum.text": mock_enum_text,
    }, mock_doc_instance


class TestExportDocx:
    def test_export_docx_full(self, book_dir):
        modules, mock_doc = _make_docx_mocks()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import export_docx
            result = export_docx(book_dir)
        assert isinstance(result, bytes)
        mock_doc.save.assert_called_once()

    def test_export_docx_no_optional_files(self, tmp_path):
        d = tmp_path / "Book_Min"
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": "Min", "author": "A", "year": ""}))
        modules, mock_doc = _make_docx_mocks()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import export_docx
            result = export_docx(d)
        assert isinstance(result, bytes)


class TestAddMdToDocx:
    def test_add_md_to_docx_all_elements(self):
        modules, mock_doc = _make_docx_mocks()
        md = (
            "# H1\n## H2\n### H3\n#### H4\n\n"
            "---\n\n"
            "- bullet item\n\n"
            "Regular paragraph\n\n"
            "**bold** and *italic* and `code`"
        )
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import _add_md_to_docx
            _add_md_to_docx(mock_doc, md)
        # Headings should be added
        assert mock_doc.add_heading.call_count >= 4
        # add_paragraph called for HR, bullet, and regular text
        assert mock_doc.add_paragraph.call_count >= 1


class TestAddFormattedParagraph:
    def test_formatted_paragraph_with_style(self):
        modules, mock_doc = _make_docx_mocks()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import _add_formatted_paragraph
            _add_formatted_paragraph(mock_doc, "**bold** *italic* `code` plain", style="List Bullet")
        mock_doc.add_paragraph.assert_called_once_with(style="List Bullet")

    def test_formatted_paragraph_no_style(self):
        modules, mock_doc = _make_docx_mocks()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import _add_formatted_paragraph
            _add_formatted_paragraph(mock_doc, "plain text")
        mock_doc.add_paragraph.assert_called_once_with()


# ═══════════════════════════════════════════════════════════════════
# exporters.py — PPTX export (lines 422-556)
# ═══════════════════════════════════════════════════════════════════


def _make_pptx_mocks():
    """Build mock modules for python-pptx."""
    mock_pptx_mod = types.ModuleType("pptx")
    mock_util = types.ModuleType("pptx.util")
    mock_dml = types.ModuleType("pptx.dml")
    mock_color = types.ModuleType("pptx.dml.color")
    mock_enum = types.ModuleType("pptx.enum")
    mock_enum_text = types.ModuleType("pptx.enum.text")

    mock_util.Inches = lambda x: x
    mock_util.Pt = lambda x: x
    mock_color.RGBColor = lambda r, g, b: (r, g, b)
    mock_enum_text.PP_ALIGN = MagicMock()
    mock_enum_text.PP_ALIGN.CENTER = 1
    mock_enum_text.PP_ALIGN.LEFT = 0

    mock_prs = MagicMock()
    mock_pptx_mod.Presentation = MagicMock(return_value=mock_prs)

    mock_pptx_mod.util = mock_util
    mock_pptx_mod.dml = mock_dml
    mock_pptx_mod.enum = mock_enum

    return {
        "pptx": mock_pptx_mod,
        "pptx.util": mock_util,
        "pptx.dml": mock_dml,
        "pptx.dml.color": mock_color,
        "pptx.enum": mock_enum,
        "pptx.enum.text": mock_enum_text,
    }, mock_prs


class TestExportPptx:
    def test_export_pptx_full(self, book_dir):
        modules, mock_prs = _make_pptx_mocks()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import export_pptx
            result = export_pptx(book_dir)
        assert isinstance(result, bytes)
        mock_prs.save.assert_called_once()
        # Title slide + summary + concepts + logical + claims + patterns + final = 7
        assert mock_prs.slides.add_slide.call_count >= 3

    def test_export_pptx_minimal(self, tmp_path):
        d = tmp_path / "Book_PptxMin"
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"title": "Min", "author": "A", "year": ""}))
        (d / "extractions.json").write_text("[]")
        modules, mock_prs = _make_pptx_mocks()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import export_pptx
            result = export_pptx(d)
        assert isinstance(result, bytes)


class TestPptxHelpers:
    def test_add_centered_text(self):
        modules, _ = _make_pptx_mocks()
        mock_slide = MagicMock()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import _add_centered_text
            _add_centered_text(mock_slide, "Hello", 1, 2, 11, 1.5, 36, bold=True, color=(0, 0, 0))
        mock_slide.shapes.add_textbox.assert_called_once()

    def test_add_centered_text_no_color(self):
        modules, _ = _make_pptx_mocks()
        mock_slide = MagicMock()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import _add_centered_text
            _add_centered_text(mock_slide, "Hello", 1, 2, 11, 1.5, 36)
        mock_slide.shapes.add_textbox.assert_called_once()

    def test_add_slide_title(self):
        modules, _ = _make_pptx_mocks()
        mock_slide = MagicMock()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import _add_slide_title
            _add_slide_title(mock_slide, "Title Here")
        mock_slide.shapes.add_textbox.assert_called_once()

    def test_add_bullet_list_single(self):
        modules, _ = _make_pptx_mocks()
        mock_slide = MagicMock()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import _add_bullet_list
            _add_bullet_list(mock_slide, ["First"], 1, 2, 11, 5)
        mock_slide.shapes.add_textbox.assert_called_once()

    def test_add_bullet_list_multiple(self):
        modules, _ = _make_pptx_mocks()
        mock_slide = MagicMock()
        with patch.dict(sys.modules, modules):
            from ppke.export.exporters import _add_bullet_list
            _add_bullet_list(mock_slide, ["A", "B", "C"], 1, 2, 11, 5)
        tf = mock_slide.shapes.add_textbox.return_value.text_frame
        assert tf.add_paragraph.call_count == 2  # first uses paragraphs[0]


# ═══════════════════════════════════════════════════════════════════
# exporters.py — minor branches (lines 585, 618)
# ═══════════════════════════════════════════════════════════════════


class TestExtractBulletsMaxReached:
    def test_extract_bullets_caps_at_max(self):
        from ppke.export.exporters import _extract_bullets
        md = "\n".join(f"- Bullet number {i} is long enough" for i in range(20))
        result = _extract_bullets(md, max_bullets=3)
        assert len(result) == 3

    def test_extract_bullets_fallback_caps_at_max(self):
        from ppke.export.exporters import _extract_bullets
        # No bullet lines, long lines trigger fallback; more than max_bullets
        md = "\n".join(
            f"This is a long line number {i} that exceeds thirty chars definitely"
            for i in range(10)
        )
        result = _extract_bullets(md, max_bullets=3)
        assert len(result) == 3


class TestExportMarkdownZipAudioScript:
    def test_zip_includes_audio_script(self, book_dir):
        (book_dir / "audio_script.json").write_text('{"script": "test"}')
        from ppke.export.exporters import export_markdown_zip
        import zipfile

        result = export_markdown_zip(book_dir)
        zf = zipfile.ZipFile(BytesIO(result))
        names = zf.namelist()
        assert any("audio_script.json" in n for n in names)


# ═══════════════════════════════════════════════════════════════════
# registry.py — _convert_pdf (lines 59-88)
# ═══════════════════════════════════════════════════════════════════


class TestConvertPdfMocked:
    def test_convert_pdf_text_pages(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF")

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Hello world"
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 1
        mock_doc.__getitem__ = lambda self, i: mock_page

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".pdf"](f)
        assert "Hello world" in result
        assert "# Doc" in result

    def test_convert_pdf_ocr_fallback(self, tmp_path):
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"%PDF")

        mock_page = MagicMock()
        mock_page.get_text.return_value = ""  # no text → trigger OCR
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 1
        mock_doc.__getitem__ = lambda self, i: mock_page

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}), \
             patch("ppke.converter.ocr.ocr_pdf_pages", return_value={0: "OCR text"}):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".pdf"](f)
        assert "OCR" in result

    def test_convert_pdf_ocr_import_error(self, tmp_path):
        f = tmp_path / "scan2.pdf"
        f.write_bytes(b"%PDF")

        mock_page = MagicMock()
        mock_page.get_text.return_value = ""
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 1
        mock_doc.__getitem__ = lambda self, i: mock_page

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}), \
             patch("ppke.converter.ocr.ocr_pdf_pages", side_effect=ImportError("no ocr")):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".pdf"](f)
        # Should still return something (just without OCR pages)
        assert "# Scan2" in result


# ═══════════════════════════════════════════════════════════════════
# registry.py — _convert_docx (lines 101-121)
# ═══════════════════════════════════════════════════════════════════


class TestConvertDocxMocked:
    def test_convert_docx(self, tmp_path):
        f = tmp_path / "test.docx"
        f.write_bytes(b"fake")

        mock_para1 = MagicMock()
        mock_para1.text = "Title"
        mock_para1.style.name = "Heading 1"

        mock_para2 = MagicMock()
        mock_para2.text = "Subtitle"
        mock_para2.style.name = "Heading 2"

        mock_para3 = MagicMock()
        mock_para3.text = "Sub-sub"
        mock_para3.style.name = "Heading 3"

        mock_para4 = MagicMock()
        mock_para4.text = "Doc Title"
        mock_para4.style.name = "Title"

        mock_para5 = MagicMock()
        mock_para5.text = "Body text"
        mock_para5.style.name = "Normal"

        mock_para_empty = MagicMock()
        mock_para_empty.text = ""
        mock_para_empty.style.name = "Normal"

        mock_doc_inst = MagicMock()
        mock_doc_inst.paragraphs = [mock_para1, mock_para2, mock_para3, mock_para4, mock_para5, mock_para_empty]

        mock_docx_mod = MagicMock()
        mock_docx_mod.Document.return_value = mock_doc_inst

        with patch.dict(sys.modules, {"docx": mock_docx_mod}):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".docx"](f)
        assert "# Title" in result
        assert "## Subtitle" in result
        assert "### Sub-sub" in result
        assert "# Doc Title" in result
        assert "Body text" in result


# ═══════════════════════════════════════════════════════════════════
# registry.py — _convert_epub (lines 129, 136-148)
# ═══════════════════════════════════════════════════════════════════


class TestConvertEpubMocked:
    def test_convert_epub(self, tmp_path):
        f = tmp_path / "book.epub"
        f.write_bytes(b"fake")

        mock_item = MagicMock()
        mock_item.get_content.return_value = b"<p>Chapter text</p>"

        mock_epub_book = MagicMock()
        mock_epub_book.get_items_of_type.return_value = [mock_item]

        mock_ebooklib = MagicMock()
        mock_ebooklib.ITEM_DOCUMENT = 9
        mock_epub = MagicMock()
        mock_epub.read_epub.return_value = mock_epub_book
        mock_ebooklib.epub = mock_epub

        mock_bs4 = MagicMock()
        mock_soup_inst = MagicMock()
        mock_soup_inst.get_text.return_value = "Chapter text"
        mock_bs4.BeautifulSoup.return_value = mock_soup_inst

        with patch.dict(sys.modules, {
            "ebooklib": mock_ebooklib,
            "ebooklib.epub": mock_epub,
            "bs4": mock_bs4,
        }):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".epub"](f)
        assert "Chapter text" in result
        assert "# Book" in result


# ═══════════════════════════════════════════════════════════════════
# registry.py — _convert_html (lines 163-172)
# ═══════════════════════════════════════════════════════════════════


class TestConvertHtmlMocked:
    def test_convert_html(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<html><head><title>Page Title</title></head><body><p>Content</p></body></html>")

        mock_soup = MagicMock()
        mock_soup.title.string = "Page Title"
        mock_soup.get_text.return_value = "Content"

        mock_bs4 = MagicMock()
        mock_bs4.BeautifulSoup.return_value = mock_soup

        with patch.dict(sys.modules, {"bs4": mock_bs4}):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".html"](f)
        assert "# Page Title" in result
        assert "Content" in result

    def test_convert_html_no_title(self, tmp_path):
        f = tmp_path / "notitle.html"
        f.write_text("<html><body>Hello</body></html>")

        mock_soup = MagicMock()
        mock_soup.title = None
        mock_soup.get_text.return_value = "Hello"

        mock_bs4 = MagicMock()
        mock_bs4.BeautifulSoup.return_value = mock_soup

        with patch.dict(sys.modules, {"bs4": mock_bs4}):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".html"](f)
        assert "# notitle" in result


# ═══════════════════════════════════════════════════════════════════
# registry.py — _convert_pptx (lines 184, 197-217)
# ═══════════════════════════════════════════════════════════════════


class TestConvertPptxMocked:
    def test_convert_pptx(self, tmp_path):
        f = tmp_path / "slides.pptx"
        f.write_bytes(b"fake")

        mock_para1 = MagicMock()
        mock_para1.text = "Slide Title"
        mock_para2 = MagicMock()
        mock_para2.text = "Slide Body"

        mock_tf = MagicMock()
        mock_tf.paragraphs = [mock_para1, mock_para2]

        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_shape.text_frame = mock_tf

        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]

        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        mock_pptx_mod = MagicMock()
        mock_pptx_mod.Presentation.return_value = mock_prs

        with patch.dict(sys.modules, {"pptx": mock_pptx_mod}):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".pptx"](f)
        assert "Slide Title" in result
        assert "Slide Body" in result
        assert "## Slide 1" in result

    def test_convert_pptx_no_text_frame(self, tmp_path):
        f = tmp_path / "empty_slides.pptx"
        f.write_bytes(b"fake")

        mock_shape = MagicMock()
        mock_shape.has_text_frame = False

        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]

        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        mock_pptx_mod = MagicMock()
        mock_pptx_mod.Presentation.return_value = mock_prs

        with patch.dict(sys.modules, {"pptx": mock_pptx_mod}):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".pptx"](f)
        assert "# Empty Slides" in result


# ═══════════════════════════════════════════════════════════════════
# registry.py — _convert_audio (lines 226-228)
# ═══════════════════════════════════════════════════════════════════


class TestConvertAudioMocked:
    def test_convert_audio(self, tmp_path):
        f = tmp_path / "audio.mp3"
        f.write_bytes(b"fake")

        with patch("ppke.audio.transcriber.transcribe", return_value="# Transcript\n\nHello world"):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".mp3"](f)
        assert "Hello world" in result


# ═══════════════════════════════════════════════════════════════════
# registry.py — _convert_csv > 500 rows (line 296)
# ═══════════════════════════════════════════════════════════════════


class TestConvertCsvOverflow:
    def test_csv_over_500_rows(self, tmp_path):
        import csv as csv_mod

        f = tmp_path / "big.csv"
        with open(f, "w", newline="") as csvf:
            writer = csv_mod.writer(csvf)
            writer.writerow(["Col"])
            for i in range(510):
                writer.writerow([f"row{i}"])

        from ppke.converter.registry import _CONVERTERS

        result = _CONVERTERS[".csv"](f)
        assert "additional rows not shown" in result


# ═══════════════════════════════════════════════════════════════════
# registry.py — _convert_latex pandoc success (line 244-245)
# ═══════════════════════════════════════════════════════════════════


class TestConvertLatexPandoc:
    def test_latex_pandoc_success(self, tmp_path):
        f = tmp_path / "paper.tex"
        f.write_text(r"\section{Intro} Text")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "# Intro\n\nText"

        with patch("subprocess.run", return_value=mock_result):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".tex"](f)
        assert "# paper" in result
        assert "# Intro" in result


# ═══════════════════════════════════════════════════════════════════
# registry.py — _convert_excel (lines 312-347)
# ═══════════════════════════════════════════════════════════════════


class TestConvertExcelMocked:
    def test_convert_excel(self, tmp_path):
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"fake")

        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [
            ("Header1", "Header2"),
            ("val1", "val2"),
            (None, "val3"),
        ]

        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__ = lambda self, key: mock_ws

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".xlsx"](f)
        assert "## Sheet1" in result
        assert "Header1" in result
        assert "val1" in result

    def test_convert_excel_empty_sheet(self, tmp_path):
        f = tmp_path / "empty.xlsx"
        f.write_bytes(b"fake")

        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = []

        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Empty"]
        mock_wb.__getitem__ = lambda self, key: mock_ws

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".xlsx"](f)
        assert "empty workbook" in result

    def test_convert_excel_open_error(self, tmp_path):
        f = tmp_path / "bad.xlsx"
        f.write_bytes(b"fake")

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.side_effect = Exception("corrupt file")

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}):
            from ppke.converter.registry import _CONVERTERS
            with pytest.raises(ValueError, match="Could not open"):
                _CONVERTERS[".xlsx"](f)

    def test_convert_excel_over_500_rows(self, tmp_path):
        f = tmp_path / "big.xlsx"
        f.write_bytes(b"fake")

        rows = [("H1",)] + [(f"r{i}",) for i in range(510)]
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = rows

        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Big"]
        mock_wb.__getitem__ = lambda self, key: mock_ws

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}):
            from ppke.converter.registry import _CONVERTERS
            result = _CONVERTERS[".xlsx"](f)
        assert "additional rows not shown" in result


# ═══════════════════════════════════════════════════════════════════
# registry.py — _convert_zip error in member (lines 382-383)
# ═══════════════════════════════════════════════════════════════════


class TestConvertZipError:
    def test_zip_member_conversion_error(self, tmp_path):
        import zipfile

        zpath = tmp_path / "mixed.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("good.txt", "good content")
            zf.writestr("bad.md", "# Bad")

        # Patch the .md converter to raise
        from ppke.converter.registry import _CONVERTERS
        original = _CONVERTERS[".md"]
        _CONVERTERS[".md"] = lambda p: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            result = _CONVERTERS[".zip"](zpath)
            # .txt should still work, .md should be skipped
            assert "good content" in result
        finally:
            _CONVERTERS[".md"] = original


# ═══════════════════════════════════════════════════════════════════
# ocr.py — ocr_image (lines 59, 66-100)
# ═══════════════════════════════════════════════════════════════════


class TestOcrImage:
    def _setup_mocks(self):
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pil = MagicMock()
        mock_image_mod = MagicMock()
        mock_pil.Image = mock_image_mod
        return mock_pytesseract, mock_pil, mock_image_mod

    def test_ocr_image_high_confidence(self, tmp_path):
        f = tmp_path / "scan.png"
        f.write_bytes(b"\x89PNG fake")

        mock_pytesseract, mock_pil, mock_image_mod = self._setup_mocks()

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "PIL": mock_pil, "PIL.Image": mock_image_mod}), \
             patch("ppke.converter.ocr._detect_language", return_value="eng"), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("Good text", 85.0)):
            from ppke.converter.ocr import ocr_image
            result = ocr_image(f)
        assert result == "Good text"

    def test_ocr_image_low_confidence_vision_fallback(self, tmp_path):
        f = tmp_path / "scan.png"
        f.write_bytes(b"\x89PNG fake")

        mock_pytesseract, mock_pil, mock_image_mod = self._setup_mocks()

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "PIL": mock_pil, "PIL.Image": mock_image_mod}), \
             patch("ppke.converter.ocr._detect_language", return_value=None), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("Bad text", 30.0)), \
             patch("ppke.converter.ocr.vision_ocr", return_value="Vision text"):
            from ppke.converter.ocr import ocr_image
            result = ocr_image(f, lang=None)
        assert result == "Vision text"

    def test_ocr_image_low_confidence_vision_fails(self, tmp_path):
        f = tmp_path / "scan.png"
        f.write_bytes(b"\x89PNG fake")

        mock_pytesseract, mock_pil, mock_image_mod = self._setup_mocks()

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "PIL": mock_pil, "PIL.Image": mock_image_mod}), \
             patch("ppke.converter.ocr._detect_language", return_value="eng"), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("Bad text", 30.0)), \
             patch("ppke.converter.ocr.vision_ocr", side_effect=RuntimeError("API fail")):
            from ppke.converter.ocr import ocr_image
            result = ocr_image(f)
        assert result == "Bad text"

    def test_ocr_image_empty_text_vision_fallback(self, tmp_path):
        f = tmp_path / "blank.png"
        f.write_bytes(b"\x89PNG fake")

        mock_pytesseract, mock_pil, mock_image_mod = self._setup_mocks()

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "PIL": mock_pil, "PIL.Image": mock_image_mod}), \
             patch("ppke.converter.ocr._detect_language", return_value="eng"), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("", 0.0)), \
             patch("ppke.converter.ocr.vision_ocr", return_value="Vision recovered"):
            from ppke.converter.ocr import ocr_image
            result = ocr_image(f)
        assert result == "Vision recovered"

    def test_ocr_image_empty_text_vision_fails(self, tmp_path):
        f = tmp_path / "blank2.png"
        f.write_bytes(b"\x89PNG fake")

        mock_pytesseract, mock_pil, mock_image_mod = self._setup_mocks()

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "PIL": mock_pil, "PIL.Image": mock_image_mod}), \
             patch("ppke.converter.ocr._detect_language", return_value="eng"), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("", 0.0)), \
             patch("ppke.converter.ocr.vision_ocr", side_effect=RuntimeError("fail")):
            from ppke.converter.ocr import ocr_image
            result = ocr_image(f)
        assert "no text detected" in result

    def test_ocr_image_empty_no_vision(self, tmp_path):
        f = tmp_path / "blank3.png"
        f.write_bytes(b"\x89PNG fake")

        mock_pytesseract, mock_pil, mock_image_mod = self._setup_mocks()

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "PIL": mock_pil, "PIL.Image": mock_image_mod}), \
             patch("ppke.converter.ocr._detect_language", return_value="eng"), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("", 0.0)):
            from ppke.converter.ocr import ocr_image
            result = ocr_image(f, use_vision_fallback=False)
        assert "no text detected" in result

    def test_ocr_image_with_explicit_lang(self, tmp_path):
        f = tmp_path / "de_scan.png"
        f.write_bytes(b"\x89PNG fake")

        mock_pytesseract, mock_pil, mock_image_mod = self._setup_mocks()

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "PIL": mock_pil, "PIL.Image": mock_image_mod}), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("German text", 80.0)) as mock_tess:
            from ppke.converter.ocr import ocr_image
            result = ocr_image(f, lang="deu", use_vision_fallback=False)
        assert result == "German text"


# ═══════════════════════════════════════════════════════════════════
# ocr.py — ocr_pdf_pages (lines 119-177)
# ═══════════════════════════════════════════════════════════════════


class TestOcrPdfPages:
    def test_ocr_pdf_pages_basic(self, tmp_path):
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"%PDF")

        mock_img = MagicMock()
        mock_pytesseract = MagicMock()
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [mock_img]

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image}), \
             patch("ppke.converter.ocr._detect_language", return_value="eng"), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("Page text", 75.0)):
            from ppke.converter.ocr import ocr_pdf_pages
            result = ocr_pdf_pages(f, [0, 1])
        assert 0 in result
        assert "Page text" in result[0]

    def test_ocr_pdf_pages_no_images(self, tmp_path):
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"%PDF")

        mock_pytesseract = MagicMock()
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = []

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image}):
            from ppke.converter.ocr import ocr_pdf_pages
            result = ocr_pdf_pages(f, [0])
        assert result == {}

    def test_ocr_pdf_pages_low_confidence_vision(self, tmp_path):
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"%PDF")

        mock_img = MagicMock()
        mock_pytesseract = MagicMock()
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [mock_img]

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image}), \
             patch("ppke.converter.ocr._detect_language", return_value="eng"), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("Bad", 20.0)), \
             patch("ppke.converter.ocr.vision_ocr", return_value="Vision page text"):
            from ppke.converter.ocr import ocr_pdf_pages
            result = ocr_pdf_pages(f, [0])
        assert result[0] == "Vision page text"

    def test_ocr_pdf_pages_vision_fails(self, tmp_path):
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"%PDF")

        mock_img = MagicMock()
        mock_pytesseract = MagicMock()
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [mock_img]

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image}), \
             patch("ppke.converter.ocr._detect_language", return_value="eng"), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("Low", 20.0)), \
             patch("ppke.converter.ocr.vision_ocr", side_effect=RuntimeError("API err")):
            from ppke.converter.ocr import ocr_pdf_pages
            result = ocr_pdf_pages(f, [0])
        # Low confidence annotation
        assert "OCR confidence" in result[0]

    def test_ocr_pdf_pages_empty_text(self, tmp_path):
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"%PDF")

        mock_img = MagicMock()
        mock_pytesseract = MagicMock()
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [mock_img]

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image}), \
             patch("ppke.converter.ocr._detect_language", return_value="eng"), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("", 0.0)), \
             patch("ppke.converter.ocr.vision_ocr", side_effect=RuntimeError("fail")):
            from ppke.converter.ocr import ocr_pdf_pages
            result = ocr_pdf_pages(f, [0], use_vision_fallback=True)
        assert "no text detected" in result[0]

    def test_ocr_pdf_pages_explicit_lang(self, tmp_path):
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"%PDF")

        mock_img = MagicMock()
        mock_pytesseract = MagicMock()
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [mock_img]

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image}), \
             patch("ppke.converter.ocr._tesseract_with_confidence", return_value=("Text", 80.0)):
            from ppke.converter.ocr import ocr_pdf_pages
            result = ocr_pdf_pages(f, [0], lang="deu", use_vision_fallback=False)
        assert result[0] == "Text"


# ═══════════════════════════════════════════════════════════════════
# ocr.py — vision_ocr (lines 199-271)
# ═══════════════════════════════════════════════════════════════════


class TestVisionOcr:
    def test_vision_ocr_anthropic(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG\r\n")

        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="Anthropic OCR text")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from ppke.converter.ocr import vision_ocr
            result = vision_ocr(f, provider="anthropic", api_key="test-key")
        assert result == "Anthropic OCR text"

    def test_vision_ocr_anthropic_no_key(self, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_bytes(b"\xff\xd8\xff")

        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="Result")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from ppke.converter.ocr import vision_ocr
            result = vision_ocr(f, provider="anthropic")
        assert result == "Result"
        mock_anthropic.Anthropic.assert_called_once_with()

    def test_vision_ocr_openai(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG\r\n")

        mock_msg = MagicMock()
        mock_msg.content = "OpenAI OCR text"
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict(sys.modules, {"openai": mock_openai}):
            from ppke.converter.ocr import vision_ocr
            result = vision_ocr(f, provider="openai", api_key="test-key")
        assert result == "OpenAI OCR text"

    def test_vision_ocr_openai_no_key(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG\r\n")

        mock_msg = MagicMock()
        mock_msg.content = "Result"
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict(sys.modules, {"openai": mock_openai}):
            from ppke.converter.ocr import vision_ocr
            result = vision_ocr(f, provider="openai")
        mock_openai.OpenAI.assert_called_once_with()

    def test_vision_ocr_openai_none_content(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG\r\n")

        mock_msg = MagicMock()
        mock_msg.content = None
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict(sys.modules, {"openai": mock_openai}):
            from ppke.converter.ocr import vision_ocr
            result = vision_ocr(f, provider="openai", api_key="k")
        assert result == ""

    def test_vision_ocr_unsupported_provider(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG\r\n")

        from ppke.converter.ocr import vision_ocr

        with pytest.raises(ValueError, match="not supported"):
            vision_ocr(f, provider="gemini")

    def test_vision_ocr_mime_types(self, tmp_path):
        """Various extensions map to correct MIME types."""
        for ext in (".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif"):
            f = tmp_path / f"img{ext}"
            f.write_bytes(b"data")

            mock_resp = MagicMock()
            mock_resp.content = [MagicMock(text="ok")]
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_resp
            mock_anthropic = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client

            with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
                from ppke.converter.ocr import vision_ocr
                result = vision_ocr(f, provider="anthropic", api_key="k")
            assert result == "ok"


# ═══════════════════════════════════════════════════════════════════
# ocr.py — _tesseract_with_confidence (lines 289-311)
# ═══════════════════════════════════════════════════════════════════


class TestTesseractWithConfidence:
    def test_normal(self):
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.return_value = {
            "conf": [90, 85, 80],
            "text": ["Hello", "world", "test"],
        }

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            from ppke.converter.ocr import _tesseract_with_confidence
            text, conf = _tesseract_with_confidence(MagicMock(), lang="eng")
        assert "Hello" in text
        assert conf == pytest.approx(85.0)

    def test_fallback_on_error(self):
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.side_effect = RuntimeError("osd error")
        mock_pytesseract.image_to_string.return_value = "Fallback text"

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            from ppke.converter.ocr import _tesseract_with_confidence
            text, conf = _tesseract_with_confidence(MagicMock(), lang="eng")
        assert text == "Fallback text"
        assert conf == 50.0

    def test_empty_page(self):
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.return_value = {
            "conf": [],
            "text": [],
        }

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            from ppke.converter.ocr import _tesseract_with_confidence
            text, conf = _tesseract_with_confidence(MagicMock(), lang="eng")
        assert text == ""
        assert conf == 0.0

    def test_filters_negative_confidence(self):
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.return_value = {
            "conf": [-1, 80, -1, 70],
            "text": ["", "word1", "", "word2"],
        }

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            from ppke.converter.ocr import _tesseract_with_confidence
            text, conf = _tesseract_with_confidence(MagicMock(), lang="eng")
        assert "word1" in text
        assert "word2" in text


# ═══════════════════════════════════════════════════════════════════
# ocr.py — _detect_language (lines 322-344)
# ═══════════════════════════════════════════════════════════════════


class TestDetectLanguage:
    def test_detect_latin(self):
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_osd.return_value = {"script": "Latin"}

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            from ppke.converter.ocr import _detect_language
            result = _detect_language(MagicMock())
        assert result == "eng"

    def test_detect_han(self):
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_osd.return_value = {"script": "Han"}

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            from ppke.converter.ocr import _detect_language
            result = _detect_language(MagicMock())
        assert result == "chi_sim"

    def test_detect_cyrillic(self):
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_osd.return_value = {"script": "Cyrillic"}

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            from ppke.converter.ocr import _detect_language
            result = _detect_language(MagicMock())
        assert result == "rus"

    def test_detect_unknown_script(self):
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_osd.return_value = {"script": "Unknown"}

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            from ppke.converter.ocr import _detect_language
            result = _detect_language(MagicMock())
        assert result is None

    def test_detect_osd_failure(self):
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.side_effect = RuntimeError("OSD failed")

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            from ppke.converter.ocr import _detect_language
            result = _detect_language(MagicMock())
        assert result is None

    def test_detect_additional_scripts(self):
        scripts = {
            "Hangul": "kor",
            "Hiragana": "jpn",
            "Katakana": "jpn",
            "Devanagari": "hin",
            "Arabic": "ara",
            "Greek": "ell",
            "Hebrew": "heb",
            "Thai": "tha",
        }
        for script, expected_lang in scripts.items():
            mock_pytesseract = MagicMock()
            mock_pytesseract.Output.DICT = "dict"
            mock_pytesseract.image_to_osd.return_value = {"script": script}

            with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
                from ppke.converter.ocr import _detect_language
                result = _detect_language(MagicMock())
            assert result == expected_lang, f"Failed for script {script}"


# ═══════════════════════════════════════════════════════════════════
# url.py — convert_url with mocked trafilatura (lines 48-100)
# ═══════════════════════════════════════════════════════════════════


class TestConvertUrlMocked:
    def test_convert_url_full(self):
        mock_trafilatura = MagicMock()
        mock_trafilatura.fetch_url.return_value = "<html>content</html>"

        mock_meta = MagicMock()
        mock_meta.title = "Article Title"
        mock_meta.author = "Author Name"
        mock_meta.date = "2025-01-01"
        mock_meta.description = "Article description"
        mock_trafilatura.extract_metadata.return_value = mock_meta
        mock_trafilatura.extract.return_value = "Article body in markdown"

        with patch.dict(sys.modules, {"trafilatura": mock_trafilatura}):
            from ppke.converter.url import convert_url
            result = convert_url("https://example.com/article")
        assert "# Article Title" in result
        assert "Author: Author Name" in result
        assert "Date: 2025-01-01" in result
        assert "Article body in markdown" in result
        assert "> Article description" in result

    def test_convert_url_no_metadata(self):
        mock_trafilatura = MagicMock()
        mock_trafilatura.fetch_url.return_value = "<html>content</html>"
        mock_trafilatura.extract_metadata.side_effect = Exception("parse error")
        mock_trafilatura.extract.return_value = "Body text"

        with patch.dict(sys.modules, {"trafilatura": mock_trafilatura}):
            from ppke.converter.url import convert_url
            result = convert_url("https://example.com/my-page")
        assert "Body text" in result

    def test_convert_url_no_content_fallback(self):
        mock_trafilatura = MagicMock()
        mock_trafilatura.fetch_url.return_value = "<html>content</html>"
        mock_trafilatura.extract_metadata.return_value = None
        mock_trafilatura.extract.return_value = None  # no content

        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "<html><title>Fallback</title><body>Fallback text</body></html>"
        mock_requests.get.return_value = mock_resp

        mock_soup = MagicMock()
        mock_soup.title.string.strip.return_value = "Fallback"
        mock_soup.get_text.return_value = "Fallback text"
        mock_bs4 = MagicMock()
        mock_bs4.BeautifulSoup.return_value = mock_soup

        with patch.dict(sys.modules, {
            "trafilatura": mock_trafilatura,
            "requests": mock_requests,
            "bs4": mock_bs4,
        }):
            from ppke.converter.url import convert_url
            result = convert_url("https://example.com/page")
        assert "Fallback" in result

    def test_convert_url_download_fails(self):
        mock_trafilatura = MagicMock()
        mock_trafilatura.fetch_url.return_value = None

        with patch.dict(sys.modules, {"trafilatura": mock_trafilatura}):
            from ppke.converter.url import convert_url
            with pytest.raises(ValueError, match="Could not download"):
                convert_url("https://example.com/broken")

    def test_convert_url_auto_https(self):
        mock_trafilatura = MagicMock()
        mock_trafilatura.fetch_url.return_value = "<html></html>"
        mock_trafilatura.extract_metadata.return_value = None
        mock_trafilatura.extract.return_value = "Content"

        with patch.dict(sys.modules, {"trafilatura": mock_trafilatura}):
            from ppke.converter.url import convert_url
            result = convert_url("example.com/page")
        mock_trafilatura.fetch_url.assert_called_with("https://example.com/page")

    def test_convert_url_no_author_no_date(self):
        mock_trafilatura = MagicMock()
        mock_trafilatura.fetch_url.return_value = "<html></html>"
        mock_meta = MagicMock()
        mock_meta.title = "Title"
        mock_meta.author = None
        mock_meta.date = None
        mock_meta.description = None
        mock_trafilatura.extract_metadata.return_value = mock_meta
        mock_trafilatura.extract.return_value = "Body"

        with patch.dict(sys.modules, {"trafilatura": mock_trafilatura}):
            from ppke.converter.url import convert_url
            result = convert_url("https://example.com/test")
        assert "Author" not in result
        assert "Date" not in result
        assert "Body" in result

    def test_convert_url_metadata_no_title(self):
        mock_trafilatura = MagicMock()
        mock_trafilatura.fetch_url.return_value = "<html></html>"
        mock_meta = MagicMock()
        mock_meta.title = None
        mock_meta.author = None
        mock_meta.date = None
        mock_meta.description = None
        mock_trafilatura.extract_metadata.return_value = mock_meta
        mock_trafilatura.extract.return_value = "Body"

        with patch.dict(sys.modules, {"trafilatura": mock_trafilatura}):
            from ppke.converter.url import convert_url
            result = convert_url("https://example.com/my-article")
        # Should fall back to _url_title
        assert "# My Article" in result


# ═══════════════════════════════════════════════════════════════════
# url.py — _fallback_scrape (lines 121-139)
# ═══════════════════════════════════════════════════════════════════


class TestFallbackScrapeMocked:
    def test_fallback_scrape(self):
        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "<html><head><title>Test Page</title></head><body><p>Hello</p></body></html>"
        mock_requests.get.return_value = mock_resp

        mock_soup = MagicMock()
        mock_soup.title.string.strip.return_value = "Test Page"
        mock_soup.get_text.return_value = "Hello\n\n\n\nWorld"
        mock_bs4 = MagicMock()
        mock_bs4.BeautifulSoup.return_value = mock_soup

        with patch.dict(sys.modules, {"requests": mock_requests, "bs4": mock_bs4}):
            from ppke.converter.url import _fallback_scrape
            result = _fallback_scrape("https://example.com/test")
        assert "# Test Page" in result
        assert "Source:" in result

    def test_fallback_scrape_no_title(self):
        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>Content</body></html>"
        mock_requests.get.return_value = mock_resp

        mock_soup = MagicMock()
        mock_soup.title = None
        mock_soup.get_text.return_value = "Content"
        mock_bs4 = MagicMock()
        mock_bs4.BeautifulSoup.return_value = mock_soup

        with patch.dict(sys.modules, {"requests": mock_requests, "bs4": mock_bs4}):
            from ppke.converter.url import _fallback_scrape
            result = _fallback_scrape("https://example.com/some-page")
        assert "Some Page" in result


# ═══════════════════════════════════════════════════════════════════
# youtube.py — convert_youtube (lines 41-114)
# ═══════════════════════════════════════════════════════════════════


class TestConvertYoutubeMocked:
    def _make_yt_dlp_mock(self, info=None):
        mock_yt_dlp = MagicMock()
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = info or {
            "title": "Test Video",
            "uploader": "TestChannel",
            "upload_date": "20250115",
            "duration_string": "5:30",
            "duration": 330,
            "view_count": 12345,
        }
        mock_yt_dlp.YoutubeDL.return_value = mock_ydl
        mock_yt_dlp.utils = MagicMock()
        mock_yt_dlp.utils.DownloadError = type("DownloadError", (Exception,), {})
        return mock_yt_dlp

    def test_convert_youtube_full(self, tmp_path):
        mock_yt_dlp = self._make_yt_dlp_mock()

        def fake_glob(self_path, pattern):
            f = tmp_path / "audio.mp3"
            f.write_bytes(b"fake mp3")
            return [f]

        with patch.dict(sys.modules, {"yt_dlp": mock_yt_dlp}), \
             patch("ppke.audio.transcriber.transcribe", return_value="# Audio\n\nTranscribed text"), \
             patch("pathlib.Path.glob", fake_glob):
            from ppke.converter.youtube import convert_youtube
            result = convert_youtube("https://www.youtube.com/watch?v=test")
        assert "# Test Video" in result
        assert "TestChannel" in result
        assert "2025-01-15" in result
        assert "5:30" in result
        assert "12,345" in result
        assert "Transcribed text" in result

    def test_convert_youtube_minimal_info(self, tmp_path):
        info = {
            "title": None,
            "uploader": None,
            "channel": None,
            "upload_date": None,
            "duration_string": None,
            "duration": None,
            "view_count": None,
        }
        mock_yt_dlp = self._make_yt_dlp_mock(info)

        def fake_glob(self_path, pattern):
            f = tmp_path / "audio.mp3"
            f.write_bytes(b"fake mp3")
            return [f]

        with patch.dict(sys.modules, {"yt_dlp": mock_yt_dlp}), \
             patch("ppke.audio.transcriber.transcribe", return_value="No heading\n\nText"), \
             patch("pathlib.Path.glob", fake_glob):
            from ppke.converter.youtube import convert_youtube
            result = convert_youtube("https://youtu.be/test")
        assert "# YouTube Video" in result
        assert "Unknown" in result

    def test_convert_youtube_no_audio_files(self, tmp_path):
        mock_yt_dlp = self._make_yt_dlp_mock()

        with patch.dict(sys.modules, {"yt_dlp": mock_yt_dlp}), \
             patch("pathlib.Path.glob", return_value=[]):
            from ppke.converter.youtube import convert_youtube
            with pytest.raises(ValueError, match="no audio file"):
                convert_youtube("https://www.youtube.com/watch?v=test")

    def test_convert_youtube_download_error(self, tmp_path):
        mock_yt_dlp = MagicMock()
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        dl_error = type("DownloadError", (Exception,), {})
        mock_ydl.extract_info.side_effect = dl_error("download failed")
        mock_yt_dlp.YoutubeDL.return_value = mock_ydl
        mock_yt_dlp.utils = MagicMock()
        mock_yt_dlp.utils.DownloadError = dl_error

        with patch.dict(sys.modules, {"yt_dlp": mock_yt_dlp}):
            from ppke.converter.youtube import convert_youtube
            with pytest.raises(ValueError, match="yt-dlp download failed"):
                convert_youtube("https://www.youtube.com/watch?v=test")

    def test_convert_youtube_generic_error(self, tmp_path):
        mock_yt_dlp = MagicMock()
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = RuntimeError("unexpected")
        mock_yt_dlp.YoutubeDL.return_value = mock_ydl
        mock_yt_dlp.utils = MagicMock()
        mock_yt_dlp.utils.DownloadError = type("DownloadError", (Exception,), {})

        with patch.dict(sys.modules, {"yt_dlp": mock_yt_dlp}):
            from ppke.converter.youtube import convert_youtube
            with pytest.raises(ValueError, match="Failed to download"):
                convert_youtube("https://www.youtube.com/watch?v=test")

    def test_convert_youtube_channel_fallback(self, tmp_path):
        info = {
            "title": "Video",
            "uploader": None,
            "channel": "ChannelName",
            "upload_date": "20250101",
            "duration_string": None,
            "duration": 60,
            "view_count": None,
        }
        mock_yt_dlp = self._make_yt_dlp_mock(info)

        def fake_glob(self_path, pattern):
            f = tmp_path / "audio.mp3"
            f.write_bytes(b"fake mp3")
            return [f]

        with patch.dict(sys.modules, {"yt_dlp": mock_yt_dlp}), \
             patch("ppke.audio.transcriber.transcribe", return_value="# Title\n\nBody"), \
             patch("pathlib.Path.glob", fake_glob):
            from ppke.converter.youtube import convert_youtube
            result = convert_youtube("https://www.youtube.com/watch?v=test")
        assert "ChannelName" in result
        assert "1:00" in result  # _fmt_duration(60)

    def test_convert_youtube_extract_info_returns_none(self, tmp_path):
        mock_yt_dlp = MagicMock()
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = None
        mock_yt_dlp.YoutubeDL.return_value = mock_ydl
        mock_yt_dlp.utils = MagicMock()
        mock_yt_dlp.utils.DownloadError = type("DownloadError", (Exception,), {})

        def fake_glob(self_path, pattern):
            f = tmp_path / "audio.mp3"
            f.write_bytes(b"fake mp3")
            return [f]

        with patch.dict(sys.modules, {"yt_dlp": mock_yt_dlp}), \
             patch("ppke.audio.transcriber.transcribe", return_value="# T\n\nText"), \
             patch("pathlib.Path.glob", fake_glob):
            from ppke.converter.youtube import convert_youtube
            result = convert_youtube("https://www.youtube.com/watch?v=test")
        assert "# YouTube Video" in result

    def test_convert_youtube_short_upload_date(self, tmp_path):
        info = {
            "title": "Video",
            "uploader": "U",
            "upload_date": "2025",  # not 8 chars
            "duration_string": "3:00",
            "duration": 180,
            "view_count": None,
        }
        mock_yt_dlp = self._make_yt_dlp_mock(info)

        def fake_glob(self_path, pattern):
            f = tmp_path / "audio.mp3"
            f.write_bytes(b"fake mp3")
            return [f]

        with patch.dict(sys.modules, {"yt_dlp": mock_yt_dlp}), \
             patch("ppke.audio.transcriber.transcribe", return_value="# T\n\nText"), \
             patch("pathlib.Path.glob", fake_glob):
            from ppke.converter.youtube import convert_youtube
            result = convert_youtube("https://www.youtube.com/watch?v=test")
        # upload_date not reformatted (not 8 chars)
        assert "# Video" in result
