# PPKE v3.0 API Reference

**Version:** 3.0.0
**Last Updated:** 2026-03-01
**Audience:** Template Developers, Advanced Users, API Consumers

---

## Table of Contents

1. [Overview](#overview)
2. [REST API (Web Server)](#rest-api-web-server)
3. [Core Interfaces](#core-interfaces)
4. [Template API](#template-api)
5. [Configuration API](#configuration-api)
6. [Pipeline API](#pipeline-api)
7. [LLM Client API](#llm-client-api)
8. [Parser API](#parser-api)
9. [Data Models](#data-models)
10. [Exceptions](#exceptions)
11. [Type Definitions](#type-definitions)

---

## Overview

This document provides comprehensive API documentation for PPKE v3.0, covering the REST API (web server), Python interfaces for template developers, and advanced user APIs.

**Stability Guarantees:**
- 🟢 **Stable:** Public APIs with backward compatibility guarantees
- 🟡 **Experimental:** May change in minor versions
- 🔴 **Internal:** No guarantees, may change anytime

---

## REST API (Web Server) 🟢

**Base URL:** `http://localhost:8000` (default when running `ppke serve`)

All API endpoints return JSON unless otherwise noted. Authentication is via JWT token in the `ppke_token` cookie (set at login).

### Pages (HTML)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Main dashboard — list books, upload, search |
| GET | `/login` | Login page |
| GET | `/register` | Registration page |
| GET | `/notebook/{folder}` | Interactive book notebook view |
| GET | `/upload` | File upload page |
| GET | `/settings` | Settings panel |
| GET | `/graph` | Knowledge graph visualization |
| GET | `/workspaces` | Workspace management |
| GET | `/cost-dashboard` | LLM cost tracking dashboard |

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | Login (email + password) → sets JWT cookie |
| POST | `/auth/register` | Register new account |
| POST | `/auth/logout` | Logout (clears cookie) |
| GET | `/auth/oauth/{provider}` | Start OAuth flow (google, github) |
| GET | `/auth/oauth/{provider}/callback` | OAuth callback |
| GET | `/api/auth/me` | Get current authenticated user |

### Books

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/books` | List all books in the user's vault |
| GET | `/api/books/{folder}` | Get book details and metadata |
| GET | `/api/books/{folder}/extractions` | Get extraction data for a book |

### Query & Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/query` | Query a book (JSON response) |
| POST | `/api/query/stream` | Query with SSE streaming response |
| POST | `/api/cross-query` | Cross-book synthesis query |
| POST | `/api/search` | Full-text search across extractions |

### Upload & Import

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload` | Upload and ingest files (PDF, DOCX, EPUB, MD, images, etc.) |
| POST | `/api/import-url` | Import from URL or YouTube link |
| POST | `/api/import-rss` | Import podcast episodes from RSS feed |

### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/jobs/{job_id}` | Check background job status |
| GET | `/api/stats` | Vault statistics (book count, extraction totals) |

### Content Generation

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/history/{folder}` | Get chat history for a book |
| GET/POST | `/api/summary/{folder}` | Get or generate executive summary |
| GET/POST | `/api/study-guide/{folder}` | Get or generate study guide |
| GET | `/api/glossary/{folder}` | Generate glossary of key terms |
| GET | `/api/flashcards/{folder}` | Generate study flashcards |

### Audio & Multimedia

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/audio-overview` | Generate podcast-style audio overview |
| POST | `/api/audio-overview/cross-book` | Generate cross-book comparative audio |
| GET | `/api/audio/{folder}/transcript` | Get audio script/transcript |
| GET | `/api/audio/presets` | List available voice presets |
| POST | `/api/audio/upload-recording` | Upload and transcribe audio recording |
| GET | `/api/audio/{folder}` | Stream audio file |

### Knowledge Graph

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/graph` | Get graph data (nodes + edges) |
| GET | `/api/graph/search` | Search graph nodes |
| GET | `/api/graph/clusters` | Get concept clusters |
| GET | `/api/graph/analytics` | Full graph analytics |
| GET | `/api/graph/path` | Find shortest path between concepts |
| GET | `/api/graph/gaps` | Identify knowledge gaps |
| GET | `/api/graph/contradictions` | Detect contradictions across books |
| GET | `/api/graph/export` | Export graph as JSON |
| GET | `/api/graph/obsidian-export` | Export graph as Obsidian vault (ZIP) |
| GET | `/api/graph/markdown-export` | Export graph as Markdown |

### Export

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/export/{folder}/pdf` | Export analysis as PDF report |
| GET | `/api/export/{folder}/docx` | Export analysis as DOCX |
| GET | `/api/export/{folder}/pptx` | Export analysis as PPTX slides |
| GET | `/api/export/{folder}/zip` | Export all book files as ZIP |

### Academic

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/bibliography` | Generate bibliography across books |
| GET/POST | `/api/literature-review` | Generate or retrieve literature review |
| GET | `/api/argument-map/{folder}` | Generate argument map for a book |

### Settings & Config

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | Get current configuration |
| POST | `/api/settings` | Update LLM provider/model settings |

### Workspaces & Collaboration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/workspaces` | List user's workspaces |
| POST | `/api/workspaces` | Create a new workspace |
| GET | `/api/workspaces/{ws_id}/members` | List workspace members |
| POST | `/api/workspaces/{ws_id}/invite` | Invite user to workspace (admin/owner/editor) |
| POST | `/api/workspaces/{ws_id}/members/{user_id}/role` | Update member role (admin/owner only) |
| DELETE | `/api/workspaces/{ws_id}/members/{user_id}` | Remove member (admin/owner only) |
| POST | `/api/workspaces/{ws_id}/share` | Share a book with workspace (`permissions`: `view`\|`edit`) |
| GET | `/api/workspaces/{ws_id}/shared-books` | List shared books in workspace |
| PATCH | `/api/workspaces/{ws_id}/shared-books/{share_id}` | Update shared book permissions (admin/owner only) |
| DELETE | `/api/workspaces/{ws_id}/shared-books/{share_id}` | Unshare a book from workspace |

#### Workspace Permission Levels

| Role | Invite Members | Share Books | Manage Shared Books | Change Roles | Remove Members |
|------|---------------|-------------|--------------------|--------------| ---------------|
| **Owner** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Admin** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Editor** | ✓ | ✓ | ✗ | ✗ | ✗ |
| **Viewer** | ✗ | ✗ | ✗ | ✗ | ✗ |

#### Shared Book Permission Levels

| Permission | Description |
|-----------|-------------|
| `view` | Members can read the book content only (read-only) |
| `edit` | Members can read and annotate the book |

### Annotations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/annotations` | Create annotation on an extraction |
| GET | `/api/annotations/{folder}` | Get annotations for a book |
| DELETE | `/api/annotations/{ann_id}` | Delete an annotation |

### Infrastructure

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check (DB, Redis, Vector Store, LLM) |
| GET | `/metrics` | Prometheus metrics |
| GET | `/api/cost-dashboard` | LLM cost/usage data |
| GET | `/api/activity` | User activity log |
| POST | `/api/keys` | Create API key |
| GET | `/api/keys` | List API keys |
| DELETE | `/api/keys/{key_id}` | Revoke API key |
| GET | `/api/usage` | Usage statistics |

---

## Core Interfaces

### DomainTemplate (Abstract Base Class) 🟢

**Module:** `ppke.templates.base`

The core interface that all domain templates must implement.

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from pathlib import Path
from typing import Any

class DomainTemplate(ABC):
    """Base class for all domain-specific templates."""
```

#### Properties

##### `name` 🟢
```python
@property
@abstractmethod
def name(self) -> str:
    """
    Unique template identifier (lowercase, hyphenated).

    Returns:
        str: Template name (e.g., "philosophy", "legal-contracts")

    Example:
        >>> template.name
        'philosophy'
    """
```

##### `version` 🟢
```python
@property
@abstractmethod
def version(self) -> str:
    """
    Template version (semantic versioning).

    Returns:
        str: Version string (e.g., "1.2.3")

    Example:
        >>> template.version
        '2.0.0'
    """
```

##### `description` 🟢
```python
@property
@abstractmethod
def description(self) -> str:
    """
    Human-readable template description.

    Returns:
        str: Short description for `ppke template list`

    Example:
        >>> template.description
        'Deep analysis of philosophical texts'
    """
```

#### Methods

##### `get_prompts()` 🟢
```python
@abstractmethod
def get_prompts(self) -> dict[str, str]:
    """
    Return prompt templates for all 7 skills.

    Returns:
        dict[str, str]: Mapping of skill names to prompt templates.
            Required keys:
                - structural_extraction
                - logical_map
                - concept_index
                - author_model
                - pattern_detection
                - cross_book_synthesis
                - qa_validation

    Prompts may contain placeholders:
        - {paragraphs}: Batch of paragraphs to analyze
        - {title}: Book title
        - {author}: Book author
        - {summaries}: Previously extracted summaries
        - {extractions}: Full extraction results

    Example:
        >>> prompts = template.get_prompts()
        >>> print(prompts['structural_extraction'])
        'Analyze the following paragraphs...{paragraphs}'
    """
```

##### `get_extraction_schema()` 🟢
```python
@abstractmethod
def get_extraction_schema(self) -> type[BaseModel]:
    """
    Return Pydantic model for Skill 1 extraction results.

    The schema must include at minimum:
        - paragraph_id: str
        - summary: str
        - key_terms: list[str]

    Additional domain-specific fields are encouraged.

    Returns:
        type[BaseModel]: Pydantic model class

    Example:
        >>> schema = template.get_extraction_schema()
        >>> result = schema(
        ...     paragraph_id="{01}.p1.0",
        ...     summary="Test summary",
        ...     key_terms=["term1"]
        ... )
        >>> result.paragraph_id
        '{01}.p1.0'
    """
```

##### `get_output_config()` 🟢
```python
@abstractmethod
def get_output_config(self) -> dict[str, Any]:
    """
    Define output file structure.

    Returns:
        dict: Configuration with structure:
            {
                "files": [
                    {
                        "filename": str,  # Required
                        "sections": list[str],  # Optional
                        "format": str  # Optional, default: "markdown"
                    },
                    ...
                ],
                # Global options (optional)
                "include_metadata": bool,  # Default: True
                "include_citations": bool,  # Default: True
            }

    Example:
        >>> config = template.get_output_config()
        >>> config['files'][0]
        {'filename': '01_Structure.md', 'sections': ['Overview']}
    """
```

##### `post_process_extraction()` 🟡 (Optional)
```python
def post_process_extraction(self, result: BaseModel) -> BaseModel:
    """
    Optional: Custom post-processing of extraction results.

    Use cases:
        - Normalize terms or citations
        - Validate field consistency
        - Enrich data with external sources

    Args:
        result: Extraction result from LLM

    Returns:
        BaseModel: Processed extraction result

    Default: No-op (returns input unchanged)

    Example:
        >>> def post_process_extraction(self, result):
        ...     # Normalize case citations
        ...     result.citations = [c.upper() for c in result.citations]
        ...     return result
    """
    return result
```

##### `validate_output()` 🟡 (Optional)
```python
def validate_output(self, output_dir: Path) -> list[str]:
    """
    Optional: Custom output validation.

    Args:
        output_dir: Directory containing output files

    Returns:
        list[str]: Validation errors (empty list = success)

    Example:
        >>> errors = template.validate_output(Path("./output"))
        >>> errors
        ['Missing required file: 01_Structure.md']
    """
    return []
```

---

## Template API

### TemplateRegistry 🟢

**Module:** `ppke.templates.registry`

Discovers and manages domain templates.

```python
class TemplateRegistry:
    """Discovers and loads domain templates."""

    def __init__(self):
        """Initialize registry and discover templates."""
        self._templates: dict[str, DomainTemplate] = {}
        self._cache: dict[str, DomainTemplate] = {}
        self.discover()
```

#### Methods

##### `discover()` 🟢
```python
def discover(self) -> None:
    """
    Discover templates from official and custom directories.

    Searches:
        - Official: ppke/templates/official/
        - Custom:   ~/.ppke/templates/custom/

    Raises:
        TemplateLoadError: If template fails to load
    """
```

##### `get_template()` 🟢
```python
def get_template(self, name: str) -> DomainTemplate:
    """
    Load a template by name (with caching).

    Args:
        name: Template identifier

    Returns:
        DomainTemplate: Loaded template instance

    Raises:
        TemplateNotFoundError: If template doesn't exist

    Example:
        >>> registry = TemplateRegistry()
        >>> template = registry.get_template("philosophy")
        >>> template.name
        'philosophy'
    """
```

##### `list_templates()` 🟢
```python
def list_templates(self) -> list[dict]:
    """
    Return list of all available templates with metadata.

    Returns:
        list[dict]: Template info dictionaries with keys:
            - name: str
            - version: str
            - description: str
            - tier: "official" | "custom"

    Example:
        >>> registry.list_templates()
        [
            {
                'name': 'philosophy',
                'version': '2.0.0',
                'description': 'Philosophical text analysis',
                'tier': 'official'
            },
            ...
        ]
    """
```

---

## Configuration API

### PPKEConfig 🟢

**Module:** `ppke.config`

Master configuration for PPKE.

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class PPKEConfig:
    """Master configuration for PPKE v2.0."""

    llm: LLMConfig
    vault_path: Path
    template_name: str = "philosophy"
    enable_vector_db: bool = False
    enable_graph: bool = False
    enable_cache: bool = True
```

#### Class Methods

##### `load()` 🟢
```python
@classmethod
def load(cls, config_path: Path = Path.home() / ".ppke" / "config.json") -> "PPKEConfig":
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to config file (default: ~/.ppke/config.json)

    Returns:
        PPKEConfig: Loaded configuration

    Raises:
        ConfigNotFoundError: If config file doesn't exist
        ConfigValidationError: If config is invalid

    Example:
        >>> config = PPKEConfig.load()
        >>> config.template_name
        'philosophy'
    """
```

#### Instance Methods

##### `get_template()` 🟢
```python
def get_template(self) -> DomainTemplate:
    """
    Lazy load the active template from registry.

    Returns:
        DomainTemplate: Active template instance

    Example:
        >>> config = PPKEConfig.load()
        >>> template = config.get_template()
        >>> template.name
        'philosophy'
    """
```

##### `save()` 🟢
```python
def save(self, config_path: Path | None = None) -> None:
    """
    Save configuration to JSON file.

    Args:
        config_path: Path to save config (default: ~/.ppke/config.json)

    Example:
        >>> config.template_name = "legal"
        >>> config.save()
    """
```

### LLMConfig 🟢

**Module:** `ppke.config`

Configuration for LLM providers.

```python
@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: str = "anthropic"  # anthropic|openai|deepseek|gemini|openrouter
    model: str = "claude-sonnet-4-20250514"
    small_model: str | None = None  # Two-tier: cheap model for extraction
    max_tokens: int = 4096
    temperature: float = 0.2
    paragraphs_per_batch: int = 5
    max_paragraph_tokens: int = 2000
    max_workers: int = 4
```

---

## Pipeline API

### PipelineOrchestrator 🟢

**Module:** `ppke.pipeline.orchestrator`

Manages the 7-skill processing pipeline.

```python
class PipelineOrchestrator:
    """Manages the 7-skill processing pipeline."""

    def __init__(self, config: PPKEConfig):
        """
        Initialize orchestrator with configuration.

        Args:
            config: PPKE configuration
        """
        self.config = config
        self.template = config.get_template()
        self.llm_client = LLMClient(config.llm)
        self.progress_tracker = ProgressTracker(config.vault_path)
```

#### Methods

##### `ingest()` 🟢
```python
async def ingest(self, filepath: Path) -> None:
    """
    Run full ingestion pipeline.

    Pipeline stages:
        1. Parse document
        2. Skill 1: Structural extraction (parallel)
        3. Skills 2-7: Advanced analysis (concurrent)
        4. Coverage validation
        5. Output generation

    Args:
        filepath: Path to document to ingest

    Raises:
        DocumentParseError: If document parsing fails
        LLMError: If LLM calls fail
        OutputError: If output generation fails

    Example:
        >>> orchestrator = PipelineOrchestrator(config)
        >>> await orchestrator.ingest(Path("~/Documents/book.md"))
    """
```

---

## LLM Client API

### LLMClient 🟢

**Module:** `ppke.llm.client`

Provider-agnostic LLM client.

```python
class LLMClient:
    """Provider-agnostic LLM client with unified interface."""

    def __init__(self, config: LLMConfig):
        """
        Initialize LLM client.

        Args:
            config: LLM configuration
        """
```

#### Methods

##### `generate()` 🟢
```python
async def generate(
    self,
    prompt: str,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: type[BaseModel] | None = None,
) -> str | BaseModel:
    """
    Generate completion from LLM.

    Args:
        prompt: User prompt
        system: System prompt (optional)
        temperature: Sampling temperature (optional, uses config default)
        max_tokens: Max tokens (optional, uses config default)
        response_format: Pydantic model for structured output (optional)

    Returns:
        str: Text response (if response_format is None)
        BaseModel: Structured response (if response_format provided)

    Raises:
        LLMError: If API call fails
        ValidationError: If structured output doesn't match schema

    Example:
        >>> client = LLMClient(config)
        >>> response = await client.generate("Explain Dasein")
        >>> print(response)
        'Dasein is Heidegger's term for...'

        >>> # Structured output
        >>> response = await client.generate(
        ...     "Extract concepts",
        ...     response_format=ExtractionResult
        ... )
        >>> response.key_terms
        ['Dasein', 'Being-in-the-world']
    """
```

---

## Parser API

### MarkdownParser 🟢

**Module:** `ppke.parser.markdown`

Domain-agnostic Markdown document parser.

```python
class MarkdownParser:
    """Domain-agnostic Markdown document parser."""

    def parse(self, filepath: Path) -> Book:
        """
        Parse Markdown into structured Book/Chapter/Paragraph hierarchy.

        Args:
            filepath: Path to Markdown file

        Returns:
            Book: Structured representation

        Raises:
            FileNotFoundError: If file doesn't exist
            ParseError: If parsing fails

        Example:
            >>> parser = MarkdownParser()
            >>> book = parser.parse(Path("book.md"))
            >>> book.title
            'Being and Time'
            >>> len(book.chapters)
            10
        """
```

---

## Data Models

### Book 🟢

**Module:** `ppke.parser.models`

```python
@dataclass
class Book:
    """Structured representation of a book."""

    title: str
    author: str
    filepath: Path
    chapters: list[Chapter]
    metadata: dict

    def all_paragraphs(self) -> list[Paragraph]:
        """Return all paragraphs across all chapters."""
```

### Chapter 🟢

```python
@dataclass
class Chapter:
    """Chapter in a book."""

    number: int
    title: str
    paragraphs: list[Paragraph]
```

### Paragraph 🟢

```python
@dataclass
class Paragraph:
    """Single paragraph with metadata."""

    id: str  # Format: "{CH}.p{P}.{S}"
    chapter_number: int
    paragraph_number: int
    sub_paragraph: int
    text: str
    token_count: int
```

---

## Exceptions

### PPKE Exception Hierarchy 🟢

**Module:** `ppke.exceptions`

```python
class PPKEError(Exception):
    """Base exception for all PPKE errors."""

class TemplateError(PPKEError):
    """Base for template-related errors."""

class TemplateNotFoundError(TemplateError):
    """Template not found in registry."""

class TemplateLoadError(TemplateError):
    """Template failed to load."""

class TemplateValidationError(TemplateError):
    """Template validation failed."""

class ConfigError(PPKEError):
    """Base for configuration errors."""

class ConfigNotFoundError(ConfigError):
    """Config file not found."""

class ConfigValidationError(ConfigError):
    """Config validation failed."""

class LLMError(PPKEError):
    """Base for LLM-related errors."""

class LLMAPIError(LLMError):
    """LLM API call failed."""

class LLMRateLimitError(LLMError):
    """LLM rate limit exceeded."""

class ParseError(PPKEError):
    """Document parsing failed."""

class OutputError(PPKEError):
    """Output generation failed."""
```

---

## Type Definitions

### Common Type Aliases 🟢

**Module:** `ppke.types`

```python
from typing import TypeAlias
from pathlib import Path

# File paths
FilePath: TypeAlias = str | Path

# LLM providers
LLMProvider: TypeAlias = Literal["anthropic", "openai", "deepseek", "gemini", "openrouter"]

# Template tiers
TemplateTier: TypeAlias = Literal["official", "custom"]

# Skill names
SkillName: TypeAlias = Literal[
    "structural_extraction",
    "logical_map",
    "concept_index",
    "author_model",
    "pattern_detection",
    "cross_book_synthesis",
    "qa_validation",
]
```

---

## Example Usage

### Creating a Custom Template

```python
from ppke.templates.base import DomainTemplate
from pydantic import BaseModel, Field

class MyExtractionResult(BaseModel):
    paragraph_id: str
    summary: str
    key_terms: list[str]
    custom_field: str = Field(default="", description="Domain-specific field")

class MyTemplate(DomainTemplate):
    @property
    def name(self) -> str:
        return "my-domain"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "My domain template"

    def get_prompts(self) -> dict[str, str]:
        return {
            "structural_extraction": "Extract from: {paragraphs}",
            # ... 6 more skills
        }

    def get_extraction_schema(self) -> type[BaseModel]:
        return MyExtractionResult

    def get_output_config(self) -> dict[str, Any]:
        return {
            "files": [
                {"filename": "01_Output.md", "sections": ["Overview"]}
            ]
        }
```

### Using the Pipeline Programmatically

```python
import asyncio
from pathlib import Path
from ppke.config import PPKEConfig
from ppke.pipeline.orchestrator import PipelineOrchestrator

async def main():
    # Load configuration
    config = PPKEConfig.load()

    # Create orchestrator
    orchestrator = PipelineOrchestrator(config)

    # Ingest document
    await orchestrator.ingest(Path("~/Documents/my-book.md"))

    print("Ingestion complete!")

# Run
asyncio.run(main())
```

---

## Versioning and Stability

### API Stability Levels

- 🟢 **Stable:** Guaranteed backward compatibility within major version
- 🟡 **Experimental:** May change in minor versions (deprecation warnings)
- 🔴 **Internal:** No guarantees, subject to change

### Deprecation Policy

1. Feature marked as deprecated in version N
2. Deprecation warnings in N, N+1
3. Removed in N+2

Example:
- v2.0: Feature X stable
- v2.3: Feature X deprecated (warnings)
- v2.4: Feature X deprecated (warnings)
- v2.5: Feature X removed

---

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for API changes across versions.

---

**Document Version:** 3.0
**Last Updated:** 2026-03-01
**Maintained By:** PPKE Core Team
