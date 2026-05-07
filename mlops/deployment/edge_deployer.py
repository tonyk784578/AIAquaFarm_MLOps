"""Edge deployer — downloads production models and pushes to edge devices.

Pulls the latest production model from MLflow, optionally converts to
ONNX/TensorRT for edge optimisation, then deploys to edge device via
SSH/SCP or an edge management API.

TODO (Phase 4): Implement ONNX export and TensorRT conversion.
TODO (Phase 4): Add health check after deployment (inference smoke test).
TODO (Phase 4): Support over-the-air update with rollback on failure.
"""

from pathlib import Path
from typing import Optional

import structlog

from mlops.registry.mlflow_registry import ModelRegistry

logger = structlog.get_logger()


class EdgeDeployer:
    """Deploys models from MLflow registry to edge devices.

    Attributes:
        registry: ModelRegistry for fetching production models.
        edge_host: Edge device hostname or IP.
        deploy_path: Target directory on edge device.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        edge_host: str,
        deploy_path: str = "/opt/aquafarm/models",
    ) -> None:
        self.registry = registry
        self.edge_host = edge_host
        self.deploy_path = deploy_path

    def deploy_model(self, model_name: str, local_cache: Optional[Path] = None) -> bool:
        """Download production model and deploy to edge device.

        Args:
            model_name: Registered model name to deploy.
            local_cache: Optional local directory for model cache.

        Returns:
            True if deployment was successful.

        TODO (Phase 4): Download from MLflow, convert to ONNX, push via SCP.
        """
        uri = self.registry.get_production_model_uri(model_name)
        if not uri:
            logger.error("no_production_model_to_deploy", model=model_name)
            return False

        logger.info("deploying_model_stub", model=model_name, uri=uri, target=self.edge_host)
        # TODO (Phase 4):
        # 1. mlflow.artifacts.download_artifacts(artifact_uri=uri, dst_path=local_cache)
        # 2. Convert to ONNX: onnx_path = export_to_onnx(local_path)
        # 3. Push: scp onnx_path edge_host:deploy_path
        # 4. Restart inference service on edge
        return False

    def deploy_all(self) -> dict[str, bool]:
        """Deploy all production models to the edge device.

        Returns:
            Dict mapping model name to deployment success status.
        """
        from mlops.registry.mlflow_registry import REGISTERED_MODELS
        results = {}
        for model_name in REGISTERED_MODELS:
            results[model_name] = self.deploy_model(model_name)
        logger.info("all_models_deployed", results=results)
        return results
