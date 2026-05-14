"""LSTM and Transformer models for water quality prediction.

Two architectures:
    LSTMWaterQualityModel:        2-layer LSTM with MC-Dropout
    TransformerWaterQualityModel: Lightweight Transformer encoder

Both predict [ammonia_ppm, nitrite_ppm] from a normalised
(seq_len, n_features) time-series window.

MC-Dropout (Gal & Ghahramani, 2016) provides calibrated 95% confidence
intervals by running N stochastic forward passes at inference time.
"""

from __future__ import annotations

import dataclasses
from typing import Literal

import numpy as np
import structlog
import torch
import torch.nn as nn

logger = structlog.get_logger()

# ── Feature / target constants ─────────────────────────────────────────────────
FEATURE_NAMES: list[str] = [
    "temperature_c",
    "ph",
    "dissolved_oxygen_mgl",
    "turbidity_ntu",
    "conductivity_us_cm",
    "feeding_amount_kg_24h",
    "biomass_kg",
    "water_exchange_rate_pct",
]
TARGET_NAMES: list[str] = ["ammonia_ppm", "nitrite_ppm"]
N_FEATURES: int = len(FEATURE_NAMES)   # 8
N_OUTPUTS: int = len(TARGET_NAMES)     # 2
SEQ_LEN: int = 24                      # 24-hour lookback window


# ── Model configuration ────────────────────────────────────────────────────────

@dataclasses.dataclass
class WQModelConfig:
    """Hyperparameters for WQ prediction models.

    Both LSTM and Transformer share seq_len / n_features / n_outputs.
    Architecture-specific params are used only by the respective model.
    """

    arch: Literal["lstm", "transformer"] = "lstm"
    seq_len: int = SEQ_LEN
    n_features: int = N_FEATURES
    n_outputs: int = N_OUTPUTS
    # LSTM
    hidden_size: int = 128
    num_layers: int = 2
    dropout: float = 0.3
    # Transformer
    d_model: int = 64
    nhead: int = 4
    num_encoder_layers: int = 2
    dim_feedforward: int = 256
    # MC-Dropout inference
    mc_samples: int = 50


# ── Positional encoding ────────────────────────────────────────────────────────

class _PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding (Vaswani et al., 2017)."""

    def __init__(self, d_model: int, max_len: int = 128) -> None:
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(max_len).unsqueeze(1).float()
        div = torch.exp(
            torch.arange(0, d_model, 2).float() * -(np.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div[: d_model // 2])
        self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, : x.size(1)]  # type: ignore[index]


# ── PyTorch model definitions ──────────────────────────────────────────────────

class LSTMWaterQualityModel(nn.Module):
    """Two-layer LSTM with MC-Dropout for uncertainty quantification.

    Architecture::

        LSTM(n_features → hidden_size, num_layers, dropout)
          └─ last hidden state (batch, hidden_size)
             └─ Dropout(dropout)
                └─ FC(hidden_size → 64) → ReLU
                   └─ FC(64 → n_outputs)  [ammonia, nitrite]
    """

    def __init__(self, cfg: WQModelConfig) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=cfg.n_features,
            hidden_size=cfg.hidden_size,
            num_layers=cfg.num_layers,
            batch_first=True,
            dropout=cfg.dropout if cfg.num_layers > 1 else 0.0,
        )
        self.dropout = nn.Dropout(cfg.dropout)
        self.head = nn.Sequential(
            nn.Linear(cfg.hidden_size, 64),
            nn.ReLU(),
            nn.Linear(64, cfg.n_outputs),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input tensor (batch, seq_len, n_features).

        Returns:
            Output tensor (batch, n_outputs).
        """
        out, _ = self.lstm(x)           # (batch, seq_len, hidden_size)
        out = self.dropout(out[:, -1])  # last timestep
        return self.head(out)


class TransformerWaterQualityModel(nn.Module):
    """Lightweight Transformer encoder for water quality prediction.

    Architecture::

        Linear(n_features → d_model)
          └─ PositionalEncoding
             └─ TransformerEncoder(nhead, num_layers, dim_ff, dropout)
                └─ last timestep (batch, d_model)
                   └─ Dropout
                      └─ FC(d_model → n_outputs)
    """

    def __init__(self, cfg: WQModelConfig) -> None:
        super().__init__()
        self.input_proj = nn.Linear(cfg.n_features, cfg.d_model)
        self.pos_enc = _PositionalEncoding(cfg.d_model, max_len=cfg.seq_len + 8)
        enc_layer = nn.TransformerEncoderLayer(
            d_model=cfg.d_model,
            nhead=cfg.nhead,
            dim_feedforward=cfg.dim_feedforward,
            dropout=cfg.dropout,
            batch_first=True,
            norm_first=True,  # Pre-LN: more stable training
        )
        self.transformer = nn.TransformerEncoder(enc_layer, cfg.num_encoder_layers)
        self.dropout = nn.Dropout(cfg.dropout)
        self.head = nn.Linear(cfg.d_model, cfg.n_outputs)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input tensor (batch, seq_len, n_features).

        Returns:
            Output tensor (batch, n_outputs).
        """
        x = self.input_proj(x)          # (batch, seq_len, d_model)
        x = self.pos_enc(x)
        x = self.transformer(x)         # (batch, seq_len, d_model)
        x = self.dropout(x[:, -1])      # last timestep
        return self.head(x)


def build_model(cfg: WQModelConfig) -> nn.Module:
    """Factory: construct a model from config.

    Args:
        cfg: Model configuration.

    Returns:
        Untrained PyTorch model.

    Raises:
        ValueError: If cfg.arch is not recognised.
    """
    match cfg.arch:
        case "lstm":
            return LSTMWaterQualityModel(cfg)
        case "transformer":
            return TransformerWaterQualityModel(cfg)
        case _:
            raise ValueError(f"Unknown architecture: {cfg.arch!r}")


# ── High-level inference wrapper ───────────────────────────────────────────────

class WaterQualityPredictionModel:
    """High-level wrapper providing MC-Dropout inference with uncertainty.

    Handles model construction, checkpoint loading, MLflow loading,
    and stochastic inference.

    Usage (inference)::

        model = WaterQualityPredictionModel()
        model.load_from_checkpoint("wq_model.pt")
        result = model.predict(normalised_sequence)   # (seq_len, n_features)

    Usage (training)::

        model = WaterQualityPredictionModel(cfg).build()
        torch_model = model.pytorch_model()
        # ... training loop ...
        model.save_checkpoint("wq_model.pt", version="v1.0")
    """

    def __init__(
        self,
        cfg: WQModelConfig | None = None,
        device: str = "cpu",
    ) -> None:
        self.cfg = cfg or WQModelConfig()
        self.device = torch.device(device)
        self._model: nn.Module | None = None
        self.model_version: str = "not_loaded"
        self.is_loaded: bool = False

    # ── Construction / loading ─────────────────────────────────────────────────

    def build(self) -> "WaterQualityPredictionModel":
        """Construct model from config. Returns self for chaining."""
        self._model = build_model(self.cfg).to(self.device)
        self.is_loaded = True
        return self

    def pytorch_model(self) -> nn.Module:
        """Return raw PyTorch model (needed for training loop)."""
        if self._model is None:
            raise RuntimeError("Model not built — call build() first")
        return self._model

    def load_from_checkpoint(self, path: str) -> None:
        """Load weights from a .pt checkpoint produced by save_checkpoint().

        Args:
            path: Path to checkpoint file.
        """
        ckpt = torch.load(path, map_location=self.device, weights_only=True)
        if "config" in ckpt:
            self.cfg = WQModelConfig(**ckpt["config"])
        self._model = build_model(self.cfg).to(self.device)
        self._model.load_state_dict(ckpt["model_state_dict"])
        self._model.eval()
        self.model_version = ckpt.get("version", "unknown")
        self.is_loaded = True
        logger.info("checkpoint_loaded", path=path, version=self.model_version)

    def load_from_mlflow(self, model_uri: str) -> None:
        """Load from MLflow artifact (saved with mlflow.pytorch.log_model).

        Args:
            model_uri: MLflow URI e.g. 'models:/WaterQualityPredictor/Production'.
        """
        try:
            import mlflow.pytorch

            self._model = mlflow.pytorch.load_model(
                model_uri, map_location=self.device
            )
            self._model.eval()
            self.model_version = model_uri.rsplit("/", 1)[-1]
            self.is_loaded = True
            logger.info("mlflow_model_loaded", uri=model_uri)
        except Exception as exc:
            logger.error("mlflow_load_failed", uri=model_uri, error=str(exc))
            raise

    def save_checkpoint(self, path: str, version: str = "dev") -> None:
        """Save model weights and config to a .pt checkpoint.

        Args:
            path: Output file path.
            version: Version string embedded in checkpoint.
        """
        if self._model is None:
            raise RuntimeError("No model to save")
        torch.save(
            {
                "model_state_dict": self._model.state_dict(),
                "config": dataclasses.asdict(self.cfg),
                "version": version,
            },
            path,
        )
        logger.info("checkpoint_saved", path=path, version=version)

    # ── Inference ──────────────────────────────────────────────────────────────

    @torch.no_grad()
    def predict(
        self,
        sequence: np.ndarray,
        mc_samples: int | None = None,
    ) -> dict[str, float]:
        """Predict ammonia and nitrite with MC-Dropout uncertainty.

        Runs N stochastic forward passes (dropout enabled) and returns
        the mean prediction with 95% confidence intervals.

        Args:
            sequence: Normalised feature array of shape (seq_len, n_features).
                      Use FeatureScaler.transform() before calling.
            mc_samples: Number of MC forward passes. Defaults to cfg.mc_samples.

        Returns:
            Dict with keys:
                ammonia_ppm, nitrite_ppm               — point estimates
                ammonia_confidence, nitrite_confidence  — calibrated confidence (0–1)
                ammonia_ci_lower, ammonia_ci_upper      — 95% CI bounds
                nitrite_ci_lower, nitrite_ci_upper      — 95% CI bounds
        """
        if not self.is_loaded or self._model is None:
            return self._empty_prediction()

        x = torch.FloatTensor(sequence).unsqueeze(0).to(self.device)  # (1, seq, feat)
        n = mc_samples if mc_samples is not None else self.cfg.mc_samples

        # MC-Dropout: keep dropout active during inference
        self._model.train()
        samples: list[np.ndarray] = []
        with torch.no_grad():
            for _ in range(n):
                out = self._model(x)
                samples.append(out.cpu().numpy()[0])
        self._model.eval()

        arr = np.array(samples)       # (n, 2)
        mean = arr.mean(0)            # (2,)
        std = arr.std(0) + 1e-8       # avoid zero division

        ammonia = float(np.clip(mean[0], 0.0, 10.0))
        nitrite = float(np.clip(mean[1], 0.0, 2.0))

        # Confidence: 1 - normalised_std
        # Expected natural variation: ~0.15 ppm NH3, ~0.03 ppm NO2
        ammonia_conf = float(np.clip(1.0 - std[0] / 0.15, 0.0, 1.0))
        nitrite_conf = float(np.clip(1.0 - std[1] / 0.03, 0.0, 1.0))

        return {
            "ammonia_ppm": ammonia,
            "nitrite_ppm": nitrite,
            "ammonia_confidence": round(ammonia_conf, 4),
            "nitrite_confidence": round(nitrite_conf, 4),
            "ammonia_ci_lower": float(np.clip(mean[0] - 1.96 * std[0], 0.0, None)),
            "ammonia_ci_upper": float(mean[0] + 1.96 * std[0]),
            "nitrite_ci_lower": float(np.clip(mean[1] - 1.96 * std[1], 0.0, None)),
            "nitrite_ci_upper": float(mean[1] + 1.96 * std[1]),
        }

    @torch.no_grad()
    def predict_batch(self, sequences: np.ndarray) -> np.ndarray:
        """Deterministic batch inference for training evaluation.

        Args:
            sequences: Array of shape (batch, seq_len, n_features).

        Returns:
            Predictions array of shape (batch, n_outputs).
        """
        if not self.is_loaded or self._model is None:
            return np.zeros((len(sequences), N_OUTPUTS))
        self._model.eval()
        x = torch.FloatTensor(sequences).to(self.device)
        return self._model(x).cpu().numpy()

    def get_version(self) -> str:
        """Return model version string."""
        return self.model_version

    @staticmethod
    def _empty_prediction() -> dict[str, float]:
        return {
            "ammonia_ppm": 0.0,
            "nitrite_ppm": 0.0,
            "ammonia_confidence": 0.0,
            "nitrite_confidence": 0.0,
            "ammonia_ci_lower": 0.0,
            "ammonia_ci_upper": 0.0,
            "nitrite_ci_lower": 0.0,
            "nitrite_ci_upper": 0.0,
        }
