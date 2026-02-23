# PHASE 1: AUDIT & SPECIFICATION
**PPKE v2.0 Refactoring - Foundation Phase**

---

## 📋 PHASE OVERVIEW

**Phase Number**: 1 of 4
**Estimated Effort**: 8-12 hours
**Prerequisites**: None (starting phase)
**Complexity**: Medium

**Objective**: Conduct a comprehensive audit of philosophy-specific coupling in the PPKE codebase and create a detailed specification document (`spec-plan-v2.md`) for the transition to a general-purpose knowledge framework with plugin architecture.

---

## 🎯 DELIVERABLES

By the end of this phase, you will have created:

1. ✅ **`spec-plan-v2.md`** - Comprehensive refactoring specification
2. ✅ **`LICENSE`** - Apache 2.0 license file
3. ✅ **`REFACTORING_CHECKLIST.md`** - Migration tracking checklist
4. ✅ **Audit Report** - Document of all philosophy couplings found

---

## 🔄 RALPH WIGGUM METHODOLOGY

For **every task** in this phase, follow this cycle:

```
1. EXECUTE  → Implement the change
2. AUDIT    → Check for logical/functional/integration errors
3. ITERATE  → Fix issues until spec compliance
4. VALIDATE → Test in real-world scenarios
```

**Never skip the audit step.** Even documentation requires validation.

---

## 📦 CODEBASE CONTEXT

### Current PPKE Architecture (v1.x)

```
ppke/
├── cli.py                      # 1,980 lines - Click-based CLI (23 commands)
├── config.py                   # 204 lines - Configuration management
├── tui.py                      # Terminal UI dashboard
│
├── parser/
│   ├── models.py               # 156 lines - Philosophy-coupled dataclasses
│   └── markdown.py             # Markdown parser
│
├── llm/
│   ├── client.py               # Multi-provider LLM client (5 providers)
│   └── prompts.py              # 🔴 HARDCODED PHILOSOPHY PROMPTS
│
├── pipeline/
│   ├── orchestrator.py         # 34 KB - Main ingestion controller
│   ├── async_orchestrator.py  # Asyncio-based pipeline
│   ├── extractor.py            # Skill 1: Structural extraction
│   ├── logical_map.py          # 🔴 Skill 3: PHILOSOPHY-SPECIFIC
│   ├── concepts.py             # Skill 4: Concept indexing
│   ├── patterns.py             # 🔴 Skill 5: PHILOSOPHY-SPECIFIC
│   ├── synthesizer.py          # Cross-book synthesis
│   └── validator.py            # Coverage validation
│
├── output/
│   └── writer.py               # 🔴 PHILOSOPHY-SPECIFIC OUTPUT STRUCTURE
│
├── vectordb/
│   └── store.py                # ChromaDB semantic search
│
├── graph/
│   └── knowledge_graph.py      # NetworkX concept graph
│
└── progress/
    └── tracker.py              # Ingestion progress tracking
```

**🔴 Red indicators** mark files with heavy philosophy coupling.

---

## 📍 CURRENT STATE ANALYSIS

### Supported LLM Providers (5)
- Anthropic (Claude Sonnet 4, Haiku)
- OpenAI (GPT-4o, GPT-4o-mini)
- DeepSeek (deepseek-chat)
- Gemini (1.5 Pro, 1.5 Flash)
- OpenRouter (proxy)

### Current CLI Commands (23)
```bash
# Lifecycle
ppke init, config, status, doctor

# Ingestion
ppke ingest, async-ingest, parse, re-read

# Querying
ppke query, cross-query

# Search
ppke search, vector-search, graph-query, list, stats, graph-stats

# Knowledge Management
ppke graph-build, notebook

# User Experience
ppke cheat, menu, tui
```

### Data Models (Philosophy-Coupled)
```python
# ppke/parser/models.py

@dataclass
class ExtractionResult:
    paragraph_id: str
    original_text: str

    # 🔴 Philosophy-specific fields
    topic_sentence: str
    function_in_argument: str        # ← Assumes philosophical argument
    explicit_claims: list[str]       # ← Philosophy concept
    implicit_assumptions: list[str]  # ← Philosophy concept
    logical_steps: list[str]         # ← Philosophy concept
    defined_concepts: list[str]
    emotional_tone: str
    tone_evidence: str
    internal_references: list[str]
    depth: DepthLevel
```

---

## 🎯 TASK 1: AUDIT PHILOSOPHY COUPLING

### 1.1 Audit `ppke/llm/prompts.py`

**Current State**: All prompts are hardcoded Python strings with explicit philosophy references.

**Action**: Open `C:\Code\CliCode\ppke\ppke\llm\prompts.py` and document:

1. **List all prompt templates** (there are 7+):
   - `STRUCTURAL_EXTRACTION_SYSTEM`
   - `LOGICAL_MAP_SYSTEM`
   - `CONCEPT_INDEX_SYSTEM`
   - `PATTERN_DETECTION_SYSTEM`
   - `AUTHOR_MODEL_SYSTEM`
   - `SINGLE_BOOK_QUERY_SYSTEM`
   - `CROSS_BOOK_QUERY_SYSTEM`

2. **Identify philosophy-specific language** in each:
   - References to "thesis," "argument," "claims," "premises"
   - "Philosophical text" assumptions
   - "Counterargument," "logical structure"
   - Example emotional tones: "assertive," "polemical," "questioning"

3. **Document extraction format**:
   - Current JSON schema expected from LLM
   - Which fields are philosophy-specific vs. generic

**Example from `STRUCTURAL_EXTRACTION_SYSTEM`**:
```python
STRUCTURAL_EXTRACTION_SYSTEM = """
You are analyzing a **philosophical text**. For each paragraph, extract:
...
- function_in_argument: How does this paragraph function in the overall **argument**?
  (e.g., introduces **thesis**, provides supporting **premise**, addresses **counterargument**, ...)
...
"""
```

**Audit Output**: Create section in your audit report:

```markdown
### Prompts Audit (ppke/llm/prompts.py)

**Total Prompts**: 7

**Philosophy Coupling Severity**: 🔴 CRITICAL

**Findings**:
1. `STRUCTURAL_EXTRACTION_SYSTEM` (Line X):
   - "philosophical text" (3 occurrences)
   - "argument," "thesis," "premise," "counterargument"
   - Field: `function_in_argument` assumes philosophical structure

2. `LOGICAL_MAP_SYSTEM` (Line Y):
   - "central thesis," "argument threads"
   - Expects philosophical argumentation structure

3. [... continue for all prompts ...]

**Generalization Strategy**:
- Extract prompts to template YAML files
- Replace "philosophical text" with "text" or domain-agnostic language
- Make field names configurable per domain
- Create philosophy template that preserves exact v1.x behavior
```

---

### 1.2 Audit `ppke/parser/models.py`

**Current State**: Dataclasses with philosophy-specific field names and structures.

**Action**: Open `C:\Code\CliCode\ppke\ppke\parser\models.py` and analyze:

1. **`ExtractionResult` dataclass**:
   - Which fields are philosophy-specific?
   - Which fields are domain-agnostic?
   - Can fields be made optional for other domains?

2. **Other models**:
   - `Paragraph`, `Chapter`, `Book` - Are these generic or coupled?
   - `ConceptEntry`, `LogicalNode`, `PatternEntry` - Philosophy assumptions?

**Audit Output**:

```markdown
### Data Models Audit (ppke/parser/models.py)

**Total Dataclasses**: 7

**Philosophy Coupling Severity**: 🟡 MODERATE

**Findings**:

1. `ExtractionResult`:
   - **Domain-agnostic fields**:
     - `paragraph_id`, `original_text`, `topic_sentence`
     - `defined_concepts`, `internal_references`, `depth`

   - **Philosophy-specific fields**:
     - `function_in_argument` (assumes argumentation)
     - `explicit_claims`, `implicit_assumptions`, `logical_steps`

   - **Potentially generic fields**:
     - `emotional_tone`, `tone_evidence` (could apply to legal, medical)

2. `Paragraph`, `Chapter`, `Book`:
   - **Verdict**: ✅ Domain-agnostic (structural, not semantic)

3. `ConceptEntry`:
   - **Verdict**: ✅ Mostly generic (concept tracking applies to all domains)
   - Minor: "semantic_shifts" assumes philosophical evolution

4. `LogicalNode`:
   - **Verdict**: 🔴 Philosophy-specific (argument tree structure)

**Refactoring Strategy**:
- Convert all dataclasses to Pydantic models
- Make `ExtractionResult` fields dynamic based on template schema
- Allow templates to define custom fields
- Philosophy template uses all current fields
- Legal template might use: `legal_standard`, `case_references`, `holding`, etc.
```

---

### 1.3 Audit `ppke/pipeline/orchestrator.py` and Stage Modules

**Current State**: Pipeline assumes 7-stage philosophy analysis.

**Action**: Analyze pipeline architecture:

1. **`ppke/pipeline/orchestrator.py`**:
   - Hard-coded 7-stage pipeline
   - Skip logic for philosophy books (Bibliography, Index, Appendix)
   - Output file generation assumes philosophy structure

2. **`ppke/pipeline/logical_map.py`**:
   - `build_logical_map()` - Assumes philosophical argument structure
   - Prompt: "Identify the central thesis and major argument threads"

3. **`ppke/pipeline/concepts.py`**:
   - `build_concept_index()` - Mostly generic
   - Minor coupling: "philosophical concepts"

4. **`ppke/pipeline/patterns.py`**:
   - `detect_patterns()` - Philosophy-specific pattern types
   - Metaphor detection, contradiction, emotional arcs (could be generic)

**Audit Output**:

```markdown
### Pipeline Audit

**Philosophy Coupling Severity**: 🔴 CRITICAL (orchestrator), 🟡 MODERATE (stages)

**Findings**:

1. **orchestrator.py** (Line 1-800+):
   - Hard-coded 7-stage pipeline (Skills 1-7)
   - Skip logic: `_SKIP_CHAPTER_TITLES = frozenset({'bibliography', 'index', 'appendix', ...})`
     - **Verdict**: Mostly generic (applies to academic books)
   - Output files: `02_Logical_Map.md`, `06_Patterns.md`
     - **Verdict**: 🔴 Philosophy-specific naming

2. **logical_map.py** (73 lines):
   - Function: `build_logical_map(book, extractions, config)`
   - Prompt system: `LOGICAL_MAP_SYSTEM` (from prompts.py)
   - **Verdict**: 🔴 Entirely philosophy-specific
   - **Refactoring**: Make "logical_map" an optional stage defined by template

3. **concepts.py** (116 lines):
   - Function: `build_concept_index(book, extractions, config)`
   - **Verdict**: ✅ Mostly generic (concept tracking works for all domains)
   - Minor: References to "philosophical concepts" in prompt

4. **patterns.py** (95 lines):
   - Function: `detect_patterns(book, extractions, config)`
   - Detected patterns: metaphor, contradiction, emotional_arcs
   - **Verdict**: 🟡 Could be generic with different pattern types per domain
   - Philosophy: metaphor, contradiction, emotional_arcs
   - Legal: precedent_references, statutory_interpretation, case_citations

**Refactoring Strategy**:
- Replace hard-coded pipeline with dynamic stage loading from templates
- Each template defines: `stages: [extraction, logical_map, concepts, patterns]`
- Each stage references a Python module or template-defined prompt
- Philosophy template preserves exact 7-stage pipeline
- Legal template might use: `[extraction, legal_analysis, precedent_map, compliance_check]`
```

---

### 1.4 Audit `ppke/output/writer.py`

**Current State**: Generates philosophy-specific output files.

**Action**: Analyze output file generation:

1. **Generated files**:
   - `meta.yml` - Generic metadata
   - `01_Raw_Structure.md` - Generic extraction dump
   - `02_Logical_Map.md` - 🔴 Philosophy-specific
   - `03_Concept_Index.md` - ✅ Generic
   - `05_Coverage_Report.md` - ✅ Generic
   - `06_Patterns.md` - 🟡 Semi-generic
   - `extractions.json` - ✅ Generic (searchable)

2. **File naming and structure**:
   - Markdown headers assume philosophy
   - Example: "# Central Thesis and Argument Threads"

**Audit Output**:

```markdown
### Output Generation Audit (ppke/output/writer.py)

**Philosophy Coupling Severity**: 🟡 MODERATE

**Findings**:

1. **File Names**:
   - `02_Logical_Map.md` - Philosophy-specific name
   - Should be configurable: `02_<TemplateAnalysisName>.md`
   - Legal example: `02_Legal_Analysis.md`

2. **File Content**:
   - Headers and markdown structure assume philosophy
   - Example (Logical_Map.md):
     ```markdown
     # Central Thesis and Argument Threads

     ## Main Thesis
     [Extracted thesis here...]
     ```
   - Legal equivalent:
     ```markdown
     # Legal Holdings and Precedent Analysis

     ## Primary Holding
     [Court's main decision...]
     ```

3. **Generic Files**:
   - ✅ `meta.yml` - Already generic
   - ✅ `01_Raw_Structure.md` - Just dumps extractions
   - ✅ `03_Concept_Index.md` - Concept tracking (generic)
   - ✅ `05_Coverage_Report.md` - Validation report (generic)
   - ✅ `extractions.json` - JSON dump (generic)

**Refactoring Strategy**:
- Templates define output file names and structures
- Philosophy template: `logical_map.md_template` with current headers
- Legal template: `legal_analysis.md_template` with legal headers
- Writer becomes generic renderer that loads templates
```

---

## 🎯 TASK 2: CREATE SPECIFICATION DOCUMENT

Now that you've audited all coupling points, create the comprehensive specification.

### 2.1 Create `spec-plan-v2.md`

**File**: `C:\Code\CliCode\ppke\spec-plan-v2.md`

**Structure**:

```markdown
# PPKE v2.0 Refactoring Specification
**From Philosophy-Specific Tool → General-Purpose Knowledge Framework**

---

## Executive Summary

Current PPKE v1.x is tightly coupled to philosophical text analysis. This specification outlines the transition to a domain-agnostic knowledge engine with plugin architecture, enabling use in law, medicine, science, and other domains.

**Key Changes**:
1. Replace hardcoded dataclasses with Pydantic models
2. Extract prompts to template YAML/JSON files
3. Implement 2-tier plugin system (Official + Custom)
4. Dynamic pipeline loading based on domain templates
5. Maintain 100% backward compatibility for philosophy domain

---

## Goals

1. **Generalization**: Domain-agnostic core functionality
2. **Plugin Architecture**: 2-tier system (Tier 1 Official, Tier 2 Custom)
3. **Standardized Schema**: Pydantic-based dynamic schemas
4. **Licensing**: Apache 2.0 for commercial compatibility
5. **Obsidian Integration**: Maintain seamless vault backend

---

## Audit Summary

[Insert findings from Task 1 here - copy your audit outputs]

---

## Architecture Changes

### Before (v1.x): Philosophy-Specific Monolith

```
ppke/
├── llm/prompts.py          # Hardcoded philosophy prompts
├── parser/models.py        # Philosophy dataclasses
├── pipeline/
│   ├── orchestrator.py     # Hard-coded 7-stage pipeline
│   ├── logical_map.py      # Philosophy-specific analysis
│   └── patterns.py         # Philosophy-specific patterns
└── output/writer.py        # Philosophy output structure
```

**Problems**:
- ❌ Cannot analyze legal contracts without modifying core code
- ❌ Medical texts get philosophy-specific analysis
- ❌ No community contributions possible
- ❌ Every domain needs core code changes

---

### After (v2.0): Plugin-Based Framework

```
ppke/
├── templates/              # NEW: Template system
│   ├── base.py             # PluginTemplate base class
│   ├── loader.py           # Dynamic template discovery
│   ├── validator.py        # Schema validation
│   │
│   ├── official/           # Tier 1: Verified plugins
│   │   ├── philosophy/
│   │   │   ├── template.yml        # Domain config
│   │   │   ├── prompts.yml         # LLM prompts
│   │   │   ├── schema.yml          # Pydantic schema
│   │   │   └── outputs.yml         # Output file templates
│   │   │
│   │   └── legal/
│   │       ├── template.yml
│   │       ├── prompts.yml
│   │       ├── schema.yml
│   │       └── outputs.yml
│   │
│   └── custom/             # Tier 2: User plugins (example structure)
│       └── README.md       # Points to ~/.ppke/plugins/
│
├── llm/
│   ├── prompts.py          # REFACTORED: Dynamic prompt loader
│   └── client.py           # Unchanged (already generic)
│
├── parser/
│   ├── models.py           # REFACTORED: Pydantic models
│   └── schema_builder.py   # NEW: Dynamic schema from templates
│
├── pipeline/
│   ├── orchestrator.py     # REFACTORED: Dynamic stage loading
│   ├── registry.py         # NEW: Stage registry
│   └── stages/             # Refactored stages (generic)
│       ├── extractor.py
│       ├── analyzer.py     # Generic analyzer (replaces logical_map)
│       ├── concepts.py
│       └── patterns.py
│
└── output/
    ├── writer.py           # REFACTORED: Template-driven renderer
    └── renderers.py        # NEW: Output format handlers
```

**Benefits**:
- ✅ Add new domains without changing core code
- ✅ Community can submit custom plugins
- ✅ Philosophy domain 100% backward compatible
- ✅ Official plugins curated and verified

---

## Data Model Refactoring

### Current (v1.x): Hardcoded Dataclasses

```python
# ppke/parser/models.py (v1.x)

@dataclass
class ExtractionResult:
    paragraph_id: str
    topic_sentence: str
    function_in_argument: str        # ← Hardcoded field
    explicit_claims: list[str]       # ← Hardcoded field
    implicit_assumptions: list[str]  # ← Hardcoded field
    logical_steps: list[str]         # ← Hardcoded field
    # ... 6 more hardcoded fields
```

**Problem**: Cannot adapt to legal, medical, or scientific domains.

---

### Proposed (v2.0): Pydantic Dynamic Models

```python
# ppke/parser/models.py (v2.0)

from pydantic import BaseModel, Field, create_model
from typing import Any, Dict

class BaseParagraph(BaseModel):
    """Domain-agnostic paragraph structure."""
    chapter_number: int
    paragraph_number: int
    text: str
    depth: DepthLevel
    sub_number: int | None = None

    @property
    def paragraph_id(self) -> str:
        if self.sub_number:
            return f"{{{self.chapter_number:02d}}}.p{self.paragraph_number}.{self.sub_number}"
        return f"{{{self.chapter_number:02d}}}.p{self.paragraph_number}"


class BaseExtraction(BaseModel):
    """Core extraction fields (domain-agnostic)."""
    paragraph_id: str
    original_text: str
    topic_sentence: str
    defined_concepts: list[str] = Field(default_factory=list)
    internal_references: list[str] = Field(default_factory=list)
    depth: DepthLevel


def build_extraction_model(template_schema: Dict[str, Any]) -> type[BaseModel]:
    """
    Dynamically create a Pydantic model from template schema.

    Args:
        template_schema: Template's schema.yml content

    Returns:
        Pydantic model class with template-defined fields

    Example (philosophy template):
        schema:
          name: PhilosophyExtraction
          base: BaseExtraction
          fields:
            - name: function_in_argument
              type: str
              description: "Role in philosophical argument"
            - name: explicit_claims
              type: list[str]
              description: "Explicit claims made"
            ...

    Example (legal template):
        schema:
          name: LegalExtraction
          base: BaseExtraction
          fields:
            - name: legal_standard
              type: str
              description: "Applicable legal standard"
            - name: case_references
              type: list[str]
              description: "Cited case law"
            ...
    """
    fields = {}
    for field_def in template_schema.get('fields', []):
        field_name = field_def['name']
        field_type = eval(field_def['type'])  # TODO: Safe eval
        field_desc = field_def.get('description', '')

        fields[field_name] = (field_type, Field(description=field_desc))

    return create_model(
        template_schema['name'],
        __base__=BaseExtraction,
        **fields
    )
```

**Usage**:
```python
# Load philosophy template
philosophy_schema = load_template_schema('philosophy')
PhilosophyExtraction = build_extraction_model(philosophy_schema)

# Instantiate with philosophy-specific fields
result = PhilosophyExtraction(
    paragraph_id="{01}.p5",
    original_text="...",
    topic_sentence="...",
    function_in_argument="introduces central thesis",  # Philosophy field
    explicit_claims=["Claim 1", "Claim 2"],             # Philosophy field
    # ...
)

# Load legal template
legal_schema = load_template_schema('legal')
LegalExtraction = build_extraction_model(legal_schema)

# Instantiate with legal-specific fields
result = LegalExtraction(
    paragraph_id="{01}.p5",
    original_text="...",
    topic_sentence="...",
    legal_standard="strict scrutiny",           # Legal field
    case_references=["Brown v. Board", "..."], # Legal field
    # ...
)
```

---

## Template System Design

### Template Directory Structure

```
ppke/templates/official/philosophy/
├── template.yml          # Domain metadata and configuration
├── prompts.yml           # LLM prompt templates
├── schema.yml            # Pydantic field definitions
└── outputs.yml           # Output file templates

ppke/templates/official/legal/
├── template.yml
├── prompts.yml
├── schema.yml
└── outputs.yml

~/.ppke/plugins/scientific_research/   # User custom plugin
├── template.yml
├── prompts.yml
├── schema.yml
└── outputs.yml
```

---

### `template.yml` (Philosophy Example)

```yaml
# ppke/templates/official/philosophy/template.yml

name: philosophy
version: "2.0.0"
tier: official
author: PPKE Core Team
description: "Philosophical text analysis with argument mapping"

# Pipeline stages (executed in order)
stages:
  - id: extraction
    name: "Structural Extraction"
    module: ppke.pipeline.stages.extractor
    prompt: prompts.extraction

  - id: logical_map
    name: "Logical Architecture"
    module: ppke.pipeline.stages.analyzer
    prompt: prompts.logical_map
    output_file: "02_Logical_Map.md"

  - id: concepts
    name: "Concept Indexing"
    module: ppke.pipeline.stages.concepts
    prompt: prompts.concepts
    output_file: "03_Concept_Index.md"

  - id: patterns
    name: "Pattern Detection"
    module: ppke.pipeline.stages.patterns
    prompt: prompts.patterns
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

---

### `prompts.yml` (Philosophy Example)

```yaml
# ppke/templates/official/philosophy/prompts.yml

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

    Return JSON in the exact schema provided.

  user_template: |
    Analyze the following paragraphs from chapter {chapter_number}:

    {paragraphs_json}

logical_map:
  system: |
    You are analyzing the **logical architecture** of a philosophical text.

    Given all paragraph extractions, identify:
    1. **central_thesis**: The main thesis or argument of the entire work
    2. **argument_threads**: Major lines of argument (3-7 threads)
       - For each thread:
         - Summary of the thread
         - Paragraphs involved (by ID)
         - How it supports the central thesis

    Return JSON.

  user_template: |
    Extractions from "{book_title}" by {author}:

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
    Concepts from "{book_title}":

    {extractions_json}

patterns:
  system: |
    Detect **rhetorical and philosophical patterns** in the text.

    Identify:
    1. **Metaphors**: Recurring metaphors and their significance
    2. **Contradictions**: Apparent contradictions and potential resolutions
    3. **Emotional Arcs**: Shifts in emotional tone throughout the text

    Return JSON with pattern arrays.

  user_template: |
    Analyze patterns in "{book_title}":

    {extractions_json}
```

---

### `schema.yml` (Philosophy Example)

```yaml
# ppke/templates/official/philosophy/schema.yml

extraction_model:
  name: PhilosophyExtraction
  base: BaseExtraction
  description: "Pydantic model for philosophical text extraction"

  fields:
    - name: function_in_argument
      type: str
      description: "Role in the philosophical argument"
      examples:
        - "introduces central thesis"
        - "provides supporting premise"
        - "addresses counterargument"

    - name: explicit_claims
      type: list[str]
      description: "Explicitly stated claims"
      default: []

    - name: implicit_assumptions
      type: list[str]
      description: "Unstated assumptions the argument relies on"
      default: []

    - name: logical_steps
      type: list[str]
      description: "Step-by-step logical progression"
      default: []

    - name: emotional_tone
      type: str
      description: "Emotional register of the paragraph"
      examples:
        - "assertive"
        - "polemical"
        - "neutral"
        - "questioning"

    - name: tone_evidence
      type: str
      description: "Textual evidence supporting the identified tone"
      default: ""
```

---

### `outputs.yml` (Philosophy Example)

```yaml
# ppke/templates/official/philosophy/outputs.yml

logical_map_template: |
  # Logical Architecture: {book_title}
  **Author**: {author}
  **Ingested**: {ingest_date}

  ---

  ## Central Thesis

  {central_thesis}

  ---

  ## Argument Threads

  {{% for thread in argument_threads %}}
  ### Thread {loop.index}: {thread.summary}

  **Paragraphs**: {thread.paragraph_ids}

  **Relationship to Thesis**: {thread.supports_thesis}

  {{% endfor %}}

concept_index_template: |
  # Concept Index: {book_title}
  **Author**: {author}

  ---

  {{% for concept in concepts %}}
  ## {concept.name}

  **Occurrences**: {concept.occurrences}

  {{% if concept.semantic_shifts %}}
  **Semantic Evolution**:
  {concept.semantic_shifts}
  {{% endif %}}

  ---
  {{% endfor %}}

patterns_template: |
  # Rhetorical Patterns: {book_title}

  ---

  ## Metaphors

  {{% for metaphor in metaphors %}}
  - **{metaphor.type}**: {metaphor.description}
    - Examples: {metaphor.examples}
  {{% endfor %}}

  ---

  ## Contradictions

  {{% for contradiction in contradictions %}}
  - **Apparent Contradiction**: {contradiction.description}
    - **Potential Resolution**: {contradiction.resolution}
  {{% endfor %}}

  ---

  ## Emotional Arcs

  {emotional_arc_description}
```

---

## Pipeline Refactoring

### Current Hard-Coded Pipeline (v1.x)

```python
# ppke/pipeline/orchestrator.py (v1.x)

def ingest_book(book, config, ...):
    # Hard-coded 7 stages

    # Skill 1: Structural Extraction
    extractions = extract_chapters(book, config)

    # Skill 3: Logical Map (hardcoded module)
    logical_map = build_logical_map(book, extractions, config)

    # Skill 4: Concepts (hardcoded module)
    concepts = build_concept_index(book, extractions, config)

    # Skill 5: Patterns (hardcoded module)
    patterns = detect_patterns(book, extractions, config)

    # Hardcoded output generation
    write_output_files(book, extractions, logical_map, concepts, patterns, ...)
```

---

### Proposed Dynamic Pipeline (v2.0)

```python
# ppke/pipeline/orchestrator.py (v2.0)

def ingest_book(book, config, domain='philosophy', ...):
    # Load domain template
    template = load_template(domain)

    # Build Pydantic model from template
    ExtractionModel = build_extraction_model(template.schema)

    # Execute stages dynamically
    results = {}
    for stage in template.stages:
        stage_module = import_module(stage.module)
        stage_func = getattr(stage_module, f"run_{stage.id}")

        results[stage.id] = stage_func(
            book=book,
            config=config,
            template=template,
            previous_results=results,
            ExtractionModel=ExtractionModel
        )

    # Generate outputs from template
    render_outputs(book, template, results)
```

---

## Plugin Discovery System

```python
# ppke/templates/loader.py

from pathlib import Path
import yaml

OFFICIAL_TEMPLATES_DIR = Path(__file__).parent / "official"
CUSTOM_TEMPLATES_DIR = Path.home() / ".ppke" / "plugins"

def discover_templates() -> dict[str, Path]:
    """
    Discover all available templates (Tier 1 + Tier 2).

    Returns:
        {
            'philosophy': Path('ppke/templates/official/philosophy'),
            'legal': Path('ppke/templates/official/legal'),
            'scientific_research': Path('/home/user/.ppke/plugins/scientific_research'),
        }
    """
    templates = {}

    # Tier 1: Official templates
    for template_dir in OFFICIAL_TEMPLATES_DIR.iterdir():
        if template_dir.is_dir() and (template_dir / "template.yml").exists():
            templates[template_dir.name] = template_dir

    # Tier 2: Custom user templates
    if CUSTOM_TEMPLATES_DIR.exists():
        for template_dir in CUSTOM_TEMPLATES_DIR.iterdir():
            if template_dir.is_dir() and (template_dir / "template.yml").exists():
                # Avoid name conflicts (official takes precedence)
                if template_dir.name not in templates:
                    templates[template_dir.name] = template_dir

    return templates


def load_template(domain: str) -> PluginTemplate:
    """Load and validate a template."""
    templates = discover_templates()

    if domain not in templates:
        available = ', '.join(templates.keys())
        raise ValueError(f"Unknown domain '{domain}'. Available: {available}")

    template_path = templates[domain]

    # Load all template files
    with open(template_path / "template.yml") as f:
        config = yaml.safe_load(f)

    with open(template_path / "prompts.yml") as f:
        prompts = yaml.safe_load(f)

    with open(template_path / "schema.yml") as f:
        schema = yaml.safe_load(f)

    with open(template_path / "outputs.yml") as f:
        outputs = yaml.safe_load(f)

    # Validate and return
    template = PluginTemplate(
        name=config['name'],
        version=config['version'],
        tier=config['tier'],
        stages=config['stages'],
        prompts=prompts,
        schema=schema,
        outputs=outputs,
        skip_chapters=config.get('skip_chapters', [])
    )

    validate_template(template)  # Security check

    return template
```

---

## CLI Changes

### New Commands

```bash
# List all available domains (official + custom)
$ ppke list-domains
Available domains:
  - philosophy (official) - v2.0.0
  - legal (official) - v2.0.0
  - scientific_research (custom) - v1.0.0

# Ingest with domain flag
$ ppke ingest --domain philosophy path/to/book.md
$ ppke ingest --domain legal path/to/contract.md
$ ppke ingest --domain scientific_research path/to/paper.md

# Validate a custom plugin
$ ppke validate-plugin ~/.ppke/plugins/my_domain
✅ Plugin 'my_domain' is valid
⚠️  Warning: prompt 'extraction' is very long (>5000 chars)

# Promote a custom plugin to official (maintainer only)
$ ppke promote-plugin my_domain
```

### Backward Compatibility

```bash
# v1.x command (no --domain flag)
$ ppke ingest path/to/philosophy.md

# v2.0 behavior: defaults to 'philosophy' domain
# Produces identical output to v1.x
```

---

## Migration Checklist

### Phase 1: Audit & Specification ✅ (Current Phase)
- [x] Audit prompts.py for philosophy coupling
- [x] Audit models.py for dataclass limitations
- [x] Audit pipeline stages for hardcoding
- [x] Audit output generation for philosophy assumptions
- [x] Create spec-plan-v2.md
- [x] Add Apache 2.0 LICENSE
- [x] Create REFACTORING_CHECKLIST.md

### Phase 2: Refactor Core (Next Phase)
- [ ] Convert dataclasses to Pydantic models
- [ ] Create template system (base classes)
- [ ] Move prompts to philosophy/prompts.yml
- [ ] Implement dynamic prompt loader
- [ ] Refactor orchestrator for dynamic stages
- [ ] Create legal template (proof of concept)
- [ ] Update CLI with --domain flag

### Phase 3: Plugin Ecosystem
- [ ] Implement template discovery
- [ ] Create plugin validator
- [ ] Write PLUGINS.md documentation
- [ ] Implement ppke list-domains
- [ ] Implement ppke validate-plugin
- [ ] Implement ppke promote-plugin
- [ ] Create example Tier 2 plugin

### Phase 4: Validation
- [ ] Test philosophy domain (100% v1.x compatibility)
- [ ] Test legal domain
- [ ] Test custom plugin
- [ ] Performance benchmarks
- [ ] Security audit
- [ ] Documentation complete

---

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `LICENSE` | **NEW** | Apache 2.0 license |
| `spec-plan-v2.md` | **NEW** | This document |
| `REFACTORING_CHECKLIST.md` | **NEW** | Migration tracking |
| `ppke/parser/models.py` | **REFACTOR** | Dataclasses → Pydantic |
| `ppke/parser/schema_builder.py` | **NEW** | Dynamic model builder |
| `ppke/llm/prompts.py` | **REFACTOR** | Hardcoded → Dynamic loader |
| `ppke/pipeline/orchestrator.py` | **REFACTOR** | Hardcoded → Dynamic stages |
| `ppke/pipeline/registry.py` | **NEW** | Stage registry |
| `ppke/pipeline/stages/analyzer.py` | **NEW** | Generic analyzer (replaces logical_map) |
| `ppke/output/writer.py` | **REFACTOR** | Hardcoded → Template renderer |
| `ppke/output/renderers.py` | **NEW** | Output format handlers |
| `ppke/templates/base.py` | **NEW** | PluginTemplate base class |
| `ppke/templates/loader.py` | **NEW** | Template discovery |
| `ppke/templates/validator.py` | **NEW** | Schema validation |
| `ppke/templates/official/philosophy/*` | **NEW** | Philosophy template (v1.x equivalent) |
| `ppke/templates/official/legal/*` | **NEW** | Legal template (new domain) |
| `ppke/cli.py` | **UPDATE** | Add --domain flag, list-domains, validate-plugin |

---

## Success Criteria

### Must Have
✅ 100% backward compatibility with philosophy domain
✅ At least 2 working domains (philosophy + legal)
✅ Template system with validation
✅ Dynamic Pydantic model generation
✅ Apache 2.0 license applied

### Should Have
✅ Plugin discovery for custom plugins
✅ Documentation for plugin development
✅ Example Tier 2 plugin
✅ Security validation for plugins

### Nice to Have
✅ Web-based plugin registry
✅ Auto-update for official templates
✅ Template versioning system

---

[End of spec-plan-v2.md]
```

---

## 🎯 TASK 3: CREATE APACHE 2.0 LICENSE

**File**: `C:\Code\CliCode\ppke\LICENSE`

**Action**: Create the LICENSE file with Apache 2.0 text.

**Content**:

```
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
```

**Customization**:
Replace the APPENDIX section with:

```
Copyright 2025 PPKE Project Contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## 🎯 TASK 4: CREATE REFACTORING CHECKLIST

**File**: `C:\Code\CliCode\ppke\REFACTORING_CHECKLIST.md`

**Purpose**: Track progress through all 4 phases with granular tasks.

**Content**:

```markdown
# PPKE v2.0 Refactoring Checklist

Track progress through the transition from philosophy-specific tool to general-purpose knowledge framework.

---

## Phase 1: Audit & Specification ✅

### Audit Tasks
- [x] Audit `ppke/llm/prompts.py` for philosophy coupling
- [x] Audit `ppke/parser/models.py` for dataclass limitations
- [x] Audit `ppke/pipeline/orchestrator.py` for hardcoded pipeline
- [x] Audit `ppke/pipeline/logical_map.py` for philosophy assumptions
- [x] Audit `ppke/pipeline/concepts.py` for domain coupling
- [x] Audit `ppke/pipeline/patterns.py` for philosophy-specific patterns
- [x] Audit `ppke/output/writer.py` for output structure assumptions

### Documentation Tasks
- [x] Create `spec-plan-v2.md` with full architecture design
- [x] Create `LICENSE` (Apache 2.0)
- [x] Create `REFACTORING_CHECKLIST.md` (this file)

### Validation
- [x] All philosophy couplings identified and documented
- [x] Spec plan includes before/after code examples
- [x] Apache 2.0 license properly formatted

---

## Phase 2: Refactor Core 🔄

### Data Model Refactoring
- [ ] Convert `Paragraph` dataclass to Pydantic model
- [ ] Convert `Chapter` dataclass to Pydantic model
- [ ] Convert `Book` dataclass to Pydantic model
- [ ] Convert `ExtractionResult` to `BaseExtraction` Pydantic model
- [ ] Create `ppke/parser/schema_builder.py` with `build_extraction_model()`
- [ ] Test dynamic Pydantic model generation

### Template System
- [ ] Create `ppke/templates/base.py` with `PluginTemplate` class
- [ ] Create `ppke/templates/loader.py` with template discovery
- [ ] Create `ppke/templates/validator.py` with schema validation
- [ ] Create `ppke/templates/official/philosophy/template.yml`
- [ ] Create `ppke/templates/official/philosophy/prompts.yml`
- [ ] Create `ppke/templates/official/philosophy/schema.yml`
- [ ] Create `ppke/templates/official/philosophy/outputs.yml`
- [ ] Create `ppke/templates/official/legal/template.yml`
- [ ] Create `ppke/templates/official/legal/prompts.yml`
- [ ] Create `ppke/templates/official/legal/schema.yml`
- [ ] Create `ppke/templates/official/legal/outputs.yml`

### Prompt Refactoring
- [ ] Refactor `ppke/llm/prompts.py` to load prompts from templates
- [ ] Create `load_prompt(template, prompt_id)` function
- [ ] Test philosophy prompts load correctly from template
- [ ] Test legal prompts load correctly from template

### Pipeline Refactoring
- [ ] Refactor `ppke/pipeline/orchestrator.py` for dynamic stage loading
- [ ] Add `domain` parameter to `ingest_book()`
- [ ] Implement stage registry system
- [ ] Create `ppke/pipeline/stages/analyzer.py` (generic version of logical_map)
- [ ] Refactor `ppke/pipeline/stages/extractor.py` to use templates
- [ ] Refactor `ppke/pipeline/concepts.py` to use templates
- [ ] Refactor `ppke/pipeline/patterns.py` to use templates
- [ ] Test philosophy pipeline produces identical output to v1.x
- [ ] Test legal pipeline successfully ingests contracts

### Output Refactoring
- [ ] Refactor `ppke/output/writer.py` for template-driven rendering
- [ ] Create `ppke/output/renderers.py` with Jinja2 support
- [ ] Test philosophy output files match v1.x format exactly
- [ ] Test legal output files render correctly

### CLI Updates
- [ ] Add `--domain` flag to `ppke ingest`
- [ ] Add `ppke list-domains` command
- [ ] Update `ppke status` to show domain
- [ ] Update help text for all commands
- [ ] Test backward compatibility (no --domain flag defaults to philosophy)

### Testing
- [ ] All existing tests pass with philosophy domain
- [ ] Create `tests/test_templates.py` for template loading
- [ ] Create `tests/test_legal_domain.py` for legal template
- [ ] Create `tests/test_pydantic_models.py` for dynamic models
- [ ] Performance regression tests (not slower than v1.x)

---

## Phase 3: Plugin Ecosystem 🔄

### Plugin Discovery
- [ ] Implement `discover_templates()` function
- [ ] Scan `ppke/templates/official/` for Tier 1 plugins
- [ ] Scan `~/.ppke/plugins/` for Tier 2 custom plugins
- [ ] Handle name conflicts (official takes precedence)
- [ ] Test plugin discovery with 3+ domains

### Plugin Validation
- [ ] Create `validate_template()` function
- [ ] Schema validation (all required files present)
- [ ] Security validation (no arbitrary code execution)
- [ ] Prompt size warnings (>5000 chars)
- [ ] Test with malicious plugin attempts

### Documentation
- [ ] Create `PLUGINS.md` with plugin development guide
- [ ] Document template YAML schema
- [ ] Document Pydantic field types
- [ ] Document submission process for Tier 2 → Tier 1 promotion
- [ ] Create example Tier 2 plugin (scientific_research)

### CLI Commands
- [ ] Implement `ppke list-domains` (show all available templates)
- [ ] Implement `ppke validate-plugin <path>`
- [ ] Implement `ppke promote-plugin <domain>` (maintainer only)
- [ ] Update `ppke doctor` to check for plugin issues

### Testing
- [ ] Test official philosophy plugin loads correctly
- [ ] Test official legal plugin loads correctly
- [ ] Test custom scientific_research plugin loads correctly
- [ ] Test plugin validation rejects invalid schemas
- [ ] Test promote-plugin workflow

---

## Phase 4: System Validation 🔄

### Domain Compatibility Testing
- [ ] Philosophy domain produces identical output to v1.x
- [ ] Legal domain successfully ingests sample contract
- [ ] Scientific_research plugin successfully ingests sample paper
- [ ] Cross-domain queries work (philosophy + legal)
- [ ] Vector search works across all domains

### API Key Management Testing
- [ ] Anthropic provider works with all domains
- [ ] OpenAI provider works with all domains
- [ ] DeepSeek provider works with all domains
- [ ] Gemini provider works with all domains
- [ ] OpenRouter provider works with all domains
- [ ] Provider switching with `--provider` flag works

### Integration Testing
- [ ] Vector search indexes multi-domain data correctly
- [ ] Knowledge graph supports cross-domain concepts
- [ ] Cross-query synthesizes across domains
- [ ] Progress tracking works for all domains
- [ ] Checkpoint/resume works for all domains

### Performance Testing
- [ ] Parallel extraction maintains v1.x speed
- [ ] Async pipeline performance benchmarks
- [ ] Memory usage with large documents
- [ ] Template loading overhead is negligible (<100ms)

### Security Testing
- [ ] Plugin validation blocks arbitrary code execution
- [ ] Path traversal protection in template loading
- [ ] API key security (not exposed in templates)
- [ ] No SQL/code injection via template fields

### Documentation
- [ ] All 23 CLI commands documented
- [ ] Plugin development guide is complete and tested
- [ ] Migration guide from v1.x to v2.0 written
- [ ] Release notes for PPKE 2.0 prepared
- [ ] README updated with new features

### Final Validation
- [ ] Test coverage >80%
- [ ] Zero security vulnerabilities
- [ ] All commands have help text
- [ ] Example data for all domains
- [ ] Ready for release

---

## Release Criteria

### Must Have ✅
- [ ] 100% backward compatibility with philosophy domain
- [ ] At least 2 working domains (philosophy + legal)
- [ ] Template system with validation
- [ ] Dynamic Pydantic model generation
- [ ] Apache 2.0 license applied
- [ ] All tests passing

### Should Have ✅
- [ ] Plugin discovery for custom plugins
- [ ] Documentation for plugin development
- [ ] Example Tier 2 plugin
- [ ] Security validation for plugins

### Nice to Have 🎯
- [ ] Web-based plugin registry
- [ ] Auto-update for official templates
- [ ] Template versioning system
- [ ] Community plugin showcase

---

**Last Updated**: [DATE]
**Current Phase**: Phase 1 (Audit & Specification)
```

---

## ✅ VALIDATION CRITERIA

After completing all tasks in Phase 1, validate:

### 1. Audit Report Completeness
- [ ] All 7+ prompts from `prompts.py` analyzed
- [ ] All dataclasses from `models.py` analyzed
- [ ] All pipeline stages analyzed
- [ ] Output generation analyzed
- [ ] Severity ratings assigned (🔴 Critical, 🟡 Moderate, ✅ Generic)

### 2. Specification Quality
- [ ] `spec-plan-v2.md` contains before/after code examples
- [ ] Template YAML examples are complete
- [ ] Pydantic refactoring strategy is clear
- [ ] Pipeline refactoring strategy is detailed
- [ ] File changes table is accurate

### 3. License Correctness
- [ ] `LICENSE` file is Apache 2.0
- [ ] Copyright year is 2025
- [ ] Copyright holder is "PPKE Project Contributors"

### 4. Checklist Accuracy
- [ ] `REFACTORING_CHECKLIST.md` covers all 4 phases
- [ ] Tasks are granular and actionable
- [ ] Phase 1 tasks are marked as completed
- [ ] Release criteria are defined

---

## 🔄 RALPH WIGGUM VALIDATION

Before moving to Phase 2, perform final audit:

### Execute ✅
- Created `spec-plan-v2.md`
- Created `LICENSE`
- Created `REFACTORING_CHECKLIST.md`

### Audit 🔍
- [ ] Read through `spec-plan-v2.md` - Does it make sense?
- [ ] Are all code examples syntactically correct?
- [ ] Are template YAML examples valid YAML?
- [ ] Is the Pydantic refactoring feasible?
- [ ] Are there any logical gaps in the design?

### Iterate 🔁
If any issues found:
1. Document the issue
2. Update `spec-plan-v2.md` with corrections
3. Re-validate

### Validate ✅
- [ ] Spec plan reviewed by at least one other developer (if team)
- [ ] All deliverables present and complete
- [ ] Ready to proceed to Phase 2

---

## 📚 REFERENCE MATERIALS

### Internal Docs
- `ARCHITECTURE_V2.md` - High-level v2.0 vision
- `spec-plan-v2.md` - Detailed specification (created in this phase)
- `TRANSITION_ROADMAP.md` - Project timeline

### External Resources
- Pydantic documentation: https://docs.pydantic.dev/
- YAML specification: https://yaml.org/spec/
- Apache 2.0 License: https://www.apache.org/licenses/LICENSE-2.0
- Plugin architecture patterns: https://realpython.com/python-application-layouts/

---

## 🚀 NEXT STEPS

After completing Phase 1, proceed to:

**Phase 2: Refactor Core**
Use the metaprompt: `prompts/phase-2-refactor-core.md`

**Estimated Duration**: 20-30 hours
**Key Milestone**: Philosophy domain produces identical output to v1.x via template system

---

## ❓ TROUBLESHOOTING

### Common Issues in Phase 1

**Issue**: Too many philosophy couplings found, overwhelming to document
**Solution**: Focus on the top 3 critical areas: prompts, models, pipeline stages

**Issue**: Pydantic dynamic model generation seems complex
**Solution**: Start with simple example (2-3 fields) before tackling full ExtractionResult

**Issue**: Unsure how templates should be structured
**Solution**: Reference existing template examples in Django, Jinja2, or FastAPI

**Issue**: Apache 2.0 license concerns about commercial use
**Solution**: Apache 2.0 explicitly allows commercial use while requiring attribution

---

## 📧 CONTACT

Questions about Phase 1?
- Open GitHub issue with `[Phase 1]` prefix
- Tag maintainers for review
- Check `CONTRIBUTING.md` for guidelines

---

**END OF PHASE 1 METAPROMPT**

**Next Metaprompt**: `prompts/phase-2-refactor-core.md`
