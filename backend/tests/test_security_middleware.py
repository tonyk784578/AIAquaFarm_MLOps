"""Tests for the request-size + security-headers middlewares."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security_middleware import (
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)


def _app(max_bytes: int = 32) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=max_bytes)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ok")
    def read_ok() -> dict:
        return {"ok": True}

    @app.post("/echo")
    def echo(payload: dict) -> dict:
        return payload

    return app


def test_get_passes_through_under_limit():
    client = TestClient(_app())
    resp = client.get("/ok")
    assert resp.status_code == 200
    # Security headers should be present on every response
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_post_under_limit_succeeds():
    client = TestClient(_app(max_bytes=1024))
    resp = client.post("/echo", json={"k": "v"})
    assert resp.status_code == 200
    assert resp.json() == {"k": "v"}


def test_content_length_over_limit_rejected_with_413():
    client = TestClient(_app(max_bytes=32))
    big_payload = {"data": "x" * 200}
    resp = client.post("/echo", json=big_payload)
    assert resp.status_code == 413
    body = resp.json()
    assert body["detail"] == "request body too large"
    assert body["max_bytes"] == 32
    assert body["observed_bytes"] >= 32


def test_security_headers_do_not_override_handler_headers():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, headers={"X-Custom": "from-mw"})

    @app.get("/explicit")
    def explicit():
        from starlette.responses import JSONResponse
        return JSONResponse({"ok": True}, headers={"X-Custom": "from-handler"})

    client = TestClient(app)
    resp = client.get("/explicit")
    # Handler-set header wins; middleware only adds what's missing.
    assert resp.headers["x-custom"] == "from-handler"
