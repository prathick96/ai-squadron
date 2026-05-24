"""
tests/test_event_bus.py
Unit tests for the EventBus in LOCAL mode (no Redis required).
Run: pytest tests/test_event_bus.py -v
"""
import asyncio
import pytest
from packages.bus.event_bus import EventBus
from packages.schemas.events import (
    AgentID, EventEnvelope, EventMetadata, EventType, Priority
)


def _make_envelope(event_type=EventType.VENTURE_BRIEF_READY) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        source_agent=AgentID.CEO_NICHE_SCOUT,
        target_agent=AgentID.PRODUCT_TEAM,
        payload={"niche": "AI tax tools", "go_decision": True},
        metadata=EventMetadata(
            run_id="run-test-001",
            venture_id="ven_test_001",
            pipeline_stage="CEO_NODE",
            token_cost=120,
            latency_ms=340,
        ),
    )


@pytest.mark.asyncio
async def test_bus_local_mode_ping():
    bus = EventBus()
    assert bus._mode == "local"
    assert await bus.ping() is True


@pytest.mark.asyncio
async def test_publish_and_consume():
    bus = EventBus()
    env = _make_envelope()
    await bus.publish(env)

    received = []
    async def consume_one():
        async for envelope in bus.consume("test_consumer"):
            received.append(envelope)
            break  # take exactly one

    await asyncio.wait_for(consume_one(), timeout=3.0)
    assert len(received) == 1
    assert received[0].event_type == EventType.VENTURE_BRIEF_READY
    assert received[0].payload["niche"] == "AI tax tools"


@pytest.mark.asyncio
async def test_publish_multiple_events():
    bus = EventBus()
    events_to_send = [
        _make_envelope(EventType.VENTURE_BRIEF_READY),
        _make_envelope(EventType.TECH_SPEC_READY),
        _make_envelope(EventType.BUILD_COMPLETE),
    ]
    for e in events_to_send:
        await bus.publish(e)

    received = []
    async def consume_three():
        async for envelope in bus.consume("test_consumer_2"):
            received.append(envelope)
            if len(received) == 3:
                break

    await asyncio.wait_for(consume_three(), timeout=5.0)
    assert len(received) == 3
    types = [e.event_type for e in received]
    assert EventType.VENTURE_BRIEF_READY in types
    assert EventType.TECH_SPEC_READY in types
    assert EventType.BUILD_COMPLETE in types


@pytest.mark.asyncio
async def test_filter_by_event_type():
    bus = EventBus()
    await bus.publish(_make_envelope(EventType.VENTURE_BRIEF_READY))
    await bus.publish(_make_envelope(EventType.QA_PASSED))
    await bus.publish(_make_envelope(EventType.VENTURE_BRIEF_READY))

    received = []
    async def consume_filtered():
        async for envelope in bus.consume(
            "filter_consumer",
            filter_types=[EventType.VENTURE_BRIEF_READY]
        ):
            received.append(envelope)
            if len(received) == 2:
                break

    await asyncio.wait_for(consume_filtered(), timeout=5.0)
    assert len(received) == 2
    assert all(e.event_type == EventType.VENTURE_BRIEF_READY for e in received)


@pytest.mark.asyncio
async def test_envelope_serialisation_roundtrip():
    env = _make_envelope()
    env.priority = Priority.CRITICAL
    bus_dict = env.to_bus_dict()
    restored = EventEnvelope.from_bus_dict(bus_dict)

    assert restored.event_type    == env.event_type
    assert restored.source_agent  == env.source_agent
    assert restored.priority      == Priority.CRITICAL
    assert restored.payload       == env.payload
    assert restored.metadata.run_id == "run-test-001"
    assert restored.metadata.token_cost == 120
