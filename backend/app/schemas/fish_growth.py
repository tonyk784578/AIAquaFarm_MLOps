"""Pydantic schemas for fish growth measurement records."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FishGrowthBase(BaseModel):
    """Shared fields for fish growth read/write operations."""

    tank_id: str = Field(..., max_length=50)
    avg_length_cm: Optional[float] = Field(None, ge=0.0)
    avg_weight_g: Optional[float] = Field(None, ge=0.0)
    fish_count: Optional[int] = Field(None, ge=0)
    biomass_kg: Optional[float] = Field(None, ge=0.0)


class FishGrowthCreate(FishGrowthBase):
    """Schema for creating a new growth record (inbound from growth AI module)."""

    measured_at: datetime
    daily_growth_rate_pct: Optional[float] = None
    feed_conversion_ratio: Optional[float] = Field(None, ge=0.0)
    model_version: Optional[str] = None
    inference_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    frame_count_analyzed: Optional[int] = Field(None, ge=0)


class FishGrowthRead(FishGrowthBase):
    """Schema for outbound API responses."""

    id: int
    measured_at: datetime
    daily_growth_rate_pct: Optional[float] = None
    feed_conversion_ratio: Optional[float] = None
    model_version: Optional[str] = None
    inference_confidence: Optional[float] = None
    frame_count_analyzed: Optional[int] = None

    model_config = {"from_attributes": True}
