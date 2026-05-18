"""Cross-cutting HTTP security middlewares.

Two middlewares, both safe to enable in dev and production:

* ``RequestSizeLimitMiddleware`` — Reject requests whose body exceeds
  ``max_body_bytes`` before the route handler runs. Uses the ``Content-Length``
  header when present (cheap); otherwise streams the body in chunks and aborts
  as soon as the cumulative size exceeds the limit. Returns 413 Payload Too
  Large.

* ``SecurityHeadersMiddleware`` — Append defence-in-depth headers to every
  response (``X-Content-Type-Options``, ``X-Frame-Options``, etc.). Nginx
  already adds these for browser traffic, but direct hits to the FastAPI
  port should be hardened too.

Both are tiny Starlette pure-ASGI middlewares — no extra dependency.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 1 MiB is plenty for JSON control payloads and the AI agent's tool-use input;
# model checkpoints upload to S3/MLflow directly and never traverse FastAPI.
DEFAULT_MAX_BODY_BYTES = 1 * 1024 * 1024


class RequestSizeLimitMiddleware:
    """ASGI middleware enforcing an upper bound on request body size.

    Behaviour:
      * Skips GET / HEAD / DELETE / OPTIONS (no meaningful body expected).
      * If ``Content-Length`` is set and exceeds the limit → 413 immediately.
      * Otherwise wraps ``receive`` to count bytes; aborts at the limit.
    """

    SAFE_METHODS = frozenset({"GET", "HEAD", "DELETE", "OPTIONS"})

    def __init__(self, app: ASGIApp, max_body_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in self.SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        # Fast path: Content-Length declared and too large.
        content_length = _content_length(scope)
        if content_length is not None and content_length > self.max_body_bytes:
            await self._reject(send, content_length)
            return

        # Slow path: stream and tally.
        body_seen = 0
        limit = self.max_body_bytes

        async def receive_with_cap() -> Message:
            nonlocal body_seen
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"") or b""
                body_seen += len(body)
                if body_seen > limit:
                    # Drain the rest so the client sees a clean close, then
                    # raise to short-circuit the handler.
                    raise _BodyTooLargeError()
            return message

        try:
            await self.app(scope, receive_with_cap, send)
        except _BodyTooLargeError:
            await self._reject(send, body_seen)

    async def _reject(self, send: Send, observed: int) -> None:
        resp = JSONResponse(
            status_code=413,
            content={
                "detail": "request body too large",
                "max_bytes": self.max_body_bytes,
                "observed_bytes": observed,
            },
        )
        await resp(scope={"type": "http"}, receive=_noop_receive, send=send)


class _BodyTooLargeError(Exception):
    """Internal marker raised when streamed body exceeds the cap."""


def _content_length(scope: Scope) -> int | None:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() == b"content-length":
            try:
                return int(raw_value)
            except (TypeError, ValueError):
                return None
    return None


async def _noop_receive() -> Message:
    return {"type": "http.disconnect"}


# ── Security headers ──────────────────────────────────────────────────────────


class SecurityHeadersMiddleware:
    """Append defence-in-depth headers to every HTTP response."""

    DEFAULT_HEADERS: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }

    def __init__(self, app: ASGIApp, headers: dict[str, str] | None = None) -> None:
        self.app = app
        self.headers = {**self.DEFAULT_HEADERS, **(headers or {})}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Merge our headers — preserve any already set by the handler.
                existing = {k.decode().lower() for k, _ in message.get("headers", [])}
                extra = [
                    (k.lower().encode(), v.encode())
                    for k, v in self.headers.items()
                    if k.lower() not in existing
                ]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, send_with_headers)


# Tiny convenience for tests
async def _starlette_health(_: Request) -> Response:
    return JSONResponse({"status": "ok"})
