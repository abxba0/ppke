# PPKE v1.x → v2.0 Migration Guide

**Version:** 2.0.0
**Last Updated:** 2026-02-21
**Target Audience:** Existing PPKE v1.x Users

---

## Table of Contents

1. [Overview](#overview)
2. [What's New in v2.0](#whats-new-in-v20)
3. [Breaking Changes](#breaking-changes)
4. [Backward Compatibility](#backward-compatibility)
5. [Migration Steps](#migration-steps)
6. [Configuration Migration](#configuration-migration)
7. [Data Format Changes](#data-format-changes)
8. [Command-Line Changes](#command-line-changes)
9. [Troubleshooting](#troubleshooting)
10. [Rollback Instructions](#rollback-instructions)

---

## Overview

PPKE v2.0 introduces a **domain-agnostic template system** while maintaining 100% backward compatibility for philosophy analysis. Existing v1.x users can upgrade seamlessly with zero changes to their workflows.

**Key Points:**
- ✅ **Zero Breaking Changes** for philosophy users
- ✅ **Automatic Config Migration** on first run
- ✅ **Same Output Files** (byte-for-byte compatible)
- ✅ **Same CLI Commands** (with new optional flags)
- ✅ **Data Compatibility** (existing vaults work as-is)

**Upgrade Time:** ~5 minutes
**Risk Level:** Low (fully reversible)

---

## What's New in v2.0

### 1. Template System
- **Multi-Domain Support:** Use PPKE for legal, scientific, medical documents
- **Plugin Architecture:** Install community templates
- **Customizable Workflows:** Create your own domain templates

### 2. Performance Improvements
- **Two-Tier LLM Architecture:** 83% cost reduction via small model for extraction
- **Prompt Caching:** 90% discount on cached tokens (Anthropic)
- **Parallel Processing:** 4x speedup for Skill 1

### 3. Enhanced Features
- **Template Management:** `ppke template list`, `ppke template install`
- **Better Progress Tracking:** More granular checkpoints
- **Improved Error Handling:** Better retry logic and error messages

### 4. Open Source
- **Apache 2.0 License:** Free for commercial use
- **Community Plugins:** Growing ecosystem of domain templates
- **Active Development:** Regular updates and community support

---

## Breaking Changes

### For Philosophy Users: **NONE**

PPKE v2.0 maintains 100% backward compatibility for philosophy analysis. All v1.x workflows continue to work without modification.

### For Advanced Users/API Consumers

If you've built custom integrations on top of PPKE internals:

1. **Python API Changes:**
   - `ppke.llm.prompts` module → Prompts now in templates
   - Direct dataclass imports → Use `template.get_extraction_schema()`

2. **Internal File Structure:**
   - New: `template_metadata.json` in vault directories
   - Existing files unchanged

3. **Configuration Schema:**
   - New field: `template_name` (defaults to "philosophy")

---

## Backward Compatibility

### What Stays the Same

✅ **All CLI Commands:**
```bash
# v1.x commands (still work in v2.0)
ppke ingest ~/Documents/being-and-time.md
ppke query "What is Dasein?"
ppke analyze --skill concepts Book_Title
ppke notebook "Heidegger's ontology"
ppke menu
```

✅ **Output Files:**
```
Book_Title/
├── 01_Raw_Structure.md      # Same format
├── 02_Logical_Map.md         # Same format
├── 03_Concept_Index.md       # Same format
├── 04_Author_Model.md        # Same format
├── 05_Coverage_Report.md     # Same format
├── 06_Patterns.md            # Same format
└── extractions.json          # Same schema
```

✅ **Configuration:**
```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4"
  },
  "vault_path": "~/KnowledgeBase"
}
```

### What's New (Optional)

🆕 **Domain Selection:**
```bash
# Explicit domain selection (optional, defaults to philosophy)
ppke ingest --domain philosophy ~/Documents/being-and-time.md

# Use different domain
ppke ingest --domain legal ~/Documents/contract.pdf
```

🆕 **Template Management:**
```bash
ppke template list                # Show installed templates
ppke template install <url>       # Install community template
ppke template validate <path>     # Validate template structure
```

---

## Migration Steps

### Step 1: Backup (Recommended)

```bash
# Backup your config
cp ~/.ppke/config.json ~/.ppke/config.json.backup

# Backup your vault (if using local storage)
cp -r ~/KnowledgeBase ~/KnowledgeBase.backup
```

### Step 2: Upgrade PPKE

```bash
# Using pip
pip install --upgrade ppke

# Or using pipx
pipx upgrade ppke

# Verify version
ppke --version
# Expected: ppke version 2.0.0
```

### Step 3: Automatic Config Migration

On first run, PPKE v2.0 automatically migrates your configuration:

```bash
# Run any command
ppke config --show
```

**Migration Process:**
1. Detects v1.x config format
2. Adds `template_name: "philosophy"` field
3. Preserves all existing settings
4. Creates `config.json.v1.backup`

**Output:**
```
✓ Configuration migrated to v2.0
✓ Backup saved: ~/.ppke/config.json.v1.backup
✓ Using template: philosophy (default)
```

### Step 4: Verify Migration

```bash
# Check config
ppke config --show

# Expected output includes:
# template_name: philosophy
```

### Step 5: Test with Existing Vault

```bash
# Ingest a document (should work exactly as before)
ppke ingest ~/Documents/test-document.md

# Query existing vault (should work as before)
ppke query "test query"
```

**That's it!** You're now running PPKE v2.0.

---

## Configuration Migration

### v1.x Config Format

```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 4096,
    "temperature": 0.2,
    "paragraphs_per_batch": 5,
    "max_workers": 4
  },
  "vault_path": "/home/user/KnowledgeBase",
  "enable_vector_db": false,
  "enable_graph": false
}
```

### v2.0 Config Format (Auto-Migrated)

```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "small_model": null,           // NEW: Optional cheaper model
    "max_tokens": 4096,
    "temperature": 0.2,
    "paragraphs_per_batch": 5,
    "max_workers": 4
  },
  "vault_path": "/home/user/KnowledgeBase",
  "template_name": "philosophy",   // NEW: Defaults to philosophy
  "enable_vector_db": false,
  "enable_graph": false,
  "enable_cache": true             // NEW: Prompt caching
}
```

### New Configuration Options

**Two-Tier LLM (Cost Optimization):**
```bash
# Use cheap model for extraction, expensive for analysis
ppke config --small-model claude-haiku-3-5-20241022

# Cost comparison (300-page book):
# v1.x:  $15.00 (all claude-sonnet-4)
# v2.0:  $2.50  (haiku for extraction, sonnet for analysis)
```

**Domain Selection:**
```bash
# Default domain is philosophy (no config needed)

# Override per-command
ppke ingest --domain legal contract.pdf
```

---

## Data Format Changes

### Philosophy Template: 100% Compatible

All output files remain identical to v1.x:

| File | v1.x | v2.0 | Changes |
|------|------|------|---------|
| `01_Raw_Structure.md` | ✅ | ✅ | None |
| `02_Logical_Map.md` | ✅ | ✅ | None |
| `03_Concept_Index.md` | ✅ | ✅ | None |
| `04_Author_Model.md` | ✅ | ✅ | None |
| `05_Coverage_Report.md` | ✅ | ✅ | None |
| `06_Patterns.md` | ✅ | ✅ | None |
| `extractions.json` | ✅ | ✅ | Schema unchanged |
| `meta.yml` | ✅ | ✅ | None |

### New Files (Optional, Template-Specific)

```
Book_Title/
├── template_metadata.json    // NEW: Records template version
└── ... (all v1.x files unchanged)
```

**template_metadata.json:**
```json
{
  "template_name": "philosophy",
  "template_version": "2.0.0",
  "ppke_version": "2.0.0",
  "ingestion_date": "2026-02-21T10:30:00Z"
}
```

**Note:** This file is informational only and doesn't affect functionality.

---

## Command-Line Changes

### All v1.x Commands Still Work

| v1.x Command | v2.0 Status | Notes |
|--------------|-------------|-------|
| `ppke init` | ✅ Works | Now asks for template preference |
| `ppke ingest` | ✅ Works | New: `--domain` flag (optional, defaults to philosophy) |
| `ppke query` | ✅ Works | Unchanged |
| `ppke analyze` | ✅ Works | Unchanged |
| `ppke notebook` | ✅ Works | Unchanged |
| `ppke menu` | ✅ Works | Shows template info |
| `ppke config` | ✅ Works | Unchanged |
| `ppke cheat` | ✅ Works | Updated with new commands |
| `ppke doctor` | ✅ Works | Validates template config |
| `ppke tui` | ✅ Works | Shows active template |

### New Commands in v2.0

```bash
# Template management
ppke template list                    # List installed templates
ppke template install <url>           # Install from GitHub
ppke template install <path>          # Install from local directory
ppke template validate <path>         # Validate template structure
ppke template info <name>             # Show template details

# Advanced (for maintainers)
ppke promote-plugin <name>            # Promote Tier 2 → Tier 1
```

---

## Troubleshooting

### Issue: "Template 'philosophy' not found"

**Cause:** Template system not initialized.

**Fix:**
```bash
# Reinstall PPKE
pip install --force-reinstall ppke

# Verify templates
ppke template list
# Should show: philosophy (official)
```

---

### Issue: Output files different from v1.x

**Cause:** Wrong template selected.

**Fix:**
```bash
# Check active template
ppke config --show | grep template_name

# Should show: Default domain is philosophy
```

---

### Issue: Performance degradation

**Cause:** Not using two-tier LLM architecture.

**Fix:**
```bash
# Enable two-tier (83% cost reduction)
ppke config --small-model claude-haiku-3-5-20241022

# Verify
ppke config --show | grep small_model
```

---

### Issue: Config migration failed

**Cause:** Corrupted config file.

**Fix:**
```bash
# Restore backup
cp ~/.ppke/config.json.backup ~/.ppke/config.json

# Or reinitialize
rm ~/.ppke/config.json
ppke init
```

---

### Issue: Existing vault not recognized

**Cause:** Vault path changed.

**Fix:**
```bash
# Check vault path
ppke config --show | grep vault_path

# Update if needed
ppke config --vault-path ~/KnowledgeBase
```

---

## Rollback Instructions

If you need to revert to v1.x:

### Step 1: Uninstall v2.0

```bash
pip uninstall ppke
```

### Step 2: Install v1.x

```bash
pip install ppke==1.9.0  # Replace with your v1.x version
```

### Step 3: Restore Config (if needed)

```bash
# Restore v1.x config
cp ~/.ppke/config.json.v1.backup ~/.ppke/config.json
```

### Step 4: Verify

```bash
ppke --version
# Should show: ppke version 1.9.0 (or your version)
```

**Note:** All data in your vault remains compatible with v1.x (no data loss).

---

## FAQ

### Q: Do I need to re-ingest my existing books?
**A:** No. All existing vault data is fully compatible with v2.0.

### Q: Will my custom scripts break?
**A:** Only if they import internal PPKE modules (e.g., `ppke.llm.prompts`). CLI usage is 100% backward compatible.

### Q: Can I use v2.0 templates with v1.x data?
**A:** Yes. Templates are additive; philosophy template works with all v1.x vaults.

### Q: What if I want to try other templates?
**A:** Install community templates (when available), then use `--domain <name>` flag. Your philosophy workflow is unaffected.

### Q: Is there a performance difference?
**A:** v2.0 is faster (4x parallel extraction) and cheaper (83% cost reduction with two-tier LLM).

### Q: Can I run v1.x and v2.0 side-by-side?
**A:** Not recommended. Use virtual environments if needed:
```bash
# v1.x environment
python -m venv ppke-v1
source ppke-v1/bin/activate
pip install ppke==1.9.0

# v2.0 environment
python -m venv ppke-v2
source ppke-v2/bin/activate
pip install ppke==2.0.0
```

---

## Getting Help

**Community Support:**
- GitHub Issues: https://github.com/ppke/ppke/issues
- Discussions: https://github.com/ppke/ppke/discussions
- Wiki: https://github.com/ppke/ppke/wiki

**Documentation:**
- Full Docs: https://ppke.readthedocs.io
- Migration FAQ: https://github.com/ppke/ppke/wiki/Migration-FAQ
- Video Tutorial: [Coming Soon]

**Direct Support:**
- Email: support@ppke.dev
- Discord: https://discord.gg/ppke (community)

---

## Conclusion

Upgrading to PPKE v2.0 is seamless for existing users while unlocking powerful new capabilities. The philosophy template ensures zero disruption to your workflow, while the template system opens doors to new knowledge domains.

**Next Steps:**
1. ✅ Follow [Migration Steps](#migration-steps)
2. 🚀 Explore new features (template system, cost optimization)
3. 🌟 Try community templates for other domains
4. 💬 Share feedback and join the community

**Welcome to PPKE v2.0!** 🎉

---

---
---

# PPKE v2.0 → v3.0 Migration Guide

**Version:** 3.0.0
**Last Updated:** 2025-07-17
**Target Audience:** Existing PPKE v2.x Users

---

## Overview

PPKE v3.0 adds a **full-featured web GUI**, multi-user authentication, AI chat, knowledge graphs, audio overviews, and production infrastructure — while preserving 100% backward compatibility for CLI workflows.

**Key Points:**
- ✅ **Zero Breaking CLI Changes** — all v2.x commands work identically
- ✅ **Web GUI is Optional** — install only if you want it
- ✅ **Same Output Formats** — existing vaults and exports unchanged
- ✅ **New Optional Dependencies** — modular extras for web, OCR, audio
- ✅ **Docker Deployment** — production-ready with one command

**Upgrade Time:** ~2 minutes
**Risk Level:** Low (CLI fully backward-compatible)

---

## What's New in v3.0

| Feature | Description |
|---------|-------------|
| **Web GUI** | FastAPI + Jinja2 + HTMX dashboard with 80+ API endpoints |
| **Document Intelligence** | URL/YouTube/RSS ingestion, OCR, content conversion |
| **AI Chat** | Streaming chat with citation-backed answers per book |
| **Knowledge Graph** | Interactive concept visualization with D3.js |
| **Audio Overviews** | Podcast-style audio summaries via TTS |
| **Export Suite** | PDF, DOCX, PPTX export with academic citations |
| **Multi-User Auth** | JWT authentication, roles, workspaces |
| **Infrastructure** | Celery task queue, Redis cache, Sentry monitoring, S3 storage |

---

## Breaking Changes

### For CLI Users: **NONE**

All v2.x CLI commands continue to work without modification:
```bash
ppke ingest book.md --title "..." --author "..."
ppke query --book "..." --question "..."
ppke template list
```

### For Python API Consumers

If you import from `ppke.parser`:
```python
# v2.x
from ppke.parser.models import BookAnalysis

# v3.0 — same import still works
from ppke.parser.models import BookAnalysis
```

No internal API changes affect existing integrations.

---

## Migration Steps

### Step 1: Update Installation

```bash
# CLI only (same as before)
pip install -e .

# With web GUI
pip install -e ".[web]"

# With all features
pip install -e ".[web,ocr,audio]"
```

### Step 2: Try the Web GUI (Optional)

```bash
# Start the web server
ppke serve

# Open in browser
open http://localhost:8000
```

### Step 3: Docker Deployment (Optional)

For production with PostgreSQL, Redis, and Celery:

```bash
docker-compose up -d
```

---

## New CLI Commands

| Command | Description |
|---------|-------------|
| `ppke serve` | Start the web GUI server |

All existing commands (`ingest`, `query`, `template`, `init`, `config`) remain unchanged.

---

## Optional Dependencies

v3.0 uses a modular extras system. You only install what you need:

| Extra | Install Command | What It Adds |
|-------|----------------|--------------|
| _(none)_ | `pip install -e .` | CLI-only (same as v2.x) |
| `web` | `pip install -e ".[web]"` | Web GUI, FastAPI, Jinja2 |
| `ocr` | `pip install -e ".[ocr]"` | PDF/image OCR (pytesseract) |
| `audio` | `pip install -e ".[audio]"` | Audio generation (gTTS, pydub) |
| `dev` | `pip install -e ".[dev]"` | Testing and linting tools |

---

## Python Version

v3.0 requires **Python ≥ 3.10** (same as v2.x). The CI matrix now tests against Python 3.10, 3.11, and 3.12.

---

## Environment Variables (New, Optional)

These are only needed if you use the web GUI or Docker deployment:

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECRET_KEY` | JWT signing secret | Auto-generated |
| `DATABASE_URL` | PostgreSQL connection | SQLite (local) |
| `REDIS_URL` | Redis for caching/tasks | In-memory cache |
| `SENTRY_DSN` | Error monitoring | Disabled |
| `S3_BUCKET` | Cloud storage | Local filesystem |

---

## Rollback

To return to v2.x behavior, simply don't install web extras and don't run `ppke serve`. The CLI works identically to v2.x.

---

**Document Version:** 2.0
**Last Updated:** 2025-07-17
**Maintained By:** PPKE Core Team
