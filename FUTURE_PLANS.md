# PPKE Development Roadmap

> **Last Updated:** 2026-02-28
> **Current Version:** 3.0.0

---

## Phase 0 — Foundation (DONE)

Everything built in the initial session to transform PPKE from CLI-only to a full web platform.

- [x] **FastAPI web server** (`ppke/web/app.py`) — 15+ REST endpoints, Jinja2 templates, HTMX
- [x] **Dashboard** — Library grid, stats cards, book metadata
- [x] **Notebook view** — Tabbed interface (Chat, Structure, Concepts, Logical Map, Patterns)
- [x] **Upload page** — Drag-and-drop, format detection, background ingestion with progress
- [x] **Knowledge graph** — D3.js force-directed graph (Obsidian-style), zoom/pan, filtering
- [x] **Document converters** (`ppke/converter/`) — PDF, DOCX, EPUB, HTML, PPTX, images (OCR), audio
- [x] **Audio module** (`ppke/audio/`) — Whisper transcription, NotebookLM-style podcast generation
- [x] **CLI integration** — `ppke serve` command
- [x] **Dependencies** — `[web]`, `[ocr]`, `[audio]` optional groups in pyproject.toml

---

## Phase 1 — Web GUI Polish & Production Readiness (DONE)

All the things that make the web GUI feel like a real product instead of a prototype.

- [x] **Dark mode** — Toggle with localStorage persistence, system preference detection, all 6 templates updated
- [x] **Markdown rendering** — marked.js in chat bubbles with code highlighting, blockquotes, lists
- [x] **SSE streaming** — `/api/query/stream` endpoint, real-time token-by-token chat responses
- [x] **Toast notifications** — Success/error/info/warning toasts replacing all `alert()` calls
- [x] **Keyboard shortcuts** — `Ctrl+K` search, `Ctrl+U` upload, `Ctrl+H` home, `Ctrl+D` dark mode, `?` help modal, `Esc` close
- [x] **Settings page** — `/settings` with provider, model, API key, domain, vector/graph toggles, live save
- [x] **Error handling middleware** — Catch-all exception handler, validation error formatter, clean JSON errors
- [x] **Path traversal protection** — Regex validation on all folder parameters, `..` blocking, filename sanitization
- [x] **Mobile responsive** — Hamburger menu, responsive grid breakpoints, touch-friendly controls
- [x] **Graph dark mode** — All graph UI elements (tooltip, legend, controls, labels) dark-mode aware

### What this unlocked
The web GUI is now a complete, polished single-user application. You can run `ppke serve`, open it in a browser, upload documents, chat with books, explore the concept graph, generate audio overviews, and configure settings — all with proper dark mode, real-time streaming, and keyboard navigation.

---

## Phase 2 — Document Intelligence (DONE)

Make the converter pipeline smarter and support more input sources.

### 2.1 New Input Sources
- [x] **URL scraping** — `ppke/converter/url.py`: `convert_url()` uses `trafilatura`; BeautifulSoup fallback; auto-detects YouTube
- [x] **YouTube import** — `ppke/converter/youtube.py`: `convert_youtube()` downloads audio via `yt-dlp`, transcribes via Whisper, prepends video metadata
- [x] **LaTeX** — `@register(".tex")` in registry: pandoc subprocess → regex fallback; strips preamble, maps `\section` to headings
- [x] **CSV** — `@register(".csv")` in registry: stdlib `csv` → Markdown table (max 500 rows)
- [x] **Excel** — `@register(".xlsx")` / `@register(".xls")`: `openpyxl` → one Markdown table section per sheet

### 2.2 OCR Improvements
- [x] **Hybrid OCR** — `ocr_image()` and `ocr_pdf_pages()`: Tesseract first → Vision LLM (Claude/GPT-4o) fallback when confidence < 55
- [x] **Confidence scoring** — `_tesseract_with_confidence()` returns `(text, mean_confidence)`; low-confidence pages annotated with `<!-- OCR confidence: N% -->`
- [x] **Language detection** — `_detect_language()` uses Tesseract OSD; maps script → language code; detected language reused across all pages of a PDF
- [ ] **Table detection** — Preserve table structure from PDFs as Markdown tables *(deferred to Phase 4)*
- [ ] **Image preprocessing** — Deskew, denoise, contrast enhancement with OpenCV *(deferred)*

### 2.3 Batch Processing
- [x] **Multi-file upload** — `/api/upload` now accepts `files: list[UploadFile]`; one job per file; returns `{"jobs": [...]}` for batch
- [x] **Queue system** — Batch progress UI in upload.html: per-file job row with spinner → green checkmark + Open link
- [x] **ZIP upload** — `@register(".zip")` in registry: extracts to tempdir, converts each supported member, concatenates Markdown
- [ ] **Smart chapter detection** — Use PDF bookmarks/TOC for chapter splitting *(deferred to Phase 3)*

### New Endpoints
- `POST /api/import-url` — accepts `url`, auto-detects YouTube vs web page, starts background ingestion job

### New UI
- Upload page redesigned with three tabs: **File Upload**, **From URL**, **Batch Upload**
- YouTube URL auto-detection badge (red YouTube icon appears when URL matches)
- Batch file queue preview list with file sizes
- Shared polling UI with per-job spinners → checkmarks

### New Dependencies (`[ingest]`)
- `trafilatura>=1.6.0` — article extraction
- `requests>=2.31.0` — HTTP fallback
- `yt-dlp>=2024.1.0` — YouTube audio download
- `openpyxl>=3.1.0` — Excel support

---

## Phase 3 — AI Chat Enhancements (DONE)

Make the query engine significantly smarter.

### 3.1 Conversation Memory
- [x] **Multi-turn chat** — `chat_history.json` per book; `_load_history()` + `_save_history()`; last 6 turns injected as `CONVERSATION HISTORY` block into every query prompt
- [x] **Follow-up suggestions** — LLM asked to include `follow_up_questions:[...]` in JSON; sent as SSE `suggestions` event; rendered as clickable chip buttons below each answer
- [x] **Query templates** — 5 pre-built template chips in chat toolbar: "Summarize this book", "Key claims", "Main concepts", "Open questions", "Strongest argument"

### 3.2 RAG Pipeline
- [x] **Vector-enhanced queries** — `_rag_context_block()` calls `VectorStore.search(question, book_filter=folder)`; top-5 hits prepended to prompt as `SEMANTICALLY RELEVANT PASSAGES` block; degrades gracefully when ChromaDB unavailable
- [x] **Sources badge** — `sources` SSE event; rendered as "N vector sources used" indigo badge on assistant bubble
- [x] **Citation jump** — Clicking a paragraph ID in quotes switches to Structure tab
- [ ] **Hybrid search** — Full-text + vector combined retrieval *(deferred to Phase 4)*

### 3.3 Content Generation
- [x] **Executive summaries** — `POST /api/summary/{folder}` generates via LLM (cached `summary.md`); `GET` serves it; "Generate" button in Summary tab with Markdown rendering
- [x] **Flashcard generation** — `GET /api/flashcards/{folder}` → Anki-importable TSV (concept→definition+pid); download button in book header
- [x] **Study guide** — `POST /api/study-guide/{folder}` → chapter-by-chapter notes via LLM (cached `study_guide.md`); Study Guide tab with "Generate" button
- [x] **Glossary** — `GET /api/glossary/{folder}` → built from `extractions.json` (no LLM); searchable table in Glossary tab with paragraph ID jump links

### New Endpoints (7)
`GET/DELETE /api/history/{folder}` · `GET/POST /api/summary/{folder}` · `GET/POST /api/study-guide/{folder}` · `GET /api/glossary/{folder}` · `GET /api/flashcards/{folder}`

### New UI (notebook.html)
8 tabs · query template chips · follow-up suggestion chips · clear history button · RAG badge · flashcards download

---

## Phase 4 — Knowledge Graph Intelligence (DONE)

Make the graph view a real analytical tool, not just visualization.

### 4.1 Graph Features
- [x] **Search within graph** — Fuzzy search in sidebar with autocomplete; `focusNode()` zooms + highlights with gold border (2.5s auto-reset)
- [x] **Cluster detection** — Louvain community detection via `networkx.community.louvain_communities()`; "Color by Cluster" toggle in sidebar; 15-color palette
- [x] **Edge labels on hover** — Hovering any link shows "Source **relation** Target" tooltip + bold stroke; relation text rendered at link midpoint
- [x] **Path finder** — Two concept inputs + autocomplete; `nx.shortest_path()`; renders path as colored node chips with "→ relation →" edges; highlights path in graph for 6s
- [x] **Export** — JSON download, PNG (canvas 2× retina), Obsidian vault ZIP (all via buttons in header)

### 4.2 Graph Analytics
- [x] **Centrality analysis** — PageRank + betweenness centrality on concept nodes; top-10 shown in sidebar with clickable bars; `ppke/graph/analytics.py`
- [x] **Gap detection** — Concepts in 2+ books with no concept↔concept edges; listed in sidebar with book counts
- [x] **Contradiction detection** — All `contradicts` edges shown in sidebar with red labels
- [ ] **Temporal view** — Timeline slider *(deferred — requires year metadata on edges)*

### 4.3 External Integration
- [x] **Obsidian export** — `GET /api/graph/obsidian-export` → ZIP with one `.md` per concept, `[[wikilinks]]` for related concepts, book sources
- [x] **Markdown graph export** — `GET /api/graph/markdown-export` → ZIP with interlinked Markdown files

### New Module: `ppke/graph/analytics.py`
Standalone analytics functions: `search_nodes()`, `compute_clusters()`, `compute_centrality()`, `find_shortest_path()`, `detect_gaps()`, `detect_contradictions()`, `obsidian_vault_zip()`, `markdown_export_zip()`

### New Endpoints (8)
`GET /api/graph/search` · `GET /api/graph/clusters` · `GET /api/graph/analytics` · `GET /api/graph/path` · `GET /api/graph/gaps` · `GET /api/graph/contradictions` · `GET /api/graph/export` · `GET /api/graph/obsidian-export` · `GET /api/graph/markdown-export`

### Bug Fix
Fixed `api_graph_data` to handle both `src`/`dst` and `source`/`target` edge key formats in `knowledge_graph.json`

### New UI (graph.html)
- **Layout**: sidebar (280px) + full-height graph area
- **Sidebar sections**: Search, Path Finder, Clusters toggle, Top Concepts (centrality bars), Knowledge Gaps, Contradictions
- **Graph enhancements**: edge labels on hover, cluster coloring, path highlighting with gold strokes, search zoom-to-node with highlight
- **Export buttons**: JSON, PNG, Obsidian ZIP in header bar

---

## Phase 5 — Audio & Multimedia (DONE)

Reach full NotebookLM feature parity and beyond.

### 5.1 Audio Input
- [x] **YouTube transcript import** — Already implemented in Phase 2 (`ppke/converter/youtube.py`)
- [x] **Podcast RSS import** — New `ppke/audio/rss.py`: `parse_feed()` + `download_and_transcribe()`; `POST /api/import-rss` endpoint; "Podcast RSS" tab in upload.html with feed preview + batch episode download
- [x] **Browser recording** — MediaRecorder API in upload.html "Record" tab; records WebM audio → `POST /api/audio/upload-recording` → Whisper transcription → ingestion as book
- [ ] **Speaker diarization** — Deferred *(requires heavy `pyannote.audio` dependency)*

### 5.2 Audio Output
- [x] **Voice selection UI** — 7 named presets in `VOICE_PRESETS` (4 Edge TTS: Natural/Professional/British/Australian; 3 OpenAI: Classic/Warm/Dynamic); dropdown in audio modal; `GET /api/audio/presets`
- [x] **Length control** — 3 presets in `LENGTH_PRESETS` (Short ~2min/400w, Medium ~5min/1000w, Long ~10min/2000w); dropdown in audio modal; word target passed to LLM prompt
- [x] **Topic-focused audio** — Optional topic text input in audio modal; when set, LLM prompt focuses 60%+ of conversation on that topic
- [x] **Cross-book podcast** — `generate_cross_book_script()` in overview.py + `POST /api/audio-overview/cross-book` endpoint; takes two book folders, generates comparative discussion
- [x] **Playback controls** — 5 speed buttons (0.75×, 1×, 1.25×, 1.5×, 2×) below audio player; collapsible transcript panel with `GET /api/audio/{folder}/transcript`; `script_to_transcript()` renders Markdown

### 5.3 Video (Future)
- [ ] **Lecture video import** — *(deferred to later phase)*
- [ ] **Video summaries** — *(deferred to later phase)*

### Enhanced Module: `ppke/audio/overview.py`
- `VOICE_PRESETS` — 7 named voice pairs (Edge TTS + OpenAI TTS)
- `LENGTH_PRESETS` — short/medium/long with word targets + max_tokens
- `generate_script()` — now accepts `length` and `topic` params
- `generate_cross_book_script()` — comparative podcast for 2 books
- `synthesize_from_preset()` — convenience wrapper using preset names
- `script_to_transcript()` — script → readable Markdown

### New Module: `ppke/audio/rss.py`
- `parse_feed()` — parse RSS, find audio enclosures, return episode metadata
- `download_and_transcribe()` — download episode audio, Whisper transcribe, return Markdown

### New Endpoints (6)
`POST /api/audio-overview/cross-book` · `GET /api/audio/{folder}/transcript` · `GET /api/audio/presets` · `POST /api/import-rss` · `POST /api/audio/upload-recording` · Modified `POST /api/audio-overview` (voice_preset, length, topic params)

### New UI
- **upload.html**: 5 tabs (File Upload, From URL, Batch Upload, **Podcast RSS**, **Record**)
  - Podcast RSS: feed URL input, episode count, preview button, batch import
  - Record: MediaRecorder UI with timer, playback preview, title/author fields, discard/submit
- **notebook.html audio modal**: voice preset dropdown, length dropdown, topic focus input, speed buttons (0.75–2×), collapsible transcript panel

---

## Phase 6 — Export & Content Generation (DONE)

Turn analysis into publishable outputs.

### 6.1 Document Export
- [x] **PDF export** — `GET /api/export/{folder}/pdf` generates typeset HTML/CSS report, rendered with `weasyprint` (graceful fallback to HTML if not installed); cover page, section dividers, page numbers, proper typography
- [x] **DOCX export** — `GET /api/export/{folder}/docx` generates Word document via `python-docx` with title page, styled headings, bullet lists, inline bold/italic formatting, all analysis sections + summary + study guide
- [x] **Slide deck** — `GET /api/export/{folder}/pptx` auto-generates PowerPoint via `python-pptx` with: title slide, executive summary bullets, top concepts (frequency-ranked), logical structure, key claims, patterns, closing stats slide; 16:9 widescreen format
- [x] **Markdown ZIP** — `GET /api/export/{folder}/zip` downloads all Markdown files, meta.yml, extractions.json, audio scripts as a ZIP archive

### 6.2 Academic Tools
- [x] **Literature review** — `POST /api/literature-review` cross-book LLM synthesis with thematic analysis, key debates, gaps; cached as `literature_review.md`; Lit Review tab in notebook UI
- [x] **Bibliography** — `GET /api/bibliography?style=apa|mla|chicago` generates formatted citation lists from all books' `meta.yml`; Bibliography tab with style switcher dropdown
- [x] **Argument maps** — `GET /api/argument-map/{folder}` builds node/edge graph from `extractions.json` (claims, assumptions, concepts, support/leads_to/grounds relationships); SVG force-directed diagram in Argument Map tab + Markdown text view

### New Module: `ppke/export/exporters.py`
- `export_pdf()` — HTML/CSS typeset report → weasyprint PDF (with fallback)
- `export_docx()` — python-docx Word document with title page + all sections
- `export_pptx()` — python-pptx slide deck from key concepts + claims
- `export_markdown_zip()` — ZIP archive of all book files

### New Module: `ppke/export/academic.py`
- `generate_bibliography()` — APA/MLA/Chicago formatted citations from meta.yml
- `generate_literature_review()` — LLM-powered cross-book synthesis
- `generate_argument_map()` — structured claim/assumption/concept graph from extractions
- `argument_map_to_markdown()` — readable text rendering of argument map

### New Endpoints (8)
`GET /api/export/{folder}/pdf` · `GET /api/export/{folder}/docx` · `GET /api/export/{folder}/pptx` · `GET /api/export/{folder}/zip` · `GET /api/bibliography` · `GET/POST /api/literature-review` · `GET /api/argument-map/{folder}`

### New UI (notebook.html)
- **Export dropdown** — emerald button in book header with PDF, Word, Slides, ZIP, Flashcards options
- **3 new tabs**: Argument Map (SVG diagram + text view), Bibliography (APA/MLA/Chicago switcher), Lit Review (LLM-generated cross-book synthesis)
- 11 total tabs: Chat, Structure, Concepts, Logical Map, Patterns, Summary, Glossary, Study Guide, Argument Map, Bibliography, Lit Review

### New Dependencies (`[export]`)
- `weasyprint>=60.0` — PDF generation from HTML/CSS
- `python-docx>=1.0.0` — Word document generation (shared with `[ocr]`)
- `python-pptx>=0.6.21` — PowerPoint slide deck generation

---

## Phase 7 — Multi-User & Collaboration + Multi-Tenant (DONE)

Transform from single-user to team tool with full multi-tenant support.

### 7.1 Authentication
- [x] **JWT-based auth** — Login/register with email + password; bcrypt hashing (PBKDF2 fallback); 72h token expiry; cookie + Bearer header support
- [x] **OAuth** — Google, GitHub sign-in placeholders (requires `GOOGLE_CLIENT_ID`/`GITHUB_CLIENT_SECRET` env vars); OAuth callback scaffold
- [x] **Per-user vaults** — Each user gets isolated `~/.ppke/vaults/{user_id}/` directory; all book data fully isolated between users

### 7.2 Collaboration
- [x] **Shared notebooks** — `POST /api/workspaces/{ws_id}/share` shares a book to a workspace; `GET /api/workspaces/{ws_id}/shared-books` lists shared books; shared books appear on dashboard
- [x] **Annotations** — `POST/GET/DELETE /api/annotations` for personal notes on any paragraph; annotations loaded per-book in notebook view
- [x] **Activity feed** — `GET /api/activity` shows recent actions (sign in, uploads, shares, annotations); workspace-scoped and user-scoped views; displayed on workspaces page

### 7.3 Access Control
- [x] **Roles** — Admin, Editor, Viewer per workspace; role-checked invite/share/remove operations; `require_role()` FastAPI dependency factory
- [x] **API key management** — `POST/GET/DELETE /api/keys` for per-user LLM API key storage (base64 encoded); displayed in settings page
- [x] **Usage quotas** — `usage_records` table tracks tokens, cost, provider per request; `GET /api/usage` returns 30-day summary; displayed in settings page

### 7.4 Multi-Tenant Support
- [x] **Workspaces** — `POST/GET /api/workspaces` create and list workspaces; each workspace has isolated membership, shared books, activity
- [x] **Workspace members** — `GET /api/workspaces/{ws_id}/members`, `POST /api/workspaces/{ws_id}/invite`, role management, member removal
- [x] **Vault isolation** — `_user_vault_path(user)` → `~/.ppke/vaults/{user_id}/`; all 40+ API endpoints updated to use per-user vault; `_book_dirs(user)` accepts optional user

### New Module: `ppke/auth/`
- `database.py` — SQLite schema (8 tables: users, workspaces, workspace_members, shared_books, annotations, activity_log, api_keys, usage_records); full CRUD operations; auto-migrate on first connection
- `jwt_auth.py` — JWT token creation/verification via PyJWT (HMAC fallback if not installed); bcrypt password hashing (PBKDF2 fallback); auto-generated persistent secret key
- `deps.py` — FastAPI dependencies: `get_current_user`, `get_optional_user`, `require_role()`, `get_user_vault_path()`

### New Templates
- `login.html` — Sign in form with email/password + OAuth buttons (Google, GitHub)
- `register.html` — Registration form with name/email/password/confirm + OAuth buttons
- `workspaces.html` — Workspace list with create modal, members modal with invite, activity feed

### New Endpoints (20+)
`GET/POST /auth/login` · `GET/POST /auth/register` · `GET /auth/logout` · `GET /auth/oauth/{provider}` · `GET /api/auth/me` ·
`GET/POST /api/workspaces` · `GET /api/workspaces/{ws_id}/members` · `POST /api/workspaces/{ws_id}/invite` ·
`POST /api/workspaces/{ws_id}/members/{id}/role` · `DELETE /api/workspaces/{ws_id}/members/{id}` ·
`POST /api/workspaces/{ws_id}/share` · `GET /api/workspaces/{ws_id}/shared-books` ·
`POST/GET/DELETE /api/annotations` · `GET /api/activity` ·
`POST/GET/DELETE /api/keys` · `GET /api/usage`

### Updated UI
- **base.html**: User avatar dropdown in nav (name, email, workspaces, sign out); "Sign In" link for unauthenticated; Workspaces nav link; mobile menu auth section
- **settings.html**: Per-user API key management section; usage stats dashboard (requests, tokens, est. cost); user info in system info
- All pages redirect to `/login` when unauthenticated

### New Dependencies (`[auth]`)
- `PyJWT>=2.8.0` — JWT token handling
- `bcrypt>=4.0.0` — Password hashing

---

## Phase 8 — Deployment & Infrastructure (NEXT)

Production-grade deployment and monitoring.

### 8.1 Containerization
- [ ] **Dockerfile** — Multi-stage build: Python base + optional Tesseract/ffmpeg
- [ ] **Docker Compose** — App + optional PostgreSQL + Redis + ChromaDB
- [ ] **Health checks** — `/api/health` endpoint (done), Docker HEALTHCHECK

### 8.2 Production Hardening
- [ ] **Task queue** — Replace `threading.Thread` with Celery/RQ for background jobs
- [ ] **Database** — SQLite for single-user, PostgreSQL for multi-user
- [ ] **Object storage** — S3/GCS for uploaded files and generated audio
- [ ] **Caching** — Redis for API response caching and rate limiting

### 8.3 Monitoring
- [ ] **Structured logging** — JSON logs with request IDs
- [ ] **Metrics** — Prometheus `/metrics` endpoint (request latency, ingestion duration)
- [ ] **Error tracking** — Sentry integration
- [ ] **Cost dashboard** — Per-book LLM token usage tracking

### Implementation notes
- Celery: `celery_app = Celery(broker='redis://...')`, wrap `_run_ingest` as task
- SQLite: Use `sqlmodel` for ORM, migrate meta.yml to database tables

---

## Phase 9 — Monetization (Optional)

SaaS model for hosted deployment.

### 9.1 Pricing
- [ ] **Free** — 3 books, text-only, basic search
- [ ] **Pro ($15/mo)** — Unlimited books, OCR, audio, vector search
- [ ] **Team ($40/mo)** — Collaboration, shared workspaces
- [ ] **Enterprise** — Self-hosted, SSO, custom domains, SLA

### 9.2 Payments
- [ ] **Stripe subscriptions** — Monthly/annual billing
- [ ] **Usage-based billing** — LLM API cost pass-through + margin
- [ ] **Credit system** — Pre-paid credits for audio generation

### 9.3 Marketplace
- [ ] **Template marketplace** — Community domain templates
- [ ] **Pre-built knowledge bases** — Curated book collections for sale

---

## Architecture

```
                    ┌──────────────────────────────────────┐
                    │           Web Browser (Client)        │
                    │  Tailwind + HTMX + D3.js + marked.js │
                    └─────────────────┬────────────────────┘
                                      │ HTTP / SSE
                    ┌─────────────────▼────────────────────┐
                    │         FastAPI Web Server            │
                    │         (ppke/web/app.py)             │
                    │                                       │
                    │  Middleware: Error handling,           │
                    │  path traversal protection,           │
                    │  input sanitization                   │
                    │                                       │
                    │  Pages: /, /notebook, /upload,        │
                    │         /graph, /settings             │
                    │  API:   /api/books, /api/query,       │
                    │         /api/query/stream (SSE),      │
                    │         /api/settings, /api/health    │
                    └─────────────────┬────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
    ┌─────────▼──────────┐  ┌────────▼─────────┐  ┌─────────▼──────────┐
    │  Document Converter │  │   PPKE Core      │  │   Audio Module     │
    │  (ppke/converter/)  │  │   Engine         │  │   (ppke/audio/)    │
    │                     │  │                  │  │                    │
    │  23 file formats    │  │  parser/         │  │  Whisper API       │
    │  OCR + Vision LLM   │  │  pipeline/       │  │  OpenAI TTS        │
    │  Decorator registry │  │  llm/            │  │  Edge TTS (free)   │
    └────────────────────┘  │  output/         │  │  pydub             │
                             │  vectordb/       │  └────────────────────┘
                             │  graph/          │
                             └──────────────────┘
```

## Priority Matrix

| Phase | Key Deliverable | Impact | Effort | Status |
|-------|----------------|--------|--------|--------|
| 0 | Web GUI + Converters + Audio | Critical | Large | DONE |
| 1 | Dark mode, SSE, Settings, Security | High | Medium | DONE |
| 2 | URL/YouTube import, Hybrid OCR | High | Medium | DONE |
| 3 | Multi-turn chat, RAG, Flashcards | High | Medium | DONE |
| 4 | Graph analytics, Path finder | Medium | Medium | DONE |
| 5 | Full NotebookLM audio parity | Medium | Large | DONE |
| 6 | PDF/DOCX/Slides export | Medium | Medium | DONE |
| 7 | Multi-user auth & collab | High | Large | Next |
| 8 | Docker, Celery, Monitoring | High | Large | Planned |
| 9 | SaaS monetization | Variable | Large | Optional |
