"""Pydantic schemas for feeding AI module inputs and outputs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FeedingAnalysisInput(BaseModel):
    """Input frame for feeding activity analysis."""

    tank_id: str
    frame_bytes: bytes
    timestamp: datetime
    current_feed_amount_kg: float = Field(..., ge=0.0)
    feeding_duration_s: int = Field(..., ge=0)


class FeedingActivityOutput(BaseModel):
    """Output of feeding activity analysis for a single frame."""

    tank_id: str
    timestamp: datetime
    activity_score: float = Field(..., ge=0.0, le=1.0, description="0=no activity, 1=max activity")
    surface_disturbance_score: float = Field(..., ge=0.0, le=1.0)
    visible_pellet_count: Optional[int] = None
    waste_estimate_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    model_version: str = "unknown"


class FeedOptimizationOutput(BaseModel):
    """Recommended feeding parameters for the next feeding event."""

    tank_id: str
    recommended_amount_kg: float = Field(..., ge=0.0)
    recommended_duration_s: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    estimated_fcr_improvement: Optional[float] = None
