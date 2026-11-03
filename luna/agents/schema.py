from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from luna.models.schema import Usage


class AgentConfig(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    role: str = ""
    model: str = "default"
    fallback_model: str | None = None
    tools: list[str] = Field(default_factory=list)
    permissions: list[Any] = Field(default_factory=list)
    max_iterations: int = 10
    context_limit_tokens: int = 8000
    memory_enabled: bool = True


class AgentResult(BaseModel):
    output: str | None = None
    iterations: int = 0
    tool_calls: list[Any] = Field(default_factory=list)
    session_id: str | None = None
    usage: Usage = Field(default_factory=Usage)
    status: str = "completed"
    approval_id: str | None = None


class AgentMaxIterationsError(Exception):
    pass


# Re-export convenience; actual Agent defined in engine.
__all__ = ["AgentConfig", "AgentResult", "AgentMaxIterationsError"]

def __getattr__(name):
    if name == "Agent":
        from luna.agents.engine import Agent as _Agent

        return _Agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["AgentConfig", "AgentResult", "AgentMaxIterationsError"]

