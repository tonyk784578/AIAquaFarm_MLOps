"""Management agent LangGraph workflow definition.

Graph topology:

    START
      |
      v
    collect_data          <- fetch latest snapshot from backend API
      |
      v
    analyse_situation     <- Claude claude-sonnet-4-6 with tool use; falls back to rule-based
      |
      |-- [action required] --> execute_commands
      |                               |
      |<------------------------------+
      v
    generate_report
      |
      v
     END
"""

from __future__ import annotations

import structlog

from agents.management_agent.nodes import (
    analyse_situation,
    collect_farm_data,
    execute_commands,
    generate_report,
)
from agents.management_agent.state import AgentState

logger = structlog.get_logger()


def _needs_action(state: AgentState) -> str:
    """Route to execute_commands if any non-trivial action was decided."""
    decisions = state.get("control_decisions", [])
    has_action = any(d.get("action_type") != "no_action" for d in decisions)
    return "execute" if has_action else "report"


def build_management_graph():  # type: ignore[return]
    """Build and compile the management agent LangGraph StateGraph.

    Returns:
        Compiled LangGraph graph ready for invocation, or None if
        langgraph is not installed.
    """
    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(AgentState)

        graph.add_node("collect_data", collect_farm_data)
        graph.add_node("analyse_situation", analyse_situation)
        graph.add_node("execute_commands", execute_commands)
        graph.add_node("generate_report", generate_report)

        graph.add_edge(START, "collect_data")
        graph.add_edge("collect_data", "analyse_situation")
        graph.add_conditional_edges(
            "analyse_situation",
            _needs_action,
            {"execute": "execute_commands", "report": "generate_report"},
        )
        graph.add_edge("execute_commands", "generate_report")
        graph.add_edge("generate_report", END)

        compiled = graph.compile()
        logger.info("management_graph_built")
        return compiled

    except ImportError:
        logger.warning("langgraph_not_installed", msg="Install langgraph to use agents")
        return None


management_graph = build_management_graph()
