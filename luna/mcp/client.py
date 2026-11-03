"""Minimal MCP client over STDIO (JSON-RPC newline framing).

HTTP transport is intentionally not supported (future phase).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from typing import Any


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.command = command
        self.args = list(args or [])
        self.env = env
        self.cwd = cwd
        self.timeout = timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id: int = 1
        self._initialized: bool = False

    async def connect(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return
        env = None
        if self.env is not None:
            env = dict(os.environ)
            env.update(self.env)
        self._proc = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            async for raw in self._proc.stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                mid = msg.get("id")
                if mid is not None and mid in self._pending:
                    fut = self._pending.pop(mid)
                    if not fut.done():
                        fut.set_result(msg)
        except Exception:
            pass

    async def _drain_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        try:
            async for _ in self._proc.stderr:
                pass
        except Exception:
            pass

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._proc is None or self._proc.returncode is not None:
            await self.connect()
        assert self._proc is not None and self._proc.stdin is not None
        rid = self._next_id
        self._next_id += 1
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._pending[rid] = fut
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        self._proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()
        try:
            msg = await asyncio.wait_for(fut, timeout=self.timeout)
        except TimeoutError as exc:
            self._pending.pop(rid, None)
            raise MCPError(f"timeout waiting for {method}") from exc
        if "error" in msg:
            raise MCPError(str(msg["error"]))
        return msg.get("result")

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        with contextlib.suppress(Exception):
            self._proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))

    async def initialize(self, client_name: str = "luna-runtime", client_version: str = "0.1.0", protocol_version: str = "2024-11-05") -> Any:
        result = await self._request(
            "initialize",
            {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": client_version},
            },
        )
        self._notify("notifications/initialized", {})
        try:
            if self._proc is not None and self._proc.stdin is not None:
                await self._proc.stdin.drain()
        except Exception:
            pass
        self._initialized = True
        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._request("tools/list", {})
        if isinstance(result, dict):
            return list(result.get("tools") or [])
        return []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        result = await self._request("tools/call", {"name": name, "arguments": arguments or {}})
        return result

    async def list_resources(self) -> list[dict[str, Any]]:
        result = await self._request("resources/list", {})
        if isinstance(result, dict):
            return list(result.get("resources") or [])
        return []

    async def read_resource(self, uri: str) -> Any:
        return await self._request("resources/read", {"uri": uri})

    async def ping(self) -> Any:
        return await self._request("ping", {})

    async def close(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.stdin is not None:
                self._proc.stdin.close()
        except Exception:
            pass
        if self._reader_task is not None:
            self._reader_task.cancel()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except TimeoutError:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except TimeoutError:
                self._proc.kill()
        self._proc = None

    async def shutdown(self) -> None:
        await self.close()

    @property
    def initialized(self) -> bool:
        return self._initialized


__all__ = ["MCPClient", "MCPError"]
