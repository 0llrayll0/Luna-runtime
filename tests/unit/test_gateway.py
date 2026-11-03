from __future__ import annotations
import pytest
from tests.fixtures.mock_provider import MockProvider
from luna.models.gateway import ModelGateway
from luna.models.schema import CompletionRequest, Message, Usage
from luna.providers.base import ProviderBase



@pytest.mark.asyncio
async def test_gateway_selection_by_provider_slash_model():
    p = MockProvider(name="ollama", models=["llama3"])
    gw = ModelGateway(providers=[p])
    req = CompletionRequest(model="ollama/llama3", messages=[Message(role="user", content="hi")])
    resp = await gw.complete(req)
    assert resp.provider == "ollama"
    assert resp.model == "llama3"
    assert p.calls == 1


@pytest.mark.asyncio
async def test_gateway_fallback_to_next_provider():
    failing = MockProvider(name="a")
    # make complete raise
    async def boom(request):
        raise RuntimeError("down")

    failing.complete = boom  # type: ignore
    ok = MockProvider(name="b")
    gw = ModelGateway(providers=[failing, ok])
    req = CompletionRequest(model="m1", messages=[Message(role="user", content="hi")])
    resp = await gw.complete(req)
    assert resp.provider == "b"


@pytest.mark.asyncio
async def test_gateway_token_estimation_when_missing():
    # Easier: use MockProvider with response lacking usage? MockProvider always usage. Build custom
    class EstProvider(ProviderBase):
        def __init__(self):
            super().__init__(name="est", base_url="http://x")

        async def list_models(self):
            return ["m"]

        async def complete(self, request):
            from luna.models.schema import CompletionResponse

            return CompletionResponse(
                content="four words here now",
                usage=Usage(input_tokens=0, output_tokens=0, estimated=False),
                model=request.model,
                provider=self.name,
            )

        async def stream(self, request):
            yield

        async def health(self):
            return True

    gw = ModelGateway(providers=[EstProvider()])
    req = CompletionRequest(model="est/m", messages=[Message(role="user", content="hello world test")])
    resp = await gw.complete(req)
    assert resp.usage.estimated is True
    assert resp.usage.input_tokens > 0


@pytest.mark.asyncio
async def test_gateway_stream():
    p = MockProvider(name="mock")
    gw = ModelGateway(providers=[p])
    req = CompletionRequest(model="mock/m1", messages=[Message(role="user", content="hi")])
    chunks = [c async for c in gw.stream(req)]
    assert chunks and chunks[0].content == "mocked"


@pytest.mark.asyncio
async def test_anthropic_not_implemented():
    from luna.providers.anthropic import AnthropicProvider

    with pytest.raises(NotImplementedError):
        AnthropicProvider()
