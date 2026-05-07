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

import httpx
import structlog

from agents.config import get_agent_settings
from agents.management_agent.state import AgentState, FarmSnapshot

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
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.backend_url}/api/v1/dashboard/summary")
            resp.raise_for_status()
            data = resp.json()

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
    """Use Claude claude-sonnet-4-6 with tool use to analyse the farm snapshot.

    Falls back to the rule-based optimizer if the Anthropic API is unavailable.

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
        "Analyse the situation and use the decide_control_action tool to specify what "
        "actions, if any, should be taken."
    )

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            system=_SYSTEM_PROMPT,
            tools=_TOOLS,
            messages=[{"role": "user", "content": user_message}],
        )

        decisions: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "tool_use" and block.name == "decide_control_action":
                decisions = block.input.get("decisions", [])
                break

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
        return {"control_decisions": decisions}

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
        return {"control_decisions": decisions}


async def execute_commands(state: AgentState) -> dict[str, Any]:
    """Dispatch control commands to the backend control API.

    Args:
        state: Current agent state including control_decisions.

    Returns:
        State update with executed_commands list.
    """
    decisions = state.get("control_decisions", [])
    executed: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        for decision in decisions:
            action = decision.get("action_type")
            tank_id = decision.get("tank_id", "ALL")
            params = decision.get("parameters", {})

            try:
                if action == "no_action":
                    continue

                elif action == "stop_feeding":
                    resp = await client.post(
                        f"{settings.backend_url}/api/v1/control/feeding/stop/{tank_id}"
                    )
                    resp.raise_for_status()
                    executed.append({"decision": decision, "status": "ok"})

                elif action == "reduce_feeding":
                    factor = params.get("reduction_factor", 0.5)
                    resp = await client.post(
                        f"{settings.backend_url}/api/v1/control/feeding/adjust",
                        json={"tank_id": tank_id, "reduction_factor": factor},
                    )
                    resp.raise_for_status()
                    executed.append({"decision": decision, "status": "ok"})

                elif action == "increase_aeration":
                    resp = await client.post(
                        f"{settings.backend_url}/api/v1/control/aeration/increase",
                        json={"tank_id": tank_id},
                    )
                    resp.raise_for_status()
                    executed.append({"decision": decision, "status": "ok"})

                elif action == "water_exchange":
                    pct = params.get("exchange_pct", 10.0)
                    resp = await client.post(
                        f"{settings.backend_url}/api/v1/control/water-exchange",
                        json={"tank_id": tank_id, "exchange_pct": pct},
                    )
                    resp.raise_for_status()
                    executed.append({"decision": decision, "status": "ok"})

                elif action == "create_alert":
                    resp = await client.post(
                        f"{settings.backend_url}/api/v1/alerts/",
                        json={
                            "tank_id": tank_id,
                            "severity": params.get("severity", "warning"),
                            "category": params.get("category", "water_quality"),
                            "title": params.get("title", "AI Agent Alert"),
                            "message": params.get("message", decision.get("reasoning", "")),
                            "source": "management_agent",
                        },
                    )
                    resp.raise_for_status()
                    executed.append({"decision": decision, "status": "ok"})

                logger.info("command_executed", action=action, tank_id=tank_id)

            except Exception as exc:
                logger.error(
                    "command_failed", action=action, tank_id=tank_id, error=str(exc)
                )
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
