"""Feeding activity analyser — processes video frames over a feeding window.

Aggregates per-frame activity scores into session-level statistics
used by the feed optimizer to adjust next-period feed amounts.

TODO (Phase 2): Add temporal smoothing (rolling average over 30 s window).
TODO (Phase 2): Implement satiation detection (activity drop > 30% in 60 s).
"""

from dataclasses import dataclass, field
from typing import Optional

import structlog

from ai_modules.feeding.model import FeedingActivityModel

logger = structlog.get_logger()


@dataclass
class FeedingSession:
    """Accumulated statistics for a single feeding event.

    Attributes:
        tank_id:            Tank being analysed.
        activity_scores:    Per-frame activity score list.
        peak_activity:      Maximum observed activity score.
        satiation_detected: True if activity dropped significantly.
        frame_count:        Total frames processed.
    """

    tank_id: str
    activity_scores: list[float] = field(default_factory=list)
    peak_activity: float = 0.0
    satiation_detected: bool = False
    frame_count: int = 0


class ActivityAnalyzer:
    """Analyses feeding activity across a video feeding window.

    Attributes:
        model: Loaded FeedingActivityModel for per-frame inference.
        satiation_drop_threshold: Activity drop ratio to trigger satiation flag.
        satiation_window: Number of frames to check for activity trend.
    """

    def __init__(
        self,
        model: Optional[FeedingActivityModel] = None,
        satiation_drop_threshold: float = 0.3,
        satiation_window: int = 30,
    ) -> None:
        self.model = model or FeedingActivityModel()
        self.satiation_drop_threshold = satiation_drop_threshold
        self.satiation_window = satiation_window

    def process_frame(self, session: FeedingSession, frame: bytes) -> float:
        """Process a single frame and update session statistics.

        Args:
            session: Current feeding session accumulator.
            frame: Raw frame bytes.

        Returns:
            Activity score for this frame.

        TODO (Phase 2): Decode bytes → numpy before passing to model.
        """
        predictions = self.model.predict(frame)
        score = predictions[0]["activity_score"] if predictions else 0.5

        session.activity_scores.append(score)
        session.frame_count += 1
        session.peak_activity = max(session.peak_activity, score)
        session.satiation_detected = self._check_satiation(session)

        return score

    def _check_satiation(self, session: FeedingSession) -> bool:
        """Detect if fish activity has dropped (satiation signal).

        Args:
            session: Current feeding session.

        Returns:
            True if satiation is detected.
        """
        scores = session.activity_scores
        if len(scores) < self.satiation_window * 2:
            return False
        recent = scores[-self.satiation_window:]
        earlier = scores[-self.satiation_window * 2 : -self.satiation_window]
        recent_avg = sum(recent) / len(recent)
        earlier_avg = sum(earlier) / len(earlier)
        if earlier_avg > 0:
            drop_ratio = (earlier_avg - recent_avg) / earlier_avg
            return drop_ratio >= self.satiation_drop_threshold
        return False

    def get_session_summary(self, session: FeedingSession) -> dict:
        """Compute final summary statistics for a completed feeding session.

        Args:
            session: Completed feeding session.

        Returns:
            Dict with avg_activity, peak_activity, satiation_detected.
        """
        scores = session.activity_scores
        avg = sum(scores) / len(scores) if scores else 0.0
        return {
            "tank_id": session.tank_id,
            "avg_activity_score": round(avg, 3),
            "peak_activity_score": round(session.peak_activity, 3),
            "satiation_detected": session.satiation_detected,
            "frames_analyzed": session.frame_count,
        }
