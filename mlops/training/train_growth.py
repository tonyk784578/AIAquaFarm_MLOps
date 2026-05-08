"""Training pipeline for the fish growth detection (YOLOv8) model.

Fine-tunes YOLOv8 on labelled fish detection images exported from CVAT
and registers the best checkpoint to the MLflow model registry.

Data format — YOLO v8 (one directory tree, referenced by data.yaml)::

    dataset/
      data.yaml          # train/val/test paths + class names
      images/
        train/ *.jpg
        val/   *.jpg
      labels/
        train/ *.txt     # cls cx cy w h  (normalised)
        val/   *.txt

Usage::

    python -m mlops.training.train_growth \\
        --data dataset/data.yaml \\
        --model yolov8n.pt \\
        --epochs 100 \\
        --imgsz 640 \\
        --batch 16 \\
        --device cpu \\
        --register

Requirements: ai_modules[vision] (ultralytics) must be installed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import mlflow
import structlog

logger = structlog.get_logger()

EXPERIMENT_NAME = "fish-growth-detection"
MODEL_NAME = "FishDetection"


def train(
    data_yaml: str,
    base_model: str = "yolov8n.pt",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    device: str = "cpu",
    patience: int = 20,
    mlflow_uri: str = "http://localhost:5000",
    register: bool = False,
    output_dir: str = ".",
) -> None:
    """Fine-tune YOLOv8 on fish detection data with MLflow tracking.

    Args:
        data_yaml: Path to YOLO data.yaml file.
        base_model: Base YOLOv8 weights name or path ('yolov8n.pt', 'yolov8s.pt', …).
        epochs: Maximum training epochs.
        imgsz: Input image size in pixels (square).
        batch: Training batch size (-1 = auto-batch).
        device: PyTorch device string ('cpu', '0', 'cuda:0').
        patience: Early stopping patience (epochs without improvement).
        mlflow_uri: MLflow tracking server URL.
        register: If True, register best model to the MLflow model registry.
        output_dir: Directory for local checkpoint artefacts.
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        raise ImportError(
            "ultralytics is required for growth model training.\n"
            "Install with: pip install 'ai_modules[vision]'"
        )

    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment(EXPERIMENT_NAME)
    output_path = Path(output_dir)

    with mlflow.start_run() as run:
        params = {
            "base_model": base_model,
            "epochs": epochs,
            "imgsz": imgsz,
            "batch": batch,
            "device": device,
            "patience": patience,
        }
        mlflow.log_params(params)
        logger.info("starting_growth_model_training", **params)

        # YOLOv8 training — logs per-epoch metrics to its own CSV;
        # we pull final metrics for MLflow after training completes.
        model = YOLO(base_model)
        results = model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=device,
            patience=patience,
            project=str(output_path / "runs"),
            name="fish_detection",
            exist_ok=True,
        )

        # Log detection metrics to MLflow
        metrics = {
            "mAP50": float(results.box.map50),
            "mAP50_95": float(results.box.map),
            "precision": float(results.box.mp),
            "recall": float(results.box.mr),
        }
        mlflow.log_metrics(metrics)
        logger.info("training_complete", **{k: round(v, 4) for k, v in metrics.items()})

        # Best weights path (ultralytics saves to <project>/<name>/weights/best.pt)
        best_pt = output_path / "runs" / "fish_detection" / "weights" / "best.pt"
        if best_pt.exists():
            mlflow.log_artifact(str(best_pt), artifact_path="weights")
        else:
            logger.warning("best_weights_not_found", expected=str(best_pt))

        # Log the YOLO model to MLflow (PyTorch format)
        mlflow.pytorch.log_model(
            model.model,
            artifact_path="model",
            registered_model_name=MODEL_NAME if register else None,
        )
        logger.info(
            "model_logged_to_mlflow",
            run_id=run.info.run_id,
            registered=register,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train fish growth detection model (YOLOv8)")
    parser.add_argument("--data", required=True, help="Path to data.yaml")
    parser.add_argument("--model", default="yolov8n.pt", help="Base YOLO weights")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--mlflow-uri", default="http://localhost:5000")
    parser.add_argument("--register", action="store_true", help="Register to MLflow registry")
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args()

    train(
        data_yaml=args.data,
        base_model=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        patience=args.patience,
        mlflow_uri=args.mlflow_uri,
        register=args.register,
        output_dir=args.output_dir,
    )
