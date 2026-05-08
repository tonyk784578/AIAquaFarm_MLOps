"""Pydantic schemas for fish growth measurement records."""

from datetime import datetime

from pydantic import BaseModel, Field


class FishGrowthBase(BaseModel):
    """Shared fields for fish growth read/write operations."""

    tank_id: str = Field(..., max_length=50)
    avg_length_cm: float | None = Field(None, ge=0.0)
    avg_weight_g: float | None = Field(None, ge=0.0)
    fish_count: int | None = Field(None, ge=0)
    biomass_kg: float | None = Field(None, ge=0.0)


class FishGrowthCreate(FishGrowthBase):
    """Schema for creating a new growth record (inbound from growth AI module)."""

    measured_at: datetime
    daily_growth_rate_pct: float | None = None
    feed_conversion_ratio: float | None = Field(None, ge=0.0)
    model_version: str | None = None
    inference_confidence: float | None = Field(None, ge=0.0, le=1.0)
    frame_count_analyzed: int | None = Field(None, ge=0)


class FishGrowthRead(FishGrowthBase):
    """Schema for outbound API responses."""

    id: int
    measured_at: datetime
    daily_growth_rate_pct: float | None = None
    feed_conversion_ratio: float | None = None
    model_version: str | None = None
    inference_confidence: float | None = None
    frame_count_analyzed: int | None = None

    model_config = {"from_attributes": True}
