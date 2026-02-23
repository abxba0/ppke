# PHASE 3: PLUGIN ECOSYSTEM
**PPKE v2.0 Refactoring - Community & Extension Phase**

---

## 📋 PHASE OVERVIEW

**Phase Number**: 3 of 4
**Estimated Effort**: 12-16 hours
**Prerequisites**: Phase 1 & 2 complete (template system working)
**Complexity**: Medium

**Objective**: Implement the 2-tier plugin system (Tier 1 Official, Tier 2 Custom), create plugin development documentation, and build tooling for plugin validation, discovery, and promotion.

---

## 🎯 DELIVERABLES

1. ✅ **Plugin Discovery System** (scans `~/.ppke/plugins/`)
2. ✅ **PLUGINS.md** (complete plugin development guide)
3. ✅ **TEMPLATE_DEVELOPMENT_GUIDE.md** (technical reference)
4. ✅ **Example Tier 2 Plugin** (`scientific_research`)
5. ✅ **CLI Commands**:
   - `ppke list-domains` (already in Phase 2)
   - `ppke validate-plugin <path>`
   - `ppke promote-plugin <name>` (maintainer only)
6. ✅ **Plugin Registry** (JSON-based tracking)

---

## 🔄 RALPH WIGGUM METHODOLOGY

For **every task**:

```
1. EXECUTE  → Implement the feature
2. AUDIT    → Test with valid & invalid plugins
3. ITERATE  → Fix edge cases
4. VALIDATE → Test end-to-end workflow
```

---

## 🎯 TASK 1: ENHANCE PLUGIN DISCOVERY

### 1.1 Update Template Loader (Already Started in Phase 2)

**File**: `ppke/templates/loader.py`

Already implemented `discover_templates()` - verify it correctly:
- Scans `ppke/templates/official/` (Tier 1)
- Scans `~/.ppke/plugins/` (Tier 2)
- Official templates take precedence on name conflicts

**Test**:
```bash
$ mkdir -p ~/.ppke/plugins/test_domain
$ touch ~/.ppke/plugins/test_domain/template.yml
$ python -c "from ppke.templates.loader import discover_templates; print(discover_templates())"
# Should show: {'philosophy': ..., 'legal': ..., 'test_domain': ...}
```

---

### 1.2 Create Plugin Registry

**New File**: `ppke/templates/registry.py`

```python
"""Plugin registry for tracking installed templates."""

from pathlib import Path
import json
from datetime import datetime
from typing import Optional

REGISTRY_FILE = Path.home() / ".ppke" / "plugin_registry.json"


def get_registry() -> dict:
    """Load plugin registry."""
    if not REGISTRY_FILE.exists():
        return {'plugins': {}, 'last_updated': None}

    with open(REGISTRY_FILE, 'r') as f:
        return json.load(f)


def register_plugin(name: str, tier: str, version: str, source: str, author: str = None):
    """
    Register a plugin in the local registry.

    Args:
        name: Plugin name
        tier: 'official' or 'custom'
        version: Semantic version
        source: Installation source ('bundled', 'manual', 'github:<url>', etc.)
        author: Plugin author
    """
    registry = get_registry()

    registry['plugins'][name] = {
        'name': name,
        'tier': tier,
        'version': version,
        'source': source,
        'author': author,
        'installed_at': datetime.utcnow().isoformat()
    }
    registry['last_updated'] = datetime.utcnow().isoformat()

    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(registry, f, indent=2)


def unregister_plugin(name: str):
    """Remove plugin from registry."""
    registry = get_registry()
    if name in registry['plugins']:
        del registry['plugins'][name]
        registry['last_updated'] = datetime.utcnow().isoformat()

        with open(REGISTRY_FILE, 'w') as f:
            json.dump(registry, f, indent=2)


def get_plugin_info(name: str) -> Optional[dict]:
    """Get metadata for a registered plugin."""
    registry = get_registry()
    return registry['plugins'].get(name)
```

**Usage**:
```python
from ppke.templates.registry import register_plugin, get_plugin_info

# Register official plugins on first run
register_plugin('philosophy', 'official', '2.0.0', 'bundled', 'PPKE Core Team')
register_plugin('legal', 'official', '2.0.0', 'bundled', 'PPKE Core Team')

# Register user plugin
register_plugin('my_domain', 'custom', '1.0.0', 'manual', 'John Doe')

# Query
info = get_plugin_info('philosophy')
print(info['tier'])  # 'official'
```

---

## 🎯 TASK 2: CREATE PLUGIN DOCUMENTATION

### 2.1 Create PLUGINS.md

**File**: `C:\Code\CliCode\ppke\PLUGINS.md`

```markdown
# PPKE Plugin System
**Extend PPKE to Analyze Any Domain**

---

## Overview

PPKE v2.0 uses a **2-tier plugin system**:

1. **Tier 1: Official Plugins** - Verified and maintained by PPKE core team
   - Location: `ppke/templates/official/`
   - Examples: `philosophy`, `legal`
   - Quality-assured, tested, and documented

2. **Tier 2: Custom Plugins** - Community-submitted or user-created
   - Location: `~/.ppke/plugins/`
   - Developed by anyone for specialized domains
   - Can be promoted to Tier 1 after review

---

## Quick Start: Using Plugins

### List Available Domains

```bash
$ ppke list-domains
Available domains:
  - philosophy (official) - v2.0.0
    Philosophical text analysis with argument mapping
  - legal (official) - v2.0.0
    Legal document analysis with case law tracking
  - scientific_research (custom) - v1.0.0
    Scientific paper analysis with methodology extraction
```

### Ingest with a Domain

```bash
# Use philosophy template (default)
$ ppke ingest path/to/philosophy_book.md

# Use legal template
$ ppke ingest --domain legal path/to/contract.md

# Use custom scientific_research template
$ ppke ingest --domain scientific_research path/to/paper.md
```

---

## Creating a Custom Plugin

### Step 1: Create Plugin Directory

```bash
$ mkdir -p ~/.ppke/plugins/my_domain
$ cd ~/.ppke/plugins/my_domain
```

### Step 2: Create Required Files

Every plugin needs 4 files:

1. `template.yml` - Plugin metadata and configuration
2. `schema.yml` - Pydantic field definitions
3. `prompts.yml` - LLM prompts
4. `outputs.yml` - Output file templates (optional)

---

### File 1: `template.yml`

```yaml
name: my_domain
version: "1.0.0"
tier: custom
author: Your Name
description: "Brief description of what this plugin analyzes"

# Pipeline stages (executed in order)
stages:
  - id: extraction
    name: "Structural Extraction"
    module: ppke.pipeline.stages.extractor
    prompt: extraction

  - id: my_custom_analysis
    name: "Domain-Specific Analysis"
    module: ppke.pipeline.stages.analyzer
    prompt: custom_analysis
    output_file: "02_My_Analysis.md"

  - id: concepts
    name: "Concept Indexing"
    module: ppke.pipeline.stages.concepts
    prompt: concepts
    output_file: "03_Concept_Index.md"

# Skip logic (optional)
skip_chapters:
  - bibliography
  - references

# Output configuration
outputs:
  folder_format: "Book_{title}_{author}_{year}"
  files:
    - "meta.yml"
    - "01_Raw_Structure.md"
    - "02_My_Analysis.md"
    - "03_Concept_Index.md"
    - "extractions.json"
```

---

### File 2: `schema.yml`

```yaml
extraction_model:
  name: MyDomainExtraction
  base: BaseExtraction
  description: "Pydantic model for my domain extraction"

  fields:
    # Define your domain-specific fields
    - name: my_field_1
      type: str
      description: "What does this field capture?"
      default: ""

    - name: my_field_2
      type: list[str]
      description: "Another field (list of strings)"
      default: []

    - name: my_numeric_field
      type: int
      description: "Numeric field example"
      default: 0
```

**Supported Field Types**:
- `str` - String
- `int` - Integer
- `float` - Float
- `bool` - Boolean
- `list[str]` - List of strings
- `list[int]` - List of integers
- `Optional[str]` - Optional string (can be null)

---

### File 3: `prompts.yml`

```yaml
extraction:
  system: |
    You are analyzing a **[YOUR DOMAIN]** text. For each paragraph, extract:

    1. **topic_sentence**: One-sentence summary (< 30 words)
    2. **my_field_1**: [Explain what to extract]
    3. **my_field_2**: [Explain what to extract]

    Return JSON matching the schema exactly.

  user_template: |
    Analyze the following paragraphs from chapter {chapter_number}:

    {paragraphs_json}

custom_analysis:
  system: |
    You are performing [CUSTOM ANALYSIS NAME].

    Given all paragraph extractions, identify:
    1. **key_insight_1**: [What to find]
    2. **key_insight_2**: [What to find]

    Return JSON.

  user_template: |
    Analyze "{book_title}" by {author}:

    {extractions_json}

concepts:
  system: |
    Track **concepts** throughout the text.

    For each concept:
    1. **concept**: Normalized name
    2. **occurrences**: Paragraph IDs
    3. **semantic_shifts**: Evolution of meaning

    Return JSON array.

  user_template: |
    Concept index for "{book_title}":

    {extractions_json}
```

---

### File 4: `outputs.yml` (Optional)

```yaml
custom_analysis_template: |
  # Custom Analysis: {book_title}
  **Author**: {author}

  ---

  ## Key Insights

  {custom_analysis_content}

concept_index_template: |
  # Concepts: {book_title}

  ---

  {{% for concept in concepts %}}
  ## {concept.name}
  **Occurrences**: {concept.occurrences}
  {{% endfor %}}
```

---

### Step 3: Validate Your Plugin

```bash
$ ppke validate-plugin ~/.ppke/plugins/my_domain
✅ Plugin 'my_domain' is valid
✅ All required files present
✅ Schema is valid
✅ No security issues detected
⚠️  Warning: Prompt 'extraction' is very long (4500 chars)
```

---

### Step 4: Use Your Plugin

```bash
$ ppke ingest --domain my_domain path/to/document.md
```

---

## Plugin Development Best Practices

### 1. Start Simple
Begin with the **extraction** stage only. Add custom analysis stages later.

### 2. Study Existing Templates
Look at `ppke/templates/official/philosophy/` and `ppke/templates/official/legal/` for examples.

### 3. Keep Prompts Focused
- Each prompt should have a single, clear purpose
- Keep system prompts under 3000 characters
- Provide clear examples in prompts

### 4. Test Incrementally
Test each stage independently before combining:
```bash
# Test just extraction
$ ppke ingest --domain my_domain test_doc.md

# Check output files
$ cat ~/KnowledgeBase/Book_*/01_Raw_Structure.md
```

### 5. Use Semantic Field Names
- ❌ Bad: `field1`, `data`, `output`
- ✅ Good: `research_methodology`, `legal_standard`, `emotional_tone`

### 6. Provide Defaults
Always provide `default: ""` or `default: []` for optional fields.

### 7. Document Your Plugin
Add a `README.md` to your plugin directory explaining:
- What domain it's for
- What fields it extracts
- Example use cases

---

## Promoting a Plugin to Tier 1 (Official)

### Submission Process

1. **Ensure Quality**:
   - Plugin has been used successfully on 5+ documents
   - All fields are well-documented
   - Prompts produce consistent, accurate results

2. **Open GitHub Issue**:
   - Title: `[Plugin Submission] <your_domain>`
   - Include:
     - Domain description
     - Use cases
     - Example outputs
     - Link to plugin files (GitHub Gist or repo)

3. **Core Team Review**:
   - Code quality check
   - Security audit
   - Usefulness assessment
   - Documentation completeness

4. **Promotion**:
   - If approved, plugin moves to `ppke/templates/official/`
   - Listed as "official" in `ppke list-domains`
   - Included in future PPKE releases

---

## Plugin Registry Commands

### List All Domains
```bash
$ ppke list-domains
```

### Validate Plugin
```bash
$ ppke validate-plugin ~/.ppke/plugins/my_domain
```

### Promote Plugin (Maintainer Only)
```bash
$ ppke promote-plugin my_domain
✅ Promoted 'my_domain' from Tier 2 (custom) to Tier 1 (official)
Moved: ~/.ppke/plugins/my_domain -> ppke/templates/official/my_domain
```

---

## Example: Scientific Research Plugin

See `~/.ppke/plugins/scientific_research/` for a complete example:
- Extracts: methodology, findings, statistical_tests, citations
- Analyzes: research_questions, hypotheses, conclusions
- Tracks: terminology, author_contributions

**Install**:
```bash
$ ppke install-plugin scientific_research
# Or manually copy to ~/.ppke/plugins/scientific_research/
```

**Usage**:
```bash
$ ppke ingest --domain scientific_research path/to/research_paper.md
```

---

## Troubleshooting

### "Unknown domain 'my_domain'"
- Check plugin directory: `ls ~/.ppke/plugins/my_domain`
- Ensure `template.yml` exists
- Run: `ppke list-domains` to see if discovered

### "Schema validation error"
- Run: `ppke validate-plugin ~/.ppke/plugins/my_domain`
- Check `schema.yml` syntax (valid YAML?)
- Ensure all required fields present

### "Prompt returns invalid JSON"
- Test prompt independently in LLM playground
- Simplify prompt and add more examples
- Check JSON schema matches Pydantic model exactly

---

## Resources

- **Technical Reference**: See `TEMPLATE_DEVELOPMENT_GUIDE.md`
- **Pydantic Docs**: https://docs.pydantic.dev/
- **YAML Specification**: https://yaml.org/spec/
- **Example Templates**: `ppke/templates/official/`

---

**Questions?**
- GitHub Issues: Tag with `plugin-development`
- Discussions: #plugins channel
```

---

### 2.2 Create TEMPLATE_DEVELOPMENT_GUIDE.md

**File**: `C:\Code\CliCode\ppke\TEMPLATE_DEVELOPMENT_GUIDE.md`

```markdown
# Template Development Guide
**Technical Reference for PPKE Plugin Developers**

---

## Architecture Overview

### Template Loading Flow

```
1. User runs: ppke ingest --domain my_domain doc.md
2. PPKE calls: load_template('my_domain')
3. Loader searches:
   - ppke/templates/official/my_domain/
   - ~/.ppke/plugins/my_domain/
4. Loads 4 YAML files:
   - template.yml (config)
   - schema.yml (Pydantic fields)
   - prompts.yml (LLM prompts)
   - outputs.yml (output templates)
5. Validator checks: security, schema correctness
6. Build dynamic Pydantic model from schema
7. Execute pipeline stages
8. Render outputs
```

---

## Template File Reference

### template.yml

**Required Fields**:
```yaml
name: str           # Lowercase, underscores only (e.g., 'my_domain')
version: str        # Semantic version (e.g., '1.0.0')
tier: str           # 'official' or 'custom'
author: str         # Your name or organization
description: str    # Brief description (< 200 chars)
stages: list        # Pipeline stages (see below)
```

**Optional Fields**:
```yaml
skip_chapters: list[str]   # Chapter titles to skip
outputs: dict              # Output configuration
```

**Stages Structure**:
```yaml
stages:
  - id: extraction                         # Unique stage ID
    name: "Structural Extraction"          # Human-readable name
    module: ppke.pipeline.stages.extractor # Python module path
    prompt: extraction                     # Prompt ID from prompts.yml
    output_file: "02_MyAnalysis.md"       # (optional) Output file name
```

**Built-in Stage Modules**:
- `ppke.pipeline.stages.extractor` - Paragraph-level extraction
- `ppke.pipeline.stages.analyzer` - Document-level analysis
- `ppke.pipeline.stages.concepts` - Concept tracking
- `ppke.pipeline.stages.patterns` - Pattern detection

---

### schema.yml

**Required Structure**:
```yaml
extraction_model:
  name: str          # PascalCase (e.g., 'MyDomainExtraction')
  base: str          # Always 'BaseExtraction'
  description: str   # Model description
  fields: list       # Field definitions
```

**Field Definition**:
```yaml
fields:
  - name: str          # camelCase (e.g., 'myField')
    type: str          # See "Supported Types" below
    description: str   # What this field captures
    default: any       # (optional) Default value (required fields use `...`)
    examples: list     # (optional) Example values for documentation
```

**Supported Types**:
| Type String | Python Type | Example |
|-------------|-------------|---------|
| `str` | `str` | `"example"` |
| `int` | `int` | `42` |
| `float` | `float` | `3.14` |
| `bool` | `bool` | `true` |
| `list[str]` | `list[str]` | `["a", "b"]` |
| `list[int]` | `list[int]` | `[1, 2, 3]` |
| `Optional[str]` | `Optional[str]` | `null` or `"value"` |

---

### prompts.yml

**Structure**:
```yaml
<prompt_id>:
  system: str       # System prompt (instructs LLM behavior)
  user_template: str  # User prompt template (formatted with variables)
```

**Template Variables**:
Variables are injected dynamically:
- `{chapter_number}` - Current chapter number
- `{paragraphs_json}` - JSON string of paragraphs
- `{extractions_json}` - JSON string of extraction results
- `{book_title}` - Book title
- `{author}` - Book author

**Example**:
```yaml
my_prompt:
  system: |
    You are analyzing legal contracts.
  user_template: |
    Analyze chapter {chapter_number} of "{book_title}":

    {paragraphs_json}
```

---

### outputs.yml

**Jinja2 Templates** for rendering markdown outputs:

```yaml
my_analysis_template: |
  # My Analysis: {book_title}

  ## Results

  {{% for item in results %}}
  - {item.name}: {item.value}
  {{% endfor %}}
```

---

## Dynamic Pydantic Model Generation

### How It Works

1. `schema_builder.py` reads `schema.yml`
2. Creates Pydantic `Field()` objects for each field
3. Uses `pydantic.create_model()` to build dynamic class
4. Returns model class that extends `BaseExtraction`

### Example Transformation

**Input** (`schema.yml`):
```yaml
extraction_model:
  name: LegalExtraction
  fields:
    - name: legalStandard
      type: str
      description: "Applicable legal standard"
      default: ""
```

**Generated Python Class**:
```python
class LegalExtraction(BaseExtraction):
    legal_standard: str = Field(default="", description="Applicable legal standard")
```

**Usage**:
```python
from ppke.parser.schema_builder import build_extraction_model

template = load_template('legal')
LegalExtraction = build_extraction_model(template.schema['extraction_model'])

result = LegalExtraction(
    paragraph_id="{01}.p1",
    original_text="...",
    topic_sentence="...",
    legal_standard="strict scrutiny"  # Template-specific field
)
```

---

## Security Considerations

### Validated Items
1. **No arbitrary code execution**: Prompts checked for `import os`, `import subprocess`
2. **Schema validation**: All fields must match supported types
3. **File path restrictions**: Templates cannot write outside vault
4. **YAML injection**: Only `yaml.safe_load()` used

### What's NOT Protected
- **Prompt injection**: Malicious prompts can instruct LLM to ignore instructions
- **Cost attacks**: Extremely long prompts could incur high API costs

**Recommendation**: Only install plugins from trusted sources.

---

## Testing Your Plugin

### Test Script Template

```python
# test_my_domain.py

from ppke.templates.loader import load_template
from ppke.parser.schema_builder import build_extraction_model

def test_my_domain_template():
    # Load template
    template = load_template('my_domain')

    assert template.name == 'my_domain'
    assert len(template.stages) >= 1

    # Build model
    ExtractionModel = build_extraction_model(template.schema['extraction_model'])

    # Instantiate
    result = ExtractionModel(
        paragraph_id="{01}.p1",
        original_text="Test",
        topic_sentence="Summary",
        my_field_1="test value"  # Your custom field
    )

    assert result.my_field_1 == "test value"

def test_prompt_loading():
    template = load_template('my_domain')
    from ppke.llm.prompts import load_prompt

    system, user = load_prompt(
        template,
        'extraction',
        format_vars={'chapter_number': 1, 'paragraphs_json': '[]'}
    )

    assert 'my domain' in system.lower()
    assert 'chapter 1' in user.lower()
```

**Run**:
```bash
$ pytest test_my_domain.py -v
```

---

**END OF PLUGINS.md**
```

---

## 🎯 TASK 3: CREATE EXAMPLE TIER 2 PLUGIN

### 3.1 Scientific Research Plugin

**Directory**: `~/.ppke/plugins/scientific_research/`

Create complete working plugin for scientific paper analysis.

**Files**:
- `template.yml`
- `schema.yml`
- `prompts.yml`
- `outputs.yml`
- `README.md`

**Schema fields**:
- `research_question`
- `methodology`
- `findings`
- `statistical_tests`
- `citations`
- `limitations`

(Full implementation omitted for brevity - follow philosophy template structure)

---

## 🎯 TASK 4: CREATE CLI COMMANDS

### 4.1 `ppke validate-plugin`

**File**: `ppke/cli.py`

```python
@cli.command()
@click.argument('plugin_path', type=click.Path(exists=True))
def validate_plugin(plugin_path):
    """Validate a custom plugin."""
    from ppke.templates.loader import load_template
    from pathlib import Path

    plugin_dir = Path(plugin_path)
    plugin_name = plugin_dir.name

    try:
        # Attempt to load
        template = load_template(plugin_name)

        console.print(f"✅ Plugin '{plugin_name}' is valid\n", style="green")
        console.print(f"  Name: {template.name}")
        console.print(f"  Version: {template.version}")
        console.print(f"  Tier: {template.tier}")
        console.print(f"  Author: {template.author}")
        console.print(f"  Stages: {len(template.stages)}")

        # Warnings
        for prompt_id, prompt in template.prompts.items():
            system_len = len(prompt.get('system', ''))
            if system_len > 5000:
                console.print(f"  ⚠️  Prompt '{prompt_id}' is very long ({system_len} chars)", style="yellow")

    except Exception as e:
        console.print(f"❌ Plugin validation failed: {e}", style="red")
        raise
```

---

### 4.2 `ppke promote-plugin` (Maintainer Only)

```python
@cli.command()
@click.argument('plugin_name')
@click.option('--force', is_flag=True, help='Skip confirmation')
def promote_plugin(plugin_name, force):
    """Promote a Tier 2 plugin to Tier 1 (official). Maintainer only."""
    import shutil
    from ppke.templates.loader import CUSTOM_TEMPLATES_DIR, OFFICIAL_TEMPLATES_DIR
    from ppke.templates.registry import get_plugin_info, register_plugin

    # Check if plugin exists in custom
    custom_path = CUSTOM_TEMPLATES_DIR / plugin_name
    if not custom_path.exists():
        console.print(f"❌ Plugin '{plugin_name}' not found in custom plugins", style="red")
        return

    # Load and validate
    template = load_template(plugin_name)
    if template.tier != 'custom':
        console.print(f"❌ Plugin is already Tier 1 (official)", style="red")
        return

    # Confirm
    if not force:
        confirm = click.confirm(f"Promote '{plugin_name}' to official?")
        if not confirm:
            console.print("Cancelled")
            return

    # Move to official
    official_path = OFFICIAL_TEMPLATES_DIR / plugin_name
    shutil.copytree(custom_path, official_path)

    # Update registry
    register_plugin(plugin_name, 'official', template.version, 'promoted', template.author)

    console.print(f"✅ Promoted '{plugin_name}' to Tier 1 (official)", style="green")
    console.print(f"  Moved: {custom_path} -> {official_path}")
```

---

## ✅ VALIDATION CRITERIA

### Plugin System
- [ ] `discover_templates()` finds both official and custom plugins
- [ ] Name conflicts resolved (official takes precedence)
- [ ] Plugin registry tracks all installed plugins

### Documentation
- [ ] `PLUGINS.md` complete and tested
- [ ] `TEMPLATE_DEVELOPMENT_GUIDE.md` technical and accurate
- [ ] Example plugin (`scientific_research`) works

### CLI Commands
- [ ] `ppke validate-plugin` catches invalid schemas
- [ ] `ppke promote-plugin` successfully moves plugins
- [ ] `ppke list-domains` shows tier badges

### Testing
- [ ] Create plugin from scratch following `PLUGINS.md`
- [ ] Validate plugin with `ppke validate-plugin`
- [ ] Ingest document with custom plugin
- [ ] Promote plugin to Tier 1

---

**END OF PHASE 3 METAPROMPT**

**Next**: Phase 4 - System Validation (`prompts/phase-4-system-validation.md`)
