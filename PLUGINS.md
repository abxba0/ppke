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

  {% for concept in concepts %}
  ## {concept.name}
  **Occurrences**: {concept.occurrences}
  {% endfor %}
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
