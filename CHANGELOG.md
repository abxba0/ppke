# Changelog

All notable changes to PPKE (Personal & Professional Knowledge Engine) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.0.0] - 2026-03-01

### 🎉 Major Release: Full Web Platform & Multi-User Collaboration

This release transforms PPKE from a CLI-only tool into a **full-featured web platform** with 80+ API endpoints, multi-user support, document converters, audio features, and production deployment infrastructure.

#### Added

**Web GUI (Phase 1):**
- Full-featured web interface via `ppke serve` — dark mode, responsive design
- Server-Sent Events (SSE) streaming for real-time query responses
- Settings panel for LLM provider/model configuration in the browser
- Interactive notebook view with book exploration and chat

**Document Intelligence (Phase 2):**
- 23+ format support — PDF, DOCX, EPUB, HTML, images (OCR), and more
- URL import — ingest web pages directly as Markdown
- YouTube transcript extraction and ingestion
- Hybrid OCR with multi-script support (Latin, CJK, Arabic, Cyrillic, Devanagari)

**AI Chat & RAG (Phase 3):**
- Chat history persistence per book
- RAG-enhanced queries with vector DB retrieval
- AI-powered content generation: summaries, study guides, glossaries, flashcards
- Query suggestions based on book content

**Knowledge Graph Intelligence (Phase 4):**
- Graph analytics — clusters, shortest paths, gap analysis, contradiction detection
- Interactive graph visualization in the browser
- Export to Obsidian vault format and Markdown
- Semantic search across graph nodes

**Audio & Multimedia (Phase 5):**
- Audio overviews — podcast-style audio summaries of book analyses
- Cross-book audio — comparative podcast episodes for two books
- Podcast RSS import — download, transcribe, and ingest episodes
- In-browser voice recording with Whisper transcription
- Multiple voice presets and TTS providers

**Export & Content Generation (Phase 6):**
- PDF export with typeset reports (via WeasyPrint)
- DOCX export for Word-compatible documents
- PPTX export for presentation slides
- LLM-generated literature reviews across multiple books
- Argument map generation and export
- Bibliography management

**Multi-User & Collaboration (Phase 7):**
- JWT authentication with user registration and login
- OAuth support (Google, GitHub)
- Workspaces — create teams, invite members, assign roles
- Book sharing across workspace members
- Annotations on specific extractions
- Activity logging and audit trail
- API key management per user
- Usage tracking and rate limiting

**Infrastructure & Deployment (Phase 8):**
- Docker deployment with `docker-compose.yml` (app, PostgreSQL, Redis, Celery worker)
- Celery + Redis for background task processing
- PostgreSQL support for production databases (SQLite default for development)
- Prometheus metrics endpoint (`/metrics`)
- Sentry error tracking integration
- Cost dashboard for LLM usage monitoring
- Structured logging with request tracing
- S3/GCS cloud storage support
- Health check endpoint (`/api/health`)

**CI & Testing:**
- Comprehensive test suite with 91% code coverage (310+ tests)
- Updated CI matrix from Python 3.8/3.9/3.10 to 3.10/3.11/3.12 (matching `requires-python = ">=3.10"`)
- Expanded pylint configuration for clean 10.00/10 score

#### Changed
- Version bumped from 0.1.0 to 3.0.0
- Project description updated to "CLI + Web platform"
- Architecture expanded from CLI-only to web + CLI dual interface

#### Fixed
- Broken import `ppke.parser.markdown_parser` → `ppke.parser.markdown`
- Incorrect function reference `parse_markdown` → `parse_markdown_text`
- Exception chaining (`raise ... from e`) in all HTTP error handlers
- Removed redundant reimports and unused imports

---

## [2.0.0] - 2026-02-22

### 🎉 Major Release: Multi-Domain Knowledge Engine

This release transforms PPKE from a philosophy-specific tool into a **domain-agnostic knowledge extraction platform** while maintaining **100% backward compatibility** for philosophy analysis.

#### Added

**Core Features:**
- **Multi-domain support** - Analyze philosophy, legal, scientific, and custom domain texts
- **2-tier plugin system** (official + community templates)
- **Pydantic-based dynamic schemas** for type-safe data models
- **Template-driven prompts** for easy customization
- **Legal domain template** (official) with legal-specific fields:
  - `legal_standard`: Applicable legal standards
  - `case_references`: Referenced case law
  - `holding`: Court decisions and rulings
  - `statutory_citations`: Cited laws and statutes
- **Template system** for creating and managing domain templates

**New CLI Commands:**
- `ppke ingest --domain <name>` - Specify domain for ingestion (defaults to philosophy)
- `ppke list-domains` - Show available domain templates
- `ppke validate-plugin <path>` - Validate custom plugin structure
- `ppke promote-plugin <name>` - Promote community plugins to official status

**Performance Optimizations:**
- **Two-tier LLM architecture**: Use cheaper models for extraction, expensive for analysis
  - 83% cost reduction on typical workloads
  - Configurable via `--small-model` flag
- **Prompt caching**: 90% discount on cached tokens (Anthropic)
  - Automatic for supported providers
- **Parallel processing**: 4x speedup for multi-chapter extraction
  - Configurable worker count via `--max-workers`
- **Low-information paragraph detection**: Skip empty/boilerplate content
- **Citation stripping**: Remove footnotes and citations before analysis
- **Smart chapter skipping**: Auto-skip bibliographies, indexes, appendices

**Architectural Features:**
- **Progress tracking**: Persistent progress tracker with checkpoint/resume
- **Vector database integration**: Fast semantic search (optional, requires ChromaDB)
- **Knowledge graph**: Concept-level graph reasoning (optional, requires NetworkX)
- **Async ingestion pipeline**: Background processing with progress updates

**Testing & Quality:**
- Comprehensive test suite with 82%+ code coverage
- Template system validation tests
- Backward compatibility test suite
- Multi-provider LLM tests

#### Changed

**Data Models:**
- Refactored from dataclasses to Pydantic models
  - Better validation and type safety
  - JSON schema generation
  - Automatic field validation

**Prompts:**
- Moved from hardcoded `ppke/llm/prompts.py` to YAML templates
- Now loaded dynamically from template files
- Easier customization and community contributions

**Pipeline:**
- Pipeline dynamically loads stages from templates
- Support for custom stage modules
- Pluggable output generation

**Output Generation:**
- Template-driven rendering via Jinja2
- Customizable output files per domain
- Maintains v1.x output format for philosophy

**Configuration:**
- New field: `small_model` for two-tier LLM (optional)
- New field: `enable_cache` for prompt caching (default: true)
- Automatic migration from v1.x config format

#### Maintained

**100% Backward Compatibility for Philosophy Domain:**
- ✅ All v1.x CLI commands work unchanged
- ✅ Same vault structure (`Book_Title_Author_Year/`)
- ✅ Same output files (byte-for-byte compatible):
  - `01_Raw_Structure.md`
  - `02_Logical_Map.md`
  - `03_Concept_Index.md`
  - `04_Author_Model.md`
  - `05_Coverage_Report.md`
  - `06_Patterns.md`
  - `extractions.json`
  - `meta.yml`
- ✅ Same API key configuration (`.env` format)
- ✅ Same LLM provider support (Anthropic, OpenAI, DeepSeek, Gemini, OpenRouter)

**Philosophy Template Fields (v1.x Compatible):**
- `function_in_argument`
- `explicit_claims`
- `implicit_assumptions`
- `logical_steps`
- `emotional_tone`
- `tone_evidence`
- `defined_concepts`
- `internal_references`
- `is_argument_carrying`

#### Documentation

- **MIGRATION_GUIDE.md** - Comprehensive v1.x → v2.0 upgrade guide
- **PLUGINS.md** - Plugin development guide for custom domains
- **TEMPLATE_DEVELOPMENT_GUIDE.md** - Technical reference for templates
- **API_REFERENCE.md** - Updated API documentation
- **ARCHITECTURE_V2.md** - System architecture documentation
- Updated **README.md** with multi-domain examples

#### Fixed

- Pydantic validation errors in test suite
- File permission handling on Windows
- Template schema field naming consistency
- Memory leaks in parallel extraction
- Error handling in template loading

#### Security

- Template validation to prevent code injection
- Sandboxed template rendering
- API key security (not logged, proper .env handling)
- Input sanitization for user queries

#### Performance Benchmarks

**Cost Comparison** (300-page philosophy book):
- v1.x: ~$15.00 (all Claude Sonnet 4)
- v2.0 (two-tier): ~$2.50 (Haiku extraction + Sonnet analysis)
- **Savings: 83%**

**Speed Comparison** (same book, 4 workers):
- v1.x: ~45 minutes (sequential extraction)
- v2.0: ~12 minutes (parallel extraction)
- **Speedup: 3.75x**

---

## [1.9.0] - 2025-01-15 (Pre-v2.0 Release)

### Added
- Initial notebook command for synthesis queries
- TUI mode for interactive exploration
- Doctor command for health checks
- Cheat sheet command

### Changed
- Improved error messages and logging
- Better progress reporting during ingestion

### Fixed
- Various bug fixes and stability improvements

---

## [1.0.0] - 2024-06-01 (Initial Release)

### Added
- Core philosophy text analysis
- Structural extraction with 9 analytical dimensions
- Logical mapping of arguments
- Concept indexing and cross-referencing
- Pattern detection across chapters
- Author model generation
- Support for Anthropic Claude
- Basic configuration management
- Vault-based knowledge storage

---

## Version Numbering

PPKE follows [Semantic Versioning](https://semver.org/):
- **MAJOR** version (X.0.0): Incompatible API changes
- **MINOR** version (0.X.0): New features, backward compatible
- **PATCH** version (0.0.X): Bug fixes, backward compatible

### Compatibility Promise

- **Philosophy domain**: Always backward compatible across MINOR versions
- **CLI interface**: Breaking changes only in MAJOR versions
- **Data format**: Migrations provided for MAJOR versions
- **Template API**: Versioned independently, deprecated features supported for 1 year

---

## Upgrade Paths

### From v2.x to v3.0

```bash
# Install with web dependencies
pip install -e ".[web]"

# Start the web GUI
ppke serve
```

**Key additions:** Web GUI, document converters, audio, multi-user auth, Docker deployment.
**No breaking changes** to CLI commands or vault format.

### From v1.x to v2.0
See [MIGRATION_GUIDE.md](docs/user-guides/MIGRATION_GUIDE.md) for detailed instructions.

**TL;DR:**
```bash
pip install --upgrade ppke
ppke config --show  # Auto-migrates config
# Done! All v1.x commands work unchanged
```

---

## Deprecation Policy

PPKE follows a **1-year deprecation cycle**:

1. **Deprecated**: Feature marked as deprecated in release notes
2. **Warning**: Usage triggers deprecation warnings for 2 minor versions
3. **Removed**: Feature removed in next MAJOR version (minimum 1 year notice)

**Currently Deprecated:**
- None

---

## Roadmap

### Completed in v3.0 (Released)
- ✅ Web-based vault viewer & GUI
- ✅ Export to Obsidian/Notion/PDF/DOCX/PPTX
- ✅ Audio/video transcript analysis
- ✅ Real-time collaboration features
- ✅ Advanced analytics dashboard
- ✅ Cloud vault sync (S3/GCS)
- ✅ Enterprise features (JWT auth, activity logs)

### Planned for v3.1 (Q2 2026)
- Medical domain template
- Multi-language support
- Integration with academic databases (arXiv, PubMed)
- Plugin marketplace
- Batch processing for multiple books

---

## Community Contributions

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Contributors to v2.0:**
- PPKE Core Team
- Community template developers
- Beta testers and early adopters

---

## License

PPKE v3.0 is dual-licensed under the Apache License 2.0 and the PPKE Social Impact License.
See [DUAL-LICENSE.md](DUAL-LICENSE.md) for details.

---

## Support

- **Bug Reports**: [GitHub Issues](https://github.com/ppke/ppke/issues)
- **Feature Requests**: [GitHub Discussions](https://github.com/ppke/ppke/discussions)
- **Documentation**: [Read the Docs](https://ppke.readthedocs.io)
- **Community**: [Discord](https://discord.gg/ppke)

---

**Thank you for using PPKE!** 🎉
