from __future__ import annotations

import asyncio

from luna.models.schema import CompletionResponse, StreamChunk, Usage
from luna.providers.base import ProviderBase


class MockProvider(ProviderBase):
    """Test-only provider. Not for production."""

    def __init__(
        self,
        name="mock",
        models=None,
        response=None,
        responses=None,
        complete_side_effect=None,
        health=True,
    ):
        super().__init__(name=name, base_url="http://mock")
        self._models = list(models or ["m1"])
        self._response = response
        self._responses = list(responses or [])
        self._side_effect = complete_side_effect
        self._health = health
        self.calls = 0

    async def list_models(self):
        return list(self._models)

    async def complete(self, request):
        self.calls += 1
        if self._side_effect is not None:
            result = self._side_effect(request, self.calls)
            if asyncio.iscoroutine(result):
                result = await result
            resp = result
        elif self._responses:
            idx = min(self.calls - 1, len(self._responses) - 1)
            item = self._responses[idx]
            if callable(item):
                item = item(request)
            resp = item
        elif callable(self._response):
            maybe = self._response(request)
            if asyncio.iscoroutine(maybe):
                maybe = await maybe
            resp = maybe
        elif self._response is not None:
            resp = self._response
        else:
            resp = CompletionResponse(
                content="mocked",
                tool_calls=[],
                usage=Usage(input_tokens=4, output_tokens=2, estimated=False),
                finish_reason="stop",
                model=request.model,
                provider=self.name,
            )

        if isinstance(resp, CompletionResponse):
            if not resp.model:
                resp = resp.model_copy(update={"model": request.model})
            if not resp.provider:
                resp = resp.model_copy(update={"provider": self.name})
        return resp

    async def stream(self, request):
        self.calls += 1
        yield StreamChunk(content="mocked", done=True, finish_reason="stop", provider=self.name, model=request.model)

    async def health(self):
        return self._health
