"""Structured logging — JSON format with request IDs.

Configures Python's logging module to output structured JSON logs
suitable for log aggregation (ELK, Datadog, CloudWatch, etc.).

Environment variables:
    PPKE_LOG_FORMAT — "json" or "text" (default: "json" in production, "text" in dev)
    PPKE_LOG_LEVEL — Logging level (default: "INFO")
    PPKE_ENVIRONMENT — "production", "staging", or "development" (default: "development")
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# ── Request ID context ──

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request ID."""
    return _request_id.get()


def set_request_id(request_id: str | None = None) -> str:
    """Set (or generate) a request ID for the current context."""
    rid = request_id or str(uuid.uuid4())[:12]
    _request_id.set(rid)
    return rid


# ── JSON Log Formatter ──


class JSONFormatter(logging.Formatter):
    """Outputs each log record as a JSON object, one per line."""

    def __init__(self, service_name: str = "ppke"):
        super().__init__()
        self.service_name = service_name
        self.hostname = os.environ.get("HOSTNAME", "unknown")
        self.environment = os.environ.get("PPKE_ENVIRONMENT", "development")

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "environment": self.environment,
            "hostname": self.hostname,
        }

        # Add request ID if available
        request_id = get_request_id()
        if request_id:
            log_entry["request_id"] = request_id

        # Add source location
        log_entry["source"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add exception info
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Add any extra fields
        for key in ("request_method", "request_path", "status_code",
                     "duration_ms", "user_id", "client_ip", "job_id",
                     "book_folder", "tokens_used", "cost_usd"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


# ── Text Formatter (dev mode) ──


class DetailedTextFormatter(logging.Formatter):
    """Human-readable format with request ID and color."""

    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        request_id = get_request_id()
        rid_str = f" [{request_id}]" if request_id else ""
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        msg = f"{color}{ts} {record.levelname:8s}{self.RESET}{rid_str} {record.name}: {record.getMessage()}"
        if record.exc_info and record.exc_info[0] is not None:
            msg += "\n" + self.formatException(record.exc_info)
        return msg


# ── Configuration ──


def configure_logging(
    level: str | None = None,
    log_format: str | None = None,
    service_name: str = "ppke",
) -> None:
    """Configure the root logger with structured output.

    Call this once at application startup (before creating the FastAPI app).
    """
    level = (level or os.environ.get("PPKE_LOG_LEVEL", "INFO")).upper()
    environment = os.environ.get("PPKE_ENVIRONMENT", "development")

    if log_format is None:
        log_format = os.environ.get("PPKE_LOG_FORMAT", "")
        if not log_format:
            log_format = "json" if environment == "production" else "text"

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level, logging.INFO))

    if log_format == "json":
        handler.setFormatter(JSONFormatter(service_name=service_name))
    else:
        handler.setFormatter(DetailedTextFormatter())

    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "httpcore", "httpx", "urllib3", "chromadb"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("ppke").info(
        "Logging configured: level=%s, format=%s, environment=%s",
        level, log_format, environment,
    )


# ── FastAPI Middleware ──


class RequestLoggingMiddleware:
    """ASGI middleware that adds request IDs and logs request/response."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        request_id = set_request_id()
        start_time = time.time()

        path = scope.get("path", "")
        method = scope.get("method", "")
        client = scope.get("client", ("", 0))
        client_ip = client[0] if client else ""

        status_code = 0

        async def send_wrapper(message: dict):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                # Inject request ID header
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = dict(message, headers=headers)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.time() - start_time) * 1000, 1)
            # Skip health check and static file logging
            if not path.startswith(("/api/health", "/static")):
                access_logger = logging.getLogger("ppke.access")
                access_logger.info(
                    "%s %s %d %.1fms",
                    method, path, status_code, duration_ms,
                    extra={
                        "request_method": method,
                        "request_path": path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "client_ip": client_ip,
                        "request_id": request_id,
                    },
                )
