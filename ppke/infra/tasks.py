"""Task queue — Celery with Redis broker, fallback to threading.

When Redis + Celery are available, background jobs are enqueued as real
distributed tasks with persistence, retry logic, and result tracking.
When unavailable, falls back to daemon threads (single-process mode).

Environment variables:
    CELERY_BROKER_URL — Redis URL for Celery broker (default: redis://localhost:6379/0)
    CELERY_RESULT_BACKEND — Result backend URL (default: same as broker)
    PPKE_TASK_BACKEND — Force "celery" or "thread" (auto-detected if unset)
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Job store (in-memory or Redis-backed) ──

_jobs: dict[str, dict[str, Any]] = {}

_redis_client: Any = None


def _get_redis():
    """Return a Redis client if available, else None."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.environ.get("REDIS_URL") or os.environ.get("CELERY_BROKER_URL")
    if not redis_url:
        return None
    try:
        import redis
        _redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        logger.info("Redis connected for job store: %s", redis_url)
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def _job_key(job_id: str) -> str:
    return f"ppke:job:{job_id}"


def set_job(job_id: str, data: dict[str, Any]) -> None:
    """Store job state in Redis (if available) and in-memory."""
    import json as _json
    _jobs[job_id] = data
    r = _get_redis()
    if r:
        try:
            r.setex(_job_key(job_id), 86400, _json.dumps(data, default=str))
        except Exception:
            pass


def get_job(job_id: str) -> dict[str, Any] | None:
    """Retrieve job state from memory first, then Redis."""
    import json as _json
    if job_id in _jobs:
        return _jobs[job_id]
    r = _get_redis()
    if r:
        try:
            raw = r.get(_job_key(job_id))
            if raw:
                data = _json.loads(raw)
                _jobs[job_id] = data
                return data
        except Exception:
            pass
    return None


def update_job(job_id: str, **fields: Any) -> None:
    """Partially update a job's state."""
    data = get_job(job_id)
    if data:
        data.update(fields)
        set_job(job_id, data)


# ── Celery app (created lazily) ──

_celery_app: Any = None


def _get_celery_app():
    """Create and return a Celery application, or None if unavailable."""
    global _celery_app
    if _celery_app is not None:
        return _celery_app

    backend_env = os.environ.get("PPKE_TASK_BACKEND", "").lower()
    if backend_env == "thread":
        return None

    broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    result_backend = os.environ.get("CELERY_RESULT_BACKEND", broker_url)

    try:
        from celery import Celery
        app = Celery("ppke", broker=broker_url, backend=result_backend)
        app.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="UTC",
            enable_utc=True,
            task_track_started=True,
            task_acks_late=True,
            worker_prefetch_multiplier=1,
            task_soft_time_limit=3600,
            task_time_limit=7200,
            task_default_retry_delay=60,
            task_max_retries=3,
        )
        # Verify broker connectivity
        conn = app.connection()
        conn.ensure_connection(max_retries=1, timeout=2)
        conn.close()
        _celery_app = app
        logger.info("Celery connected: broker=%s", broker_url)
        return _celery_app
    except Exception as exc:
        logger.info("Celery unavailable (%s), using thread fallback", exc)
        return None


def get_celery_app():
    """Public accessor for the Celery app (may be None)."""
    return _get_celery_app()


# ── Task execution ──


def create_job(
    extra: dict[str, Any] | None = None,
) -> str:
    """Create a new job entry and return its ID."""
    job_id = str(uuid.uuid4())[:8]
    data = {
        "status": "running",
        "stage": "Starting...",
        "progress": 0,
        "book_folder": None,
        "error": None,
        "started": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        data.update(extra)
    set_job(job_id, data)
    return job_id


def run_task(
    func: Callable[..., Any],
    *args: Any,
    job_id: str | None = None,
    **kwargs: Any,
) -> str:
    """Execute a function as a background task.

    Uses Celery if available, otherwise a daemon thread.
    Returns the job_id used for tracking.
    """
    if job_id is None:
        job_id = create_job()

    celery_app = _get_celery_app()

    if celery_app is not None:
        # Register function as a Celery task dynamically
        task_name = f"ppke.task.{func.__name__}_{job_id}"
        try:
            @celery_app.task(name=task_name, bind=False)
            def _celery_wrapper():
                return func(*args, **kwargs)

            _celery_wrapper.apply_async()
            logger.info("Task %s dispatched via Celery", job_id)
        except Exception as exc:
            logger.warning("Celery dispatch failed (%s), falling back to thread", exc)
            _run_in_thread(func, args, kwargs, job_id)
    else:
        _run_in_thread(func, args, kwargs, job_id)

    return job_id


def _run_in_thread(
    func: Callable[..., Any],
    args: tuple,
    kwargs: dict,
    job_id: str,
) -> None:
    """Run function in a daemon thread."""
    def _wrapper():
        try:
            func(*args, **kwargs)
        except Exception as exc:
            logger.exception("Task %s failed in thread: %s", job_id, exc)
            update_job(job_id, status="failed", error=str(exc), stage=f"Failed: {exc}")

    t = threading.Thread(target=_wrapper, daemon=True, name=f"ppke-task-{job_id}")
    t.start()
    logger.debug("Task %s running in thread", job_id)
