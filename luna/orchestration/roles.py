"""Reusable agent roles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Role:
    name: str
    prompt_suffix: str = ""
    allowed_tools: list[str] | None = None
    max_iterations: int = 10
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskSpec:
    id: str
    agent_role: str
    input: str = ""
    depends_on: list[str] = field(default_factory=list)


__all__ = ["Role", "TaskSpec"]
