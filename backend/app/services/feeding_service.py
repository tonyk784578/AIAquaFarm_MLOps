"""Feeding activity inference service.

Provides:
    FeedingInferenceEngine  — singleton; holds FeedingActivityModel + optimizer.
    FeedingService          — per-request service; runs frame inference and
                              computes feed recommendations.
"""

from __future__ import annotations

import structlog
from ai_modules.feeding.activity_analyzer import ActivityAnalyzer, FeedingSession
from ai_modules.feeding.feed_optimizer import FeedOptimizer, FeedRecommendation
from ai_modules.feeding.model import FeedingActivityModel
from ai_modules.feeding.schemas import (
    FeedingActivityOutput,
    FeedingAnalysisInput,
    FeedOptimizationOutput,
)

logger = structlog.get_logger()


class FeedingInferenceEngine:
    """Application-scoped singleton holding feeding AI components.

    Attributes:
        model: FeedingActivityModel (ResNet18 regression wrapper).
        analyzer: ActivityAnalyzer aggregating per-frame scores.
        optimizer: FeedOptimizer computing next-feed recommendations.
        sessions: Per-tank active FeedingSession accumulators.
        is_ready: True once model weights are loaded.
    """

    def __init__(self) -> None:
        self.model = FeedingActivityModel()
        self.analyzer = ActivityAnalyzer(model=self.model)
        self.optimizer = FeedOptimizer()
        self.sessions: dict[str, FeedingSession] = {}
        self.is_ready: bool = False
        self._model_path: str = ""

    @classmethod
    def from_checkpoint(cls, model_path: str) -> FeedingInferenceEngine:
        """Load from a local .pt checkpoint.

        Args:
            model_path: Path to feeding model checkpoint.

        Returns:
            Initialised engine; degrades gracefully if load fails.
        """
        engine = cls()
        engine._model_path = model_path
        engine.model.load(model_path)
        engine.analyzer = ActivityAnalyzer(model=engine.model)
        engine.is_ready = engine.model.is_loaded
        if engine.is_ready:
            logger.info("feeding_engine_ready", path=model_path)
        else:
            logger.warning("feeding_engine_degraded", path=model_path)
        return engine

    @classmethod
    def from_mlflow(
        cls,
        tracking_uri: str,
        model_name: str = "FeedingActivityClassifier",
        stage: str = "Production",
    ) -> FeedingInferenceEngine:
        """Load from the MLflow model registry.

        Args:
            tracking_uri: MLflow server URL.
            model_name: Registered model name.
            stage: Model stage ('Production', 'Staging').

        Returns:
            Initialised engine; degrades gracefully if MLflow unreachable.
        """
        engine = cls()
        uri = f"models:/{model_name}/{stage}"
        engine._model_path = f"{tracking_uri} | {uri}"
        try:
            import mlflow
            mlflow.set_tracking_uri(tracking_uri)
            engine.model.load(uri)
            engine.analyzer = ActivityAnalyzer(model=engine.model)
            engine.is_ready = engine.model.is_loaded
            logger.info("feeding_engine_ready_from_mlflow", uri=uri)
        except Exception as exc:
            logger.warning("feeding_engine_mlflow_unavailable", error=str(exc))
        return engine

    def get_or_create_session(self, tank_id: str) -> FeedingSession:
        if tank_id not in self.sessions:
            self.sessions[tank_id] = FeedingSession(tank_id=tank_id)
        return self.sessions[tank_id]

    def reset_session(self, tank_id: str) -> None:
        """Start a fresh session for the given tank (call between feeding periods)."""
        self.sessions[tank_id] = FeedingSession(tank_id=tank_id)

    def status(self) -> dict:
        return {
            "model_name": "FeedingActivityClassifier",
            "is_loaded": self.is_ready,
            "model_version": self.model.get_version(),
            "model_path": self._model_path,
            "device": "cpu",
            "active_sessions": list(self.sessions.keys()),
        }


class FeedingService:
    """Per-request service for feeding activity analysis and feed optimization."""

    def __init__(self, engine: FeedingInferenceEngine) -> None:
        self.engine = engine

    def analyse_frame(self, inp: FeedingAnalysisInput) -> FeedingActivityOutput:
        """Process a single camera frame and update the tank's feeding session.

        Args:
            inp: FeedingAnalysisInput with frame bytes and session metadata.

        Returns:
            FeedingActivityOutput with activity score and session stats.
        """
        session = self.engine.get_or_create_session(inp.tank_id)
        score = self.engine.analyzer.process_frame(session, inp.frame_bytes)
        summary = self.engine.analyzer.get_session_summary(session)

        logger.info(
            "feeding_frame_analysed",
            tank_id=inp.tank_id,
            activity_score=round(score, 3),
            frames=summary["frames_analyzed"],
            satiation=summary["satiation_detected"],
        )

        return FeedingActivityOutput(
            tank_id=inp.tank_id,
            timestamp=inp.timestamp,
            activity_score=round(score, 4),
            surface_disturbance_score=round(score, 4),  # proxy until dedicated model
            model_version=self.engine.model.get_version(),
        )

    def get_recommendation(
        self,
        tank_id: str,
        biomass_kg: float,
        current_fcr: float | None = None,
        water_quality_penalty: float = 0.0,
    ) -> FeedOptimizationOutput:
        """Compute the next feed recommendation from session statistics.

        Args:
            tank_id: Tank identifier.
            biomass_kg: Current estimated biomass.
            current_fcr: Most recent feed conversion ratio.
            water_quality_penalty: Penalty from water quality AI (0–1).

        Returns:
            FeedOptimizationOutput with recommended amount and reasoning.
        """
        session = self.engine.get_or_create_session(tank_id)
        summary = self.engine.analyzer.get_session_summary(session)

        rec: FeedRecommendation = self.engine.optimizer.compute_recommendation(
            biomass_kg=biomass_kg,
            avg_activity_score=summary["avg_activity_score"],
            satiation_detected=summary["satiation_detected"],
            current_fcr=current_fcr,
            water_quality_penalty=water_quality_penalty,
        )

        logger.info(
            "feed_recommendation_computed",
            tank_id=tank_id,
            amount_kg=rec.amount_kg,
            ratio=rec.adjustment_ratio,
        )

        return FeedOptimizationOutput(
            tank_id=tank_id,
            recommended_amount_kg=rec.amount_kg,
            recommended_duration_s=rec.duration_s,
            confidence=1.0 if self.engine.is_ready else 0.5,
            reasoning=rec.reasoning,
        )
