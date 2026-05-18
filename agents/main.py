"""Agent service entry point — FastAPI app + scheduled management cycle.

Runs the management agent on a configurable interval for every tank in
``settings.default_tank_ids`` and exposes HTTP endpoints for manual
triggering, status inspection, history, and live event streaming.

Endpoints:
    POST /run                   Manually trigger one management cycle (service-key)
    POST /optimize              Run optimization subgraph for a specific tank (service-key)
    GET  /status                Last management cycle report
    GET  /optimization/status   Last optimization result (per-tank if ?tank_id=)
    GET  /history               Recent management cycle history
    GET  /history/optimization  Recent optimization history
    GET  /events/stream         Server-Sent Events stream of live agent activity
    GET  /health                Liveness probe
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agents.config import get_agent_settings
from agents.management_agent.graph import management_graph
from agents.runtime import EventBus, StateStore, require_service_key
from agents.runtime.event_bus import EVENT_CHANNEL

logger = structlog.get_logger()
settings = get_agent_settings()


# ── Module-level shared services (initialised in lifespan) ────────────────────

_redis_client: Any = None
_state: StateStore | None = None
_bus: EventBus | None = None

_cycle_lock = asyncio.Lock()
_opt_lock = asyncio.Lock()


def get_state_store() -> StateStore:
    if _state is None:
        raise RuntimeError("State store not initialised — call inside FastAPI lifespan")
    return _state


def get_event_bus() -> EventBus:
    if _bus is None:
        raise RuntimeError("Event bus not initialised — call inside FastAPI lifespan")
    return _bus


# ── Management cycle ──────────────────────────────────────────────────────────


async def run_management_cycle(tank_id: str = "ALL") -> dict[str, Any]:
    """Execute one full management agent cycle for a tank.

    Args:
        tank_id: Tank to focus on. ``ALL`` lets the LLM aggregate across tanks
            (current default for backwards compatibility).

    Returns:
        Final AgentState after the LangGraph workflow completes.
    """
    async with _cycle_lock:
        bus = get_event_bus()
        await bus.publish("cycle_started", tank_id=tank_id, data={})
        logger.info("management_cycle_start", tank_id=tank_id)

        if management_graph is None:
            logger.error("management_graph_not_available")
            return {"error": "langgraph not installed"}

        initial_state: dict[str, Any] = {
            "farm_snapshot": {},
            "control_decisions": [],
            "executed_commands": [],
            "iteration_count": 0,
        }
        try:
            result = await management_graph.ainvoke(initial_state)
        except Exception as exc:
            logger.exception("management_cycle_crashed", tank_id=tank_id)
            await bus.publish("error", tank_id=tank_id, data={"error": str(exc)})
            return {"error": str(exc)}

        record = await get_state_store().save_management_cycle(result)
        await bus.publish(
            "cycle_completed",
            tank_id=tank_id,
            data={
                "final_report": record["final_report"],
                "decisions": len(record["decisions"]),
                "executed": len(record["executed"]),
            },
        )
        logger.info("management_cycle_complete", tank_id=tank_id, report=record["final_report"])
        return result


# ── Optimization cycle ────────────────────────────────────────────────────────


async def run_optimization(tank_id: str, current_state: dict[str, Any]) -> dict[str, Any]:
    """Execute the optimization agent subgraph for a specific tank."""
    async with _opt_lock:
        from agents.optimization_agent.graph import optimization_graph

        bus = get_event_bus()
        await bus.publish("optimization_started", tank_id=tank_id, data={})

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
        try:
            result = await optimization_graph.ainvoke(initial)
        except Exception as exc:
            logger.exception("optimization_cycle_crashed", tank_id=tank_id)
            await bus.publish("error", tank_id=tank_id, data={"error": str(exc)})
            return {"error": str(exc)}

        await get_state_store().save_optimization(tank_id, result)
        await bus.publish(
            "optimization_completed",
            tank_id=tank_id,
            data={
                "selected_action": (result.get("selected_action") or {}).get("action"),
                "score": (result.get("selected_action") or {}).get("score"),
            },
        )
        logger.info(
            "optimization_cycle_complete",
            tank_id=tank_id,
            action=(result.get("selected_action") or {}).get("action"),
        )
        return result


# ── Scheduler ─────────────────────────────────────────────────────────────────


async def _scheduler() -> None:
    """Run cycles for every default tank on the configured interval."""
    interval = settings.cycle_interval_seconds
    tanks = settings.default_tank_ids or ["ALL"]
    logger.info("scheduler_started", interval_seconds=interval, tanks=tanks)

    try:
        while True:
            for tank_id in tanks:
                try:
                    await run_management_cycle(tank_id=tank_id)
                except Exception as exc:
                    logger.error("scheduler_iteration_failed", tank_id=tank_id, error=str(exc))
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("scheduler_cancelled")
        raise


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise Redis state + event bus, start the scheduler task."""
    global _redis_client, _state, _bus

    try:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
        await _redis_client.ping()
        logger.info("redis_connected", url=settings.redis_url)
    except Exception as exc:
        logger.warning("redis_unavailable_degraded", error=str(exc))
        _redis_client = None

    _state = StateStore(_redis_client, history_size=settings.history_size) if _redis_client else _InMemoryStateStore()
    _bus = EventBus(_redis_client)

    task = asyncio.create_task(_scheduler())
    logger.info("agent_service_started", cycle_interval_s=settings.cycle_interval_seconds)
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        if _redis_client is not None:
            try:
                await _redis_client.aclose()
            except Exception:
                pass
        logger.info("agent_service_stopped")


# ── In-memory fallback (when Redis is down) ──────────────────────────────────


class _InMemoryStateStore:
    """Fallback that mirrors StateStore semantics in-process. No persistence."""

    def __init__(self) -> None:
        self._last_mgmt: dict[str, Any] = {}
        self._last_opt: dict[str, dict[str, Any]] = {}
        self._history_mgmt: list[dict[str, Any]] = []
        self._history_opt: list[dict[str, Any]] = []
        self._cap = 50

    async def save_management_cycle(self, result: dict[str, Any]) -> dict[str, Any]:
        from datetime import datetime, timezone

        record = {
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "final_report": result.get("final_report", ""),
            "decisions": result.get("control_decisions", []),
            "executed": result.get("executed_commands", []),
            "iteration_count": result.get("iteration_count", 0),
            "twin_result": result.get("twin_result"),
            "error": result.get("error"),
        }
        self._last_mgmt = record
        self._history_mgmt.insert(0, record)
        self._history_mgmt = self._history_mgmt[: self._cap]
        return record

    async def get_last_management_cycle(self) -> dict[str, Any]:
        return self._last_mgmt

    async def get_management_history(self, n: int = 20) -> list[dict[str, Any]]:
        return self._history_mgmt[:n]

    async def save_optimization(self, tank_id: str, result: dict[str, Any]) -> dict[str, Any]:
        from datetime import datetime, timezone

        record = {
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tank_id": tank_id,
            "selected_action": result.get("selected_action"),
            "simulation_result": result.get("simulation_result"),
            "candidates": len(result.get("recommended_actions", [])),
            "error": result.get("error"),
        }
        self._last_opt[tank_id] = record
        self._history_opt.insert(0, record)
        self._history_opt = self._history_opt[: self._cap]
        return record

    async def get_last_optimization(self, tank_id: str) -> dict[str, Any]:
        return self._last_opt.get(tank_id, {})

    async def get_optimization_history(self, n: int = 20) -> list[dict[str, Any]]:
        return self._history_opt[:n]


# ── FastAPI app ───────────────────────────────────────────────────────────────


def _configure_logging() -> None:
    logging.basicConfig(level=settings.log_level.upper(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


_configure_logging()

app = FastAPI(
    title="AIAquafarm Agent Service",
    description=(
        "LangGraph multi-agent orchestration for RAS farm automation.\n\n"
        "- Management agent: full farm cycle (data collection → analysis → commands → report)\n"
        "- Optimization agent: digital twin candidate evaluation for a specific tank\n"
        "- Live SSE stream at /events/stream"
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# ── Observability (Prometheus metrics + OpenTelemetry tracing) ───────────────
from agents.observability import setup_observability  # noqa: E402

setup_observability(app, service_name="aquafarm-agents")

# ── HTTP hardening — applies to both internal callers and any future ingress ─
from agents.runtime.security import (  # noqa: E402
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)

app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=1 * 1024 * 1024)
app.add_middleware(SecurityHeadersMiddleware)


@app.post(
    "/run",
    summary="Manually trigger management cycle",
    dependencies=[Depends(require_service_key)],
)
async def manual_run(tank_id: str = Query(default="ALL")) -> JSONResponse:
    """Trigger one management agent cycle immediately. Service key required."""
    result = await run_management_cycle(tank_id=tank_id)
    return JSONResponse(
        content={
            "status": "ok",
            "tank_id": tank_id,
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


@app.post(
    "/optimize",
    summary="Run optimization subgraph for a tank",
    dependencies=[Depends(require_service_key)],
)
async def optimize_tank(body: OptimizeRequest) -> JSONResponse:
    """Run gather → candidates → twin sim → select for a specific tank."""
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
    record = await get_state_store().get_last_management_cycle()
    if not record:
        return JSONResponse(content={"status": "no_cycle_run_yet"})
    return JSONResponse(content=record)


@app.get("/optimization/status", summary="Last optimization result")
async def get_optimization_status(tank_id: str = Query(default="")) -> JSONResponse:
    record = await get_state_store().get_last_optimization(tank_id) if tank_id else {}
    if not record:
        # Try the most-recent across tanks
        history = await get_state_store().get_optimization_history(n=1)
        if history:
            return JSONResponse(content=history[0])
        return JSONResponse(content={"status": "no_optimization_run_yet"})
    return JSONResponse(content=record)


@app.get("/history", summary="Recent management cycle history")
async def get_history(n: int = Query(default=20, ge=1, le=200)) -> JSONResponse:
    return JSONResponse(content={"items": await get_state_store().get_management_history(n)})


@app.get("/history/optimization", summary="Recent optimization history")
async def get_optimization_history(n: int = Query(default=20, ge=1, le=200)) -> JSONResponse:
    return JSONResponse(content={"items": await get_state_store().get_optimization_history(n)})


@app.get("/events/stream", summary="Server-Sent Events stream of agent activity")
async def stream_events():
    """Forward Redis pub/sub events as SSE for the dashboard.

    When Redis is unavailable the stream emits only periodic keep-alive
    pings; the frontend should reconnect with backoff.
    """
    try:
        from sse_starlette.sse import EventSourceResponse
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="sse-starlette not installed",
        )

    bus = get_event_bus()

    async def _generator():
        async for payload in bus.subscribe():
            if payload:
                yield {"event": "agent", "data": payload}
            else:
                yield {"event": "ping", "data": ""}

    return EventSourceResponse(_generator())


@app.get("/health", summary="Liveness probe")
async def health() -> JSONResponse:
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "aquafarm-agents",
            "version": "0.2.0",
            "management_graph": management_graph is not None,
            "redis_connected": _redis_client is not None,
            "event_channel": EVENT_CHANNEL,
            "tanks": settings.default_tank_ids,
            "cycle_interval_s": settings.cycle_interval_seconds,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("agents.main:app", host="0.0.0.0", port=8001, reload=False)
