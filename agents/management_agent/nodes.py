"""Management agent node functions for the LangGraph workflow.

Each function receives the current AgentState, performs its work,
and returns a dict of state keys to update.

analyse_situation uses Claude claude-sonnet-4-6 with tool use to:
  - Interpret the farm snapshot
  - Decide on control actions (feeding adjustment, aeration, alerts)
  - Return structured ControlDecision list
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from agents.config import get_agent_settings
from agents.management_agent.state import AgentState, FarmSnapshot
from agents.runtime.http import AgentHTTPClient
from agents.runtime.llm import LLMClient, LLMUnavailableError

logger = structlog.get_logger()
settings = get_agent_settings()

# ── System prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an expert RAS (Recirculating Aquaculture System) farm management AI.

Your job is to analyse the current state of an indoor fish farm and decide on control actions.

## Water quality thresholds
| Parameter         | Warning          | Critical         |
|-------------------|------------------|------------------|
| Ammonia (NH3)     | >= 0.5 ppm       | >= 1.0 ppm       |
| Nitrite (NO2)     | >= 0.1 ppm       | >= 0.2 ppm       |
| Dissolved O2      | <= 6.0 mg/L      | <= 5.0 mg/L      |
| pH                | <6.5 or >8.5     | <6.0 or >9.0     |
| Temperature       | <18C or >28C     | <15C or >30C     |

## Control actions available
- no_action: All parameters normal, continue current regime
- stop_feeding: Immediately stop automatic feeder (critical ammonia/nitrite)
- reduce_feeding: Reduce feed amount by a percentage
- increase_aeration: Boost aeration pump speed (low dissolved oxygen)
- water_exchange: Trigger partial water exchange
- create_alert: Create an alert notification for the farm operator

Always explain your reasoning. Return confidence scores (0.0-1.0) for each decision."""

# ── Tool schemas for Claude tool use ──────────────────────────────────────────

_TOOLS = [
    {
        "name": "decide_control_action",
        "description": "Submit control decisions based on the farm snapshot analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "decisions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action_type": {
                                "type": "string",
                                "enum": [
                                    "no_action",
                                    "stop_feeding",
                                    "reduce_feeding",
                                    "increase_aeration",
                                    "water_exchange",
                                    "create_alert",
                                ],
                            },
                            "tank_id": {"type": "string"},
                            "parameters": {
                                "type": "object",
                                "description": "Action-specific parameters",
                            },
                            "reasoning": {"type": "string"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                            },
                        },
                        "required": ["action_type", "tank_id", "reasoning", "confidence"],
                    },
                }
            },
            "required": ["decisions"],
        },
    }
]


async def collect_farm_data(state: AgentState) -> dict[str, Any]:
    """Fetch the latest snapshot from the backend API.

    Args:
        state: Current agent state.

    Returns:
        State update with populated farm_snapshot.
    """
    logger.info("collecting_farm_data")
    try:
        async with AgentHTTPClient() as client:
            data = await client.get_json("/api/v1/dashboard/summary")

        snapshot: FarmSnapshot = {
            "water_quality": data.get("water_quality") or {},
            "fish_growth": data.get("fish_growth") or {},
            "feeding": {},
            "active_alerts": data.get("recent_alerts") or [],
        }
        return {
            "farm_snapshot": snapshot,
            "iteration_count": state.get("iteration_count", 0) + 1,
            "error": None,
        }
    except Exception as exc:
        logger.error("collect_farm_data_failed", error=str(exc))
        return {"error": f"Data collection failed: {exc}"}


async def analyse_situation(state: AgentState) -> dict[str, Any]:
    """Analyse the farm snapshot via optimization subgraph + Claude tool use.

    1. Runs the optimization agent subgraph (gather → candidates → twin sim → select).
    2. If a non-trivial action is recommended, passes it to Claude for final
       validation and supplementary decisions (e.g. additional alerts).
    3. Falls back to the rule-based optimizer if both LLM and subgraph fail.

    Args:
        state: Current agent state including farm_snapshot.

    Returns:
        State update with control_decisions list.
    """
    if state.get("error"):
        logger.warning("skipping_analysis_due_to_error", error=state["error"])
        return {"control_decisions": []}

    snapshot = state.get("farm_snapshot", {})
    wq = snapshot.get("water_quality", {})
    growth = snapshot.get("fish_growth", {})
    alerts = snapshot.get("active_alerts", [])

    # ── Step 1: Run optimization subgraph ─────────────────────────────────────
    opt_decision: dict[str, Any] = {}
    twin_result: dict[str, Any] | None = None
    try:
        from agents.optimization_agent.graph import optimization_graph
        if optimization_graph is not None:
            tank_id = wq.get("tank_id", "ALL")
            opt_state = {
                "inputs": {
                    "tank_id": tank_id,
                    "water_quality_prediction": wq,
                    "growth_metrics": growth,
                    "feeding_activity": snapshot.get("feeding", {}),
                }
            }
            opt_result = await optimization_graph.ainvoke(opt_state)
            opt_decision = opt_result.get("selected_action") or {}
            # Persist full twin simulation results for observability
            twin_result = {
                "selected_action": opt_decision,
                "candidates": opt_result.get("candidates", []),
                "simulation_scores": opt_result.get("simulation_scores", []),
            }
            logger.info(
                "optimization_subgraph_result",
                action=opt_decision.get("action"),
                score=opt_decision.get("score"),
            )
    except Exception as exc:
        logger.warning("optimization_subgraph_failed", error=str(exc))

    user_message = (
        "Current farm status snapshot:\n\n"
        "**Water Quality**\n"
        f"- Ammonia: {wq.get('ammonia_ppm', 'N/A')} ppm"
        f" (confidence: {wq.get('ammonia_confidence', 'N/A')})\n"
        f"- Nitrite: {wq.get('nitrite_ppm', 'N/A')} ppm"
        f" (confidence: {wq.get('nitrite_confidence', 'N/A')})\n"
        f"- Dissolved O2: {wq.get('dissolved_oxygen_mgl', 'N/A')} mg/L\n"
        f"- Temperature: {wq.get('temperature_c', 'N/A')} C\n"
        f"- pH: {wq.get('ph', 'N/A')}\n"
        f"- Tank: {wq.get('tank_id', 'unknown')}\n\n"
        "**Fish Growth**\n"
        f"- Biomass: {growth.get('biomass_kg', 'N/A')} kg\n"
        f"- Daily growth rate: {growth.get('daily_growth_rate_pct', 'N/A')} %\n"
        f"- FCR: {growth.get('feed_conversion_ratio', 'N/A')}\n\n"
        f"**Active Alerts**: {len(alerts)} alert(s)\n"
        f"{json.dumps(alerts[:2], indent=2, ensure_ascii=False) if alerts else 'None'}\n\n"
        + (
            f"**Optimization Agent Recommendation**: {opt_decision.get('action', 'none')} "
            f"(digital twin score: {opt_decision.get('score', 'N/A')})\n"
            f"Reasoning: {opt_decision.get('reasoning', '')}\n\n"
            if opt_decision else ""
        )
        + "Analyse the situation and use the decide_control_action tool to specify what "
        "actions, if any, should be taken. Consider the optimization agent's recommendation."
    )

    # ── Step 2: Build message history for the LLM call ────────────────────────
    history: list[dict[str, Any]] = list(state.get("message_history") or [])
    history.append({"role": "user", "content": user_message})

    try:
        llm = LLMClient(timeout_s=settings.llm_timeout_seconds)
        response = await llm.messages(
            system=_SYSTEM_PROMPT,
            messages=history,
            tools=_TOOLS,
        )

        # Persist assistant turn so future cycles can reference prior reasoning
        history.append({"role": "assistant", "content": LLMClient.dump_content(response)})

        decisions = (LLMClient.extract_tool_input(response, "decide_control_action") or {}).get(
            "decisions", []
        )

        if not decisions:
            decisions = [{
                "action_type": "no_action",
                "tank_id": wq.get("tank_id", "ALL"),
                "parameters": {},
                "reasoning": "All parameters within normal range — no action required",
                "confidence": 1.0,
            }]

        logger.info(
            "analysis_complete",
            model=settings.llm_model,
            decisions=len(decisions),
            actions=[d["action_type"] for d in decisions],
        )
        return {
            "control_decisions": decisions,
            "message_history": history,
            "twin_result": twin_result,
        }

    except Exception as exc:
        logger.warning("llm_analysis_failed_using_rule_fallback", error=str(exc))
        from agents.optimization_agent.optimizer import RuleBasedOptimizer

        optimizer = RuleBasedOptimizer()
        result = optimizer.evaluate(
            water_quality=wq,
            growth=growth,
            feeding=snapshot.get("feeding", {}),
        )
        decisions = [{
            "action_type": result.action_type,
            "tank_id": wq.get("tank_id", "ALL"),
            "parameters": result.parameters,
            "reasoning": f"[rule-based fallback] {result.reasoning}",
            "confidence": result.urgency,
        }]
        return {
            "control_decisions": decisions,
            "message_history": history,
            "twin_result": twin_result,
        }


async def execute_commands(state: AgentState) -> dict[str, Any]:
    """Dispatch control commands to the backend control API.

    Args:
        state: Current agent state including control_decisions.

    Returns:
        State update with executed_commands list.
    """
    decisions = state.get("control_decisions", [])
    executed: list[dict[str, Any]] = []

    async with AgentHTTPClient() as client:
        for decision in decisions:
            action = decision.get("action_type")
            tank_id = decision.get("tank_id", "ALL")
            params = decision.get("parameters", {})

            try:
                if action == "no_action":
                    continue

                elif action == "stop_feeding":
                    await client.post_json(f"/api/v1/control/feeding/stop/{tank_id}")
                    executed.append({"decision": decision, "status": "ok"})

                elif action == "reduce_feeding":
                    await client.post_json(
                        "/api/v1/control/feeding/adjust",
                        {"tank_id": tank_id, "reduction_factor": params.get("reduction_factor", 0.5)},
                    )
                    executed.append({"decision": decision, "status": "ok"})

                elif action == "increase_aeration":
                    await client.post_json(
                        "/api/v1/control/aeration/increase",
                        {"tank_id": tank_id, "boost_pct": params.get("boost_pct", 30.0)},
                    )
                    executed.append({"decision": decision, "status": "ok"})

                elif action == "water_exchange":
                    await client.post_json(
                        "/api/v1/control/water-exchange",
                        {"tank_id": tank_id, "exchange_pct": params.get("exchange_pct", 10.0)},
                    )
                    executed.append({"decision": decision, "status": "ok"})

                elif action == "create_alert":
                    await client.post_json(
                        "/api/v1/alerts/",
                        {
                            "tank_id": tank_id,
                            "severity": params.get("severity", "warning"),
                            "category": params.get("category", "water_quality"),
                            "title": params.get("title", "AI Agent Alert"),
                            "message": params.get("message", decision.get("reasoning", "")),
                            "source": "management_agent",
                        },
                    )
                    executed.append({"decision": decision, "status": "ok"})

                logger.info("command_executed", action=action, tank_id=tank_id)

            except Exception as exc:
                logger.error("command_failed", action=action, tank_id=tank_id, error=str(exc))
                executed.append({"decision": decision, "status": "error", "error": str(exc)})

    return {"executed_commands": executed}


async def generate_report(state: AgentState) -> dict[str, Any]:
    """Produce a structured farm status report.

    Args:
        state: Full agent state after all processing.

    Returns:
        State update with final_report string.
    """
    decisions = state.get("control_decisions", [])
    executed = state.get("executed_commands", [])
    error = state.get("error")

    action_summary = ", ".join(
        f"{d['action_type']}({d.get('tank_id', '')})"
        for d in decisions
        if d.get("action_type") != "no_action"
    ) or "no_action"

    non_trivial = len([d for d in decisions if d.get("action_type") != "no_action"])
    report_parts = [
        f"Management cycle #{state.get('iteration_count', 0)} complete.",
        f"Actions taken: {action_summary}.",
        f"Commands executed: {len(executed)} / {non_trivial}.",
    ]
    if error:
        report_parts.append(f"Warning: {error}")

    report = " ".join(report_parts)
    logger.info("report_generated", report=report)
    return {"final_report": report}
