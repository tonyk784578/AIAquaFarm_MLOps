"""Management agent state definition for LangGraph.

The AgentState TypedDict is the shared memory that flows through
every node in the management agent graph. All nodes read from and
write to this state object.
"""

from typing import Any, Optional, TypedDict


class FarmSnapshot(TypedDict, total=False):
    """Point-in-time snapshot of all AI module outputs."""

    water_quality: dict[str, Any]
    fish_growth: dict[str, Any]
    feeding: dict[str, Any]
    active_alerts: list[dict[str, Any]]


class ControlDecision(TypedDict, total=False):
    """Control decision produced by the optimization agent."""

    action_type: str  # 'feed' | 'adjust_pump' | 'alert' | 'no_action'
    tank_id: str
    parameters: dict[str, Any]
    reasoning: str
    confidence: float


class AgentState(TypedDict, total=False):
    """Shared state for the management agent LangGraph workflow.

    Fields:
        farm_snapshot:      Latest data from all AI modules.
        control_decisions:  List of decisions produced by optimization agent.
        executed_commands:  Record of commands dispatched to edge devices.
        error:              Error message if any node fails.
        iteration_count:    Guard against infinite loops.
        final_report:       Human-readable summary for the dashboard.
        message_history:    Accumulated LLM messages for multi-turn reasoning.
                            Each entry is a dict with 'role' and 'content' keys
                            matching the Anthropic Messages API format.
        twin_result:        Output from the digital twin simulation used by the
                            optimization subgraph. Contains per-candidate scores
                            and the selected best action.
    """

    farm_snapshot: FarmSnapshot
    control_decisions: list[ControlDecision]
    executed_commands: list[dict[str, Any]]
    error: Optional[str]
    iteration_count: int
    final_report: str
    message_history: list[dict[str, Any]]
    twin_result: Optional[dict[str, Any]]
