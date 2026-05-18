"""FastAPI dependency: gate write endpoints with the shared service key.

The agent service is on the internal network only (Docker compose), but
the public-facing reverse proxy may forward to it. To prevent unauthorized
trigger of ``/run`` / ``/optimize`` (which can issue real control commands),
require the shared ``X-Service-Key`` header on every write endpoint.

When ``backend_api_key`` is empty (dev environments without secrets), the
dependency permits all requests but logs a warning at import time.
"""

from __future__ import annotations

import structlog
from fastapi import Header, HTTPException, status

from agents.config import get_agent_settings

logger = structlog.get_logger()


def require_service_key(
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
) -> None:
    """Reject the request unless the X-Service-Key header matches settings.

    In dev (no key set), this dependency is a no-op so endpoints stay reachable.
    In production (key set), missing/wrong keys produce HTTP 401.
    """
    settings = get_agent_settings()
    expected = settings.backend_api_key
    if not expected:
        # Dev mode — no key configured. Allow but warn once per call.
        logger.warning("service_key_unset_allowing_request")
        return

    if not x_service_key or x_service_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-Service-Key",
        )
