"""Pydantic schemas for alert records."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AlertBase(BaseModel):
    """Shared fields for alert read/write operations."""

    tank_id: str = Field(..., max_length=50)
    severity: Literal["critical", "warning", "info"]
    category: Literal["water_quality", "fish_growth", "feeding", "equipment", "system"]
    title: str = Field(..., max_length=200)
    message: str


class AlertCreate(AlertBase):
    """Schema for creating a new alert (inbound from AI modules or agent)."""

    metric_name: Optional[str] = Field(None, max_length=100)
    metric_value: Optional[str] = Field(None, max_length=50)
    threshold_value: Optional[str] = Field(None, max_length=50)
    source: str = Field(default="system", max_length=50)


class AlertRead(AlertBase):
    """Schema for outbound API responses."""

    id: int
    created_at: datetime
    resolved_at: Optional[datetime] = None
    is_active: bool
    metric_name: Optional[str] = None
    metric_value: Optional[str] = None
    threshold_value: Optional[str] = None
    resolution_notes: Optional[str] = None
    resolved_by: Optional[str] = None
    source: str

    model_config = {"from_attributes": True}


class AlertUpdate(BaseModel):
    """Schema for resolving an alert."""

    resolution_notes: Optional[str] = Field(None, max_length=1000)
    resolved_by: Optional[str] = Field(None, max_length=100)
