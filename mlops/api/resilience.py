"""Resilience primitives for ``mlops_api`` → MLflow calls.

Two cooperating components:

* **CircuitBreaker** — Bounds cascading failure when the MLflow tracking
  server is slow or down. Standard 3-state machine:

      CLOSED → ``failure_threshold`` consecutive failures → OPEN
      OPEN  → wait ``recovery_seconds`` → HALF_OPEN
      HALF_OPEN → next call: success → CLOSED, failure → OPEN

  While OPEN, ``call()`` raises ``CircuitOpenError`` immediately without
  invoking the wrapped function.

* **ResponseCache** — Tiny in-memory TTL cache. When the circuit is open
  (or the call fails), endpoints fall back to the most recent cached
  response so the dashboard keeps rendering.

Both components are pure stdlib — no extra dependency.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ── Circuit breaker ───────────────────────────────────────────────────────────


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised by ``CircuitBreaker.call`` when the circuit is open."""


@dataclass
class CircuitBreaker:
    """3-state circuit breaker for async callables.

    Attributes:
        name: Identifier used in log lines.
        failure_threshold: Consecutive failures to open the circuit.
        recovery_seconds: Time before transitioning OPEN → HALF_OPEN.
        state: Current state.
        failures: Consecutive failure counter (reset on success).
        opened_at: Monotonic timestamp when the circuit last opened.
    """

    name: str
    failure_threshold: int = 5
    recovery_seconds: float = 30.0
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    opened_at: float = 0.0

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        """Invoke ``func()`` under the circuit's policy.

        Raises:
            CircuitOpenError: If the circuit is OPEN.
            Whatever exception ``func`` raised, after recording the failure.
        """
        async with self._lock:
            self._maybe_attempt_recovery()
            if self.state is CircuitState.OPEN:
                raise CircuitOpenError(f"circuit '{self.name}' is open")

        try:
            result = await func()
        except Exception:
            async with self._lock:
                self._record_failure()
            raise

        async with self._lock:
            self._record_success()
        return result

    # ── Internal state transitions ────────────────────────────────────────────

    def _maybe_attempt_recovery(self) -> None:
        if self.state is CircuitState.OPEN and (
            time.monotonic() - self.opened_at >= self.recovery_seconds
        ):
            logger.info("circuit_half_open name=%s", self.name)
            self.state = CircuitState.HALF_OPEN

    def _record_success(self) -> None:
        if self.state is not CircuitState.CLOSED:
            logger.info("circuit_closed name=%s", self.name)
        self.state = CircuitState.CLOSED
        self.failures = 0

    def _record_failure(self) -> None:
        self.failures += 1
        if self.state is CircuitState.HALF_OPEN or self.failures >= self.failure_threshold:
            if self.state is not CircuitState.OPEN:
                logger.warning(
                    "circuit_open name=%s failures=%d",
                    self.name,
                    self.failures,
                )
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()


# ── Response cache ────────────────────────────────────────────────────────────


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float


class ResponseCache:
    """Tiny TTL cache used as fallback when MLflow is unavailable.

    Cached values survive past ``ttl_seconds`` for fallback use even after
    expiration — ``get_stale`` returns the last value regardless of age, so
    the dashboard keeps showing the previous registry/audit/drift snapshot
    instead of 500ing when the breaker is open.
    """

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, _Entry[Any]] = {}
        self._lock = asyncio.Lock()

    async def get_fresh(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.expires_at < time.monotonic():
                return None
            return entry.value

    async def get_stale(self, key: str) -> Any | None:
        """Return the last cached value regardless of age, or None."""
        async with self._lock:
            entry = self._entries.get(key)
            return entry.value if entry is not None else None

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._entries[key] = _Entry(value=value, expires_at=time.monotonic() + self.ttl_seconds)

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()


# ── Combined helper ───────────────────────────────────────────────────────────


async def call_with_fallback(
    *,
    breaker: CircuitBreaker,
    cache: ResponseCache,
    key: str,
    func: Callable[[], Awaitable[T]],
) -> tuple[T, bool]:
    """Run ``func`` through the breaker; on failure, return cached value.

    Args:
        breaker: Circuit breaker guarding ``func``.
        cache: TTL cache providing fallback values.
        key: Cache key (e.g. ``"registry"``, ``"drift"``).
        func: Async producer of the fresh value.

    Returns:
        Tuple ``(value, was_fallback)``. ``was_fallback`` is True when the
        returned value came from the cache because the upstream call failed.

    Raises:
        CircuitOpenError or the upstream exception if no cached value
        exists yet (cold start).
    """
    # Fresh path
    try:
        fresh = await breaker.call(func)
    except Exception as exc:
        stale = await cache.get_stale(key)
        if stale is not None:
            logger.warning(
                "mlflow_fallback_to_cache key=%s reason=%s",
                key,
                exc.__class__.__name__,
            )
            return stale, True
        raise

    await cache.set(key, fresh)
    return fresh, False
