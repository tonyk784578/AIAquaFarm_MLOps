"""Seed test data into the AIAquafarm database.

SQLAlchemy 직접 삽입 방식 — HTTP API 미사용.
Usage:
    make seed
    또는: docker compose exec backend python scripts/seed_data.py
"""

import asyncio
import random
import sys
from datetime import datetime, timedelta

from sqlalchemy import select

sys.path.insert(0, "/app")

from app.db.session import AsyncSessionLocal
from app.models.alert import Alert
from app.models.feeding import FeedingRecord
from app.models.fish_growth import FishGrowthRecord
from app.models.water_quality import WaterQualityReading

TANK_IDS = ["TANK-01", "TANK-02", "TANK-03"]
DAYS = 7


def _ts(days_ago: float = 0) -> datetime:
    """UTC naive datetime (TIMESTAMP WITHOUT TIME ZONE 호환)."""
    return datetime.utcnow() - timedelta(days=days_ago)


def make_wq(tank_id: str, ts: datetime) -> WaterQualityReading:
    return WaterQualityReading(
        tank_id=tank_id,
        measured_at=ts,
        temperature_c=round(22.5 + random.gauss(0, 0.5), 2),
        ph=round(7.2 + random.gauss(0, 0.1), 2),
        dissolved_oxygen_mgl=round(7.8 + random.gauss(0, 0.3), 2),
        turbidity_ntu=round(max(0.1, 1.5 + random.gauss(0, 0.2)), 2),
        ammonia_ppm=round(max(0.0, random.gauss(0.15, 0.05)), 3),
        nitrite_ppm=round(max(0.0, random.gauss(0.03, 0.01)), 3),
        ammonia_confidence=round(random.uniform(0.80, 0.95), 2),
        nitrite_confidence=round(random.uniform(0.78, 0.92), 2),
        source="sensor",
    )


def make_growth(tank_id: str, ts: datetime, day_idx: int) -> FishGrowthRecord:
    base_w = 150.0 + day_idx * 2.5
    return FishGrowthRecord(
        tank_id=tank_id,
        measured_at=ts,
        avg_length_cm=round(18.0 + day_idx * 0.1 + random.gauss(0, 0.2), 2),
        avg_weight_g=round(base_w + random.gauss(0, 3), 1),
        fish_count=random.randint(480, 500),
        biomass_kg=round((base_w * 490) / 1000, 2),
        daily_growth_rate_pct=round(random.gauss(1.5, 0.2), 2),
        feed_conversion_ratio=round(random.gauss(1.2, 0.1), 2),
        model_version="stub-v0.1",
        inference_confidence=0.92,
        frame_count_analyzed=random.randint(50, 100),
    )


def make_feeding(tank_id: str, ts: datetime) -> FeedingRecord:
    recommended = round(random.uniform(2.5, 3.2), 2)
    return FeedingRecord(
        tank_id=tank_id,
        started_at=ts,
        ended_at=ts + timedelta(seconds=75),
        commanded_amount_kg=recommended,
        actual_amount_kg=round(recommended * random.uniform(0.9, 1.1), 2),
        duration_seconds=75,
        activity_score=round(random.uniform(0.6, 0.95), 3),
        recommended_amount_kg=recommended,
        feed_waste_estimate_pct=round(random.uniform(3.0, 12.0), 1),
        trigger_source=random.choice(["ai", "schedule"]),
        is_completed=True,
        is_emergency_stopped=False,
    )


def make_alerts() -> list[Alert]:
    now = datetime.utcnow()
    return [
        Alert(
            tank_id="TANK-01",
            created_at=now - timedelta(minutes=22),
            severity="critical",
            category="water_quality",
            title="암모니아 위험 수준 초과",
            message="TANK-01 암모니아 농도 0.82 ppm — 위험 임계값(0.8 ppm) 초과.",
            metric_name="ammonia_ppm",
            metric_value="0.82",
            threshold_value="0.80",
            source="virtual_sensor",
            is_active=True,
        ),
        Alert(
            tank_id="TANK-02",
            created_at=now - timedelta(hours=1, minutes=31),
            severity="critical",
            category="water_quality",
            title="용존산소 위험 수준",
            message="TANK-02 용존산소 5.9 mg/L — 위험 임계값(6.0 mg/L) 미만.",
            metric_name="dissolved_oxygen_mgl",
            metric_value="5.9",
            threshold_value="6.0",
            source="virtual_sensor",
            is_active=True,
        ),
        Alert(
            tank_id="TANK-03",
            created_at=now - timedelta(hours=3),
            resolved_at=now - timedelta(hours=2),
            severity="warning",
            category="feeding",
            title="급이량 과다 감지",
            message="TANK-03 실제 급이량(3.52 kg)이 권장량(3.10 kg) 대비 113% 수준.",
            metric_name="actual_amount_kg",
            metric_value="3.52",
            threshold_value="3.10",
            source="ai",
            is_active=False,
        ),
    ]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        # 기존 데이터 확인
        existing = (await db.execute(select(WaterQualityReading).limit(1))).scalar_one_or_none()
        if existing:
            print("이미 데이터가 존재합니다. 덮어쓰려면 DB를 초기화한 후 다시 실행하세요.")
            return

        print("더미 데이터 삽입 중...")
        total = 0

        for day in range(DAYS, 0, -1):
            day_idx = DAYS - day
            for hour in range(0, 24):
                ts = _ts(days_ago=day - hour / 24)
                for tank_id in TANK_IDS:
                    # 수질 (매 시간)
                    db.add(make_wq(tank_id, ts))
                    total += 1

                    # 성장 (하루 1회, 정오)
                    if hour == 12:
                        db.add(make_growth(tank_id, ts, day_idx))
                        total += 1

                    # 급이 (하루 2회, 08:00 / 18:00)
                    if hour in (8, 18):
                        db.add(make_feeding(tank_id, ts))
                        total += 1

        # 알림
        for alert in make_alerts():
            db.add(alert)
            total += 1

        await db.commit()
        print(f"완료 — {total}건 삽입")


if __name__ == "__main__":
    asyncio.run(seed())
