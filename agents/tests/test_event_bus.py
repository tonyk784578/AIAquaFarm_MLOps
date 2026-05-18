"""Tests for the Redis pub/sub event bus."""

from __future__ import annotations

import asyncio
import json

import pytest

from agents.runtime.event_bus import EVENT_CHANNEL, AgentEvent, EventBus


@pytest.mark.asyncio
async def test_publish_writes_to_channel(fake_redis):
    bus = EventBus(fake_redis)
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(EVENT_CHANNEL)
    # Drain the subscribe ack
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)

    await bus.publish("cycle_started", tank_id="TANK-01", data={"foo": "bar"})

    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    assert msg is not None
    payload = msg["data"]
    if isinstance(payload, bytes):
        payload = payload.decode()
    parsed = json.loads(payload)
    assert parsed["kind"] == "cycle_started"
    assert parsed["tank_id"] == "TANK-01"
    assert parsed["data"] == {"foo": "bar"}
    assert "ts" in parsed

    await pubsub.unsubscribe(EVENT_CHANNEL)
    await pubsub.close()


@pytest.mark.asyncio
async def test_publish_is_noop_when_redis_missing():
    bus = EventBus(None)
    assert not bus.is_available
    event = await bus.publish("error", tank_id="X", data={"msg": "no redis"})
    assert event.kind == "error"


@pytest.mark.asyncio
async def test_timed_node_emits_start_and_completion(fake_redis):
    bus = EventBus(fake_redis)
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(EVENT_CHANNEL)
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)

    async with bus.timed_node("analyse_situation", tank_id="TANK-01"):
        await asyncio.sleep(0.01)

    kinds = []
    for _ in range(2):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        assert msg is not None
        data = msg["data"]
        if isinstance(data, bytes):
            data = data.decode()
        kinds.append(json.loads(data)["kind"])

    assert kinds == ["node_started", "node_completed"]
    await pubsub.unsubscribe(EVENT_CHANNEL)
    await pubsub.close()


def test_agent_event_serialization_is_json():
    ev = AgentEvent.now("decision_made", tank_id="T1", data={"a": 1})
    s = ev.to_json()
    parsed = json.loads(s)
    assert parsed["kind"] == "decision_made"
    assert parsed["data"]["a"] == 1
