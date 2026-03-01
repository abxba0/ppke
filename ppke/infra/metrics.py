"""Prometheus metrics collection.

Exposes a ``/metrics`` endpoint and middleware for automatic request
latency tracking, ingestion duration, and custom counters.

Environment variables:
    PPKE_METRICS_ENABLED — "true" to enable (default: "true")
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Prometheus client (lazy import) ──

_metrics_enabled: bool | None = None
_registry: Any = None


def is_metrics_enabled() -> bool:
    global _metrics_enabled
    if _metrics_enabled is not None:
        return _metrics_enabled
    _metrics_enabled = os.environ.get("PPKE_METRICS_ENABLED", "true").lower() == "true"
    return _metrics_enabled


def _get_prometheus():
    """Try to import prometheus_client, return module or None."""
    try:
        import prometheus_client
        return prometheus_client
    except ImportError:
        return None


# ── Metric objects (created lazily) ──

_http_requests_total: Any = None
_http_request_duration: Any = None
_http_requests_in_progress: Any = None
_ingestion_duration: Any = None
_ingestion_total: Any = None
_llm_tokens_total: Any = None
_llm_cost_total: Any = None
_active_jobs: Any = None
_cache_hits: Any = None
_cache_misses: Any = None


def _ensure_metrics():
    """Initialize all Prometheus metric objects."""
    global _http_requests_total, _http_request_duration, _http_requests_in_progress
    global _ingestion_duration, _ingestion_total, _llm_tokens_total, _llm_cost_total
    global _active_jobs, _cache_hits, _cache_misses

    if _http_requests_total is not None:
        return True

    prom = _get_prometheus()
    if prom is None:
        return False

    _http_requests_total = prom.Counter(
        "ppke_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status_code"],
    )
    _http_request_duration = prom.Histogram(
        "ppke_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    )
    _http_requests_in_progress = prom.Gauge(
        "ppke_http_requests_in_progress",
        "Number of HTTP requests currently in progress",
        ["method"],
    )
    _ingestion_duration = prom.Histogram(
        "ppke_ingestion_duration_seconds",
        "Book ingestion duration in seconds",
        ["source_type"],
        buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800),
    )
    _ingestion_total = prom.Counter(
        "ppke_ingestion_total",
        "Total ingestion jobs",
        ["source_type", "status"],
    )
    _llm_tokens_total = prom.Counter(
        "ppke_llm_tokens_total",
        "Total LLM tokens used",
        ["provider", "model"],
    )
    _llm_cost_total = prom.Counter(
        "ppke_llm_cost_usd_total",
        "Total LLM cost in USD",
        ["provider"],
    )
    _active_jobs = prom.Gauge(
        "ppke_active_jobs",
        "Number of currently running background jobs",
    )
    _cache_hits = prom.Counter(
        "ppke_cache_hits_total",
        "Total cache hits",
    )
    _cache_misses = prom.Counter(
        "ppke_cache_misses_total",
        "Total cache misses",
    )

    logger.info("Prometheus metrics initialized")
    return True


# ── Public metric recording functions ──


def record_request(method: str, path: str, status_code: int, duration: float) -> None:
    """Record an HTTP request metric."""
    if not is_metrics_enabled() or not _ensure_metrics():
        return
    # Normalize path to avoid high cardinality
    normalized = _normalize_path(path)
    _http_requests_total.labels(method=method, path=normalized, status_code=str(status_code)).inc()
    _http_request_duration.labels(method=method, path=normalized).observe(duration)


def record_request_start(method: str) -> None:
    if not is_metrics_enabled() or not _ensure_metrics():
        return
    _http_requests_in_progress.labels(method=method).inc()


def record_request_end(method: str) -> None:
    if not is_metrics_enabled() or not _ensure_metrics():
        return
    _http_requests_in_progress.labels(method=method).dec()


def record_ingestion(source_type: str, status: str, duration: float) -> None:
    """Record a book ingestion metric."""
    if not is_metrics_enabled() or not _ensure_metrics():
        return
    _ingestion_total.labels(source_type=source_type, status=status).inc()
    if status == "completed":
        _ingestion_duration.labels(source_type=source_type).observe(duration)


def record_llm_usage(provider: str, model: str, tokens: int, cost_usd: float) -> None:
    """Record LLM token usage."""
    if not is_metrics_enabled() or not _ensure_metrics():
        return
    _llm_tokens_total.labels(provider=provider, model=model).inc(tokens)
    _llm_cost_total.labels(provider=provider).inc(cost_usd)


def record_active_jobs(count: int) -> None:
    if not is_metrics_enabled() or not _ensure_metrics():
        return
    _active_jobs.set(count)


def record_cache_hit() -> None:
    if not is_metrics_enabled() or not _ensure_metrics():
        return
    _cache_hits.inc()


def record_cache_miss() -> None:
    if not is_metrics_enabled() or not _ensure_metrics():
        return
    _cache_misses.inc()


def _normalize_path(path: str) -> str:
    """Reduce path cardinality by replacing dynamic segments."""
    parts = path.rstrip("/").split("/")
    normalized = []
    for i, part in enumerate(parts):
        if not part:
            continue
        # Replace UUID-like segments and hash segments
        if len(part) >= 8 and any(c.isdigit() for c in part):
            # Check if it looks like a book folder or ID
            if part.startswith("Book_") or len(part) == 8:
                normalized.append("{id}")
                continue
        normalized.append(part)
    return "/" + "/".join(normalized) if normalized else "/"


# ── Metrics endpoint ──


def generate_metrics() -> str:
    """Generate Prometheus text-format metrics output."""
    prom = _get_prometheus()
    if prom is None:
        return "# prometheus_client not installed\n"
    _ensure_metrics()
    return prom.generate_latest(prom.REGISTRY).decode("utf-8")


# ── ASGI Middleware ──


class MetricsMiddleware:
    """ASGI middleware that records request metrics."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        if not is_metrics_enabled():
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # Don't track the metrics endpoint itself
        if path == "/metrics":
            return await self.app(scope, receive, send)

        record_request_start(method)
        start = time.time()
        status_code = 500

        async def send_wrapper(message: dict):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.time() - start
            record_request_end(method)
            record_request(method, path, status_code, duration)
