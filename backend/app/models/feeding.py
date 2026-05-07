"""SQLAlchemy ORM model for feeding events and AI-optimised feed commands.

Records both automatic (AI-driven) and manual feeding events.
The feeding AI module writes the `activity_score` and `recommended_amount_kg`
after analysing camera footage of fish feeding behaviour.

TODO (Phase 2): Add FK to equipment table for feeder device tracking.
"""

from datetime import datetime

from sqlalchemy import Boolean, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FeedingRecord(Base):
    """Record of a single feeding event — planned, executed, or cancelled."""

    __tablename__ = "feeding_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tank_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Commanded vs actual amounts
    commanded_amount_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_amount_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Feeding AI outputs
    activity_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="0.0–1.0 feeding activity from vision AI"
    )
    recommended_amount_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    feed_waste_estimate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Status
    trigger_source: Mapped[str] = mapped_column(
        String(20), default="ai", comment="'ai' | 'manual' | 'schedule'"
    )
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_emergency_stopped: Mapped[bool] = mapped_column(Boolean, default=False)

    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (Index("ix_feed_tank_time", "tank_id", "started_at"),)
