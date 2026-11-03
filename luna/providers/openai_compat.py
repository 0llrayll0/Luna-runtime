from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from luna.models.schema import (
    CompletionRequest,
    CompletionResponse,
    Message,
    StreamChunk,
    ToolCall,
    Usage,
)
from luna.providers.base import ProviderBase

_ESTIMATE_DIVISOR = 4


def _estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(text) // _ESTIMATE_DIVISOR)


class OpenAICompatibleProvider(ProviderBase):
    def __init__(
        self,
        base_url: str = "https://api.openai.com",
        name: str = "openai-compatible",
        *,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff: float = 0.5,
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(name=name, base_url=base_url.rstrip("/"), timeout=timeout)
        self.api_key = api_key
        self.max_retries = max(1, max_retries)
        self.backoff = backoff
        self._extra_headers = dict(headers or {})
        if client is not None:
            self._client = client
        else:
            self._client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(timeout))

    def _headers(self) -> dict[str, str]:
        h = dict(self._extra_headers)
        if self.api_key:
            h.setdefault("Authorization", f"Bearer {self.api_key}")
        return h

    def _api_base(self) -> str:
        base = self.base_url
        if not base.endswith("/v1"):
            base = base + "/v1"
        return base

    def _url(self, path: str) -> str:
        return f"{self._api_base()}{path}"

    @staticmethod
    def _message_to_openai(msg: Message) -> dict[str, Any]:
        out: dict[str, Any] = {
            "role": msg.role,
            "content": msg.content if msg.content is not None else "",
        }
        if msg.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.id or f"call_{i}",
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.args or {})},
                }
                for i, tc in enumerate(msg.tool_calls)
            ]
        if msg.role == "tool" and msg.tool_result is not None and "tool_call_id" not in out:
            raw = msg.tool_result.get("id") if isinstance(msg.tool_result, dict) else ""
            out["tool_call_id"] = str(raw or "")
        return out

    @staticmethod
    def _convert_tool_calls(raw: Any) -> list[ToolCall]:
        out: list[ToolCall] = []
        for item in raw or []:
            fn = (item or {}).get("function", {}) if isinstance(item, dict) else {}
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
                except json.JSONDecodeError:
                    args = {"_raw": args}
            out.append(
                ToolCall(
                    id=(item or {}).get("id", "") if isinstance(item, dict) else "",
                    name=fn.get("name", ""),
                    args=args or {},
                )
            )
        return out

    async def _retry(self, coro_factory):
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return await coro_factory()
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt + 1 >= self.max_retries:
                    raise
                await asyncio.sleep(self.backoff * (2**attempt))
        if last:
            raise last
        raise RuntimeError("unreachable")

    async def list_models(self) -> list[str]:
        async def _do():
            resp = await self._client.get(self._url("/models"), headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            ids = []
            for m in data.get("data", []):
                ids.append(m.get("id") or str(m))
            return ids

        return await self._retry(_do)

    async def health(self) -> bool:
        try:
            await self.list_models()
            return True
        except Exception:  # noqa: BLE001
            return False

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [self._message_to_openai(m) for m in request.messages],
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        payload.update(request.extra.get("payload", {}) if isinstance(request.extra, dict) else {})

        async def _do():
            resp = await self._client.post(
                self._url("/chat/completions"), json=payload, headers=self._headers()
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._retry(_do)
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {}) or {}
        tool_calls = self._convert_tool_calls(msg.get("tool_calls"))
        content = msg.get("content")
        usage_raw = data.get("usage", {}) or {}
        if usage_raw:
            usage = Usage(
                input_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
                output_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
                estimated=False,
            )
        else:
            joined = "".join(m.content or "" for m in request.messages)
            usage = Usage(
                input_tokens=_estimate_tokens(joined),
                output_tokens=_estimate_tokens(content),
                estimated=True,
            )
        return CompletionResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=choice.get("finish_reason"),
            model=data.get("model", request.model),
            provider=self.name,
        )

    async def stream(self, request: CompletionRequest):
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [self._message_to_openai(m) for m in request.messages],
            "stream": True,
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        async def _gen():
            async with self._client.stream(
                "POST", self._url("/chat/completions"), json=payload, headers=self._headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        yield StreamChunk(done=True, finish_reason="stop", provider=self.name, model=request.model)
                        continue
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choice = (data.get("choices") or [{}])[0]
                    delta = choice.get("delta", {}) or {}
                    content = delta.get("content", "") or ""
                    tool_deltas = delta.get("tool_calls")
                    converted = self._convert_tool_calls(tool_deltas) if tool_deltas else []
                    finish = choice.get("finish_reason")
                    usage_raw = data.get("usage")
                    usage = None
                    if usage_raw:
                        usage = Usage(
                            input_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
                            output_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
                            estimated=False,
                        )
                    yield StreamChunk(
                        content=content,
                        tool_calls=converted,
                        finish_reason=finish,
                        model=data.get("model", request.model),
                        provider=self.name,
                        usage=usage,
                        done=finish is not None,
                    )

        async for chunk in _gen():
            yield chunk

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["OpenAICompatibleProvider"]