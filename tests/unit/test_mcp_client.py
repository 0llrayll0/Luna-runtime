import sys

import pytest

from luna.mcp.client import MCPClient

FAKE = [sys.executable, "/tmp/opencode/fake_mcp_server.py"]


@pytest.mark.asyncio
async def test_initialize():
    client = MCPClient(command=FAKE[0], args=FAKE[1:])
    await client.initialize()
    assert client.initialized is True
    await client.close()


@pytest.mark.asyncio
async def test_list_tools():
    client = MCPClient(command=FAKE[0], args=FAKE[1:])
    await client.initialize()
    tools = await client.list_tools()
    assert any(t["name"] == "echo" for t in tools)
    await client.close()


@pytest.mark.asyncio
async def test_call_tool():
    client = MCPClient(command=FAKE[0], args=FAKE[1:])
    await client.initialize()
    result = await client.call_tool("echo", {"text": "hi"})
    assert result["content"][0]["text"] == "hi"
    await client.close()


@pytest.mark.asyncio
async def test_list_and_read_resources():
    client = MCPClient(command=FAKE[0], args=FAKE[1:])
    await client.initialize()
    res = await client.list_resources()
    assert res and res[0]["uri"] == "file:///tmp/foo.txt"
    read = await client.read_resource("file:///tmp/foo.txt")
    assert read["contents"][0]["text"] == "hello resource"
    await client.close()


@pytest.mark.asyncio
async def test_timeout():
    client = MCPClient(command=sys.executable, args=["-c", "import time; time.sleep(10)"], timeout=0.2)
    with pytest.raises(BaseException):
        await client.initialize()
    await client.close()
