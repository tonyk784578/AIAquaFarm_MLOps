"""SQLAlchemy ORM model for fish growth measurement records.

Records are produced by the growth AI module (vision-based size estimation).
Each record represents one inference pass on a camera frame.

TODO (Phase 2): Add FK to a `Fish` or `Batch` table once batch management is built.
"""

from datetime import datetime

from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FishGrowthRecord(Base):
    """Fish size measurement derived from camera frame analysis."""

    __tablename__ = "fish_growth_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tank_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    measured_at: Mapped[datetime] = mapped_column(nullable=False, index=True)

    # Vision AI estimates
    avg_length_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fish_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    biomass_kg: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Growth rate since last measurement
    daily_growth_rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    feed_conversion_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Model metadata
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    inference_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    frame_count_analyzed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (Index("ix_fg_tank_time", "tank_id", "measured_at"),)
