"""Caching layer — Redis with in-memory LRU fallback.

Provides a unified cache interface for API response caching, rate limiting,
and general key-value storage.

Environment variables:
    REDIS_URL — Redis connection URL (default: redis://localhost:6379/0)
    PPKE_CACHE_TTL — Default cache TTL in seconds (default: 300)
    PPKE_CACHE_BACKEND — Force "redis" or "memory" (auto-detected if unset)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

# ── In-Memory LRU Cache ──


class MemoryCache:
    """Thread-safe LRU cache with TTL support."""

    def __init__(self, max_size: int = 1024):
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        import threading
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expires_at = item
            if expires_at and time.time() > expires_at:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        with self._lock:
            expires_at = time.time() + ttl if ttl > 0 else 0
            self._store[key] = (value, expires_at)
            self._store.move_to_end(key)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def incr(self, key: str, ttl: int = 60) -> int:
        """Increment a counter key, used for rate limiting."""
        with self._lock:
            item = self._store.get(key)
            if item is None or (item[1] and time.time() > item[1]):
                val = 1
                expires_at = time.time() + ttl
            else:
                val = item[0] + 1
                expires_at = item[1]
            self._store[key] = (val, expires_at)
            return val


# ── Redis Cache ──


class RedisCache:
    """Redis-backed cache with JSON serialization."""

    def __init__(self, redis_url: str):
        import redis
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._prefix = "ppke:cache:"
        # Verify connection
        self._client.ping()
        logger.info("Redis cache connected: %s", redis_url)

    def get(self, key: str) -> Any | None:
        raw = self._client.get(self._prefix + key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        serialized = json.dumps(value, default=str)
        if ttl > 0:
            self._client.setex(self._prefix + key, ttl, serialized)
        else:
            self._client.set(self._prefix + key, serialized)

    def delete(self, key: str) -> bool:
        return bool(self._client.delete(self._prefix + key))

    def clear(self) -> None:
        keys = self._client.keys(self._prefix + "*")
        if keys:
            self._client.delete(*keys)

    def incr(self, key: str, ttl: int = 60) -> int:
        """Atomic increment for rate limiting."""
        full_key = self._prefix + key
        pipe = self._client.pipeline()
        pipe.incr(full_key)
        pipe.expire(full_key, ttl)
        results = pipe.execute()
        return results[0]

    @property
    def client(self):
        return self._client


# ── Singleton factory ──

_cache_instance: MemoryCache | RedisCache | None = None


def get_cache() -> MemoryCache | RedisCache:
    """Return the global cache instance (Redis or memory)."""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance

    backend = os.environ.get("PPKE_CACHE_BACKEND", "").lower()
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    if backend == "memory":
        _cache_instance = MemoryCache()
        logger.info("Using in-memory cache")
        return _cache_instance

    if backend == "redis" or not backend:
        try:
            _cache_instance = RedisCache(redis_url)
            return _cache_instance
        except Exception as exc:
            logger.info("Redis unavailable (%s), using in-memory cache", exc)

    _cache_instance = MemoryCache()
    return _cache_instance


def get_default_ttl() -> int:
    """Return the configured default TTL."""
    return int(os.environ.get("PPKE_CACHE_TTL", "300"))


# ── Rate limiter ──


def check_rate_limit(
    key: str,
    max_requests: int = 60,
    window_seconds: int = 60,
) -> tuple[bool, int]:
    """Check if a request is within rate limits.

    Returns (allowed: bool, current_count: int).
    """
    cache = get_cache()
    rate_key = f"ratelimit:{key}"
    count = cache.incr(rate_key, ttl=window_seconds)
    return count <= max_requests, count


# ── Cache key helpers ──


def cache_key(*parts: str) -> str:
    """Build a namespaced cache key from parts."""
    raw = ":".join(str(p) for p in parts)
    if len(raw) > 200:
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    return raw
