"""Infrastructure module for PPKE — Phase 8.

Provides production-grade components:
- Task queue (Celery with Redis broker, threading fallback)
- Caching (Redis with in-memory fallback)
- Structured logging (JSON with request IDs)
- Prometheus metrics collection
- Sentry error tracking
- Object storage (S3/GCS with local filesystem fallback)
- PostgreSQL database support
"""
