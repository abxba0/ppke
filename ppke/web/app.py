"""FastAPI application — main web server for PPKE.

Phase 1 complete: dark mode, markdown chat, SSE streaming, toasts,
keyboard shortcuts, settings page, error middleware, path traversal
protection, mobile responsive.

Phase 2 complete: URL/YouTube import, .tex/.csv/.xlsx/.zip converters,
hybrid OCR with confidence scoring, multi-file upload.

Run with:
    ppke serve
    uvicorn ppke.web.app:app --reload
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from typing import List as TypingList
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ppke.config import Config, SUPPORTED_PROVIDERS, PROVIDER_ENV_VARS

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

# ── In-memory job tracker ──

_jobs: dict[str, dict[str, Any]] = {}


# ── Error handling middleware ──


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return clean validation errors instead of 422 blobs."""
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append(f"{field}: {error['msg']}")
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": errors},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all error handler for unhandled exceptions."""
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}"},
    )


# ── Path traversal protection ──

# Only allow alphanumerics, underscores, hyphens, dots in folder names
_SAFE_FOLDER_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def _safe_folder(folder: str) -> str:
    """Validate folder name to prevent path traversal attacks."""
    if not _SAFE_FOLDER_RE.match(folder) or ".." in folder:
        raise HTTPException(400, "Invalid folder name")
    return folder


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
    import yaml

    meta_path = book_dir / "meta.yml"
    if meta_path.exists():
        return yaml.safe_load(meta_path.read_text()) or {}
    return {"title": book_dir.name, "author": "Unknown"}


def _load_extractions(book_dir: Path) -> list[dict]:
    path = book_dir / "extractions.json"
    if path.exists():
        return json.loads(path.read_text())
    return []


# ── HTML pages ──


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
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
    folder = _safe_folder(folder)
    book_dir = _vault_path() / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    meta = _load_book_meta(book_dir)

    files = {}
    for fname in ["01_Raw_Structure.md", "02_Logical_Map.md", "03_Concept_Index.md",
                   "06_Patterns.md", "05_Coverage_Report.md"]:
        fpath = book_dir / fname
        files[fname] = fpath.read_text() if fpath.exists() else ""

    extractions = _load_extractions(book_dir)

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
        "extractions": extractions[:20],
        "total_extractions": len(extractions),
    })


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    from ppke.converter import SUPPORTED_EXTENSIONS

    return templates.TemplateResponse("upload.html", {
        "request": request,
        "supported_formats": sorted(SUPPORTED_EXTENSIONS),
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    config = _get_config()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "config": {
            "vault_path": str(config.vault_path),
            "provider": config.llm.provider,
            "model": config.llm.model,
            "default_domain": config.default_domain or "philosophy",
            "has_api_key": bool(config.llm.active_api_key),
            "vector_search": config.enable_vector_search,
            "knowledge_graph": config.enable_knowledge_graph,
        },
        "providers": SUPPORTED_PROVIDERS,
    })


@app.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    books = []
    for d in _book_dirs():
        meta = _load_book_meta(d)
        books.append({"folder": d.name, "title": meta.get("title", d.name)})
    return templates.TemplateResponse("graph.html", {"request": request, "books": books})


# ── REST API endpoints ──


@app.get("/api/books")
async def api_list_books():
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
    folder = _safe_folder(folder)
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
    folder = _safe_folder(folder)
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
    book = _safe_folder(book)
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


@app.get("/api/query/stream")
async def api_query_stream(
    book: str = Query(...),
    question: str = Query(...),
):
    """SSE streaming endpoint for book queries.

    Returns server-sent events with tokens as they arrive, providing
    a real-time typing effect in the chat UI.
    """
    book = _safe_folder(book)
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

    async def event_generator():
        """Generate SSE events. Falls back to single JSON response."""
        try:
            client = LLMClient(config.llm)

            # Try streaming if the client supports it
            if hasattr(client, 'complete_stream'):
                for token in client.complete_stream(SINGLE_BOOK_QUERY_SYSTEM, user_prompt):
                    yield f"data: {json.dumps({'token': token})}\n\n"
            else:
                # Non-streaming fallback: get full result and send as single event
                result = client.complete_json(SINGLE_BOOK_QUERY_SYSTEM, user_prompt)
                answer = result.get("answer", "No answer generated.")
                # Send answer in chunks to simulate streaming
                words = answer.split(" ")
                chunk = []
                for word in words:
                    chunk.append(word)
                    if len(chunk) >= 3:
                        yield f"data: {json.dumps({'token': ' '.join(chunk) + ' '})}\n\n"
                        chunk = []
                if chunk:
                    yield f"data: {json.dumps({'token': ' '.join(chunk)})}\n\n"

                # Send metadata
                quotes = result.get("verbatim_quotes", [])
                if quotes:
                    yield f"data: {json.dumps({'quotes': quotes})}\n\n"
                confidence = result.get("confidence")
                if confidence:
                    yield f"data: {json.dumps({'confidence': confidence})}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("SSE query failed")
            yield f"data: {json.dumps({'token': f'Error: {e}'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/cross-query")
async def api_cross_query(question: str = Form(...)):
    from ppke.llm.client import LLMClient
    from ppke.pipeline.synthesizer import cross_book_synthesis

    config = _get_config()
    client = LLMClient(config.llm)
    result = cross_book_synthesis(client, config.vault_path, question)
    return result


@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=1), book: str | None = None):
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
    files: TypingList[UploadFile] = File(...),
    title: str = Form(...),
    author: str = Form(...),
    year: str = Form(""),
    domain: str = Form("philosophy"),
):
    """Upload and ingest one or more documents.

    Accepts a list of files.  Each file gets its own background ingestion job.
    Returns ``{"jobs": [...]}`` so the UI can poll each independently.
    """
    from ppke.converter import convert_to_markdown

    config = _get_config()
    upload_dir = config.vault_path / ".uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    job_ids: list[str] = []

    for file in files:
        safe_filename = re.sub(r"[^\w\.\-]", "_", file.filename or "upload")
        temp_path = upload_dir / safe_filename

        content = await file.read()
        temp_path.write_bytes(content)

        try:
            markdown_text = convert_to_markdown(temp_path)
        except (ValueError, ImportError) as e:
            temp_path.unlink(missing_ok=True)
            raise HTTPException(400, str(e))

        # Use the original (unsuffixed) stem so we don't duplicate extensions
        md_path = upload_dir / f"{temp_path.stem}.md"
        md_path.write_text(markdown_text)

        # Per-file title: use provided title for single uploads; append filename for batch
        file_title = title if len(files) == 1 else f"{title} — {temp_path.stem}"

        job_id = str(uuid.uuid4())[:8]
        _jobs[job_id] = {
            "status": "running",
            "stage": "Starting ingestion...",
            "progress": 0,
            "book_folder": None,
            "error": None,
            "started": datetime.now().isoformat(),
            "filename": safe_filename,
        }
        job_ids.append(job_id)

        import threading

        def _run_ingest(
            jid=job_id,
            tp=temp_path,
            mp=md_path,
            ftitle=file_title,
        ):
            try:
                from ppke.parser.markdown import parse_markdown_book
                from ppke.pipeline.orchestrator import ingest_book
                from ppke.progress.tracker import ProgressTracker
                from ppke.vectordb.store import VectorStore
                from ppke.graph.knowledge_graph import KnowledgeGraph

                book = parse_markdown_book(mp, ftitle, author, year or None)
                _jobs[jid]["stage"] = f"Parsed: {len(book.chapters)} chapters"
                _jobs[jid]["progress"] = 10

                tracker = ProgressTracker()
                vector_store = VectorStore(config.vault_path) if config.enable_vector_search else None
                knowledge_graph = KnowledgeGraph(config.vault_path) if config.enable_knowledge_graph else None

                def progress_cb(stage: str, detail: str):
                    _jobs[jid]["stage"] = f"[{stage}] {detail}"

                book_dir = ingest_book(
                    book, config,
                    domain=domain,
                    progress_callback=progress_cb,
                    tracker=tracker,
                    vector_store=vector_store,
                    knowledge_graph=knowledge_graph,
                )

                _jobs[jid]["status"] = "completed"
                _jobs[jid]["progress"] = 100
                _jobs[jid]["book_folder"] = book_dir.name if hasattr(book_dir, "name") else str(book_dir)
                _jobs[jid]["stage"] = "Ingestion complete!"

            except Exception as e:
                logger.exception("Ingestion failed for job %s", jid)
                _jobs[jid]["status"] = "failed"
                _jobs[jid]["error"] = str(e)
                _jobs[jid]["stage"] = f"Failed: {e}"
            finally:
                tp.unlink(missing_ok=True)
                mp.unlink(missing_ok=True)

        threading.Thread(target=_run_ingest, daemon=True).start()

    # Backwards-compatible: single file → return {job_id, status}
    # Multiple files → return {jobs: [...], status}
    if len(job_ids) == 1:
        return {"job_id": job_ids[0], "status": "running"}
    return {"jobs": job_ids, "status": "running", "count": len(job_ids)}


@app.post("/api/import-url")
async def api_import_url(
    url: str = Form(...),
    title: str = Form(""),
    author: str = Form(""),
    year: str = Form(""),
    domain: str = Form("philosophy"),
):
    """Import a web page or YouTube video URL and ingest it.

    Detects YouTube URLs automatically and uses yt-dlp + Whisper.
    All other URLs are scraped with trafilatura.

    Returns ``{"job_id": ..., "status": "running"}``.
    """
    # Basic URL validation
    url = url.strip()
    if not url.startswith(("http://", "https://", "www.")):
        raise HTTPException(400, "Please provide a valid URL starting with http:// or https://")

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    from ppke.converter.url import is_youtube_url

    is_yt = is_youtube_url(url)

    config = _get_config()
    upload_dir = config.vault_path / ".uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "status": "running",
        "stage": "Fetching URL...",
        "progress": 0,
        "book_folder": None,
        "error": None,
        "started": datetime.now().isoformat(),
        "url": url,
        "source_type": "youtube" if is_yt else "web",
    }

    import threading

    def _run_url_ingest():
        md_path: Path | None = None
        try:
            _jobs[job_id]["stage"] = "Downloading content..."
            _jobs[job_id]["progress"] = 5

            if is_yt:
                from ppke.converter.youtube import convert_youtube
                markdown_text = convert_youtube(url)
            else:
                from ppke.converter.url import convert_url
                markdown_text = convert_url(url)

            _jobs[job_id]["stage"] = "Content extracted — starting ingestion..."
            _jobs[job_id]["progress"] = 20

            # Derive title from Markdown h1 if not provided
            ingest_title = title.strip()
            if not ingest_title:
                for line in markdown_text.splitlines():
                    if line.startswith("# "):
                        ingest_title = line[2:].strip()
                        break
                if not ingest_title:
                    from urllib.parse import urlparse
                    ingest_title = urlparse(url).netloc or "Imported Article"

            ingest_author = author.strip() or "Web Import"

            # Write to temp .md file
            safe_stem = re.sub(r"[^\w\-]", "_", ingest_title)[:60]
            md_path = upload_dir / f"{safe_stem}_{job_id}.md"
            md_path.write_text(markdown_text)

            from ppke.parser.markdown import parse_markdown_book
            from ppke.pipeline.orchestrator import ingest_book
            from ppke.progress.tracker import ProgressTracker
            from ppke.vectordb.store import VectorStore
            from ppke.graph.knowledge_graph import KnowledgeGraph

            book = parse_markdown_book(md_path, ingest_title, ingest_author, year or None)
            _jobs[job_id]["stage"] = f"Parsed: {len(book.chapters)} chapters"
            _jobs[job_id]["progress"] = 30

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
            logger.exception("URL ingestion failed for job %s (url=%s)", job_id, url)
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(e)
            _jobs[job_id]["stage"] = f"Failed: {e}"
        finally:
            if md_path is not None:
                md_path.unlink(missing_ok=True)

    threading.Thread(target=_run_url_ingest, daemon=True).start()

    return {"job_id": job_id, "status": "running", "source_type": "youtube" if is_yt else "web"}


@app.get("/api/jobs/{job_id}")
async def api_job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    return job


@app.get("/api/stats")
async def api_stats():
    books = _book_dirs()
    total_chapters = 0
    total_paragraphs = 0
    total_concepts = 0

    for d in books:
        meta = _load_book_meta(d)
        total_chapters += meta.get("total_chapters", 0)
        total_paragraphs += meta.get("total_paragraphs", 0)
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


@app.get("/api/graph")
async def api_graph_data(book: str | None = None):
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

    # Fallback: build from extractions
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
    folder = _safe_folder(folder)
    from ppke.audio.overview import generate_script, synthesize_audio
    from ppke.llm.client import LLMClient

    config = _get_config()
    book_dir = _vault_path() / folder
    if not book_dir.exists():
        raise HTTPException(404, f"Book not found: {folder}")

    client = LLMClient(config.llm)

    try:
        script = generate_script(book_dir, client)
    except Exception as e:
        raise HTTPException(500, f"Script generation failed: {e}")

    script_path = book_dir / "audio_script.json"
    script_path.write_text(json.dumps(script, indent=2))

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
    folder = _safe_folder(folder)
    audio_path = _vault_path() / folder / "audio_overview.mp3"
    if not audio_path.exists():
        raise HTTPException(404, "Audio overview not generated yet")

    def iterfile():
        with open(audio_path, "rb") as f:
            yield from f

    return StreamingResponse(iterfile(), media_type="audio/mpeg")


@app.get("/api/config")
async def api_config():
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


@app.post("/api/settings")
async def api_update_settings(
    provider: str = Form(...),
    model: str = Form(...),
    api_key: str = Form(""),
    default_domain: str = Form("philosophy"),
    vector_search: bool = Form(False),
    knowledge_graph: bool = Form(False),
):
    """Update PPKE configuration via the web UI."""
    from ppke.config import save_env_file

    config = _get_config()
    config.llm.provider = provider
    config.llm.model = model
    config.default_domain = default_domain
    config.enable_vector_search = vector_search
    config.enable_knowledge_graph = knowledge_graph
    config.save()

    # Save API key if provided
    if api_key.strip():
        env_var = PROVIDER_ENV_VARS.get(provider, "API_KEY")
        save_env_file({env_var: api_key.strip()})

    return {"status": "ok", "message": "Settings saved"}


@app.get("/api/health")
async def api_health():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.0.0"}
