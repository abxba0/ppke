# PHASE 2: REFACTOR CORE CODEBASE
**PPKE v2.0 Refactoring - Implementation Phase**

---

## 📋 PHASE OVERVIEW

**Phase Number**: 2 of 4
**Estimated Effort**: 20-30 hours
**Prerequisites**: Phase 1 complete (`spec-plan-v2.md`, `LICENSE` created)
**Complexity**: High

**Objective**: Transform the philosophy-specific PPKE core into a domain-agnostic framework with template-driven behavior. This phase implements the architecture designed in Phase 1.

---

## 🎯 DELIVERABLES

By the end of this phase, you will have:

1. ✅ **Pydantic-based data models** (replacing dataclasses)
2. ✅ **Dynamic schema builder** (`ppke/parser/schema_builder.py`)
3. ✅ **Template system** (`ppke/templates/base.py`, `loader.py`, `validator.py`)
4. ✅ **Philosophy template** (100% backward compatible with v1.x)
5. ✅ **Legal template** (proof-of-concept for new domain)
6. ✅ **Refactored pipeline** (dynamic stage loading)
7. ✅ **Refactored prompts** (loaded from template files)
8. ✅ **Refactored output writer** (template-driven rendering)
9. ✅ **Updated CLI** with `--domain` flag

---

## 🔄 RALPH WIGGUM METHODOLOGY

For **every task** in this phase:

```
1. EXECUTE  → Implement the change
2. AUDIT    → Run tests, check for regressions
3. ITERATE  → Fix bugs until all tests pass
4. VALIDATE → Test with real philosophy & legal documents
```

**Critical**: After each file refactor, run `pytest tests/` to ensure no regressions.

---

## 🎯 TASK 1: REFACTOR DATA MODELS TO PYDANTIC

### 1.1 Convert `Paragraph`, `Chapter`, `Book` to Pydantic

**Current State** (`ppke/parser/models.py`):
```python
@dataclass
class Paragraph:
    chapter_number: int
    paragraph_number: int
    text: str
    depth: DepthLevel = DepthLevel.FULL
    sub_number: int | None = None

    @property
    def paragraph_id(self) -> str:
        if self.sub_number:
            return f"{{{self.chapter_number:02d}}}.p{self.paragraph_number}.{self.sub_number}"
        return f"{{{self.chapter_number:02d}}}.p{self.paragraph_number}"
```

**New Implementation**:

```python
# ppke/parser/models.py (REFACTORED)

from pydantic import BaseModel, Field, field_validator, computed_field
from enum import Enum
from typing import Optional

class DepthLevel(str, Enum):
    """Depth of analysis for a paragraph."""
    FULL = "FULL"     # Deep annotation
    LIGHT = "LIGHT"   # Topic + function only
    SKIP = "SKIP"     # Boilerplate, skip entirely


class Paragraph(BaseModel):
    """Domain-agnostic paragraph structure."""
    chapter_number: int = Field(..., ge=0, description="Chapter number (0-indexed)")
    paragraph_number: int = Field(..., ge=1, description="Paragraph number within chapter")
    text: str = Field(..., min_length=1, description="Paragraph text content")
    depth: DepthLevel = Field(default=DepthLevel.FULL, description="Analysis depth")
    sub_number: Optional[int] = Field(default=None, description="Sub-paragraph index for splits")

    @computed_field
    @property
    def paragraph_id(self) -> str:
        """Generate paragraph ID (e.g., {01}.p5 or {01}.p5.2)."""
        if self.sub_number:
            return f"{{{self.chapter_number:02d}}}.p{self.paragraph_number}.{self.sub_number}"
        return f"{{{self.chapter_number:02d}}}.p{self.paragraph_number}"

    model_config = {
        "frozen": False,  # Allow mutation during processing
        "validate_assignment": True,
        "str_strip_whitespace": True
    }


class Chapter(BaseModel):
    """Domain-agnostic chapter structure."""
    number: int = Field(..., ge=0)
    title: str = Field(..., min_length=1)
    paragraphs: list[Paragraph] = Field(default_factory=list)

    model_config = {"validate_assignment": True}


class Book(BaseModel):
    """Domain-agnostic book structure."""
    title: str = Field(..., min_length=1)
    author: str = Field(..., min_length=1)
    year: int = Field(..., ge=1000, le=9999)
    source_path: str = Field(..., description="Original markdown file path")
    chapters: list[Chapter] = Field(default_factory=list)

    @computed_field
    @property
    def folder_name(self) -> str:
        """Generate vault folder name: Book_{Title}_{Author}_{YYYY}"""
        safe_title = self.title.replace(" ", "_").replace("/", "-")
        safe_author = self.author.replace(" ", "_").replace("/", "-")
        return f"Book_{safe_title}_{safe_author}_{self.year}"

    def all_paragraphs(self) -> list[Paragraph]:
        """Flatten all paragraphs across all chapters."""
        return [p for ch in self.chapters for p in ch.paragraphs]

    model_config = {"validate_assignment": True}
```

**Migration Steps**:
1. **Backup** `ppke/parser/models.py` as `models_v1_backup.py`
2. **Replace** dataclasses with Pydantic models above
3. **Update imports** throughout codebase (search for `from ppke.parser.models import`)
4. **Fix instantiation**: Pydantic uses `model_validate()` instead of direct dict unpacking
5. **Run tests**: `pytest tests/test_parser.py -v`

**Validation**:
```python
# Test Pydantic models work
from ppke.parser.models import Paragraph, Chapter, Book

p = Paragraph(chapter_number=1, paragraph_number=5, text="Test")
assert p.paragraph_id == "{01}.p5"

# Test validation
try:
    Paragraph(chapter_number=-1, paragraph_number=1, text="Test")
    assert False, "Should have raised validation error"
except Exception:
    pass  # Expected
```

---

### 1.2 Create Dynamic `BaseExtraction` Model

**New File**: `ppke/parser/models.py` (add to existing refactored file)

```python
from typing import Any

class BaseExtraction(BaseModel):
    """
    Core extraction fields shared across all domains.
    Domain-specific templates extend this with additional fields.
    """
    paragraph_id: str = Field(..., description="Paragraph identifier")
    original_text: str = Field(..., description="Original paragraph text")
    topic_sentence: str = Field(..., description="One-sentence summary (<30 words)")
    defined_concepts: list[str] = Field(default_factory=list, description="Concepts introduced/defined")
    internal_references: list[str] = Field(default_factory=list, description="References to other sections")
    depth: DepthLevel = Field(default=DepthLevel.FULL, description="Analysis depth applied")

    model_config = {"extra": "allow"}  # Allow template-specific fields
```

**Why `extra="allow"`**: Templates can add custom fields (e.g., `function_in_argument`, `legal_standard`) without modifying the base class.

---

### 1.3 Create Dynamic Schema Builder

**New File**: `ppke/parser/schema_builder.py`

```python
"""Dynamic Pydantic model generation from template schemas."""

from pydantic import BaseModel, Field, create_model
from typing import Any, Type
from ppke.parser.models import BaseExtraction

def build_extraction_model(template_schema: dict[str, Any]) -> Type[BaseModel]:
    """
    Dynamically create a Pydantic model from template schema.

    Args:
        template_schema: Template's schema.yml content (parsed YAML)

    Returns:
        Pydantic model class with template-defined fields

    Example:
        Philosophy schema:
        {
            'name': 'PhilosophyExtraction',
            'base': 'BaseExtraction',
            'fields': [
                {'name': 'function_in_argument', 'type': 'str', 'description': '...'},
                {'name': 'explicit_claims', 'type': 'list[str]', 'default': []},
                ...
            ]
        }

        Legal schema:
        {
            'name': 'LegalExtraction',
            'base': 'BaseExtraction',
            'fields': [
                {'name': 'legal_standard', 'type': 'str', 'description': '...'},
                {'name': 'case_references', 'type': 'list[str]', 'default': []},
                ...
            ]
        }
    """
    # Extract model name
    model_name = template_schema.get('name', 'DynamicExtraction')

    # Determine base model
    base_class_name = template_schema.get('base', 'BaseExtraction')
    base_class = BaseExtraction  # TODO: Support other bases

    # Build field definitions
    fields = {}
    for field_def in template_schema.get('fields', []):
        field_name = field_def['name']

        # Parse type string (e.g., "str", "list[str]", "int", etc.)
        field_type = _parse_type(field_def['type'])

        # Get description and default
        field_desc = field_def.get('description', '')
        field_default = field_def.get('default', ...)  # ... means required

        # Create Pydantic Field
        if field_default is ...:
            fields[field_name] = (field_type, Field(description=field_desc))
        else:
            fields[field_name] = (field_type, Field(default=field_default, description=field_desc))

    # Create dynamic model
    dynamic_model = create_model(
        model_name,
        __base__=base_class,
        **fields
    )

    return dynamic_model


def _parse_type(type_str: str) -> Type:
    """
    Parse type string to Python type.

    Examples:
        'str' -> str
        'int' -> int
        'list[str]' -> list[str]
        'Optional[str]' -> Optional[str]
    """
    # Simple types
    if type_str == 'str':
        return str
    elif type_str == 'int':
        return int
    elif type_str == 'float':
        return float
    elif type_str == 'bool':
        return bool

    # List types
    elif type_str.startswith('list[') and type_str.endswith(']'):
        inner_type = type_str[5:-1]
        return list[_parse_type(inner_type)]

    # Optional types
    elif type_str.startswith('Optional[') and type_str.endswith(']'):
        inner_type = type_str[9:-1]
        return Optional[_parse_type(inner_type)]

    else:
        raise ValueError(f"Unsupported type string: {type_str}")
```

**Test** (`tests/test_schema_builder.py` - NEW):

```python
import pytest
from ppke.parser.schema_builder import build_extraction_model
from ppke.parser.models import BaseExtraction

def test_build_philosophy_extraction_model():
    schema = {
        'name': 'PhilosophyExtraction',
        'base': 'BaseExtraction',
        'fields': [
            {'name': 'function_in_argument', 'type': 'str', 'description': 'Role in argument'},
            {'name': 'explicit_claims', 'type': 'list[str]', 'default': []}
        ]
    }

    PhilosophyExtraction = build_extraction_model(schema)

    # Instantiate
    result = PhilosophyExtraction(
        paragraph_id="{01}.p5",
        original_text="Test text",
        topic_sentence="Summary",
        function_in_argument="introduces thesis",
        explicit_claims=["Claim 1"]
    )

    assert result.function_in_argument == "introduces thesis"
    assert result.explicit_claims == ["Claim 1"]
    assert isinstance(result, BaseExtraction)


def test_build_legal_extraction_model():
    schema = {
        'name': 'LegalExtraction',
        'base': 'BaseExtraction',
        'fields': [
            {'name': 'legal_standard', 'type': 'str', 'description': 'Legal standard'},
            {'name': 'case_references', 'type': 'list[str]', 'default': []}
        ]
    }

    LegalExtraction = build_extraction_model(schema)

    result = LegalExtraction(
        paragraph_id="{01}.p1",
        original_text="Legal text",
        topic_sentence="Summary",
        legal_standard="strict scrutiny",
        case_references=["Brown v. Board"]
    )

    assert result.legal_standard == "strict scrutiny"
    assert result.case_references == ["Brown v. Board"]
```

**Run**: `pytest tests/test_schema_builder.py -v`

---

## 🎯 TASK 2: CREATE TEMPLATE SYSTEM

### 2.1 Create Plugin Template Base Class

**New File**: `ppke/templates/base.py`

```python
"""Base classes for PPKE plugin templates."""

from pydantic import BaseModel, Field
from typing import Any

class PluginTemplate(BaseModel):
    """
    Base class for domain templates.

    Attributes:
        name: Template identifier (e.g., 'philosophy', 'legal')
        version: Semantic version
        tier: 'official' or 'custom'
        author: Creator name
        description: Brief description
        stages: List of pipeline stages
        prompts: Prompt templates (loaded from prompts.yml)
        schema: Pydantic schema definition (loaded from schema.yml)
        outputs: Output file templates (loaded from outputs.yml)
        skip_chapters: Chapter titles to skip during ingestion
    """
    name: str = Field(..., min_length=1, pattern=r'^[a-z_]+$')
    version: str = Field(..., pattern=r'^\d+\.\d+\.\d+$')
    tier: str = Field(..., pattern=r'^(official|custom)$')
    author: str = Field(...)
    description: str = Field(...)

    stages: list[dict[str, Any]] = Field(default_factory=list)
    prompts: dict[str, Any] = Field(default_factory=dict)
    schema: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    skip_chapters: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid", "validate_assignment": True}
```

---

### 2.2 Create Template Loader

**New File**: `ppke/templates/loader.py`

```python
"""Template discovery and loading system."""

from pathlib import Path
import yaml
from ppke.templates.base import PluginTemplate
from ppke.templates.validator import validate_template

# Template directories
OFFICIAL_TEMPLATES_DIR = Path(__file__).parent / "official"
CUSTOM_TEMPLATES_DIR = Path.home() / ".ppke" / "plugins"


def discover_templates() -> dict[str, Path]:
    """
    Discover all available templates (Tier 1 Official + Tier 2 Custom).

    Returns:
        Dictionary mapping template name -> template directory path
    """
    templates = {}

    # Tier 1: Official templates
    if OFFICIAL_TEMPLATES_DIR.exists():
        for template_dir in OFFICIAL_TEMPLATES_DIR.iterdir():
            if template_dir.is_dir() and (template_dir / "template.yml").exists():
                templates[template_dir.name] = template_dir

    # Tier 2: Custom user templates
    if CUSTOM_TEMPLATES_DIR.exists():
        for template_dir in CUSTOM_TEMPLATES_DIR.iterdir():
            if template_dir.is_dir() and (template_dir / "template.yml").exists():
                # Official templates take precedence
                if template_dir.name not in templates:
                    templates[template_dir.name] = template_dir

    return templates


def load_template(domain: str) -> PluginTemplate:
    """
    Load and validate a template by domain name.

    Args:
        domain: Template name (e.g., 'philosophy', 'legal')

    Returns:
        Validated PluginTemplate instance

    Raises:
        ValueError: If domain not found or validation fails
    """
    templates = discover_templates()

    if domain not in templates:
        available = ', '.join(sorted(templates.keys()))
        raise ValueError(f"Unknown domain '{domain}'. Available: {available}")

    template_path = templates[domain]

    # Load template configuration
    with open(template_path / "template.yml", encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # Load prompts
    prompts_file = template_path / "prompts.yml"
    if prompts_file.exists():
        with open(prompts_file, encoding='utf-8') as f:
            prompts = yaml.safe_load(f)
    else:
        prompts = {}

    # Load schema
    schema_file = template_path / "schema.yml"
    if schema_file.exists():
        with open(schema_file, encoding='utf-8') as f:
            schema = yaml.safe_load(f)
    else:
        schema = {}

    # Load outputs
    outputs_file = template_path / "outputs.yml"
    if outputs_file.exists():
        with open(outputs_file, encoding='utf-8') as f:
            outputs = yaml.safe_load(f)
    else:
        outputs = {}

    # Build PluginTemplate
    template = PluginTemplate(
        name=config['name'],
        version=config['version'],
        tier=config.get('tier', 'custom'),
        author=config.get('author', 'Unknown'),
        description=config.get('description', ''),
        stages=config.get('stages', []),
        prompts=prompts,
        schema=schema,
        outputs=outputs,
        skip_chapters=config.get('skip_chapters', [])
    )

    # Validate template
    validate_template(template)

    return template
```

---

### 2.3 Create Template Validator

**New File**: `ppke/templates/validator.py`

```python
"""Template validation and security checks."""

from ppke.templates.base import PluginTemplate

def validate_template(template: PluginTemplate) -> None:
    """
    Validate template structure and security.

    Raises:
        ValueError: If validation fails
    """
    # Required fields check
    if not template.stages:
        raise ValueError(f"Template '{template.name}' has no stages defined")

    if not template.schema:
        raise ValueError(f"Template '{template.name}' has no schema defined")

    # Validate stages
    for stage in template.stages:
        required_keys = ['id', 'name', 'module']
        for key in required_keys:
            if key not in stage:
                raise ValueError(f"Stage missing required key '{key}': {stage}")

    # Validate schema
    schema = template.schema.get('extraction_model', {})
    if 'name' not in schema:
        raise ValueError("Schema missing 'extraction_model.name'")
    if 'fields' not in schema:
        raise ValueError("Schema missing 'extraction_model.fields'")

    # Security: Check for suspicious patterns
    prompts_str = str(template.prompts)
    if 'import os' in prompts_str or 'import subprocess' in prompts_str:
        raise ValueError("Template contains suspicious code patterns (import os/subprocess)")

    # Warning: Large prompts
    for prompt_id, prompt_content in template.prompts.items():
        if isinstance(prompt_content, dict):
            system_prompt = prompt_content.get('system', '')
            if len(system_prompt) > 5000:
                print(f"⚠️  Warning: Prompt '{prompt_id}' is very long ({len(system_prompt)} chars)")
```

---

### 2.4 Create Philosophy Template (Tier 1 Official)

**New Directory**: `ppke/templates/official/philosophy/`

**File**: `ppke/templates/official/philosophy/template.yml`

```yaml
# Philosophy Template - 100% backward compatible with PPKE v1.x

name: philosophy
version: "2.0.0"
tier: official
author: PPKE Core Team
description: "Philosophical text analysis with argument mapping and concept tracking"

# Pipeline stages (executed in order)
stages:
  - id: extraction
    name: "Structural Extraction"
    module: ppke.pipeline.stages.extractor
    prompt: extraction

  - id: logical_map
    name: "Logical Architecture"
    module: ppke.pipeline.stages.analyzer
    prompt: logical_map
    output_file: "02_Logical_Map.md"

  - id: concepts
    name: "Concept Indexing"
    module: ppke.pipeline.stages.concepts
    prompt: concepts
    output_file: "03_Concept_Index.md"

  - id: patterns
    name: "Pattern Detection"
    module: ppke.pipeline.stages.patterns
    prompt: patterns
    output_file: "06_Patterns.md"

# Skip logic (chapters to skip during ingestion)
skip_chapters:
  - bibliography
  - index
  - appendix
  - appendices
  - references
  - works cited
  - glossary
  - endnotes
  - notes
  - further reading

# Output configuration
outputs:
  folder_format: "Book_{title}_{author}_{year}"
  files:
    - "meta.yml"
    - "01_Raw_Structure.md"
    - "02_Logical_Map.md"
    - "03_Concept_Index.md"
    - "05_Coverage_Report.md"
    - "06_Patterns.md"
    - "extractions.json"
```

**File**: `ppke/templates/official/philosophy/schema.yml`

```yaml
# Philosophy Extraction Schema

extraction_model:
  name: PhilosophyExtraction
  base: BaseExtraction
  description: "Pydantic model for philosophical text extraction"

  fields:
    - name: function_in_argument
      type: str
      description: "How this paragraph functions in the overall philosophical argument"
      examples:
        - "introduces central thesis"
        - "provides supporting premise"
        - "addresses counterargument"
        - "transitions between arguments"

    - name: explicit_claims
      type: list[str]
      description: "List of explicitly stated claims"
      default: []

    - name: implicit_assumptions
      type: list[str]
      description: "Unstated assumptions the argument relies on"
      default: []

    - name: logical_steps
      type: list[str]
      description: "Step-by-step breakdown of the logical progression"
      default: []

    - name: emotional_tone
      type: str
      description: "Emotional register (assertive, polemical, neutral, questioning, etc.)"
      default: "neutral"

    - name: tone_evidence
      type: str
      description: "Textual evidence supporting the identified tone"
      default: ""
```

**File**: `ppke/templates/official/philosophy/prompts.yml`

```yaml
# Philosophy Prompts (copy from ppke/llm/prompts.py)

extraction:
  system: |
    You are analyzing a **philosophical text**. For each paragraph, extract:

    1. **topic_sentence**: One-sentence summary (< 30 words)
    2. **function_in_argument**: How does this paragraph function in the overall argument?
       (e.g., introduces thesis, provides supporting premise, addresses counterargument, transitions, concludes)
    3. **explicit_claims**: List of explicitly stated claims
    4. **implicit_assumptions**: Unstated assumptions the argument relies on
    5. **logical_steps**: Step-by-step breakdown of logical progression
    6. **defined_concepts**: Concepts introduced or defined
    7. **emotional_tone**: Emotional register (assertive, polemical, neutral, questioning, etc.)
    8. **tone_evidence**: Textual evidence for the tone
    9. **internal_references**: References to other sections of the text

    Return JSON matching the schema exactly.

  user_template: |
    Analyze the following paragraphs from chapter {chapter_number}:

    {paragraphs_json}

logical_map:
  system: |
    You are analyzing the **logical architecture** of a philosophical text.

    Given all paragraph extractions, identify:
    1. **central_thesis**: The main thesis or argument of the entire work (1-3 sentences)
    2. **argument_threads**: Major lines of argument (3-7 threads)
       - For each thread:
         - **summary**: Brief description of the thread
         - **paragraph_ids**: List of paragraph IDs involved
         - **supports_thesis**: How it supports the central thesis

    Return JSON.

  user_template: |
    Logical architecture for "{book_title}" by {author}:

    {extractions_json}

concepts:
  system: |
    Track **philosophical concepts** throughout the text.

    For each concept mentioned in the extractions:
    1. **concept**: Normalized concept name (lowercase, singular)
    2. **occurrences**: List of paragraph IDs where it appears
    3. **semantic_shifts**: Note if the concept's meaning evolves

    Return JSON array of concepts.

  user_template: |
    Concept index for "{book_title}":

    {extractions_json}

patterns:
  system: |
    Detect **rhetorical and philosophical patterns** in the text.

    Identify:
    1. **Metaphors**: Recurring metaphors and their philosophical significance
    2. **Contradictions**: Apparent contradictions and potential resolutions
    3. **Emotional Arcs**: Shifts in emotional tone throughout the text

    Return JSON with pattern arrays.

  user_template: |
    Analyze patterns in "{book_title}":

    {extractions_json}
```

**File**: `ppke/templates/official/philosophy/outputs.yml` (content omitted for brevity - similar structure to prompts)

---

### 2.5 Create Legal Template (Tier 1 Official)

Create similar structure for `ppke/templates/official/legal/` with legal-specific fields:
- `legal_standard` (e.g., "strict scrutiny", "rational basis")
- `case_references` (e.g., ["Brown v. Board of Education"])
- `holding` (court's main decision)
- `statutory_citations` (laws referenced)

(Full legal template files omitted for brevity - follow philosophy template structure)

---

## 🎯 TASK 3: REFACTOR PIPELINE

### 3.1 Refactor `ppke/llm/prompts.py`

**Current**: Hardcoded Python strings
**New**: Dynamic loader from template

```python
# ppke/llm/prompts.py (REFACTORED)

"""Dynamic prompt loading from templates."""

from ppke.templates.base import PluginTemplate

def load_prompt(template: PluginTemplate, prompt_id: str, format_vars: dict = None) -> tuple[str, str]:
    """
    Load system and user prompts from template.

    Args:
        template: Loaded PluginTemplate
        prompt_id: Prompt identifier (e.g., 'extraction', 'logical_map')
        format_vars: Variables to format user_template (e.g., {'chapter_number': 1})

    Returns:
        (system_prompt, user_prompt) tuple

    Raises:
        ValueError: If prompt_id not found in template
    """
    if prompt_id not in template.prompts:
        available = ', '.join(template.prompts.keys())
        raise ValueError(f"Prompt '{prompt_id}' not found. Available: {available}")

    prompt_config = template.prompts[prompt_id]

    system_prompt = prompt_config.get('system', '')
    user_template = prompt_config.get('user_template', '')

    # Format user prompt if variables provided
    if format_vars:
        user_prompt = user_template.format(**format_vars)
    else:
        user_prompt = user_template

    return system_prompt, user_prompt
```

**Usage Example**:
```python
from ppke.templates.loader import load_template
from ppke.llm.prompts import load_prompt

template = load_template('philosophy')
system, user = load_prompt(
    template,
    'extraction',
    format_vars={'chapter_number': 1, 'paragraphs_json': '...'}
)
```

---

### 3.2 Refactor `ppke/pipeline/orchestrator.py`

**Key Changes**:
1. Add `domain` parameter (default: `'philosophy'`)
2. Load template dynamically
3. Build extraction model from schema
4. Execute stages from template config

**Simplified Refactored Function**:

```python
# ppke/pipeline/orchestrator.py (REFACTORED)

from ppke.templates.loader import load_template
from ppke.parser.schema_builder import build_extraction_model

def ingest_book(
    book: Book,
    config: Config,
    domain: str = 'philosophy',  # NEW parameter
    progress_callback=None,
    **kwargs
) -> dict:
    """
    Ingest book using domain-specific template.

    Args:
        book: Parsed Book model
        config: Configuration
        domain: Template name (default: 'philosophy')
        progress_callback: Optional callback(stage_name, progress_pct)

    Returns:
        Dictionary of stage results
    """
    # Load template
    template = load_template(domain)

    # Build dynamic extraction model
    ExtractionModel = build_extraction_model(template.schema['extraction_model'])

    # Execute stages
    results = {}
    for i, stage_config in enumerate(template.stages):
        stage_id = stage_config['id']
        stage_name = stage_config['name']

        if progress_callback:
            progress_callback(stage_name, (i / len(template.stages)) * 100)

        # Load stage module dynamically
        stage_module = import_module(stage_config['module'])
        stage_func = getattr(stage_module, f'run_{stage_id}')

        # Execute stage
        results[stage_id] = stage_func(
            book=book,
            config=config,
            template=template,
            extraction_model=ExtractionModel,
            previous_results=results
        )

    # Generate outputs
    from ppke.output.writer import render_outputs
    render_outputs(book, template, results, config.vault_path)

    return results
```

---

## 🎯 TASK 4: UPDATE CLI

### 4.1 Add `--domain` Flag to `ppke ingest`

**File**: `ppke/cli.py`

```python
@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--domain', default='philosophy', help='Domain template (default: philosophy)')
@click.option('--provider', type=click.Choice(['anthropic', 'openai', 'deepseek', 'gemini', 'openrouter']), help='Override LLM provider')
def ingest(file_path, domain, provider):
    """Ingest a document using domain-specific template."""
    # ... existing code ...

    ingest_book(book, config, domain=domain, ...)
```

### 4.2 Add `ppke list-domains` Command

```python
@cli.command()
def list_domains():
    """List all available domain templates."""
    from ppke.templates.loader import discover_templates
    templates = discover_templates()

    console.print("\n[bold]Available domains:[/bold]\n")
    for name, path in sorted(templates.items()):
        # Load template to get metadata
        template = load_template(name)
        tier_badge = "[green]official[/green]" if template.tier == 'official' else "[yellow]custom[/yellow]"
        console.print(f"  - {name} ({tier_badge}) - v{template.version}")
        console.print(f"    {template.description}\n")
```

---

## ✅ VALIDATION CRITERIA

After completing Phase 2:

### Backward Compatibility
- [ ] `ppke ingest philosophy.md` (no `--domain`) works identically to v1.x
- [ ] Output files match v1.x exactly (bit-for-bit identical extractions.json)
- [ ] All 23 existing CLI commands still work

### New Functionality
- [ ] `ppke ingest --domain philosophy philosophy.md` works
- [ ] `ppke ingest --domain legal contract.md` successfully ingests
- [ ] `ppke list-domains` shows philosophy + legal

### Tests
- [ ] `pytest tests/` - All existing tests pass
- [ ] `pytest tests/test_schema_builder.py` - Dynamic models work
- [ ] `pytest tests/test_templates.py` - Template loading works

### Code Quality
- [ ] No hardcoded prompts in `ppke/llm/prompts.py`
- [ ] No philosophy-specific logic in `ppke/pipeline/orchestrator.py`
- [ ] Pydantic models validate correctly

---

**END OF PHASE 2 METAPROMPT**

**Next**: Phase 3 - Plugin Ecosystem (`prompts/phase-3-plugin-ecosystem.md`)
