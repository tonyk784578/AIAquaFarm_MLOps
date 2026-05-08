"""Redis async client — singleton for the backend application.

Provides a lazy-initialised async Redis connection used for:
  - Control command pub/sub (cmd:{tank_id}:{device})
  - WebSocket push notification fan-out
  - Rate limiting / caching (future)

Channel naming convention:
  cmd:{tank_id}:feeder   — feeder on/off, amount
  cmd:{tank_id}:pump     — circulation pump speed
  cmd:{tank_id}:aeration — blower control
  cmd:{tank_id}:exchange — water exchange valve
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger()

_redis: aioredis.Redis | None = None


async def init_redis(redis_url: str) -> None:
    """Initialise the Redis connection pool.

    Called once from the FastAPI lifespan on startup.

    Args:
        redis_url: Redis connection URL (e.g. 'redis://redis:6379/0').
    """
    global _redis
    _redis = aioredis.from_url(redis_url, decode_responses=True)
    await _redis.ping()
    logger.info("redis_connected", url=redis_url)


async def close_redis() -> None:
    """Close the Redis connection pool on shutdown."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("redis_closed")


def get_redis_client() -> aioredis.Redis:
    """Return the module-level Redis client.

    Raises:
        RuntimeError: If init_redis() has not been called.
    """
    if _redis is None:
        raise RuntimeError("Redis not initialised — call init_redis() first")
    return _redis


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency that yields the Redis client."""
    yield get_redis_client()
