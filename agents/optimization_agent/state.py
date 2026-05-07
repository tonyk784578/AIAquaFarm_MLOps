"""Optimization agent state definition.

TODO (Phase 3): Add digital twin simulation result fields.
"""

from typing import Any, Optional, TypedDict


class OptimizationInput(TypedDict, total=False):
    """Inputs gathered from the three AI modules."""

    water_quality_prediction: dict[str, Any]
    growth_metrics: dict[str, Any]
    feeding_activity: dict[str, Any]
    tank_id: str


class OptimizationState(TypedDict, total=False):
    """Shared state for the optimization agent subgraph.

    Fields:
        inputs:                 AI module outputs passed from management agent.
        simulation_result:      RASbit digital twin simulation output.
        recommended_actions:    Ranked list of control actions.
        selected_action:        Final chosen action after simulation validation.
        error:                  Error message if optimization fails.
    """

    inputs: OptimizationInput
    simulation_result: Optional[dict[str, Any]]
    recommended_actions: list[dict[str, Any]]
    selected_action: Optional[dict[str, Any]]
    error: Optional[str]
