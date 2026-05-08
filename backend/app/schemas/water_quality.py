"""Pydantic schemas for water quality readings."""

from datetime import datetime

from pydantic import BaseModel, Field


class WaterQualityBase(BaseModel):
    """Shared fields for water quality read/write operations."""

    tank_id: str = Field(..., max_length=50)
    temperature_c: float | None = Field(None, ge=-5.0, le=50.0)
    ph: float | None = Field(None, ge=0.0, le=14.0)
    dissolved_oxygen_mgl: float | None = Field(None, ge=0.0, le=30.0)
    turbidity_ntu: float | None = Field(None, ge=0.0)
    salinity_ppt: float | None = Field(None, ge=0.0, le=50.0)
    ammonia_ppm: float | None = Field(None, ge=0.0)
    nitrite_ppm: float | None = Field(None, ge=0.0)
    nitrate_ppm: float | None = Field(None, ge=0.0)


class WaterQualityCreate(WaterQualityBase):
    """Schema for creating a new reading (inbound from sensor collector)."""

    measured_at: datetime
    source: str = Field(default="sensor", pattern="^(sensor|virtual_sensor|manual)$")
    ammonia_confidence: float | None = Field(None, ge=0.0, le=1.0)
    nitrite_confidence: float | None = Field(None, ge=0.0, le=1.0)


class WaterQualityRead(WaterQualityBase):
    """Schema for outbound API responses."""

    id: int
    measured_at: datetime
    source: str
    ammonia_confidence: float | None = None
    nitrite_confidence: float | None = None

    model_config = {"from_attributes": True}
