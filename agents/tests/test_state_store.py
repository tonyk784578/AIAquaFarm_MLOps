"""Tests for the Redis-backed agent state store."""

from __future__ import annotations

import pytest

from agents.runtime.state_store import StateStore


@pytest.mark.asyncio
async def test_save_and_get_last_management_cycle(fake_redis):
    store = StateStore(fake_redis, history_size=5)

    result = {
        "final_report": "Cycle #1 complete",
        "control_decisions": [{"action_type": "no_action"}],
        "executed_commands": [],
        "iteration_count": 1,
    }
    record = await store.save_management_cycle(result)
    assert record["final_report"] == "Cycle #1 complete"
    assert "ran_at" in record

    fetched = await store.get_last_management_cycle()
    assert fetched["final_report"] == "Cycle #1 complete"


@pytest.mark.asyncio
async def test_history_is_bounded(fake_redis):
    store = StateStore(fake_redis, history_size=3)
    for i in range(10):
        await store.save_management_cycle({"final_report": f"r{i}", "iteration_count": i})

    history = await store.get_management_history(n=10)
    assert len(history) == 3
    # Newest entry is first
    assert history[0]["final_report"] == "r9"
    assert history[-1]["final_report"] == "r7"


@pytest.mark.asyncio
async def test_per_tank_optimization_isolation(fake_redis):
    store = StateStore(fake_redis)
    await store.save_optimization("TANK-01", {
        "selected_action": {"action": "reduce_feeding"},
        "simulation_result": {"status": "ok"},
        "recommended_actions": [{}, {}],
    })
    await store.save_optimization("TANK-02", {
        "selected_action": {"action": "water_exchange"},
        "recommended_actions": [],
    })

    a = await store.get_last_optimization("TANK-01")
    b = await store.get_last_optimization("TANK-02")
    assert a["selected_action"]["action"] == "reduce_feeding"
    assert b["selected_action"]["action"] == "water_exchange"
    assert a["candidates"] == 2
    assert b["candidates"] == 0


@pytest.mark.asyncio
async def test_missing_keys_return_empty(fake_redis):
    store = StateStore(fake_redis)
    assert await store.get_last_management_cycle() == {}
    assert await store.get_last_optimization("UNKNOWN") == {}
    assert await store.get_management_history(5) == []
