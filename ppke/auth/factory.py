"""Backend factory — resolves the active auth + data backends.

Set ``AUTH_BACKEND=supabase`` (in ``~/.ppke/.env`` or environment) to
use Supabase.  Any other value (or unset) defaults to the local backend
(SQLite / self-hosted PostgreSQL + custom JWT).

Usage::

    from ppke.auth.factory import get_auth_backend, get_data_backend

    auth = get_auth_backend()   # AuthBackend implementation
    data = get_data_backend()   # DataBackend implementation
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


def _detect_backend_name() -> str:
    """Determine which backend to use from env vars."""
    # Load .env first
    try:
        from ppke.config import _load_env_file
        for k, v in _load_env_file().items():
            os.environ.setdefault(k, v)
    except Exception:
        pass

    name = os.environ.get("AUTH_BACKEND", "").strip().lower()
    if name == "supabase":
        return "supabase"
    return "local"


@lru_cache(maxsize=1)
def get_auth_backend():
    """Return the active AuthBackend singleton."""
    name = _detect_backend_name()
    if name == "supabase":
        from ppke.auth.supabase_backend import SupabaseAuthBackend
        logger.info("Using Supabase auth backend")
        return SupabaseAuthBackend()
    else:
        from ppke.auth.local_backend import LocalAuthBackend
        logger.info("Using local auth backend")
        return LocalAuthBackend()


@lru_cache(maxsize=1)
def get_data_backend():
    """Return the active DataBackend singleton."""
    name = _detect_backend_name()
    if name == "supabase":
        from ppke.auth.supabase_backend import SupabaseDataBackend
        logger.info("Using Supabase data backend")
        return SupabaseDataBackend()
    else:
        from ppke.auth.local_backend import LocalDataBackend
        logger.info("Using local data backend")
        return LocalDataBackend()


def is_supabase() -> bool:
    """Quick check — True when using the Supabase backend."""
    return _detect_backend_name() == "supabase"
