"""Data drift detection for AIAquafarm AI models.

Computes Population Stability Index (PSI) and KL-divergence between a
reference (training) distribution and a current (production) distribution.
Used by AutoMLPipeline to decide whether to trigger emergency retraining
even when sample count thresholds have not been met.

PSI thresholds (industry standard):
    PSI < 0.10  → no significant drift (stable)
    PSI < 0.20  → moderate drift (monitor)
    PSI ≥ 0.20  → significant drift → trigger retraining

Usage::

    from mlops.evaluation.drift_detector import DriftDetector
    detector = DriftDetector()
    result = detector.check_water_quality(reference_csv="data/wq_train.csv",
                                          current_csv="data/wq_live.csv")
    if result.should_retrain:
        pipeline.trigger_retraining("WaterQualityPredictor")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()

# ── PSI constants ──────────────────────────────────────────────────────────────
PSI_STABLE = 0.10
PSI_WARNING = 0.20  # ≥ this triggers retraining

N_BINS = 10
EPS = 1e-8  # prevent log(0)

# Features monitored per model
_WQ_FEATURES = [
    "temperature_c", "ph", "dissolved_oxygen_mgl", "turbidity_ntu",
    "ammonia_ppm", "nitrite_ppm",
]
_FEEDING_FEATURES = ["activity_score"]
_GROWTH_FEATURES = ["fish_count", "avg_length_cm", "avg_weight_g"]


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class FeatureDriftResult:
    """PSI and KL-divergence for a single feature."""
    feature: str
    psi: float
    kl_divergence: float
    status: str  # 'stable' | 'warning' | 'drift'


@dataclass
class DriftReport:
    """Aggregated drift report for one model's input distribution.

    Attributes:
        model_name: Registered model name.
        max_psi: Worst-case PSI across all monitored features.
        mean_psi: Mean PSI.
        should_retrain: True when max_psi ≥ PSI_WARNING.
        features: Per-feature FeatureDriftResult list.
        n_reference: Number of reference samples.
        n_current: Number of current samples.
    """
    model_name: str
    max_psi: float
    mean_psi: float
    should_retrain: bool
    features: list[FeatureDriftResult] = field(default_factory=list)
    n_reference: int = 0
    n_current: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "max_psi": round(self.max_psi, 4),
            "mean_psi": round(self.mean_psi, 4),
            "should_retrain": self.should_retrain,
            "n_reference": self.n_reference,
            "n_current": self.n_current,
            "features": [
                {
                    "feature": f.feature,
                    "psi": round(f.psi, 4),
                    "kl_divergence": round(f.kl_divergence, 4),
                    "status": f.status,
                }
                for f in self.features
            ],
        }


# ── Core statistics ────────────────────────────────────────────────────────────

def _bin_proportions(
    reference: np.ndarray,
    current: np.ndarray,
    n_bins: int = N_BINS,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute per-bin proportions for reference and current arrays.

    Bins are defined by reference quantiles so they contain roughly equal
    counts from the reference distribution.

    Returns:
        Tuple of (ref_proportions, cur_proportions), each of length n_bins.
    """
    quantiles = np.linspace(0, 100, n_bins + 1)
    bin_edges = np.percentile(reference, quantiles)
    # Ensure edges are strictly monotone (degenerate features → single value)
    bin_edges = np.unique(bin_edges)
    if len(bin_edges) < 2:
        return np.array([1.0]), np.array([1.0])

    ref_counts = np.histogram(reference, bins=bin_edges)[0].astype(float)
    cur_counts = np.histogram(current, bins=bin_edges)[0].astype(float)

    ref_props = (ref_counts + EPS) / (ref_counts.sum() + EPS * len(ref_counts))
    cur_props = (cur_counts + EPS) / (cur_counts.sum() + EPS * len(cur_counts))
    return ref_props, cur_props


def compute_psi(reference: np.ndarray, current: np.ndarray) -> float:
    """Population Stability Index between two 1-D distributions.

    PSI = Σ (cur - ref) × ln(cur / ref)

    Args:
        reference: Reference (training) sample array.
        current: Current (production) sample array.

    Returns:
        PSI value ≥ 0.
    """
    ref_p, cur_p = _bin_proportions(reference, current)
    psi = float(np.sum((cur_p - ref_p) * np.log(cur_p / ref_p + EPS)))
    return max(0.0, psi)


def compute_kl(reference: np.ndarray, current: np.ndarray) -> float:
    """KL-divergence D_KL(current || reference) between two 1-D distributions.

    Args:
        reference: Reference distribution.
        current: Current distribution.

    Returns:
        KL-divergence value ≥ 0.
    """
    ref_p, cur_p = _bin_proportions(reference, current)
    kl = float(np.sum(cur_p * np.log(cur_p / ref_p + EPS)))
    return max(0.0, kl)


def _psi_status(psi: float) -> str:
    if psi < PSI_STABLE:
        return "stable"
    if psi < PSI_WARNING:
        return "warning"
    return "drift"


# ── DriftDetector ──────────────────────────────────────────────────────────────

class DriftDetector:
    """Computes feature-level drift between reference and current data.

    Typical usage in AutoMLPipeline:
        - reference: the CSV used for the last training run.
        - current: a window of recent production inference inputs.
    """

    def _check_features(
        self,
        model_name: str,
        reference_df: Any,   # pd.DataFrame
        current_df: Any,     # pd.DataFrame
        features: list[str],
    ) -> DriftReport:
        """Compare distributions for each feature and build a DriftReport."""
        results: list[FeatureDriftResult] = []

        for feat in features:
            if feat not in reference_df.columns or feat not in current_df.columns:
                logger.warning("feature_missing_skip", model=model_name, feature=feat)
                continue

            ref_arr = reference_df[feat].dropna().to_numpy(dtype=float)
            cur_arr = current_df[feat].dropna().to_numpy(dtype=float)

            if len(ref_arr) < 10 or len(cur_arr) < 10:
                logger.warning("too_few_samples", feature=feat, ref=len(ref_arr), cur=len(cur_arr))
                continue

            psi = compute_psi(ref_arr, cur_arr)
            kl = compute_kl(ref_arr, cur_arr)
            results.append(FeatureDriftResult(
                feature=feat,
                psi=psi,
                kl_divergence=kl,
                status=_psi_status(psi),
            ))

        if not results:
            return DriftReport(
                model_name=model_name,
                max_psi=0.0,
                mean_psi=0.0,
                should_retrain=False,
                features=[],
                n_reference=len(reference_df),
                n_current=len(current_df),
            )

        psi_values = [r.psi for r in results]
        max_psi = max(psi_values)
        mean_psi = float(np.mean(psi_values))
        should_retrain = max_psi >= PSI_WARNING

        report = DriftReport(
            model_name=model_name,
            max_psi=max_psi,
            mean_psi=mean_psi,
            should_retrain=should_retrain,
            features=results,
            n_reference=len(reference_df),
            n_current=len(current_df),
        )
        logger.info(
            "drift_check_complete",
            model=model_name,
            max_psi=round(max_psi, 4),
            should_retrain=should_retrain,
        )
        return report

    def check_water_quality(
        self,
        reference_csv: str | Path,
        current_csv: str | Path,
    ) -> DriftReport:
        """Check input drift for WaterQualityPredictor.

        Args:
            reference_csv: Path to training CSV (same format as generate_wq_test_data.py).
            current_csv: Path to recent production sensor CSV.

        Returns:
            DriftReport with per-feature PSI values.
        """
        import pandas as pd
        ref = pd.read_csv(reference_csv)
        cur = pd.read_csv(current_csv)
        return self._check_features("WaterQualityPredictor", ref, cur, _WQ_FEATURES)

    def check_feeding(
        self,
        reference_csv: str | Path,
        current_csv: str | Path,
    ) -> DriftReport:
        """Check score distribution drift for FeedingActivityClassifier.

        Compares the distribution of predicted activity_score values between
        the training label distribution and recent inference outputs.

        Args:
            reference_csv: Training labels.csv (path, score columns).
            current_csv: Recent inference outputs CSV (same columns).

        Returns:
            DriftReport.
        """
        import pandas as pd
        ref = pd.read_csv(reference_csv)
        cur = pd.read_csv(current_csv)
        return self._check_features("FeedingActivityClassifier", ref, cur, _FEEDING_FEATURES)

    def check_growth(
        self,
        reference_csv: str | Path,
        current_csv: str | Path,
    ) -> DriftReport:
        """Check population-level growth metric drift for FishDetection.

        Args:
            reference_csv: Historical growth records CSV.
            current_csv: Recent inference output CSV.

        Returns:
            DriftReport.
        """
        import pandas as pd
        ref = pd.read_csv(reference_csv)
        cur = pd.read_csv(current_csv)
        return self._check_features("FishDetection", ref, cur, _GROWTH_FEATURES)

    def check_all(
        self,
        wq_reference: str | None = None,
        wq_current: str | None = None,
        feeding_reference: str | None = None,
        feeding_current: str | None = None,
        growth_reference: str | None = None,
        growth_current: str | None = None,
    ) -> dict[str, Any]:
        """Run drift detection for all available model pairs.

        Returns:
            Dict with per-model DriftReport dicts and an overall summary.
        """
        reports: dict[str, Any] = {}

        if wq_reference and wq_current:
            reports["WaterQualityPredictor"] = self.check_water_quality(
                wq_reference, wq_current
            ).to_dict()

        if feeding_reference and feeding_current:
            reports["FeedingActivityClassifier"] = self.check_feeding(
                feeding_reference, feeding_current
            ).to_dict()

        if growth_reference and growth_current:
            reports["FishDetection"] = self.check_growth(
                growth_reference, growth_current
            ).to_dict()

        n_drift = sum(1 for r in reports.values() if r.get("should_retrain"))
        summary = {
            "models_checked": len(reports),
            "drift_detected": n_drift,
            "psi_warning_threshold": PSI_WARNING,
        }
        return {"reports": reports, "summary": summary}
