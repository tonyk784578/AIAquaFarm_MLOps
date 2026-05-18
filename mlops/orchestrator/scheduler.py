"""Periodic AutoML scheduler — drives ``AutoMLPipeline.check_and_retrain``.

Two cadences run side-by-side:

* **AutoML cycle** (default 60 min) — count new samples, run drift check,
  retrain + promote eligible models.
* **Drift-only cycle** (default 15 min) — fast lightweight PSI computation
  without training; emits ``drift`` audit events. Useful for the dashboard
  ticker.

Every run writes one ``automl`` (or ``drift``) ``AuditEvent``, plus one
``promotion`` event per model that was successfully promoted.

Run directly::

    python -m mlops scheduler

Run a one-shot cycle (for debugging or external cron drivers)::

    python -m mlops scheduler --once
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from mlops.config import Settings, get_settings
from mlops.evaluation.drift_detector import DriftDetector
from mlops.orchestrator.audit_log import AuditLog
from mlops.training.automl import AutoMLPipeline

logger = structlog.get_logger()


class OrchestratorScheduler:
    """Runs AutoML + drift checks on a fixed cadence and writes audit events.

    Attributes:
        settings: MLOps Settings.
        audit: AuditLog handle.
        pipeline: AutoMLPipeline (lazily constructed if data_lake unavailable).
        detector: DriftDetector for lightweight cycles.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.audit = audit or AuditLog(self.settings.audit_log_path)
        self.detector = DriftDetector()

        data_lake = self._maybe_data_lake()
        self.pipeline = AutoMLPipeline(
            mlflow_uri=self.settings.mlflow_tracking_uri,
            data_lake=data_lake,
            device=self.settings.device,
            output_dir=str(self.settings.artifact_dir),
        )

    # ── Single-cycle helpers ───────────────────────────────────────────────────

    def run_automl_cycle(self) -> dict[str, Any]:
        """Run one AutoML check-and-retrain pass and record audit events."""
        logger.info("automl_cycle_start")
        s = self.settings
        try:
            result = self.pipeline.check_and_retrain(
                water_data_path=s.wq_training_csv,
                feeding_data_path=s.feeding_training_dir,
                growth_data_yaml=s.growth_training_yaml,
                dry_run=s.dry_run,
                wq_reference_csv=s.wq_reference_csv,
                wq_current_csv=s.wq_current_csv,
                feeding_reference_csv=s.feeding_reference_csv,
                feeding_current_csv=s.feeding_current_csv,
                growth_reference_csv=s.growth_reference_csv,
                growth_current_csv=s.growth_current_csv,
            )
        except Exception as exc:
            logger.exception("automl_cycle_failed")
            self.audit.log("error", model="", data={"phase": "automl", "error": str(exc)})
            return {"results": {}, "summary": {"error": str(exc)}}

        # One pipeline-level event …
        self.audit.log("automl", model="", data=result.get("summary", {}))
        # … plus per-model detail for the dashboard timeline.
        for model_name, r in result.get("results", {}).items():
            self.audit.log(
                "automl",
                model=model_name,
                data={
                    "new_samples": r.get("new_samples"),
                    "threshold": r.get("threshold"),
                    "triggered": r.get("triggered"),
                    "drift_triggered": r.get("drift_triggered"),
                    "promoted": r.get("promoted"),
                    "run_id": r.get("run_id"),
                    "gate_results": r.get("gate_results"),
                    "drift_report": r.get("drift_report"),
                    "error": r.get("error"),
                },
            )
            if r.get("promoted"):
                self.audit.log(
                    "promotion",
                    model=model_name,
                    data={"run_id": r.get("run_id"), "gate_results": r.get("gate_results")},
                )
        logger.info("automl_cycle_done", **result.get("summary", {}))
        return result

    def run_drift_cycle(self) -> dict[str, Any]:
        """Run drift-only PSI check across all configured CSV pairs."""
        s = self.settings
        logger.info("drift_cycle_start")
        try:
            report = self.detector.check_all(
                wq_reference=s.wq_reference_csv,
                wq_current=s.wq_current_csv,
                feeding_reference=s.feeding_reference_csv,
                feeding_current=s.feeding_current_csv,
                growth_reference=s.growth_reference_csv,
                growth_current=s.growth_current_csv,
            )
        except Exception as exc:
            logger.exception("drift_cycle_failed")
            self.audit.log("error", model="", data={"phase": "drift", "error": str(exc)})
            return {"reports": {}, "summary": {"error": str(exc)}}

        for model_name, r in report.get("reports", {}).items():
            self.audit.log("drift", model=model_name, data=r)
        logger.info("drift_cycle_done", **report.get("summary", {}))
        return report

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run_forever(self) -> None:
        """Run AutoML + drift cycles on their respective cadences until interrupted."""
        import schedule

        s = self.settings
        schedule.every(s.automl_interval_minutes).minutes.do(self.run_automl_cycle)
        schedule.every(s.drift_only_interval_minutes).minutes.do(self.run_drift_cycle)

        logger.info(
            "scheduler_started",
            automl_min=s.automl_interval_minutes,
            drift_min=s.drift_only_interval_minutes,
            dry_run=s.dry_run,
        )

        # Run once at startup so the dashboard shows fresh data immediately.
        self.run_drift_cycle()

        while True:
            schedule.run_pending()
            time.sleep(5)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _maybe_data_lake(self):
        """Return a DataLakeStorage instance, or None if boto3 is unavailable."""
        try:
            from mlops.data_lake.storage import from_settings as _lake_from_settings

            return _lake_from_settings()
        except Exception as exc:
            logger.warning("data_lake_unavailable", error=str(exc))
            return None
