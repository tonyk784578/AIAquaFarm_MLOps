"""Shared pytest fixtures for the agents test suite."""

from __future__ import annotations

import os

import pytest

# Ensure required env vars exist before AgentSettings is constructed.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("BACKEND_API_KEY", "test-service-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def fake_redis():
    """Return an async fakeredis client for state-store/event-bus tests."""
    try:
        import fakeredis.aioredis  # type: ignore[import-untyped]
    except ImportError:
        pytest.skip("fakeredis not installed")
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()
