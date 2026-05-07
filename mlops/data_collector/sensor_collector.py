"""Sensor data collector — polls physical water quality sensors.

Runs as a background service, polling sensors every N seconds,
writing readings to the backend API, triggering virtual sensor
prediction, and publishing real-time updates to Redis.

Protocol note: Real Modbus/MQTT drivers should replace
collect_sensor_reading() when physical hardware is available.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import httpx
import structlog

logger = structlog.get_logger()

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
POLL_INTERVAL_SECONDS = int(os.getenv("SENSOR_POLL_INTERVAL", "5"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


async def collect_sensor_reading(tank_id: str) -> dict:
    """Simulate reading from a physical water quality sensor.

    Replace this function with a real Modbus/MQTT driver when
    physical hardware is available.

    Args:
        tank_id: Tank identifier.

    Returns:
        Sensor reading dict matching WaterQualityCreate schema.
    """
    import random

    hour = datetime.now(timezone.utc).hour
    # Diurnal temp pattern
    temp = round(22.5 + 1.5 * __import__("math").sin(2 * 3.14159 * (hour - 6) / 24)
                 + random.gauss(0, 0.15), 2)
    return {
        "tank_id": tank_id,
        "measured_at": datetime.now(tz=timezone.utc).isoformat(),
        "temperature_c": temp,
        "ph": round(7.2 + random.gauss(0, 0.05), 3),
        "dissolved_oxygen_mgl": round(max(4.0, 8.2 - 0.1 * (temp - 22) + random.gauss(0, 0.1)), 3),
        "turbidity_ntu": round(abs(random.gauss(1.8, 0.3)), 3),
        "source": "sensor",
    }


async def push_reading_to_backend(
    reading: dict,
    client: httpx.AsyncClient,
) -> dict | None:
    """POST sensor reading to backend API.

    Args:
        reading: Sensor reading dict.
        client: Reused async HTTP client.

    Returns:
        Saved reading dict from the API, or None on failure.
    """
    try:
        resp = await client.post(
            f"{BACKEND_URL}/api/v1/monitoring/water-quality",
            json=reading,
            timeout=5.0,
        )
        resp.raise_for_status()
        logger.debug("sensor_reading_pushed", tank_id=reading["tank_id"])
        return resp.json()
    except httpx.HTTPError as exc:
        logger.error("sensor_push_failed", error=str(exc), tank_id=reading["tank_id"])
        return None


async def trigger_wq_prediction(
    tank_id: str,
    client: httpx.AsyncClient,
) -> dict | None:
    """Call the water quality prediction endpoint after each sensor reading.

    Runs inference using the last 24 h of readings from TimescaleDB,
    stores the predicted ammonia/nitrite in the DB, and returns the result.

    Args:
        tank_id: Tank identifier.
        client: Reused async HTTP client.

    Returns:
        PredictResponse dict, or None if inference is unavailable.
    """
    try:
        resp = await client.post(
            f"{BACKEND_URL}/api/v1/water-quality/predict",
            json={"tank_id": tank_id},
            timeout=15.0,
        )
        if resp.status_code == 503:
            # Engine not yet loaded — skip silently
            return None
        resp.raise_for_status()
        result = resp.json()
        logger.info(
            "wq_prediction_complete",
            tank_id=tank_id,
            ammonia_ppm=result.get("ammonia_ppm"),
            nitrite_ppm=result.get("nitrite_ppm"),
            ammonia_alert=result.get("ammonia_alert"),
        )
        return result
    except httpx.HTTPError as exc:
        logger.debug("wq_prediction_unavailable", tank_id=tank_id, error=str(exc))
        return None


async def publish_to_redis(tank_id: str, reading: dict) -> None:
    """Publish the latest reading to Redis so WebSocket clients are notified.

    Args:
        tank_id: Tank identifier.
        reading: Combined physical + virtual sensor reading dict.
    """
    import json

    try:
        import redis.asyncio as aioredis

        message = json.dumps(
            {
                "type": "water_quality",
                "tank_id": tank_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": reading,
            },
            default=str,
        )
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        await r.publish(f"wq:{tank_id}", message)
        await r.aclose()
    except Exception as exc:
        logger.debug("redis_publish_failed", tank_id=tank_id, error=str(exc))


async def process_tank(tank_id: str, client: httpx.AsyncClient) -> None:
    """Full pipeline for one tank: collect → push → predict → publish.

    Args:
        tank_id: Tank identifier.
        client: Reused async HTTP client.
    """
    reading = await collect_sensor_reading(tank_id)
    saved = await push_reading_to_backend(reading, client)

    # Trigger WQ inference (best-effort; won't block if model not loaded)
    prediction = await trigger_wq_prediction(tank_id, client)

    # Merge prediction fields into reading for the Redis event
    combined = {**(saved or reading)}
    if prediction:
        combined.update({
            "ammonia_ppm": prediction.get("ammonia_ppm"),
            "nitrite_ppm": prediction.get("nitrite_ppm"),
            "ammonia_confidence": prediction.get("ammonia_confidence"),
            "nitrite_confidence": prediction.get("nitrite_confidence"),
            "ammonia_alert": prediction.get("ammonia_alert"),
            "nitrite_alert": prediction.get("nitrite_alert"),
        })

    await publish_to_redis(tank_id, combined)


async def run_collector(tank_ids: list[str]) -> None:
    """Main sensor collection loop — polls all tanks at POLL_INTERVAL_SECONDS.

    Args:
        tank_ids: List of tank IDs to poll.
    """
    logger.info("sensor_collector_started", tanks=tank_ids, interval=POLL_INTERVAL_SECONDS)
    async with httpx.AsyncClient() as client:
        while True:
            tasks = [process_tank(tid, client) for tid in tank_ids]
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    tanks = os.getenv("TANK_IDS", "TANK-01,TANK-02,TANK-03").split(",")
    asyncio.run(run_collector(tanks))
