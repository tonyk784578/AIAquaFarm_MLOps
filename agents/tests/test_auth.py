"""Tests for the service-key FastAPI dependency."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.runtime.auth import require_service_key


def _app():
    app = FastAPI()

    @app.post("/protected", dependencies=[__import__("fastapi").Depends(require_service_key)])
    def protected():
        return {"ok": True}

    return app


def test_protected_requires_service_key():
    client = TestClient(_app())
    resp = client.post("/protected")
    assert resp.status_code == 401


def test_protected_accepts_correct_key():
    client = TestClient(_app())
    # conftest.py sets BACKEND_API_KEY=test-service-key
    resp = client.post("/protected", headers={"X-Service-Key": "test-service-key"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_protected_rejects_wrong_key():
    client = TestClient(_app())
    resp = client.post("/protected", headers={"X-Service-Key": "wrong"})
    assert resp.status_code == 401
