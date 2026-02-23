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

  {% for item in results %}
  - {item.name}: {item.value}
  {% endfor %}
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

**END OF TEMPLATE_DEVELOPMENT_GUIDE.md**
