"""Comprehensive tests for Phase 8 infrastructure modules.

Covers: cache, tasks, logging_config, metrics, sentry_integration,
storage, and auth/database PostgreSQL wrapper + cost queries.
"""

from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
import tempfile
import time
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ═══════════════════════════════════════════════════════════════════
# Cache tests
# ═══════════════════════════════════════════════════════════════════


class TestMemoryCache:
    def setup_method(self):
        from ppke.infra.cache import MemoryCache
        self.cache = MemoryCache(max_size=5)

    def test_set_and_get(self):
        self.cache.set("k1", "v1")
        assert self.cache.get("k1") == "v1"

    def test_get_missing(self):
        assert self.cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        self.cache.set("k2", "v2", ttl=1)
        assert self.cache.get("k2") == "v2"
        time.sleep(1.1)
        assert self.cache.get("k2") is None

    def test_no_ttl(self):
        self.cache.set("k3", "v3", ttl=0)
        assert self.cache.get("k3") == "v3"

    def test_delete_existing(self):
        self.cache.set("k4", "v4")
        assert self.cache.delete("k4") is True
        assert self.cache.get("k4") is None

    def test_delete_missing(self):
        assert self.cache.delete("missing") is False

    def test_clear(self):
        self.cache.set("a", 1)
        self.cache.set("b", 2)
        self.cache.clear()
        assert self.cache.get("a") is None
        assert self.cache.get("b") is None

    def test_lru_eviction(self):
        for i in range(6):
            self.cache.set(f"item{i}", i)
        # item0 should have been evicted (max_size=5)
        assert self.cache.get("item0") is None
        assert self.cache.get("item5") == 5

    def test_incr_new_key(self):
        val = self.cache.incr("counter1")
        assert val == 1

    def test_incr_existing_key(self):
        self.cache.incr("counter2")
        val = self.cache.incr("counter2")
        assert val == 2

    def test_incr_expired_key(self):
        self.cache.incr("counter3", ttl=1)
        time.sleep(1.1)
        val = self.cache.incr("counter3", ttl=60)
        assert val == 1  # Reset after expiry

    def test_lru_move_to_end(self):
        """Accessing a key moves it to the end, preventing eviction."""
        for i in range(5):
            self.cache.set(f"x{i}", i)
        # Access x0 to make it recently used
        self.cache.get("x0")
        # Add a new item to trigger eviction of x1 (oldest unused)
        self.cache.set("new", 99)
        assert self.cache.get("x0") == 0  # Still alive
        assert self.cache.get("x1") is None  # Evicted

    def test_complex_values(self):
        """Test caching of complex data structures."""
        data = {"items": [1, 2, 3], "nested": {"a": True}}
        self.cache.set("complex", data)
        assert self.cache.get("complex") == data


class TestRedisCache:
    """Test RedisCache with mocked redis client."""

    def setup_method(self):
        import sys
        self.mock_client = MagicMock()
        self.mock_client.ping.return_value = True
        # Create a fake redis module and inject it into sys.modules
        self.fake_redis_mod = MagicMock()
        self.fake_redis_mod.Redis.from_url.return_value = self.mock_client
        self._orig_redis = sys.modules.get("redis")
        sys.modules["redis"] = self.fake_redis_mod

    def teardown_method(self):
        import sys
        if self._orig_redis is None:
            sys.modules.pop("redis", None)
        else:
            sys.modules["redis"] = self._orig_redis

    def _make_cache(self):
        from ppke.infra.cache import RedisCache
        return RedisCache("redis://localhost:6379/0")

    def test_init_success(self):
        cache = self._make_cache()
        self.mock_client.ping.assert_called_once()
        assert cache.client is self.mock_client

    def test_get_hit(self):
        self.mock_client.get.return_value = '{"key": "value"}'
        cache = self._make_cache()
        result = cache.get("test")
        assert result == {"key": "value"}
        self.mock_client.get.assert_called_with("ppke:cache:test")

    def test_get_miss(self):
        self.mock_client.get.return_value = None
        cache = self._make_cache()
        assert cache.get("missing") is None

    def test_get_non_json(self):
        self.mock_client.get.return_value = "plain_string"
        cache = self._make_cache()
        result = cache.get("raw")
        assert result == "plain_string"

    def test_set_with_ttl(self):
        cache = self._make_cache()
        cache.set("k", {"v": 1}, ttl=60)
        self.mock_client.setex.assert_called_once()

    def test_set_without_ttl(self):
        cache = self._make_cache()
        cache.set("k", "v", ttl=0)
        self.mock_client.set.assert_called_once()

    def test_delete(self):
        self.mock_client.delete.return_value = 1
        cache = self._make_cache()
        assert cache.delete("k") is True

    def test_clear(self):
        self.mock_client.keys.return_value = ["ppke:cache:a", "ppke:cache:b"]
        cache = self._make_cache()
        cache.clear()
        self.mock_client.delete.assert_called_once()

    def test_clear_empty(self):
        self.mock_client.keys.return_value = []
        cache = self._make_cache()
        cache.clear()
        assert self.mock_client.delete.call_count == 0

    def test_incr(self):
        pipe = MagicMock()
        pipe.execute.return_value = [5, True]
        self.mock_client.pipeline.return_value = pipe
        cache = self._make_cache()
        result = cache.incr("ratelimit:test", ttl=60)
        assert result == 5


class TestCacheFactory:
    def setup_method(self):
        import ppke.infra.cache as cm
        cm._cache_instance = None

    def teardown_method(self):
        import ppke.infra.cache as cm
        cm._cache_instance = None

    @patch.dict(os.environ, {"PPKE_CACHE_BACKEND": "memory"}, clear=False)
    def test_get_cache_memory_backend(self):
        from ppke.infra.cache import get_cache, MemoryCache
        cache = get_cache()
        assert isinstance(cache, MemoryCache)

    @patch.dict(os.environ, {"PPKE_CACHE_BACKEND": "", "REDIS_URL": ""}, clear=False)
    def test_get_cache_fallback_to_memory(self):
        from ppke.infra.cache import get_cache, MemoryCache
        import ppke.infra.cache as cm
        cm._cache_instance = None
        cache = get_cache()
        assert isinstance(cache, MemoryCache)

    def test_get_cache_singleton(self):
        import ppke.infra.cache as cm
        cm._cache_instance = None
        with patch.dict(os.environ, {"PPKE_CACHE_BACKEND": "memory"}):
            from ppke.infra.cache import get_cache
            c1 = get_cache()
            c2 = get_cache()
            assert c1 is c2


class TestCacheHelpers:
    def setup_method(self):
        import ppke.infra.cache as cm
        cm._cache_instance = None

    def teardown_method(self):
        import ppke.infra.cache as cm
        cm._cache_instance = None

    def test_cache_key_short(self):
        from ppke.infra.cache import cache_key
        result = cache_key("stats", "user123")
        assert result == "stats:user123"

    def test_cache_key_long_hashed(self):
        from ppke.infra.cache import cache_key
        long_part = "x" * 250
        result = cache_key("prefix", long_part)
        assert len(result) == 32  # SHA256 truncated

    def test_get_default_ttl(self):
        from ppke.infra.cache import get_default_ttl
        with patch.dict(os.environ, {"PPKE_CACHE_TTL": "600"}):
            assert get_default_ttl() == 600

    def test_get_default_ttl_default(self):
        from ppke.infra.cache import get_default_ttl
        with patch.dict(os.environ, {}, clear=False):
            if "PPKE_CACHE_TTL" in os.environ:
                del os.environ["PPKE_CACHE_TTL"]
            assert get_default_ttl() == 300

    @patch.dict(os.environ, {"PPKE_CACHE_BACKEND": "memory"}, clear=False)
    def test_check_rate_limit_allowed(self):
        from ppke.infra.cache import check_rate_limit
        allowed, count = check_rate_limit("test_user", max_requests=10)
        assert allowed is True
        assert count == 1

    @patch.dict(os.environ, {"PPKE_CACHE_BACKEND": "memory"}, clear=False)
    def test_check_rate_limit_exceeded(self):
        from ppke.infra.cache import check_rate_limit
        for _ in range(5):
            check_rate_limit("limit_user", max_requests=5)
        allowed, count = check_rate_limit("limit_user", max_requests=5)
        assert allowed is False
        assert count == 6


# ═══════════════════════════════════════════════════════════════════
# Task queue tests
# ═══════════════════════════════════════════════════════════════════


class TestJobStore:
    def setup_method(self):
        import ppke.infra.tasks as tm
        tm._jobs.clear()
        tm._redis_client = None

    def test_set_and_get_job(self):
        from ppke.infra.tasks import set_job, get_job
        data = {"status": "running", "progress": 50}
        set_job("j1", data)
        result = get_job("j1")
        assert result == data

    def test_get_missing_job(self):
        from ppke.infra.tasks import get_job
        assert get_job("nonexistent") is None

    def test_update_job(self):
        from ppke.infra.tasks import set_job, get_job, update_job
        set_job("j2", {"status": "running", "progress": 0})
        update_job("j2", progress=50, stage="halfway")
        result = get_job("j2")
        assert result["progress"] == 50
        assert result["stage"] == "halfway"

    def test_update_nonexistent_job(self):
        from ppke.infra.tasks import update_job
        # Should not raise
        update_job("missing_job", status="failed")

    def test_job_key(self):
        from ppke.infra.tasks import _job_key
        assert _job_key("abc123") == "ppke:job:abc123"


class TestCreateJob:
    def setup_method(self):
        import ppke.infra.tasks as tm
        tm._jobs.clear()
        tm._redis_client = None

    def test_create_job_basic(self):
        from ppke.infra.tasks import create_job, get_job
        job_id = create_job()
        assert len(job_id) == 8
        job = get_job(job_id)
        assert job["status"] == "running"
        assert job["progress"] == 0
        assert job["error"] is None

    def test_create_job_with_extra(self):
        from ppke.infra.tasks import create_job, get_job
        job_id = create_job(extra={"filename": "test.pdf"})
        job = get_job(job_id)
        assert job["filename"] == "test.pdf"
        assert job["status"] == "running"


class TestRunTask:
    def setup_method(self):
        import ppke.infra.tasks as tm
        tm._jobs.clear()
        tm._redis_client = None
        tm._celery_app = None

    @patch.dict(os.environ, {"PPKE_TASK_BACKEND": "thread"}, clear=False)
    def test_run_task_thread_fallback(self):
        from ppke.infra.tasks import run_task, create_job, get_job
        results = []

        def worker():
            results.append("done")

        job_id = create_job()
        returned_id = run_task(worker, job_id=job_id)
        assert returned_id == job_id
        # Wait for thread
        time.sleep(0.2)
        assert results == ["done"]

    @patch.dict(os.environ, {"PPKE_TASK_BACKEND": "thread"}, clear=False)
    def test_run_task_auto_create_job(self):
        from ppke.infra.tasks import run_task, get_job
        def noop():
            pass
        job_id = run_task(noop)
        assert len(job_id) == 8
        assert get_job(job_id) is not None

    @patch.dict(os.environ, {"PPKE_TASK_BACKEND": "thread"}, clear=False)
    def test_run_task_exception_updates_job(self):
        from ppke.infra.tasks import run_task, create_job, get_job

        def failing():
            raise ValueError("test error")

        job_id = create_job()
        run_task(failing, job_id=job_id)
        time.sleep(0.3)
        job = get_job(job_id)
        assert job["status"] == "failed"
        assert "test error" in job["error"]

    @patch.dict(os.environ, {"PPKE_TASK_BACKEND": "thread"}, clear=False)
    def test_get_celery_app_forced_thread(self):
        from ppke.infra.tasks import _get_celery_app
        import ppke.infra.tasks as tm
        tm._celery_app = None
        assert _get_celery_app() is None

    def test_get_celery_app_public(self):
        from ppke.infra.tasks import get_celery_app
        import ppke.infra.tasks as tm
        tm._celery_app = None
        with patch.dict(os.environ, {"PPKE_TASK_BACKEND": "thread"}):
            assert get_celery_app() is None

    def test_get_redis_no_url(self):
        from ppke.infra.tasks import _get_redis
        import ppke.infra.tasks as tm
        tm._redis_client = None
        with patch.dict(os.environ, {}, clear=True):
            assert _get_redis() is None


# ═══════════════════════════════════════════════════════════════════
# Logging tests
# ═══════════════════════════════════════════════════════════════════


class TestRequestId:
    def test_set_and_get(self):
        from ppke.infra.logging_config import set_request_id, get_request_id
        rid = set_request_id("test-123")
        assert rid == "test-123"
        assert get_request_id() == "test-123"

    def test_auto_generate(self):
        from ppke.infra.logging_config import set_request_id, get_request_id
        rid = set_request_id()
        assert len(rid) == 12
        assert get_request_id() == rid


class TestJSONFormatter:
    def test_basic_format(self):
        from ppke.infra.logging_config import JSONFormatter, set_request_id
        set_request_id("req-abc")
        fmt = JSONFormatter(service_name="test")
        record = logging.LogRecord(
            name="test.logger", level=logging.INFO, pathname="test.py",
            lineno=42, msg="Hello %s", args=("world",), exc_info=None,
        )
        output = fmt.format(record)
        data = json.loads(output)
        assert data["message"] == "Hello world"
        assert data["level"] == "INFO"
        assert data["service"] == "test"
        assert data["request_id"] == "req-abc"
        assert data["source"]["line"] == 42

    def test_exception_format(self):
        from ppke.infra.logging_config import JSONFormatter
        fmt = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="Error", args=(), exc_info=exc_info,
        )
        output = fmt.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert data["exception"]["type"] == "ValueError"
        assert "test error" in data["exception"]["message"]

    def test_extra_fields(self):
        from ppke.infra.logging_config import JSONFormatter
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="req", args=(), exc_info=None,
        )
        record.request_method = "GET"
        record.status_code = 200
        record.duration_ms = 42.5
        output = fmt.format(record)
        data = json.loads(output)
        assert data["request_method"] == "GET"
        assert data["status_code"] == 200
        assert data["duration_ms"] == 42.5


class TestDetailedTextFormatter:
    def test_basic_format(self):
        from ppke.infra.logging_config import DetailedTextFormatter, set_request_id
        set_request_id("rid-xyz")
        fmt = DetailedTextFormatter()
        record = logging.LogRecord(
            name="test.logger", level=logging.WARNING, pathname="test.py",
            lineno=10, msg="Warning msg", args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "WARNING" in output
        assert "[rid-xyz]" in output
        assert "test.logger" in output
        assert "Warning msg" in output

    def test_exception_in_text(self):
        from ppke.infra.logging_config import DetailedTextFormatter
        fmt = DetailedTextFormatter()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="Error", args=(), exc_info=exc_info,
        )
        output = fmt.format(record)
        assert "RuntimeError" in output
        assert "boom" in output

    def test_no_request_id(self):
        from ppke.infra.logging_config import DetailedTextFormatter, _request_id
        _request_id.set("")
        fmt = DetailedTextFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hi", args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "[" not in output or "[]" not in output


class TestConfigureLogging:
    def test_json_format(self):
        from ppke.infra.logging_config import configure_logging
        with patch.dict(os.environ, {"PPKE_ENVIRONMENT": "production"}):
            configure_logging(level="DEBUG", log_format="json")

    def test_text_format(self):
        from ppke.infra.logging_config import configure_logging
        configure_logging(level="INFO", log_format="text")

    def test_auto_detect_format(self):
        from ppke.infra.logging_config import configure_logging
        with patch.dict(os.environ, {"PPKE_ENVIRONMENT": "development", "PPKE_LOG_FORMAT": ""}):
            configure_logging()


class TestRequestLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        from ppke.infra.logging_config import RequestLoggingMiddleware
        called = []

        async def mock_app(scope, receive, send):
            called.append(True)

        mw = RequestLoggingMiddleware(mock_app)
        await mw({"type": "lifespan"}, None, None)
        assert called == [True]

    @pytest.mark.asyncio
    async def test_http_adds_request_id(self):
        from ppke.infra.logging_config import RequestLoggingMiddleware
        headers_sent = []

        async def mock_app(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })
            await send({"type": "http.response.body", "body": b""})

        async def capture_send(message):
            if message["type"] == "http.response.start":
                headers_sent.extend(message.get("headers", []))

        mw = RequestLoggingMiddleware(mock_app)
        await mw(
            {"type": "http", "path": "/api/test", "method": "GET", "client": ("127.0.0.1", 8000)},
            None, capture_send,
        )
        header_names = [h[0] for h in headers_sent]
        assert b"x-request-id" in header_names

    @pytest.mark.asyncio
    async def test_health_not_logged(self):
        """Health endpoint should not produce access logs."""
        from ppke.infra.logging_config import RequestLoggingMiddleware

        async def mock_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def noop_send(msg):
            pass

        mw = RequestLoggingMiddleware(mock_app)
        # Should complete without error
        await mw(
            {"type": "http", "path": "/api/health", "method": "GET", "client": ("127.0.0.1", 0)},
            None, noop_send,
        )


# ═══════════════════════════════════════════════════════════════════
# Metrics tests
# ═══════════════════════════════════════════════════════════════════


class TestMetricsConfig:
    def setup_method(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = None

    def test_metrics_enabled_default(self):
        from ppke.infra.metrics import is_metrics_enabled
        import ppke.infra.metrics as mm
        mm._metrics_enabled = None
        with patch.dict(os.environ, {"PPKE_METRICS_ENABLED": "true"}):
            assert is_metrics_enabled() is True

    def test_metrics_disabled(self):
        from ppke.infra.metrics import is_metrics_enabled
        import ppke.infra.metrics as mm
        mm._metrics_enabled = None
        with patch.dict(os.environ, {"PPKE_METRICS_ENABLED": "false"}):
            assert is_metrics_enabled() is False

    def test_metrics_cached(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = True
        from ppke.infra.metrics import is_metrics_enabled
        assert is_metrics_enabled() is True


class TestNormalizePath:
    def test_static_path(self):
        from ppke.infra.metrics import _normalize_path
        assert _normalize_path("/api/books") == "/api/books"

    def test_book_folder_path(self):
        from ppke.infra.metrics import _normalize_path
        result = _normalize_path("/api/notebook/Book_Test_Author_2024")
        assert "{id}" in result

    def test_uuid_like_path(self):
        from ppke.infra.metrics import _normalize_path
        result = _normalize_path("/api/jobs/ab12cd34")
        assert result == "/api/jobs/{id}"

    def test_empty_path(self):
        from ppke.infra.metrics import _normalize_path
        assert _normalize_path("/") == "/"

    def test_regular_segments_preserved(self):
        from ppke.infra.metrics import _normalize_path
        assert _normalize_path("/api/settings") == "/api/settings"


class TestMetricRecording:
    """Test that record_* functions don't crash when prometheus is missing."""

    def setup_method(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = None
        mm._http_requests_total = None

    def test_record_request_disabled(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = False
        from ppke.infra.metrics import record_request
        record_request("GET", "/test", 200, 0.1)  # Should not raise

    def test_record_request_start_disabled(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = False
        from ppke.infra.metrics import record_request_start
        record_request_start("GET")

    def test_record_request_end_disabled(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = False
        from ppke.infra.metrics import record_request_end
        record_request_end("GET")

    def test_record_ingestion_disabled(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = False
        from ppke.infra.metrics import record_ingestion
        record_ingestion("file_upload", "completed", 5.0)

    def test_record_llm_usage_disabled(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = False
        from ppke.infra.metrics import record_llm_usage
        record_llm_usage("anthropic", "claude-3", 100, 0.01)

    def test_record_active_jobs_disabled(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = False
        from ppke.infra.metrics import record_active_jobs
        record_active_jobs(3)

    def test_record_cache_hit_disabled(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = False
        from ppke.infra.metrics import record_cache_hit
        record_cache_hit()

    def test_record_cache_miss_disabled(self):
        import ppke.infra.metrics as mm
        mm._metrics_enabled = False
        from ppke.infra.metrics import record_cache_miss
        record_cache_miss()


class TestGenerateMetrics:
    def test_without_prometheus(self):
        from ppke.infra.metrics import generate_metrics
        import ppke.infra.metrics as mm
        mm._http_requests_total = None
        with patch.object(mm, "_get_prometheus", return_value=None):
            result = generate_metrics()
            assert "not installed" in result


class TestMetricsMiddleware:
    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        from ppke.infra.metrics import MetricsMiddleware
        called = []
        async def mock_app(scope, receive, send):
            called.append(True)
        mw = MetricsMiddleware(mock_app)
        await mw({"type": "websocket"}, None, None)
        assert called == [True]

    @pytest.mark.asyncio
    async def test_metrics_endpoint_skipped(self):
        from ppke.infra.metrics import MetricsMiddleware
        import ppke.infra.metrics as mm
        mm._metrics_enabled = True
        called = []
        async def mock_app(scope, receive, send):
            called.append(True)
        mw = MetricsMiddleware(mock_app)
        await mw({"type": "http", "path": "/metrics", "method": "GET"}, None, None)
        assert called == [True]


# ═══════════════════════════════════════════════════════════════════
# Sentry tests
# ═══════════════════════════════════════════════════════════════════


class TestSentryIntegration:
    def setup_method(self):
        import ppke.infra.sentry_integration as si
        si._initialized = False

    def test_init_no_dsn(self):
        from ppke.infra.sentry_integration import init_sentry
        with patch.dict(os.environ, {"SENTRY_DSN": ""}):
            result = init_sentry()
            assert result is False

    def test_init_already_initialized(self):
        import ppke.infra.sentry_integration as si
        si._initialized = True
        assert si.init_sentry() is True

    def test_capture_exception_not_initialized(self):
        from ppke.infra.sentry_integration import capture_exception
        result = capture_exception(ValueError("test"))
        assert result is None

    def test_capture_message_not_initialized(self):
        from ppke.infra.sentry_integration import capture_message
        result = capture_message("test msg")
        assert result is None

    def test_set_user_not_initialized(self):
        from ppke.infra.sentry_integration import set_user
        # Should not raise
        set_user("uid", "email@test.com", "name")

    def test_add_breadcrumb_not_initialized(self):
        from ppke.infra.sentry_integration import add_breadcrumb
        # Should not raise
        add_breadcrumb("test crumb", category="test")


class TestBeforeSend:
    def test_filters_http_exception(self):
        from ppke.infra.sentry_integration import _before_send
        event = {
            "exception": {
                "values": [{"type": "HTTPException"}]
            }
        }
        assert _before_send(event, {}) is None

    def test_filters_validation_error(self):
        from ppke.infra.sentry_integration import _before_send
        event = {
            "exception": {
                "values": [{"type": "RequestValidationError"}]
            }
        }
        assert _before_send(event, {}) is None

    def test_passes_real_exception(self):
        from ppke.infra.sentry_integration import _before_send
        event = {
            "exception": {
                "values": [{"type": "ValueError"}]
            }
        }
        assert _before_send(event, {}) is event

    def test_passes_no_exception(self):
        from ppke.infra.sentry_integration import _before_send
        event = {"message": "test"}
        assert _before_send(event, {}) is event


# ═══════════════════════════════════════════════════════════════════
# Storage tests
# ═══════════════════════════════════════════════════════════════════


class TestLocalStorage:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        from ppke.infra.storage import LocalStorage
        self.storage = LocalStorage(base_path=Path(self.tmp_dir))

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_put_and_get_bytes(self):
        self.storage.put("test.txt", b"hello world")
        assert self.storage.get("test.txt") == b"hello world"

    def test_put_fileobj(self):
        buf = io.BytesIO(b"stream data")
        self.storage.put("stream.bin", buf)
        assert self.storage.get("stream.bin") == b"stream data"

    def test_get_missing(self):
        assert self.storage.get("nope.txt") is None

    def test_get_stream(self):
        self.storage.put("stream_test.txt", b"content")
        stream = self.storage.get_stream("stream_test.txt")
        assert stream is not None
        data = stream.read()
        stream.close()
        assert data == b"content"

    def test_get_stream_missing(self):
        assert self.storage.get_stream("nope") is None

    def test_delete_existing(self):
        self.storage.put("del.txt", b"bye")
        assert self.storage.delete("del.txt") is True
        assert self.storage.get("del.txt") is None

    def test_delete_missing(self):
        assert self.storage.delete("missing") is False

    def test_exists(self):
        self.storage.put("exist.txt", b"yes")
        assert self.storage.exists("exist.txt") is True
        assert self.storage.exists("nope.txt") is False

    def test_list_keys(self):
        self.storage.put("dir1/a.txt", b"a")
        self.storage.put("dir1/b.txt", b"b")
        self.storage.put("dir2/c.txt", b"c")
        keys = self.storage.list_keys("dir1")
        assert len(keys) == 2

    def test_list_keys_empty(self):
        assert self.storage.list_keys("empty") == []

    def test_list_keys_no_prefix(self):
        self.storage.put("root.txt", b"r")
        keys = self.storage.list_keys()
        assert "root.txt" in keys

    def test_get_url(self):
        url = self.storage.get_url("test/file.txt")
        assert url.startswith("file://")

    def test_nested_directory(self):
        self.storage.put("deep/nested/file.txt", b"deep")
        assert self.storage.get("deep/nested/file.txt") == b"deep"


class TestStorageFactory:
    def setup_method(self):
        import ppke.infra.storage as sm
        sm._storage_instance = None

    def teardown_method(self):
        import ppke.infra.storage as sm
        sm._storage_instance = None

    @patch.dict(os.environ, {"PPKE_STORAGE_BACKEND": "local"}, clear=False)
    def test_get_storage_local(self):
        from ppke.infra.storage import get_storage, LocalStorage
        storage = get_storage()
        assert isinstance(storage, LocalStorage)

    @patch.dict(os.environ, {"PPKE_STORAGE_BACKEND": "s3", "AWS_S3_BUCKET": ""}, clear=False)
    def test_get_storage_s3_no_bucket(self):
        from ppke.infra.storage import get_storage, LocalStorage
        storage = get_storage()
        assert isinstance(storage, LocalStorage)

    @patch.dict(os.environ, {"PPKE_STORAGE_BACKEND": "gcs", "GCS_BUCKET": ""}, clear=False)
    def test_get_storage_gcs_no_bucket(self):
        from ppke.infra.storage import get_storage, LocalStorage
        storage = get_storage()
        assert isinstance(storage, LocalStorage)

    def test_get_storage_singleton(self):
        import ppke.infra.storage as sm
        sm._storage_instance = None
        with patch.dict(os.environ, {"PPKE_STORAGE_BACKEND": "local"}):
            from ppke.infra.storage import get_storage
            s1 = get_storage()
            s2 = get_storage()
            assert s1 is s2

    @patch.dict(os.environ, {"PPKE_STORAGE_BACKEND": "s3", "AWS_S3_BUCKET": "test-bucket"}, clear=False)
    def test_get_storage_s3_init_failure(self):
        """S3 init failure falls back to local."""
        from ppke.infra.storage import get_storage, LocalStorage
        with patch("ppke.infra.storage.S3Storage", side_effect=Exception("No AWS creds")):
            storage = get_storage()
            assert isinstance(storage, LocalStorage)

    @patch.dict(os.environ, {"PPKE_STORAGE_BACKEND": "gcs", "GCS_BUCKET": "test-bucket"}, clear=False)
    def test_get_storage_gcs_init_failure(self):
        from ppke.infra.storage import get_storage, LocalStorage
        with patch("ppke.infra.storage.GCSStorage", side_effect=Exception("No GCS creds")):
            storage = get_storage()
            assert isinstance(storage, LocalStorage)


# ═══════════════════════════════════════════════════════════════════
# Database tests — DBConnection wrapper + cost queries
# ═══════════════════════════════════════════════════════════════════


class TestDBConnection:
    def setup_method(self):
        import ppke.infra.tasks as tm
        # Reset database backend detection
        import ppke.auth.database as db
        db._db_backend = None
        db._pg_pool = None

    def test_sqlite_wrapper(self):
        from ppke.auth.database import DBConnection
        raw = sqlite3.connect(":memory:")
        raw.row_factory = sqlite3.Row
        conn = DBConnection(raw, "sqlite")
        assert conn.backend == "sqlite"
        conn.execute("CREATE TABLE test (id TEXT, val TEXT)")
        conn.execute("INSERT INTO test VALUES (?, ?)", ("1", "hello"))
        conn.commit()
        row = conn.execute("SELECT * FROM test WHERE id = ?", ("1",)).fetchone()
        assert dict(row)["val"] == "hello"

    def test_sqlite_executescript(self):
        from ppke.auth.database import DBConnection
        raw = sqlite3.connect(":memory:")
        conn = DBConnection(raw, "sqlite")
        conn.executescript("CREATE TABLE t (id TEXT); INSERT INTO t VALUES ('x');")
        conn.commit()

    def test_empty_result(self):
        from ppke.auth.database import _EmptyResult
        er = _EmptyResult()
        assert er.rowcount == 0
        assert er.fetchone() is None
        assert er.fetchall() == []


class TestRowConversion:
    def test_row_to_dict_none(self):
        from ppke.auth.database import _row_to_dict
        assert _row_to_dict(None) is None

    def test_row_to_dict_dict(self):
        from ppke.auth.database import _row_to_dict
        d = {"a": 1}
        assert _row_to_dict(d) == {"a": 1}

    def test_row_to_dict_sqlite_row(self):
        from ppke.auth.database import _row_to_dict
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE t (id TEXT, val TEXT)")
        conn.execute("INSERT INTO t VALUES ('1', 'hello')")
        row = conn.execute("SELECT * FROM t").fetchone()
        result = _row_to_dict(row)
        assert result == {"id": "1", "val": "hello"}

    def test_rows_to_dicts(self):
        from ppke.auth.database import _rows_to_dicts
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE t (id TEXT)")
        conn.execute("INSERT INTO t VALUES ('a')")
        conn.execute("INSERT INTO t VALUES ('b')")
        rows = conn.execute("SELECT * FROM t").fetchall()
        result = _rows_to_dicts(rows)
        assert len(result) == 2
        assert result[0]["id"] == "a"


class TestDetectBackend:
    def test_sqlite_default(self):
        import ppke.auth.database as db
        db._db_backend = None
        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            assert db._detect_backend() == "sqlite"

    def test_postgresql(self):
        import ppke.auth.database as db
        db._db_backend = None
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/ppke"}):
            assert db._detect_backend() == "postgresql"

    def test_postgres_shorthand(self):
        import ppke.auth.database as db
        db._db_backend = None
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://user:pass@localhost/ppke"}):
            assert db._detect_backend() == "postgresql"

    def test_cached(self):
        import ppke.auth.database as db
        db._db_backend = "sqlite"
        assert db._detect_backend() == "sqlite"

    def test_get_db_backend(self):
        import ppke.auth.database as db
        db._db_backend = None
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            assert db.get_db_backend() == "sqlite"


class TestCostQueries:
    def setup_method(self):
        import ppke.auth.database as db
        db._db_backend = None
        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            self.db_path = Path(tempfile.mktemp(suffix=".db"))
            self.conn = db.get_db(self.db_path)
            # Create a test user
            self.user = db.create_user(self.conn, "cost@test.com", "Cost Tester", "hash123")
            self.user_id = self.user["id"]
            # Insert some usage records
            for i in range(5):
                db.record_usage(
                    self.conn, self.user_id,
                    action="query" if i < 3 else "ingestion",
                    tokens_used=1000 * (i + 1),
                    cost_usd=0.01 * (i + 1),
                    provider="anthropic",
                    model="claude-3",
                    book_folder=f"Book_Test_{i % 2}",
                )

    def teardown_method(self):
        try:
            self.db_path.unlink(missing_ok=True)
        except Exception:
            pass
        import ppke.auth.database as db
        db._db_backend = None

    def test_get_user_usage(self):
        from ppke.auth.database import get_user_usage
        usage = get_user_usage(self.conn, self.user_id, days=30)
        assert usage["total_requests"] == 5
        assert usage["total_tokens"] == 15000  # 1000+2000+3000+4000+5000

    def test_get_cost_by_book(self):
        from ppke.auth.database import get_cost_by_book
        results = get_cost_by_book(self.conn, self.user_id, days=30)
        assert len(results) == 2  # Book_Test_0 and Book_Test_1
        for r in results:
            assert "book_folder" in r
            assert "total_tokens" in r
            assert "total_cost" in r

    def test_get_cost_by_provider(self):
        from ppke.auth.database import get_cost_by_provider
        results = get_cost_by_provider(self.conn, self.user_id, days=30)
        assert len(results) == 1  # Only anthropic
        assert results[0]["provider"] == "anthropic"

    def test_get_cost_by_action(self):
        from ppke.auth.database import get_cost_by_action
        results = get_cost_by_action(self.conn, self.user_id, days=30)
        assert len(results) == 2  # query and ingestion
        actions = {r["action"] for r in results}
        assert "query" in actions
        assert "ingestion" in actions

    def test_get_cost_daily(self):
        from ppke.auth.database import get_cost_daily
        results = get_cost_daily(self.conn, self.user_id, days=30)
        assert len(results) >= 1  # At least today
        assert "date" in results[0]
        assert "total_tokens" in results[0]

    def test_record_usage_with_book_folder(self):
        from ppke.auth.database import record_usage, get_cost_by_book
        record_usage(
            self.conn, self.user_id,
            action="chat",
            tokens_used=500,
            cost_usd=0.005,
            provider="openai",
            model="gpt-4o",
            book_folder="Book_NewBook_Author_2024",
        )
        books = get_cost_by_book(self.conn, self.user_id, days=30)
        folders = [b["book_folder"] for b in books]
        assert "Book_NewBook_Author_2024" in folders


class TestGetDBSqlite:
    def test_creates_tables(self):
        import ppke.auth.database as db
        db._db_backend = None
        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            path = Path(tempfile.mktemp(suffix=".db"))
            try:
                conn = db.get_db(path)
                # Verify tables exist
                result = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
                table_names = [_row_to_dict_compat(r) for r in result]
                assert len(table_names) >= 8
            finally:
                path.unlink(missing_ok=True)
                db._db_backend = None


def _row_to_dict_compat(row):
    """Helper for SQLite Row objects."""
    if isinstance(row, dict):
        return row.get("name", "")
    return dict(row).get("name", "")


class TestDBConnectionPostgres:
    """Test PostgreSQL-specific DBConnection behavior using mocks."""

    def test_pg_parameter_translation(self):
        """The execute method should convert ? to %s for postgresql."""
        from ppke.auth.database import DBConnection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        wrapper = DBConnection(mock_conn, "postgresql")
        wrapper.execute("SELECT * FROM users WHERE id = ? AND name = ?", ("id1", "name1"))
        # Verify %s was used
        call_args = mock_cursor.execute.call_args
        assert "%s" in call_args[0][0]
        assert "?" not in call_args[0][0]

    def test_pg_insert_or_ignore_translation(self):
        from ppke.auth.database import DBConnection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        wrapper = DBConnection(mock_conn, "postgresql")
        wrapper.execute("INSERT OR IGNORE INTO test VALUES (?)", ("val",))
        call_sql = mock_cursor.execute.call_args[0][0]
        assert "INSERT OR IGNORE" not in call_sql
        assert "INSERT" in call_sql

    def test_pg_duplicate_key_handling(self):
        from ppke.auth.database import DBConnection, _EmptyResult
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("duplicate key value violates unique constraint")
        mock_conn.cursor.return_value = mock_cursor
        wrapper = DBConnection(mock_conn, "postgresql")
        result = wrapper.execute("INSERT INTO test VALUES (%s)", ("val",))
        assert isinstance(result, _EmptyResult)

    def test_pg_executescript(self):
        from ppke.auth.database import DBConnection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        wrapper = DBConnection(mock_conn, "postgresql")
        wrapper.executescript("CREATE TABLE test (id TEXT)")
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_commit_and_rollback(self):
        from ppke.auth.database import DBConnection
        mock_conn = MagicMock()
        wrapper = DBConnection(mock_conn, "postgresql")
        wrapper.commit()
        mock_conn.commit.assert_called_once()
        wrapper.rollback()
        mock_conn.rollback.assert_called_once()

    def test_close(self):
        from ppke.auth.database import DBConnection
        mock_conn = MagicMock()
        wrapper = DBConnection(mock_conn, "postgresql")
        wrapper.close()
        mock_conn.close.assert_called_once()

    def test_row_factory_sqlite(self):
        from ppke.auth.database import DBConnection
        raw = sqlite3.connect(":memory:")
        wrapper = DBConnection(raw, "sqlite")
        wrapper.row_factory = sqlite3.Row
        assert wrapper.row_factory == sqlite3.Row

    def test_row_factory_pg_noop(self):
        from ppke.auth.database import DBConnection
        mock_conn = MagicMock()
        wrapper = DBConnection(mock_conn, "postgresql")
        wrapper.row_factory = None  # Should not raise
        assert wrapper.row_factory is None
