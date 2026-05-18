"""AIAquafarm MLOps package — orchestration, registry, evaluation, and deployment.

Sub-packages
------------
    config         — environment-driven settings (Settings)
    registry       — MLflow model-registry wrapper (ModelRegistry)
    evaluation     — quality gates + drift detection (ModelEvaluator, DriftDetector)
    training       — training scripts + AutoML orchestration (AutoMLPipeline)
    deployment     — edge-device OTA deployer (EdgeDeployer)
    data_collector — sensor/camera collectors for the data lake
    data_lake      — S3-compatible object-storage client (DataLakeStorage)
    orchestrator   — runtime audit log + periodic scheduler
    api            — FastAPI observability + admin endpoints

Top-level helpers
-----------------
    get_settings   — cached MLOps Settings singleton
"""

from mlops.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
__version__ = "0.1.0"
