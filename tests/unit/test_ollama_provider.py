from __future__ import annotations

import httpx
import pytest

from luna.models.schema import CompletionRequest, Message
from luna.providers.ollama import OllamaProvider


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_ollama_list_models():
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "llama3"}, {"name": "qwen2.5"}]})

    provider = OllamaProvider(base_url="http://test", transport=_transport(handler))
    assert await provider.list_models() == ["llama3", "qwen2.5"]


@pytest.mark.asyncio
async def test_ollama_complete_converts_tools():
    def handler(request):
        body = request.read().decode()
        assert "/api/chat" in str(request.url)
        assert "llama3" in body
        return httpx.Response(
            200,
            json={
                "model": "llama3",
                "message": {
                    "role": "assistant",
                    "content": "hello",
                    "tool_calls": [{"function": {"name": "get_time", "arguments": {"tz": "UTC"}}}],
                },
                "done": True,
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )

    provider = OllamaProvider(base_url="http://test", transport=_transport(handler))
    req = CompletionRequest(model="llama3", messages=[Message(role="user", content="hi")])
    resp = await provider.complete(req)
    assert resp.content == "hello"
    assert resp.tool_calls[0].name == "get_time"
    assert resp.tool_calls[0].args == {"tz": "UTC"}
    assert resp.usage.input_tokens == 10
    assert resp.usage.output_tokens == 5
    assert resp.provider == "ollama"


@pytest.mark.asyncio
async def test_ollama_stream():
    lines = [
        '{"model":"llama3","message":{"role":"assistant","content":"Hi"},"done":false}',
        '{"model":"llama3","message":{"role":"assistant","content":"!"},"done":true,"prompt_eval_count":3,"eval_count":2}',
    ]

    def handler(request):
        return httpx.Response(200, text="\n".join(lines) + "\n")

    provider = OllamaProvider(base_url="http://test", transport=_transport(handler))
    req = CompletionRequest(model="llama3", messages=[Message(role="user", content="hi")])
    chunks = [c async for c in provider.stream(req)]
    assert len(chunks) == 2
    assert chunks[0].content == "Hi"
    assert chunks[1].done is True
    assert chunks[1].usage.input_tokens == 3
    assert chunks[1].usage.output_tokens == 2


@pytest.mark.asyncio
async def test_ollama_health_false():
    def handler(request):
        return httpx.Response(500)

    provider = OllamaProvider(base_url="http://test", transport=_transport(handler))
    assert await provider.health() is False