# Test Coverage Plan — Road to >90%

**Current overall coverage: 74% (8291 stmts, 2156 missed)**
**Target: >90% (need to cover ~1330 more statements)**

---

## Module Coverage Summary (sorted by impact — uncovered lines)

| Module | Stmts | Miss | Cover | Gap to 90% |
|--------|-------|------|-------|------------|
| `ppke/web/app.py` | 1293 | 531 | 59% | ~402 lines |
| `ppke/cli.py` | 1237 | 296 | 76% | ~173 lines |
| `ppke/export/exporters.py` | 353 | 184 | 48% | ~149 lines |
| `ppke/converter/registry.py` | 247 | 112 | 55% | ~87 lines |
| `ppke/templates/installer.py` | 145 | 108 | 26% | ~94 lines |
| `ppke/parser/models_v1_backup.py` | 102 | 102 | 0% | backup file |
| `ppke/converter/ocr.py` | 107 | 92 | 14% | ~81 lines |
| `ppke/audio/overview.py` | 141 | 62 | 56% | ~49 lines |
| `ppke/graph/knowledge_graph.py` | 224 | 60 | 73% | ~38 lines |
| `ppke/pipeline/orchestrator.py` | 445 | 53 | 88% | ~9 lines |
| `ppke/pipeline/async_orchestrator.py` | 167 | 46 | 72% | ~30 lines |
| `ppke/auth/database.py` | 273 | 43 | 84% | ~16 lines |
| `ppke/audio/rss.py` | 66 | 40 | 39% | ~34 lines |
| `ppke/converter/url.py` | 68 | 43 | 37% | ~36 lines |
| `ppke/converter/youtube.py` | 69 | 37 | 46% | ~31 lines |
| `ppke/tui.py` | 188 | 37 | 80% | ~19 lines |
| `ppke/parser/schema_builder.py` | 62 | 34 | 45% | ~28 lines |
| `ppke/vectordb/store.py` | 140 | 34 | 76% | ~20 lines |
| `ppke/audio/transcriber.py` | 54 | 34 | 37% | ~29 lines |
| `ppke/infra/tasks.py` | 114 | 33 | 71% | ~22 lines |
| `ppke/templates/loader.py` | 63 | 22 | 65% | ~16 lines |
| `ppke/templates/validator.py` | 74 | 22 | 70% | ~15 lines |
| `ppke/llm/prompts.py` | 52 | 19 | 63% | ~14 lines |
| `ppke/infra/sentry_integration.py` | 87 | 18 | 79% | ~10 lines |
| `ppke/llm/prompts_v1_backup.py` | 16 | 16 | 0% | backup file |
| `ppke/templates/registry.py` | 56 | 15 | 73% | ~10 lines |
| `ppke/graph/analytics.py` | 204 | 12 | 94% | 0 (at target) |
| `ppke/export/academic.py` | 208 | 12 | 94% | 0 (at target) |
| `ppke/auth/deps.py` | 73 | 10 | 86% | ~3 lines |
| `ppke/auth/jwt_auth.py` | 79 | 8 | 90% | 0 (at target) |
| `ppke/templates/base.py` | 24 | 7 | 71% | ~5 lines |

---

## Phase 1 — High-Impact Web Routes (est. +8-10% coverage)

**Target files:**
- `ppke/web/app.py` — 59% → 90% (cover ~402 more lines)

**What's uncovered:**
- OAuth callback handlers (lines 225-234, 265-271, 292-308)
- Book upload & processing routes (lines 346-349, 387-388, 597-646)
- Chat/RAG routes with actual LLM calls (lines 665-753, 831-920)
- Study guide, glossary, flashcard generation (lines 939-1037)
- Literature review & argument map routes (lines 1058-1060, 1101-1109)
- Workspace CRUD deep paths (lines 1174-1213, 1229-1266)
- Annotation CRUD (lines 1312-1330, 1342-1387)
- Cost dashboard & usage routes (lines 1398-1454)
- Import/RSS routes (lines 1560-1616, 1622-1679)
- Settings update, template routes (lines 1911-1914, 1939)

**Approach:** Add more FastAPI TestClient tests with mocked DB and LLM dependencies. Focus on route-level behavior, not LLM output.

**Priority: CRITICAL** — This single file accounts for ~25% of all uncovered code.

---

## Phase 2 — CLI Module (est. +3-4% coverage)

**Target files:**
- `ppke/cli.py` — 76% → 90% (cover ~173 more lines)

**What's uncovered:**
- Various CLI subcommands not fully exercised
- Interactive prompts / TUI integration paths
- Error handling branches in CLI commands

**Approach:** Use Click's `CliRunner` with mocked file system, LLM client, and config. Test each subcommand with various flag combinations.

**Priority: HIGH** — Second largest source of uncovered code.

---

## Phase 3 — Export & Converter Modules (est. +4-5% coverage)

**Target files:**
- `ppke/export/exporters.py` — 48% → 90% (~149 lines)
- `ppke/converter/registry.py` — 55% → 90% (~87 lines)
- `ppke/converter/ocr.py` — 14% → 90% (~81 lines)
- `ppke/converter/url.py` — 37% → 90% (~36 lines)
- `ppke/converter/youtube.py` — 46% → 90% (~31 lines)

**What's uncovered:**
- **exporters.py**: DOCX/PPTX generation (requires python-docx, python-pptx), full PDF rendering pipeline, ZIP bundling with assets
- **registry.py**: PDF/EPUB/DOCX/PPTX/Excel converter branches, error paths
- **ocr.py**: Tesseract/EasyOCR/PaddleOCR backends, image preprocessing, PDF OCR pipeline
- **url.py**: Full URL scraping with trafilatura, fallback scraper, readability extraction
- **youtube.py**: yt-dlp integration, transcript download, duration filtering

**Approach:** Mock external tools (tesseract, yt-dlp, trafilatura) at the subprocess/import level. Test each converter format individually. Use `sys.modules` injection for optional dependencies.

**Priority: HIGH** — Combined ~384 uncovered lines.

---

## Phase 4 — Audio Module (est. +1-2% coverage)

**Target files:**
- `ppke/audio/overview.py` — 56% → 90% (~49 lines)
- `ppke/audio/rss.py` — 39% → 90% (~34 lines)
- `ppke/audio/transcriber.py` — 37% → 90% (~29 lines)

**What's uncovered:**
- **overview.py**: TTS synthesis (OpenAI/Edge-TTS), cross-book script generation deep paths
- **rss.py**: Full RSS feed parsing, episode download
- **transcriber.py**: Whisper local transcription, OpenAI transcription API

**Approach:** Mock TTS APIs, feedparser, whisper model. Test script generation and synthesis orchestration.

**Priority: MEDIUM** — ~112 lines total.

---

## Phase 5 — Templates & Infrastructure (est. +2-3% coverage)

**Target files:**
- `ppke/templates/installer.py` — 26% → 90% (~94 lines)
- `ppke/templates/loader.py` — 65% → 90% (~16 lines)
- `ppke/templates/validator.py` — 70% → 90% (~15 lines)
- `ppke/templates/registry.py` — 73% → 90% (~10 lines)
- `ppke/templates/base.py` — 71% → 90% (~5 lines)
- `ppke/infra/tasks.py` — 71% → 90% (~22 lines)
- `ppke/infra/sentry_integration.py` — 79% → 90% (~10 lines)

**What's uncovered:**
- **installer.py**: Git clone, pip install, file copy flows, emoji display, error recovery
- **loader.py**: Template discovery, YAML parsing, validation pipeline
- **validator.py**: Schema validation branches for each field type
- **tasks.py**: Redis job store operations, thread pool edge cases

**Approach:** Mock git/pip subprocess calls for installer. Test validator with various invalid schemas. Test task execution with mocked Redis.

**Priority: MEDIUM** — ~172 lines total.

---

## Phase 6 — Pipeline & Graph (est. +1-2% coverage)

**Target files:**
- `ppke/pipeline/async_orchestrator.py` — 72% → 90% (~30 lines)
- `ppke/pipeline/orchestrator.py` — 88% → 90% (~9 lines)
- `ppke/graph/knowledge_graph.py` — 73% → 90% (~38 lines)
- `ppke/parser/schema_builder.py` — 45% → 90% (~28 lines)

**What's uncovered:**
- **async_orchestrator.py**: Async chapter processing, progress callbacks, error recovery
- **orchestrator.py**: Edge cases in double-pass validation, resume logic
- **knowledge_graph.py**: Graph construction from extractions, Obsidian export
- **schema_builder.py**: Complex type parsing, nested model generation

**Approach:** Create test extractions and exercise graph building. Mock LLM for async orchestrator. Test schema builder with various template schemas.

**Priority: MEDIUM** — ~105 lines total.

---

## Phase 7 — Small Modules & Cleanup (est. +1% coverage)

**Target files:**
- `ppke/llm/prompts.py` — 63% → 90% (~14 lines)
- `ppke/tui.py` — 80% → 90% (~19 lines)
- `ppke/vectordb/store.py` — 76% → 90% (~20 lines)
- `ppke/auth/database.py` — 84% → 90% (~16 lines)
- `ppke/auth/deps.py` — 86% → 90% (~3 lines)

**What's uncovered:**
- **prompts.py**: Alternative prompt templates
- **tui.py**: Rich console display branches, progress bar edge cases
- **vectordb/store.py**: ChromaDB operations when available, search ranking
- **auth/database.py**: PostgreSQL-specific branches, edge cases in CRUD
- **auth/deps.py**: Edge cases in token extraction

**Approach:** Simple targeted unit tests for each uncovered branch.

**Priority: LOW** — ~72 lines total.

---

## Excluded from Coverage Target

These files are backup/legacy and can be excluded via `.coveragerc`:
- `ppke/parser/models_v1_backup.py` (102 lines, 0%) — legacy backup
- `ppke/llm/prompts_v1_backup.py` (16 lines, 0%) — legacy backup

**Recommendation:** Add to `.coveragerc` `omit` list to avoid inflating the gap.

---

## Pre-existing Test Failures (10 tests)

These failures exist in the repo before our work and are NOT related to coverage:
1. `test_architectural_features::TestVectorStoreDegradedMode` — `_CHROMA_AVAILABLE` attribute missing
2. `test_architectural_features::TestVectorSearchCommand` — same
3. `test_coverage_boost::test_main_runs_init_on_first_run` — exit code mismatch
4. `test_loop2_coverage` (4 tests) — orchestrator coverage validation failures
5. `test_providers` (3 tests) — init wizard exit code mismatches

---

## Execution Priority Summary

| Phase | Est. Coverage Gain | Effort | Lines to Cover |
|-------|-------------------|--------|----------------|
| Phase 1 — Web Routes | +8-10% | High | ~402 |
| Phase 2 — CLI | +3-4% | High | ~173 |
| Phase 3 — Export & Converters | +4-5% | Medium | ~384 |
| Phase 4 — Audio | +1-2% | Low | ~112 |
| Phase 5 — Templates & Infra | +2-3% | Medium | ~172 |
| Phase 6 — Pipeline & Graph | +1-2% | Medium | ~105 |
| Phase 7 — Small Modules | +1% | Low | ~72 |
| **Total** | **~20-27%** | | **~1420** |

**After completing Phases 1-5, we should reach ~90%+.**
Phases 6-7 provide buffer to ensure we comfortably exceed the target.
