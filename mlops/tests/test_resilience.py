"""Unit tests for mlops/api/resilience.py — circuit breaker + response cache."""

from __future__ import annotations

import asyncio

import pytest

from mlops.api.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    ResponseCache,
    call_with_fallback,
)


# ── CircuitBreaker ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_breaker_starts_closed_and_passes_calls():
    breaker = CircuitBreaker(name="t", failure_threshold=3)

    async def ok():
        return "value"

    assert await breaker.call(ok) == "value"
    assert breaker.state is CircuitState.CLOSED


@pytest.mark.asyncio
async def test_breaker_opens_after_consecutive_failures():
    breaker = CircuitBreaker(name="t", failure_threshold=2, recovery_seconds=60)

    async def boom():
        raise RuntimeError("upstream down")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    assert breaker.state is CircuitState.CLOSED

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN


@pytest.mark.asyncio
async def test_breaker_open_short_circuits_without_calling_func():
    breaker = CircuitBreaker(name="t", failure_threshold=1, recovery_seconds=60)

    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN

    calls = {"n": 0}

    async def ok():
        calls["n"] += 1
        return "should not run"

    with pytest.raises(CircuitOpenError):
        await breaker.call(ok)
    assert calls["n"] == 0  # func was never invoked


@pytest.mark.asyncio
async def test_breaker_recovers_after_recovery_window():
    breaker = CircuitBreaker(name="t", failure_threshold=1, recovery_seconds=0.05)

    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN

    await asyncio.sleep(0.06)

    async def ok():
        return "recovered"

    assert await breaker.call(ok) == "recovered"
    assert breaker.state is CircuitState.CLOSED


@pytest.mark.asyncio
async def test_breaker_half_open_failure_reopens():
    breaker = CircuitBreaker(name="t", failure_threshold=1, recovery_seconds=0.05)

    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)

    await asyncio.sleep(0.06)  # → HALF_OPEN on next call

    with pytest.raises(RuntimeError):
        await breaker.call(boom)

    assert breaker.state is CircuitState.OPEN


# ── ResponseCache ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_returns_fresh_within_ttl():
    cache = ResponseCache(ttl_seconds=10)
    await cache.set("k", {"a": 1})
    assert await cache.get_fresh("k") == {"a": 1}


@pytest.mark.asyncio
async def test_cache_get_fresh_returns_none_after_expiry():
    cache = ResponseCache(ttl_seconds=0.01)
    await cache.set("k", "v")
    await asyncio.sleep(0.02)
    assert await cache.get_fresh("k") is None


@pytest.mark.asyncio
async def test_cache_get_stale_survives_expiry():
    cache = ResponseCache(ttl_seconds=0.01)
    await cache.set("k", "v")
    await asyncio.sleep(0.02)
    assert await cache.get_stale("k") == "v"


# ── call_with_fallback ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fallback_returns_cached_when_breaker_open():
    breaker = CircuitBreaker(name="t", failure_threshold=1, recovery_seconds=60)
    cache = ResponseCache(ttl_seconds=10)
    await cache.set("registry", {"models": ["seeded"]})

    async def boom():
        raise RuntimeError("mlflow down")

    # First call fails and trips the breaker, but cache provides fallback
    value, was_fallback = await call_with_fallback(
        breaker=breaker, cache=cache, key="registry", func=boom
    )
    assert was_fallback is True
    assert value == {"models": ["seeded"]}
    assert breaker.state is CircuitState.OPEN


@pytest.mark.asyncio
async def test_fallback_raises_when_no_cache_and_circuit_open():
    breaker = CircuitBreaker(name="t", failure_threshold=1, recovery_seconds=60)
    cache = ResponseCache(ttl_seconds=10)

    async def boom():
        raise RuntimeError("down")

    # Cold start with no cached value — caller sees the underlying error
    with pytest.raises(RuntimeError):
        await call_with_fallback(breaker=breaker, cache=cache, key="x", func=boom)

    # Subsequent call: breaker open, still no cache → raises CircuitOpenError
    with pytest.raises(CircuitOpenError):
        await call_with_fallback(breaker=breaker, cache=cache, key="x", func=boom)


@pytest.mark.asyncio
async def test_fresh_call_caches_value():
    breaker = CircuitBreaker(name="t", failure_threshold=5)
    cache = ResponseCache(ttl_seconds=10)

    async def ok():
        return {"models": ["live"]}

    value, was_fallback = await call_with_fallback(
        breaker=breaker, cache=cache, key="registry", func=ok
    )
    assert value == {"models": ["live"]}
    assert was_fallback is False
    assert await cache.get_fresh("registry") == {"models": ["live"]}
