"""Templates for global KnowledgeBase files."""

PROJECT_SETTINGS_TEMPLATE = """\
# PPKE Project Settings

## Configuration
- **Vault Path:** {vault_path}
- **LLM Provider:** {provider}
- **Model:** {model}
- **Selective Depth:** {selective_depth}
- **Double Pass:** {double_pass}

## Encoded Books
{book_list}

## Last Updated
{last_updated}
"""

MASTER_CONCEPT_INDEX_HEADER = """\
# Master Concept Index

Cross-book concept tracking. Each entry references:
```
Book_Folder_Name → {{CH}}.p{{P}}
```

---

"""

PLAYBOOK_TEMPLATE = """\
# PPKE Playbook

## Commands

### Ingest a Book
```bash
ppke ingest <book.md> --title "Title" --author "Author" --year YYYY
```

### Query a Single Book
```bash
ppke query --book "Book_Title_Author_YYYY" --question "Your question"
```

### Cross-Book Query
```bash
ppke cross-query --question "Your question"
```

### Configure
```bash
ppke config --provider anthropic --model claude-sonnet-4-20250514
ppke config --vault-path /path/to/vault
```

## File Structure

Each book produces:
- `meta.yml` - Book metadata
- `01_Raw_Structure.md` - Per-paragraph structural extraction
- `02_Logical_Map.md` - Argument architecture
- `03_Concept_Index.md` - Concept tracking with semantic drift
- `04_Author_Model.md` - Author's intellectual framework
- `05_Coverage_Report.md` - Completeness verification
"""
