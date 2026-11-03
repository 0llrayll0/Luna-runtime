from __future__ import annotations

from luna.permissions.permissions import (
    ExecutionMode,
    PermissionEngine,
    PermissionLevel,
)


def test_restricted_denies_unallowed() -> None:
    eng = PermissionEngine(mode=ExecutionMode.RESTRICTED, allowed_tools={"t"}, allowed_permissions={PermissionLevel.READ})
    res = eng.check("t2", [PermissionLevel.READ])
    assert type(res).__name__ == "Deny"


def test_restricted_allows_explicit() -> None:
    eng = PermissionEngine(mode=ExecutionMode.RESTRICTED, allowed_tools={"t"}, allowed_permissions={PermissionLevel.READ})
    res = eng.check("t", [PermissionLevel.READ])
    assert type(res).__name__ == "Allow"


def test_controlled_approval_for_execute() -> None:
    eng = PermissionEngine(mode=ExecutionMode.CONTROLLED)
    res = eng.check("terminal_run", [PermissionLevel.EXECUTE], args={"command": ["echo", "hi"]})
    assert type(res).__name__ == "PendingApproval"
    req = res.request
    assert req.tool == "terminal_run"
    assert req.id in eng.approvals
    eng.resolve(req.id, True)
    assert eng.is_approved(req.id)


def test_controlled_auto_read() -> None:
    eng = PermissionEngine(mode=ExecutionMode.CONTROLLED)
    res = eng.check("fs_read", [PermissionLevel.READ])
    assert type(res).__name__ == "Allow"


def test_trusted_auto_approve_allowed() -> None:
    eng = PermissionEngine(mode=ExecutionMode.TRUSTED, allowed_tools={"fs_read"}, allowed_permissions={PermissionLevel.READ})
    res = eng.check("fs_read", [PermissionLevel.READ])
    assert type(res).__name__ == "Allow"


def test_trusted_denies_not_allowed() -> None:
    eng = PermissionEngine(mode=ExecutionMode.TRUSTED, allowed_tools={"fs_read"}, allowed_permissions={PermissionLevel.READ})
    res = eng.check("fs_delete", [PermissionLevel.DELETE])
    assert type(res).__name__ == "Deny"


def test_denied_tool() -> None:
    eng = PermissionEngine(mode=ExecutionMode.CONTROLLED, denied_tools={"bad"})
    res = eng.check("bad", [PermissionLevel.READ])
    assert type(res).__name__ == "Deny"


def test_approval_request_resolve() -> None:
    eng = PermissionEngine(mode=ExecutionMode.CONTROLLED)
    res = eng.check("x", [PermissionLevel.DELETE])
    req = res.request
    req.resolve(False)
    assert req.resolved is False
    assert eng.is_approved(req.id) is False