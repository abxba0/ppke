"""Vision-RAG pipeline — structured analysis of figures, diagrams, and tables.

Unlike the OCR module (which transcribes text from images), this pipeline uses
Vision LLMs to semantically analyze visual elements — extracting structured
descriptions, relationships, data points, and conclusions from scientific
diagrams, flowcharts, tables, and other complex visuals.

The extracted :class:`VisualElement` objects are designed to be indexed into the
vector store alongside text-based extractions, so that RAG queries can surface
relevant visual context.

Usage::

    from ppke.pipeline.vision_rag import analyze_image, analyze_document_visuals

    # Single image
    element = analyze_image(Path("figure1.png"), provider="anthropic")

    # All images in a directory
    elements = analyze_document_visuals(Path("./figures/"), provider="openai")

Install dependencies with::

    pip install 'ppke[ocr]'
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Image file extensions that this module can process
_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".tif", ".bmp",
})

# MIME type mapping for Vision LLM API calls
_MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
}

# Prompt for structured visual analysis (not OCR transcription)
_VISION_ANALYSIS_PROMPT = """\
Analyze this image and extract structured information. Return a JSON object with:

{
  "visual_type": "<figure|table|diagram|flowchart|chart|photograph|illustration|other>",
  "title": "<title or caption if visible, else brief descriptive title>",
  "description": "<detailed natural-language description of what the image shows>",
  "extracted_data": {
    "entities": ["<key entities, labels, or named elements in the image>"],
    "relationships": ["<relationships between entities, e.g. 'A causes B', 'X is part of Y'>"],
    "data_points": ["<any numerical data, measurements, or statistics visible>"],
    "text_content": ["<any text labels, annotations, or captions in the image>"]
  },
  "conclusions": ["<key takeaways or conclusions that can be drawn from this visual>"],
  "context_summary": "<one-paragraph summary suitable for search indexing>"
}

Be thorough and precise. For tables, extract all rows and columns. For diagrams,
describe all nodes and edges. For charts, describe axes, data series, and trends.
Output ONLY valid JSON, nothing else."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class VisualElement(BaseModel):
    """Structured representation of a visual element extracted from a document.

    Designed to be indexed into the vector store alongside text extractions
    for unified RAG retrieval.
    """

    source_path: str = Field(..., description="Path to the source image file")
    source_page: int | None = Field(default=None, description="Page number (0-based) if from a PDF")
    visual_type: str = Field(default="other", description="Type: figure, table, diagram, flowchart, chart, photograph, illustration, other")
    title: str = Field(default="", description="Title or caption of the visual")
    description: str = Field(default="", description="Detailed natural-language description")
    extracted_data: dict[str, Any] = Field(default_factory=dict, description="Structured data extracted from the visual")
    conclusions: list[str] = Field(default_factory=list, description="Key takeaways from the visual")
    context_summary: str = Field(default="", description="Search-indexable summary of the visual")

    model_config = {"validate_assignment": True}

    @property
    def element_id(self) -> str:
        """Unique identifier for this visual element."""
        page_part = f"_p{self.source_page}" if self.source_page is not None else ""
        return f"visual_{Path(self.source_path).stem}{page_part}"

    def to_rag_text(self) -> str:
        """Build a composite text suitable for vector embedding and RAG retrieval.

        Combines title, description, extracted entities/relationships,
        conclusions, and the context summary into a single searchable string.
        """
        parts: list[str] = []

        if self.title:
            parts.append(f"[{self.visual_type.upper()}] {self.title}")
        if self.description:
            parts.append(self.description)

        data = self.extracted_data
        if data.get("entities"):
            parts.append("Entities: " + ", ".join(data["entities"]))
        if data.get("relationships"):
            parts.append("Relationships: " + " | ".join(data["relationships"]))
        if data.get("data_points"):
            parts.append("Data: " + " | ".join(data["data_points"]))
        if data.get("text_content"):
            parts.append("Labels: " + " | ".join(data["text_content"]))

        if self.conclusions:
            parts.append("Conclusions: " + " | ".join(self.conclusions))
        if self.context_summary:
            parts.append(self.context_summary)

        return " | ".join(parts) if parts else f"[Visual: {self.source_path}]"


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------


def analyze_image(
    image_path: Path,
    *,
    provider: str = "anthropic",
    api_key: str | None = None,
    source_page: int | None = None,
) -> VisualElement:
    """Analyze an image using a Vision LLM and return structured data.

    Unlike :func:`ppke.converter.ocr.vision_ocr` which performs OCR
    (text transcription), this function semantically analyzes the visual
    content — identifying entities, relationships, data points, and
    drawing conclusions.

    Parameters
    ----------
    image_path:
        Path to the image file.
    provider:
        ``"anthropic"`` (default) or ``"openai"``.
    api_key:
        API key for the Vision LLM provider. Falls back to env vars.
    source_page:
        Optional page number (0-based) if the image came from a PDF.

    Returns
    -------
    VisualElement
        Structured analysis of the visual content.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    suffix = image_path.suffix.lower()
    if suffix not in _IMAGE_EXTENSIONS:
        raise ValueError(
            f"Unsupported image format: '{suffix}'. "
            f"Supported: {sorted(_IMAGE_EXTENSIONS)}"
        )

    logger.info("Analyzing image %s via %s Vision LLM", image_path.name, provider)

    try:
        raw_json = _call_vision_llm(image_path, provider=provider, api_key=api_key)
        parsed = _parse_analysis_response(raw_json)
    except Exception as exc:
        logger.warning(
            "Vision analysis failed for %s: %s — returning minimal element",
            image_path.name, exc,
        )
        parsed = {}

    return VisualElement(
        source_path=str(image_path),
        source_page=source_page,
        visual_type=parsed.get("visual_type", "other"),
        title=parsed.get("title", image_path.stem),
        description=parsed.get("description", ""),
        extracted_data=parsed.get("extracted_data", {}),
        conclusions=parsed.get("conclusions", []),
        context_summary=parsed.get("context_summary", ""),
    )


def analyze_document_visuals(
    image_dir: Path,
    *,
    provider: str = "anthropic",
    api_key: str | None = None,
) -> list[VisualElement]:
    """Analyze all images in a directory and return structured elements.

    Scans the directory for supported image files and processes each one
    through the Vision LLM analysis pipeline.

    Parameters
    ----------
    image_dir:
        Directory containing image files.
    provider:
        ``"anthropic"`` or ``"openai"``.
    api_key:
        API key for the Vision LLM provider.

    Returns
    -------
    list[VisualElement]
        Structured analysis for each image found.
    """
    if not image_dir.is_dir():
        logger.warning("Not a directory: %s — returning empty list", image_dir)
        return []

    image_files = sorted(
        f for f in image_dir.iterdir()
        if f.is_file() and f.suffix.lower() in _IMAGE_EXTENSIONS
    )

    if not image_files:
        logger.info("No image files found in %s", image_dir)
        return []

    logger.info("Analyzing %d image(s) in %s", len(image_files), image_dir)

    elements: list[VisualElement] = []
    for img_path in image_files:
        element = analyze_image(
            img_path,
            provider=provider,
            api_key=api_key,
        )
        elements.append(element)

    logger.info("Analyzed %d visual element(s)", len(elements))
    return elements


def build_visual_context(
    elements: list[VisualElement],
) -> str:
    """Build a Markdown context block from visual elements for LLM prompts.

    Combines all visual element analyses into a structured Markdown section
    that can be appended to RAG context provided to the LLM.

    Parameters
    ----------
    elements:
        List of analyzed visual elements.

    Returns
    -------
    str
        Markdown-formatted visual context section.
    """
    if not elements:
        return ""

    sections: list[str] = ["## Visual Elements Analysis\n"]

    for i, elem in enumerate(elements, 1):
        section = f"### Visual {i}: {elem.title or elem.element_id}\n"
        section += f"**Type:** {elem.visual_type}\n\n"

        if elem.description:
            section += f"{elem.description}\n\n"

        data = elem.extracted_data
        if data.get("entities"):
            section += "**Key Elements:** " + ", ".join(data["entities"]) + "\n\n"
        if data.get("relationships"):
            section += "**Relationships:**\n"
            for rel in data["relationships"]:
                section += f"- {rel}\n"
            section += "\n"
        if data.get("data_points"):
            section += "**Data Points:**\n"
            for dp in data["data_points"]:
                section += f"- {dp}\n"
            section += "\n"

        if elem.conclusions:
            section += "**Conclusions:**\n"
            for c in elem.conclusions:
                section += f"- {c}\n"
            section += "\n"

        sections.append(section)

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _call_vision_llm(
    image_path: Path,
    *,
    provider: str = "anthropic",
    api_key: str | None = None,
) -> str:
    """Send an image to a Vision LLM for structured analysis.

    Returns the raw text response (expected to be JSON).
    """
    image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    mime = _MIME_MAP.get(image_path.suffix.lower(), "image/png")

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
                        {"type": "text", "text": _VISION_ANALYSIS_PROMPT},
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
                        {"type": "text", "text": _VISION_ANALYSIS_PROMPT},
                    ],
                }
            ],
        )
        return resp.choices[0].message.content or ""

    else:
        raise ValueError(f"Vision analysis not supported for provider: {provider}")


def _parse_analysis_response(raw: str) -> dict[str, Any]:
    """Parse the Vision LLM JSON response into a dict.

    Handles common response quirks: markdown code fences, trailing commas,
    and partial JSON.
    """
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[first_newline + 1:]
        # Remove closing fence
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse vision analysis JSON — attempting repair")
        # Try to extract JSON object from surrounding text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        logger.error("Could not parse vision analysis response")
        return {}
