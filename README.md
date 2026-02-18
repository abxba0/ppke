# PPKE - Personal Philosophical Knowledge Engine

A CLI tool for structured philosophical book analysis. PPKE ingests markdown books, extracts their logical structure using LLMs, and builds a queryable knowledge base with full verbatim fidelity.

## Features

- **Structural Extraction** - Parses books into chapters and paragraphs, extracts claims, arguments, and concepts via LLM
- **Sub-Paragraph Splitting** - Automatically splits long paragraphs into sub-paragraphs (`{03}.p12.1`, `{03}.p12.2`) when they exceed token limits
- **Parallel Extraction** - Multi-threaded chapter extraction for faster ingestion of large books
- **Coverage Validation** - Ensures 100% paragraph coverage with automatic re-read on gaps
- **Interactive Re-Read** - User-triggered re-scan of specific chapters after ingestion
- **Logical Architecture** - Maps argument chains and inferential connections across chapters
- **Concept Indexing** - Tracks concept definitions, evolution, and cross-references
- **Semantic Deduplication** - Master Concept Index groups semantically equivalent concepts across books using LLM matching (not just string matching)
- **Pattern Detection** - Identifies rhetorical strategies, dialectical tensions, and recurring structures
- **Cross-Book Synthesis** - Compares and contrasts ideas across multiple encoded books
- **Single-Book Querying** - Ask questions about any ingested book with verbatim evidence

## Quick Start

### 1. Install

```bash
pip install -e .
```

### 2. First-Time Setup

Run the setup wizard on first launch:

```bash
ppke init
```

This will walk you through:
- Choosing your LLM provider (Anthropic or OpenAI)
- Entering your API key (stored securely in `~/.ppke/.env` with `chmod 600`)
- Setting the knowledge base directory
- Configuring batch size

If you just run `ppke` without any command on a fresh install, the setup wizard starts automatically.

### 3. Ingest a Book

```bash
ppke ingest book.md --title "Being and Time" --author "Heidegger" --year 1927
```

Long paragraphs are automatically split into sub-paragraphs. Chapters are extracted in parallel for faster processing.

### 4. Query

```bash
# Single book
ppke query --book "Book_Being_and_Time_Heidegger_1927" --question "What is Dasein?"

# Across all books
ppke cross-query --question "How do these authors differ on free will?"
```

### 5. Re-Read Specific Chapters

```bash
ppke re-read --book "Book_Being_and_Time_Heidegger_1927" --chapters "1,3,5"
```

## Commands

| Command | Description |
|---------|-------------|
| `ppke init` | First-time setup wizard (API keys, provider, vault path) |
| `ppke ingest <file>` | Ingest a markdown book into the knowledge base |
| `ppke parse <file>` | Dry-run parse (shows structure, no LLM calls) |
| `ppke query` | Query a single ingested book |
| `ppke cross-query` | Query across all ingested books |
| `ppke re-read` | Re-extract specific chapters from an ingested book |
| `ppke config` | View or update configuration |

## Configuration

### Setup Wizard (`ppke init`)

The recommended way to configure PPKE. Interactively prompts for all settings and securely stores API keys.

### Manual Configuration

**API keys** - set via environment variables or `~/.ppke/.env`:

```bash
# Option A: environment variable
export ANTHROPIC_API_KEY=sk-ant-...

# Option B: stored in ~/.ppke/.env (created by ppke init)
# File is chmod 600, never committed to git
```

**Settings** - view and update via CLI:

```bash
ppke config --show
ppke config --provider openai --model gpt-4o
ppke config --vault-path ~/my-vault
ppke config --batch-size 10
```

Config file: `~/.ppke/config.json`

### Options for `ppke ingest`

| Flag | Description |
|------|-------------|
| `--title` | Book title (required) |
| `--author` | Book author (required) |
| `--year` | Publication year |
| `--provider` | Override LLM provider (`anthropic` / `openai`) |
| `--model` | Override model name |
| `--vault-path` | Override output directory |
| `--batch-size` | Paragraphs per LLM batch |
| `--operator` | Human operator name for versioning |
| `--double-pass` | Enable double-pass extraction for verification |
| `-v, --verbose` | Verbose logging |

### Advanced Config Options

| Setting | Default | Description |
|---------|---------|-------------|
| `max_paragraph_tokens` | 2000 | Split paragraphs exceeding this token count |
| `max_workers` | 4 | Parallel extraction threads |
| `paragraphs_per_batch` | 5 | Paragraphs sent per LLM call |

## Project Structure

```
ppke/
├── cli.py               # CLI entry point (Click)
├── config.py            # Configuration & .env management
├── parser/
│   ├── models.py        # Data models (Book, Chapter, Paragraph, etc.)
│   └── markdown.py      # Markdown parsing + sub-paragraph splitting
├── llm/
│   ├── client.py        # Unified Anthropic/OpenAI client
│   └── prompts.py       # Prompt templates for all pipeline stages
├── pipeline/
│   ├── orchestrator.py  # Master controller (parallel extraction, re-read)
│   ├── extractor.py     # Structural extraction (Skill 1)
│   ├── validator.py     # Coverage validation (Skill 2)
│   ├── logical_map.py   # Logical architecture (Skill 3)
│   ├── concepts.py      # Concept indexing (Skill 4)
│   ├── patterns.py      # Pattern detection (Skill 5)
│   └── synthesizer.py   # Cross-book synthesis (Skill 6)
├── output/
│   ├── writer.py        # File generation + semantic deduplication
│   └── templates.py     # Output templates
└── tests/
    ├── test_parser.py
    └── test_validator.py
```

## Output Structure

Each ingested book creates a folder in the vault:

```
~/KnowledgeBase/
├── 00_PROJECT_SETTINGS.md      # Global config
├── MASTER_CONCEPT_INDEX.md     # Cross-book concepts (semantically deduplicated)
├── QA_RESULTS.md               # Coverage status
├── PLAYBOOK.md                 # Usage guide
└── Book_Being_and_Time_Heidegger_1927/
    ├── meta.yml                # Book metadata
    ├── 01_Raw_Structure.md     # Full extraction
    ├── 02_Logical_Map.md       # Argument architecture
    ├── 03_Concept_Index.md     # Concept tracking
    ├── 04_Author_Model.md      # Author analysis
    └── 05_Coverage_Report.md   # Validation report
```

## Requirements

- Python >= 3.10
- An API key for [Anthropic](https://console.anthropic.com/settings/keys) or [OpenAI](https://platform.openai.com/api-keys)

## Development

```bash
pip install -e ".[dev]"
pytest ppke/tests/
```

## License

Private project.
