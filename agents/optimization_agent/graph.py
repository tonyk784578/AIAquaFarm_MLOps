"""Optimization agent LangGraph subgraph.

Graph topology (Phase 3 target):

    START
      │
      ▼
    gather_module_outputs   ← collect water quality, growth, feeding AI results
      │
      ▼
    generate_candidates     ← LLM proposes candidate control actions
      │
      ▼
    simulate_in_twin        ← RASbit digital twin validates candidates
      │
      ▼
    select_optimal          ← pick best action by simulated outcome
      │
      ▼
    END

TODO (Phase 3): Implement all nodes.
TODO (Phase 3): Wire digital twin HTTP client in simulate_in_twin node.
"""

import structlog

from agents.optimization_agent.nodes import (
    gather_module_outputs,
    generate_candidates,
    select_optimal,
    simulate_in_twin,
)
from agents.optimization_agent.state import OptimizationState

logger = structlog.get_logger()


def build_optimization_graph():  # type: ignore[return]
    """Build and compile the optimization agent subgraph.

    Returns:
        Compiled LangGraph graph.

    TODO (Phase 3): Replace stub with full implementation.
    """
    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(OptimizationState)

        graph.add_node("gather_module_outputs", gather_module_outputs)
        graph.add_node("generate_candidates", generate_candidates)
        graph.add_node("simulate_in_twin", simulate_in_twin)
        graph.add_node("select_optimal", select_optimal)

        graph.add_edge(START, "gather_module_outputs")
        graph.add_edge("gather_module_outputs", "generate_candidates")
        graph.add_edge("generate_candidates", "simulate_in_twin")
        graph.add_edge("simulate_in_twin", "select_optimal")
        graph.add_edge("select_optimal", END)

        return graph.compile()
    except ImportError:
        logger.warning("langgraph_not_installed")
        return None


optimization_graph = build_optimization_graph()
