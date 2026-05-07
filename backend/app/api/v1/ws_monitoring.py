"""WebSocket endpoint for real-time monitoring data push.

Clients connect to WS /api/v1/ws/monitoring/{tank_id} and receive
JSON-encoded WSMessage events whenever new water quality readings
are published to the Redis channel "wq:{tank_id}".

Message format:
    {"type": "water_quality", "tank_id": "TANK-01",
     "timestamp": "...", "data": {WaterQualityReading fields}}
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings

logger = structlog.get_logger()
router = APIRouter()

_PING_INTERVAL = 30  # seconds between server-side pings


async def _redis_listener(tank_id: str, websocket: WebSocket) -> None:
    """Subscribe to the Redis channel for a tank and forward messages.

    Runs until the WebSocket is closed or the Redis connection drops.
    """
    settings = get_settings()
    try:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        channel = f"wq:{tank_id}"
        await pubsub.subscribe(channel)
        logger.info("ws_subscribed", tank_id=tank_id, channel=channel)

        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])

    except Exception as exc:
        logger.error("ws_redis_listener_error", tank_id=tank_id, error=str(exc))
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await redis_client.aclose()
        except Exception:
            pass


async def _ping_loop(websocket: WebSocket) -> None:
    """Send periodic pings to detect dead connections."""
    while True:
        await asyncio.sleep(_PING_INTERVAL)
        await websocket.send_json({"type": "ping"})


@router.websocket("/monitoring/{tank_id}")
async def ws_monitoring(websocket: WebSocket, tank_id: str) -> None:
    """WebSocket endpoint for real-time water quality monitoring.

    Args:
        websocket: WebSocket connection.
        tank_id: Tank identifier to subscribe to (e.g. ``TANK-01``).
             Use ``ALL`` to receive updates from all tanks.

    The client will receive JSON messages with this shape::

        {
          "type": "water_quality",
          "tank_id": "TANK-01",
          "timestamp": "2024-01-15T10:30:00Z",
          "data": { ...WaterQualityReading fields... }
        }
    """
    await websocket.accept()
    logger.info("ws_client_connected", tank_id=tank_id)

    try:
        # Run listener and ping concurrently; cancel both when either exits
        listener_task = asyncio.create_task(_redis_listener(tank_id, websocket))
        ping_task = asyncio.create_task(_ping_loop(websocket))

        done, pending = await asyncio.wait(
            [listener_task, ping_task],
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        logger.info("ws_client_disconnected", tank_id=tank_id)
    except Exception as exc:
        logger.error("ws_error", tank_id=tank_id, error=str(exc))
    finally:
        logger.info("ws_connection_closed", tank_id=tank_id)
