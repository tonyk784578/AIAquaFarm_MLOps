"""Generate synthetic RAS water quality training data via nitrification ODE simulation.

Simulates a recirculating aquaculture system with the following dynamics:

    dNH3/dt = loading(t) - k_nit(T) * NH3
    dNO2/dt = k_nit(T)   * NH3 - k_nox(T) * NO2

where:
    loading(t) — ammonia excretion spikes after each feeding event
    k_nit(T)   — nitrification rate (Arrhenius temperature dependence)
    k_nox(T)   — nitrite oxidation rate

Physical sensor features are generated with realistic diurnal patterns and
Gaussian noise. Produces a CSV ready for mlops/training/train_water.py.

Usage::

    python scripts/generate_wq_test_data.py \\
        --days 30 \\
        --tanks 3 \\
        --output data/wq_training_data.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

# ── Simulation parameters ──────────────────────────────────────────────────────
FEEDINGS_PER_DAY = 3          # morning / noon / evening
FEED_HOURS = [7, 12, 18]      # feeding event hours
FEED_LOADING_PPM = 0.12       # ammonia spike per feeding (ppm equiv.)
K_NIT_BASE = 0.18             # nitrification rate at 25°C (per hour)
K_NOX_BASE = 0.30             # nitrite oxidation rate at 25°C (per hour)
ARRHENIUS_THETA = 1.07        # temperature coefficient (Arrhenius approx)
T_REF = 25.0                  # reference temperature (°C)


# ── Helper functions ───────────────────────────────────────────────────────────

def k_nit(temp_c: float) -> float:
    """Temperature-corrected nitrification rate."""
    return K_NIT_BASE * ARRHENIUS_THETA ** (temp_c - T_REF)


def k_nox(temp_c: float) -> float:
    """Temperature-corrected nitrite oxidation rate."""
    return K_NOX_BASE * ARRHENIUS_THETA ** (temp_c - T_REF)


def generate_tank(
    tank_id: str,
    days: int,
    base_temp: float = 23.0,
    biomass_kg: float = 120.0,
) -> pd.DataFrame:
    """Simulate one tank for the given number of days at hourly resolution.

    Args:
        tank_id: Tank identifier string.
        days: Simulation length in days.
        base_temp: Mean water temperature (°C).
        biomass_kg: Initial biomass; grows ~0.3%/day.

    Returns:
        DataFrame with all feature and target columns, hourly indexed.
    """
    n_hours = days * 24
    timestamps = pd.date_range("2024-01-01", periods=n_hours, freq="h")

    # ── Physical sensor features ───────────────────────────────────────────
    hour_of_day = np.arange(n_hours) % 24

    # Temperature: base + diurnal cycle + noise
    temp = (
        base_temp
        + 1.5 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
        + RNG.normal(0, 0.2, n_hours)
    )

    # DO: inversely correlated with temp + diurnal aeration effects
    do_mg = (
        8.5
        - 0.1 * (temp - T_REF)
        + 0.4 * np.sin(2 * np.pi * (hour_of_day - 10) / 24)
        + RNG.normal(0, 0.15, n_hours)
    ).clip(4.0, 14.0)

    # pH: slight diurnal variation from photosynthesis (algae in sump)
    ph = (
        7.2
        + 0.15 * np.sin(2 * np.pi * (hour_of_day - 14) / 24)
        + RNG.normal(0, 0.05, n_hours)
    ).clip(6.0, 9.0)

    turbidity = np.abs(RNG.normal(1.8, 0.4, n_hours))
    conductivity = RNG.normal(820, 20, n_hours).clip(600, 1200)

    # Feeding pulses
    feeding = np.zeros(n_hours)
    daily_feed_kg = biomass_kg * 0.015  # 1.5% of biomass per day
    for h_idx in range(n_hours):
        if hour_of_day[h_idx] in FEED_HOURS:
            feeding[h_idx] = daily_feed_kg / FEEDINGS_PER_DAY

    # Biomass growth (0.3%/day)
    biomass = np.array([biomass_kg * (1.003 ** (i / 24)) for i in range(n_hours)])

    # Water exchange: fixed 5% ± noise, extra on weekends
    exchange = np.abs(RNG.normal(5.0, 0.5, n_hours))

    # ── ODE integration (Euler, dt=1h) ────────────────────────────────────
    nh3 = np.zeros(n_hours)
    no2 = np.zeros(n_hours)
    nh3_val = RNG.uniform(0.02, 0.08)   # initial condition
    no2_val = RNG.uniform(0.005, 0.02)

    for i in range(n_hours):
        T = temp[i]
        loading = FEED_LOADING_PPM * feeding[i] / max(daily_feed_kg / FEEDINGS_PER_DAY, 1e-6) * 0.05

        dnh3 = loading - k_nit(T) * nh3_val - exchange[i] / 100 * nh3_val
        dno2 = k_nit(T) * nh3_val - k_nox(T) * no2_val - exchange[i] / 100 * no2_val

        nh3_val = max(0.0, nh3_val + dnh3)
        no2_val = max(0.0, no2_val + dno2)

        nh3[i] = nh3_val + RNG.normal(0, 0.005)
        no2[i] = no2_val + RNG.normal(0, 0.002)

    nh3 = np.clip(nh3, 0.0, 5.0)
    no2 = np.clip(no2, 0.0, 1.0)

    return pd.DataFrame({
        "tank_id": tank_id,
        "timestamp": timestamps,
        "temperature_c": temp.round(3),
        "ph": ph.round(3),
        "dissolved_oxygen_mgl": do_mg.round(3),
        "turbidity_ntu": turbidity.round(3),
        "conductivity_us_cm": conductivity.round(1),
        "feeding_amount_kg_24h": (feeding * 24 / FEEDINGS_PER_DAY).round(3),
        "biomass_kg": biomass.round(2),
        "water_exchange_rate_pct": exchange.round(2),
        "ammonia_ppm": nh3.round(4),
        "nitrite_ppm": no2.round(4),
    })


def generate(days: int, n_tanks: int, output: str) -> None:
    """Generate data for multiple tanks and write to CSV.

    Args:
        days: Simulation days per tank.
        n_tanks: Number of tanks to simulate.
        output: Output CSV file path.
    """
    tanks = []
    base_temps = [22.0, 24.0, 23.5, 21.0, 25.0]
    biomasses = [100.0, 150.0, 80.0, 200.0, 120.0]

    for i in range(n_tanks):
        tank_id = f"TANK-{i+1:02d}"
        df = generate_tank(
            tank_id=tank_id,
            days=days,
            base_temp=base_temps[i % len(base_temps)],
            biomass_kg=biomasses[i % len(biomasses)],
        )
        tanks.append(df)
        print(f"  {tank_id}: {len(df):,} rows  "
              f"NH3 mean={df.ammonia_ppm.mean():.3f}  "
              f"NO2 mean={df.nitrite_ppm.mean():.3f}")

    combined = pd.concat(tanks, ignore_index=True)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False)
    print(f"\nSaved {len(combined):,} rows to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate synthetic RAS water quality training data"
    )
    parser.add_argument("--days", type=int, default=30, help="Simulation days per tank")
    parser.add_argument("--tanks", type=int, default=3, help="Number of tanks")
    parser.add_argument("--output", default="data/wq_training_data.csv", help="Output CSV path")
    args = parser.parse_args()

    print(f"Simulating {args.tanks} tank(s) × {args.days} days…")
    generate(days=args.days, n_tanks=args.tanks, output=args.output)
