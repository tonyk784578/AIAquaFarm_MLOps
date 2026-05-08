"""Agent service entry point — FastAPI app + scheduled management cycle.

Runs the management agent on a configurable interval and exposes HTTP
endpoints for manual triggering, status inspection, and optimization.

Endpoints:
    POST /run              Manually trigger one management cycle
    POST /optimize         Run optimization subgraph for a specific tank
    GET  /status           Last management cycle report
    GET  /health           Liveness probe
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agents.config import get_agent_settings
from agents.management_agent.graph import management_graph

logger = structlog.get_logger()
settings = get_agent_settings()

_last_report: dict[str, Any] = {}
_last_optimization: dict[str, Any] = {}
_cycle_lock = asyncio.Lock()
_opt_lock = asyncio.Lock()


# ── Management cycle ───────────────────────────────────────────────────────────

async def run_management_cycle() -> dict[str, Any]:
    """Execute one full management agent cycle.

    Returns:
        Final AgentState after the LangGraph workflow completes.
    """
    async with _cycle_lock:
        logger.info("management_cycle_start")
        if management_graph is None:
            logger.error("management_graph_not_available")
            return {"error": "langgraph not installed"}

        initial_state: dict[str, Any] = {
            "farm_snapshot": {},
            "control_decisions": [],
            "executed_commands": [],
            "iteration_count": 0,
        }
        result = await management_graph.ainvoke(initial_state)
        _last_report.update(
            {
                "ran_at": datetime.now(timezone.utc).isoformat(),
                "final_report": result.get("final_report", ""),
                "decisions": result.get("control_decisions", []),
                "executed": result.get("executed_commands", []),
                "error": result.get("error"),
            }
        )
        logger.info("management_cycle_complete", report=result.get("final_report", ""))
        return result


# ── Optimization cycle ─────────────────────────────────────────────────────────

async def run_optimization(tank_id: str, current_state: dict[str, Any]) -> dict[str, Any]:
    """Execute the optimization agent subgraph for a specific tank.

    Args:
        tank_id: Target tank identifier.
        current_state: Current sensor readings for the digital twin.

    Returns:
        Final OptimizationState with selected_action and simulation_result.
    """
    async with _opt_lock:
        from agents.optimization_agent.graph import optimization_graph

        if optimization_graph is None:
            return {"error": "optimization graph not available"}

        initial: dict[str, Any] = {
            "inputs": {
                "tank_id": tank_id,
                "water_quality_prediction": current_state,
                "growth_metrics": {},
                "feeding_activity": {},
            }
        }
        result = await optimization_graph.ainvoke(initial)
        _last_optimization.update(
            {
                "ran_at": datetime.now(timezone.utc).isoformat(),
                "tank_id": tank_id,
                "selected_action": result.get("selected_action"),
                "simulation_result": result.get("simulation_result"),
                "candidates": len(result.get("recommended_actions", [])),
            }
        )
        logger.info(
            "optimization_cycle_complete",
            tank_id=tank_id,
            action=result.get("selected_action", {}).get("action"),
        )
        return result


# ── Scheduler ──────────────────────────────────────────────────────────────────

async def _scheduler(interval_seconds: int) -> None:
    """Run the management cycle at a fixed interval."""
    logger.info("scheduler_started", interval_seconds=interval_seconds)
    while True:
        try:
            await run_management_cycle()
        except Exception as exc:
            logger.error("management_cycle_error", error=str(exc))
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    interval = settings.agent_timeout_seconds
    task = asyncio.create_task(_scheduler(interval))
    logger.info("agent_service_started", cycle_interval_s=interval)
    yield
    task.cancel()
    logger.info("agent_service_stopped")


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AIAquafarm Agent Service",
    description=(
        "LangGraph multi-agent orchestration for RAS farm automation.\n\n"
        "- Management agent: full farm cycle (data collection → analysis → commands → report)\n"
        "- Optimization agent: digital twin candidate evaluation for a specific tank"
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/run", summary="Manually trigger management cycle")
async def manual_run() -> JSONResponse:
    """Trigger one complete management agent cycle immediately."""
    result = await run_management_cycle()
    return JSONResponse(
        content={
            "status": "ok",
            "final_report": result.get("final_report", ""),
            "decisions": len(result.get("control_decisions", [])),
            "executed": len(result.get("executed_commands", [])),
        }
    )


class OptimizeRequest(BaseModel):
    tank_id: str = Field(..., description="Target tank identifier")
    ammonia_ppm: float = Field(default=0.0, ge=0.0)
    nitrite_ppm: float = Field(default=0.0, ge=0.0)
    dissolved_oxygen_mgl: float = Field(default=7.0, ge=0.0)
    temperature_c: float = Field(default=23.0)
    water_exchange_rate_pct: float = Field(default=5.0, ge=0.0, le=100.0)


@app.post("/optimize", summary="Run optimization subgraph for a tank")
async def optimize_tank(body: OptimizeRequest) -> JSONResponse:
    """Run the optimization pipeline for a specific tank.

    Executes: gather → generate candidates (Claude) → digital twin simulation → select best.

    Returns the selected action and simulation forecast summary.
    """
    try:
        current_state = {
            "tank_id": body.tank_id,
            "ammonia_ppm": body.ammonia_ppm,
            "nitrite_ppm": body.nitrite_ppm,
            "dissolved_oxygen_mgl": body.dissolved_oxygen_mgl,
            "temperature_c": body.temperature_c,
            "water_exchange_rate_pct": body.water_exchange_rate_pct,
        }
        result = await run_optimization(body.tank_id, current_state)
        return JSONResponse(
            content={
                "status": "ok",
                "tank_id": body.tank_id,
                "selected_action": result.get("selected_action"),
                "simulation_result": result.get("simulation_result"),
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Optimization failed: {exc}",
        )


@app.get("/status", summary="Last cycle status")
async def get_status() -> JSONResponse:
    """Return the result of the most recent management cycle."""
    if not _last_report:
        return JSONResponse(content={"status": "no_cycle_run_yet"})
    return JSONResponse(content=_last_report)


@app.get("/optimization/status", summary="Last optimization result")
async def get_optimization_status() -> JSONResponse:
    """Return the result of the most recent optimization run."""
    if not _last_optimization:
        return JSONResponse(content={"status": "no_optimization_run_yet"})
    return JSONResponse(content=_last_optimization)


@app.get("/health", summary="Liveness probe")
async def health() -> JSONResponse:
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "aquafarm-agents",
            "management_graph": management_graph is not None,
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agents.main:app", host="0.0.0.0", port=8001, reload=False)
