# PPKE Future Plans & Development Roadmap

> **Last Updated:** 2026-02-27
> **Current Version:** 2.0.0 (CLI + Web GUI + Converters + Audio)

---

## Table of Contents

1. [What Has Been Done (Current Session)](#1-what-has-been-done-current-session)
2. [Phase 1 — Web GUI Polish & Production Readiness](#2-phase-1--web-gui-polish--production-readiness)
3. [Phase 2 — OCR & Document Converter Enhancements](#3-phase-2--ocr--document-converter-enhancements)
4. [Phase 3 — Audio Features (NotebookLM Parity)](#4-phase-3--audio-features-notebooklm-parity)
5. [Phase 4 — Knowledge Graph & Visualization](#5-phase-4--knowledge-graph--visualization)
6. [Phase 5 — Multi-User & Collaboration](#6-phase-5--multi-user--collaboration)
7. [Phase 6 — AI Enhancements & Intelligence](#7-phase-6--ai-enhancements--intelligence)
8. [Phase 7 — Content Generation & Export](#8-phase-7--content-generation--export)
9. [Phase 8 — Video & Multimedia](#9-phase-8--video--multimedia)
10. [Phase 9 — Deployment & Scale](#10-phase-9--deployment--scale)
11. [Phase 10 — Monetization & SaaS](#11-phase-10--monetization--saas)
12. [Technical Debt & Maintenance](#12-technical-debt--maintenance)
13. [Architecture Decisions](#13-architecture-decisions)

---

## 1. What Has Been Done (Current Session)

### 1.1 Web GUI Layer (`ppke/web/`)

**Files Created:**
- `ppke/web/__init__.py` — Package init
- `ppke/web/app.py` — Full FastAPI application with:
  - REST API endpoints wrapping all existing CLI commands
  - Server-rendered HTML pages via Jinja2 + HTMX
  - File upload with background ingestion jobs
  - Real-time ingestion progress polling
  - Chat/query interface for single-book and cross-book queries
  - Full-text search API
  - Audio overview generation endpoint
  - Knowledge graph data API (D3-compatible)
  - Static file serving
  - Configuration API (redacts secrets)

**Templates Created:**
- `ppke/web/templates/base.html` — Base layout with Tailwind CSS, HTMX, navigation, global search
- `ppke/web/templates/dashboard.html` — Library view with stats cards, book grid, async stat loading
- `ppke/web/templates/notebook.html` — Per-book view with:
  - Tabbed interface (Chat, Structure, Concepts, Logical Map, Patterns)
  - Live chat with streaming answers and citation display
  - Audio overview generation modal
- `ppke/web/templates/upload.html` — Drag-and-drop upload with:
  - Format detection, metadata fields, domain selection
  - Background ingestion with live progress bar
  - Success redirect to notebook view
- `ppke/web/templates/graph.html` — Obsidian-style interactive knowledge graph with:
  - D3.js force-directed layout
  - Color-coded nodes (concept/book/paragraph)
  - Click-to-highlight connections
  - Zoom/pan controls
  - Book filter dropdown
  - Node detail panel

**CLI Integration:**
- Added `ppke serve` command to `cli.py`
- Launches uvicorn with configurable `--host`, `--port`, `--reload`

### 1.2 Document Converter Layer (`ppke/converter/`)

**Files Created:**
- `ppke/converter/__init__.py` — Public API: `convert_to_markdown()`, `SUPPORTED_EXTENSIONS`
- `ppke/converter/registry.py` — Universal converter with decorator-based registration:
  - `.md` — Pass-through
  - `.txt` — Wrap in heading structure
  - `.pdf` — PyMuPDF text extraction with OCR fallback
  - `.docx` — python-docx with heading hierarchy preservation
  - `.epub` — ebooklib + BeautifulSoup
  - `.html/.htm` — BeautifulSoup with script/style removal
  - `.jpg/.jpeg/.png/.tiff/.tif/.bmp/.webp` — Tesseract OCR
  - `.pptx` — python-pptx slide-by-slide extraction
  - `.mp3/.mp4/.m4a/.wav/.webm/.ogg` — Audio transcription via Whisper
- `ppke/converter/ocr.py` — OCR utilities:
  - `ocr_image()` — Tesseract single-image OCR
  - `ocr_pdf_pages()` — Selective page OCR for scanned PDFs
  - `vision_ocr()` — Claude/GPT-4V Vision LLM fallback for complex layouts

### 1.3 Audio Module (`ppke/audio/`)

**Files Created:**
- `ppke/audio/__init__.py` — Package init
- `ppke/audio/transcriber.py` — Audio-to-text transcription:
  - `transcribe()` — OpenAI Whisper API with timestamped Markdown output
  - `transcribe_local()` — Local Whisper model fallback
  - Segment-level timestamps formatted as `[MM:SS]` markers
- `ppke/audio/overview.py` — NotebookLM-style audio overview generation:
  - `generate_script()` — LLM-powered podcast script from book analysis
  - `synthesize_audio()` — TTS synthesis with two distinct voices
  - `_synthesize_openai()` — OpenAI TTS HD backend
  - `_synthesize_edge()` — Edge TTS (free, no API key) backend
  - Concatenation with pydub, 400ms pauses between turns

### 1.4 Dependency Updates (`pyproject.toml`)

**New optional dependency groups:**
- `[web]` — fastapi, uvicorn, python-multipart, jinja2
- `[ocr]` — PyMuPDF, pytesseract, pdf2image, Pillow, python-docx, beautifulsoup4
- `[audio]` — pydub, edge-tts
- `[all]` — Everything combined

---

## 2. Phase 1 — Web GUI Polish & Production Readiness

### 2.1 Authentication & Security
- [ ] Add user authentication (OAuth2 via Google/GitHub, or JWT-based local auth)
- [ ] Implement CSRF protection for all form submissions
- [ ] Add rate limiting per-user to control LLM API costs
- [ ] Sanitize all user input (HTML escaping in templates, path traversal prevention)
- [ ] Add session management with secure cookie storage
- [ ] Implement API key management in the web UI (instead of .env file)

### 2.2 UI/UX Improvements
- [ ] Add dark mode toggle (already have Tailwind darkMode config)
- [ ] Implement responsive mobile layout for all pages
- [ ] Add keyboard shortcuts (Ctrl+K for search, Ctrl+N for new upload)
- [ ] Add loading skeletons instead of spinners
- [ ] Implement proper Markdown rendering in chat responses (use marked.js or similar)
- [ ] Add syntax highlighting for code blocks in extractions
- [ ] Add breadcrumb navigation
- [ ] Implement "recently viewed" section on dashboard
- [ ] Add book cover image support (auto-generate from title/author)
- [ ] Implement toast notifications for success/error events

### 2.3 Real-Time Features
- [ ] Replace polling with WebSocket for ingestion progress
- [ ] Add server-sent events (SSE) for streaming LLM responses in chat
- [ ] Implement live search-as-you-type with debouncing
- [ ] Add real-time concept count updates during ingestion

### 2.4 Performance
- [ ] Add response caching for frequently accessed book metadata
- [ ] Implement lazy loading for extraction data (paginated API already exists)
- [ ] Add database layer (SQLite or PostgreSQL) instead of JSON file reads
- [ ] Add thumbnail/preview generation for uploaded documents
- [ ] Implement CDN-friendly static asset hashing

---

## 3. Phase 2 — OCR & Document Converter Enhancements

### 3.1 Additional Format Support
- [ ] **URL/Web scraping** — Paste a URL, scrape article content (use `trafilatura` or `readability-lxml`)
- [ ] **Google Docs** — Import via Google Drive API
- [ ] **Notion pages** — Import via Notion API
- [ ] **LaTeX** — Convert `.tex` files to Markdown (use `pandoc` or `pylatexenc`)
- [ ] **CSV/Excel** — Import tabular data as structured Markdown tables
- [ ] **Handwritten notes** — Dedicated pipeline using Vision LLM (Claude/GPT-4V)
- [ ] **Multi-page TIFF** — Support for multi-page scanned documents

### 3.2 OCR Quality Improvements
- [ ] Add OCR confidence scoring — flag low-confidence pages for human review
- [ ] Implement hybrid OCR: Tesseract first, Vision LLM fallback for low-confidence pages
- [ ] Add language detection and auto-configuration for Tesseract
- [ ] Support right-to-left languages (Arabic, Hebrew, Farsi)
- [ ] Add table structure detection and preservation in PDFs
- [ ] Implement equation/formula detection (LaTeX output)

### 3.3 Pre-Processing Pipeline
- [ ] Add image preprocessing: deskew, denoise, contrast enhancement (OpenCV)
- [ ] Implement automatic page rotation detection
- [ ] Add duplicate page/content detection
- [ ] Implement smart chapter detection from PDF bookmarks/TOC

### 3.4 Batch Processing
- [ ] Add bulk upload (ZIP/folder containing multiple documents)
- [ ] Implement queue-based processing for large uploads
- [ ] Add progress tracking per-file in multi-file uploads
- [ ] Support drag-and-drop multiple files at once

---

## 4. Phase 3 — Audio Features (NotebookLM Parity)

### 4.1 Audio Input Enhancements
- [ ] **YouTube transcript import** — Use `yt-dlp` to download audio, then transcribe
- [ ] **Podcast RSS import** — Paste RSS feed URL, auto-transcribe episodes
- [ ] **Real-time voice input** — Browser-based recording with Web Audio API
- [ ] **Speaker diarization** — Identify different speakers in audio (use `pyannote.audio`)
- [ ] **Multi-language transcription** — Auto-detect language, configure per-file
- [ ] **Meeting recording import** — Support Zoom/Teams/Google Meet exports

### 4.2 Audio Output Enhancements
- [ ] **Custom voice selection** — Let users choose from multiple voice pairs
- [ ] **Audio length control** — Short (2 min), Medium (5 min), Long (10 min) overviews
- [ ] **Topic-focused overviews** — "Generate audio about [specific concept]"
- [ ] **Cross-book audio** — Generate podcast comparing multiple books
- [ ] **Background music** — Add subtle background music to audio overviews
- [ ] **Chapter-by-chapter audio** — Generate separate audio per chapter
- [ ] **Audio bookmarks** — Click on transcript to jump to audio position
- [ ] **Playback speed control** — 0.5x, 1x, 1.5x, 2x in web player
- [ ] **Download formats** — MP3, WAV, M4A export options

### 4.3 Voice Cloning (Advanced)
- [ ] ElevenLabs voice cloning integration — Use author's own voice (if available)
- [ ] Custom voice training for consistent "PPKE hosts"
- [ ] Multiple language TTS for non-English content

---

## 5. Phase 4 — Knowledge Graph & Visualization

### 5.1 Graph Visualization Enhancements
- [ ] **Time-based graph** — Show how concepts evolve chronologically
- [ ] **Hierarchical layout** — Tree layout for argument structures
- [ ] **Cluster detection** — Auto-group related concepts using Louvain community detection
- [ ] **Search within graph** — Type a concept name, zoom to it
- [ ] **Edge labels** — Show relationship types on hover
- [ ] **Node sizing** — Size by frequency, importance, or connectivity
- [ ] **Export graph** — Export as PNG, SVG, or JSON for other tools
- [ ] **3D graph** — Three.js powered 3D visualization option
- [ ] **Mini-map** — Obsidian-style overview panel for large graphs

### 5.2 Graph Intelligence
- [ ] **Path finding** — "How is concept A connected to concept B?"
- [ ] **Centrality analysis** — Identify the most important concepts across books
- [ ] **Gap detection** — Find concepts that should be connected but aren't
- [ ] **Contradiction detection** — Highlight conflicting claims across books
- [ ] **Influence mapping** — Which author's concepts influenced others?
- [ ] **Temporal evolution** — Track how a concept's meaning shifts across books/years

### 5.3 Integration with Other Tools
- [ ] **Obsidian export** — Generate Obsidian-compatible vault with wikilinks
- [ ] **Notion export** — Push graph as linked database pages
- [ ] **Neo4j export** — Full graph database export for power users
- [ ] **Cytoscape.js** — Alternative visualization engine for large graphs

---

## 6. Phase 5 — Multi-User & Collaboration

### 6.1 User System
- [ ] User registration and login (email + password)
- [ ] OAuth providers (Google, GitHub, Microsoft)
- [ ] User profiles with avatar, bio, expertise areas
- [ ] Per-user vault isolation (each user gets their own knowledge base)
- [ ] Usage quotas and API cost tracking per user

### 6.2 Collaboration Features
- [ ] **Shared notebooks** — Invite others to view/query your notebooks
- [ ] **Team workspaces** — Organizations with shared vaults
- [ ] **Annotations** — Add personal notes/highlights to any paragraph
- [ ] **Comments** — Threaded discussions on specific extractions
- [ ] **Activity feed** — See recent ingestions, queries, and annotations
- [ ] **Export sharing** — Generate shareable links to specific analyses

### 6.3 Permissions & Access Control
- [ ] Role-based access (Admin, Editor, Viewer)
- [ ] Per-notebook sharing permissions
- [ ] Audit log for all actions
- [ ] API key management per user

---

## 7. Phase 6 — AI Enhancements & Intelligence

### 7.1 Smarter Querying
- [ ] **Retrieval-Augmented Generation (RAG)** — Use vector search as context for LLM queries
- [ ] **Multi-turn conversations** — Chat history with context window management
- [ ] **Follow-up suggestions** — "You might also want to ask about..."
- [ ] **Query templates** — Pre-built question types ("Compare X and Y", "Summarize chapter N")
- [ ] **Auto-generated study questions** — LLM generates quiz questions from content

### 7.2 Content Analysis
- [ ] **Sentiment analysis** — Track emotional arc across chapters
- [ ] **Readability scoring** — Flesch-Kincaid, Gunning Fog, etc.
- [ ] **Citation network** — Detect and map bibliographic references
- [ ] **Writing style analysis** — Vocabulary richness, sentence complexity
- [ ] **Argument strength scoring** — Rate how well-supported claims are

### 7.3 Auto-Organization
- [ ] **Smart tagging** — Auto-tag books by topic, difficulty, genre
- [ ] **Related book recommendations** — "Based on this book, you might enjoy..."
- [ ] **Concept clustering** — Group related concepts across entire vault
- [ ] **Duplicate concept detection** — Merge "free will" and "freedom of the will"

### 7.4 Agentic Features
- [ ] **Research agent** — "Find all arguments about X across my library"
- [ ] **Comparison agent** — "Write a 500-word essay comparing these two books"
- [ ] **Summary agent** — "Summarize this book in 3 paragraphs, 1 page, or 5 pages"
- [ ] **Fact-checking agent** — Cross-reference claims against other books in vault

---

## 8. Phase 7 — Content Generation & Export

### 8.1 Auto-Generated Documents
- [ ] **Executive summaries** — One-page summary for any book
- [ ] **Literature reviews** — Cross-book synthesis formatted as academic lit review
- [ ] **Flashcards** — Anki-compatible flashcard deck generation
- [ ] **Study guides** — Chapter-by-chapter study notes with key concepts
- [ ] **Timelines** — Chronological event/argument timelines
- [ ] **Glossaries** — Auto-generated term definitions from concept index
- [ ] **Bibliographies** — Formatted citation lists (APA, MLA, Chicago)

### 8.2 Export Formats
- [ ] **PDF export** — Beautiful typeset reports with citations
- [ ] **EPUB export** — E-reader compatible books
- [ ] **DOCX export** — Microsoft Word format
- [ ] **Slide deck** — Auto-generated presentation from key concepts
- [ ] **Obsidian vault** — Full compatible export with wikilinks and graph
- [ ] **Zotero integration** — Push notes/annotations to Zotero library
- [ ] **Markdown zip** — Download entire notebook as ZIP

---

## 9. Phase 8 — Video & Multimedia

### 9.1 Video Input
- [ ] **YouTube video import** — Extract audio + keyframes
- [ ] **Lecture video import** — Transcribe + extract slide content via OCR
- [ ] **Screen recording import** — OCR text from screen recordings
- [ ] **Documentary analysis** — Combine transcript + visual analysis

### 9.2 Visual Content
- [ ] **Diagram extraction** — Detect and describe diagrams in documents
- [ ] **Chart/graph analysis** — Extract data from charts using Vision LLM
- [ ] **Image annotation** — Link images to related concepts
- [ ] **Infographic generation** — Auto-generate visual summaries

### 9.3 Video Output
- [ ] **Video summaries** — Generate narrated slideshows from book analysis
- [ ] **Animated concept maps** — Video showing concept evolution over chapters
- [ ] **Tutorial generation** — Create educational videos from content

---

## 10. Phase 9 — Deployment & Scale

### 10.1 Containerization
- [ ] **Dockerfile** — Multi-stage build (Python + Node if needed)
- [ ] **Docker Compose** — Full stack with optional PostgreSQL, Redis, ChromaDB
- [ ] **Kubernetes manifests** — Helm chart for cloud deployment
- [ ] **Health checks** — /healthz and /readyz endpoints

### 10.2 Cloud Deployment
- [ ] **Vercel/Render** — One-click deploy for the web frontend
- [ ] **Railway/Fly.io** — Full-stack deployment with persistent storage
- [ ] **AWS/GCP/Azure** — Terraform modules for enterprise deployment
- [ ] **CDN** — Static asset distribution

### 10.3 Scaling
- [ ] **Task queue** — Celery/RQ for background ingestion jobs (replace threading)
- [ ] **Database migration** — SQLite → PostgreSQL for multi-user
- [ ] **Object storage** — S3/GCS for uploaded files and audio
- [ ] **Worker processes** — Separate ingestion workers from web server
- [ ] **Caching layer** — Redis for API response caching
- [ ] **Rate limiting** — Per-user API rate limits

### 10.4 Monitoring
- [ ] **Structured logging** — JSON logs with request IDs
- [ ] **Metrics** — Prometheus metrics for API latency, ingestion times
- [ ] **Error tracking** — Sentry integration
- [ ] **Cost tracking** — Per-user LLM API cost monitoring dashboard

---

## 11. Phase 10 — Monetization & SaaS

### 11.1 Pricing Tiers
- [ ] **Free tier** — 3 books, text-only, basic search
- [ ] **Pro tier** — Unlimited books, OCR, audio overviews, vector search
- [ ] **Team tier** — Collaboration, shared workspaces, priority support
- [ ] **Enterprise** — Self-hosted, SSO, custom domains, SLA

### 11.2 Payment Integration
- [ ] Stripe subscription management
- [ ] Usage-based billing for LLM API costs
- [ ] Credit system for audio generation
- [ ] Invoice generation

### 11.3 Marketplace
- [ ] **Template marketplace** — Users sell custom domain templates
- [ ] **Pre-built knowledge bases** — Curated book collections
- [ ] **Plugin system** — Third-party extensions

---

## 12. Technical Debt & Maintenance

### 12.1 Testing
- [ ] Add integration tests for web API endpoints
- [ ] Add E2E tests with Playwright for web UI
- [ ] Add converter unit tests (mock PyMuPDF, pytesseract, etc.)
- [ ] Add audio module tests (mock OpenAI, pydub)
- [ ] Ensure overall test coverage stays above 80%

### 12.2 Code Quality
- [ ] Add type hints throughout web module
- [ ] Add OpenAPI schema documentation for all API endpoints
- [ ] Add input validation with Pydantic models for API requests
- [ ] Add error handling middleware for consistent error responses
- [ ] Add request logging middleware

### 12.3 Documentation
- [ ] Write user guide for web interface
- [ ] Document all API endpoints with examples
- [ ] Add architecture diagram for web + converter + audio modules
- [ ] Add developer setup guide (prerequisites: Tesseract, ffmpeg, poppler)
- [ ] Add deployment guide

### 12.4 CI/CD
- [ ] Add GitHub Actions workflow for web GUI tests
- [ ] Add Docker build step to CI pipeline
- [ ] Add automated dependency security scanning
- [ ] Add lighthouse performance tests for web pages

---

## 13. Architecture Decisions

### Current Architecture (after this session)

```
                    ┌──────────────────────────────────────┐
                    │           Web Browser (Client)        │
                    │  HTML + Tailwind + HTMX + D3.js      │
                    └─────────────────┬────────────────────┘
                                      │ HTTP / WebSocket
                    ┌─────────────────▼────────────────────┐
                    │         FastAPI Web Server            │
                    │         (ppke/web/app.py)             │
                    │                                       │
                    │  Pages: /, /notebook, /upload, /graph │
                    │  API:   /api/books, /api/query, ...   │
                    └─────────────────┬────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
    ┌─────────▼──────────┐  ┌────────▼─────────┐  ┌─────────▼──────────┐
    │  Document Converter │  │   PPKE Core      │  │   Audio Module     │
    │  (ppke/converter/)  │  │   Engine         │  │   (ppke/audio/)    │
    │                     │  │                  │  │                    │
    │  PDF → Markdown     │  │  parser/         │  │  transcriber.py   │
    │  DOCX → Markdown    │  │  pipeline/       │  │  overview.py      │
    │  Image → OCR → MD   │  │  llm/            │  │                   │
    │  Audio → Transcript │  │  output/         │  │  Whisper API      │
    │  EPUB → Markdown    │  │  vectordb/       │  │  OpenAI TTS       │
    │  HTML → Markdown    │  │  graph/          │  │  Edge TTS (free)  │
    │  PPTX → Markdown    │  │  templates/      │  │  pydub            │
    └────────────────────┘  └──────────────────┘  └────────────────────┘
              │                       │                       │
              └───────────────────────┼───────────────────────┘
                                      │
                    ┌─────────────────▼────────────────────┐
                    │       LLM Providers (External)        │
                    │  Anthropic | OpenAI | Gemini |        │
                    │  DeepSeek  | OpenRouter               │
                    └──────────────────────────────────────┘
```

### Key Design Principles

1. **Convert-then-ingest** — All document formats are converted to Markdown FIRST, then fed into the existing parser. Zero changes needed in downstream pipeline code.

2. **Graceful degradation** — Every optional dependency (ChromaDB, PyMuPDF, Tesseract, pydub) has an ImportError guard. The system works with just core deps; features activate as deps are installed.

3. **CLI parity** — Every web API endpoint maps 1:1 to an existing CLI command. The web GUI is a skin on the same engine, not a fork.

4. **Background processing** — Long-running tasks (ingestion, audio generation) run in background threads with polling-based progress tracking. Future: migrate to Celery/RQ for production.

5. **No database required** — All data still persists as JSON/YAML/Markdown files in the vault directory. Future: optional database layer for multi-user.

---

## Priority Matrix

| Feature | Impact | Effort | Priority |
|---------|--------|--------|----------|
| WebSocket for real-time progress | High | Low | P0 |
| Streaming LLM responses in chat | High | Medium | P0 |
| PDF/DOCX converter testing | High | Low | P0 |
| Dark mode | Medium | Low | P1 |
| YouTube import | High | Medium | P1 |
| URL scraping | High | Low | P1 |
| Multi-turn chat history | High | Medium | P1 |
| Flashcard generation | Medium | Medium | P2 |
| Speaker diarization | Medium | High | P2 |
| User authentication | High | High | P2 (needed for multi-user) |
| Docker deployment | High | Medium | P2 |
| 3D graph visualization | Low | High | P3 |
| Video import | Medium | High | P3 |
| Stripe billing | Medium | High | P3 (monetization phase) |

---

*This document is a living roadmap. Update it as features are completed and priorities shift.*
