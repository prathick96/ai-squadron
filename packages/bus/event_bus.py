"""
packages/bus/event_bus.py
Dual-mode event bus:
  - REDIS mode  (REDIS_URL set)       → Redis Streams (production)
  - LOCAL mode  (REDIS_URL not set)   → asyncio.Queue  (dev/test, no Redis needed)

Usage:
    bus = EventBus()
    await bus.publish(envelope)
    async for envelope in bus.consume("MY_CONSUMER"):
        ...
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis

from packages.schemas.events import EventEnvelope

log = logging.getLogger(__name__)

_STREAM_NAME  = os.getenv("REDIS_STREAM_NAME",   "squadron:events")
_GROUP_NAME   = os.getenv("REDIS_CONSUMER_GROUP", "squadron:workers")
_BLOCK_MS     = 2_000   # block for 2 s waiting for new messages
_MAX_PENDING  = 1_000   # max messages to fetch per XREADGROUP call


class EventBus:
    """
    Thread-safe async event bus.
    Instantiate once per process and share the reference.
    """

    def __init__(self) -> None:
        redis_url = os.getenv("REDIS_URL")
        if redis_url and redis_url != "redis://localhost:6379":
            self._mode   = "redis"
            self._client: aioredis.Redis = aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        else:
            # Fallback: pure asyncio queue — no Redis dependency for local dev
            self._mode   = "local"
            self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
        log.info("EventBus initialised in %s mode", self._mode)

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, envelope: EventEnvelope) -> str:
        """
        Publish an event envelope to the bus.
        Returns the message ID (Redis entry ID or UUID string).
        """
        data = envelope.to_bus_dict()
        if self._mode == "redis":
            msg_id: str = await self._client.xadd(_STREAM_NAME, data)  # type: ignore[assignment]
            log.debug("Published %s → %s  [id=%s]", envelope.event_type, envelope.target_agent, msg_id)
            return msg_id
        else:
            await self._queue.put(data)
            log.debug("Published %s → %s  [local queue]", envelope.event_type, envelope.target_agent)
            return envelope.event_id

    # ------------------------------------------------------------------
    # Consume
    # ------------------------------------------------------------------

    async def consume(
        self,
        consumer_name: str,
        filter_types: list[str] | None = None,
    ) -> AsyncGenerator[EventEnvelope, None]:
        """
        Async generator that yields EventEnvelopes from the bus.
        Runs indefinitely — use in an async for loop inside a task.

        Args:
            consumer_name: Unique identifier for this consumer instance.
            filter_types:  Optional list of EventType strings to filter.
                           If None, all events are yielded.
        """
        if self._mode == "redis":
            await self._ensure_group_exists()
            while True:
                try:
                    results = await self._client.xreadgroup(
                        _GROUP_NAME,
                        consumer_name,
                        {_STREAM_NAME: ">"},
                        count=_MAX_PENDING,
                        block=_BLOCK_MS,
                    )
                    if not results:
                        continue
                    for _stream, messages in results:
                        for msg_id, fields in messages:
                            try:
                                envelope = EventEnvelope.from_bus_dict(fields)
                                if filter_types and envelope.event_type not in filter_types:
                                    await self._client.xack(_STREAM_NAME, _GROUP_NAME, msg_id)
                                    continue
                                yield envelope
                                await self._client.xack(_STREAM_NAME, _GROUP_NAME, msg_id)
                            except Exception as exc:
                                log.exception("Failed to parse bus message %s: %s", msg_id, exc)
                                await self._client.xack(_STREAM_NAME, _GROUP_NAME, msg_id)
                except Exception as exc:
                    log.error("EventBus consume error: %s — retrying in 3s", exc)
                    await asyncio.sleep(3)
        else:
            # Local asyncio queue mode
            while True:
                try:
                    raw = await asyncio.wait_for(self._queue.get(), timeout=2.0)
                    envelope = EventEnvelope.from_bus_dict(raw)
                    if filter_types and envelope.event_type not in filter_types:
                        continue
                    yield envelope
                except asyncio.TimeoutError:
                    continue
                except Exception as exc:
                    log.exception("Local queue parse error: %s", exc)

    # ------------------------------------------------------------------
    # Redis group management
    # ------------------------------------------------------------------

    async def _ensure_group_exists(self) -> None:
        try:
            await self._client.xgroup_create(
                _STREAM_NAME, _GROUP_NAME, id="0", mkstream=True
            )
            log.info("Created Redis consumer group '%s' on stream '%s'", _GROUP_NAME, _STREAM_NAME)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                pass  # Group already exists — expected after first run
            else:
                raise

    async def ping(self) -> bool:
        """Health check — returns True if the bus is reachable."""
        if self._mode == "redis":
            try:
                return await self._client.ping()
            except Exception:
                return False
        return True

    async def close(self) -> None:
        if self._mode == "redis":
            await self._client.aclose()


# ---------------------------------------------------------------------------
# Module-level singleton — import and use directly
# ---------------------------------------------------------------------------
_bus_instance: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = EventBus()
    return _bus_instance
