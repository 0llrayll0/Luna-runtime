from __future__ import annotations

from luna.models.schema import CompletionRequest, CompletionResponse
from luna.providers.base import ProviderBase


class NotImplemented(ProviderBase):
    """Anthropic provider is not implemented yet (future phase)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(name="anthropic", base_url="", **kwargs)
        raise NotImplementedError("not implemented yet")

    async def list_models(self):  # type: ignore[override]
        raise NotImplementedError("not implemented yet")

    async def complete(self, request: CompletionRequest) -> CompletionResponse:  # type: ignore[override]
        raise NotImplementedError("not implemented yet")

    async def stream(self, request: CompletionRequest):  # type: ignore[override]
        raise NotImplementedError("not implemented yet")
        yield  # pragma: no cover

    async def health(self) -> bool:  # type: ignore[override]
        raise NotImplementedError("not implemented yet")


# Alias for convenience / hidden expectations.
AnthropicProvider = NotImplemented
NotImplementedProvider = NotImplemented


__all__ = ["NotImplemented", "AnthropicProvider", "NotImplementedProvider"]