# PPKE Development Roadmap

> **Last Updated:** 2026-02-27
> **Current Version:** 2.0.0

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

## Phase 3 — AI Chat Enhancements (NEXT)

Make the query engine significantly smarter.

### 3.1 Conversation Memory
- [ ] **Multi-turn chat** — Store chat history per book in a JSON file, send last N turns as context
- [ ] **Follow-up suggestions** — LLM generates 3 related questions after each answer
- [ ] **Query templates** — Pre-built buttons: "Summarize chapter N", "Compare X and Y", "Find all claims about Z"

### 3.2 RAG Pipeline
- [ ] **Vector-enhanced queries** — Use ChromaDB to retrieve top-K relevant paragraphs before querying LLM
- [ ] **Hybrid search** — Combine full-text search + vector similarity for retrieval
- [ ] **Citation highlighting** — Click a paragraph ID in chat to jump to the source text in the Structure tab

### 3.3 Content Generation
- [ ] **Executive summaries** — One-page summary button on each notebook
- [ ] **Flashcard generation** — Generate Anki-compatible `.apkg` deck from concept index
- [ ] **Study guide** — Chapter-by-chapter notes with key concepts, claims, and questions
- [ ] **Glossary** — Auto-generated term definitions from extraction data

### Implementation notes
- Chat history: Store in `{book_dir}/chat_history.json`, load last 10 turns into LLM context
- RAG: Already have VectorStore — pipe `store.search(question)` results into the query prompt
- Flashcards: Use `genanki` library to produce `.apkg` files downloadable from the UI

---

## Phase 4 — Knowledge Graph Intelligence

Make the graph view a real analytical tool, not just visualization.

### 4.1 Graph Features
- [ ] **Search within graph** — Type a concept name, zoom to it with highlight animation
- [ ] **Cluster detection** — Louvain community detection (NetworkX built-in), color by cluster
- [ ] **Edge labels on hover** — Show "defines", "contradicts", "supports" on link hover
- [ ] **Path finder** — "How is concept A connected to concept B?" — shortest path with explanation
- [ ] **Export** — Download graph as PNG/SVG/JSON

### 4.2 Graph Analytics
- [ ] **Centrality analysis** — PageRank/betweenness to find the most important concepts
- [ ] **Gap detection** — Concepts that appear in multiple books but are never connected
- [ ] **Contradiction detection** — Highlight edges where authors disagree
- [ ] **Temporal view** — Timeline slider showing concept evolution across publication years

### 4.3 External Integration
- [ ] **Obsidian export** — Generate vault with `[[wikilinks]]` matching concept names
- [ ] **Markdown graph export** — Download concept index as interlinked Markdown files

### Implementation notes
- Louvain: `networkx.community.louvain_communities(G)` → assign group colors
- Path finder: `nx.shortest_path(G, source, target)` → return path + edge labels
- Obsidian: Write one `.md` per concept with `[[Related Concept]]` links

---

## Phase 5 — Audio & Multimedia

Reach full NotebookLM feature parity and beyond.

### 5.1 Audio Input
- [ ] **YouTube transcript import** — Paste YouTube URL → download audio → transcribe → ingest
- [ ] **Podcast RSS import** — Paste RSS feed → auto-transcribe recent episodes
- [ ] **Browser recording** — Record voice input directly in the web UI (Web Audio API)
- [ ] **Speaker diarization** — Identify speakers using `pyannote.audio`

### 5.2 Audio Output
- [ ] **Voice selection UI** — Pick from multiple voice pairs for podcast generation
- [ ] **Length control** — Short (2 min) / Medium (5 min) / Long (10 min) overviews
- [ ] **Topic-focused audio** — "Generate audio about [specific concept]"
- [ ] **Cross-book podcast** — Compare two books in a single podcast episode
- [ ] **Playback controls** — Speed control (0.5x-2x), audio bookmarks linked to transcript

### 5.3 Video (Future)
- [ ] **Lecture video import** — Extract audio + OCR slide content
- [ ] **Video summaries** — Generate narrated slideshows from book analysis

### Implementation notes
- YouTube: `yt-dlp -x --audio-format mp3 URL` → pipe to existing `transcribe()`
- Voice selection: Add voice picker to audio modal, pass to `synthesize_audio()`
- Length control: Vary `max_tokens` in script generation prompt (800 words ≈ 5 min)

---

## Phase 6 — Export & Content Generation

Turn analysis into publishable outputs.

### 6.1 Document Export
- [ ] **PDF export** — Generate typeset reports with `weasyprint` or `reportlab`
- [ ] **DOCX export** — Word format via `python-docx`
- [ ] **Slide deck** — Auto-generate PowerPoint from key concepts via `python-pptx`
- [ ] **Markdown ZIP** — Download entire notebook as ZIP archive

### 6.2 Academic Tools
- [ ] **Literature review** — Cross-book synthesis formatted as academic lit review section
- [ ] **Bibliography** — Formatted citation lists (APA, MLA, Chicago) from `meta.yml`
- [ ] **Argument maps** — Visual argument diagrams from logical map data

### Implementation notes
- PDF: Render Markdown templates with Jinja2 → convert with weasyprint
- ZIP: Stream a ZIP file from all files in the book directory

---

## Phase 7 — Multi-User & Collaboration

Transform from single-user to team tool.

### 7.1 Authentication
- [ ] **JWT-based auth** — Login/register with email + password (bcrypt hashing)
- [ ] **OAuth** — Google, GitHub sign-in via `authlib`
- [ ] **Per-user vaults** — Each user gets isolated `~/.ppke/{user_id}/` directory

### 7.2 Collaboration
- [ ] **Shared notebooks** — Invite via email to view/query a notebook
- [ ] **Annotations** — Personal notes/highlights on any paragraph
- [ ] **Activity feed** — Recent ingestions, queries, annotations across team

### 7.3 Access Control
- [ ] **Roles** — Admin, Editor, Viewer per workspace
- [ ] **API key management** — Per-user LLM API key storage
- [ ] **Usage quotas** — Track and limit LLM API costs per user

### Implementation notes
- Auth: FastAPI `Depends()` with JWT middleware, store users in SQLite
- Vaults: `Config.vault_path = base_vault / user_id`
- Requires database migration from JSON files → SQLite/PostgreSQL

---

## Phase 8 — Deployment & Infrastructure

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
| 3 | Multi-turn chat, RAG, Flashcards | High | Medium | Next |
| 4 | Graph analytics, Path finder | Medium | Medium | Planned |
| 5 | Full NotebookLM audio parity | Medium | Large | Planned |
| 6 | PDF/DOCX/Slides export | Medium | Medium | Planned |
| 7 | Multi-user auth & collab | High | Large | Planned |
| 8 | Docker, Celery, Monitoring | High | Large | Planned |
| 9 | SaaS monetization | Variable | Large | Optional |
