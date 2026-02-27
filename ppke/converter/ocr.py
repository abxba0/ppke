"""OCR utilities — Tesseract and Vision LLM fallback.

Uses pytesseract for standard OCR, with optional Vision LLM (Claude / GPT-4V)
fallback for complex layouts (handwriting, tables, diagrams).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def ocr_image(image_path: Path) -> str:
    """OCR a single image file using Tesseract.

    Falls back to a simple file-content description if Tesseract is not
    installed.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise ImportError(
            "Image OCR requires pytesseract + Pillow. "
            "Install with: pip install 'ppke[ocr]'"
        )

    img = Image.open(image_path)
    text = pytesseract.image_to_string(img).strip()
    if not text:
        logger.warning("Tesseract returned empty text for %s", image_path.name)
        return f"[Image: {image_path.name} — no text detected by OCR]"
    return text


def ocr_pdf_pages(pdf_path: Path, page_numbers: list[int]) -> dict[int, str]:
    """OCR specific pages of a PDF that have no extractable text.

    Returns a dict mapping page number → OCR text.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError(
            "PDF OCR requires pytesseract + pdf2image + poppler. "
            "Install with: pip install 'ppke[ocr]'"
        )

    results: dict[int, str] = {}
    for page_num in page_numbers:
        images = convert_from_path(
            str(pdf_path), first_page=page_num + 1, last_page=page_num + 1
        )
        if images:
            text = pytesseract.image_to_string(images[0]).strip()
            if text:
                results[page_num] = text
            else:
                results[page_num] = f"[Page {page_num + 1}: no text detected by OCR]"
    return results


def vision_ocr(image_path: Path, provider: str = "anthropic", api_key: str | None = None) -> str:
    """Use a Vision LLM (Claude or GPT-4V) to OCR complex documents.

    Handles handwriting, tables, diagrams, and low-quality scans that
    Tesseract cannot parse reliably.
    """
    import base64

    image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".tiff": "image/tiff", ".tif": "image/tiff",
        ".bmp": "image/bmp",
    }
    mime = mime_map.get(image_path.suffix.lower(), "image/png")

    prompt = (
        "Transcribe this document page to Markdown. "
        "Preserve all headings, paragraphs, and structure exactly. "
        "For tables, use Markdown table syntax. "
        "For diagrams or figures, describe them in [brackets]. "
        "Output ONLY the transcribed Markdown, nothing else."
    )

    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": image_data}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return resp.content[0].text

    elif provider == "openai":
        import openai

        client = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_data}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return resp.choices[0].message.content or ""

    else:
        raise ValueError(f"Vision OCR not supported for provider: {provider}")
