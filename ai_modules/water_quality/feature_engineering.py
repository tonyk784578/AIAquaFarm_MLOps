"""Feature engineering for water quality time-series prediction.

Provides:
    FeatureScaler   — per-feature z-score normalisation with save/load
    WindowBuilder   — sliding-window extraction from a DataFrame
    impute_window   — forward-fill + column-default gap filling

Feature columns (N_FEATURES = 8):
    temperature_c, ph, dissolved_oxygen_mgl, turbidity_ntu,
    conductivity_us_cm, feeding_amount_kg_24h, biomass_kg,
    water_exchange_rate_pct

Target columns (N_OUTPUTS = 2):
    ammonia_ppm, nitrite_ppm
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import structlog

from ai_modules.water_quality.model import (
    FEATURE_NAMES,
    N_FEATURES,
    N_OUTPUTS,
    SEQ_LEN,
    TARGET_NAMES,
)

logger = structlog.get_logger()

# Default values used when a feature column is entirely missing or NULL
FEATURE_DEFAULTS: dict[str, float] = {
    "temperature_c": 22.5,
    "ph": 7.2,
    "dissolved_oxygen_mgl": 7.8,
    "turbidity_ntu": 1.5,
    "conductivity_us_cm": 800.0,
    "feeding_amount_kg_24h": 0.0,
    "biomass_kg": 100.0,
    "water_exchange_rate_pct": 5.0,
}


# ── Feature scaler ─────────────────────────────────────────────────────────────

class FeatureScaler:
    """Per-feature z-score normalisation for the WQ prediction model.

    Fitted on training data; the statistics are saved alongside the model
    checkpoint so inference uses the same normalisation.

    Attributes:
        feature_mean: (n_features,) mean of each input feature.
        feature_std:  (n_features,) std of each input feature.
        target_mean:  (n_targets,) mean of each target.
        target_std:   (n_targets,) std of each target.
        is_fitted:    True after fit() is called.
    """

    def __init__(self) -> None:
        self.feature_mean: np.ndarray = np.zeros(N_FEATURES)
        self.feature_std: np.ndarray = np.ones(N_FEATURES)
        self.target_mean: np.ndarray = np.zeros(N_OUTPUTS)
        self.target_std: np.ndarray = np.ones(N_OUTPUTS)
        self.is_fitted: bool = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "FeatureScaler":
        """Compute normalisation statistics from training data.

        Args:
            X: Feature array of shape (N, seq_len, n_features) or (N, n_features).
            y: Target array of shape (N, n_outputs).

        Returns:
            Self for chaining.
        """
        x_flat = X.reshape(-1, X.shape[-1])
        self.feature_mean = x_flat.mean(0)
        self.feature_std = x_flat.std(0) + 1e-8
        self.target_mean = y.mean(0)
        self.target_std = y.std(0) + 1e-8
        self.is_fitted = True
        logger.info(
            "scaler_fitted",
            feature_means=self.feature_mean.round(3).tolist(),
            target_means=self.target_mean.round(4).tolist(),
        )
        return self

    def transform_features(self, X: np.ndarray) -> np.ndarray:
        """Normalise feature array.

        Args:
            X: Shape (..., n_features) — any leading dims are preserved.

        Returns:
            Normalised array of same shape.
        """
        return (X - self.feature_mean) / self.feature_std

    def transform_targets(self, y: np.ndarray) -> np.ndarray:
        """Normalise target array.

        Args:
            y: Shape (..., n_outputs).

        Returns:
            Normalised array.
        """
        return (y - self.target_mean) / self.target_std

    def inverse_transform_targets(self, y_norm: np.ndarray) -> np.ndarray:
        """Denormalise model output back to physical units.

        Args:
            y_norm: Normalised target array (..., n_outputs).

        Returns:
            Physical values in ppm.
        """
        return y_norm * self.target_std + self.target_mean

    def save(self, path: str | Path) -> None:
        """Save statistics to a .npz file.

        Args:
            path: Destination file path (e.g. 'wq_scaler.npz').
        """
        np.savez(
            str(path),
            feature_mean=self.feature_mean,
            feature_std=self.feature_std,
            target_mean=self.target_mean,
            target_std=self.target_std,
        )
        logger.info("scaler_saved", path=str(path))

    @classmethod
    def load(cls, path: str | Path) -> "FeatureScaler":
        """Load statistics from a .npz file.

        Args:
            path: Path to saved scaler file.

        Returns:
            Fitted FeatureScaler instance.
        """
        data = np.load(str(path))
        scaler = cls()
        scaler.feature_mean = data["feature_mean"]
        scaler.feature_std = data["feature_std"]
        scaler.target_mean = data["target_mean"]
        scaler.target_std = data["target_std"]
        scaler.is_fitted = True
        logger.info("scaler_loaded", path=str(path))
        return scaler


# ── Window builder ─────────────────────────────────────────────────────────────

class WindowBuilder:
    """Extracts fixed-length sliding windows from a time-series DataFrame.

    Each window produces one (X, y) sample:
        X = features at timesteps [t-seq_len .. t-1]  shape (seq_len, n_features)
        y = targets at timestep t                      shape (n_outputs,)
    """

    def __init__(
        self,
        seq_len: int = SEQ_LEN,
        feature_cols: list[str] | None = None,
        target_cols: list[str] | None = None,
    ) -> None:
        self.seq_len = seq_len
        self.feature_cols = feature_cols or FEATURE_NAMES
        self.target_cols = target_cols or TARGET_NAMES

    def build_windows(
        self,
        df: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Build all sliding windows from a DataFrame.

        Args:
            df: DataFrame with feature and target columns, sorted by time.
                Missing feature columns are filled with FEATURE_DEFAULTS.
                Missing target rows are dropped.

        Returns:
            Tuple (X, y):
                X: (N, seq_len, n_features) float32 array
                y: (N, n_outputs) float32 array
        """
        df = self._prepare(df)
        feats = df[self.feature_cols].values.astype(np.float32)
        targets = df[self.target_cols].values.astype(np.float32)

        # Drop rows where any target is NaN
        valid_mask = ~np.isnan(targets).any(axis=1)

        n = len(df)
        X_list: list[np.ndarray] = []
        y_list: list[np.ndarray] = []

        for i in range(self.seq_len, n):
            if not valid_mask[i]:
                continue
            X_list.append(feats[i - self.seq_len : i])
            y_list.append(targets[i])

        if not X_list:
            logger.warning("no_windows_built", df_len=n, seq_len=self.seq_len)
            return np.empty((0, self.seq_len, len(self.feature_cols)), dtype=np.float32), \
                   np.empty((0, len(self.target_cols)), dtype=np.float32)

        return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32)

    def build_inference_window(
        self,
        df: pd.DataFrame,
    ) -> np.ndarray:
        """Build a single inference window from the last seq_len rows.

        Args:
            df: DataFrame with at least seq_len rows, sorted by time ascending.
                Must contain feature columns (target columns not needed).

        Returns:
            Feature array of shape (seq_len, n_features).

        Raises:
            ValueError: If df has fewer than seq_len rows.
        """
        if len(df) < self.seq_len:
            raise ValueError(
                f"Need at least {self.seq_len} rows, got {len(df)}"
            )
        df = self._prepare(df)
        return df[self.feature_cols].iloc[-self.seq_len :].values.astype(np.float32)

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add missing feature columns with defaults and fill NaN values."""
        df = df.copy()
        for col in self.feature_cols:
            if col not in df.columns:
                df[col] = FEATURE_DEFAULTS.get(col, 0.0)
            else:
                # Forward-fill, then fill remaining with column default
                df[col] = df[col].ffill().fillna(FEATURE_DEFAULTS.get(col, 0.0))
        return df


# ── Gap imputation ─────────────────────────────────────────────────────────────

def impute_window(
    df: pd.DataFrame,
    expected_freq: str = "1h",
    expected_len: int = SEQ_LEN,
) -> pd.DataFrame:
    """Resample to regular hourly intervals and fill gaps.

    Called on the raw TimescaleDB query result before building the
    inference window. Handles missing hourly buckets due to sensor
    outages or write failures.

    Args:
        df: DataFrame indexed by datetime with feature columns.
        expected_freq: Target frequency string (e.g. '1h').
        expected_len: Desired number of rows after resampling.

    Returns:
        DataFrame reindexed to expected_freq with gaps forward-filled.
    """
    if df.empty:
        return df

    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have a DatetimeIndex for impute_window()")

    # Resample to regular grid, then forward-fill, then backfill
    df_resampled = df.resample(expected_freq).mean()
    df_resampled = df_resampled.ffill().bfill()

    # Apply column defaults for any still-missing values
    for col in df_resampled.columns:
        if col in FEATURE_DEFAULTS:
            df_resampled[col] = df_resampled[col].fillna(FEATURE_DEFAULTS[col])

    # Keep only the last expected_len rows
    if len(df_resampled) > expected_len:
        df_resampled = df_resampled.iloc[-expected_len:]

    return df_resampled
