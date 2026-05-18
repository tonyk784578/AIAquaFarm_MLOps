"""Retry decorators for transient failures in agent nodes.

Built on tenacity. Two profiles:

* ``@retry_http`` — for backend HTTP calls. Retries on connection errors,
  timeouts, and 5xx responses (HTTPStatusError with .response.status_code >= 500).
  Up to 3 attempts, exponential backoff 0.5 → 4 s.

* ``@retry_llm`` — for Anthropic Messages API. Retries on rate-limit errors,
  connection errors, and 5xx. Up to 4 attempts with longer backoff to respect
  rate limits.

Both decorators log every retry attempt with structlog. Non-retryable
exceptions (4xx other than 429, ValueError, etc.) bubble up immediately.
"""

from __future__ import annotations

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    after_log,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random_exponential,
)

logger = structlog.get_logger()


# ── HTTP retry predicate ───────────────────────────────────────────────────────


def _is_retryable_http(exc: BaseException) -> bool:
    """Decide whether an exception from httpx should trigger a retry."""
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return False


# ── LLM retry predicate ───────────────────────────────────────────────────────


def _is_retryable_llm(exc: BaseException) -> bool:
    """Decide whether an exception from the Anthropic SDK should retry."""
    name = exc.__class__.__name__
    # Anthropic SDK raises APIConnectionError, APITimeoutError, RateLimitError,
    # InternalServerError — all retryable. We match by class name to avoid a
    # hard import of the anthropic package at module load time.
    if name in {
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
        "ServiceUnavailableError",
    }:
        return True
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError)):
        return True
    return False


# ── Decorators ────────────────────────────────────────────────────────────────


def retry_http(max_attempts: int = 3):
    """Decorator: retry an async function on transient HTTP failures.

    Args:
        max_attempts: Maximum total attempts (including the first call).

    Usage::

        @retry_http(max_attempts=3)
        async def fetch_snapshot():
            ...
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(max_attempts),
                    wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
                    retry=retry_if_exception(_is_retryable_http),
                    reraise=True,
                ):
                    with attempt:
                        result = await func(*args, **kwargs)
                        if attempt.retry_state.attempt_number > 1:
                            logger.info(
                                "retry_http_success",
                                function=func.__name__,
                                attempt=attempt.retry_state.attempt_number,
                            )
                        return result
            except RetryError as exc:
                logger.error(
                    "retry_http_exhausted",
                    function=func.__name__,
                    attempts=max_attempts,
                    error=str(exc.last_attempt.exception()) if exc.last_attempt else "unknown",
                )
                raise

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


def retry_llm(max_attempts: int = 4):
    """Decorator: retry an async function on transient LLM API failures.

    Slower backoff and more attempts than ``retry_http`` to respect rate
    limits and survive brief Anthropic outages.

    Args:
        max_attempts: Maximum total attempts.
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(max_attempts),
                    wait=wait_random_exponential(multiplier=1.0, min=1.0, max=20.0),
                    retry=retry_if_exception(_is_retryable_llm),
                    reraise=True,
                ):
                    with attempt:
                        result = await func(*args, **kwargs)
                        if attempt.retry_state.attempt_number > 1:
                            logger.info(
                                "retry_llm_success",
                                function=func.__name__,
                                attempt=attempt.retry_state.attempt_number,
                            )
                        return result
            except RetryError as exc:
                logger.error(
                    "retry_llm_exhausted",
                    function=func.__name__,
                    attempts=max_attempts,
                    error=str(exc.last_attempt.exception()) if exc.last_attempt else "unknown",
                )
                raise

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


# Re-export tenacity bits that callers may want
__all__ = [
    "AsyncRetrying",
    "RetryError",
    "after_log",
    "retry_http",
    "retry_if_exception_type",
    "retry_llm",
    "stop_after_attempt",
    "wait_exponential",
]
