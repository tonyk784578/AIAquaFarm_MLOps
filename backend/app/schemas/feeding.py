"""Pydantic schemas for feeding records and control commands."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FeedingBase(BaseModel):
    """Shared fields for feeding records."""

    tank_id: str = Field(..., max_length=50)
    commanded_amount_kg: float | None = Field(None, ge=0.0, le=100.0)


class FeedingCreate(FeedingBase):
    """Schema for creating a new feeding record."""

    started_at: datetime
    trigger_source: Literal["ai", "manual", "schedule"] = "ai"
    recommended_amount_kg: float | None = Field(None, ge=0.0)
    activity_score: float | None = Field(None, ge=0.0, le=1.0)
    model_version: str | None = None


class FeedingRead(FeedingBase):
    """Schema for outbound API responses."""

    id: int
    started_at: datetime
    ended_at: datetime | None = None
    actual_amount_kg: float | None = None
    duration_seconds: int | None = None
    activity_score: float | None = None
    recommended_amount_kg: float | None = None
    feed_waste_estimate_pct: float | None = None
    trigger_source: str
    is_completed: bool
    is_emergency_stopped: bool

    model_config = {"from_attributes": True}


class FeedingCommand(BaseModel):
    """Control command to trigger a feeding event."""

    tank_id: str = Field(..., max_length=50)
    amount_kg: float = Field(..., gt=0.0, le=50.0, description="Feed amount in kg")
    duration_seconds: int = Field(
        default=60, ge=5, le=600, description="Maximum feeding duration in seconds"
    )
    notes: str | None = Field(None, max_length=500)
