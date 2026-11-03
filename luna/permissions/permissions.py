"""Permission engine for Luna Runtime.

Execution is NOT truly sandboxed: subprocesses run on the host. This module only
applies policy gating, allowlists and (for tools) timeout/cwd restrictions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PermissionLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    NETWORK = "network"
    ADMIN = "admin"


class ExecutionMode(StrEnum):
    RESTRICTED = "restricted"
    CONTROLLED = "controlled"
    TRUSTED = "trusted"


HIGH_RISK = {PermissionLevel.EXECUTE, PermissionLevel.DELETE, PermissionLevel.NETWORK}


@dataclass
class Policy:
    mode: ExecutionMode = ExecutionMode.CONTROLLED
    allowed_tools: set[str] = field(default_factory=set)
    denied_tools: set[str] = field(default_factory=set)
    allowed_permissions: set[PermissionLevel] = field(default_factory=set)
    allowed: set[str] = field(default_factory=set)
    denied: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.allowed:
            self.allowed_tools |= self.allowed
        if self.denied:
            self.denied_tools |= self.denied


@dataclass
class ApprovalRequest:
    id: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    level: PermissionLevel | None = None
    reason: str = ""
    resolved: bool | None = None
    decision: Any = None

    def resolve(self, decision: Any) -> None:
        if isinstance(decision, bool):
            self.resolved = decision
        elif isinstance(decision, str):
            lowered = decision.lower()
            self.resolved = lowered in ("allow", "allowed", "approve", "approved", "yes", "true", "1")
        else:
            self.resolved = bool(decision)
        self.decision = decision


@dataclass
class Allow:
    reason: str = "allowed"


@dataclass
class Deny:
    reason: str = "denied"


@dataclass
class PendingApproval:
    request: ApprovalRequest
    reason: str = "pending approval"


class PermissionEngine:
    def __init__(
        self,
        mode: ExecutionMode | str = ExecutionMode.CONTROLLED,
        policy: Policy | None = None,
        allowed_tools: set[str] | None = None,
        denied_tools: set[str] | None = None,
        allowed_permissions: set[PermissionLevel] | None = None,
        allowed: set[str] | None = None,
        denied: set[str] | None = None,
    ) -> None:
        self.mode = mode if isinstance(mode, ExecutionMode) else ExecutionMode(mode)
        self.policy = policy or Policy(mode=self.mode)
        if self.policy.mode != self.mode:
            self.policy.mode = self.mode
        if allowed_tools:
            self.policy.allowed_tools |= set(allowed_tools)
        if denied_tools:
            self.policy.denied_tools |= set(denied_tools)
        if allowed_permissions:
            self.policy.allowed_permissions |= set(allowed_permissions)
        if allowed:
            self.policy.allowed_tools |= set(allowed)
        if denied:
            self.policy.denied_tools |= set(denied)
        self.approvals: dict[str, ApprovalRequest] = {}

    def _normalize_level(self, level: Any) -> PermissionLevel:
        if isinstance(level, PermissionLevel):
            return level
        return PermissionLevel(str(level).lower())

    def _levels(self, permissions_required: Any) -> set[PermissionLevel]:
        if permissions_required is None:
            return set()
        if isinstance(permissions_required, PermissionLevel):
            return {permissions_required}
        if isinstance(permissions_required, str):
            return {self._normalize_level(x.strip()) for x in permissions_required.split(",") if x.strip()}
        if isinstance(permissions_required, (list, tuple, set, frozenset)):
            return {self._normalize_level(x) for x in permissions_required}
        return {self._normalize_level(permissions_required)}

    def check(
        self,
        tool: str,
        permissions_required: Any = None,
        args: dict[str, Any] | None = None,
        level: Any = None,
    ) -> Any:
        args = args or {}
        levels = self._levels(permissions_required)
        if level is not None:
            levels |= self._levels(level)

        if tool in self.policy.denied_tools:
            return Deny(reason=f"tool {tool} denied by policy")

        if self.mode == ExecutionMode.RESTRICTED:
            if tool not in self.policy.allowed_tools:
                return Deny(reason=f"tool {tool} not explicitly allowed (restricted)")
            if levels and not levels.issubset(self.policy.allowed_permissions):
                return Deny(reason=f"permissions {levels} not explicitly allowed (restricted)")
            return Allow(reason="explicitly allowed")

        if self.mode == ExecutionMode.TRUSTED:
            if tool not in self.policy.allowed_tools and self.policy.allowed_tools:
                return Deny(reason=f"tool {tool} not in allowed set (trusted)")
            if levels and self.policy.allowed_permissions and not levels.issubset(self.policy.allowed_permissions):
                return Deny(reason=f"permissions {levels} not in allowed set (trusted)")
            return Allow(reason="trusted auto-approve")

        # CONTROLLED
        needs_approval = bool(levels & HIGH_RISK)
        explicitly_allowed = tool in self.policy.allowed_tools and (
            not levels or levels.issubset(self.policy.allowed_permissions)
        )
        if needs_approval and not explicitly_allowed:
            req = ApprovalRequest(
                id=str(uuid.uuid4()),
                tool=tool,
                args=dict(args),
                level=next(iter(levels & HIGH_RISK)) if (levels & HIGH_RISK) else (next(iter(levels)) if levels else None),
                reason=f"approval required for {sorted(perm.value for perm in (levels & HIGH_RISK)) or sorted(perm.value for perm in levels)}",
            )
            self.approvals[req.id] = req
            return PendingApproval(request=req, reason=req.reason)
        return Allow(reason="allowed by controlled policy")

    def resolve(self, approval_id: Any, decision: Any = None) -> ApprovalRequest | None:
        if isinstance(approval_id, ApprovalRequest):
            req = approval_id
            if decision is not None:
                req.resolve(decision)
            # mirror into store if present
            self.approvals[req.id] = req
            return req
        # support resolve(decision) called on store entry externally; allow positional decision as first? 
        req = self.approvals.get(str(approval_id))
        if req is None:
            # maybe approval_id is a decision and there is a single pending?
            if decision is None and len(self.approvals) == 1:
                req = next(iter(self.approvals.values()))
                req.resolve(approval_id)
                return req
            return None
        if decision is not None:
            req.resolve(decision)
        return req

    def is_approved(self, approval_id: str) -> bool:
        req = self.approvals.get(approval_id)
        if req is None:
            return False
        return req.resolved is True