"""ORM models package.

All models inherit from app.db.session.Base and are registered
automatically when this package is imported during DB initialisation.
"""

from app.models.alert import Alert
from app.models.feeding import FeedingRecord
from app.models.fish_growth import FishGrowthRecord
from app.models.water_quality import WaterQualityReading

__all__ = ["Alert", "FeedingRecord", "FishGrowthRecord", "WaterQualityReading"]
