"""Model evaluation and promotion gate for all AIAquafarm AI modules.

Each model has a quality gate — minimum metric thresholds that must be met
before a candidate run can be promoted to the Production stage in the MLflow
model registry.

Gates
-----
FishDetection            → mAP50 ≥ 0.65, mAP50_95 ≥ 0.40
FeedingActivityClassifier → val_mae ≤ 0.12, val_mse ≤ 0.03
WaterQualityPredictor    → val_loss ≤ 0.01, test_loss ≤ 0.015

Promotion flow
--------------
    1. Fetch metrics logged for a completed MLflow run.
    2. Compare against the registered gate for that model.
    3. If the candidate beats the gate AND beats the current production
       model's metrics, promote it; otherwise archive the run.

Usage::

    from mlops.evaluation.evaluator import ModelEvaluator
    evaluator = ModelEvaluator(mlflow_uri="http://localhost:5000")
    promoted = evaluator.evaluate_and_maybe_promote("FeedingActivityClassifier", run_id="abc123")
"""

from __future__ import annotations

import dataclasses
from typing import Any

import mlflow
import structlog
from mlflow.tracking import MlflowClient

logger = structlog.get_logger()

# ── Quality gates ──────────────────────────────────────────────────────────────

@dataclasses.dataclass
class QualityGate:
    """Metric thresholds a model run must pass to be promotion-eligible.

    Attributes:
        metrics: Dict mapping metric name → (threshold, direction).
                 direction is 'min' (lower-is-better) or 'max' (higher-is-better).
    """
    metrics: dict[str, tuple[float, str]]

    def check(self, run_metrics: dict[str, float]) -> tuple[bool, dict[str, bool]]:
        """Evaluate run_metrics against gate thresholds.

        Args:
            run_metrics: Dict of metric name → value from an MLflow run.

        Returns:
            Tuple of (all_passed, per_metric_result_dict).
        """
        results: dict[str, bool] = {}
        for metric, (threshold, direction) in self.metrics.items():
            value = run_metrics.get(metric)
            if value is None:
                results[metric] = False
                continue
            if direction == "min":
                results[metric] = value <= threshold
            else:
                results[metric] = value >= threshold
        return all(results.values()), results


QUALITY_GATES: dict[str, QualityGate] = {
    "FishDetection": QualityGate(metrics={
        "mAP50":    (0.65, "max"),
        "mAP50_95": (0.40, "max"),
        "precision": (0.60, "max"),
        "recall":    (0.60, "max"),
    }),
    "FeedingActivityClassifier": QualityGate(metrics={
        "val_mae": (0.12, "min"),
        "val_mse": (0.03, "min"),
        "best_val_mae": (0.12, "min"),
    }),
    "WaterQualityPredictor": QualityGate(metrics={
        "val_loss":  (0.01,  "min"),
        "test_loss": (0.015, "min"),
    }),
}


# ── Evaluator ──────────────────────────────────────────────────────────────────

class ModelEvaluator:
    """Evaluates MLflow runs against quality gates and promotes passing models.

    Attributes:
        tracking_uri: MLflow tracking server URI.
        client: MLflow tracking client.
    """

    def __init__(self, tracking_uri: str = "http://localhost:5000") -> None:
        self.tracking_uri = tracking_uri
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient(tracking_uri=tracking_uri)

    def get_run_metrics(self, run_id: str) -> dict[str, float]:
        """Fetch all metrics logged for a completed MLflow run.

        Args:
            run_id: MLflow run ID.

        Returns:
            Dict of metric name → last logged value.
        """
        run = self.client.get_run(run_id)
        return dict(run.data.metrics)

    def get_production_metrics(self, model_name: str) -> dict[str, float] | None:
        """Fetch metrics of the currently promoted Production model version.

        Args:
            model_name: Registered model name.

        Returns:
            Metric dict, or None if no Production version exists.
        """
        try:
            versions = self.client.get_latest_versions(model_name, stages=["Production"])
            if not versions:
                return None
            prod_run_id = versions[0].run_id
            return self.get_run_metrics(prod_run_id)
        except Exception as exc:
            logger.warning("production_metrics_fetch_failed", model=model_name, error=str(exc))
            return None

    def _is_better_than_production(
        self,
        model_name: str,
        candidate_metrics: dict[str, float],
        prod_metrics: dict[str, float],
    ) -> bool:
        """Return True if candidate improves on the production model's primary metric.

        Primary metric per model:
            FishDetection            → mAP50_95 (max)
            FeedingActivityClassifier → val_mae  (min)
            WaterQualityPredictor    → val_loss  (min)
        """
        primary: dict[str, tuple[str, str]] = {
            "FishDetection":             ("mAP50_95", "max"),
            "FeedingActivityClassifier": ("best_val_mae", "min"),
            "WaterQualityPredictor":     ("val_loss", "min"),
        }
        metric_name, direction = primary.get(model_name, ("val_loss", "min"))

        cand_val = candidate_metrics.get(metric_name)
        prod_val = prod_metrics.get(metric_name)

        if cand_val is None:
            return False
        if prod_val is None:
            return True  # no incumbent → promote by default

        if direction == "min":
            return cand_val < prod_val
        return cand_val > prod_val

    def evaluate_and_maybe_promote(
        self,
        model_name: str,
        run_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """Evaluate a training run and promote to Production if it passes.

        Args:
            model_name: Registered model name (must be in QUALITY_GATES).
            run_id: MLflow run ID to evaluate.
            force: Skip the "better-than-production" check; promote if gate passes.

        Returns:
            Dict with keys:
                promoted (bool), gate_passed (bool), better_than_prod (bool),
                gate_results (dict), candidate_metrics (dict), message (str).
        """
        gate = QUALITY_GATES.get(model_name)
        if gate is None:
            return {
                "promoted": False,
                "gate_passed": False,
                "better_than_prod": False,
                "gate_results": {},
                "candidate_metrics": {},
                "message": f"No quality gate defined for model '{model_name}'",
            }

        candidate_metrics = self.get_run_metrics(run_id)
        gate_passed, gate_results = gate.check(candidate_metrics)

        logger.info(
            "gate_evaluation",
            model=model_name,
            run_id=run_id,
            gate_passed=gate_passed,
            results=gate_results,
        )

        if not gate_passed:
            return {
                "promoted": False,
                "gate_passed": False,
                "better_than_prod": False,
                "gate_results": gate_results,
                "candidate_metrics": candidate_metrics,
                "message": "Quality gate not met — model not promoted",
            }

        prod_metrics = self.get_production_metrics(model_name)
        better = force or self._is_better_than_production(
            model_name, candidate_metrics, prod_metrics or {}
        )

        if not better:
            return {
                "promoted": False,
                "gate_passed": True,
                "better_than_prod": False,
                "gate_results": gate_results,
                "candidate_metrics": candidate_metrics,
                "message": "Gate passed but does not improve on current Production model",
            }

        # Find the model version corresponding to this run
        versions = self.client.search_model_versions(f"name='{model_name}'")
        run_versions = [v for v in versions if v.run_id == run_id]
        if not run_versions:
            return {
                "promoted": False,
                "gate_passed": True,
                "better_than_prod": True,
                "gate_results": gate_results,
                "candidate_metrics": candidate_metrics,
                "message": f"Run {run_id} has not been registered as a model version",
            }

        version = int(run_versions[0].version)
        self.client.transition_model_version_stage(
            name=model_name,
            version=str(version),
            stage="Production",
            archive_existing_versions=True,
        )
        logger.info(
            "model_promoted",
            model=model_name,
            version=version,
            run_id=run_id,
        )

        return {
            "promoted": True,
            "gate_passed": True,
            "better_than_prod": True,
            "gate_results": gate_results,
            "candidate_metrics": candidate_metrics,
            "version": version,
            "message": f"Promoted {model_name} v{version} to Production",
        }

    def report_all_production_models(self) -> list[dict[str, Any]]:
        """Return a summary of all registered models' Production versions.

        Returns:
            List of dicts with model name, version, run_id, and key metrics.
        """
        summary = []
        for model_name in QUALITY_GATES:
            try:
                versions = self.client.get_latest_versions(model_name, stages=["Production"])
                if not versions:
                    summary.append({"model": model_name, "status": "no_production_version"})
                    continue
                v = versions[0]
                metrics = self.get_run_metrics(v.run_id)
                summary.append({
                    "model": model_name,
                    "version": v.version,
                    "run_id": v.run_id,
                    "metrics": metrics,
                    "status": "production",
                })
            except Exception as exc:
                summary.append({"model": model_name, "status": "error", "error": str(exc)})
        return summary
