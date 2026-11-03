"""MCP server manager: discovery + tool proxy registration."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from luna.permissions.permissions import PermissionLevel
from luna.tools.base import Tool, ToolRegistry, ToolResult, ToolSpec


class DynamicArgs(BaseModel):
    model_config = ConfigDict(extra="allow")


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None
    timeout: float = 30.0
    permissions: list[PermissionLevel] = field(default_factory=lambda: [PermissionLevel.EXECUTE])
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServerConfig:
        perms = data.get("permissions")
        perms = [PermissionLevel(str(p).lower()) for p in perms] if perms is not None else [PermissionLevel.EXECUTE]
        return cls(
            name=data["name"],
            command=data["command"],
            args=list(data.get("args") or []),
            env=data.get("env"),
            cwd=data.get("cwd"),
            timeout=float(data.get("timeout", 30.0)),
            permissions=perms,
            enabled=bool(data.get("enabled", True)),
        )


class MCPToolProxy(Tool):
    def __init__(self, server_name: str, tool_def: dict[str, Any], client: Any, permissions: list[PermissionLevel]):
        name = tool_def.get("name", "tool")
        self.server_name = server_name
        self.tool_name = name
        self._client = client
        self._tool_def = tool_def
        spec = ToolSpec(
            id=f"mcp_{server_name}_{name}",
            name=f"{server_name}.{name}",
            description=tool_def.get("description", ""),
            input_schema=DynamicArgs,
            permissions=list(permissions),
            risk_level="medium",
            timeout=client.timeout if hasattr(client, "timeout") else None,
        )
        super().__init__(spec)

    async def aexecute(self, *args: Any, **kwargs: Any) -> ToolResult:
        params = {}
        if args and isinstance(args[0], dict):
            params.update(args[0])
        params.update(kwargs)
        try:
            res = await self._client.call_tool(self.tool_name, params)
            return ToolResult(ok=True, output=res, data=res)
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))

    async def arun(self, *args: Any, **kwargs: Any) -> ToolResult:
        return await self.aexecute(*args, **kwargs)

    def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # sync not possible in running loop; create task result impossible
                return ToolResult(ok=False, error="use aexecute in async context")
            return loop.run_until_complete(self.aexecute(*args, **kwargs))
        except RuntimeError:
            return asyncio.run(self.aexecute(*args, **kwargs))


class MCPManager:
    def __init__(self, tool_registry: ToolRegistry | None = None, permission_level: PermissionLevel = PermissionLevel.EXECUTE):
        self.tool_registry = tool_registry if tool_registry is not None else ToolRegistry()
        self.permission_level = permission_level
        self._configs: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, Any] = {}
        self._errors: dict[str, str] = {}

    def add_server(self, config: MCPServerConfig | dict[str, Any]) -> None:
        cfg = config if isinstance(config, MCPServerConfig) else MCPServerConfig.from_dict(config)
        self._configs[cfg.name] = cfg

    def load_config(self, servers: list[MCPServerConfig | dict[str, Any]]) -> None:
        for s in servers:
            self.add_server(s)

    async def connect_all(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, cfg in list(self._configs.items()):
            if not cfg.enabled:
                continue
            try:
                from luna.mcp.client import MCPClient

                client = MCPClient(command=cfg.command, args=cfg.args, env=cfg.env, cwd=cfg.cwd, timeout=cfg.timeout)
                await client.initialize()
                tools = await client.list_tools()
                proxies = []
                for td in tools:
                    proxy = MCPToolProxy(name, td, client, cfg.permissions or [self.permission_level])
                    self.tool_registry.register(proxy)
                    proxies.append(proxy)
                self._clients[name] = client
                results[name] = {"ok": True, "tools": [p.id for p in proxies]}
            except Exception as exc:
                self._errors[name] = str(exc)
                results[name] = {"ok": False, "error": str(exc)}
        return results

    async def restart(self, name: str) -> dict[str, Any]:
        await self.close_server(name)
        cfg = self._configs.get(name)
        if cfg is None:
            return {"ok": False, "error": "unknown server"}
        # re-register by reconnecting
        try:
            from luna.mcp.client import MCPClient

            client = MCPClient(command=cfg.command, args=cfg.args, env=cfg.env, cwd=cfg.cwd, timeout=cfg.timeout)
            await client.initialize()
            tools = await client.list_tools()
            for td in tools:
                proxy = MCPToolProxy(name, td, client, cfg.permissions or [self.permission_level])
                self.tool_registry.register(proxy)
            self._clients[name] = client
            self._errors.pop(name, None)
            return {"ok": True, "tools": [f"mcp_{name}_{t.get('name')}" for t in tools]}
        except Exception as exc:
            self._errors[name] = str(exc)
            return {"ok": False, "error": str(exc)}

    async def close_server(self, name: str) -> None:
        client = self._clients.pop(name, None)
        if client is not None:
            with contextlib.suppress(Exception):
                await client.close()

    async def close(self) -> None:
        for name in list(self._clients.keys()):
            await self.close_server(name)

    @property
    def clients(self) -> dict[str, Any]:
        return dict(self._clients)

    @property
    def errors(self) -> dict[str, str]:
        return dict(self._errors)


__all__ = ["MCPManager", "MCPServerConfig", "MCPToolProxy"]
