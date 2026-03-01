# PPKE Quick Start Guide

**Get up and running with PPKE in 5 minutes**

---

## 🚀 Option A: Web Interface (Recommended)

```bash
# 1. Install with web dependencies
pip install -e ".[web]"

# 2. Start the web server
ppke serve
```

Open http://localhost:8000 in your browser. You'll see the PPKE dashboard.

### Upload Your First Document

1. Click **Upload** or drag a file onto the page
2. Supported formats: PDF, DOCX, EPUB, HTML, Markdown, images (OCR), and more
3. Enter a title and author, select domain (philosophy, legal, scientific)
4. Click **Ingest** — progress updates stream in real-time via SSE

### Query Your Book

1. Open the book's **Notebook** view
2. Type a question in the chat box
3. Get answers with verbatim evidence from the text
4. Chat history is saved automatically

### Explore Features

- **Knowledge Graph** — visualize concept relationships across books
- **Audio Overview** — generate podcast-style audio summaries
- **Export** — download analysis as PDF, DOCX, or PPTX
- **Study Tools** — auto-generate glossaries, flashcards, study guides

---

## 🚀 Option B: Command Line

```bash
# 1. Install
pip install -e .

# 2. First-time setup
ppke init

# 3. Ingest a document
ppke ingest book.md --title "Being and Time" --author "Heidegger" --year 1927

# 4. Query
ppke query --book "Book_Being_and_Time_Heidegger_1927" --question "What is Dasein?"
```

---

## 🐳 Docker Deployment

For production deployment with PostgreSQL, Redis, and Celery:

```bash
# 1. Clone the repo
git clone https://github.com/abxba0/ppke.git && cd ppke

# 2. Set environment variables
cp .env.example .env
# Edit .env with your API keys and settings

# 3. Start the full stack
docker-compose up -d

# 4. Open http://localhost:8000
```

---

## ⚙️ Configuration

### Via Web UI
Navigate to **Settings** (gear icon) to configure:
- LLM provider (Anthropic, OpenAI, DeepSeek, Gemini, OpenRouter)
- Model selection
- API keys

### Via CLI
```bash
ppke init                    # Interactive setup wizard
ppke config --show           # View current settings
ppke config --provider anthropic --model claude-sonnet-4-20250514
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `DATABASE_URL` | PostgreSQL connection string (optional) |
| `REDIS_URL` | Redis connection string (optional) |
| `SECRET_KEY` | JWT signing secret (auto-generated if not set) |

---

## 📦 Optional Dependencies

| Extra | Install | Features |
|-------|---------|----------|
| `web` | `pip install -e ".[web]"` | Web GUI (FastAPI, Jinja2) |
| `ocr` | `pip install -e ".[ocr]"` | PDF/image OCR |
| `audio` | `pip install -e ".[audio]"` | Audio generation & transcription |
| `dev` | `pip install -e ".[dev]"` | Testing & linting tools |

Install everything:
```bash
pip install -e ".[web,ocr,audio,dev]"
```

---

## 📖 Next Steps

- [README](../README.md) — Full feature overview and architecture
- [API Reference](developer/API_REFERENCE.md) — REST API documentation (80+ endpoints)
- [Architecture](developer/ARCHITECTURE_V2.md) — System design and data flow
- [Plugins](user-guides/PLUGINS.md) — Create custom domain templates
- [Migration Guide](user-guides/MIGRATION_GUIDE.md) — Upgrading from v1.x or v2.x
