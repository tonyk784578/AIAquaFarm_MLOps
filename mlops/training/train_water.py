"""Training pipeline for the water quality LSTM/Transformer prediction model.

Trains on a CSV produced by scripts/generate_wq_test_data.py (or real data),
registers the best checkpoint to MLflow, and saves a companion FeatureScaler.

Usage::

    python -m mlops.training.train_water \\
        --data path/to/wq_data.csv \\
        --arch lstm \\
        --epochs 100 \\
        --lr 3e-4 \\
        --hidden-size 128 \\
        --batch-size 64 \\
        --register                # push to MLflow registry as WaterQualityPredictor
"""

from __future__ import annotations

import argparse
from pathlib import Path

import mlflow
import mlflow.pytorch
import numpy as np
import pandas as pd
import structlog
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from ai_modules.water_quality.feature_engineering import FeatureScaler, WindowBuilder
from ai_modules.water_quality.model import (
    SEQ_LEN,
    WQModelConfig,
    WaterQualityPredictionModel,
    build_model,
)

logger = structlog.get_logger()

EXPERIMENT_NAME = "water-quality-prediction"
MODEL_NAME = "WaterQualityPredictor"


# ── Data loading ───────────────────────────────────────────────────────────────

def load_dataset(
    path: str,
    seq_len: int = SEQ_LEN,
    val_frac: float = 0.15,
    test_frac: float = 0.10,
) -> tuple[
    tuple[np.ndarray, np.ndarray],
    tuple[np.ndarray, np.ndarray],
    tuple[np.ndarray, np.ndarray],
    FeatureScaler,
]:
    """Load CSV, build sliding windows, fit scaler, split into train/val/test.

    Args:
        path: CSV path; must contain all FEATURE_NAMES + TARGET_NAMES columns
              and a ``timestamp`` column sorted ascending per ``tank_id``.
        seq_len: Lookback window size.
        val_frac: Validation fraction.
        test_frac: Test fraction.

    Returns:
        Tuple of (train, val, test) as (X, y) pairs, plus the fitted FeatureScaler.
    """
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values(["tank_id", "timestamp"]).reset_index(drop=True)

    builder = WindowBuilder(seq_len=seq_len)
    all_X: list[np.ndarray] = []
    all_y: list[np.ndarray] = []

    for _, tank_df in df.groupby("tank_id"):
        X_tank, y_tank = builder.build_windows(tank_df)
        all_X.append(X_tank)
        all_y.append(y_tank)

    X = np.concatenate(all_X, axis=0)
    y = np.concatenate(all_y, axis=0)
    logger.info("dataset_loaded", total_samples=len(X), seq_len=seq_len)

    # Chronological split (no shuffle — time series)
    n = len(X)
    n_test = max(1, int(n * test_frac))
    n_val = max(1, int(n * val_frac))
    n_train = n - n_val - n_test

    X_train, y_train = X[:n_train], y[:n_train]
    X_val, y_val = X[n_train : n_train + n_val], y[n_train : n_train + n_val]
    X_test, y_test = X[n_train + n_val :], y[n_train + n_val :]

    scaler = FeatureScaler().fit(X_train, y_train)

    X_train = scaler.transform_features(X_train)
    X_val = scaler.transform_features(X_val)
    X_test = scaler.transform_features(X_test)
    y_train = scaler.transform_targets(y_train)
    y_val = scaler.transform_targets(y_val)
    y_test = scaler.transform_targets(y_test)

    logger.info(
        "split_done",
        train=n_train,
        val=len(X_val),
        test=len(X_test),
    )
    return (X_train, y_train), (X_val, y_val), (X_test, y_test), scaler


def make_loaders(
    train: tuple[np.ndarray, np.ndarray],
    val: tuple[np.ndarray, np.ndarray],
    batch_size: int,
) -> tuple[DataLoader, DataLoader]:
    """Wrap numpy arrays into PyTorch DataLoaders."""

    def _to_loader(X: np.ndarray, y: np.ndarray, shuffle: bool) -> DataLoader:
        ds = TensorDataset(
            torch.FloatTensor(X),
            torch.FloatTensor(y),
        )
        return DataLoader(ds, batch_size=batch_size, shuffle=shuffle, drop_last=False)

    return _to_loader(*train, shuffle=True), _to_loader(*val, shuffle=False)


# ── Training loop ──────────────────────────────────────────────────────────────

def evaluate(model: nn.Module, loader: DataLoader, criterion: nn.Module, device: torch.device) -> float:
    model.eval()
    total_loss = 0.0
    with torch.no_grad():
        for X_b, y_b in loader:
            out = model(X_b.to(device))
            total_loss += criterion(out, y_b.to(device)).item() * len(X_b)
    return total_loss / len(loader.dataset)


def train(
    data_path: str,
    arch: str = "lstm",
    epochs: int = 100,
    lr: float = 3e-4,
    hidden_size: int = 128,
    batch_size: int = 64,
    dropout: float = 0.3,
    patience: int = 10,
    device_str: str = "cpu",
    mlflow_uri: str = "http://localhost:5000",
    register: bool = False,
    output_dir: str = ".",
) -> None:
    """Full training loop with MLflow tracking and optional model registration.

    Args:
        data_path: Path to CSV training data.
        arch: Model architecture (``lstm`` or ``transformer``).
        epochs: Maximum training epochs.
        lr: Initial learning rate for AdamW.
        hidden_size: LSTM hidden size (or Transformer d_model).
        batch_size: Mini-batch size.
        dropout: Dropout probability.
        patience: Early stopping patience (epochs without val improvement).
        device_str: PyTorch device string.
        mlflow_uri: MLflow tracking server URL.
        register: Whether to register best model to MLflow registry.
        output_dir: Directory to save checkpoint and scaler artefacts.
    """
    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment(EXPERIMENT_NAME)
    device = torch.device(device_str)

    (X_train, y_train), (X_val, y_val), (X_test, y_test), scaler = load_dataset(data_path)
    train_loader, val_loader = make_loaders((X_train, y_train), (X_val, y_val), batch_size)

    cfg = WQModelConfig(
        arch=arch,
        hidden_size=hidden_size,
        dropout=dropout,
        d_model=hidden_size // 2,
    )
    net = build_model(cfg).to(device)
    optimizer = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.MSELoss()

    output_path = Path(output_dir)
    best_ckpt = output_path / "wq_best.pt"
    scaler_path = output_path / "wq_scaler.npz"

    with mlflow.start_run() as run:
        mlflow.log_params({
            "arch": arch,
            "epochs": epochs,
            "lr": lr,
            "hidden_size": hidden_size,
            "batch_size": batch_size,
            "dropout": dropout,
            "patience": patience,
            "seq_len": SEQ_LEN,
            "n_features": cfg.n_features,
            "n_outputs": cfg.n_outputs,
        })

        best_val_loss = float("inf")
        stale = 0

        for epoch in range(1, epochs + 1):
            net.train()
            train_loss = 0.0
            for X_b, y_b in train_loader:
                optimizer.zero_grad()
                loss = criterion(net(X_b.to(device)), y_b.to(device))
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item() * len(X_b)
            train_loss /= len(train_loader.dataset)

            val_loss = evaluate(net, val_loader, criterion, device)
            scheduler.step()

            mlflow.log_metrics({"train_loss": train_loss, "val_loss": val_loss}, step=epoch)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                stale = 0
                wq_model = WaterQualityPredictionModel(cfg=cfg, device=device_str)
                wq_model._model = net
                wq_model.is_loaded = True
                wq_model.save_checkpoint(str(best_ckpt), version=f"epoch{epoch}")
                logger.info("new_best_checkpoint", epoch=epoch, val_loss=round(val_loss, 6))
            else:
                stale += 1
                if stale >= patience:
                    logger.info("early_stopping", epoch=epoch, patience=patience)
                    break

            if epoch % 10 == 0:
                logger.info("epoch", epoch=epoch, train_loss=round(train_loss, 6), val_loss=round(val_loss, 6))

        # Evaluate on test set
        test_loader = DataLoader(
            TensorDataset(torch.FloatTensor(X_test), torch.FloatTensor(y_test)),
            batch_size=batch_size,
        )
        test_loss = evaluate(net, test_loader, criterion, device)
        mlflow.log_metric("test_loss", test_loss)
        logger.info("training_complete", best_val_loss=round(best_val_loss, 6), test_loss=round(test_loss, 6))

        # Save scaler and log artefacts
        scaler.save(str(scaler_path))
        mlflow.log_artifact(str(best_ckpt), artifact_path="checkpoint")
        mlflow.log_artifact(str(scaler_path), artifact_path="")

        # Log model to MLflow
        wq_model.load_from_checkpoint(str(best_ckpt))
        mlflow.pytorch.log_model(
            wq_model.pytorch_model(),
            artifact_path="model",
            registered_model_name=MODEL_NAME if register else None,
        )
        logger.info("model_logged_to_mlflow", run_id=run.info.run_id, registered=register)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train water quality prediction model")
    parser.add_argument("--data", required=True, help="Path to training CSV")
    parser.add_argument("--arch", default="lstm", choices=["lstm", "transformer"])
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--mlflow-uri", default="http://localhost:5000")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args()

    train(
        data_path=args.data,
        arch=args.arch,
        epochs=args.epochs,
        lr=args.lr,
        hidden_size=args.hidden_size,
        batch_size=args.batch_size,
        dropout=args.dropout,
        patience=args.patience,
        device_str=args.device,
        mlflow_uri=args.mlflow_uri,
        register=args.register,
        output_dir=args.output_dir,
    )
