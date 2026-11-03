"""Git tools for Luna Runtime (read-only status + gated commit)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from luna.permissions.permissions import PermissionLevel
from luna.tools.base import Tool, ToolResult, ToolSpec


def _allowed_root(kwargs: dict[str, Any]) -> Path:
    root = kwargs.get("allowed_root") or kwargs.get("workdir") or kwargs.get("cwd")
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


def _resolve_cwd(cwd_raw: str, root: Path) -> Path:
    from luna.tools.filesystem import resolve_inside_root

    return resolve_inside_root(cwd_raw, root)


class GitStatusInput(BaseModel):
    cwd: str = "."


class GitStatusTool(Tool):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            ToolSpec(
                id="git_status",
                name="git_status",
                description="Show git status (read-only)",
                input_schema=GitStatusInput,
                permissions=[PermissionLevel.READ],
                risk_level="low",
                timeout=30,
            ),
            **kwargs,
        )

    def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        params = dict(args[0]) if args and isinstance(args[0], dict) else kwargs
        valid = self.validate(params)
        root = _allowed_root({**self.kwargs, **params})
        try:
            cwd = _resolve_cwd(valid.get("cwd", "."), root)
        except ValueError:
            return ToolResult(ok=False, error="cwd outside allowed root")
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain=v1"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(
            ok=(proc.returncode == 0),
            output=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
            data={"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode},
            path=str(cwd),
        )


class GitCommitInput(BaseModel):
    message: str
    files: list[str] = Field(default_factory=lambda: ["."])
    cwd: str = "."
    approved: bool = False
    approval_id: str | None = None


class GitCommitTool(Tool):
    def __init__(self, permission_engine: Any = None, **kwargs: Any) -> None:
        self.permission_engine = permission_engine
        super().__init__(
            ToolSpec(
                id="git_commit",
                name="git_commit",
                description="Create a git commit (requires approval)",
                input_schema=GitCommitInput,
                permissions=[PermissionLevel.EXECUTE, PermissionLevel.WRITE],
                risk_level="high",
                timeout=60,
            ),
            **kwargs,
        )

    def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        params = dict(args[0]) if args and isinstance(args[0], dict) else kwargs
        valid = self.validate(params)
        engine = params.get("permission_engine", self.permission_engine)

        # Permission gate
        approved = bool(valid.get("approved", False))
        approval_id = valid.get("approval_id")
        if engine is not None:
            if approval_id:
                approved = approved or engine.is_approved(str(approval_id))
            else:
                decision = engine.check("git_commit", [PermissionLevel.EXECUTE, PermissionLevel.WRITE], args=params)
                from luna.permissions.permissions import Deny, PendingApproval

                if isinstance(decision, Deny):
                    return ToolResult(ok=False, error=decision.reason)
                if isinstance(decision, PendingApproval):
                    # not approved yet; request approval and stop
                    return ToolResult(
                        ok=False,
                        error="approval required",
                        data={"approval_id": decision.request.id, "pending": True},
                    )
                # Allow -> can proceed (trusted/allowed)
                approved = True

        if not approved:
            return ToolResult(ok=False, error="commit not approved")

        root = _allowed_root({**self.kwargs, **params})
        try:
            cwd = _resolve_cwd(valid.get("cwd", "."), root)
        except ValueError:
            return ToolResult(ok=False, error="cwd outside allowed root")

        files = valid.get("files") or ["."]
        # safety: resolve each file inside root
        try:
            from luna.tools.filesystem import resolve_inside_root

            resolved_files = []
            for f in files:
                resolved_files.append(str(resolve_inside_root(f, root).relative_to(root)))
        except ValueError:
            return ToolResult(ok=False, error="file path outside allowed root")

        try:
            add = subprocess.run(
                ["git", "add", *resolved_files],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if add.returncode != 0:
                return ToolResult(ok=False, error=add.stderr or "git add failed", stderr=add.stderr, returncode=add.returncode)
            commit = subprocess.run(
                ["git", "commit", "-m", valid["message"]],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(
            ok=(commit.returncode == 0),
            output=commit.stdout,
            stderr=commit.stderr,
            returncode=commit.returncode,
            data={"stdout": commit.stdout, "stderr": commit.stderr, "returncode": commit.returncode},
            path=str(cwd),
        )


def git_status(**kwargs: Any) -> ToolResult:
    return GitStatusTool(**kwargs).execute()


def git_commit(message: str, **kwargs: Any) -> ToolResult:
    return GitCommitTool(**kwargs).execute(message=message)


def register_defaults(registry: Any = None, permission_engine: Any = None, **kwargs: Any) -> Any:
    if registry is None:
        from luna.tools.base import ToolRegistry

        registry = ToolRegistry()
    registry.register(GitStatusTool(**kwargs))
    registry.register(GitCommitTool(permission_engine=permission_engine, **kwargs))
    return registry