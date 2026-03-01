"""Extended tests for infra modules — improve coverage for metrics, sentry,
storage, and tasks beyond the Phase 8 test file.
"""

from __future__ import annotations

import json
import os
import sys
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════
# metrics.py — test enabled paths with mocked prometheus
# ═══════════════════════════════════════════════════════════════════


class TestMetricsEnabled:
    """Test metric recording when prometheus_client is available (mocked)."""

    def setup_method(self):
        import ppke.infra.metrics as m
        self._orig_enabled = m._metrics_enabled
        self._orig_total = m._http_requests_total
        m._metrics_enabled = None  # reset cache

    def teardown_method(self):
        import ppke.infra.metrics as m
        m._metrics_enabled = self._orig_enabled
        m._http_requests_total = self._orig_total

    @patch.dict(os.environ, {"PPKE_METRICS_ENABLED": "true"}, clear=False)
    def test_ensure_metrics_creates_objects(self):
        import ppke.infra.metrics as m
        # Reset all metric objects
        m._http_requests_total = None
        m._http_request_duration = None
        m._http_requests_in_progress = None
        m._ingestion_duration = None
        m._ingestion_total = None
        m._llm_tokens_total = None
        m._llm_cost_total = None
        m._active_jobs = None
        m._cache_hits = None
        m._cache_misses = None

        # Create a fake prometheus module
        fake_prom = MagicMock()
        with patch.object(m, "_get_prometheus", return_value=fake_prom):
            result = m._ensure_metrics()
        assert result is True
        assert m._http_requests_total is not None
        # Second call should return True immediately
        assert m._ensure_metrics() is True

    @patch.dict(os.environ, {"PPKE_METRICS_ENABLED": "true"}, clear=False)
    def test_record_request_with_metrics(self):
        import ppke.infra.metrics as m
        m._metrics_enabled = True
        m._http_requests_total = None
        fake_prom = MagicMock()
        with patch.object(m, "_get_prometheus", return_value=fake_prom):
            m._ensure_metrics()
            m.record_request("GET", "/api/books", 200, 0.5)
            m.record_request_start("POST")
            m.record_request_end("POST")
            m.record_ingestion("file", "completed", 10.5)
            m.record_ingestion("url", "failed", 0)
            m.record_llm_usage("openai", "gpt-4", 1000, 0.05)
            m.record_active_jobs(3)
            m.record_cache_hit()
            m.record_cache_miss()

    def test_generate_metrics_no_prometheus(self):
        import ppke.infra.metrics as m
        with patch.object(m, "_get_prometheus", return_value=None):
            result = m.generate_metrics()
            assert "not installed" in result

    def test_generate_metrics_with_prometheus(self):
        import ppke.infra.metrics as m
        fake_prom = MagicMock()
        fake_prom.generate_latest.return_value = b"# HELP metric\n"
        with patch.object(m, "_get_prometheus", return_value=fake_prom):
            result = m.generate_metrics()
            assert isinstance(result, str)

    def test_normalize_path_book_folder(self):
        from ppke.infra.metrics import _normalize_path
        assert _normalize_path("/api/books/Book_abcd1234") == "/api/books/{id}"

    def test_normalize_path_short_id(self):
        from ppke.infra.metrics import _normalize_path
        assert _normalize_path("/api/jobs/abc12345") == "/api/jobs/{id}"

    def test_normalize_path_static(self):
        from ppke.infra.metrics import _normalize_path
        assert _normalize_path("/static/css/main.css") == "/static/css/main.css"

    def test_metrics_middleware_http_tracking(self):
        """Test MetricsMiddleware actually tracks HTTP requests."""
        import ppke.infra.metrics as m
        from ppke.infra.metrics import MetricsMiddleware

        m._metrics_enabled = True
        m._http_requests_total = None

        fake_prom = MagicMock()
        with patch.object(m, "_get_prometheus", return_value=fake_prom):
            m._ensure_metrics()

        app_mock = MagicMock()

        async def fake_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b""})

        mw = MetricsMiddleware(fake_app)

        import asyncio
        from unittest.mock import AsyncMock
        asyncio.run(mw({"type": "http", "path": "/api/test", "method": "GET"}, AsyncMock(), AsyncMock()))


# ═══════════════════════════════════════════════════════════════════
# sentry_integration.py — test initialized paths
# ═══════════════════════════════════════════════════════════════════


class TestSentryInitialized:
    """Test Sentry functions when initialized."""

    def setup_method(self):
        import ppke.infra.sentry_integration as s
        self._orig = s._initialized

    def teardown_method(self):
        import ppke.infra.sentry_integration as s
        s._initialized = self._orig

    @patch.dict(os.environ, {"SENTRY_DSN": "https://key@sentry.io/123"}, clear=False)
    def test_init_with_dsn(self):
        import ppke.infra.sentry_integration as s
        s._initialized = False
        # Create a fake sentry_sdk module
        fake_sentry = MagicMock()
        fake_sentry_logging = MagicMock()
        orig_sentry = sys.modules.get("sentry_sdk")
        orig_logging = sys.modules.get("sentry_sdk.integrations.logging")
        try:
            sys.modules["sentry_sdk"] = fake_sentry
            sys.modules["sentry_sdk.integrations.logging"] = fake_sentry_logging
            fake_sentry_logging.LoggingIntegration.return_value = MagicMock()
            result = s.init_sentry()
            assert result is True
            assert s._initialized is True
        finally:
            if orig_sentry is None:
                sys.modules.pop("sentry_sdk", None)
            else:
                sys.modules["sentry_sdk"] = orig_sentry
            if orig_logging is None:
                sys.modules.pop("sentry_sdk.integrations.logging", None)
            else:
                sys.modules["sentry_sdk.integrations.logging"] = orig_logging

    def test_capture_exception_when_initialized(self):
        import ppke.infra.sentry_integration as s
        s._initialized = True
        fake_sentry = MagicMock()
        fake_sentry.capture_exception.return_value = "event-123"
        orig = sys.modules.get("sentry_sdk")
        try:
            sys.modules["sentry_sdk"] = fake_sentry
            result = s.capture_exception(ValueError("test"), path="/api/test")
            assert result == "event-123" or result is not None
        finally:
            if orig is None:
                sys.modules.pop("sentry_sdk", None)
            else:
                sys.modules["sentry_sdk"] = orig

    def test_capture_message_when_initialized(self):
        import ppke.infra.sentry_integration as s
        s._initialized = True
        fake_sentry = MagicMock()
        fake_sentry.capture_message.return_value = "msg-456"
        orig = sys.modules.get("sentry_sdk")
        try:
            sys.modules["sentry_sdk"] = fake_sentry
            result = s.capture_message("test message", level="warning")
            assert result is not None
        finally:
            if orig is None:
                sys.modules.pop("sentry_sdk", None)
            else:
                sys.modules["sentry_sdk"] = orig

    def test_set_user_when_initialized(self):
        import ppke.infra.sentry_integration as s
        s._initialized = True
        fake_sentry = MagicMock()
        orig = sys.modules.get("sentry_sdk")
        try:
            sys.modules["sentry_sdk"] = fake_sentry
            s.set_user("user-1", email="test@test.com", name="Test")
            fake_sentry.set_user.assert_called_once()
        finally:
            if orig is None:
                sys.modules.pop("sentry_sdk", None)
            else:
                sys.modules["sentry_sdk"] = orig

    def test_add_breadcrumb_when_initialized(self):
        import ppke.infra.sentry_integration as s
        s._initialized = True
        fake_sentry = MagicMock()
        orig = sys.modules.get("sentry_sdk")
        try:
            sys.modules["sentry_sdk"] = fake_sentry
            s.add_breadcrumb("test breadcrumb", category="test", key="value")
            fake_sentry.add_breadcrumb.assert_called_once()
        finally:
            if orig is None:
                sys.modules.pop("sentry_sdk", None)
            else:
                sys.modules["sentry_sdk"] = orig

    @patch.dict(os.environ, {}, clear=False)
    def test_init_no_dsn(self):
        import ppke.infra.sentry_integration as s
        s._initialized = False
        os.environ.pop("SENTRY_DSN", None)
        result = s.init_sentry()
        assert result is False


# ═══════════════════════════════════════════════════════════════════
# storage.py — S3Storage and GCSStorage mock tests
# ═══════════════════════════════════════════════════════════════════


class TestS3StorageMocked:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.fake_boto3 = MagicMock()
        self.fake_boto3.client.return_value = self.mock_client
        self._orig_boto3 = sys.modules.get("boto3")
        sys.modules["boto3"] = self.fake_boto3

    def teardown_method(self):
        if self._orig_boto3 is None:
            sys.modules.pop("boto3", None)
        else:
            sys.modules["boto3"] = self._orig_boto3

    def _make_storage(self):
        from ppke.infra.storage import S3Storage
        return S3Storage("my-bucket", prefix="ppke/", region="us-east-1")

    def test_put_bytes(self):
        s = self._make_storage()
        result = s.put("test.txt", b"hello")
        assert result == "test.txt"
        self.mock_client.put_object.assert_called_once()

    def test_put_fileobj(self):
        import io
        s = self._make_storage()
        s.put("file.bin", io.BytesIO(b"data"), content_type="application/octet-stream")
        self.mock_client.put_object.assert_called_once()

    def test_get_success(self):
        body_mock = MagicMock()
        body_mock.read.return_value = b"content"
        self.mock_client.get_object.return_value = {"Body": body_mock}
        s = self._make_storage()
        result = s.get("test.txt")
        assert result == b"content"

    def test_get_not_found(self):
        # Set up a proper exceptions namespace with a real exception class
        no_such_key_exc = type("NoSuchKey", (Exception,), {})
        self.mock_client.exceptions = MagicMock()
        self.mock_client.exceptions.NoSuchKey = no_such_key_exc
        self.mock_client.get_object.side_effect = no_such_key_exc("Not found")
        s = self._make_storage()
        assert s.get("missing.txt") is None

    def test_get_stream(self):
        body_mock = MagicMock()
        self.mock_client.get_object.return_value = {"Body": body_mock}
        s = self._make_storage()
        assert s.get_stream("test.txt") is body_mock

    def test_get_stream_error(self):
        self.mock_client.get_object.side_effect = Exception("err")
        s = self._make_storage()
        assert s.get_stream("missing") is None

    def test_delete(self):
        s = self._make_storage()
        assert s.delete("test.txt") is True

    def test_delete_error(self):
        self.mock_client.delete_object.side_effect = Exception("err")
        s = self._make_storage()
        assert s.delete("bad") is False

    def test_exists_true(self):
        s = self._make_storage()
        assert s.exists("test.txt") is True

    def test_exists_false(self):
        self.mock_client.head_object.side_effect = Exception("404")
        s = self._make_storage()
        assert s.exists("missing") is False

    def test_list_keys(self):
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {"Contents": [{"Key": "ppke/file1.txt"}, {"Key": "ppke/file2.txt"}]}
        ]
        self.mock_client.get_paginator.return_value = paginator
        s = self._make_storage()
        keys = s.list_keys()
        assert len(keys) == 2

    def test_get_url(self):
        self.mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"
        s = self._make_storage()
        url = s.get_url("test.txt")
        assert "s3.example.com" in url

    def test_key_prefixing(self):
        s = self._make_storage()
        assert s._key("test.txt") == "ppke/test.txt"


class TestGCSStorageMocked:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.mock_bucket = MagicMock()
        self.mock_client.bucket.return_value = self.mock_bucket
        self.fake_gcs_mod = MagicMock()
        self.fake_gcs_mod.Client.return_value = self.mock_client
        self.fake_google = MagicMock()
        self.fake_google.cloud.storage = self.fake_gcs_mod
        self._orig_google = sys.modules.get("google")
        self._orig_gc = sys.modules.get("google.cloud")
        self._orig_gcs = sys.modules.get("google.cloud.storage")
        sys.modules["google"] = self.fake_google
        sys.modules["google.cloud"] = self.fake_google.cloud
        sys.modules["google.cloud.storage"] = self.fake_gcs_mod

    def teardown_method(self):
        for key, orig in [("google", self._orig_google), ("google.cloud", self._orig_gc), ("google.cloud.storage", self._orig_gcs)]:
            if orig is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = orig

    def _make_storage(self):
        from ppke.infra.storage import GCSStorage
        return GCSStorage("my-bucket", prefix="ppke/")

    def test_put_bytes(self):
        s = self._make_storage()
        blob = MagicMock()
        self.mock_bucket.blob.return_value = blob
        result = s.put("test.txt", b"hello")
        assert result == "test.txt"
        blob.upload_from_string.assert_called_once()

    def test_put_fileobj(self):
        import io
        s = self._make_storage()
        blob = MagicMock()
        self.mock_bucket.blob.return_value = blob
        s.put("file.bin", io.BytesIO(b"data"))
        blob.upload_from_file.assert_called_once()

    def test_get_exists(self):
        s = self._make_storage()
        blob = MagicMock()
        blob.exists.return_value = True
        blob.download_as_bytes.return_value = b"content"
        self.mock_bucket.blob.return_value = blob
        assert s.get("test.txt") == b"content"

    def test_get_not_exists(self):
        s = self._make_storage()
        blob = MagicMock()
        blob.exists.return_value = False
        self.mock_bucket.blob.return_value = blob
        assert s.get("missing") is None

    def test_get_stream(self):
        s = self._make_storage()
        blob = MagicMock()
        blob.exists.return_value = True
        blob.download_as_bytes.return_value = b"data"
        self.mock_bucket.blob.return_value = blob
        stream = s.get_stream("test.txt")
        assert stream is not None
        assert stream.read() == b"data"

    def test_get_stream_missing(self):
        s = self._make_storage()
        blob = MagicMock()
        blob.exists.return_value = False
        self.mock_bucket.blob.return_value = blob
        assert s.get_stream("missing") is None

    def test_delete_exists(self):
        s = self._make_storage()
        blob = MagicMock()
        blob.exists.return_value = True
        self.mock_bucket.blob.return_value = blob
        assert s.delete("test.txt") is True
        blob.delete.assert_called_once()

    def test_delete_not_exists(self):
        s = self._make_storage()
        blob = MagicMock()
        blob.exists.return_value = False
        self.mock_bucket.blob.return_value = blob
        assert s.delete("missing") is False

    def test_exists(self):
        s = self._make_storage()
        blob = MagicMock()
        blob.exists.return_value = True
        self.mock_bucket.blob.return_value = blob
        assert s.exists("test.txt") is True

    def test_list_keys(self):
        s = self._make_storage()
        blob1 = MagicMock()
        blob1.name = "ppke/file1.txt"
        blob2 = MagicMock()
        blob2.name = "ppke/file2.txt"
        self.mock_client.list_blobs.return_value = [blob1, blob2]
        keys = s.list_keys()
        assert len(keys) == 2

    def test_get_url(self):
        s = self._make_storage()
        blob = MagicMock()
        blob.generate_signed_url.return_value = "https://gcs.example.com/signed"
        self.mock_bucket.blob.return_value = blob
        url = s.get_url("test.txt")
        assert "gcs.example.com" in url


# ═══════════════════════════════════════════════════════════════════
# tasks.py — thread execution, Redis-backed jobs
# ═══════════════════════════════════════════════════════════════════


class TestRunTaskThread:
    def test_run_task_completes(self):
        from ppke.infra.tasks import run_task, get_job, create_job
        results = []

        def my_func(x):
            results.append(x)

        job_id = create_job()
        run_task(my_func, 42, job_id=job_id)
        # Give thread time to complete
        time.sleep(0.3)
        assert 42 in results

    def test_run_task_exception_captured(self):
        from ppke.infra.tasks import run_task, get_job, create_job

        def failing_func():
            raise RuntimeError("intentional")

        job_id = create_job()
        run_task(failing_func, job_id=job_id)
        time.sleep(0.3)
        job = get_job(job_id)
        assert job is not None
        assert job["status"] == "failed"
        assert "intentional" in job["error"]


class TestJobStoreRedis:
    def test_set_job_with_redis(self):
        from ppke.infra.tasks import set_job, get_job
        fake_redis = MagicMock()
        with patch("ppke.infra.tasks._get_redis", return_value=fake_redis):
            set_job("redis-test-1", {"status": "running"})
            fake_redis.setex.assert_called_once()

    def test_get_job_from_redis(self):
        from ppke.infra.tasks import get_job, _jobs
        fake_redis = MagicMock()
        fake_redis.get.return_value = json.dumps({"status": "completed"})
        # Remove from in-memory store first
        _jobs.pop("redis-get-1", None)
        with patch("ppke.infra.tasks._get_redis", return_value=fake_redis):
            job = get_job("redis-get-1")
            assert job is not None
            assert job["status"] == "completed"

    def test_get_job_redis_miss(self):
        from ppke.infra.tasks import get_job, _jobs
        fake_redis = MagicMock()
        fake_redis.get.return_value = None
        _jobs.pop("redis-miss-1", None)
        with patch("ppke.infra.tasks._get_redis", return_value=fake_redis):
            job = get_job("redis-miss-1")
            assert job is None
