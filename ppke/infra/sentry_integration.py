"""Sentry error tracking integration.

Initializes the Sentry SDK for automatic exception capture, performance
monitoring, and breadcrumb trails.

Environment variables:
    SENTRY_DSN — Sentry project DSN (required to enable)
    PPKE_ENVIRONMENT — Environment name (default: "development")
    SENTRY_TRACES_SAMPLE_RATE — Performance trace sample rate (default: 0.1)
    SENTRY_PROFILES_SAMPLE_RATE — Profiling sample rate (default: 0.1)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_initialized = False


def init_sentry() -> bool:
    """Initialize Sentry SDK if DSN is configured. Returns True if enabled."""
    global _initialized
    if _initialized:
        return True

    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        logger.info("Sentry DSN not configured — error tracking disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration

        environment = os.environ.get("PPKE_ENVIRONMENT", "development")
        traces_sample_rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
        profiles_sample_rate = float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1"))

        integrations = [
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ]

        # Try to add FastAPI integration
        try:
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration
            integrations.extend([
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(transaction_style="endpoint"),
            ])
        except ImportError:
            pass

        # Try to add Celery integration
        try:
            from sentry_sdk.integrations.celery import CeleryIntegration
            integrations.append(CeleryIntegration())
        except ImportError:
            pass

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=f"ppke@3.0.0",
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            integrations=integrations,
            send_default_pii=False,
            attach_stacktrace=True,
            before_send=_before_send,
        )

        _initialized = True
        logger.info("Sentry initialized: environment=%s, traces=%.0f%%",
                     environment, traces_sample_rate * 100)
        return True

    except ImportError:
        logger.info("sentry-sdk not installed — error tracking disabled")
        return False
    except Exception as exc:
        logger.warning("Failed to initialize Sentry: %s", exc)
        return False


def _before_send(event: dict, hint: dict) -> dict | None:
    """Filter or modify events before sending to Sentry."""
    # Don't send 404s or validation errors
    if "exception" in event:
        values = event["exception"].get("values", [])
        for exc_info in values:
            exc_type = exc_info.get("type", "")
            if exc_type in ("HTTPException", "RequestValidationError"):
                return None
    return event


def capture_exception(exc: Exception, **context: Any) -> str | None:
    """Capture an exception to Sentry with extra context.

    Returns the Sentry event ID, or None if Sentry is not initialized.
    """
    if not _initialized:
        return None
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_exception(exc)
    except Exception:
        return None


def capture_message(message: str, level: str = "info", **context: Any) -> str | None:
    """Send a message to Sentry."""
    if not _initialized:
        return None
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_message(message, level=level)
    except Exception:
        return None


def set_user(user_id: str, email: str = "", name: str = "") -> None:
    """Set the user context for Sentry events."""
    if not _initialized:
        return
    try:
        import sentry_sdk
        sentry_sdk.set_user({"id": user_id, "email": email, "username": name})
    except Exception:
        pass


def add_breadcrumb(message: str, category: str = "app", **data: Any) -> None:
    """Add a breadcrumb for debugging context."""
    if not _initialized:
        return
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            data=data,
            level="info",
        )
    except Exception:
        pass
