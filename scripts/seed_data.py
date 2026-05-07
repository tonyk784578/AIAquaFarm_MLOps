"""Seed test data into the AIAquafarm database.

Generates realistic synthetic sensor readings, fish growth records,
feeding events, and sample alerts for development and demo purposes.

Usage:
    python scripts/seed_data.py
    # or
    make seed
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone

import httpx

BASE_URL = "http://localhost:8000"
TANK_IDS = ["T001", "T002", "T003"]
DAYS_OF_HISTORY = 7


def random_water_quality(tank_id: str, timestamp: datetime) -> dict:
    """Generate a realistic water quality reading."""
    return {
        "tank_id": tank_id,
        "measured_at": timestamp.isoformat(),
        "temperature_c": round(22.5 + random.gauss(0, 0.5), 2),
        "ph": round(7.2 + random.gauss(0, 0.1), 2),
        "dissolved_oxygen_mgl": round(7.8 + random.gauss(0, 0.3), 2),
        "turbidity_ntu": round(max(0.1, 1.5 + random.gauss(0, 0.2)), 2),
        "ammonia_ppm": round(max(0, random.gauss(0.15, 0.05)), 3),
        "nitrite_ppm": round(max(0, random.gauss(0.03, 0.01)), 3),
        "source": "sensor",
        "ammonia_confidence": 0.85,
        "nitrite_confidence": 0.80,
    }


def random_fish_growth(tank_id: str, timestamp: datetime, day: int) -> dict:
    """Generate realistic fish growth record (growth trend over days)."""
    base_weight = 150.0 + day * 2.5  # ~2.5g/day growth
    return {
        "tank_id": tank_id,
        "measured_at": timestamp.isoformat(),
        "avg_length_cm": round(18.0 + day * 0.1 + random.gauss(0, 0.2), 2),
        "avg_weight_g": round(base_weight + random.gauss(0, 3), 1),
        "fish_count": random.randint(480, 500),
        "biomass_kg": round((base_weight * 490) / 1000, 2),
        "daily_growth_rate_pct": round(random.gauss(1.5, 0.2), 2),
        "feed_conversion_ratio": round(random.gauss(1.2, 0.1), 2),
        "model_version": "stub-v0.1",
        "inference_confidence": 0.92,
        "frame_count_analyzed": random.randint(50, 100),
    }


async def seed() -> None:
    """Run the full seeding pipeline."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Health check
        resp = await client.get("/health")
        if resp.status_code != 200:
            print(f"Backend not healthy: {resp.status_code}")
            return
        print("Backend healthy — starting seed...")

        now = datetime.now(tz=timezone.utc)
        total = 0

        for day in range(DAYS_OF_HISTORY, 0, -1):
            for hour in range(0, 24, 1):  # Hourly readings
                ts = now - timedelta(days=day, hours=hour)
                for tank_id in TANK_IDS:
                    # Water quality
                    wq = random_water_quality(tank_id, ts)
                    try:
                        await client.post("/api/v1/monitoring/water-quality", json=wq)
                        total += 1
                    except Exception as e:
                        print(f"  WQ write failed: {e}")

                    # Fish growth (once per day at noon)
                    if hour == 12:
                        fg = random_fish_growth(tank_id, ts, DAYS_OF_HISTORY - day)
                        try:
                            await client.post("/api/v1/monitoring/fish-growth", json=fg)
                            total += 1
                        except Exception as e:
                            print(f"  Growth write failed: {e}")

        # Seed a sample alert
        alert = {
            "tank_id": "T001",
            "severity": "warning",
            "category": "water_quality",
            "title": "암모니아 경고 수준 감지",
            "message": "T001 수조 암모니아 농도가 0.45 ppm으로 경고 임계값 0.5 ppm에 근접했습니다.",
            "metric_name": "ammonia_ppm",
            "metric_value": "0.45",
            "threshold_value": "0.5",
            "source": "virtual_sensor",
        }
        try:
            await client.post("/api/v1/alerts/", json=alert)
        except Exception as e:
            print(f"  Alert seed failed: {e}")

        print(f"Seeding complete — {total} records written.")


if __name__ == "__main__":
    asyncio.run(seed())
