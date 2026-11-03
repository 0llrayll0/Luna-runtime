from __future__ import annotations

import asyncio
from typing import Any

from luna.models.schema import CompletionRequest, CompletionResponse, Usage
from luna.providers.base import ProviderBase

_ESTIMATE_DIVISOR = 4


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(text) // _ESTIMATE_DIVISOR)


class ModelGateway:
    def __init__(
        self,
        providers: list[ProviderBase] | None = None,
        provider_order: list[str] | None = None,
        timeout: float = 30.0,
        fallback: bool = True,
    ) -> None:
        self.providers: dict[str, ProviderBase] = {}
        self._order: list[str] = list(provider_order or [])
        self.timeout = timeout
        self.fallback = fallback
        for p in providers or []:
            self.register(p)

    def register(self, provider: ProviderBase) -> None:
        self.providers[provider.name] = provider
        if provider.name not in self._order:
            self._order.append(provider.name)

    def register_provider(self, provider: ProviderBase) -> None:
        self.register(provider)

    def get_provider(self, name: str) -> ProviderBase | None:
        return self.providers.get(name)

    def list_providers(self) -> list[str]:
        return list(self.providers.keys())

    async def list_models(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for name, provider in self.providers.items():
            out[name] = await provider.list_models()
        return out

    def _coerce_request(self, *args: Any, **kwargs: Any) -> CompletionRequest:
        if len(args) == 1 and isinstance(args[0], CompletionRequest):
            return args[0]
        if "request" in kwargs:
            req = kwargs.pop("request")
            if isinstance(req, CompletionRequest):
                return req
        model = kwargs.pop("model", None)
        messages = kwargs.pop("messages", None)
        if model is None and len(args) >= 1:
            model = args[0]
        if messages is None and len(args) >= 2:
            messages = args[1]
        if messages is None:
            messages = []
        return CompletionRequest(model=model or "", messages=messages, **kwargs)

    def resolve(self, model: str) -> tuple[str | None, str]:
        if "/" in model:
            provider_name, model_name = model.split("/", 1)
            return provider_name, model_name
        provider_name = self._order[0] if self._order else next(iter(self.providers), None)
        return provider_name, model

    def _ensure_usage(
        self, response: CompletionResponse, request: CompletionRequest
    ) -> CompletionResponse:
        if response.usage is None:
            response.usage = Usage()
        if (
            response.usage.input_tokens == 0
            and response.usage.output_tokens == 0
            and not response.usage.estimated
        ):
            joined = "".join(m.content or "" for m in request.messages)
            response.usage = Usage(
                input_tokens=estimate_tokens(joined),
                output_tokens=estimate_tokens(response.content),
                estimated=True,
            )
        return response

    async def complete(self, *args: Any, **kwargs: Any) -> CompletionResponse:
        request = self._coerce_request(*args, **kwargs)
        provider_name, model_name = self.resolve(request.model)
        req = request.model_copy(update={"model": model_name})
        order: list[str] = []
        if provider_name and provider_name in self.providers:
            order.append(provider_name)
        if self.fallback:
            for p in self._order:
                if p not in order and p in self.providers:
                    order.append(p)
            for p in self.providers:
                if p not in order:
                    order.append(p)
        if not order:
            raise RuntimeError("no providers registered")
        last_exc: Exception | None = None
        for pname in order:
            provider = self.providers.get(pname)
            if provider is None:
                continue
            try:
                resp = await asyncio.wait_for(provider.complete(req), timeout=self.timeout)
                resp = self._ensure_usage(resp, request)
                return resp
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("no providers available")

    async def stream(self, *args: Any, **kwargs: Any):
        request = self._coerce_request(*args, **kwargs)
        provider_name, model_name = self.resolve(request.model)
        req = request.model_copy(update={"model": model_name})
        provider = self.providers.get(provider_name) if provider_name else None
        if provider is None:
            # fallback first
            if self._order:
                provider = self.providers.get(self._order[0])
            if provider is None and self.providers:
                provider = next(iter(self.providers.values()))
        if provider is None:
            raise RuntimeError("no providers registered")
        async for chunk in provider.stream(req):
            yield chunk

    async def health(self) -> dict[str, bool]:
        out = {}
        for name, provider in self.providers.items():
            try:
                out[name] = await provider.health()
            except Exception:  # noqa: BLE001
                out[name] = False
        return out

    def count_tokens(self, text: str | None = None) -> int:
        return estimate_tokens(text)


__all__ = ["ModelGateway", "estimate_tokens"]