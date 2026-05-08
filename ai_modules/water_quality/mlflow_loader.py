"""MLflow model and scaler loader for the water quality prediction module.

Fetches the Production-stage model from the MLflow registry and the
accompanying FeatureScaler artefact stored in the same run.
"""

from __future__ import annotations

import tempfile

import mlflow
import mlflow.pytorch
import structlog

from ai_modules.water_quality.feature_engineering import FeatureScaler
from ai_modules.water_quality.model import WaterQualityPredictionModel

logger = structlog.get_logger()

_SCALER_ARTIFACT = "wq_scaler.npz"


class MLflowModelLoader:
    """Load a WaterQualityPredictionModel and its FeatureScaler from MLflow.

    The scaler is expected to be logged as a run artefact alongside the
    model.  If it is absent, a default (unfitted) scaler is returned and a
    warning is emitted.

    Usage::

        loader = MLflowModelLoader("http://mlflow:5000")
        model, scaler = loader.load("models:/WaterQualityPredictor/Production")
    """

    def __init__(self, tracking_uri: str, device: str = "cpu") -> None:
        self.tracking_uri = tracking_uri
        self.device = device
        mlflow.set_tracking_uri(tracking_uri)

    def load(
        self,
        model_uri: str,
    ) -> tuple[WaterQualityPredictionModel, FeatureScaler]:
        """Load model and scaler from MLflow.

        Args:
            model_uri: MLflow model URI, e.g. ``models:/WaterQualityPredictor/Production``.

        Returns:
            Tuple of (WaterQualityPredictionModel, FeatureScaler).

        Raises:
            mlflow.MlflowException: If the model cannot be fetched.
        """
        logger.info("loading_model_from_mlflow", uri=model_uri)
        wq_model = WaterQualityPredictionModel(device=self.device)
        wq_model.load_from_mlflow(model_uri)

        scaler = self._load_scaler(model_uri)
        return wq_model, scaler

    def _load_scaler(self, model_uri: str) -> FeatureScaler:
        """Download the scaler .npz from the same MLflow run."""
        try:
            run_id = self._resolve_run_id(model_uri)
            with tempfile.TemporaryDirectory() as tmp:
                local_path = mlflow.artifacts.download_artifacts(
                    run_id=run_id,
                    artifact_path=_SCALER_ARTIFACT,
                    dst_path=tmp,
                )
                scaler = FeatureScaler.load(local_path)
                logger.info("scaler_loaded_from_mlflow", run_id=run_id)
                return scaler
        except Exception as exc:
            logger.warning(
                "scaler_not_found_in_mlflow",
                error=str(exc),
                msg="Using default (identity) scaler — predictions will be unscaled",
            )
            return FeatureScaler()

    @staticmethod
    def _resolve_run_id(model_uri: str) -> str:
        """Resolve a models:/ URI to its underlying run_id."""
        # model_uri format: models:/ModelName/Stage  or  models:/ModelName/version
        client = mlflow.tracking.MlflowClient()
        parts = model_uri.replace("models:/", "").split("/")
        model_name, version_or_stage = parts[0], parts[1]

        if version_or_stage.isdigit():
            mv = client.get_model_version(model_name, version_or_stage)
        else:
            mvs = client.get_latest_versions(model_name, stages=[version_or_stage])
            if not mvs:
                raise ValueError(
                    f"No model version in stage '{version_or_stage}' for '{model_name}'"
                )
            mv = mvs[0]

        return mv.run_id


def load_production_model_and_scaler(
    tracking_uri: str,
    model_name: str = "WaterQualityPredictor",
    stage: str = "Production",
    device: str = "cpu",
) -> tuple[WaterQualityPredictionModel, FeatureScaler]:
    """Convenience wrapper used by the FastAPI lifespan.

    Args:
        tracking_uri: MLflow server URL.
        model_name: Registered model name in MLflow.
        stage: Model stage (``Production``, ``Staging``).
        device: PyTorch device string.

    Returns:
        Tuple of loaded model and scaler.
    """
    loader = MLflowModelLoader(tracking_uri, device=device)
    return loader.load(f"models:/{model_name}/{stage}")
