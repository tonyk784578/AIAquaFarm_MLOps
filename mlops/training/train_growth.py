"""Training pipeline for the fish growth detection model.

Fine-tunes a YOLOv8 model on labelled fish detection images
exported from CVAT. Logs all metrics and artefacts to MLflow.

Training data format: YOLO v8 format (images + labels directories)
  data.yaml specifies: train, val, nc (num classes), names

TODO (Phase 2): Implement data loading from S3 data lake.
TODO (Phase 2): Add cross-validation and hyperparameter sweep.
TODO (Phase 2): Register best model to MLflow as 'FishDetection'.
"""

import argparse

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
) -> None:
    """Run YOLOv8 training with MLflow experiment tracking.

    Args:
        data_yaml: Path to YOLO data.yaml file.
        base_model: Base YOLOv8 weights ('yolov8n.pt', 'yolov8s.pt', etc.).
        epochs: Number of training epochs.
        imgsz: Input image size in pixels.
        batch: Batch size.

    TODO (Phase 2): Implement full training loop with early stopping.
    """
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run():
        mlflow.log_params({
            "base_model": base_model,
            "epochs": epochs,
            "imgsz": imgsz,
            "batch": batch,
        })

        logger.info("starting_growth_model_training", epochs=epochs)

        # TODO (Phase 2):
        # from ultralytics import YOLO
        # model = YOLO(base_model)
        # results = model.train(data=data_yaml, epochs=epochs, imgsz=imgsz, batch=batch)
        # mlflow.log_metrics({"mAP50": results.box.map50, "mAP50_95": results.box.map})
        # mlflow.pytorch.log_model(model, "model", registered_model_name=MODEL_NAME)

        logger.warning("train_growth_stub", msg="Implement in Phase 2")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train fish growth detection model")
    parser.add_argument("--data", required=True, help="Path to data.yaml")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=100)
    args = parser.parse_args()
    train(args.data, base_model=args.model, epochs=args.epochs)
