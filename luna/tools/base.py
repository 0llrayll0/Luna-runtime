"""Dynamic tool system for Luna Runtime."""

from __future__ import annotations

import contextlib
import importlib
import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from luna.permissions.permissions import PermissionLevel


@dataclass
class ToolSpec:
    id: str
    name: str
    description: str
    input_schema: type[BaseModel]
    output: Any = None
    permissions: list[PermissionLevel] = field(default_factory=list)
    risk_level: str = "low"
    timeout: float | None = None


@dataclass
class ToolResult:
    ok: bool = True
    output: Any = None
    error: str | None = None
    # common subprocess-like fields
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    path: str | None = None
    data: Any = None

    def __await__(self):
        async def _coro():
            return self

        return _coro().__await__()

    def model_dump(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class Tool(ABC):
    def __init__(self, spec: ToolSpec, **kwargs: Any) -> None:
        self.spec = spec
        self.kwargs = kwargs

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def permissions_required(self) -> list[PermissionLevel]:
        return list(self.spec.permissions)

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        model = self.spec.input_schema(**params)
        return model.model_dump()

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        ...

    def run(self, *args: Any, **kwargs: Any) -> ToolResult:
        return self.execute(*args, **kwargs)

    async def aexecute(self, *args: Any, **kwargs: Any) -> ToolResult:
        return self.execute(*args, **kwargs)

    async def arun(self, *args: Any, **kwargs: Any) -> ToolResult:
        return self.execute(*args, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> ToolResult:
        return self.execute(*args, **kwargs)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool | Callable[[], Tool], spec: ToolSpec | None = None) -> None:
        if isinstance(tool, Tool):
            self._tools[tool.id] = tool
            return
        if callable(tool) and spec is None:
            maybe = tool()
            if isinstance(maybe, Tool):
                self._tools[maybe.id] = maybe
                return
        # allow register(factory, spec=...)
        if spec is not None and callable(tool):
            instance = tool() if not inspect.signature(tool).parameters else tool
            # best-effort
            if isinstance(instance, Tool):
                self._tools[instance.id] = instance
                return
        # last: tool id
        raise TypeError("register expects a Tool instance or zero-arg factory")

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def list_specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def get(self, tool_id: str) -> Tool | None:
        return self._tools.get(tool_id)

    def execute(self, tool_id: str, args: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        tool = self.get(tool_id)
        if tool is None:
            return ToolResult(ok=False, error=f"unknown tool: {tool_id}")
        params = dict(args or {})
        params.update(kwargs)
        return tool.execute(**params)

    def load_entrypoints(self, paths: list[str] | str | None = None) -> None:
        if not paths:
            return
        if isinstance(paths, str):
            paths = [paths]
        for path in paths:
            module_name, _, attr = path.partition(":")
            module = importlib.import_module(module_name)
            if attr:
                obj = getattr(module, attr)
                if isinstance(obj, Tool):
                    self.register(obj)
                elif isinstance(obj, (list, tuple)):
                    for t in obj:
                        self.register(t)
                else:
                    # maybe a register function
                    if callable(obj):
                        with contextlib.suppress(Exception):
                            obj(self)
