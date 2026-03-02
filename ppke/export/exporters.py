"""Document exporters — PDF, DOCX, PPTX, and Markdown ZIP.

Each function takes a book directory (Path) and returns bytes suitable for
streaming back via FastAPI ``Response``.

Dependencies:
- PDF:  ``weasyprint`` (falls back to simple HTML rendering)
- DOCX: ``python-docx``
- PPTX: ``python-pptx``
- ZIP:  stdlib ``zipfile``
"""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ── Shared helpers ──


def _load_meta(book_dir: Path) -> dict[str, Any]:
    meta_path = book_dir / "meta.yml"
    if meta_path.exists():
        return yaml.safe_load(meta_path.read_text()) or {}
    return {}


def _load_md_file(book_dir: Path, filename: str, max_chars: int = 0) -> str:
    path = book_dir / filename
    if not path.exists():
        return ""
    text = path.read_text()
    if max_chars and len(text) > max_chars:
        return text[:max_chars]
    return text


def _load_extractions(book_dir: Path) -> list[dict]:
    path = book_dir / "extractions.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


# ── Markdown → HTML (shared by PDF) ──

_MD_FILES = [
    ("01_Raw_Structure.md", "Structure"),
    ("02_Logical_Map.md", "Logical Map"),
    ("03_Concept_Index.md", "Concept Index"),
    ("04_Author_Model.md", "Author Model"),
    ("06_Patterns.md", "Patterns"),
]


def _md_to_simple_html(md_text: str) -> str:
    """Minimal Markdown-to-HTML for rendering in PDF/DOCX.

    Handles headings, bold, italic, bullet lists, horizontal rules, and code blocks.
    """
    lines = md_text.split("\n")
    html_lines: list[str] = []
    in_list = False
    in_code = False

    for line in lines:
        stripped = line.strip()

        # Code fences
        if stripped.startswith("```"):
            if in_code:
                html_lines.append("</pre>")
                in_code = False
            else:
                html_lines.append('<pre style="background:#f5f5f5;padding:8px;font-size:0.85em;border-radius:4px">')
                in_code = True
            continue
        if in_code:
            html_lines.append(line)
            continue

        # Close list if leaving list context
        if in_list and not stripped.startswith(("- ", "* ", "• ")):
            html_lines.append("</ul>")
            in_list = False

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            html_lines.append("<hr>")
            continue

        # Headings
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{_inline(stripped[2:])}</h1>")
            continue
        if stripped.startswith("## "):
            html_lines.append(f"<h2>{_inline(stripped[3:])}</h2>")
            continue
        if stripped.startswith("### "):
            html_lines.append(f"<h3>{_inline(stripped[4:])}</h3>")
            continue
        if stripped.startswith("#### "):
            html_lines.append(f"<h4>{_inline(stripped[5:])}</h4>")
            continue

        # Bullet lists
        if stripped.startswith(("- ", "* ", "• ")):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            content = stripped[2:]
            html_lines.append(f"<li>{_inline(content)}</li>")
            continue

        # Empty line
        if not stripped:
            html_lines.append("")
            continue

        # Regular paragraph
        html_lines.append(f"<p>{_inline(stripped)}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_code:
        html_lines.append("</pre>")

    return "\n".join(html_lines)


def _inline(text: str) -> str:
    """Convert inline Markdown formatting (bold, italic, code)."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


# ── PDF export ──


def export_pdf(book_dir: Path) -> bytes:
    """Generate a typeset PDF report from all book analysis files.

    Uses weasyprint if available, falls back to a simple HTML-to-bytes approach.
    """
    meta = _load_meta(book_dir)
    title = meta.get("title", book_dir.name)
    author = meta.get("author", "Unknown")
    year = meta.get("year", "")

    # Build HTML document
    sections_html = ""
    for filename, section_title in _MD_FILES:
        md_text = _load_md_file(book_dir, filename)
        if md_text:
            sections_html += f'<div class="section"><h2>{section_title}</h2>\n{_md_to_simple_html(md_text)}</div>\n'

    # Include summary if generated
    summary_md = _load_md_file(book_dir, "summary.md")
    if summary_md:
        sections_html = f'<div class="section">{_md_to_simple_html(summary_md)}</div>\n' + sections_html

    # Include study guide if generated
    study_md = _load_md_file(book_dir, "study_guide.md")
    if study_md:
        sections_html += f'<div class="section"><h2>Study Guide</h2>\n{_md_to_simple_html(study_md)}</div>\n'

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{
    size: A4;
    margin: 2cm;
    @bottom-center {{ content: counter(page) " / " counter(pages); font-size: 9pt; color: #999; }}
}}
body {{
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #222;
}}
h1 {{
    font-size: 22pt;
    color: #1a1a2e;
    border-bottom: 2px solid #4361ee;
    padding-bottom: 8px;
    margin-top: 0;
}}
h2 {{
    font-size: 16pt;
    color: #1a1a2e;
    border-bottom: 1px solid #ddd;
    padding-bottom: 4px;
    margin-top: 28px;
    page-break-after: avoid;
}}
h3 {{
    font-size: 13pt;
    color: #333;
    margin-top: 20px;
    page-break-after: avoid;
}}
h4 {{ font-size: 11pt; color: #555; margin-top: 16px; }}
p {{ margin: 6px 0; text-align: justify; }}
ul {{ margin: 6px 0 6px 20px; }}
li {{ margin: 3px 0; }}
hr {{ border: none; border-top: 1px solid #ccc; margin: 20px 0; }}
code {{
    background: #f0f0f0;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 0.9em;
}}
pre {{
    background: #f5f5f5;
    padding: 10px;
    border-radius: 4px;
    font-size: 0.85em;
    overflow-x: auto;
}}
strong {{ color: #1a1a2e; }}
.cover {{
    text-align: center;
    padding: 120px 40px 60px;
    page-break-after: always;
}}
.cover h1 {{
    font-size: 28pt;
    border: none;
    margin-bottom: 12px;
}}
.cover .author {{ font-size: 14pt; color: #666; margin-top: 8px; }}
.cover .meta {{ font-size: 10pt; color: #999; margin-top: 30px; }}
.section {{ page-break-before: auto; margin-bottom: 24px; }}
</style>
</head>
<body>
<div class="cover">
    <h1>{_html_escape(title)}</h1>
    <div class="author">{_html_escape(author)}{f' ({year})' if year else ''}</div>
    <div class="meta">
        Analysis Report &mdash; Generated by PPKE<br>
        {meta.get('total_chapters', '?')} chapters &middot; {meta.get('total_paragraphs', '?')} paragraphs
    </div>
</div>
{sections_html}
</body>
</html>"""

    try:
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
        return pdf_bytes
    except ImportError:
        # Fallback: return HTML as "PDF" (browser can still render it)
        logger.warning("weasyprint not installed — returning HTML report instead of PDF")
        return html.encode("utf-8")


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ── DOCX export ──


def export_docx(book_dir: Path) -> bytes:
    """Generate a Word document from all book analysis files.

    Requires ``python-docx``.
    """
    try:
        from docx import Document
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise ImportError(
            "DOCX export requires python-docx. Install with: pip install python-docx"
        )

    meta = _load_meta(book_dir)
    title = meta.get("title", book_dir.name)
    author = meta.get("author", "Unknown")
    year = meta.get("year", "")

    doc = Document()

    # Title page
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(title)
    title_run.bold = True
    title_run.font.size = Pt(24)
    title_run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)

    author_para = doc.add_paragraph()
    author_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    author_run = author_para.add_run(f"{author}{f' ({year})' if year else ''}")
    author_run.font.size = Pt(14)
    author_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    meta_para = doc.add_paragraph()
    meta_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_run = meta_para.add_run(
        f"Analysis Report — Generated by PPKE\n"
        f"{meta.get('total_chapters', '?')} chapters · {meta.get('total_paragraphs', '?')} paragraphs"
    )
    meta_run.font.size = Pt(9)
    meta_run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    doc.add_page_break()

    # Include summary first if available
    summary_md = _load_md_file(book_dir, "summary.md")
    if summary_md:
        _add_md_to_docx(doc, summary_md)
        doc.add_page_break()

    # Add each analysis section
    for filename, section_title in _MD_FILES:
        md_text = _load_md_file(book_dir, filename)
        if md_text:
            doc.add_heading(section_title, level=1)
            _add_md_to_docx(doc, md_text)

    # Study guide
    study_md = _load_md_file(book_dir, "study_guide.md")
    if study_md:
        doc.add_heading("Study Guide", level=1)
        _add_md_to_docx(doc, study_md)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _add_md_to_docx(doc: Any, md_text: str) -> None:
    """Add Markdown content to a python-docx Document, handling basic formatting."""
    from docx.shared import Pt

    for line in md_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Headings
        if stripped.startswith("#### "):
            doc.add_heading(stripped[5:], level=4)
        elif stripped.startswith("### "):
            doc.add_heading(stripped[4:], level=3)
        elif stripped.startswith("## "):
            doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith("# "):
            doc.add_heading(stripped[2:], level=1)
        elif stripped in ("---", "***", "___"):
            # Horizontal rule → thin paragraph
            p = doc.add_paragraph()
            p.add_run("─" * 60).font.size = Pt(6)
        elif stripped.startswith(("- ", "* ", "• ")):
            content = stripped[2:]
            _add_formatted_paragraph(doc, content, style="List Bullet")
        else:
            _add_formatted_paragraph(doc, stripped)


def _add_formatted_paragraph(doc: Any, text: str, style: str | None = None) -> None:
    """Add a paragraph with inline bold/italic formatting."""
    from docx.shared import Pt

    if style:
        para = doc.add_paragraph(style=style)
    else:
        para = doc.add_paragraph()

    # Split on bold/italic markers and add runs
    parts = re.split(r"(\*\*.*?\*\*|\*.*?\*|`.*?`)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            run = para.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*") and part.endswith("*"):
            run = para.add_run(part[1:-1])
            run.italic = True
        elif part.startswith("`") and part.endswith("`"):
            run = para.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        else:
            para.add_run(part)


# ── PPTX export ──


def export_pptx(book_dir: Path) -> bytes:
    """Generate a PowerPoint slide deck from key book concepts.

    Creates slides for: title, executive summary, key concepts,
    logical structure, patterns, and a concluding slide.
    """
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
    except ImportError:
        raise ImportError(
            "Slide deck export requires python-pptx. Install with: pip install python-pptx"
        )

    meta = _load_meta(book_dir)
    title = meta.get("title", book_dir.name)
    author = meta.get("author", "Unknown")
    year = meta.get("year", "")
    extractions = _load_extractions(book_dir)

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Slide 1: Title
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout
    _add_centered_text(slide, title, Inches(1), Inches(2), Inches(11.333), Inches(1.5), Pt(36), bold=True, color=RGBColor(0x1A, 0x1A, 0x2E))
    _add_centered_text(slide, f"{author}{f' ({year})' if year else ''}", Inches(1), Inches(3.5), Inches(11.333), Inches(0.8), Pt(18), color=RGBColor(0x66, 0x66, 0x66))
    _add_centered_text(slide, "Analysis Report — Generated by PPKE", Inches(1), Inches(5), Inches(11.333), Inches(0.5), Pt(12), color=RGBColor(0x99, 0x99, 0x99))

    # Slide 2: Executive Summary (if available)
    summary_md = _load_md_file(book_dir, "summary.md")
    if summary_md:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _add_slide_title(slide, "Executive Summary")
        # Extract bullet points from summary
        bullets = _extract_bullets(summary_md, max_bullets=6)
        _add_bullet_list(slide, bullets, Inches(0.8), Inches(1.6), Inches(11.7), Inches(5))

    # Slide 3: Key Concepts
    concepts: dict[str, int] = {}
    for ext in extractions:
        for c in ext.get("defined_concepts", []):
            key = c.strip()
            concepts[key] = concepts.get(key, 0) + 1
    top_concepts = sorted(concepts.items(), key=lambda x: -x[1])[:10]
    if top_concepts:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _add_slide_title(slide, "Key Concepts")
        bullets = [f"{name} (mentioned {count}×)" for name, count in top_concepts]
        _add_bullet_list(slide, bullets, Inches(0.8), Inches(1.6), Inches(11.7), Inches(5))

    # Slide 4: Logical Structure
    logic_md = _load_md_file(book_dir, "02_Logical_Map.md", max_chars=3000)
    if logic_md:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _add_slide_title(slide, "Logical Structure")
        bullets = _extract_bullets(logic_md, max_bullets=7)
        _add_bullet_list(slide, bullets, Inches(0.8), Inches(1.6), Inches(11.7), Inches(5))

    # Slide 5: Key Claims
    all_claims: list[str] = []
    for ext in extractions:
        for claim in ext.get("explicit_claims", [])[:1]:
            if len(claim) > 20:
                all_claims.append(claim)
            if len(all_claims) >= 8:
                break
        if len(all_claims) >= 8:
            break
    if all_claims:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _add_slide_title(slide, "Key Claims")
        _add_bullet_list(slide, all_claims[:8], Inches(0.8), Inches(1.6), Inches(11.7), Inches(5))

    # Slide 6: Patterns & Tensions
    patterns_md = _load_md_file(book_dir, "06_Patterns.md", max_chars=3000)
    if patterns_md:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _add_slide_title(slide, "Patterns & Tensions")
        bullets = _extract_bullets(patterns_md, max_bullets=6)
        _add_bullet_list(slide, bullets, Inches(0.8), Inches(1.6), Inches(11.7), Inches(5))

    # Final slide
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    stats = f"{meta.get('total_chapters', '?')} chapters · {meta.get('total_paragraphs', '?')} paragraphs · {len(concepts)} concepts"
    _add_centered_text(slide, title, Inches(1), Inches(2.5), Inches(11.333), Inches(1), Pt(28), bold=True, color=RGBColor(0x1A, 0x1A, 0x2E))
    _add_centered_text(slide, stats, Inches(1), Inches(3.8), Inches(11.333), Inches(0.5), Pt(14), color=RGBColor(0x66, 0x66, 0x66))
    _add_centered_text(slide, "Generated by PPKE — Personal & Professional Knowledge Engine", Inches(1), Inches(5), Inches(11.333), Inches(0.5), Pt(11), color=RGBColor(0x99, 0x99, 0x99))

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _add_centered_text(slide: Any, text: str, left: Any, top: Any, width: Any, height: Any,
                        font_size: Any, bold: bool = False, color: Any = None) -> None:
    from pptx.enum.text import PP_ALIGN
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = font_size
    p.font.bold = bold
    p.alignment = PP_ALIGN.CENTER
    if color:
        p.font.color.rgb = color


def _add_slide_title(slide: Any, title: str) -> None:
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    txBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(0.9))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
    p.alignment = PP_ALIGN.LEFT


def _add_bullet_list(slide: Any, bullets: list[str], left: Any, top: Any, width: Any, height: Any) -> None:
    from pptx.util import Pt
    from pptx.dml.color import RGBColor

    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, bullet in enumerate(bullets):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = f"• {bullet}"
        p.font.size = Pt(16)
        p.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        p.space_after = Pt(8)


def _extract_bullets(md_text: str, max_bullets: int = 6) -> list[str]:
    """Extract bullet points or key lines from Markdown text."""
    bullets: list[str] = []
    for line in md_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "• ")):
            text = stripped[2:].strip()
            # Clean inline markdown
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
            text = re.sub(r"\*(.+?)\*", r"\1", text)
            text = re.sub(r"`(.+?)`", r"\1", text)
            if len(text) > 15:
                bullets.append(text[:200])
        if len(bullets) >= max_bullets:
            break
    # If no bullets found, extract from headings or first non-empty lines
    if not bullets:
        for line in md_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("## ", "### ")) and len(stripped) > 5:
                text = re.sub(r"^#+\s*", "", stripped)
                bullets.append(text[:200])
            elif len(stripped) > 30 and not stripped.startswith("#"):
                text = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
                bullets.append(text[:200])
            if len(bullets) >= max_bullets:
                break
    return bullets


# ── Markdown ZIP export ──


def export_markdown_zip(book_dir: Path) -> bytes:
    """Create a ZIP archive of all Markdown files and metadata for a book."""
    buf = io.BytesIO()
    folder_name = book_dir.name

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # meta.yml
        meta_path = book_dir / "meta.yml"
        if meta_path.exists():
            zf.writestr(f"{folder_name}/meta.yml", meta_path.read_text())

        # All analysis Markdown files
        for filename, _ in _MD_FILES:
            fpath = book_dir / filename
            if fpath.exists():
                zf.writestr(f"{folder_name}/{filename}", fpath.read_text())

        # Generated content
        for extra in ("summary.md", "study_guide.md", "extractions.json"):
            fpath = book_dir / extra
            if fpath.exists():
                zf.writestr(f"{folder_name}/{extra}", fpath.read_text())

        # Audio script if present
        script_path = book_dir / "audio_script.json"
        if script_path.exists():
            zf.writestr(f"{folder_name}/audio_script.json", script_path.read_text())

    return buf.getvalue()


# ── LaTeX export ──


def _latex_escape(s: str) -> str:
    """Escape special LaTeX characters in a string."""
    replacements = [
        ("\\", "\\textbackslash{}"),
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ]
    for char, escaped in replacements:
        s = s.replace(char, escaped)
    return s


def _inline_latex(text: str) -> str:
    """Convert inline Markdown formatting to LaTeX commands."""
    # Bold: **text** → \textbf{text}
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: f"\\textbf{{{_latex_escape(m.group(1))}}}", text)
    # Italic: *text* → \textit{text}
    text = re.sub(r"\*(.+?)\*", lambda m: f"\\textit{{{_latex_escape(m.group(1))}}}", text)
    # Code: `text` → \texttt{text}
    text = re.sub(r"`(.+?)`", lambda m: f"\\texttt{{{_latex_escape(m.group(1))}}}", text)
    return text


def _md_to_latex(md_text: str) -> str:
    """Convert Markdown text to LaTeX, handling common formatting."""
    lines = md_text.split("\n")
    latex_lines: list[str] = []
    in_code = False
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Code fences
        if stripped.startswith("```"):
            if in_code:
                latex_lines.append("\\end{verbatim}")
                in_code = False
            else:
                if in_list:
                    latex_lines.append("\\end{itemize}")
                    in_list = False
                latex_lines.append("\\begin{verbatim}")
                in_code = True
            continue
        if in_code:
            latex_lines.append(line)
            continue

        # Close list if leaving list context
        if in_list and not stripped.startswith(("- ", "* ", "• ")):
            latex_lines.append("\\end{itemize}")
            in_list = False

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            latex_lines.append("\\medskip\\hrule\\medskip")
            continue

        # Headings (top-level # becomes \section, deeper levels are subsections)
        if stripped.startswith("#### "):
            latex_lines.append(f"\\paragraph{{{_latex_escape(stripped[5:])}}}")
            continue
        if stripped.startswith("### "):
            latex_lines.append(f"\\subsubsection{{{_latex_escape(stripped[4:])}}}")
            continue
        if stripped.startswith("## "):
            latex_lines.append(f"\\subsection{{{_latex_escape(stripped[3:])}}}")
            continue
        if stripped.startswith("# "):
            latex_lines.append(f"\\section{{{_latex_escape(stripped[2:])}}}")
            continue

        # Bullet lists
        if stripped.startswith(("- ", "* ", "• ")):
            if not in_list:
                latex_lines.append("\\begin{itemize}")
                in_list = True
            content = _inline_latex(stripped[2:])
            latex_lines.append(f"  \\item {content}")
            continue

        # Empty line
        if not stripped:
            latex_lines.append("")
            continue

        # Regular paragraph
        latex_lines.append(_inline_latex(stripped) + "\n")

    if in_list:
        latex_lines.append("\\end{itemize}")
    if in_code:
        latex_lines.append("\\end{verbatim}")

    return "\n".join(latex_lines)


def export_latex(book_dir: Path) -> bytes:
    """Generate a LaTeX (.tex) document from a book's analysis files.

    Produces a self-contained LaTeX document suitable for compilation
    with pdflatex or xelatex.  Sections correspond to the standard PPKE
    analysis files (structure, logical map, concept index, etc.).

    Parameters
    ----------
    book_dir : Path
        Book directory containing ``meta.yml`` and analysis Markdown files.

    Returns
    -------
    bytes
        UTF-8 encoded LaTeX source.
    """
    meta = _load_meta(book_dir)
    title = _latex_escape(meta.get("title", book_dir.name))
    author = _latex_escape(meta.get("author", "Unknown"))
    year = str(meta.get("year", ""))

    sections: list[str] = []

    summary_md = _load_md_file(book_dir, "summary.md")
    if summary_md:
        sections.append(_md_to_latex(summary_md))

    for filename, section_title in _MD_FILES:
        md_text = _load_md_file(book_dir, filename)
        if md_text:
            sections.append(
                f"\\section{{{_latex_escape(section_title)}}}\n\n{_md_to_latex(md_text)}"
            )

    study_md = _load_md_file(book_dir, "study_guide.md")
    if study_md:
        sections.append(f"\\section{{Study Guide}}\n\n{_md_to_latex(study_md)}")

    body = "\n\n".join(sections)
    date_field = year if year else "\\today"

    doc = (
        "\\documentclass[12pt,a4paper]{article}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\usepackage{lmodern}\n"
        "\\usepackage{microtype}\n"
        "\\usepackage{hyperref}\n"
        "\\usepackage{parskip}\n"
        "\n"
        f"\\title{{{title}}}\n"
        f"\\author{{{author}}}\n"
        f"\\date{{{date_field}}}\n"
        "\n"
        "\\begin{document}\n"
        "\n"
        "\\maketitle\n"
        "\\tableofcontents\n"
        "\\newpage\n"
        "\n"
        f"{body}\n"
        "\n"
        "\\end{document}\n"
    )
    return doc.encode("utf-8")


# ── BibTeX export ──


def _make_cite_key(meta: dict[str, Any]) -> str:
    """Generate a BibTeX cite key from author last name and year."""
    author = meta.get("author", "Unknown")
    year = str(meta.get("year", ""))
    last_name = re.split(r"[,\s]+", author.strip())[0]
    last_name = re.sub(r"[^a-zA-Z0-9]", "", last_name) or "Unknown"
    return f"{last_name}{year}" if year else last_name


def _bibtex_escape(s: str) -> str:
    """Escape BibTeX special characters in a field value.

    Protects unmatched braces.  Backslashes are left as-is since they
    typically introduce LaTeX commands in BibTeX values.
    """
    s = s.replace("{", "\\{")
    s = s.replace("}", "\\}")
    return s


def meta_to_bibtex_entry(meta: dict[str, Any], cite_key: str | None = None) -> str:
    """Convert a book metadata dict to a BibTeX ``@book`` entry string.

    Parameters
    ----------
    meta : dict
        Book metadata (from ``meta.yml``).
    cite_key : str | None
        Override the auto-generated cite key.

    Returns
    -------
    str
        A BibTeX ``@book`` entry.
    """
    key = cite_key or _make_cite_key(meta)
    fields: list[str] = []

    if meta.get("title"):
        fields.append(f"  title     = {{{_bibtex_escape(meta['title'])}}}")
    if meta.get("author"):
        fields.append(f"  author    = {{{_bibtex_escape(meta['author'])}}}")
    if meta.get("year"):
        fields.append(f"  year      = {{{meta['year']}}}")
    if meta.get("publisher"):
        fields.append(f"  publisher = {{{_bibtex_escape(meta['publisher'])}}}")
    if meta.get("isbn"):
        fields.append(f"  isbn      = {{{_bibtex_escape(str(meta['isbn']))}}}")
    if meta.get("doi"):
        fields.append(f"  doi       = {{{_bibtex_escape(meta['doi'])}}}")
    if meta.get("url"):
        fields.append(f"  url       = {{{_bibtex_escape(meta['url'])}}}")
    if meta.get("language"):
        fields.append(f"  language  = {{{_bibtex_escape(meta['language'])}}}")
    if meta.get("domain"):
        fields.append(f"  note      = {{domain: {_bibtex_escape(meta['domain'])}}}")

    body = ",\n".join(fields)
    return f"@book{{{key},\n{body}\n}}"


def export_bibtex(book_dir: Path) -> bytes:
    """Generate a BibTeX (.bib) entry for a single book.

    Reads ``meta.yml`` and produces a ``@book`` BibTeX entry that is
    round-trip compatible with the existing BibTeX importer
    (``ppke.converter.zotero``).

    Parameters
    ----------
    book_dir : Path
        Book directory containing ``meta.yml``.

    Returns
    -------
    bytes
        UTF-8 encoded BibTeX source.
    """
    meta = _load_meta(book_dir)
    entry = meta_to_bibtex_entry(meta)
    header = f"% BibTeX export generated by PPKE\n% Book: {book_dir.name}\n\n"
    return (header + entry + "\n").encode("utf-8")
