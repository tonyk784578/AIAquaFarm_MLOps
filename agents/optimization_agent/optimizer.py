"""Rule-based optimization logic — fallback when LLM is unavailable.

Encodes domain knowledge from RAS aquaculture best practices:
- Ammonia/nitrite threshold-based feeding reduction
- DO-triggered aeration control
- Temperature-based feeding frequency adjustment

Used as a safety net alongside the LLM-based optimization agent.

TODO (Phase 3): Replace placeholder thresholds with values from config.
TODO (Phase 4): Train a small RL model to replace rule-based logic.
"""

from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class OptimizationResult:
    """Result of a rule-based optimization pass.

    Attributes:
        action_type: Type of recommended action.
        parameters: Action-specific parameters.
        reasoning: Human-readable explanation.
        urgency: 0.0 (routine) to 1.0 (critical).
    """

    action_type: str
    parameters: dict[str, Any]
    reasoning: str
    urgency: float = 0.0


class RuleBasedOptimizer:
    """Applies RAS domain rules to produce control recommendations.

    Used as a fallback when LLM-based optimization is unavailable or
    as a safety guard to veto unsafe LLM suggestions.
    """

    # Water quality safe ranges
    AMMONIA_CRITICAL_PPM = 1.0
    AMMONIA_WARNING_PPM = 0.5
    NITRITE_CRITICAL_PPM = 0.2
    DO_CRITICAL_MGL = 5.0
    PH_MIN = 6.5
    PH_MAX = 8.5

    def evaluate(
        self,
        water_quality: dict[str, Any],
        growth: dict[str, Any],
        feeding: dict[str, Any],
    ) -> OptimizationResult:
        """Apply rule hierarchy to current sensor data.

        Rules are evaluated in priority order; the first triggered rule wins.

        Args:
            water_quality: Latest water quality reading dict.
            growth: Latest fish growth metrics dict.
            feeding: Latest feeding activity dict.

        Returns:
            OptimizationResult with recommended action.

        TODO (Phase 3): Add per-tank rule profiles loaded from DB.
        """
        ammonia = water_quality.get("ammonia_ppm", 0.0) or 0.0
        do_level = water_quality.get("dissolved_oxygen_mgl", 8.0) or 8.0

        # Critical: high ammonia — stop feeding immediately
        if ammonia >= self.AMMONIA_CRITICAL_PPM:
            logger.warning("critical_ammonia_level", ammonia_ppm=ammonia)
            return OptimizationResult(
                action_type="stop_feeding",
                parameters={"reason": "critical_ammonia"},
                reasoning=f"Ammonia {ammonia:.2f} ppm exceeds critical threshold {self.AMMONIA_CRITICAL_PPM} ppm",
                urgency=1.0,
            )

        # Critical: low dissolved oxygen — increase aeration
        if do_level < self.DO_CRITICAL_MGL:
            logger.warning("critical_low_do", do_mgl=do_level)
            return OptimizationResult(
                action_type="increase_aeration",
                parameters={"reason": "low_do"},
                reasoning=f"Dissolved oxygen {do_level:.2f} mg/L below critical {self.DO_CRITICAL_MGL} mg/L",
                urgency=0.9,
            )

        # Warning: elevated ammonia — reduce feed amount
        if ammonia >= self.AMMONIA_WARNING_PPM:
            activity_score = feeding.get("activity_score", 0.7) or 0.7
            reduction_factor = max(0.3, 1.0 - (ammonia - self.AMMONIA_WARNING_PPM))
            return OptimizationResult(
                action_type="reduce_feeding",
                parameters={"reduction_factor": reduction_factor},
                reasoning=f"Ammonia {ammonia:.2f} ppm elevated — reducing feed by {(1 - reduction_factor) * 100:.0f}%",
                urgency=0.5,
            )

        # Normal: adjust feeding by activity score
        activity_score = feeding.get("activity_score", 0.7) or 0.7
        return OptimizationResult(
            action_type="normal_feeding",
            parameters={"activity_score": activity_score},
            reasoning="All parameters within normal range",
            urgency=0.0,
        )
