"""Monitoring service — data retrieval for dashboard, monitoring, and alert APIs.

Encapsulates all read-path DB queries so router functions stay thin.

Redis caching:
    get_dashboard_summary   — 5 s TTL on key "cache:dashboard:summary"
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import redis.asyncio as aioredis
import structlog
from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.feeding import FeedingRecord
from app.models.fish_growth import FishGrowthRecord
from app.models.water_quality import WaterQualityReading
from app.schemas.alert import AlertCreate, AlertRead, AlertUpdate
from app.schemas.feeding import FeedingCreate, FeedingRead
from app.schemas.fish_growth import FishGrowthCreate, FishGrowthRead
from app.schemas.water_quality import WaterQualityCreate, WaterQualityRead

logger = structlog.get_logger()

_DASHBOARD_CACHE_KEY = "cache:dashboard:summary"
_DASHBOARD_TTL_S = 5
_ALERTS_CHANNEL = "events:alerts"


class MonitoringService:
    """Handles all monitoring-related database queries."""

    def __init__(self, db: AsyncSession, redis: aioredis.Redis | None = None) -> None:
        self.db = db
        self._redis = redis

    async def get_dashboard_summary(self) -> dict:
        """Return aggregated snapshot for the main dashboard panel.

        Results are cached in Redis with a 5-second TTL to handle burst
        requests from multiple dashboard clients polling simultaneously.

        Returns:
            Dict with latest water_quality, fish_growth, and active alert count.
        """
        cached = await self._cache_get(_DASHBOARD_CACHE_KEY)
        if cached:
            return cached

        latest_wq = await self.get_latest_water_quality(limit=1)
        latest_growth = await self.get_latest_fish_growth(limit=1)
        alerts = await self.list_alerts(active_only=True, limit=10)

        summary = {
            "water_quality": latest_wq[0].model_dump() if latest_wq else None,
            "fish_growth": latest_growth[0].model_dump() if latest_growth else None,
            "active_alert_count": len(alerts),
            "recent_alerts": [a.model_dump() for a in alerts[:3]],
        }

        await self._cache_set(_DASHBOARD_CACHE_KEY, summary, ttl=_DASHBOARD_TTL_S)
        return summary

    async def get_latest_water_quality(
        self,
        tank_id: str | None = None,
        limit: int = 10,
    ) -> list[WaterQualityRead]:
        """Query the most recent water quality readings.

        Args:
            tank_id: Optional filter by tank.
            limit: Maximum records.

        Returns:
            List of WaterQualityRead ordered by measured_at desc.
        """
        stmt = select(WaterQualityReading).order_by(
            desc(WaterQualityReading.measured_at)
        )
        if tank_id:
            stmt = stmt.where(WaterQualityReading.tank_id == tank_id)
        stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [WaterQualityRead.model_validate(r) for r in rows]

    async def get_water_quality_history(
        self,
        tank_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        bucket_minutes: int = 60,
        limit: int = 100,
    ) -> list[dict]:
        """Query hourly-bucketed water quality history via TimescaleDB time_bucket.

        Args:
            tank_id: Target tank.
            start_time: Range start (inclusive).
            end_time: Range end (inclusive).
            bucket_minutes: Bucket width in minutes (default 60 = 1 h).
            limit: Maximum buckets.

        Returns:
            List of dicts with bucket timestamp and averaged metrics.
        """
        from sqlalchemy import text

        # Use make_interval to keep bucket_minutes fully parameterized (no f-string in SQL).
        where_clauses = ["tank_id = :tank_id"]
        params: dict = {"tank_id": tank_id, "limit": limit, "bucket_minutes": bucket_minutes}

        if start_time:
            where_clauses.append("measured_at >= :start_time")
            params["start_time"] = start_time
        if end_time:
            where_clauses.append("measured_at <= :end_time")
            params["end_time"] = end_time

        # where_sql is assembled exclusively from hardcoded string literals above —
        # no user input is interpolated. All actual values use :param bindings.
        where_sql = " AND ".join(where_clauses)
        sql = text(f"""
            SELECT
                time_bucket(make_interval(mins => :bucket_minutes), measured_at) AS bucket,
                avg(temperature_c)          AS temperature_c,
                avg(ph)                     AS ph,
                avg(dissolved_oxygen_mgl)   AS dissolved_oxygen_mgl,
                avg(turbidity_ntu)          AS turbidity_ntu,
                avg(ammonia_ppm)            AS ammonia_ppm,
                avg(nitrite_ppm)            AS nitrite_ppm,
                avg(ammonia_confidence)     AS ammonia_confidence,
                avg(nitrite_confidence)     AS nitrite_confidence,
                count(*)                    AS sample_count
            FROM water_quality_readings
            WHERE {where_sql}
            GROUP BY bucket
            ORDER BY bucket DESC
            LIMIT :limit
        """)

        result = await self.db.execute(sql, params)
        rows = result.mappings().all()
        return [dict(r) for r in rows]

    async def get_latest_fish_growth(
        self,
        tank_id: str | None = None,
        limit: int = 10,
    ) -> list[FishGrowthRead]:
        """Query the most recent fish growth records.

        Args:
            tank_id: Optional filter.
            limit: Maximum records.

        Returns:
            Latest FishGrowthRead records.
        """
        stmt = select(FishGrowthRecord).order_by(desc(FishGrowthRecord.measured_at))
        if tank_id:
            stmt = stmt.where(FishGrowthRecord.tank_id == tank_id)
        stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [FishGrowthRead.model_validate(r) for r in rows]

    async def get_latest_feeding(
        self,
        tank_id: str | None = None,
        limit: int = 20,
    ) -> list[FeedingRead]:
        """Query the most recent feeding records.

        Args:
            tank_id: Optional tank filter.
            limit: Maximum records.

        Returns:
            Latest FeedingRead records ordered by started_at desc.
        """
        stmt = select(FeedingRecord).order_by(desc(FeedingRecord.started_at))
        if tank_id:
            stmt = stmt.where(FeedingRecord.tank_id == tank_id)
        stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [FeedingRead.model_validate(r) for r in rows]

    # ── Write paths ────────────────────────────────────────────────────────────

    async def create_water_quality_reading(
        self,
        payload: WaterQualityCreate,
    ) -> WaterQualityRead:
        """Persist a new water quality reading from an edge sensor or virtual sensor.

        Also invalidates the dashboard Redis cache so the next poll reflects
        the latest data without waiting for the TTL to expire.

        Args:
            payload: Sensor reading data.

        Returns:
            Persisted WaterQualityRead record.
        """

        row = WaterQualityReading(**payload.model_dump())
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        logger.info(
            "water_quality_reading_created",
            tank_id=row.tank_id,
            measured_at=row.measured_at.isoformat(),
        )
        if self._redis is not None:
            try:
                await self._redis.delete(_DASHBOARD_CACHE_KEY)
            except Exception:
                pass
        return WaterQualityRead.model_validate(row)

    async def create_fish_growth_record(
        self,
        payload: FishGrowthCreate,
    ) -> FishGrowthRead:
        """Persist a new fish growth measurement from the growth AI module.

        Args:
            payload: Growth measurement data.

        Returns:
            Persisted FishGrowthRead record.
        """

        row = FishGrowthRecord(**payload.model_dump())
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        logger.info(
            "fish_growth_record_created",
            tank_id=row.tank_id,
            fish_count=row.fish_count,
        )
        if self._redis is not None:
            try:
                await self._redis.delete(_DASHBOARD_CACHE_KEY)
            except Exception:
                pass
        return FishGrowthRead.model_validate(row)

    async def create_feeding_record(
        self,
        payload: FeedingCreate,
    ) -> FeedingRead:
        """Persist a new feeding event record.

        Args:
            payload: Feeding event data.

        Returns:
            Persisted FeedingRead record.
        """

        row = FeedingRecord(**payload.model_dump())
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        logger.info("feeding_record_created", tank_id=row.tank_id)
        return FeedingRead.model_validate(row)

    async def list_alerts(
        self,
        tank_id: str | None = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[AlertRead]:
        """Query alerts with optional filters.

        Args:
            tank_id: Optional tank filter.
            active_only: Return only unresolved alerts.
            limit: Maximum records.

        Returns:
            List of AlertRead records.
        """
        stmt = select(Alert).order_by(desc(Alert.created_at)).limit(limit)
        if tank_id:
            stmt = stmt.where(Alert.tank_id == tank_id)
        if active_only:
            stmt = stmt.where(Alert.is_active.is_(True))

        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [AlertRead.model_validate(r) for r in rows]

    async def create_alert(self, payload: AlertCreate) -> AlertRead:
        """Persist a new alert record.

        Args:
            payload: Alert creation data.

        Returns:
            Persisted AlertRead record.
        """
        alert = Alert(
            **payload.model_dump(),
            created_at=datetime.now(tz=UTC),
        )
        self.db.add(alert)
        await self.db.flush()
        await self.db.refresh(alert)
        record = AlertRead.model_validate(alert)
        logger.info(
            "alert_created",
            alert_id=alert.id,
            tank_id=alert.tank_id,
            severity=alert.severity,
        )
        if self._redis is not None:
            try:
                payload_json = json.dumps(
                    {
                        "type": "alert",
                        "tank_id": alert.tank_id,
                        "timestamp": alert.created_at.isoformat(),
                        "data": record.model_dump(mode="json"),
                    }
                )
                await self._redis.publish(_ALERTS_CHANNEL, payload_json)
                logger.info("alert_published", channel=_ALERTS_CHANNEL, alert_id=alert.id)
            except Exception as exc:
                logger.warning("alert_publish_failed", error=str(exc))
        return record

    async def resolve_alert(self, alert_id: int, payload: AlertUpdate) -> AlertRead:
        """Mark an alert as resolved.

        Args:
            alert_id: Alert primary key.
            payload: Resolution notes.

        Returns:
            Updated AlertRead record.

        Raises:
            HTTPException: 404 if alert not found.
        """
        result = await self.db.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one_or_none()
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert {alert_id} not found",
            )

        alert.is_active = False
        alert.resolved_at = datetime.now(tz=UTC)
        alert.resolution_notes = payload.resolution_notes
        alert.resolved_by = payload.resolved_by
        await self.db.flush()
        await self.db.refresh(alert)
        logger.info("alert_resolved", alert_id=alert_id)
        return AlertRead.model_validate(alert)

    # ── Redis helpers ──────────────────────────────────────────────────────────

    async def _cache_get(self, key: str) -> dict | None:
        """Return cached JSON value or None if missing/Redis unavailable."""
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("redis_cache_miss", key=key, error=str(exc))
            return None

    async def _cache_set(self, key: str, value: dict, ttl: int) -> None:
        """Write value to Redis with TTL (best-effort; never raises)."""
        if self._redis is None:
            return
        try:
            await self._redis.setex(key, ttl, json.dumps(value, default=str))
        except Exception as exc:
            logger.debug("redis_cache_write_failed", key=key, error=str(exc))


