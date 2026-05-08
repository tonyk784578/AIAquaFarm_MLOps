"""WebSocket endpoint for real-time monitoring data push.

Clients connect to WS /api/v1/ws/monitoring/{tank_id} and receive
JSON-encoded WSMessage events from two Redis channels:

  * ``wq:{tank_id}``   — water quality readings for the requested tank
  * ``events:alerts``  — new alert events (all tanks); filtered by tank_id
                         before forwarding (pass ``ALL`` to skip filter)

Message formats:
    {"type": "water_quality", "tank_id": "TANK-01", "timestamp": "...", "data": {...}}
    {"type": "alert",         "tank_id": "TANK-01", "timestamp": "...", "data": {...}}
    {"type": "ping"}
"""

from __future__ import annotations

import asyncio
import json
import re

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings

logger = structlog.get_logger()
router = APIRouter()

_PING_INTERVAL = 30  # seconds between server-side pings
_ALERTS_CHANNEL = "events:alerts"


async def _redis_listener(tank_id: str, websocket: WebSocket) -> None:
    """Subscribe to the Redis channels for a tank and forward messages.

    Subscribes to:
    - ``wq:{tank_id}`` for water quality data
    - ``events:alerts`` for real-time alert push (filtered by tank_id unless ``ALL``)

    Runs until the WebSocket is closed or the Redis connection drops.
    """
    settings = get_settings()
    wq_channel = f"wq:{tank_id}"
    redis_client: aioredis.Redis | None = None
    pubsub = None
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(wq_channel, _ALERTS_CHANNEL)
        logger.info(
            "ws_subscribed",
            tank_id=tank_id,
            channels=[wq_channel, _ALERTS_CHANNEL],
        )

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            raw = message["data"]
            # For the alerts channel, only forward messages for this tank
            # (or forward all when the client subscribed with tank_id=="ALL")
            if message["channel"] == _ALERTS_CHANNEL and tank_id != "ALL":
                try:
                    parsed = json.loads(raw)
                    if parsed.get("tank_id") != tank_id:
                        continue
                except Exception:
                    continue
            await websocket.send_text(raw)

    except Exception as exc:
        logger.error("ws_redis_listener_error", tank_id=tank_id, error=str(exc))
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(wq_channel, _ALERTS_CHANNEL)
            except Exception:
                pass
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                pass


async def _ping_loop(websocket: WebSocket) -> None:
    """Send periodic pings to detect dead connections."""
    while True:
        await asyncio.sleep(_PING_INTERVAL)
        await websocket.send_json({"type": "ping"})


_TANK_ID_RE = re.compile(r"^(?:[A-Z0-9][A-Z0-9_\-]*|ALL)$")


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
    if not _TANK_ID_RE.match(tank_id):
        await websocket.close(code=1008, reason="Invalid tank_id format")
        return

    await websocket.accept()
    logger.info("ws_client_connected", tank_id=tank_id)

    try:
        # Run listener and ping concurrently; cancel both when either exits.
        # FIRST_COMPLETED is required: _redis_listener catches its own exceptions
        # and can return normally, which FIRST_EXCEPTION would not detect.
        listener_task = asyncio.create_task(_redis_listener(tank_id, websocket))
        ping_task = asyncio.create_task(_ping_loop(websocket))

        done, pending = await asyncio.wait(
            [listener_task, ping_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        logger.info("ws_client_disconnected", tank_id=tank_id)
    except Exception as exc:
        logger.error("ws_error", tank_id=tank_id, error=str(exc))
    finally:
        logger.info("ws_connection_closed", tank_id=tank_id)
