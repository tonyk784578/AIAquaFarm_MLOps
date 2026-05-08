"""RASbit digital twin — physics-based water quality simulation.

Simulates the nitrification ODE to forecast ammonia (NH3) and nitrite (NO2)
over a configurable horizon given a proposed control action.

ODE model (Euler integration, dt=1h):

    dNH3/dt = loading(t) − k_nit(T) × NH3 − k_exchange × NH3
    dNO2/dt = k_nit(T)  × NH3 − k_nox(T) × NO2  − k_exchange × NO2

where:
    loading(t)   — ammonia excretion spike after each feeding event
    k_nit(T)     — nitrification rate (Arrhenius temperature dependence)
    k_nox(T)     — nitrite oxidation rate
    k_exchange   — dilution from water exchange (exchange_pct / 100)

This is the same model used in scripts/generate_wq_test_data.py but
parameterised to accept current sensor readings as initial conditions.
"""

from __future__ import annotations

import dataclasses
from typing import Any

# ── ODE parameters (calibrated to standard RAS conditions) ────────────────────
_K_NIT_BASE = 0.18      # nitrification rate at 25°C (per hour)
_K_NOX_BASE = 0.30      # nitrite oxidation rate at 25°C (per hour)
_THETA = 1.07           # Arrhenius temperature coefficient
_T_REF = 25.0           # reference temperature (°C)
_FEED_LOADING_PPM = 0.12  # ammonia spike per feeding event (ppm equiv.)


def _k_nit(temp_c: float) -> float:
    return _K_NIT_BASE * _THETA ** (temp_c - _T_REF)


def _k_nox(temp_c: float) -> float:
    return _K_NOX_BASE * _THETA ** (temp_c - _T_REF)


@dataclasses.dataclass
class SimulationResult:
    """Outcome of a single candidate action simulation.

    Attributes:
        action_type: The candidate action evaluated.
        horizon_hours: Number of hours simulated.
        final_ammonia_ppm: Predicted ammonia at end of horizon.
        final_nitrite_ppm: Predicted nitrite at end of horizon.
        peak_ammonia_ppm: Maximum ammonia reached during simulation.
        peak_nitrite_ppm: Maximum nitrite reached during simulation.
        score: Composite safety score (higher = safer).
            score = 1 − (normalised_NH3 + normalised_NO2) / 2
        trajectory: List of (NH3, NO2) tuples per hour.
    """

    action_type: str
    horizon_hours: int
    final_ammonia_ppm: float
    final_nitrite_ppm: float
    peak_ammonia_ppm: float
    peak_nitrite_ppm: float
    score: float
    trajectory: list[tuple[float, float]]


class RASbitSimulator:
    """Physics-based RAS digital twin for candidate action evaluation.

    Usage::

        sim = RASbitSimulator()
        result = sim.simulate(
            action_type="reduce_feeding",
            current_state={"ammonia_ppm": 0.4, "nitrite_ppm": 0.08,
                           "temperature_c": 23.0, "water_exchange_rate_pct": 5.0},
            parameters={"reduction_factor": 0.5},
            horizon_hours=6,
        )
        print(result.score)  # 0.0–1.0
    """

    # Alert thresholds for scoring
    NH3_CRITICAL = 1.0
    NO2_CRITICAL = 0.2
    NH3_TARGET = 0.2   # "good" level
    NO2_TARGET = 0.05

    def simulate(
        self,
        action_type: str,
        current_state: dict[str, Any],
        parameters: dict[str, Any] | None = None,
        horizon_hours: int = 6,
        feedings_per_day: int = 3,
        baseline_daily_feed_kg: float = 2.0,
        biomass_kg: float = 100.0,
    ) -> SimulationResult:
        """Simulate water quality over *horizon_hours* for the given action.

        Args:
            action_type: Proposed control action
                ('no_action', 'stop_feeding', 'reduce_feeding',
                 'increase_aeration', 'water_exchange').
            current_state: Current sensor readings dict
                (needs: ammonia_ppm, nitrite_ppm, temperature_c,
                 optionally water_exchange_rate_pct).
            parameters: Action-specific parameters
                (e.g. {'reduction_factor': 0.5} for reduce_feeding).
            horizon_hours: Simulation horizon in hours.
            feedings_per_day: Number of daily feeding events.
            baseline_daily_feed_kg: Baseline daily feed before adjustment.
            biomass_kg: Current biomass (used to scale loading).

        Returns:
            SimulationResult with trajectory and safety score.
        """
        params = parameters or {}

        # Initial conditions from sensor readings
        nh3 = max(0.0, float(current_state.get("ammonia_ppm", 0.0) or 0.0))
        no2 = max(0.0, float(current_state.get("nitrite_ppm", 0.0) or 0.0))
        temp = float(current_state.get("temperature_c", 23.0) or 23.0)
        base_exchange = float(current_state.get("water_exchange_rate_pct", 5.0) or 5.0)

        # Derive action modifiers
        feed_factor, exchange_boost = self._action_modifiers(
            action_type, params, base_exchange
        )

        daily_feed_kg = baseline_daily_feed_kg * feed_factor
        k_exchange = (base_exchange + exchange_boost) / 100.0

        # Feeding schedule over horizon: feeding if hour_of_day in FEED_HOURS
        feed_hours = {
            int(24 * i / feedings_per_day) for i in range(feedings_per_day)
        }

        trajectory: list[tuple[float, float]] = [(nh3, no2)]
        peak_nh3 = nh3
        peak_no2 = no2

        for h in range(horizon_hours):
            hour_of_day = h % 24
            loading = 0.0
            if feedings_per_day > 0 and hour_of_day in feed_hours:
                # Ammonia excretion fraction of feed eaten
                loading = _FEED_LOADING_PPM * (daily_feed_kg / max(feedings_per_day, 1)) * 0.05

            dnh3 = loading - _k_nit(temp) * nh3 - k_exchange * nh3
            dno2 = _k_nit(temp) * nh3 - _k_nox(temp) * no2 - k_exchange * no2

            nh3 = max(0.0, nh3 + dnh3)
            no2 = max(0.0, no2 + dno2)

            trajectory.append((round(nh3, 4), round(no2, 4)))
            peak_nh3 = max(peak_nh3, nh3)
            peak_no2 = max(peak_no2, no2)

        score = self._score(peak_nh3, peak_no2)

        return SimulationResult(
            action_type=action_type,
            horizon_hours=horizon_hours,
            final_ammonia_ppm=round(nh3, 4),
            final_nitrite_ppm=round(no2, 4),
            peak_ammonia_ppm=round(peak_nh3, 4),
            peak_nitrite_ppm=round(peak_no2, 4),
            score=round(score, 4),
            trajectory=trajectory,
        )

    def _action_modifiers(
        self,
        action_type: str,
        params: dict[str, Any],
        base_exchange: float,
    ) -> tuple[float, float]:
        """Return (feed_factor, exchange_boost_pct) for a given action."""
        match action_type:
            case "stop_feeding":
                return 0.0, 0.0
            case "reduce_feeding":
                factor = float(params.get("reduction_factor", 0.5))
                return max(0.0, min(1.0, factor)), 0.0
            case "water_exchange":
                pct = float(params.get("exchange_pct", 10.0))
                return 1.0, pct
            case "increase_aeration":
                # Aeration improves DO but has minor indirect effect on nitrification;
                # model as slight nitrification boost (already temperature-corrected).
                return 1.0, 0.0
            case _:  # no_action, normal_feeding
                return 1.0, 0.0

    def _score(self, peak_nh3: float, peak_no2: float) -> float:
        """Composite safety score in [0, 1]. Higher is safer."""
        nh3_norm = min(1.0, peak_nh3 / self.NH3_CRITICAL)
        no2_norm = min(1.0, peak_no2 / self.NO2_CRITICAL)
        danger = (nh3_norm + no2_norm) / 2.0
        return max(0.0, 1.0 - danger)


def evaluate_candidates(
    candidates: list[dict[str, Any]],
    current_state: dict[str, Any],
    horizon_hours: int = 6,
) -> list[dict[str, Any]]:
    """Evaluate all candidate actions with the digital twin and rank by score.

    Args:
        candidates: List of candidate action dicts (action_type, parameters, …).
        current_state: Current sensor readings dict.
        horizon_hours: Simulation horizon per candidate.

    Returns:
        Same list enriched with 'simulation' and 'score' keys, sorted best→worst.
    """
    sim = RASbitSimulator()
    enriched: list[dict[str, Any]] = []

    for candidate in candidates:
        result = sim.simulate(
            action_type=candidate.get("action", candidate.get("action_type", "no_action")),
            current_state=current_state,
            parameters=candidate.get("parameters", {}),
            horizon_hours=horizon_hours,
        )
        enriched.append(
            {
                **candidate,
                "simulation": {
                    "final_ammonia_ppm": result.final_ammonia_ppm,
                    "final_nitrite_ppm": result.final_nitrite_ppm,
                    "peak_ammonia_ppm": result.peak_ammonia_ppm,
                    "peak_nitrite_ppm": result.peak_nitrite_ppm,
                    "horizon_hours": result.horizon_hours,
                },
                "score": result.score,
            }
        )

    enriched.sort(key=lambda x: x["score"], reverse=True)
    return enriched
