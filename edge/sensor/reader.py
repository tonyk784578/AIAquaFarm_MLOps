"""Edge sensor reader — reads from physical water quality sensors.

Supports Modbus RTU/TCP and MQTT-based sensor protocols.
Sends readings to backend API and publishes to Redis.

Supported sensors (Phase 2 target):
  - YSI ProDSS (dissolved oxygen, temperature, salinity)
  - Atlas Scientific (pH, ammonia, nitrite via I2C/UART)
  - Endress+Hauser turbidity (Modbus TCP)

TODO (Phase 2): Implement Modbus driver using pymodbus.
TODO (Phase 2): Implement MQTT subscriber using paho-mqtt.
"""

import asyncio
from datetime import datetime, timezone

import httpx
import structlog

logger = structlog.get_logger()

BACKEND_URL = "http://backend:8000"
SENSOR_READ_INTERVAL = 5  # seconds


async def read_sensors(tank_id: str) -> dict:
    """Read all sensors for a tank.

    Args:
        tank_id: Tank identifier.

    Returns:
        Sensor reading dict.

    TODO (Phase 2): Replace with real Modbus/MQTT reads.
    """
    import random
    return {
        "tank_id": tank_id,
        "measured_at": datetime.now(tz=timezone.utc).isoformat(),
        "temperature_c": round(22.5 + random.gauss(0, 0.3), 2),
        "ph": round(7.2 + random.gauss(0, 0.05), 2),
        "dissolved_oxygen_mgl": round(7.8 + random.gauss(0, 0.2), 2),
        "turbidity_ntu": round(1.5 + random.uniform(0, 0.3), 2),
        "source": "sensor",
    }


async def run_sensor(tank_ids: list[str] | None = None) -> None:
    """Main sensor reading loop.

    Args:
        tank_ids: List of tanks to monitor.

    TODO (Phase 2): Read from real sensor drivers.
    """
    tanks = tank_ids or ["T001", "T002", "T003"]
    logger.info("edge_sensor_reader_started", tanks=tanks)

    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            for tank_id in tanks:
                reading = await read_sensors(tank_id)
                try:
                    await client.post(
                        f"{BACKEND_URL}/api/v1/monitoring/water-quality",
                        json=reading,
                    )
                except httpx.HTTPError as e:
                    logger.error("sensor_push_failed", tank_id=tank_id, error=str(e))
            await asyncio.sleep(SENSOR_READ_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_sensor())
