from __future__ import annotations

import asyncio
from typing import Any

from luna.agents.schema import AgentConfig, AgentMaxIterationsError, AgentResult
from luna.context.engine import ContextEngine
from luna.models.gateway import ModelGateway
from luna.models.schema import Message, Usage
from luna.permissions.permissions import Deny, PendingApproval, PermissionEngine
from luna.sessions.manager import SessionManager
from luna.tools.base import ToolRegistry


def _tool_defs(registry: ToolRegistry, allowed_ids: list[str] | None = None) -> list[dict[str, Any]]:
    allowed = set(allowed_ids or [])
    defs = []
    for spec in registry.list_specs():
        if allowed and spec.id not in allowed:
            continue
        schema = {}
        if hasattr(spec.input_schema, "model_json_schema"):
            schema = spec.input_schema.model_json_schema()
        defs.append(
            {
                "type": "function",
                "function": {
                    "name": spec.id,
                    "description": spec.description,
                    "parameters": schema,
                },
            }
        )
    return defs


class Agent:
    def __init__(
        self,
        config: AgentConfig,
        *,
        gateway: Any = None,
        tool_registry: Any = None,
        tools: Any = None,
        registry: Any = None,
        permission_engine: Any = None,
        permissions: Any = None,
        session_manager: Any = None,
        sessions: Any = None,
        context_engine: Any = None,
        context: Any = None,
        workdir: Any = None,
        **kwargs: Any,
    ) -> None:
        self.config = config
        self.gateway = gateway if gateway is not None else kwargs.get("gateway")
        self.tool_registry = tool_registry or tools or registry or kwargs.get("tool_registry") or kwargs.get("tools") or ToolRegistry()
        self.permission_engine = permission_engine or permissions or kwargs.get("permission_engine") or kwargs.get("permissions") or PermissionEngine()
        self.session_manager = session_manager or sessions or kwargs.get("session_manager") or kwargs.get("sessions") or SessionManager()
        self.context_engine = context_engine or context or kwargs.get("context_engine") or kwargs.get("context") or ContextEngine(default_budget_tokens=config.context_limit_tokens)
        if workdir is not None:
            self.workdir = workdir
        else:
            self.workdir = kwargs.get("workdir")
        if self.gateway is None:
            self.gateway = ModelGateway()

    async def _ensure_session(self, session_id: str | None) -> str:
        await self.session_manager.init()
        if session_id is None:
            return await self.session_manager.create_session(agent_name=self.config.name)
        existing = await self.session_manager.get_session(session_id)
        if existing is None:
            return await self.session_manager.create_session(session_id=session_id, agent_name=self.config.name)
        return session_id

    async def _run_tool(self, tool, args: dict[str, Any]) -> Any:
        try:
            if hasattr(tool, "arun"):
                return await tool.arun(**(args or {}))
            if hasattr(tool, "aexecute"):
                return await tool.aexecute(**(args or {}))
            # fallback sync
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: tool.execute(**(args or {})))
        except Exception as exc:  # noqa: BLE001
            from luna.tools.base import ToolResult

            return ToolResult(ok=False, error=str(exc))

    async def run_for_role(self, role: Any, task: str, session_id: str | None = None) -> AgentResult:
        try:
            from luna.orchestration.roles import Role
        except Exception:
            Role = None
        if Role is not None and isinstance(role, dict):
            role = Role(**role)
        original_prompt = self.config.system_prompt
        original_tools = list(self.config.tools)
        original_max = self.config.max_iterations
        try:
            self.config.system_prompt = (original_prompt + "\n" + getattr(role, "prompt_suffix", "")).strip()
            allowed = getattr(role, "allowed_tools", None)
            if allowed is not None:
                self.config.tools = list(allowed)
            self.config.max_iterations = getattr(role, "max_iterations", original_max)
            return await self.run(task, session_id=session_id)
        finally:
            self.config.system_prompt = original_prompt
            self.config.tools = original_tools
            self.config.max_iterations = original_max

    async def run(self, task: str, session_id: str | None = None) -> AgentResult:
        sid = await self._ensure_session(session_id)
        # append user message
        await self.session_manager.append_message(sid, Message(role="user", content=task))

        tc_defs = _tool_defs(self.tool_registry, self.config.tools)

        total_usage = Usage()
        all_tool_calls: list[Any] = []
        iterations = 0
        final_output: str | None = None
        status = "completed"
        approval_id: str | None = None

        while iterations < self.config.max_iterations:
            iterations += 1
            history = await self.session_manager.get_messages(sid)
            selected = self.context_engine.select_context(history, self.config.context_limit_tokens)

            messages: list[Message] = []
            if self.config.system_prompt:
                messages.append(Message(role="system", content=self.config.system_prompt))
            messages.extend(selected)

            resp = await self.gateway.complete(
                model=self.config.model,
                messages=messages,
                tools=tc_defs,
            )
            if resp.usage is not None:
                total_usage.input_tokens += resp.usage.input_tokens or 0
                total_usage.output_tokens += resp.usage.output_tokens or 0
                if resp.usage.estimated:
                    total_usage.estimated = True

            if resp.tool_calls:
                # append assistant with tool calls first
                await self.session_manager.append_message(
                    sid,
                    Message(role="assistant", content=resp.content or "", tool_calls=list(resp.tool_calls)),
                )
                approval_triggered = False
                for tc in resp.tool_calls:
                    all_tool_calls.append(tc)
                    tool = self.tool_registry.get(tc.name) if hasattr(self.tool_registry, "get") else None
                    args = tc.args or {}

                    # permission / existence
                    if tool is None or (self.config.tools and tc.name not in self.config.tools):
                        from luna.tools.base import ToolResult

                        tr = ToolResult(ok=False, error=f"unknown tool: {tc.name}")
                        await self.session_manager.append_message(
                            sid, Message(role="tool", content=tr.error or "", tool_result=tr, tool_calls=[])
                        )
                        continue

                    decision = self.permission_engine.check(tc.name, list(tool.spec.permissions), args=args)
                    if isinstance(decision, Deny):
                        from luna.tools.base import ToolResult

                        tr = ToolResult(ok=False, error=decision.reason)
                        await self.session_manager.append_message(
                            sid, Message(role="tool", content=tr.error or "", tool_result=tr)
                        )
                        continue
                    if isinstance(decision, PendingApproval):
                        approval_id = decision.request.id
                        status = "needs_approval"
                        # register approval id accessible
                        self.permission_engine.approvals[approval_id] = decision.request
                        from luna.tools.base import ToolResult

                        tr = ToolResult(ok=False, error="approval required", data={"approval_id": approval_id, "pending": True})
                        await self.session_manager.append_message(
                            sid, Message(role="tool", content="approval required", tool_result=tr)
                        )
                        approval_triggered = True
                        break

                    result = await self._run_tool(tool, args)
                    # inject workdir? tool already has kwargs
                    await self.session_manager.append_message(
                        sid, Message(role="tool", content=getattr(result, "output", None) if result is not None else None, tool_result=result)
                    )

                if approval_triggered:
                    break
                continue

            # final text
            final_output = resp.content
            await self.session_manager.append_message(sid, Message(role="assistant", content=resp.content or ""))
            break

        if final_output is None and status != "needs_approval" and iterations >= self.config.max_iterations:
            raise AgentMaxIterationsError(f"agent exceeded max_iterations={self.config.max_iterations}")

        return AgentResult(
            output=final_output,
            iterations=iterations,
            tool_calls=all_tool_calls,
            session_id=sid,
            usage=total_usage,
            status=status,
            approval_id=approval_id,
        )



async def execute_for_role(
    role: Any,
    task: str,
    *,
    config: Any = None,
    gateway: Any = None,
    tool_registry: Any = None,
    permission_engine: Any = None,
    session_manager: Any = None,
    context_engine: Any = None,
    workdir: Any = None,
    **kwargs: Any,
) -> AgentResult:
    from luna.agents.schema import AgentConfig
    from luna.context.engine import ContextEngine
    from luna.models.gateway import ModelGateway
    from luna.orchestration.roles import Role
    from luna.permissions.permissions import ExecutionMode, PermissionEngine
    from luna.sessions.manager import SessionManager
    from luna.tools.base import ToolRegistry

    r = role if isinstance(role, Role) else (Role(**role) if isinstance(role, dict) else role)
    base = config or AgentConfig(name=getattr(r, "name", "agent"), model=kwargs.pop("model", "default"))
    if isinstance(base, AgentConfig):
        base.system_prompt = (base.system_prompt + "\n" + getattr(r, "prompt_suffix", "")).strip()
        if getattr(r, "allowed_tools", None) is not None:
            base.tools = list(r.allowed_tools)
        base.max_iterations = getattr(r, "max_iterations", base.max_iterations)

    gw = gateway if gateway is not None else ModelGateway()
    tr = tool_registry if tool_registry is not None else ToolRegistry()
    pe = permission_engine if permission_engine is not None else PermissionEngine(mode=ExecutionMode.CONTROLLED)
    sm = session_manager if session_manager is not None else SessionManager(db_url="sqlite+aiosqlite:///:memory:")
    ce = context_engine if context_engine is not None else ContextEngine(default_budget_tokens=base.context_limit_tokens)
    agent = Agent(base, gateway=gw, tool_registry=tr, permission_engine=pe, session_manager=sm, context_engine=ce, workdir=workdir, **kwargs)
    return await agent.run(task)

__all__ = ["Agent", "AgentMaxIterationsError", "execute_for_role"]
