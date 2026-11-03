from __future__ import annotations

import pytest

from luna.events.bus import Event, SimpleEventBus


@pytest.mark.asyncio
async def test_subscribe_and_emit() -> None:
    bus = SimpleEventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("ping", handler)
    out = await bus.emit(Event(type="ping", payload={"n": 1}))
    assert len(received) == 1
    assert received[0].payload == {"n": 1}
    assert out and out[0] is None


@pytest.mark.asyncio
async def test_multiple_handlers_and_wildcard() -> None:
    bus = SimpleEventBus()
    seen: list[str] = []

    def h1(event: Event) -> str:
        seen.append("h1")
        return "a"

    async def h2(event: Event) -> str:
        seen.append("h2")
        return "b"

    bus.subscribe("x", h1)
    bus.subscribe("*", h2)
    await bus.emit("x", {"v": 2})
    assert set(seen) == {"h1", "h2"}


@pytest.mark.asyncio
async def test_no_handlers() -> None:
    bus = SimpleEventBus()
    result = await bus.emit(Event(type="nothing"))
    assert result == []
