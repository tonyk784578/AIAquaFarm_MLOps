"""Tests for the retry decorators."""

from __future__ import annotations

import httpx
import pytest

from agents.runtime.retry import retry_http, retry_llm


@pytest.mark.asyncio
async def test_retry_http_succeeds_after_transient_failures():
    calls = {"n": 0}

    @retry_http(max_attempts=3)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("network blip")
        return "ok"

    assert await flaky() == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_http_does_not_retry_on_4xx():
    """4xx responses (other than 429) should not trigger retries."""
    request = httpx.Request("GET", "http://x")
    response = httpx.Response(400, request=request)
    err = httpx.HTTPStatusError("client error", request=request, response=response)

    calls = {"n": 0}

    @retry_http(max_attempts=3)
    async def boom():
        calls["n"] += 1
        raise err

    with pytest.raises(httpx.HTTPStatusError):
        await boom()
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retry_http_retries_on_5xx():
    request = httpx.Request("GET", "http://x")
    response = httpx.Response(503, request=request)
    err = httpx.HTTPStatusError("upstream down", request=request, response=response)

    calls = {"n": 0}

    @retry_http(max_attempts=2)
    async def boom():
        calls["n"] += 1
        raise err

    with pytest.raises(httpx.HTTPStatusError):
        await boom()
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_retry_llm_retries_on_rate_limit_by_class_name():
    class RateLimitError(Exception):
        pass

    calls = {"n": 0}

    @retry_llm(max_attempts=3)
    async def call():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("slow down")
        return "result"

    assert await call() == "result"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_retry_llm_does_not_retry_on_arbitrary_exception():
    calls = {"n": 0}

    @retry_llm(max_attempts=3)
    async def call():
        calls["n"] += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError):
        await call()
    assert calls["n"] == 1
