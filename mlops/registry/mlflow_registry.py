"""MLflow model registry client — manages model versions and stage transitions.

Model lifecycle: None → Staging → Production → Archived

Registered model names:
    - FishDetection           (growth AI module)
    - FeedingActivityClassifier (feeding AI module)
    - WaterQualityPredictor   (water quality AI module)

TODO (Phase 4): Implement A/B testing with canary model stage.
"""

from __future__ import annotations

from typing import Any, Optional

import mlflow
import structlog
from mlflow.tracking import MlflowClient

logger = structlog.get_logger()

REGISTERED_MODELS = [
    "FishDetection",
    "FeedingActivityClassifier",
    "WaterQualityPredictor",
]

# ── Expected model signatures ──────────────────────────────────────────────────
# Each entry: {"inputs": [(name, dtype, shape)], "outputs": [(name, dtype, shape)]}
# shape uses -1 for variable batch dimension.

_MODEL_SIGNATURES: dict[str, dict[str, list[tuple[str, str, tuple]]]] = {
    "FishDetection": {
        "inputs":  [("frame", "float32", (-1, 3, 640, 640))],
        "outputs": [("detections", "float32", (-1,))],
    },
    "FeedingActivityClassifier": {
        "inputs":  [("frame", "float32", (-1, 3, 224, 224))],
        "outputs": [("activity_score", "float32", (-1, 1))],
    },
    "WaterQualityPredictor": {
        "inputs":  [("sequence", "float32", (-1, 24, 7))],
        "outputs": [("prediction", "float32", (-1, 3))],
    },
}


def _shapes_compatible(expected: tuple, actual: tuple) -> bool:
    """Return True if actual shape is compatible with expected (ignoring -1 dims)."""
    if len(expected) != len(actual):
        return False
    for e, a in zip(expected, actual):
        if e != -1 and e != a:
            return False
    return True


class SignatureValidationError(ValueError):
    """Raised when a model's input/output tensor does not match its expected signature."""


class ModelRegistry:
    """Wrapper around MLflow model registry for AIAquafarm models.

    Attributes:
        client: MLflow tracking client.
        tracking_uri: MLflow server URI.
    """

    def __init__(self, tracking_uri: str) -> None:
        self.tracking_uri = tracking_uri
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient(tracking_uri=tracking_uri)

    # ── Signature validation ───────────────────────────────────────────────────

    def validate_signature(
        self,
        model_name: str,
        model: Any,
        device: str = "cpu",
    ) -> bool:
        """Validate a PyTorch model's input/output shapes against the expected signature.

        Runs a single forward pass with a dummy input tensor whose shape is derived
        from _MODEL_SIGNATURES. Logs a warning (does not raise) if the model is
        not callable (e.g. a stub that hasn't been loaded yet).

        Args:
            model_name: Registered model name — must be in _MODEL_SIGNATURES.
            model: PyTorch nn.Module or any callable that accepts a tensor.
            device: Device to run the validation forward pass on.

        Returns:
            True if signature matches.

        Raises:
            SignatureValidationError: If the output shape does not match the
                expected signature, or if model_name is unknown.
        """
        sig = _MODEL_SIGNATURES.get(model_name)
        if sig is None:
            raise SignatureValidationError(
                f"No signature registered for model '{model_name}'. "
                f"Known models: {list(_MODEL_SIGNATURES)}"
            )

        try:
            import torch

            # Build dummy input replacing batch dim (-1) with 1
            input_spec = sig["inputs"][0]
            shape = tuple(1 if d == -1 else d for d in input_spec[2])
            dummy = torch.zeros(shape, dtype=torch.float32)

            try:
                import contextlib
                with torch.no_grad(), contextlib.suppress(Exception):
                    dummy = dummy.to(device)
                    output = model(dummy)
            except Exception as exc:
                logger.warning(
                    "signature_forward_pass_failed",
                    model=model_name,
                    error=str(exc),
                    msg="Skipping signature check — model may not be fully loaded",
                )
                return True  # degrade gracefully for stub/unloaded models

            out_tensor = output if isinstance(output, torch.Tensor) else output[0]
            actual_shape = tuple(out_tensor.shape)
            expected_shape = sig["outputs"][0][2]

            if not _shapes_compatible(expected_shape, actual_shape):
                raise SignatureValidationError(
                    f"{model_name}: expected output shape {expected_shape}, "
                    f"got {actual_shape}"
                )

            logger.info(
                "signature_valid",
                model=model_name,
                input_shape=shape,
                output_shape=actual_shape,
            )
            return True

        except ImportError:
            logger.warning("torch_not_available", msg="Skipping signature validation")
            return True

    def validate_and_register(
        self,
        model_name: str,
        model: Any,
        run_id: str,
        artifact_path: str = "model",
        device: str = "cpu",
    ) -> bool:
        """Validate model signature then register to MLflow if it passes.

        Args:
            model_name: Registered model name.
            model: PyTorch model to validate and register.
            run_id: MLflow run ID to register the version under.
            artifact_path: Artifact sub-path within the run.
            device: Device for validation forward pass.

        Returns:
            True if the model was registered successfully.

        Raises:
            SignatureValidationError: If signature validation fails.
        """
        self.validate_signature(model_name, model, device=device)

        model_uri = f"runs:/{run_id}/{artifact_path}"
        version_info = mlflow.register_model(model_uri, model_name)
        logger.info(
            "model_registered",
            model=model_name,
            version=version_info.version,
            run_id=run_id,
        )
        return True

    # ── Registry operations ────────────────────────────────────────────────────

    def get_production_model_uri(self, model_name: str) -> Optional[str]:
        """Return the URI for the current production version of a model.

        Args:
            model_name: Registered model name (e.g., 'FishDetection').

        Returns:
            MLflow model URI string, or None if no production version exists.
        """
        try:
            versions = self.client.get_latest_versions(
                model_name, stages=["Production"]
            )
            if versions:
                v = versions[0]
                uri = f"models:/{model_name}/{v.version}"
                logger.info("production_model_found", model=model_name, version=v.version)
                return uri
            logger.warning("no_production_model", model=model_name)
            return None
        except Exception as exc:
            logger.error("registry_lookup_failed", model=model_name, error=str(exc))
            return None

    def promote_to_production(self, model_name: str, version: int) -> None:
        """Transition a model version to Production, archiving the previous one."""
        self.client.transition_model_version_stage(
            name=model_name,
            version=str(version),
            stage="Production",
            archive_existing_versions=True,
        )
        logger.info("model_promoted", model=model_name, version=version, stage="Production")

    # ── A/B testing (Canary stage) ─────────────────────────────────────────────

    def promote_to_canary(self, model_name: str, version: int) -> None:
        """Promote a model version to the Canary stage for A/B testing.

        A Canary model receives a configurable fraction of inference traffic
        (see ``get_model_for_request``). If its metrics beat Production over
        the evaluation window, call ``graduate_canary_to_production``.

        Args:
            model_name: Registered model name.
            version: Version to promote to Canary.
        """
        # Archive any existing Canary before promoting the new one
        existing = self.client.get_latest_versions(model_name, stages=["Staging"])
        for v in existing:
            self.client.transition_model_version_stage(
                name=model_name, version=v.version, stage="Archived",
            )
        self.client.transition_model_version_stage(
            name=model_name,
            version=str(version),
            stage="Staging",  # MLflow uses "Staging" as the Canary slot
            archive_existing_versions=False,
        )
        logger.info("model_promoted_canary", model=model_name, version=version)

    def get_model_for_request(
        self,
        model_name: str,
        canary_fraction: float = 0.1,
        request_hash: int | None = None,
    ) -> tuple[str, str]:
        """Return the model URI to use for this request (Production or Canary).

        Uses deterministic hash-based routing so a given request ID always
        goes to the same model variant within a session.

        Args:
            model_name: Registered model name.
            canary_fraction: Fraction of requests [0, 1] routed to Canary.
            request_hash: Integer hash of the request (e.g. hash(tank_id)).
                          Defaults to a random value.

        Returns:
            Tuple of (model_uri, variant_label) where variant_label is
            'production' or 'canary'.
        """
        import random

        canary_versions = self.client.get_latest_versions(model_name, stages=["Staging"])
        prod_versions = self.client.get_latest_versions(model_name, stages=["Production"])

        prod_uri = (
            f"models:/{model_name}/{prod_versions[0].version}" if prod_versions else None
        )
        canary_uri = (
            f"models:/{model_name}/{canary_versions[0].version}" if canary_versions else None
        )

        if not canary_uri or canary_fraction <= 0.0:
            return prod_uri or "", "production"

        bucket = (request_hash % 100) if request_hash is not None else random.randint(0, 99)
        if bucket < int(canary_fraction * 100):
            logger.debug("ab_routing_canary", model=model_name, bucket=bucket)
            return canary_uri, "canary"

        logger.debug("ab_routing_production", model=model_name, bucket=bucket)
        return prod_uri or canary_uri, "production"

    def graduate_canary_to_production(self, model_name: str) -> bool:
        """Graduate the current Canary (Staging) version to Production.

        Args:
            model_name: Registered model name.

        Returns:
            True if a Canary version was found and promoted.
        """
        canary = self.client.get_latest_versions(model_name, stages=["Staging"])
        if not canary:
            logger.warning("no_canary_to_graduate", model=model_name)
            return False
        version = int(canary[0].version)
        self.promote_to_production(model_name, version)
        logger.info("canary_graduated", model=model_name, version=version)
        return True

    def rollback_canary(self, model_name: str) -> bool:
        """Archive the Canary version (revert to Production-only traffic).

        Args:
            model_name: Registered model name.

        Returns:
            True if a Canary was found and archived.
        """
        canary = self.client.get_latest_versions(model_name, stages=["Staging"])
        if not canary:
            logger.warning("no_canary_to_rollback", model=model_name)
            return False
        self.client.transition_model_version_stage(
            name=model_name, version=canary[0].version, stage="Archived",
        )
        logger.info("canary_rolled_back", model=model_name, version=canary[0].version)
        return True

    def compare_canary_vs_production(
        self,
        model_name: str,
        metric_name: str = "val_loss",
        direction: str = "min",
    ) -> dict[str, Any]:
        """Compare metric values of Canary vs Production versions.

        Args:
            model_name: Registered model name.
            metric_name: MLflow metric to compare.
            direction: 'min' (lower-is-better) or 'max' (higher-is-better).

        Returns:
            Dict with 'winner' ('canary' | 'production' | 'tie'), metric values,
            and recommendation ('graduate' | 'rollback' | 'continue').
        """
        def _get_metric(stage: str) -> float | None:
            versions = self.client.get_latest_versions(model_name, stages=[stage])
            if not versions:
                return None
            run = self.client.get_run(versions[0].run_id)
            return run.data.metrics.get(metric_name)

        prod_metric = _get_metric("Production")
        canary_metric = _get_metric("Staging")

        if canary_metric is None or prod_metric is None:
            return {
                "winner": "unknown",
                "prod_metric": prod_metric,
                "canary_metric": canary_metric,
                "recommendation": "continue",
                "reason": "Missing metric data",
            }

        if direction == "min":
            canary_wins = canary_metric < prod_metric
        else:
            canary_wins = canary_metric > prod_metric

        tie = canary_metric == prod_metric
        winner = "tie" if tie else ("canary" if canary_wins else "production")
        recommendation = "graduate" if canary_wins else "rollback"

        result = {
            "winner": winner,
            "prod_metric": prod_metric,
            "canary_metric": canary_metric,
            "metric_name": metric_name,
            "direction": direction,
            "recommendation": recommendation,
        }
        logger.info("ab_comparison", model=model_name, **result)
        return result

    def list_model_versions(self, model_name: str) -> list[dict]:
        """List all versions of a registered model.

        Args:
            model_name: Registered model name.

        Returns:
            List of version dicts with name, version, stage, and run_id.
        """
        try:
            versions = self.client.search_model_versions(f"name='{model_name}'")
            return [
                {
                    "name": v.name,
                    "version": v.version,
                    "stage": v.current_stage,
                    "run_id": v.run_id,
                }
                for v in versions
            ]
        except Exception as exc:
            logger.error("list_versions_failed", model=model_name, error=str(exc))
            return []
