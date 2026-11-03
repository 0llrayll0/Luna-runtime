from __future__ import annotations

from pathlib import Path

import pytest

from luna.tools.base import ToolRegistry
from luna.tools.filesystem import (
    FsDeleteTool,
    FsReadTool,
    FsWriteTool,
    resolve_inside_root,
)
from luna.tools.terminal import TerminalRunTool


def test_traversal_blocked(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError):
        resolve_inside_root("../escape.txt", root)
    with pytest.raises(ValueError):
        resolve_inside_root("/etc/passwd", root)


def test_fs_roundtrip(tmp_path: Path) -> None:
    tool = FsWriteTool(workdir=str(tmp_path))
    r = tool.execute(path="a.txt", content="hello")
    assert r.ok
    r2 = FsReadTool(workdir=str(tmp_path)).execute(path="a.txt")
    assert r2.output == "hello"


def test_terminal_timeout(tmp_path: Path) -> None:
    t = TerminalRunTool(workdir=str(tmp_path))
    r = t.execute(command=["sleep", "5"], timeout=0.1)
    assert r.ok is False
    assert "timeout" in (r.error or "").lower()


def test_terminal_blocked(tmp_path: Path) -> None:
    t = TerminalRunTool(workdir=str(tmp_path))
    r = t.execute(command="rm -rf /")
    assert r.ok is False
    assert "blocked" in (r.error or "").lower()


def test_list_and_registry(tmp_path: Path) -> None:
    reg = ToolRegistry()
    from luna.tools.filesystem import register_defaults as regfs

    regfs(reg, workdir=str(tmp_path))
    assert reg.get("fs_list") is not None
    (tmp_path / "x.txt").write_text("x")
    r = reg.execute("fs_list", {"path": "."})
    assert r.ok
    assert "x.txt" in r.output


def test_fs_delete_requires_permissionhandled_by_engine(tmp_path: Path) -> None:
    p = tmp_path / "del.txt"
    p.write_text("x")
    r = FsDeleteTool(workdir=str(tmp_path)).execute(path="del.txt")
    assert r.ok
    assert not p.exists()