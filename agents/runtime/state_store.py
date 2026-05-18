"""Redis-backed state store for agent cycle results and history.

The in-memory ``_last_report`` / ``_last_optimization`` dicts in main.py are
volatile — every restart drops them. This module persists them in Redis so
the frontend ``/agents`` dashboard always has a meaningful state to render.

Key layout (single Redis DB):

    agents:last:management           — JSON of last management cycle
    agents:last:optimization:{tank}  — JSON of last optimization for one tank
    agents:history:management        — LIST (LPUSH/LTRIM) of the last N cycles
    agents:history:optimization      — LIST of the last N optimization runs

History entries are capped via ``LTRIM`` so the store stays bounded.

Usage::

    store = StateStore(redis_client)
    await store.save_management_cycle(result)
    last = await store.get_last_management_cycle()
    history = await store.get_management_history(n=20)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()


class StateStore:
    """Async wrapper around a redis client storing agent cycle state + history.

    Args:
        redis_client: Async Redis client (``redis.asyncio.Redis``).
        history_size: Maximum entries retained per history list.
        key_prefix: Override the default ``agents:`` key prefix.
    """

    DEFAULT_HISTORY_SIZE = 50

    def __init__(
        self,
        redis_client: Any,
        history_size: int = DEFAULT_HISTORY_SIZE,
        key_prefix: str = "agents",
    ) -> None:
        self.redis = redis_client
        self.history_size = history_size
        self.k = key_prefix

    # ── Key helpers ────────────────────────────────────────────────────────────

    def _k_last_mgmt(self) -> str:
        return f"{self.k}:last:management"

    def _k_last_opt(self, tank_id: str) -> str:
        return f"{self.k}:last:optimization:{tank_id}"

    def _k_history_mgmt(self) -> str:
        return f"{self.k}:history:management"

    def _k_history_opt(self) -> str:
        return f"{self.k}:history:optimization"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _safe_loads(raw: str | bytes | None) -> dict[str, Any]:
        if raw is None:
            return {}
        try:
            return json.loads(raw if isinstance(raw, (str, bytes)) else raw.decode())
        except (json.JSONDecodeError, AttributeError, TypeError):
            return {}

    # ── Management cycle ─────────────────────────────────────────────────────

    async def save_management_cycle(self, result: dict[str, Any]) -> dict[str, Any]:
        """Persist a management cycle result and push onto history list.

        Args:
            result: AgentState-like dict (final_report, control_decisions,
                executed_commands, error, iteration_count, ...).

        Returns:
            The saved record with added ``ran_at`` timestamp.
        """
        record = {
            "ran_at": self._now_iso(),
            "final_report": result.get("final_report", ""),
            "decisions": result.get("control_decisions", []),
            "executed": result.get("executed_commands", []),
            "iteration_count": result.get("iteration_count", 0),
            "twin_result": result.get("twin_result"),
            "error": result.get("error"),
        }
        payload = json.dumps(record, ensure_ascii=False, default=str)
        try:
            await self.redis.set(self._k_last_mgmt(), payload)
            await self.redis.lpush(self._k_history_mgmt(), payload)
            await self.redis.ltrim(self._k_history_mgmt(), 0, self.history_size - 1)
        except Exception as exc:
            logger.error("state_store_save_failed", error=str(exc))
        return record

    async def get_last_management_cycle(self) -> dict[str, Any]:
        try:
            raw = await self.redis.get(self._k_last_mgmt())
        except Exception as exc:
            logger.warning("state_store_get_failed", error=str(exc))
            return {}
        return self._safe_loads(raw)

    async def get_management_history(self, n: int = 20) -> list[dict[str, Any]]:
        n = max(1, min(n, self.history_size))
        try:
            items = await self.redis.lrange(self._k_history_mgmt(), 0, n - 1)
        except Exception as exc:
            logger.warning("state_store_history_failed", error=str(exc))
            return []
        return [self._safe_loads(item) for item in items]

    # ── Optimization ─────────────────────────────────────────────────────────

    async def save_optimization(self, tank_id: str, result: dict[str, Any]) -> dict[str, Any]:
        record = {
            "ran_at": self._now_iso(),
            "tank_id": tank_id,
            "selected_action": result.get("selected_action"),
            "simulation_result": result.get("simulation_result"),
            "candidates": len(result.get("recommended_actions", [])),
            "error": result.get("error"),
        }
        payload = json.dumps(record, ensure_ascii=False, default=str)
        try:
            await self.redis.set(self._k_last_opt(tank_id), payload)
            await self.redis.lpush(self._k_history_opt(), payload)
            await self.redis.ltrim(self._k_history_opt(), 0, self.history_size - 1)
        except Exception as exc:
            logger.error("state_store_opt_save_failed", error=str(exc))
        return record

    async def get_last_optimization(self, tank_id: str) -> dict[str, Any]:
        try:
            raw = await self.redis.get(self._k_last_opt(tank_id))
        except Exception as exc:
            logger.warning("state_store_opt_get_failed", error=str(exc))
            return {}
        return self._safe_loads(raw)

    async def get_optimization_history(self, n: int = 20) -> list[dict[str, Any]]:
        n = max(1, min(n, self.history_size))
        try:
            items = await self.redis.lrange(self._k_history_opt(), 0, n - 1)
        except Exception as exc:
            logger.warning("state_store_opt_history_failed", error=str(exc))
            return []
        return [self._safe_loads(item) for item in items]
