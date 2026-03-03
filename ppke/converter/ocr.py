"""OCR utilities — Tesseract with confidence scoring and Vision LLM fallback.

Pipeline for each page/image:
  1. Tesseract OCR → confidence score (0-100)
  2. If mean confidence < threshold (default 55) → Vision LLM fallback
  3. Language is auto-detected from the first high-confidence page

The Vision LLM path uses Claude (Anthropic) or GPT-4o (OpenAI) depending on
which provider is configured.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Pages with mean Tesseract confidence below this value are re-OCR'd
# via a Vision LLM.  Range 0-100; typical good scans score 70+.
_CONFIDENCE_THRESHOLD = 55.0


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def ocr_image(
    image_path: Path,
    *,
    lang: str | None = None,
    use_vision_fallback: bool = True,
    preprocess: bool = True,
    api_key: str | None = None,
    provider: str = "anthropic",
) -> str:
    """OCR a single image file.

    Uses Tesseract with optional Vision LLM fallback for low-confidence pages.

    Parameters
    ----------
    image_path:
        Path to the image file.
    lang:
        Tesseract language code (e.g. ``"eng"``, ``"deu"``). Auto-detected
        from the image when ``None``.
    use_vision_fallback:
        When ``True`` (default), pages with mean confidence below
        ``_CONFIDENCE_THRESHOLD`` are re-processed with a Vision LLM.
    preprocess:
        When ``True`` (default), apply image preprocessing (deskew, denoise,
        contrast enhancement) via OpenCV before OCR.  Degrades gracefully
        when OpenCV is not installed.
    api_key:
        API key for the Vision LLM provider. Falls back to environment vars.
    provider:
        ``"anthropic"`` or ``"openai"``.
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

    # Image preprocessing (deskew, denoise, contrast enhancement)
    if preprocess:
        try:
            from ppke.converter.preprocess import preprocess_for_ocr

            img = preprocess_for_ocr(img, deskew=True, denoise=True, contrast=True)
        except Exception as exc:
            logger.debug("Image preprocessing skipped: %s", exc)

    # Auto-detect language if not specified
    if lang is None:
        lang = _detect_language(img) or "eng"

    text, confidence = _tesseract_with_confidence(img, lang=lang)

    if not text.strip():
        logger.warning("Tesseract returned empty text for %s (confidence=%.1f)", image_path.name, confidence)
        if use_vision_fallback:
            logger.info("Trying Vision LLM for %s", image_path.name)
            try:
                return vision_ocr(image_path, provider=provider, api_key=api_key)
            except Exception as exc:
                logger.warning("Vision LLM failed for %s: %s", image_path.name, exc)
        return f"[Image: {image_path.name} — no text detected by OCR]"

    if confidence < _CONFIDENCE_THRESHOLD and use_vision_fallback:
        logger.info(
            "Low Tesseract confidence (%.1f) for %s — trying Vision LLM",
            confidence,
            image_path.name,
        )
        try:
            return vision_ocr(image_path, provider=provider, api_key=api_key)
        except Exception as exc:
            logger.warning(
                "Vision LLM failed (%.1f confidence) for %s: %s",
                confidence,
                image_path.name,
                exc,
            )

    return text


def ocr_pdf_pages(
    pdf_path: Path,
    page_numbers: list[int],
    *,
    lang: str | None = None,
    use_vision_fallback: bool = True,
    preprocess: bool = True,
    api_key: str | None = None,
    provider: str = "anthropic",
) -> dict[int, str]:
    """OCR specific pages of a PDF that have no extractable text.

    Returns a dict mapping ``page_number → OCR text``.

    The first page with high confidence establishes the detected language for
    subsequent pages (avoids per-page detection overhead).
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
    detected_lang: str | None = lang  # persists across pages once detected

    for page_num in page_numbers:
        images = convert_from_path(
            str(pdf_path), first_page=page_num + 1, last_page=page_num + 1
        )
        if not images:
            continue

        img = images[0]

        # Image preprocessing (deskew, denoise, contrast)
        if preprocess:
            try:
                from ppke.converter.preprocess import preprocess_for_ocr

                img = preprocess_for_ocr(img, deskew=True, denoise=True, contrast=True)
            except Exception as exc:
                logger.debug("Image preprocessing skipped for page %d: %s", page_num + 1, exc)

        # Auto-detect language from first page (reuse for subsequent pages)
        if detected_lang is None:
            detected_lang = _detect_language(img) or "eng"
            logger.debug("Detected OCR language '%s' from page %d", detected_lang, page_num + 1)

        text, confidence = _tesseract_with_confidence(img, lang=detected_lang)

        # Vision LLM fallback for low-confidence or empty pages
        if (not text.strip() or confidence < _CONFIDENCE_THRESHOLD) and use_vision_fallback:
            logger.info(
                "Page %d has low OCR confidence (%.1f) — trying Vision LLM",
                page_num + 1,
                confidence,
            )
            try:
                # Write page image to a temp file for vision_ocr
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                img.save(str(tmp_path), format="PNG")
                try:
                    text = vision_ocr(tmp_path, provider=provider, api_key=api_key)
                    confidence = 100.0  # Vision LLM is authoritative
                finally:
                    tmp_path.unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("Vision LLM failed for page %d: %s", page_num + 1, exc)

        if text.strip():
            # Annotate with confidence when it was low
            if confidence < _CONFIDENCE_THRESHOLD:
                text = f"<!-- OCR confidence: {confidence:.0f}% -->\n\n{text}"
            results[page_num] = text
        else:
            results[page_num] = f"[Page {page_num + 1}: no text detected by OCR]"

    return results


def vision_ocr(
    image_path: Path,
    provider: str = "anthropic",
    api_key: str | None = None,
) -> str:
    """Use a Vision LLM (Claude or GPT-4o) to OCR complex documents.

    Handles handwriting, tables, diagrams, and low-quality scans that
    Tesseract cannot parse reliably.

    Parameters
    ----------
    image_path:
        Path to the image file.
    provider:
        ``"anthropic"`` (default) or ``"openai"``.
    api_key:
        API key. Falls back to environment variables if not provided.
    """
    import base64

    image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
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
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return resp.content[0].text

    elif provider == "openai":
        import openai

        client = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{image_data}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return resp.choices[0].message.content or ""

    else:
        raise ValueError(f"Vision OCR not supported for provider: {provider}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tesseract_with_confidence(
    img: Any,
    *,
    lang: str = "eng",
) -> tuple[str, float]:
    """Run Tesseract and return ``(text, mean_confidence)``.

    Mean confidence is computed over all words that Tesseract actually
    recognises (confidence >= 0); empty pages return confidence 0.0.
    """
    import pytesseract

    try:
        data = pytesseract.image_to_data(
            img,
            lang=lang,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:
        logger.warning("pytesseract.image_to_data failed (%s) — falling back to image_to_string", exc)
        text = pytesseract.image_to_string(img, lang=lang).strip()
        return text, 50.0  # unknown confidence

    confidences = [c for c in data["conf"] if isinstance(c, (int, float)) and c >= 0]
    words = [
        w
        for w, c in zip(data["text"], data["conf"])
        if isinstance(c, (int, float)) and c > 0 and str(w).strip()
    ]

    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    text = " ".join(words)
    return text, mean_conf


def _detect_language(img: Any) -> str | None:
    """Detect the dominant script language in an image using Tesseract OSD.

    Returns a Tesseract language code (e.g. ``"eng"``, ``"deu"``) or ``None``
    if OSD is unavailable or inconclusive.

    The mapping covers the most common European and CJK scripts.
    """
    try:
        import pytesseract

        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
        script = osd.get("script", "")
    except Exception:
        return None

    # Map Tesseract OSD script names → language codes
    _SCRIPT_TO_LANG: dict[str, str] = {
        "Latin": "eng",
        "Han": "chi_sim",
        "Hangul": "kor",
        "Hiragana": "jpn",
        "Katakana": "jpn",
        "Devanagari": "hin",
        "Arabic": "ara",
        "Cyrillic": "rus",
        "Greek": "ell",
        "Hebrew": "heb",
        "Thai": "tha",
    }
    return _SCRIPT_TO_LANG.get(script)
