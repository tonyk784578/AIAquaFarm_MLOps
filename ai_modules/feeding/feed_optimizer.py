"""Feed amount optimizer — computes optimal feed for next feeding period.

Uses feeding session statistics and historical FCR data to recommend
the feed amount that maximises growth while minimising waste.

TODO (Phase 2): Train RL policy for feed amount optimisation.
TODO (Phase 2): Add ammonia feedback loop from water quality AI.
"""

from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()

# Safety bounds — override with per-tank config in Phase 2
_MIN_FEED_RATIO = 0.5  # Minimum fraction of baseline feed
_MAX_FEED_RATIO = 1.5  # Maximum fraction of baseline feed


@dataclass
class FeedRecommendation:
    """Recommended feed parameters for the next feeding event.

    Attributes:
        amount_kg: Recommended feed amount in kilograms.
        duration_s: Recommended feeding duration in seconds.
        adjustment_ratio: Multiplier applied to baseline amount.
        reasoning: Human-readable explanation.
    """

    amount_kg: float
    duration_s: int
    adjustment_ratio: float
    reasoning: str


class FeedOptimizer:
    """Computes feed recommendations based on activity and growth data.

    Algorithm (Phase 2 target):
        1. Start with baseline feed = biomass_kg * species_feed_rate
        2. Adjust by activity score: high activity → more feed
        3. Adjust by FCR trend: worsening FCR → reduce feed
        4. Clip to [MIN_FEED_RATIO, MAX_FEED_RATIO] * baseline
        5. Detect satiation → early stop signal

    TODO (Phase 2): Replace linear model with trained regression/RL policy.
    """

    def __init__(
        self,
        baseline_feed_rate_pct: float = 2.0,
        activity_weight: float = 0.3,
    ) -> None:
        """Initialize the feed optimizer.

        Args:
            baseline_feed_rate_pct: Daily feed as % of biomass (species default).
            activity_weight: Weight for activity score in adjustment formula.
        """
        self.baseline_feed_rate_pct = baseline_feed_rate_pct
        self.activity_weight = activity_weight

    def compute_recommendation(
        self,
        biomass_kg: float,
        avg_activity_score: float,
        satiation_detected: bool,
        current_fcr: Optional[float] = None,
        water_quality_penalty: float = 0.0,
    ) -> FeedRecommendation:
        """Compute feed recommendation for the next feeding event.

        Args:
            biomass_kg: Current estimated tank biomass in kg.
            avg_activity_score: Average activity score from last session (0–1).
            satiation_detected: Whether satiation was detected last session.
            current_fcr: Most recent feed conversion ratio (lower is better).
            water_quality_penalty: Reduction factor from water quality AI (0–1).

        Returns:
            FeedRecommendation with amount and duration.
        """
        baseline_kg = biomass_kg * self.baseline_feed_rate_pct / 100.0

        # Satiation override — stop feeding
        if satiation_detected:
            return FeedRecommendation(
                amount_kg=0.0,
                duration_s=0,
                adjustment_ratio=0.0,
                reasoning="Satiation detected — skipping next feeding window",
            )

        # Activity-based adjustment: score 0.5 → ratio 1.0, score 1.0 → ratio 1+weight
        activity_ratio = 1.0 + self.activity_weight * (avg_activity_score - 0.5)

        # FCR penalty: if FCR > 1.5 (poor), reduce feed
        fcr_ratio = 1.0
        if current_fcr and current_fcr > 1.5:
            fcr_ratio = max(0.7, 1.0 - (current_fcr - 1.5) * 0.1)

        # Water quality penalty from virtual sensor
        wq_ratio = 1.0 - water_quality_penalty

        total_ratio = activity_ratio * fcr_ratio * wq_ratio
        total_ratio = max(_MIN_FEED_RATIO, min(_MAX_FEED_RATIO, total_ratio))
        recommended_kg = baseline_kg * total_ratio

        return FeedRecommendation(
            amount_kg=round(recommended_kg, 3),
            duration_s=int(recommended_kg * 60 / max(baseline_kg, 0.001)),
            adjustment_ratio=round(total_ratio, 3),
            reasoning=(
                f"Baseline {baseline_kg:.2f} kg × activity {activity_ratio:.2f} "
                f"× FCR {fcr_ratio:.2f} × WQ {wq_ratio:.2f} = {recommended_kg:.2f} kg"
            ),
        )
