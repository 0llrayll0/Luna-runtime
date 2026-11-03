from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from luna.models.schema import CompletionRequest, CompletionResponse, StreamChunk


class ProviderBase(ABC):
    def __init__(
        self,
        name: str,
        base_url: str,
        *,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.base_url = base_url
        self.timeout = timeout

    @abstractmethod
    async def list_models(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        raise NotImplementedError

    @abstractmethod
    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r}, base_url={self.base_url!r})"


__all__ = ["ProviderBase"]