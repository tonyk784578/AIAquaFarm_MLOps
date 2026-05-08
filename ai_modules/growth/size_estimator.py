"""Fish size estimation from bounding box detections.

Converts pixel-space bounding boxes to real-world fish length/weight
estimates using camera calibration ratios and allometric equations.

Reference allometric formula: W = a * L^b
  For salmon: a=0.01, b=3.0 (approximate)

TODO (Phase 2): Calibrate per-tank camera using checkerboard calibration tool.
TODO (Phase 2): Train regression model for species-specific length-weight conversion.
"""

from typing import Optional

import structlog

logger = structlog.get_logger()

# Allometric constants — replace with DB-loaded per-species values in Phase 2
_DEFAULT_ALLOMETRIC_A = 0.01
_DEFAULT_ALLOMETRIC_B = 3.0


class SizeEstimator:
    """Converts fish detection bounding boxes to length and weight estimates.

    Attributes:
        pixel_per_cm: Camera calibration ratio (pixels per centimetre).
        allometric_a: Length-weight coefficient a (species-specific).
        allometric_b: Length-weight exponent b (species-specific).
    """

    def __init__(
        self,
        pixel_per_cm: float = 10.0,
        allometric_a: float = _DEFAULT_ALLOMETRIC_A,
        allometric_b: float = _DEFAULT_ALLOMETRIC_B,
    ) -> None:
        self.pixel_per_cm = pixel_per_cm
        self.allometric_a = allometric_a
        self.allometric_b = allometric_b

    def bbox_to_length_cm(self, bbox: list[float]) -> float:
        """Estimate fish length from bounding box diagonal.

        Args:
            bbox: [x1, y1, x2, y2] bounding box in pixel coordinates.

        Returns:
            Estimated fish length in centimetres.

        TODO (Phase 2): Use body-axis keypoints instead of bbox diagonal.
        """
        x1, y1, x2, y2 = bbox
        pixel_length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        return pixel_length / self.pixel_per_cm

    def length_to_weight_g(self, length_cm: float) -> float:
        """Convert fish length to weight using allometric equation W = a * L^b.

        Args:
            length_cm: Estimated fish length in centimetres.

        Returns:
            Estimated weight in grams.
        """
        return self.allometric_a * (length_cm ** self.allometric_b)

    def estimate_biomass_kg(
        self,
        lengths_cm: list[float],
        fish_count: Optional[int] = None,
    ) -> float:
        """Estimate total tank biomass.

        Args:
            lengths_cm: List of individual fish length estimates.
            fish_count: Override total count (if some fish not visible).

        Returns:
            Total estimated biomass in kilograms.
        """
        if not lengths_cm:
            return 0.0
        total_weight_g = sum(self.length_to_weight_g(lc) for lc in lengths_cm)
        detected = len(lengths_cm)
        total = fish_count or detected
        # Scale up if not all fish were detected
        scale = total / detected if detected > 0 else 1.0
        return total_weight_g * scale / 1000.0
