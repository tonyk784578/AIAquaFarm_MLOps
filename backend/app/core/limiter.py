"""Shared slowapi rate-limiter instance + per-endpoint helpers.

The ``limiter`` instance is registered on the FastAPI app in ``main.py`` via
``app.state.limiter = limiter``. Routers import it directly and decorate
their endpoint functions::

    from app.core.limiter import limiter, is_internal_service

    @router.post("/feeding/stop/{tank_id}")
    @limiter.limit("60/minute", exempt_when=is_internal_service)
    async def stop_feeding(request: Request, ...) -> dict:
        ...

The decorator requires the endpoint function to accept the ``request: Request``
parameter (slowapi inspects it to derive the client key).

Limits are deliberately tiered:

* **Public / browser** routes — moderate cap, IP-keyed.
* **Internal service** routes (``X-Service-Key`` header set) — exempt, since
  the agent service legitimately calls control endpoints many times per
  minute and a single container IP would otherwise saturate the bucket.
* **Superuser admin** routes (mlops retrain/promote/deploy) — strict cap,
  IP-keyed, NOT exempt for service callers because no internal service
  should be triggering these.
"""

from __future__ import annotations

from typing import Final

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

limiter = Limiter(key_func=get_remote_address)


# ── Limit constants (single source of truth) ──────────────────────────────────

LIMIT_AUTH_LOGIN: Final[str] = "10/minute"
LIMIT_CONTROL_WRITE: Final[str] = "60/minute"   # AI agents are exempt via header
LIMIT_ALERT_WRITE: Final[str] = "30/minute"
LIMIT_MLOPS_ADMIN: Final[str] = "10/minute"     # retrain / promote / deploy


# ── Helpers ────────────────────────────────────────────────────────────────────


def is_internal_service(request: Request) -> bool:
    """Return True if the request carries a valid ``X-Service-Key`` header.

    Used with slowapi's ``exempt_when`` to skip rate limiting for legitimate
    internal-service calls (agents → backend). External callers that happen
    to send a wrong key still get rate-limited — they look like an attacker
    probing endpoints.
    """
    expected = get_settings().internal_api_key
    if not expected:
        return False
    return request.headers.get("X-Service-Key") == expected
