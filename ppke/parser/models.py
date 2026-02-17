"""Data models for books, chapters, and paragraphs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DepthLevel(Enum):
    """Annotation depth for a paragraph."""

    FULL = "full"  # Argument-carrying paragraphs: deep annotation
    LIGHT = "light"  # Transitional/contextual: topic + function only


@dataclass
class Paragraph:
    """A single paragraph with its assigned ID and text."""

    chapter_number: int
    paragraph_number: int
    text: str
    depth: DepthLevel = DepthLevel.LIGHT

    @property
    def paragraph_id(self) -> str:
        """Format: {CH}.p{P} e.g. {03}.p12"""
        return f"{{{self.chapter_number:02d}}}.p{self.paragraph_number}"

    def __repr__(self) -> str:
        preview = self.text[:60] + "..." if len(self.text) > 60 else self.text
        return f"Paragraph({self.paragraph_id}, {preview!r})"


@dataclass
class Chapter:
    """A chapter containing ordered paragraphs."""

    number: int
    title: str
    paragraphs: list[Paragraph] = field(default_factory=list)

    @property
    def paragraph_count(self) -> int:
        return len(self.paragraphs)

    def __repr__(self) -> str:
        return f"Chapter({self.number:02d}, {self.title!r}, {self.paragraph_count} paragraphs)"


@dataclass
class Book:
    """A parsed book with chapters and metadata."""

    title: str
    author: str
    year: Optional[str] = None
    source_path: Optional[str] = None
    chapters: list[Chapter] = field(default_factory=list)

    @property
    def total_paragraphs(self) -> int:
        return sum(ch.paragraph_count for ch in self.chapters)

    @property
    def folder_name(self) -> str:
        """Generate the KnowledgeBase folder name: Book_{Title}_{Author}_{YYYY}"""
        safe_title = self.title.replace(" ", "_")
        safe_author = self.author.replace(" ", "_")
        year_part = f"_{self.year}" if self.year else ""
        return f"Book_{safe_title}_{safe_author}{year_part}"

    @property
    def all_paragraphs(self) -> list[Paragraph]:
        return [p for ch in self.chapters for p in ch.paragraphs]

    @property
    def all_paragraph_ids(self) -> list[str]:
        return [p.paragraph_id for p in self.all_paragraphs]

    def __repr__(self) -> str:
        return (
            f"Book({self.title!r} by {self.author!r}, "
            f"{len(self.chapters)} chapters, {self.total_paragraphs} paragraphs)"
        )


@dataclass
class ExtractionResult:
    """Result of structural extraction for a single paragraph."""

    paragraph_id: str
    original_text: str
    topic_sentence: str = ""
    function_in_argument: str = ""
    explicit_claims: list[str] = field(default_factory=list)
    implicit_assumptions: list[str] = field(default_factory=list)
    logical_steps: list[str] = field(default_factory=list)
    defined_concepts: list[str] = field(default_factory=list)
    emotional_tone: str = ""
    tone_evidence: str = ""
    internal_references: list[str] = field(default_factory=list)
    depth: DepthLevel = DepthLevel.LIGHT


@dataclass
class ConceptEntry:
    """A concept tracked across a book."""

    name: str
    occurrences: list[dict] = field(default_factory=list)  # [{paragraph_id, quote, context}]
    semantic_shifts: list[dict] = field(default_factory=list)  # [{from_id, to_id, description}]


@dataclass
class LogicalNode:
    """A node in the argument tree."""

    claim: str
    paragraph_ids: list[str] = field(default_factory=list)
    premises: list[str] = field(default_factory=list)
    is_inference: bool = False
    children: list[LogicalNode] = field(default_factory=list)


@dataclass
class PatternEntry:
    """A detected pattern or tension."""

    pattern_type: str  # metaphor, contradiction, repetition, recursion, emotional_arc
    description: str
    evidence: list[dict] = field(default_factory=list)  # [{paragraph_id, quote}]
    is_hypothesis: bool = False


@dataclass
class CoverageReport:
    """Coverage validation report for a book."""

    total_chapters: int = 0
    total_paragraphs: int = 0
    processed_paragraph_count: int = 0
    missing_paragraph_ids: list[str] = field(default_factory=list)
    re_read_pass_completed: bool = False
    verification_status: str = "INCOMPLETE"
    ingest_mode: str = "QUALITY_MAX"
    ingest_date: str = ""
    notes: str = ""
