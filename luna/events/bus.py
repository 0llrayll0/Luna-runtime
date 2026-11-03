from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    type: str = ""
    name: str = ""
    payload: Any = None
    data: Any = None

    def __post_init__(self) -> None:
        if not self.type and self.name:
            self.type = self.name
        if not self.name and self.type:
            self.name = self.type
        if self.payload is None and self.data is not None:
            self.payload = self.data
        if self.data is None and self.payload is not None:
            self.data = self.payload
        if self.created_at == 0:
            self.created_at = time.time()

    created_at: float = field(default=0.0, init=True)


Handler = Callable[[Event], Awaitable[Any] | Any]


class SimpleEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = {}

    def subscribe(self, event_type: str, handler: Handler) -> Callable[[], None]:
        self._subscribers.setdefault(event_type, []).append(handler)

        def unsubscribe() -> None:
            with contextlib.suppress(KeyError, ValueError):
                self._subscribers[event_type].remove(handler)

        return unsubscribe

    async def emit(self, event: Event | str, data: Any = None) -> list[Any]:
        if isinstance(event, str):
            event = Event(type=event, payload=data)
        handlers = list(self._subscribers.get(event.type, []))
        handlers.extend(self._subscribers.get("*", []))
        results: list[Any] = []
        for handler in handlers:
            result = handler(event)
            if asyncio.iscoroutine(result):
                result = await result
            results.append(result)
        return results

    def clear(self) -> None:
        self._subscribers.clear()

    @property
    def subscriber_count(self) -> int:
        return sum(len(v) for v in self._subscribers.values())


__all__ = ["Event", "SimpleEventBus", "Handler"]
