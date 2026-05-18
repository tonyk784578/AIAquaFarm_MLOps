"""Shared HTTP client for backend calls — service-key header, timeout, retry.

Every call from an agent node to the backend MUST go through this client so
that:

* The ``X-Service-Key`` header is set consistently from ``BACKEND_API_KEY``.
* Connect/read timeouts are bounded (never block a graph node forever).
* Transient failures are retried with exponential backoff.

Usage::

    async with AgentHTTPClient() as client:
        snapshot = await client.get_json("/api/v1/dashboard/summary")
        await client.post_json("/api/v1/control/feeding/stop/TANK-01", {})
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from agents.config import get_agent_settings
from agents.runtime.retry import retry_http

logger = structlog.get_logger()


class AgentHTTPClient:
    """Async context-managed wrapper around ``httpx.AsyncClient``.

    Attributes:
        base_url: Backend base URL from settings.
        timeout: httpx.Timeout instance.
        client: Underlying httpx.AsyncClient (only valid inside ``async with``).
    """

    DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)

    def __init__(
        self,
        base_url: str | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        settings = get_agent_settings()
        self.base_url = (base_url or settings.backend_url).rstrip("/")
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self._service_key = settings.backend_api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AgentHTTPClient":
        headers: dict[str, str] = {}
        if self._service_key:
            headers["X-Service-Key"] = self._service_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, headers=headers
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Core verbs (retry-wrapped) ────────────────────────────────────────────

    @retry_http(max_attempts=3)
    async def get_json(self, path: str, **params: Any) -> Any:
        """GET ``path`` and return parsed JSON.

        Raises:
            httpx.HTTPStatusError: For non-2xx after retries exhaust.
        """
        assert self._client is not None, "use AgentHTTPClient inside async with"
        resp = await self._client.get(path, params=params or None)
        resp.raise_for_status()
        return resp.json()

    @retry_http(max_attempts=3)
    async def post_json(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """POST ``body`` to ``path`` and return parsed JSON."""
        assert self._client is not None, "use AgentHTTPClient inside async with"
        resp = await self._client.post(path, json=body or {})
        resp.raise_for_status()
        return resp.json()

    # ── Safe variants (no raise — return error dict) ──────────────────────────

    async def safe_get_json(self, path: str, default: Any = None, **params: Any) -> Any:
        """GET that returns ``default`` (or empty dict) on any error."""
        try:
            return await self.get_json(path, **params)
        except Exception as exc:
            logger.warning("safe_get_failed", path=path, error=str(exc))
            return default if default is not None else {}

    async def safe_post_json(
        self, path: str, body: dict[str, Any] | None = None, default: Any = None
    ) -> Any:
        """POST that returns ``default`` (or error dict) on any error."""
        try:
            return await self.post_json(path, body)
        except Exception as exc:
            logger.warning("safe_post_failed", path=path, error=str(exc))
            return default if default is not None else {"error": str(exc)}
