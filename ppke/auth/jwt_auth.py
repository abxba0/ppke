"""JWT token generation and verification, password hashing.

Uses PyJWT for token handling and bcrypt for password hashing.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Secret key for JWT signing — generated once, persisted to disk
_SECRET_PATH = Path.home() / ".ppke" / ".jwt_secret"
_TOKEN_EXPIRY_HOURS = 72  # 3 days


def _get_secret() -> str:
    """Load or generate the JWT secret key."""
    if _SECRET_PATH.exists():
        return _SECRET_PATH.read_text().strip()
    secret = secrets.token_hex(32)
    _SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SECRET_PATH.write_text(secret)
    _SECRET_PATH.chmod(0o600)
    return secret


# ── Password hashing ──
# Uses bcrypt if available, falls back to PBKDF2 (stdlib)


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        # Fallback: PBKDF2 with stdlib hashlib
        salt = secrets.token_hex(16)
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
        return f"pbkdf2:{salt}:{hashed.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    if hashed.startswith("pbkdf2:"):
        _, salt, stored_hash = hashed.split(":", 2)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
        return hmac.compare_digest(computed.hex(), stored_hash)
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ImportError:
        return False


# ── JWT tokens ──


def _hmac_token(user_id: str, email: str, extra: dict[str, Any] | None = None) -> str:
    """Fallback HMAC-based token when PyJWT is unavailable."""
    import base64
    import json as _json

    payload = {
        "user_id": user_id,
        "email": email,
        "exp": (datetime.now(timezone.utc) + timedelta(hours=_TOKEN_EXPIRY_HOURS)).isoformat(),
    }
    if extra:
        payload.update(extra)
    raw = _json.dumps(payload, sort_keys=True)
    sig = hmac.new(_get_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{raw}|{sig}".encode()).decode()


def create_token(user_id: str, email: str, extra: dict[str, Any] | None = None) -> str:
    """Create a JWT access token."""
    try:
        import jwt
        payload = {
            "sub": user_id,
            "email": email,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=_TOKEN_EXPIRY_HOURS),
        }
        if extra:
            payload.update(extra)
        return jwt.encode(payload, _get_secret(), algorithm="HS256")
    except BaseException:
        return _hmac_token(user_id, email, extra)


def _decode_hmac_token(token: str) -> dict[str, Any] | None:
    """Decode an HMAC fallback token."""
    import base64
    import json as _json

    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        raw, sig = decoded.rsplit("|", 1)
        expected_sig = hmac.new(_get_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = _json.loads(raw)
        exp = datetime.fromisoformat(payload["exp"])
        if datetime.now(timezone.utc) > exp:
            return None
        return {"sub": payload["user_id"], "email": payload["email"]}
    except Exception:
        return None


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT token. Returns payload or None if invalid."""
    try:
        import jwt
        payload = jwt.decode(token, _get_secret(), algorithms=["HS256"])
        return payload
    except BaseException:
        # Try HMAC fallback
        return _decode_hmac_token(token)
