"""Agent service entry point — FastAPI app + scheduled management cycle.

Runs the management agent on a configurable interval (default: 5 minutes)
and exposes HTTP endpoints for manual trigger and status inspection.

Endpoints:
    POST /run          Manually trigger one management cycle
    GET  /status       Return last cycle report
    GET  /health       Liveness probe
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from agents.config import get_agent_settings
from agents.management_agent.graph import management_graph

logger = structlog.get_logger()
settings = get_agent_settings()

_last_report: dict = {}
_cycle_lock = asyncio.Lock()


async def run_management_cycle() -> dict:
    """Execute one full management agent cycle.

    Returns:
        Final AgentState after the graph completes.
    """
    async with _cycle_lock:
        logger.info("management_cycle_start")
        if management_graph is None:
            logger.error("management_graph_not_available")
            return {"error": "langgraph not installed"}

        initial_state = {
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
        logger.info(
            "management_cycle_complete",
            report=result.get("final_report", ""),
        )
        return result


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
    interval = settings.agent_timeout_seconds  # reuse as cycle interval
    task = asyncio.create_task(_scheduler(interval))
    logger.info("agent_service_started", cycle_interval_s=interval)
    yield
    task.cancel()
    logger.info("agent_service_stopped")


app = FastAPI(
    title="AIAquafarm Agent Service",
    description="LangGraph management agent for RAS farm automation",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/run", summary="Manually trigger management cycle")
async def manual_run() -> JSONResponse:
    """Trigger one management agent cycle immediately."""
    result = await run_management_cycle()
    return JSONResponse(
        content={
            "status": "ok",
            "final_report": result.get("final_report", ""),
            "decisions": len(result.get("control_decisions", [])),
        }
    )


@app.get("/status", summary="Last cycle status")
async def get_status() -> JSONResponse:
    """Return the result of the most recent management cycle."""
    if not _last_report:
        return JSONResponse(content={"status": "no_cycle_run_yet"})
    return JSONResponse(content=_last_report)


@app.get("/health", summary="Liveness probe")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "healthy", "service": "aquafarm-agents"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("agents.main:app", host="0.0.0.0", port=8001, reload=False)
