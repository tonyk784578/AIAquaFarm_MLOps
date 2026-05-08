"""JWT token creation and password hashing utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import jwt

from app.config import get_settings

settings = get_settings()


def _refresh_secret() -> str:
    """Return the HMAC secret used for refresh tokens.

    Falls back to the main secret_key so existing deployments without a
    separate jwt_refresh_secret_key keep working.
    """
    return settings.jwt_refresh_secret_key or settings.secret_key


# ── Password helpers ───────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


# ── Token helpers ──────────────────────────────────────────────────────────────

def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    payload = {"sub": str(subject), "exp": expire, "iat": now, "type": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str | Any) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {"sub": str(subject), "exp": expire, "iat": now, "type": "refresh"}
    return jwt.encode(payload, _refresh_secret(), algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate an access JWT.

    Raises:
        JWTError: If the token is expired or invalid.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a refresh JWT (may use a separate secret).

    Raises:
        JWTError: If the token is expired or invalid.
    """
    return jwt.decode(token, _refresh_secret(), algorithms=[settings.jwt_algorithm])
