"""Farm settings API — runtime-editable thresholds and operational parameters.

Settings are layered:
  1. Defaults from pydantic-settings (env / .env file)
  2. Runtime overrides stored in Redis key ``config:farm_settings``

PATCH merges the incoming fields into the existing override dict so callers
can update one field at a time without losing previous changes.

The Redis override is intentionally ephemeral — it survives container restarts
(Redis persistence is on by default in the Compose stack) but is not the
source of truth for deployment-time config.
"""

from __future__ import annotations

import json

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db.redis import get_redis

logger = structlog.get_logger()
router = APIRouter()

_SETTINGS_KEY = "config:farm_settings"


class FarmSettings(BaseModel):
    """Editable operational thresholds and parameters."""

    ammonia_threshold_ppm: float | None = Field(None, ge=0.0, description="NH₃ warning (ppm)")
    nitrite_threshold_ppm: float | None = Field(None, ge=0.0, description="NO₂ warning (ppm)")
    dissolved_oxygen_min_mgl: float | None = Field(None, ge=0.0, description="Min DO (mg/L)")
    ph_min: float | None = Field(None, ge=0.0, le=14.0)
    ph_max: float | None = Field(None, ge=0.0, le=14.0)
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    sensor_poll_interval: int | None = Field(None, ge=1, description="Sensor interval (s)")


class FarmSettingsResponse(BaseModel):
    """Full effective settings — defaults merged with any Redis override."""

    ammonia_threshold_ppm: float
    nitrite_threshold_ppm: float
    dissolved_oxygen_min_mgl: float
    ph_min: float
    ph_max: float
    temperature_min_c: float
    temperature_max_c: float
    sensor_poll_interval: int


async def _load_override(redis: aioredis.Redis) -> dict:
    """Return the current override dict from Redis (empty dict if not set)."""
    raw = await redis.get(_SETTINGS_KEY)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}


def _effective(override: dict) -> FarmSettingsResponse:
    """Merge Redis override onto config defaults."""
    cfg = get_settings()
    return FarmSettingsResponse(
        ammonia_threshold_ppm=override.get("ammonia_threshold_ppm", cfg.ammonia_threshold_ppm),
        nitrite_threshold_ppm=override.get("nitrite_threshold_ppm", cfg.nitrite_threshold_ppm),
        dissolved_oxygen_min_mgl=override.get(
            "dissolved_oxygen_min_mgl", cfg.dissolved_oxygen_min_mgl
        ),
        ph_min=override.get("ph_min", cfg.ph_min),
        ph_max=override.get("ph_max", cfg.ph_max),
        temperature_min_c=override.get("temperature_min_c", cfg.temperature_min_c),
        temperature_max_c=override.get("temperature_max_c", cfg.temperature_max_c),
        sensor_poll_interval=override.get("sensor_poll_interval", cfg.sensor_poll_interval),
    )


@router.get(
    "",
    response_model=FarmSettingsResponse,
    summary="Get effective farm settings",
)
async def get_farm_settings(
    redis: aioredis.Redis = Depends(get_redis),
) -> FarmSettingsResponse:
    """Return the current effective farm settings.

    Values are the config defaults unless a runtime override has been
    stored via PATCH. Both layers are merged and returned.
    """
    override = await _load_override(redis)
    result = _effective(override)
    logger.info("settings_read", source="redis_override" if override else "config_defaults")
    return result


@router.patch(
    "",
    response_model=FarmSettingsResponse,
    summary="Update farm settings at runtime",
)
async def update_farm_settings(
    patch: FarmSettings,
    redis: aioredis.Redis = Depends(get_redis),
) -> FarmSettingsResponse:
    """Merge patch fields into the current runtime override and persist to Redis.

    Only non-None fields in the request body are applied. To reset a field
    to its environment-variable default, send ``null`` (which requires
    explicitly deleting the Redis key or re-deploying).

    The override has no TTL — it persists until explicitly changed or the
    Redis data is flushed.
    """
    override = await _load_override(redis)

    patch_dict = patch.model_dump(exclude_none=True)
    override.update(patch_dict)

    await redis.set(_SETTINGS_KEY, json.dumps(override))
    logger.info("settings_updated", fields=list(patch_dict.keys()))

    return _effective(override)
