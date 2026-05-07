"""MLflow model registry client — manages model versions and stage transitions.

Model lifecycle: None → Staging → Production → Archived

Registered model names:
    - FishDetection           (growth AI module)
    - FeedingActivityClassifier (feeding AI module)
    - WaterQualityPredictor   (water quality AI module)

TODO (Phase 2): Add model signature validation before registration.
TODO (Phase 4): Implement A/B testing with canary model stage.
"""

from typing import Optional

import mlflow
import structlog
from mlflow.tracking import MlflowClient

logger = structlog.get_logger()

REGISTERED_MODELS = [
    "FishDetection",
    "FeedingActivityClassifier",
    "WaterQualityPredictor",
]


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
        """Transition a model version to Production stage.

        Args:
            model_name: Registered model name.
            version: Version number to promote.

        TODO (Phase 4): Archive existing production version before promoting.
        """
        self.client.transition_model_version_stage(
            name=model_name,
            version=str(version),
            stage="Production",
            archive_existing_versions=True,
        )
        logger.info("model_promoted", model=model_name, version=version, stage="Production")

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
