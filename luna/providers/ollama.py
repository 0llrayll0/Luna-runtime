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


class OllamaProvider(ProviderBase):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        name: str = "ollama",
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(name=name, base_url=base_url.rstrip("/"), timeout=timeout)
        self.max_retries = max(1, max_retries)
        self.backoff = backoff
        if client is not None:
            self._client = client
        else:
            self._client = httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(timeout),
            )

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @staticmethod
    def _message_to_ollama(msg: Message) -> dict[str, Any]:
        out: dict[str, Any] = {"role": msg.role, "content": msg.content or ""}
        if msg.tool_calls:
            out["tool_calls"] = [
                {"function": {"name": tc.name, "arguments": tc.args}} for tc in msg.tool_calls
            ]
        if msg.tool_result is not None and msg.role == "tool":
            out["content"] = (
                msg.content if msg.content not in (None, "") else str(msg.tool_result)
            )
        return out

    @staticmethod
    def _convert_tool_calls(raw: Any) -> list[ToolCall]:
        out: list[ToolCall] = []
        for i, item in enumerate(raw or []):
            fn = (item or {}).get("function", {}) if isinstance(item, dict) else {}
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            tc_id = (item or {}).get("id") if isinstance(item, dict) else None
            out.append(ToolCall(id=tc_id or f"call_{i}", name=fn.get("name", ""), args=args or {}))
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
            resp = await self._client.get(self._url("/api/tags"))
            resp.raise_for_status()
            data = resp.json()
            names = []
            for m in data.get("models", []):
                names.append(m.get("name") or m.get("model") or str(m))
            return names

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
            "messages": [self._message_to_ollama(m) for m in request.messages],
            "stream": False,
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.temperature is not None:
            payload.setdefault("options", {})["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload.setdefault("options", {})["num_predict"] = request.max_tokens

        async def _do():
            resp = await self._client.post(self._url("/api/chat"), json=payload)
            resp.raise_for_status()
            return resp.json()

        data = await self._retry(_do)
        msg = data.get("message", {}) or {}
        tool_calls = self._convert_tool_calls(msg.get("tool_calls"))
        content = msg.get("content")
        usage = Usage(
            input_tokens=int(data.get("prompt_eval_count", 0) or 0),
            output_tokens=int(data.get("eval_count", 0) or 0),
            estimated=False,
        )
        if usage.input_tokens == 0 and usage.output_tokens == 0:
            # provider did not return counts -> estimate
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
            finish_reason="stop" if data.get("done") else None,
            model=data.get("model", request.model),
            provider=self.name,
        )

    async def stream(self, request: CompletionRequest):
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [self._message_to_ollama(m) for m in request.messages],
            "stream": True,
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.temperature is not None:
            payload.setdefault("options", {})["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload.setdefault("options", {})["num_predict"] = request.max_tokens

        async def _gen():
            async with self._client.stream("POST", self._url("/api/chat"), json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = data.get("message", {}) or {}
                    chunk_tc = self._convert_tool_calls(msg.get("tool_calls"))
                    content = msg.get("content", "") or ""
                    done = bool(data.get("done"))
                    usage = None
                    if done:
                        usage = Usage(
                            input_tokens=int(data.get("prompt_eval_count", 0) or 0),
                            output_tokens=int(data.get("eval_count", 0) or 0),
                            estimated=False,
                        )
                    yield StreamChunk(
                        content=content,
                        tool_calls=chunk_tc,
                        finish_reason="stop" if done else None,
                        model=data.get("model", request.model),
                        provider=self.name,
                        usage=usage,
                        done=done,
                    )

        async for chunk in _gen():
            yield chunk

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["OllamaProvider"]