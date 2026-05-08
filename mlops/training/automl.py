"""AutoML automation layer — orchestrates training pipeline runs.

Monitors the data lake for new labelled samples, triggers re-training when
new-data thresholds are met, and promotes models that pass the quality gate.
Also runs PSI-based drift detection and triggers emergency retraining even
before sample-count thresholds are reached when max_psi ≥ 0.20.

Retraining thresholds
---------------------
    FishDetection            → 500 new labelled images
    FeedingActivityClassifier → 300 new labelled images
    WaterQualityPredictor    → 1 000 new sensor rows

Drift thresholds (PSI)
----------------------
    PSI < 0.10  → stable, no action
    PSI < 0.20  → warning, log only
    PSI ≥ 0.20  → emergency retraining triggered

Pipeline per model
------------------
    1. Count new samples in data lake since last run.
    2. Run drift detection if reference/current CSVs are provided.
    3. If count ≥ threshold OR drift PSI ≥ 0.20: run training, capture run_id.
    4. Pass run_id to ModelEvaluator.evaluate_and_maybe_promote().
    5. Record result in AutoML run log (MLflow parent run).

Usage (programmatic)::

    from mlops.training.automl import AutoMLPipeline
    from mlops.data_lake.storage import DataLakeStorage

    lake = DataLakeStorage(bucket="aquafarm-datalake", endpoint_url="http://minio:9000")
    pipeline = AutoMLPipeline(mlflow_uri="http://mlflow:5000", data_lake=lake)
    results = pipeline.check_and_retrain(
        water_data_path="/data/wq_train.csv",
        wq_reference_csv="/data/wq_train.csv",
        wq_current_csv="/data/wq_live.csv",
    )

Usage (CLI)::

    python -m mlops.training.automl \\
        --mlflow-uri http://localhost:5000 \\
        --data-dir /data \\
        --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from mlops.evaluation.drift_detector import DriftDetector
from mlops.evaluation.evaluator import ModelEvaluator

logger = structlog.get_logger()

# ── Retraining thresholds ──────────────────────────────────────────────────────
MIN_NEW_SAMPLES_GROWTH = 500
MIN_NEW_SAMPLES_FEEDING = 300
MIN_NEW_SAMPLES_WATER = 1000

# ── Default training hyper-parameters ─────────────────────────────────────────
_DEFAULT_WATER_ARGS: dict[str, Any] = {
    "arch": "lstm",
    "epochs": 100,
    "lr": 3e-4,
    "hidden_size": 128,
    "batch_size": 64,
    "patience": 10,
}

_DEFAULT_FEEDING_ARGS: dict[str, Any] = {
    "epochs": 30,
    "lr": 1e-4,
    "batch_size": 32,
    "patience": 7,
}

_DEFAULT_GROWTH_ARGS: dict[str, Any] = {
    "base_model": "yolov8n.pt",
    "epochs": 100,
    "imgsz": 640,
    "batch": 16,
    "patience": 20,
}


# ── RetrainingResult ───────────────────────────────────────────────────────────

@dataclass
class RetrainingResult:
    """Outcome of a single model's AutoML check-and-retrain cycle.

    Attributes:
        model: Registered model name.
        new_samples: Number of new samples detected.
        threshold: Minimum new samples required to trigger retraining.
        triggered: Whether a training run was launched.
        drift_triggered: Whether retraining was triggered by drift (PSI ≥ 0.20)
            rather than sample count.
        drift_report: DriftReport.to_dict() output when drift was checked.
        run_id: MLflow run ID (only set when triggered=True).
        promoted: Whether the trained model was promoted to Production.
        gate_results: Per-metric pass/fail from the quality gate.
        error: Error message if the pipeline failed.
    """
    model: str
    new_samples: int
    threshold: int
    triggered: bool = False
    drift_triggered: bool = False
    drift_report: dict[str, Any] | None = None
    run_id: str | None = None
    promoted: bool = False
    gate_results: dict[str, bool] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "new_samples": self.new_samples,
            "threshold": self.threshold,
            "triggered": self.triggered,
            "drift_triggered": self.drift_triggered,
            "drift_report": self.drift_report,
            "run_id": self.run_id,
            "promoted": self.promoted,
            "gate_results": self.gate_results,
            "error": self.error,
        }


# ── AutoMLPipeline ─────────────────────────────────────────────────────────────

class AutoMLPipeline:
    """Monitors data lake and triggers model retraining automatically.

    Attributes:
        mlflow_uri: MLflow tracking server URI.
        data_lake: DataLakeStorage instance (may be None for dry-run).
        evaluator: ModelEvaluator for post-training quality gating.
        device: PyTorch device string ('cpu', 'cuda').
        output_dir: Local directory for checkpoint artefacts.
    """

    def __init__(
        self,
        mlflow_uri: str,
        data_lake: object | None = None,
        device: str = "cpu",
        output_dir: str = ".",
    ) -> None:
        self.mlflow_uri = mlflow_uri
        self.data_lake = data_lake
        self.device = device
        self.output_dir = Path(output_dir)
        self.evaluator = ModelEvaluator(tracking_uri=mlflow_uri)

    # ── Sample counting ────────────────────────────────────────────────────────

    def _count_new_samples(self, model_name: str) -> int:
        """Count new labelled samples in the data lake for a given model.

        Checks the S3 prefix corresponding to each model type:
            FishDetection            → raw/labelled/growth/
            FeedingActivityClassifier → raw/labelled/feeding/
            WaterQualityPredictor    → raw/sensor/

        Returns 0 if data_lake is None (dry-run mode).
        """
        if self.data_lake is None:
            logger.warning("data_lake_not_configured", model=model_name, returning=0)
            return 0

        prefix_map = {
            "FishDetection":             "raw/labelled/growth/",
            "FeedingActivityClassifier": "raw/labelled/feeding/",
            "WaterQualityPredictor":     "raw/sensor/",
        }
        prefix = prefix_map.get(model_name, "")
        try:
            keys = self.data_lake.list_objects(prefix)  # type: ignore[attr-defined]
            logger.info("sample_count", model=model_name, prefix=prefix, count=len(keys))
            return len(keys)
        except Exception as exc:
            logger.error("sample_count_failed", model=model_name, error=str(exc))
            return 0

    # ── Training dispatch ──────────────────────────────────────────────────────

    def _run_training_subprocess(
        self,
        module: str,
        extra_args: list[str],
        data_path: str,
    ) -> str | None:
        """Run a training script as a subprocess and return the MLflow run ID.

        Parses the run_id from stdout line: 'model_logged_to_mlflow run_id=<id>'.

        Args:
            module: Python module path (e.g. 'mlops.training.train_water').
            extra_args: Additional CLI arguments for the training script.
            data_path: Path to training data (--data argument).

        Returns:
            MLflow run ID string, or None if not found.
        """
        cmd = [
            sys.executable, "-m", module,
            "--data", data_path,
            "--mlflow-uri", self.mlflow_uri,
            "--output-dir", str(self.output_dir),
            "--register",
            "--device", self.device,
        ] + extra_args

        logger.info("launching_training", cmd=" ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error("training_subprocess_failed", stderr=result.stderr[-500:])
            return None

        # Extract run_id from log output
        for line in result.stdout.splitlines() + result.stderr.splitlines():
            if "run_id=" in line:
                for part in line.split():
                    if part.startswith("run_id="):
                        return part.split("=", 1)[1].strip()
        return None

    def _train_water_quality(self, data_path: str, args: dict[str, Any]) -> str | None:
        extra = [
            "--arch", args["arch"],
            "--epochs", str(args["epochs"]),
            "--lr", str(args["lr"]),
            "--hidden-size", str(args["hidden_size"]),
            "--batch-size", str(args["batch_size"]),
            "--patience", str(args["patience"]),
        ]
        return self._run_training_subprocess("mlops.training.train_water", extra, data_path)

    def _train_feeding(self, data_path: str, args: dict[str, Any]) -> str | None:
        extra = [
            "--epochs", str(args["epochs"]),
            "--lr", str(args["lr"]),
            "--batch-size", str(args["batch_size"]),
            "--patience", str(args["patience"]),
        ]
        return self._run_training_subprocess("mlops.training.train_feeding", extra, data_path)

    def _train_growth(self, data_yaml: str, args: dict[str, Any]) -> str | None:
        extra = [
            "--model", args["base_model"],
            "--epochs", str(args["epochs"]),
            "--imgsz", str(args["imgsz"]),
            "--batch", str(args["batch"]),
            "--patience", str(args["patience"]),
        ]
        return self._run_training_subprocess("mlops.training.train_growth", extra, data_yaml)

    # ── Per-model check ────────────────────────────────────────────────────────

    def _run_drift_check(
        self,
        model_name: str,
        reference_csv: str,
        current_csv: str,
    ) -> dict[str, Any] | None:
        """Run drift detection for one model and return the DriftReport dict.

        Returns None on any error so the caller can degrade gracefully.
        """
        detector = DriftDetector()
        check_map = {
            "WaterQualityPredictor":     detector.check_water_quality,
            "FeedingActivityClassifier": detector.check_feeding,
            "FishDetection":             detector.check_growth,
        }
        check_fn = check_map.get(model_name)
        if check_fn is None:
            logger.warning("no_drift_check_for_model", model=model_name)
            return None
        try:
            report = check_fn(reference_csv, current_csv)
            logger.info(
                "drift_check_done",
                model=model_name,
                max_psi=round(report.max_psi, 4),
                should_retrain=report.should_retrain,
            )
            return report.to_dict()
        except Exception as exc:
            logger.error("drift_check_failed", model=model_name, error=str(exc))
            return None

    def _check_model(
        self,
        model_name: str,
        threshold: int,
        train_fn: Any,
        data_path: str | None,
        train_args: dict[str, Any],
        dry_run: bool = False,
        drift_reference_csv: str | None = None,
        drift_current_csv: str | None = None,
    ) -> RetrainingResult:
        """Run the check-and-retrain cycle for one model.

        Retraining is triggered when either:
        - new_samples ≥ threshold  (scheduled retraining), or
        - drift max_psi ≥ PSI_WARNING (emergency retraining).

        Args:
            model_name: Registered model name.
            threshold: Minimum new samples to trigger retraining.
            train_fn: Callable that runs training and returns a run_id.
            data_path: Path to data for training (None = skip training).
            train_args: Hyperparameter dict passed to train_fn.
            dry_run: If True, count samples and check drift but skip training.
            drift_reference_csv: Reference (training) CSV for drift detection.
            drift_current_csv: Current (production) CSV for drift detection.

        Returns:
            RetrainingResult.
        """
        result = RetrainingResult(
            model=model_name,
            new_samples=self._count_new_samples(model_name),
            threshold=threshold,
        )

        # ── Drift detection ────────────────────────────────────────────────────
        drift_triggered = False
        if drift_reference_csv and drift_current_csv:
            drift_dict = self._run_drift_check(model_name, drift_reference_csv, drift_current_csv)
            result.drift_report = drift_dict
            if drift_dict and drift_dict.get("should_retrain"):
                drift_triggered = True
                logger.warning(
                    "drift_emergency_retrain",
                    model=model_name,
                    max_psi=drift_dict.get("max_psi"),
                )

        needs_retrain = result.new_samples >= threshold or drift_triggered

        if not needs_retrain:
            logger.info(
                "no_retrain_needed",
                model=model_name,
                new_samples=result.new_samples,
                threshold=threshold,
                drift_triggered=drift_triggered,
            )
            return result

        result.drift_triggered = drift_triggered

        if dry_run:
            logger.info(
                "dry_run_skip_training",
                model=model_name,
                drift_triggered=drift_triggered,
            )
            result.triggered = True
            return result

        if data_path is None:
            logger.warning("no_data_path_configured", model=model_name)
            result.error = "No data path configured for this model"
            return result

        result.triggered = True
        logger.info(
            "triggering_retraining",
            model=model_name,
            new_samples=result.new_samples,
            drift_triggered=drift_triggered,
        )

        try:
            run_id = train_fn(data_path, train_args)
            result.run_id = run_id
        except Exception as exc:
            result.error = str(exc)
            logger.error("training_failed", model=model_name, error=str(exc))
            return result

        if run_id is None:
            result.error = "Training completed but run_id could not be determined"
            return result

        # Evaluate and promote
        eval_result = self.evaluator.evaluate_and_maybe_promote(model_name, run_id)
        result.promoted = eval_result["promoted"]
        result.gate_results = eval_result.get("gate_results", {})
        logger.info(
            "automl_cycle_complete",
            model=model_name,
            promoted=result.promoted,
            gate_results=result.gate_results,
        )
        return result

    # ── Public API ─────────────────────────────────────────────────────────────

    def check_and_retrain(
        self,
        water_data_path: str | None = None,
        feeding_data_path: str | None = None,
        growth_data_yaml: str | None = None,
        water_args: dict[str, Any] | None = None,
        feeding_args: dict[str, Any] | None = None,
        growth_args: dict[str, Any] | None = None,
        dry_run: bool = False,
        # Drift detection CSVs (reference = training distribution, current = live)
        wq_reference_csv: str | None = None,
        wq_current_csv: str | None = None,
        feeding_reference_csv: str | None = None,
        feeding_current_csv: str | None = None,
        growth_reference_csv: str | None = None,
        growth_current_csv: str | None = None,
    ) -> dict[str, Any]:
        """Check all models for retraining eligibility and trigger if needed.

        Retraining is triggered per model when either:
        - New sample count ≥ threshold, or
        - Drift PSI ≥ 0.20 (emergency trigger).

        Args:
            water_data_path: Path to water quality training CSV.
            feeding_data_path: Path to feeding dataset root directory.
            growth_data_yaml: Path to YOLO data.yaml for growth model.
            water_args: Override default water-quality training hyper-parameters.
            feeding_args: Override default feeding training hyper-parameters.
            growth_args: Override default growth training hyper-parameters.
            dry_run: Count samples, check drift, log intent — skip actual training.
            wq_reference_csv: Reference CSV for water quality drift detection.
            wq_current_csv: Current production CSV for water quality drift.
            feeding_reference_csv: Reference CSV for feeding drift detection.
            feeding_current_csv: Current CSV for feeding drift detection.
            growth_reference_csv: Reference CSV for growth model drift.
            growth_current_csv: Current CSV for growth model drift.

        Returns:
            Dict with per-model RetrainingResult dicts under 'results' key,
            plus 'summary' counts.
        """
        results = {}

        results["WaterQualityPredictor"] = self._check_model(
            model_name="WaterQualityPredictor",
            threshold=MIN_NEW_SAMPLES_WATER,
            train_fn=self._train_water_quality,
            data_path=water_data_path,
            train_args={**_DEFAULT_WATER_ARGS, **(water_args or {})},
            dry_run=dry_run,
            drift_reference_csv=wq_reference_csv,
            drift_current_csv=wq_current_csv,
        ).to_dict()

        results["FeedingActivityClassifier"] = self._check_model(
            model_name="FeedingActivityClassifier",
            threshold=MIN_NEW_SAMPLES_FEEDING,
            train_fn=self._train_feeding,
            data_path=feeding_data_path,
            train_args={**_DEFAULT_FEEDING_ARGS, **(feeding_args or {})},
            dry_run=dry_run,
            drift_reference_csv=feeding_reference_csv,
            drift_current_csv=feeding_current_csv,
        ).to_dict()

        results["FishDetection"] = self._check_model(
            model_name="FishDetection",
            threshold=MIN_NEW_SAMPLES_GROWTH,
            train_fn=self._train_growth,
            data_path=growth_data_yaml,
            train_args={**_DEFAULT_GROWTH_ARGS, **(growth_args or {})},
            dry_run=dry_run,
            drift_reference_csv=growth_reference_csv,
            drift_current_csv=growth_current_csv,
        ).to_dict()

        n_triggered = sum(1 for r in results.values() if r["triggered"])
        n_drift = sum(1 for r in results.values() if r["drift_triggered"])
        n_promoted = sum(1 for r in results.values() if r["promoted"])

        summary = {
            "models_checked": len(results),
            "retrain_triggered": n_triggered,
            "drift_triggered": n_drift,
            "models_promoted": n_promoted,
            "dry_run": dry_run,
        }
        logger.info("automl_summary", **summary)
        return {"results": results, "summary": summary}

    def evaluate_and_promote(self, model_name: str, run_id: str) -> dict[str, Any]:
        """Evaluate a training run and promote to Production if it passes the gate.

        Args:
            model_name: Registered model name (must be in QUALITY_GATES).
            run_id: MLflow run ID to evaluate.

        Returns:
            Evaluation result dict from ModelEvaluator.
        """
        return self.evaluator.evaluate_and_maybe_promote(model_name, run_id)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    parser = argparse.ArgumentParser(description="AutoML pipeline — check and retrain all models")
    parser.add_argument("--mlflow-uri", default="http://localhost:5000")
    parser.add_argument("--water-data", default=None, help="Path to water quality CSV")
    parser.add_argument("--feeding-data", default=None, help="Path to feeding dataset root")
    parser.add_argument("--growth-data", default=None, help="Path to growth data.yaml")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output-dir", default=".")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count samples, check drift, log intent — skip actual training",
    )
    parser.add_argument(
        "--promote", nargs=2, metavar=("MODEL_NAME", "RUN_ID"),
        help="Directly evaluate and promote a specific run (skips threshold check)",
    )
    # Drift detection CSV pairs
    parser.add_argument("--wq-drift-ref", default=None, help="Water quality reference CSV for drift")
    parser.add_argument("--wq-drift-cur", default=None, help="Water quality current CSV for drift")
    parser.add_argument("--feeding-drift-ref", default=None, help="Feeding reference CSV for drift")
    parser.add_argument("--feeding-drift-cur", default=None, help="Feeding current CSV for drift")
    parser.add_argument("--growth-drift-ref", default=None, help="Growth reference CSV for drift")
    parser.add_argument("--growth-drift-cur", default=None, help="Growth current CSV for drift")
    args = parser.parse_args()

    pipeline = AutoMLPipeline(
        mlflow_uri=args.mlflow_uri,
        device=args.device,
        output_dir=args.output_dir,
    )

    if args.promote:
        model_name, run_id = args.promote
        result = pipeline.evaluate_and_promote(model_name, run_id)
        print(json.dumps(result, indent=2))
    else:
        results = pipeline.check_and_retrain(
            water_data_path=args.water_data,
            feeding_data_path=args.feeding_data,
            growth_data_yaml=args.growth_data,
            dry_run=args.dry_run,
            wq_reference_csv=args.wq_drift_ref,
            wq_current_csv=args.wq_drift_cur,
            feeding_reference_csv=args.feeding_drift_ref,
            feeding_current_csv=args.feeding_drift_cur,
            growth_reference_csv=args.growth_drift_ref,
            growth_current_csv=args.growth_drift_cur,
        )
        print(json.dumps(results, indent=2))
