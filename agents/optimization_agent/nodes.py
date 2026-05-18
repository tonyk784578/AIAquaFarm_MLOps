"""Optimization agent node functions.

Pipeline:
    gather_module_outputs → generate_candidates → simulate_in_twin → select_optimal

gather_module_outputs  — fetch latest AI module results from backend endpoints
generate_candidates    — Claude proposes ranked candidate control actions
simulate_in_twin       — RASbit ODE simulator scores each candidate (6h forecast)
select_optimal         — pick best scoring candidate; report if safe
"""

from __future__ import annotations

from typing import Any

import structlog

from agents.config import get_agent_settings
from agents.optimization_agent.state import OptimizationState
from agents.optimization_agent.twin_sim import evaluate_candidates
from agents.runtime.http import AgentHTTPClient
from agents.runtime.llm import LLMClient

logger = structlog.get_logger()
settings = get_agent_settings()

# ── Candidate generation prompt ────────────────────────────────────────────────

_CANDIDATE_SYSTEM = """You are a RAS (Recirculating Aquaculture System) optimization AI.
Given current AI module outputs, propose up to 5 candidate control actions.
Each candidate must include: action, parameters, reasoning, and an initial_score (0.0-1.0).

Available actions:
  no_action       — maintain current regime
  stop_feeding    — immediately halt feeder
  reduce_feeding  — parameters: {reduction_factor: 0.0-1.0}
  increase_aeration
  water_exchange  — parameters: {exchange_pct: float}
  create_alert    — parameters: {severity, category, title, message}

Respond ONLY with valid JSON array of candidate objects. No markdown. No explanation outside JSON."""

_CANDIDATE_TOOL = {
    "name": "submit_candidates",
    "description": "Submit ranked candidate control actions for digital twin evaluation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "parameters": {"type": "object"},
                        "reasoning": {"type": "string"},
                        "initial_score": {"type": "number"},
                    },
                    "required": ["action", "reasoning"],
                },
            }
        },
        "required": ["candidates"],
    },
}

# ── Default candidate set (used as LLM fallback) ───────────────────────────────

def _default_candidates(wq: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate rule-based candidate set when LLM is unavailable."""
    from agents.optimization_agent.optimizer import RuleBasedOptimizer
    result = RuleBasedOptimizer().evaluate(
        water_quality=wq, growth={}, feeding={}
    )
    return [
        {"action": result.action_type, "parameters": result.parameters,
         "reasoning": f"[rule-based] {result.reasoning}", "initial_score": result.urgency},
        {"action": "no_action", "parameters": {},
         "reasoning": "Baseline — no intervention", "initial_score": 0.5},
    ]


# ── Nodes ──────────────────────────────────────────────────────────────────────

async def gather_module_outputs(state: OptimizationState) -> dict[str, Any]:
    """Fetch the latest outputs from all three AI module endpoints.

    Calls:
        GET  /api/v1/monitoring/water-quality/latest?tank_id=…
        GET  /api/v1/growth/count/{tank_id}
        GET  /api/v1/feeding/status

    Populates state['inputs'] with water_quality_prediction, growth_metrics,
    feeding_activity, and tank_id.
    """
    existing = state.get("inputs", {})
    tank_id: str = existing.get("tank_id", "ALL")

    logger.info("gathering_ai_module_outputs", tank_id=tank_id)

    wq: dict[str, Any] = existing.get("water_quality_prediction", {})
    growth: dict[str, Any] = existing.get("growth_metrics", {})
    feeding: dict[str, Any] = existing.get("feeding_activity", {})

    async with AgentHTTPClient() as client:
        # Water quality
        wq_data = await client.safe_get_json(
            "/api/v1/monitoring/water-quality/latest", tank_id=tank_id, limit=1
        )
        if isinstance(wq_data, list) and wq_data:
            wq = wq_data[0]
        elif isinstance(wq_data, dict) and wq_data:
            wq = wq_data

        # Growth count
        growth_data = await client.safe_get_json(f"/api/v1/growth/count/{tank_id}")
        if isinstance(growth_data, dict) and growth_data:
            growth = growth_data

        # Feeding status
        feeding_data = await client.safe_get_json("/api/v1/feeding/status")
        if isinstance(feeding_data, dict) and feeding_data:
            feeding = feeding_data

    logger.info(
        "module_outputs_gathered",
        has_wq=bool(wq),
        has_growth=bool(growth),
        has_feeding=bool(feeding),
    )
    return {
        "inputs": {
            "tank_id": tank_id,
            "water_quality_prediction": wq,
            "growth_metrics": growth,
            "feeding_activity": feeding,
        }
    }


async def generate_candidates(state: OptimizationState) -> dict[str, Any]:
    """Use Claude to propose ranked candidate control actions.

    Falls back to the rule-based optimizer if the Anthropic API is unavailable.
    Returns up to 5 candidates for digital twin evaluation.
    """
    if state.get("error"):
        return {"recommended_actions": []}

    inputs = state.get("inputs", {})
    wq = inputs.get("water_quality_prediction", {})
    growth = inputs.get("growth_metrics", {})
    feeding = inputs.get("feeding_activity", {})
    tank_id = inputs.get("tank_id", "ALL")

    user_message = (
        f"Tank: {tank_id}\n\n"
        "Water Quality (AI virtual sensor):\n"
        f"  ammonia_ppm      = {wq.get('ammonia_ppm', 'N/A')}\n"
        f"  nitrite_ppm      = {wq.get('nitrite_ppm', 'N/A')}\n"
        f"  dissolved_oxygen = {wq.get('dissolved_oxygen_mgl', 'N/A')} mg/L\n"
        f"  temperature_c    = {wq.get('temperature_c', 'N/A')}\n"
        f"  ph               = {wq.get('ph', 'N/A')}\n\n"
        "Growth Metrics:\n"
        f"  fish_count  = {growth.get('fish_count', 'N/A')}\n"
        f"  biomass_kg  = {growth.get('biomass_kg', 'N/A')}\n\n"
        "Feeding Activity:\n"
        f"  activity_score = {feeding.get('activity_score', 'N/A')}\n"
        f"  satiation      = {feeding.get('satiation_detected', 'N/A')}\n\n"
        "Propose up to 5 candidate control actions. Use the submit_candidates tool."
    )

    try:
        llm = LLMClient(max_tokens=2048, temperature=0.2, timeout_s=settings.llm_timeout_seconds)
        response = await llm.messages(
            system=_CANDIDATE_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
            tools=[_CANDIDATE_TOOL],
        )

        candidates = (
            LLMClient.extract_tool_input(response, "submit_candidates") or {}
        ).get("candidates", [])

        if not candidates:
            candidates = _default_candidates(wq)

        logger.info(
            "candidates_generated",
            model=settings.llm_model,
            count=len(candidates),
            actions=[c.get("action") for c in candidates],
        )
        return {"recommended_actions": candidates}

    except Exception as exc:
        logger.warning("llm_candidate_generation_failed", error=str(exc))
        return {"recommended_actions": _default_candidates(wq)}


async def simulate_in_twin(state: OptimizationState) -> dict[str, Any]:
    """Run each candidate through the RASbit digital twin ODE simulator.

    Evaluates a 6-hour forecast for each candidate and enriches each with
    'simulation' and 'score' fields. The candidates list is returned sorted
    best → worst by score.
    """
    candidates = state.get("recommended_actions", [])
    if not candidates:
        return {"simulation_result": {"status": "no_candidates"}}

    inputs = state.get("inputs", {})
    current_state = inputs.get("water_quality_prediction", {})

    logger.info("running_digital_twin_simulation", candidates=len(candidates))

    ranked = evaluate_candidates(
        candidates=candidates,
        current_state=current_state,
        horizon_hours=6,
    )

    logger.info(
        "simulation_complete",
        best_action=ranked[0].get("action") if ranked else "none",
        best_score=ranked[0].get("score") if ranked else 0.0,
    )

    return {
        "recommended_actions": ranked,
        "simulation_result": {
            "status": "ok",
            "candidates_evaluated": len(ranked),
            "best_action": ranked[0].get("action") if ranked else "none",
            "best_score": ranked[0].get("score") if ranked else 0.0,
        },
    }


async def select_optimal(state: OptimizationState) -> dict[str, Any]:
    """Select the highest-scoring candidate from the simulation results.

    Applies a minimum score threshold (0.3) — if no candidate exceeds it,
    defaults to a create_alert action to notify the operator.
    """
    candidates = state.get("recommended_actions", [])

    MIN_SAFE_SCORE = 0.3

    if not candidates:
        selected = {
            "action": "no_action",
            "parameters": {},
            "reasoning": "No candidates generated",
            "score": 0.0,
        }
    else:
        best = candidates[0]  # already sorted best→worst by simulate_in_twin
        if best.get("score", 0.0) < MIN_SAFE_SCORE:
            selected = {
                "action": "create_alert",
                "parameters": {
                    "severity": "critical",
                    "category": "water_quality",
                    "title": "All control options predict poor water quality",
                    "message": (
                        f"Best candidate '{best.get('action')}' scored only "
                        f"{best.get('score', 0):.2f}. Manual intervention required."
                    ),
                },
                "reasoning": "Score below safety threshold — alerting operator",
                "score": best.get("score", 0.0),
            }
        else:
            selected = best

    logger.info(
        "optimal_action_selected",
        action=selected.get("action"),
        score=selected.get("score"),
        reasoning=selected.get("reasoning", "")[:80],
    )
    return {"selected_action": selected}
