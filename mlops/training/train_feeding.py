"""Training pipeline for the feeding activity classification model.

Trains a CNN classifier on labelled feeding video frames exported from CVAT.
Labels: 0=no_activity, 1=low, 2=medium, 3=high

TODO (Phase 2): Collect labelled dataset with CVAT export.
TODO (Phase 2): Implement transfer learning from ResNet50.
TODO (Phase 2): Add temporal modelling (3D CNN or LSTM over frame sequence).
"""

import argparse

import mlflow
import structlog

logger = structlog.get_logger()

EXPERIMENT_NAME = "feeding-activity-classification"
MODEL_NAME = "FeedingActivityClassifier"


def train(
    data_dir: str,
    base_model: str = "resnet50",
    epochs: int = 30,
    lr: float = 1e-4,
    batch_size: int = 32,
) -> None:
    """Train feeding activity classifier with MLflow tracking.

    Args:
        data_dir: Root directory with train/val subdirs.
        base_model: torchvision model name for transfer learning.
        epochs: Training epochs.
        lr: Learning rate.
        batch_size: Training batch size.

    TODO (Phase 2): Implement using torchvision + torchvision.transforms.
    """
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run():
        mlflow.log_params({
            "base_model": base_model,
            "epochs": epochs,
            "lr": lr,
            "batch_size": batch_size,
        })
        logger.info("starting_feeding_model_training")
        logger.warning("train_feeding_stub", msg="Implement in Phase 2")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()
    train(args.data, epochs=args.epochs)
