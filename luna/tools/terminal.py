"""Terminal tool for Luna Runtime (subprocess with timeout, no shell=True)."""

from __future__ import annotations

import contextlib
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from luna.permissions.permissions import PermissionLevel
from luna.tools.base import Tool, ToolResult, ToolSpec

DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    ":(){",
    "shutdown",
    "reboot",
    "halt",
    "> /dev/sda",
    "chmod -r 777 /",
]


def _allowed_root(kwargs: dict[str, Any]) -> Path:
    root = kwargs.get("allowed_root") or kwargs.get("workdir")
    if root is None:
        env = os.getenv("LUNA_WORKDIR")
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


def _is_blocked(command: list[str]) -> bool:
    joined = " ".join(command).lower()
    return any(pat.lower() in joined for pat in DANGEROUS_PATTERNS)


class TerminalRunInput(BaseModel):
    command: Any
    timeout: int | float = 30
    cwd: str = "."


class TerminalRunTool(Tool):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            ToolSpec(
                id="terminal_run",
                name="terminal_run",
                description="Run a command capturing stdout/stderr/returncode with timeout",
                input_schema=TerminalRunInput,
                permissions=[PermissionLevel.EXECUTE],
                risk_level="high",
                timeout=60,
            ),
            **kwargs,
        )

    def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        params = dict(args[0]) if args and isinstance(args[0], dict) else kwargs
        valid = self.validate(params)
        raw_cmd = valid["command"]
        command = shlex.split(raw_cmd) if isinstance(raw_cmd, str) else list(raw_cmd)
        if not command:
            return ToolResult(ok=False, error="empty command")
        if _is_blocked(command):
            return ToolResult(ok=False, error="command blocked by safety policy", returncode=-1)

        root = _allowed_root({**self.kwargs, **params})
        cwd_raw = valid.get("cwd", ".")
        try:
            from luna.tools.filesystem import resolve_inside_root

            cwd = resolve_inside_root(cwd_raw, root)
        except ValueError:
            return ToolResult(ok=False, error="cwd outside allowed root")
        if not cwd.is_dir():
            return ToolResult(ok=False, error=f"not a directory: {cwd_raw}")

        timeout = float(valid.get("timeout", self.kwargs.get("timeout", 30)) or 30)

        proc = None
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                return ToolResult(
                    ok=False,
                    error="timeout",
                    stdout=stdout or "",
                    stderr=stderr or "",
                    returncode=proc.returncode if proc.returncode is not None else -1,
                    data={"stdout": stdout or "", "stderr": stderr or "", "returncode": -1, "timeout": True},
                )
            rc = proc.returncode
            return ToolResult(
                ok=(rc == 0),
                output=stdout,
                error=None if rc == 0 else stderr,
                stdout=stdout,
                stderr=stderr,
                returncode=rc,
                path=str(cwd),
                data={"stdout": stdout, "stderr": stderr, "returncode": rc},
            )
        except Exception as exc:
            if proc is not None:
                with contextlib.suppress(Exception):
                    proc.kill()
            return ToolResult(ok=False, error=str(exc), returncode=-1)


def terminal_run(command: Any, **kwargs: Any) -> ToolResult:
    return TerminalRunTool(**kwargs).execute(command=command)


def register_defaults(registry: Any = None, **kwargs: Any) -> Any:
    if registry is None:
        from luna.tools.base import ToolRegistry

        registry = ToolRegistry()
    registry.register(TerminalRunTool(**kwargs))
    return registry