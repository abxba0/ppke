"""Data models for books, chapters, and paragraphs - REFACTORED with Pydantic."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, computed_field, field_validator


class DepthLevel(str, Enum):
    """Annotation depth for a paragraph."""

    FULL = "full"  # Argument-carrying paragraphs: deep annotation
    LIGHT = "light"  # Transitional/contextual: topic + function only
    SKIP = "skip"  # Non-content sections (Bibliography, Index, Appendix)


class Paragraph(BaseModel):
    """A single paragraph with its assigned ID and text."""

    chapter_number: int = Field(..., ge=0, description="Chapter number (0-indexed)")
    paragraph_number: int = Field(..., ge=1, description="Paragraph number within chapter")
    text: str = Field(..., min_length=1, description="Paragraph text content")
    depth: DepthLevel = Field(default=DepthLevel.LIGHT, description="Analysis depth")
    sub_number: Optional[int] = Field(default=None, description="Sub-paragraph index for splits")

    @computed_field
    @property
    def paragraph_id(self) -> str:
        """Format: {CH}.p{P} e.g. {03}.p12, or {CH}.p{P}.{S} for sub-paragraphs."""
        base = f"{{{self.chapter_number:02d}}}.p{self.paragraph_number}"
        if self.sub_number is not None:
            return f"{base}.{self.sub_number}"
        return base

    def __repr__(self) -> str:
        preview = self.text[:60] + "..." if len(self.text) > 60 else self.text
        return f"Paragraph({self.paragraph_id}, {preview!r})"

    model_config = {
        "frozen": False,  # Allow mutation during processing
        "validate_assignment": True,
        "str_strip_whitespace": True
    }


class Chapter(BaseModel):
    """A chapter containing ordered paragraphs."""

    number: int = Field(..., ge=0, description="Chapter number")
    title: str = Field(..., min_length=1, description="Chapter title")
    paragraphs: list[Paragraph] = Field(default_factory=list, description="List of paragraphs")

    @computed_field
    @property
    def paragraph_count(self) -> int:
        """Number of paragraphs in this chapter."""
        return len(self.paragraphs)

    def __repr__(self) -> str:
        return f"Chapter({self.number:02d}, {self.title!r}, {self.paragraph_count} paragraphs)"

    model_config = {"validate_assignment": True}


class Book(BaseModel):
    """A parsed book with chapters and metadata."""

    title: str = Field(..., min_length=1, description="Book title")
    author: str = Field(..., min_length=1, description="Book author")
    year: Optional[str] = Field(default=None, description="Publication year")
    source_path: Optional[str] = Field(default=None, description="Original markdown file path")
    chapters: list[Chapter] = Field(default_factory=list, description="List of chapters")

    @computed_field
    @property
    def total_paragraphs(self) -> int:
        """Total number of paragraphs across all chapters."""
        return sum(ch.paragraph_count for ch in self.chapters)

    @computed_field
    @property
    def folder_name(self) -> str:
        """Generate the KnowledgeBase folder name: Book_{Title}_{Author}_{YYYY}"""
        safe_title = re.sub(r'[^\w\s-]', '', self.title).replace(" ", "_")
        safe_author = re.sub(r'[^\w\s-]', '', self.author).replace(" ", "_")
        year_part = f"_{self.year}" if self.year else ""
        return f"Book_{safe_title}_{safe_author}{year_part}"

    @computed_field
    @property
    def all_paragraphs(self) -> list[Paragraph]:
        """Flatten all paragraphs across all chapters."""
        return [p for ch in self.chapters for p in ch.paragraphs]

    @computed_field
    @property
    def all_paragraph_ids(self) -> list[str]:
        """Get list of all paragraph IDs in the book."""
        return [p.paragraph_id for p in self.all_paragraphs]

    def __repr__(self) -> str:
        return (
            f"Book({self.title!r} by {self.author!r}, "
            f"{len(self.chapters)} chapters, {self.total_paragraphs} paragraphs)"
        )

    model_config = {"validate_assignment": True}


# ============================================================================
# EXTRACTION MODELS - Domain-agnostic base with dynamic extension
# ============================================================================


class BaseExtraction(BaseModel):
    """
    Core extraction fields shared across all domains.
    Domain-specific templates extend this with additional fields.
    """
    paragraph_id: str = Field(..., description="Paragraph identifier")
    original_text: str = Field(..., description="Original paragraph text")
    topic_sentence: str = Field(default="", description="One-sentence summary (<30 words)")
    defined_concepts: list[str] = Field(default_factory=list, description="Concepts introduced/defined")
    internal_references: list[str] = Field(default_factory=list, description="References to other sections")
    depth: DepthLevel = Field(default=DepthLevel.LIGHT, description="Analysis depth applied")

    model_config = {
        "extra": "allow",  # Allow template-specific fields (e.g., function_in_argument, legal_standard)
        "validate_assignment": True
    }


# Legacy ExtractionResult - kept for backward compatibility with v1.x
# Philosophy domain will use this through dynamic schema builder
class ExtractionResult(BaseExtraction):
    """
    Result of structural extraction for a single paragraph.
    LEGACY: Philosophy-specific model for v1.x compatibility.
    New domains should use BaseExtraction + dynamic schema builder.
    """
    function_in_argument: str = Field(default="", description="How this paragraph functions in the overall argument")
    explicit_claims: list[str] = Field(default_factory=list, description="Explicitly stated claims")
    implicit_assumptions: list[str] = Field(default_factory=list, description="Unstated assumptions")
    logical_steps: list[str] = Field(default_factory=list, description="Step-by-step logical progression")
    emotional_tone: str = Field(default="", description="Emotional register of the text")
    tone_evidence: str = Field(default="", description="Textual evidence for the tone")

    model_config = {
        "validate_assignment": True,
        "extra": "allow"
    }


# ============================================================================
# ANALYSIS RESULT MODELS
# ============================================================================


class ConceptEntry(BaseModel):
    """A concept tracked across a book."""

    name: str = Field(..., description="Concept name")
    occurrences: list[dict] = Field(default_factory=list, description="List of occurrences with paragraph_id, quote, context")
    semantic_shifts: list[dict] = Field(default_factory=list, description="Semantic shifts with from_id, to_id, description")

    model_config = {"validate_assignment": True}


class LogicalNode(BaseModel):
    """A node in the argument tree."""

    claim: str = Field(..., description="The claim being made")
    paragraph_ids: list[str] = Field(default_factory=list, description="Paragraph IDs supporting this claim")
    premises: list[str] = Field(default_factory=list, description="Premises supporting this claim")
    is_inference: bool = Field(default=False, description="Whether this is an inferred claim")
    children: list['LogicalNode'] = Field(default_factory=list, description="Child nodes in argument tree")

    model_config = {"validate_assignment": True}


class PatternEntry(BaseModel):
    """A detected pattern or tension."""

    pattern_type: str = Field(..., description="Type: metaphor, contradiction, repetition, recursion, emotional_arc")
    description: str = Field(..., description="Description of the pattern")
    evidence: list[dict] = Field(default_factory=list, description="Evidence with paragraph_id and quote")
    is_hypothesis: bool = Field(default=False, description="Whether this is a hypothetical pattern")

    model_config = {"validate_assignment": True}


class CoverageReport(BaseModel):
    """Coverage validation report for a book."""

    total_chapters: int = Field(default=0, description="Total number of chapters")
    total_paragraphs: int = Field(default=0, description="Total number of paragraphs")
    processed_paragraph_count: int = Field(default=0, description="Number of paragraphs processed")
    missing_paragraph_ids: list[str] = Field(default_factory=list, description="List of missing paragraph IDs")
    re_read_pass_completed: bool = Field(default=False, description="Whether re-read pass was completed")
    verification_status: str = Field(default="INCOMPLETE", description="Verification status")
    ingest_mode: str = Field(default="QUALITY_MAX", description="Ingestion mode used")
    ingest_date: str = Field(default="", description="Date of ingestion")
    notes: str = Field(default="", description="Additional notes")

    model_config = {"validate_assignment": True}


# Update forward references for recursive models
LogicalNode.model_rebuild()
