from __future__ import annotations

import os
from pathlib import Path

import pytest

from luna.agents import Agent, AgentConfig, AgentMaxIterationsError
from luna.context.engine import ContextEngine
from luna.models.gateway import ModelGateway
from luna.models.schema import CompletionResponse, Message, ToolCall, Usage
from luna.permissions.permissions import ExecutionMode, PermissionEngine
from luna.sessions.manager import SessionManager
from luna.tools.base import ToolRegistry
from luna.tools.filesystem import FsReadTool
from tests.fixtures.mock_provider import MockProvider


@pytest.mark.asyncio
async def test_direct_answer(tmp_path: Path):
    os.environ["LUNA_WORKDIR"] = str(tmp_path)
    provider = MockProvider(
        responses=[
            CompletionResponse(
                content="hello world",
                tool_calls=[],
                usage=Usage(input_tokens=5, output_tokens=2, estimated=False),
                finish_reason="stop",
                model="m1",
                provider="mock",
            )
        ]
    )
    gw = ModelGateway(providers=[provider])
    registry = ToolRegistry()
    perms = PermissionEngine(mode=ExecutionMode.CONTROLLED)
    sessions = SessionManager(db_url="sqlite+aiosqlite:///:memory:")
    context = ContextEngine(default_budget_tokens=1000)
    config = AgentConfig(name="a", system_prompt="sys", model="mock/m1", tools=[], max_iterations=3, context_limit_tokens=1000)
    agent = Agent(config, gateway=gw, tool_registry=registry, permission_engine=perms, session_manager=sessions, context_engine=context)
    result = await agent.run("hi")
    assert result.status == "completed"
    assert result.output == "hello world"
    assert result.iterations == 1
    assert result.session_id is not None


@pytest.mark.asyncio
async def test_tool_call_fs_read_then_answer(tmp_path: Path):
    os.environ["LUNA_WORKDIR"] = str(tmp_path)
    (tmp_path / "a.txt").write_text("secret", encoding="utf-8")
    provider = MockProvider(
        responses=[
            CompletionResponse(
                content=None,
                tool_calls=[ToolCall(id="c1", name="fs_read", args={"path": "a.txt"})],
                usage=Usage(input_tokens=5, output_tokens=2, estimated=False),
                finish_reason="tool_calls",
                model="m1",
                provider="mock",
            ),
            CompletionResponse(
                content="read done",
                tool_calls=[],
                usage=Usage(input_tokens=5, output_tokens=2, estimated=False),
                finish_reason="stop",
                model="m1",
                provider="mock",
            ),
        ]
    )
    gw = ModelGateway(providers=[provider])
    registry = ToolRegistry()
    registry.register(FsReadTool(workdir=tmp_path))
    perms = PermissionEngine(mode=ExecutionMode.CONTROLLED)
    sessions = SessionManager(db_url="sqlite+aiosqlite:///:memory:")
    context = ContextEngine(default_budget_tokens=1000)
    config = AgentConfig(name="a", system_prompt="sys", model="mock/m1", tools=["fs_read"], max_iterations=5, context_limit_tokens=1000)
    agent = Agent(config, gateway=gw, tool_registry=registry, permission_engine=perms, session_manager=sessions, context_engine=context, workdir=tmp_path)
    result = await agent.run("read a.txt")
    assert result.status == "completed"
    assert result.output == "read done"
    assert result.iterations == 2
    assert len(result.tool_calls) == 1


@pytest.mark.asyncio
async def test_session_reuse_persists_history(tmp_path: Path):
    os.environ["LUNA_WORKDIR"] = str(tmp_path)
    provider = MockProvider(
        responses=[
            CompletionResponse(content="first", tool_calls=[], usage=Usage(input_tokens=1, output_tokens=1, estimated=False), model="m1", provider="mock"),
            CompletionResponse(content="second", tool_calls=[], usage=Usage(input_tokens=1, output_tokens=1, estimated=False), model="m1", provider="mock"),
        ]
    )
    gw = ModelGateway(providers=[provider])
    registry = ToolRegistry()
    perms = PermissionEngine(mode=ExecutionMode.CONTROLLED)
    sessions = SessionManager(db_url="sqlite+aiosqlite:///:memory:")
    context = ContextEngine(default_budget_tokens=1000)
    config = AgentConfig(name="a", system_prompt="sys", model="mock/m1", tools=[], max_iterations=3, context_limit_tokens=1000)
    agent = Agent(config, gateway=gw, tool_registry=registry, permission_engine=perms, session_manager=sessions, context_engine=context)
    sid = "sess-1"
    r1 = await agent.run("hello", session_id=sid)
    assert r1.session_id == sid
    r2 = await agent.run("again", session_id=sid)
    assert r2.session_id == sid
    msgs = await sessions.get_messages(sid)
    assert len(msgs) >= 4


@pytest.mark.asyncio
async def test_max_iterations_raises(tmp_path: Path):
    os.environ["LUNA_WORKDIR"] = str(tmp_path)
    (tmp_path / "a.txt").write_text("secret", encoding="utf-8")
    provider = MockProvider(
        responses=[
            CompletionResponse(content=None, tool_calls=[ToolCall(id="c1", name="fs_read", args={"path": "a.txt"})], usage=Usage(input_tokens=1, output_tokens=1, estimated=False), model="m1", provider="mock")
        ]
    )
    gw = ModelGateway(providers=[provider])
    registry = ToolRegistry()
    registry.register(FsReadTool(workdir=tmp_path))
    perms = PermissionEngine(mode=ExecutionMode.CONTROLLED)
    sessions = SessionManager(db_url="sqlite+aiosqlite:///:memory:")
    context = ContextEngine(default_budget_tokens=1000)
    config = AgentConfig(name="a", system_prompt="sys", model="mock/m1", tools=["fs_read"], max_iterations=2, context_limit_tokens=1000)
    agent = Agent(config, gateway=gw, tool_registry=registry, permission_engine=perms, session_manager=sessions, context_engine=context, workdir=tmp_path)
    with pytest.raises(AgentMaxIterationsError):
        await agent.run("loop")


@pytest.mark.asyncio
async def test_context_engine_compact_and_select():
    context = ContextEngine(default_budget_tokens=10)
    msgs = [Message(role="user", content="a" * 40), Message(role="assistant", content="b" * 40)]
    selected = context.select_context(msgs, 10)
    assert len(selected) <= 2
    msgs2 = [Message(role="user", content="a" * 40), Message(role="assistant", content="b" * 40)]
    removed = context.compact(msgs2, 10)
    assert removed >= 1
    assert len(msgs2) >= 1
