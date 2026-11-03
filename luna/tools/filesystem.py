"""Filesystem tools for Luna Runtime (READ/WRITE/DELETE with path guard)."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from luna.permissions.permissions import PermissionLevel
from luna.tools.base import Tool, ToolResult, ToolSpec

WORKDIR_ENV = "LUNA_WORKDIR"


class FsListInput(BaseModel):
    path: str = "."
    recursive: bool = False


class FsReadInput(BaseModel):
    path: str
    encoding: str = "utf-8"


class FsSearchInput(BaseModel):
    query: str
    path: str = "."
    recursive: bool = True


class FsWriteInput(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"


class FsDeleteInput(BaseModel):
    path: str
    recursive: bool = False


def _allowed_root(kwargs: dict[str, Any]) -> Path:
    root = kwargs.get("allowed_root") or kwargs.get("workdir")
    if root is None:
        env = os.getenv(WORKDIR_ENV)
        if env:
            root = env
    if root is None:
        try:
            from luna.core.config import load_config

            cfg = load_config()
            wd = getattr(cfg.execution, "workdir", None)
            if wd:
                root = wd
        except Exception:
            root = None
    if root is None:
        root = os.getcwd()
    return Path(root).expanduser().resolve()


def resolve_inside_root(user_path: str, root: Path) -> Path:
    """Resolve user_path inside root; raise ValueError on traversal."""
    root = Path(root).resolve()
    # Treat absolute paths as relative to root if under root; block escape.
    candidate = Path(user_path)
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("path traversal blocked") from exc
    return target


class _FsTool(Tool):
    kind: str = ""

    def _root(self, kwargs: dict[str, Any]) -> Path:
        return _allowed_root({**self.kwargs, **kwargs})

    def _params(self, args: dict[str, Any]) -> dict[str, Any]:
        # merge positional dict
        return args


class FsListTool(_FsTool):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            ToolSpec(
                id="fs_list",
                name="fs_list",
                description="List files in a directory within allowed root",
                input_schema=FsListInput,
                permissions=[PermissionLevel.READ],
                risk_level="low",
                timeout=30,
            ),
            **kwargs,
        )

    def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        params = dict(args[0]) if args and isinstance(args[0], dict) else kwargs
        valid = self.validate(params)
        root = self._root(params)
        target = resolve_inside_root(valid["path"], root)
        if not target.exists() or not target.is_dir():
            return ToolResult(ok=False, error=f"not a directory: {valid['path']}")
        entries = []
        if valid.get("recursive"):
            for p in target.rglob("*"):
                with contextlib.suppress(ValueError):
                    entries.append(str(p.relative_to(root)))
        else:
            for p in target.iterdir():
                entries.append(p.name)
        return ToolResult(ok=True, output=entries, data=entries, path=str(target))


class FsReadTool(_FsTool):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            ToolSpec(
                id="fs_read",
                name="fs_read",
                description="Read a text file within allowed root",
                input_schema=FsReadInput,
                permissions=[PermissionLevel.READ],
                risk_level="low",
                timeout=30,
            ),
            **kwargs,
        )

    def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        params = dict(args[0]) if args and isinstance(args[0], dict) else kwargs
        valid = self.validate(params)
        root = self._root(params)
        target = resolve_inside_root(valid["path"], root)
        if not target.is_file():
            return ToolResult(ok=False, error=f"not a file: {valid['path']}")
        try:
            content = target.read_text(encoding=valid.get("encoding", "utf-8"))
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(ok=True, output=content, data=content, path=str(target))


class FsSearchTool(_FsTool):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            ToolSpec(
                id="fs_search",
                name="fs_search",
                description="Search file names/content within allowed root",
                input_schema=FsSearchInput,
                permissions=[PermissionLevel.READ],
                risk_level="low",
                timeout=60,
            ),
            **kwargs,
        )

    def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        params = dict(args[0]) if args and isinstance(args[0], dict) else kwargs
        valid = self.validate(params)
        root = self._root(params)
        base = resolve_inside_root(valid.get("path", "."), root)
        q = valid["query"].lower()
        matches: list[str] = []
        try:
            for p in base.rglob("*"):
                if not p.is_file():
                    continue
                try:
                    rel = str(p.relative_to(root))
                except ValueError:
                    continue
                if q in p.name.lower():
                    matches.append(rel)
                    continue
                try:
                    text = p.read_text(errors="ignore")
                except Exception:
                    text = ""
                if q in text.lower():
                    matches.append(rel)
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(ok=True, output=matches, data=matches, path=str(base))


class FsWriteTool(_FsTool):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            ToolSpec(
                id="fs_write",
                name="fs_write",
                description="Write a text file within allowed root",
                input_schema=FsWriteInput,
                permissions=[PermissionLevel.WRITE],
                risk_level="medium",
                timeout=30,
            ),
            **kwargs,
        )

    def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        params = dict(args[0]) if args and isinstance(args[0], dict) else kwargs
        valid = self.validate(params)
        root = self._root(params)
        target = resolve_inside_root(valid["path"], root)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(valid["content"], encoding=valid.get("encoding", "utf-8"))
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(ok=True, output=str(target), data=str(target), path=str(target))


class FsDeleteTool(_FsTool):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            ToolSpec(
                id="fs_delete",
                name="fs_delete",
                description="Delete a file (requires approval) within allowed root",
                input_schema=FsDeleteInput,
                permissions=[PermissionLevel.DELETE],
                risk_level="high",
                timeout=30,
            ),
            **kwargs,
        )

    def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        params = dict(args[0]) if args and isinstance(args[0], dict) else kwargs
        valid = self.validate(params)
        root = self._root(params)
        target = resolve_inside_root(valid["path"], root)
        if not target.exists():
            return ToolResult(ok=False, error=f"not found: {valid['path']}")
        try:
            if target.is_dir():
                if valid.get("recursive"):
                    import shutil

                    shutil.rmtree(target)
                else:
                    target.rmdir()
            else:
                target.unlink()
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(ok=True, output=str(target), data=str(target), path=str(target))


# convenience functions
def fs_list(path: str = ".", **kwargs: Any) -> ToolResult:
    return FsListTool(**kwargs).execute(path=path)


def fs_read(path: str, **kwargs: Any) -> ToolResult:
    return FsReadTool(**kwargs).execute(path=path)


def fs_search(query: str, **kwargs: Any) -> ToolResult:
    return FsSearchTool(**kwargs).execute(query=query)


def fs_write(path: str, content: str, **kwargs: Any) -> ToolResult:
    return FsWriteTool(**kwargs).execute(path=path, content=content)


def fs_delete(path: str, **kwargs: Any) -> ToolResult:
    return FsDeleteTool(**kwargs).execute(path=path)


def register_defaults(registry: Any = None, **kwargs: Any) -> Any:
    from luna.tools.base import ToolRegistry

    if registry is None:
        registry = ToolRegistry()
    for cls in (FsListTool, FsReadTool, FsSearchTool, FsWriteTool, FsDeleteTool):
        registry.register(cls(**kwargs))
    return registry


DEFAULT_TOOLS = [FsListTool, FsReadTool, FsSearchTool, FsWriteTool, FsDeleteTool]