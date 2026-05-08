"""Optimization agent state definition for LangGraph."""

from typing import Any, Optional, TypedDict


class OptimizationInput(TypedDict, total=False):
    """Inputs gathered from the three AI modules."""

    water_quality_prediction: dict[str, Any]
    growth_metrics: dict[str, Any]
    feeding_activity: dict[str, Any]
    tank_id: str


class SimulationSummary(TypedDict, total=False):
    """Summary of digital twin simulation results."""

    status: str
    candidates_evaluated: int
    best_action: str
    best_score: float
    forecast: dict[str, Any]


class OptimizationState(TypedDict, total=False):
    """Shared state for the optimization agent subgraph.

    Fields:
        inputs:                 Latest AI module outputs (from gather_module_outputs).
        recommended_actions:    Candidate actions from Claude, enriched with simulation scores.
        simulation_result:      Summary of digital twin evaluation.
        selected_action:        Best candidate chosen by select_optimal.
        error:                  Error message if optimization fails.
    """

    inputs: OptimizationInput
    recommended_actions: list[dict[str, Any]]
    simulation_result: Optional[SimulationSummary]
    selected_action: Optional[dict[str, Any]]
    error: Optional[str]
