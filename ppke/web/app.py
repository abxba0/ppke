"""FastAPI application — main web server for PPKE.

Provides REST API endpoints wrapping existing CLI functionality, plus
server-rendered HTML pages via Jinja2 + HTMX.

Run with:
    ppke serve
    # or directly:
    uvicorn ppke.web.app:app --reload
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ppke.config import Config

logger = logging.getLogger(__name__)

app = FastAPI(
    title="PPKE — Personal & Professional Knowledge Engine",
    version="2.0.0",
    description="Web interface for structured knowledge extraction from documents.",
)

# ── Static files & templates ──

_WEB_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=_WEB_DIR / "templates")

# ── In-memory job tracker for async ingestion ──

_jobs: dict[str, dict[str, Any]] = {}


# ── Helper functions ──


def _get_config() -> Config:
    return Config.load()


def _vault_path() -> Path:
    return _get_config().vault_path


def _book_dirs() -> list[Path]:
    vault = _vault_path()
    if not vault.exists():
        return []
    return sorted(
        [d for d in vault.iterdir() if d.is_dir() and d.name.startswith("Book_")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _load_book_meta(book_dir: Path) -> dict[str, Any]:
    """Load meta.yml for a book directory."""
    import yaml

    meta_path = book_dir / "meta.yml"
    if meta_path.exists():
        return yaml.safe_load(meta_path.read_text()) or {}
    return {"title": book_dir.name, "author": "Unknown"}


def _load_extractions(book_dir: Path) -> list[dict]:
    """Load extractions.json for a book directory."""
    path = book_dir / "extractions.json"
    if path.exists():
        return json.loads(path.read_text())
    return []


# ── HTML pages (server-rendered via Jinja2 + HTMX) ──


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard — library view with stats."""
    books = []
    for d in _book_dirs():
        meta = _load_book_meta(d)
        books.append({
            "folder": d.name,
            "title": meta.get("title", d.name),
            "author": meta.get("author", "Unknown"),
            "year": meta.get("year", ""),
            "chapters": meta.get("total_chapters", "?"),
            "paragraphs": meta.get("total_paragraphs", "?"),
            "status": meta.get("verification_status", "UNKNOWN"),
            "date": meta.get("ingest_date", ""),
        })

    config = _get_config()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "books": books,
        "total_books": len(books),
        "vault_path": str(config.vault_path),
        "provider": config.llm.provider,
        "model": config.llm.model,
    })


@app.get("/notebook/{folder}", response_class=HTMLResponse)
async def notebook_view(request: Request, folder: str):
    """Single notebook view — chat, concepts, source viewer."""
    book_dir = _vault_path() / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    meta = _load_book_meta(book_dir)

    # Load analysis files
    files = {}
    for fname in ["01_Raw_Structure.md", "02_Logical_Map.md", "03_Concept_Index.md",
                   "06_Patterns.md", "05_Coverage_Report.md"]:
        fpath = book_dir / fname
        files[fname] = fpath.read_text() if fpath.exists() else ""

    extractions = _load_extractions(book_dir)

    # Build chapter list
    chapters = []
    seen = set()
    for ext in extractions:
        pid = ext.get("paragraph_id", "")
        ch_num = pid.split(".")[0].strip("{}") if "." in pid else "00"
        if ch_num not in seen:
            seen.add(ch_num)
            chapters.append({"number": ch_num, "topic": ext.get("topic_sentence", "")[:80]})

    return templates.TemplateResponse("notebook.html", {
        "request": request,
        "folder": folder,
        "meta": meta,
        "files": files,
        "chapters": chapters,
        "extractions": extractions[:20],  # First 20 for initial render
        "total_extractions": len(extractions),
    })


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """File upload page."""
    from ppke.converter import SUPPORTED_EXTENSIONS

    return templates.TemplateResponse("upload.html", {
        "request": request,
        "supported_formats": sorted(SUPPORTED_EXTENSIONS),
    })


# ── REST API endpoints ──


@app.get("/api/books")
async def api_list_books():
    """List all ingested books with metadata."""
    books = []
    for d in _book_dirs():
        meta = _load_book_meta(d)
        books.append({
            "folder": d.name,
            "title": meta.get("title", d.name),
            "author": meta.get("author", "Unknown"),
            "year": meta.get("year"),
            "total_chapters": meta.get("total_chapters", 0),
            "total_paragraphs": meta.get("total_paragraphs", 0),
            "verification_status": meta.get("verification_status", "UNKNOWN"),
            "ingest_date": meta.get("ingest_date", ""),
        })
    return books


@app.get("/api/books/{folder}")
async def api_get_book(folder: str):
    """Get detailed info for a single book."""
    book_dir = _vault_path() / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    meta = _load_book_meta(book_dir)
    extractions = _load_extractions(book_dir)

    return {
        "folder": folder,
        "meta": meta,
        "total_extractions": len(extractions),
        "files": [f.name for f in book_dir.iterdir() if f.is_file()],
    }


@app.get("/api/books/{folder}/extractions")
async def api_get_extractions(
    folder: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Get paginated extractions for a book."""
    book_dir = _vault_path() / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    extractions = _load_extractions(book_dir)
    return {
        "total": len(extractions),
        "offset": offset,
        "limit": limit,
        "items": extractions[offset : offset + limit],
    }


@app.post("/api/query")
async def api_query(
    book: str = Form(...),
    question: str = Form(...),
):
    """Query a single book — returns structured answer with evidence."""
    import yaml
    from ppke.llm.client import LLMClient
    from ppke.llm.prompts import SINGLE_BOOK_QUERY_SYSTEM, SINGLE_BOOK_QUERY_USER

    config = _get_config()
    book_dir = _vault_path() / book
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {book}")

    meta = _load_book_meta(book_dir)
    raw_path = book_dir / "01_Raw_Structure.md"
    logical_path = book_dir / "02_Logical_Map.md"
    concept_path = book_dir / "03_Concept_Index.md"

    user_prompt = SINGLE_BOOK_QUERY_USER.format(
        book_title=meta.get("title", "Unknown"),
        author=meta.get("author", "Unknown"),
        question=question,
        raw_structure=raw_path.read_text()[:8000] if raw_path.exists() else "N/A",
        logical_map=logical_path.read_text()[:4000] if logical_path.exists() else "N/A",
        concept_index=concept_path.read_text()[:4000] if concept_path.exists() else "N/A",
    )

    client = LLMClient(config.llm)
    result = client.complete_json(SINGLE_BOOK_QUERY_SYSTEM, user_prompt)
    return result


@app.post("/api/cross-query")
async def api_cross_query(question: str = Form(...)):
    """Cross-book synthesis query."""
    from ppke.llm.client import LLMClient
    from ppke.pipeline.synthesizer import cross_book_synthesis

    config = _get_config()
    client = LLMClient(config.llm)
    result = cross_book_synthesis(client, config.vault_path, question)
    return result


@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=1), book: str | None = None):
    """Full-text search across all extractions."""
    results = []
    query_lower = q.lower()

    for d in _book_dirs():
        if book and d.name != book:
            continue

        meta = _load_book_meta(d)
        extractions = _load_extractions(d)

        for ext in extractions:
            searchable = " ".join([
                ext.get("original_text", ""),
                ext.get("topic_sentence", ""),
                " ".join(ext.get("explicit_claims", [])),
                " ".join(ext.get("defined_concepts", [])),
            ]).lower()

            if query_lower in searchable:
                # Find snippet
                idx = searchable.find(query_lower)
                start = max(0, idx - 60)
                end = min(len(searchable), idx + len(query_lower) + 60)
                snippet = ("..." if start > 0 else "") + searchable[start:end] + ("..." if end < len(searchable) else "")

                results.append({
                    "book": meta.get("title", d.name),
                    "folder": d.name,
                    "paragraph_id": ext.get("paragraph_id", "?"),
                    "topic": ext.get("topic_sentence", ""),
                    "snippet": snippet,
                })

        if len(results) >= 100:
            break

    return {"query": q, "total": len(results), "results": results}


@app.post("/api/upload")
async def api_upload(
    file: UploadFile = File(...),
    title: str = Form(...),
    author: str = Form(...),
    year: str = Form(""),
    domain: str = Form("philosophy"),
):
    """Upload and ingest a document.

    Accepts any supported file format (PDF, DOCX, images, audio, etc.).
    The file is first converted to Markdown, then run through the full
    ingestion pipeline. Returns a job ID for progress tracking.
    """
    from ppke.converter import convert_to_markdown

    config = _get_config()

    # Save uploaded file to temp location
    upload_dir = config.vault_path / ".uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = upload_dir / file.filename
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Convert to markdown
    try:
        markdown_text = convert_to_markdown(temp_path)
    except (ValueError, ImportError) as e:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(400, str(e))

    # Write markdown to temp file for the parser
    md_path = upload_dir / f"{temp_path.stem}.md"
    md_path.write_text(markdown_text)

    # Create background job
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "status": "running",
        "stage": "Starting ingestion...",
        "progress": 0,
        "book_folder": None,
        "error": None,
        "started": datetime.now().isoformat(),
    }

    # Run ingestion in background thread
    import threading

    def _run_ingest():
        try:
            from ppke.parser.markdown import parse_markdown_book
            from ppke.pipeline.orchestrator import ingest_book
            from ppke.progress.tracker import ProgressTracker
            from ppke.vectordb.store import VectorStore
            from ppke.graph.knowledge_graph import KnowledgeGraph

            book = parse_markdown_book(md_path, title, author, year or None)
            _jobs[job_id]["stage"] = f"Parsed: {len(book.chapters)} chapters"
            _jobs[job_id]["progress"] = 10

            tracker = ProgressTracker()
            vector_store = VectorStore(config.vault_path) if config.enable_vector_search else None
            knowledge_graph = KnowledgeGraph(config.vault_path) if config.enable_knowledge_graph else None

            def progress_cb(stage: str, detail: str):
                _jobs[job_id]["stage"] = f"[{stage}] {detail}"

            book_dir = ingest_book(
                book, config,
                domain=domain,
                progress_callback=progress_cb,
                tracker=tracker,
                vector_store=vector_store,
                knowledge_graph=knowledge_graph,
            )

            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["progress"] = 100
            _jobs[job_id]["book_folder"] = book_dir.name if hasattr(book_dir, "name") else str(book_dir)
            _jobs[job_id]["stage"] = "Ingestion complete!"

        except Exception as e:
            logger.exception("Ingestion failed for job %s", job_id)
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(e)
            _jobs[job_id]["stage"] = f"Failed: {e}"
        finally:
            # Clean up temp files
            temp_path.unlink(missing_ok=True)
            md_path.unlink(missing_ok=True)

    thread = threading.Thread(target=_run_ingest, daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "running"}


@app.get("/api/jobs/{job_id}")
async def api_job_status(job_id: str):
    """Check status of an ingestion job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    return job


@app.get("/api/stats")
async def api_stats():
    """Vault-wide statistics."""
    books = _book_dirs()
    total_chapters = 0
    total_paragraphs = 0
    total_concepts = 0

    for d in books:
        meta = _load_book_meta(d)
        total_chapters += meta.get("total_chapters", 0)
        total_paragraphs += meta.get("total_paragraphs", 0)
        # Count concepts from extraction data
        extractions = _load_extractions(d)
        for ext in extractions:
            total_concepts += len(ext.get("defined_concepts", []))

    return {
        "total_books": len(books),
        "total_chapters": total_chapters,
        "total_paragraphs": total_paragraphs,
        "total_concepts": total_concepts,
        "vault_path": str(_vault_path()),
    }


@app.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    """Interactive knowledge graph visualization page (Obsidian-style)."""
    books = []
    for d in _book_dirs():
        meta = _load_book_meta(d)
        books.append({"folder": d.name, "title": meta.get("title", d.name)})
    return templates.TemplateResponse("graph.html", {"request": request, "books": books})


@app.get("/api/graph")
async def api_graph_data(book: str | None = None):
    """Return graph data in D3-compatible format (nodes + links).

    If ``book`` is specified, return only nodes/edges related to that book.
    Otherwise return the full graph.
    """
    vault = _vault_path()
    graph_path = vault / "knowledge_graph.json"

    if graph_path.exists():
        data = json.loads(graph_path.read_text())
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        if book:
            relevant_ids = set()
            for edge in edges:
                if book in edge.get("source", "") or book in edge.get("target", ""):
                    relevant_ids.add(edge["source"])
                    relevant_ids.add(edge["target"])
            nodes = [n for n in nodes if n["id"] in relevant_ids]
            edges = [e for e in edges if e["source"] in relevant_ids and e["target"] in relevant_ids]

        d3_nodes = []
        for n in nodes:
            node_type = n.get("type", "concept")
            d3_nodes.append({
                "id": n["id"], "label": n.get("label", n["id"]),
                "type": node_type,
                "group": {"concept": 1, "book": 2, "paragraph": 3}.get(node_type, 1),
                "size": n.get("weight", 1),
            })
        d3_links = [{"source": e.get("source"), "target": e.get("target"),
                      "relation": e.get("relation", "related_to")} for e in edges]
        return {"nodes": d3_nodes, "links": d3_links}

    # Fallback: build from extractions on-the-fly
    nodes_map: dict[str, dict] = {}
    links: list[dict] = []

    for d in _book_dirs():
        if book and d.name != book:
            continue
        meta = _load_book_meta(d)
        book_id = f"book:{d.name}"
        nodes_map[book_id] = {
            "id": book_id, "label": meta.get("title", d.name),
            "type": "book", "group": 2, "size": 5,
        }
        extractions = _load_extractions(d)
        for ext in extractions:
            concepts = ext.get("defined_concepts", [])
            for concept in concepts:
                c_id = f"concept:{concept.lower().strip()}"
                if c_id not in nodes_map:
                    nodes_map[c_id] = {
                        "id": c_id, "label": concept, "type": "concept", "group": 1, "size": 1,
                    }
                else:
                    nodes_map[c_id]["size"] = nodes_map[c_id].get("size", 1) + 1
                links.append({"source": book_id, "target": c_id, "relation": "defines"})
            for i, c1 in enumerate(concepts):
                for c2 in concepts[i + 1:]:
                    links.append({
                        "source": f"concept:{c1.lower().strip()}",
                        "target": f"concept:{c2.lower().strip()}",
                        "relation": "related_to",
                    })

    return {"nodes": list(nodes_map.values()), "links": links}


@app.post("/api/audio-overview")
async def api_generate_audio_overview(
    folder: str = Form(...),
    tts_provider: str = Form("edge"),
):
    """Generate a NotebookLM-style audio overview for a book."""
    from ppke.audio.overview import generate_script, synthesize_audio
    from ppke.llm.client import LLMClient

    config = _get_config()
    book_dir = _vault_path() / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    client = LLMClient(config.llm)

    # Generate script
    try:
        script = generate_script(book_dir, client)
    except Exception as e:
        raise HTTPException(500, f"Script generation failed: {e}")

    # Save script for reference
    script_path = book_dir / "audio_script.json"
    script_path.write_text(json.dumps(script, indent=2))

    # Synthesize audio
    audio_path = book_dir / "audio_overview.mp3"
    try:
        synthesize_audio(script, audio_path, provider=tts_provider)
    except Exception as e:
        raise HTTPException(500, f"Audio synthesis failed: {e}")

    return {
        "status": "completed",
        "audio_path": str(audio_path),
        "script": script,
    }


@app.get("/api/audio/{folder}")
async def api_serve_audio(folder: str):
    """Serve the generated audio overview file."""
    audio_path = _vault_path() / folder / "audio_overview.mp3"
    if not audio_path.exists():
        raise HTTPException(404, "Audio overview not generated yet")

    def iterfile():
        with open(audio_path, "rb") as f:
            yield from f

    return StreamingResponse(iterfile(), media_type="audio/mpeg")


@app.get("/api/config")
async def api_config():
    """Get current configuration (redacts API keys)."""
    config = _get_config()
    return {
        "vault_path": str(config.vault_path),
        "provider": config.llm.provider,
        "model": config.llm.model,
        "small_model": config.llm.effective_small_model,
        "default_domain": config.default_domain,
        "vector_search": config.enable_vector_search,
        "knowledge_graph": config.enable_knowledge_graph,
        "has_api_key": bool(config.llm.active_api_key),
    }
