"""Training pipeline for the feeding activity regression model.

Fine-tunes a ResNet18 backbone to predict a continuous feeding activity
score (0.0–1.0) from a single camera frame.

Data format — ImageFolder-compatible regression layout::

    dataset/
      train/
        activity_0.00/  *.jpg   # frames with activity score ≈ 0.00
        activity_0.25/  *.jpg
        activity_0.50/  *.jpg
        activity_0.75/  *.jpg
        activity_1.00/  *.jpg
      val/
        activity_0.00/  *.jpg
        …
      labels.csv         # optional: path,score  (overrides folder names)

If labels.csv is present it is used instead of folder-name parsing.
Folder names must start with 'activity_' followed by the float score
(e.g. 'activity_0.50').

Usage::

    python -m mlops.training.train_feeding \\
        --data dataset/ \\
        --epochs 30 \\
        --lr 1e-4 \\
        --batch-size 32 \\
        --device cpu \\
        --register

Requirements: ai_modules[vision] (torchvision, opencv) must be installed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import mlflow
import mlflow.pytorch
import numpy as np
import structlog
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from ai_modules.feeding.model import FeedingActivityModel, _IMG_SIZE, _build_cnn

logger = structlog.get_logger()

EXPERIMENT_NAME = "feeding-activity-regression"
MODEL_NAME = "FeedingActivityClassifier"


# ── Dataset ────────────────────────────────────────────────────────────────────

class FeedingActivityDataset(Dataset):
    """Loads (image_path, activity_score) pairs from a directory tree.

    Parses activity scores from folder names (activity_<float>) or a
    labels.csv file in the root directory.
    """

    def __init__(self, root: Path, split: str = "train", img_size: int = _IMG_SIZE) -> None:
        self.img_size = img_size
        self.samples: list[tuple[Path, float]] = []

        labels_csv = root / "labels.csv"
        split_dir = root / split

        if labels_csv.exists():
            import csv
            with open(labels_csv) as f:
                for row in csv.DictReader(f):
                    p = Path(row["path"])
                    if p.exists():
                        self.samples.append((p, float(row["score"])))
        elif split_dir.exists():
            for class_dir in sorted(split_dir.iterdir()):
                if not class_dir.is_dir():
                    continue
                try:
                    score = float(class_dir.name.replace("activity_", ""))
                except ValueError:
                    logger.warning("skipping_dir_bad_name", dir=class_dir.name)
                    continue
                for img in class_dir.glob("*.jpg"):
                    self.samples.append((img, score))
                for img in class_dir.glob("*.png"):
                    self.samples.append((img, score))
        else:
            raise FileNotFoundError(
                f"No '{split}' subdirectory or labels.csv found in {root}"
            )

        logger.info("dataset_loaded", split=split, samples=len(self.samples))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        path, score = self.samples[idx]
        try:
            import cv2
            img = cv2.imread(str(path))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = cv2.resize(img, (self.img_size, self.img_size))
            arr = img.astype(np.float32) / 255.0
        except ImportError:
            arr = np.zeros((self.img_size, self.img_size, 3), dtype=np.float32)

        tensor = torch.from_numpy(arr).permute(2, 0, 1)  # (C, H, W)
        return tensor, torch.tensor([score], dtype=torch.float32)


# ── Training loop ──────────────────────────────────────────────────────────────

def _evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> dict[str, float]:
    """Compute MSE and MAE on a validation loader."""
    model.eval()
    total_mse = total_mae = 0.0
    with torch.no_grad():
        for X, y in loader:
            pred = model(X.to(device))
            err = pred - y.to(device)
            total_mse += (err ** 2).sum().item()
            total_mae += err.abs().sum().item()
    n = len(loader.dataset)
    return {"val_mse": total_mse / n, "val_mae": total_mae / n}


def train(
    data_dir: str,
    epochs: int = 30,
    lr: float = 1e-4,
    batch_size: int = 32,
    patience: int = 7,
    device_str: str = "cpu",
    mlflow_uri: str = "http://localhost:5000",
    register: bool = False,
    output_dir: str = ".",
) -> None:
    """Fine-tune ResNet18 for feeding activity regression.

    Args:
        data_dir: Root of the dataset directory (contains train/ and val/).
        epochs: Maximum training epochs.
        lr: Learning rate for AdamW.
        batch_size: Mini-batch size.
        patience: Early stopping patience (epochs without val MAE improvement).
        device_str: PyTorch device string.
        mlflow_uri: MLflow tracking server URL.
        register: Register best model to the MLflow model registry.
        output_dir: Directory to save local checkpoint.
    """
    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment(EXPERIMENT_NAME)
    device = torch.device(device_str)
    output_path = Path(output_dir)
    root = Path(data_dir)

    train_ds = FeedingActivityDataset(root, split="train")
    val_ds = FeedingActivityDataset(root, split="val")
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    net = _build_cnn().to(device)
    optimizer = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.MSELoss()

    best_ckpt = output_path / "feeding_best.pt"
    best_mae = float("inf")
    stale = 0

    with mlflow.start_run() as run:
        mlflow.log_params({
            "epochs": epochs,
            "lr": lr,
            "batch_size": batch_size,
            "patience": patience,
            "device": device_str,
            "arch": "resnet18",
            "img_size": _IMG_SIZE,
        })

        for epoch in range(1, epochs + 1):
            net.train()
            train_loss = 0.0
            for X, y in train_loader:
                optimizer.zero_grad()
                loss = criterion(net(X.to(device)), y.to(device))
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item() * len(X)
            train_loss /= len(train_loader.dataset)

            val_metrics = _evaluate(net, val_loader, device)
            scheduler.step()

            mlflow.log_metrics({"train_mse": train_loss, **val_metrics}, step=epoch)

            if val_metrics["val_mae"] < best_mae:
                best_mae = val_metrics["val_mae"]
                stale = 0
                fa_model = FeedingActivityModel(device=device_str)
                fa_model._net = net
                fa_model.is_loaded = True
                fa_model.save_checkpoint(str(best_ckpt), version=f"epoch{epoch}")
                logger.info("new_best_checkpoint", epoch=epoch, val_mae=round(best_mae, 4))
            else:
                stale += 1
                if stale >= patience:
                    logger.info("early_stopping", epoch=epoch, patience=patience)
                    break

            if epoch % 5 == 0:
                logger.info(
                    "epoch",
                    epoch=epoch,
                    train_mse=round(train_loss, 5),
                    **{k: round(v, 5) for k, v in val_metrics.items()},
                )

        mlflow.log_metric("best_val_mae", best_mae)
        logger.info("training_complete", best_val_mae=round(best_mae, 4))

        if best_ckpt.exists():
            mlflow.log_artifact(str(best_ckpt), artifact_path="checkpoint")

        # Load best and log to MLflow
        fa_model = FeedingActivityModel(device=device_str)
        fa_model.load(str(best_ckpt))
        mlflow.pytorch.log_model(
            fa_model.pytorch_model(),
            artifact_path="model",
            registered_model_name=MODEL_NAME if register else None,
        )
        logger.info("model_logged_to_mlflow", run_id=run.info.run_id, registered=register)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train feeding activity regression model")
    parser.add_argument("--data", required=True, help="Root of the dataset directory")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--patience", type=int, default=7)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--mlflow-uri", default="http://localhost:5000")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args()

    train(
        data_dir=args.data,
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        patience=args.patience,
        device_str=args.device,
        mlflow_uri=args.mlflow_uri,
        register=args.register,
        output_dir=args.output_dir,
    )
