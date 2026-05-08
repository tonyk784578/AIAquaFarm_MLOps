"""Monitoring API — water quality, fish growth, and feeding time-series data.

Exposes paginated historical queries and latest-value endpoints consumed
by the dashboard panels and alert evaluation logic.
"""

from datetime import datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import get_redis
from app.db.session import get_db
from app.schemas.feeding import FeedingRead
from app.schemas.fish_growth import FishGrowthCreate, FishGrowthRead
from app.schemas.water_quality import WaterQualityCreate, WaterQualityRead
from app.services.monitoring_service import MonitoringService

router = APIRouter()


@router.get("/water-quality/latest", response_model=list[WaterQualityRead])
async def get_latest_water_quality(
    tank_id: str | None = Query(None, description="Filter by tank ID"),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[WaterQualityRead]:
    """Return the most recent water quality readings.

    Args:
        tank_id: Optional tank filter.
        limit: Maximum number of records to return.
        db: Injected async DB session.

    Returns:
        List of latest WaterQualityRead records ordered by timestamp desc.
    """
    service = MonitoringService(db)
    return await service.get_latest_water_quality(tank_id=tank_id, limit=limit)


@router.get(
    "/water-quality/history",
    response_model=list[dict[str, Any]],
    summary="Hourly-bucketed water quality history (TimescaleDB time_bucket)",
)
async def get_water_quality_history(
    tank_id: str = Query(..., description="Tank ID"),
    start_time: datetime | None = Query(None, description="Range start (ISO 8601)"),
    end_time: datetime | None = Query(None, description="Range end (ISO 8601)"),
    bucket_minutes: int = Query(60, ge=1, le=1440, description="Bucket width in minutes"),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return time-bucketed water quality averages from TimescaleDB.

    Uses ``time_bucket()`` to aggregate raw readings into evenly spaced
    intervals, suitable for chart rendering.

    Args:
        tank_id: Tank to query.
        start_time: Optional range start.
        end_time: Optional range end.
        bucket_minutes: Bucket width (default 60 = 1 h).
        limit: Maximum buckets.
        db: Injected async DB session.

    Returns:
        List of bucket dicts with averaged metrics.
    """
    service = MonitoringService(db)
    return await service.get_water_quality_history(
        tank_id=tank_id,
        start_time=start_time,
        end_time=end_time,
        bucket_minutes=bucket_minutes,
        limit=limit,
    )


@router.get("/feeding/latest", response_model=list[FeedingRead])
async def get_latest_feeding(
    tank_id: str | None = Query(None, description="Filter by tank ID"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[FeedingRead]:
    """Return the most recent feeding records.

    Args:
        tank_id: Optional tank filter.
        limit: Maximum number of records.
        db: Injected async DB session.

    Returns:
        Latest FeedingRead records ordered by started_at desc.
    """
    service = MonitoringService(db)
    return await service.get_latest_feeding(tank_id=tank_id, limit=limit)


@router.get("/fish-growth/latest", response_model=list[FishGrowthRead])
async def get_latest_fish_growth(
    tank_id: str | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[FishGrowthRead]:
    """Return the most recent fish growth measurements.

    Args:
        tank_id: Optional tank filter.
        limit: Maximum records.
        db: Injected async DB session.

    Returns:
        Latest FishGrowthRead records.
    """
    service = MonitoringService(db)
    return await service.get_latest_fish_growth(tank_id=tank_id, limit=limit)


# ── Write endpoints (edge sensor / seed script / AI modules) ───────────────────

@router.post(
    "/water-quality",
    response_model=WaterQualityRead,
    status_code=201,
    summary="Ingest a water quality reading",
)
async def create_water_quality(
    payload: WaterQualityCreate,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> WaterQualityRead:
    """Persist a single water quality reading from an edge sensor or virtual sensor.

    Called by:
    - Edge sensor reader (physical Modbus/MQTT sensor data)
    - Seed script (synthetic test data)
    - SensorPublisher background task (virtual ODE sensor)

    Invalidates the dashboard cache in Redis so the next summary poll
    reflects the new reading immediately.
    """
    service = MonitoringService(db, redis=redis)
    return await service.create_water_quality_reading(payload)


@router.post(
    "/fish-growth",
    response_model=FishGrowthRead,
    status_code=201,
    summary="Ingest a fish growth measurement",
)
async def create_fish_growth(
    payload: FishGrowthCreate,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> FishGrowthRead:
    """Persist a fish growth measurement from the growth AI module.

    Called by:
    - Growth AI module after frame analysis
    - Seed script (synthetic test data)
    """
    service = MonitoringService(db, redis=redis)
    return await service.create_fish_growth_record(payload)
