from __future__ import annotations

import json

import httpx
import pytest

from luna.models.schema import CompletionRequest, Message
from luna.providers.openai_compat import OpenAICompatibleProvider


@pytest.mark.asyncio
async def test_openai_list_models():
    def handler(request):
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}]})

    provider = OpenAICompatibleProvider(base_url="http://test", transport=httpx.MockTransport(handler))
    assert await provider.list_models() == ["gpt-4o-mini", "gpt-4o"]


@pytest.mark.asyncio
async def test_openai_complete_converts_tool_calls():
    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "gpt-4o-mini"
        assert "Authorization" in request.headers
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ok",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "search", "arguments": '{"q":"hi"}'},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    provider = OpenAICompatibleProvider(base_url="http://test", api_key="sk-test", transport=httpx.MockTransport(handler))
    req = CompletionRequest(model="gpt-4o-mini", messages=[Message(role="user", content="hi")])
    resp = await provider.complete(req)
    assert resp.content == "ok"
    assert resp.tool_calls[0].id == "call_1"
    assert resp.tool_calls[0].args == {"q": "hi"}
    assert resp.usage.input_tokens == 7
    assert resp.usage.output_tokens == 3
    assert resp.finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_openai_stream():
    sse = (
        'data: {"choices":[{"delta":{"content":"He"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{"content":"llo"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":2,"completion_tokens":2}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    provider = OpenAICompatibleProvider(base_url="http://test/v1", transport=transport)
    req = CompletionRequest(model="gpt-4o-mini", messages=[Message(role="user", content="hi")])
    chunks = [c async for c in provider.stream(req)]
    contents = [c.content for c in chunks if c.content]
    assert contents == ["He", "llo"]
    assert any(c.usage is not None for c in chunks)


@pytest.mark.asyncio
async def test_openai_no_api_key_header_optional():
    def handler(request):
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    provider = OpenAICompatibleProvider(base_url="http://test", transport=transport)
    assert await provider.list_models() == []