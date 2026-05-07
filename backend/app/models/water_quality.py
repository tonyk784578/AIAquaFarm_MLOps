"""SQLAlchemy ORM model for water quality time-series data.

This table is converted to a TimescaleDB hypertable in init.sql,
partitioned by `measured_at` for efficient time-range queries.

Columns map directly to the physical and virtual sensor outputs:
  - Physical: temperature, pH, dissolved_oxygen, turbidity
  - Virtual (AI-predicted): ammonia_ppm, nitrite_ppm
"""

from datetime import datetime

from sqlalchemy import Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class WaterQualityReading(Base):
    """Water quality measurement from physical sensors and virtual sensor AI."""

    __tablename__ = "water_quality_readings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tank_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    measured_at: Mapped[datetime] = mapped_column(nullable=False, index=True)

    # Physical sensor readings
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    ph: Mapped[float | None] = mapped_column(Float, nullable=True)
    dissolved_oxygen_mgl: Mapped[float | None] = mapped_column(Float, nullable=True)
    turbidity_ntu: Mapped[float | None] = mapped_column(Float, nullable=True)
    salinity_ppt: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Virtual sensor predictions (from water quality AI module)
    ammonia_ppm: Mapped[float | None] = mapped_column(Float, nullable=True)
    nitrite_ppm: Mapped[float | None] = mapped_column(Float, nullable=True)
    nitrate_ppm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Prediction confidence (0.0–1.0)
    ammonia_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    nitrite_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Source tag: 'sensor' | 'virtual_sensor' | 'manual'
    source: Mapped[str] = mapped_column(String(20), default="sensor")

    __table_args__ = (
        Index("ix_wq_tank_time", "tank_id", "measured_at"),
        # TODO (Phase 1): TimescaleDB hypertable is created in init.sql, not here.
    )
