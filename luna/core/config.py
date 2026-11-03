from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError


class RuntimeSettings(BaseModel):
    name: str = "luna"
    environment: str = "local"
    debug: bool = False


class ModelsSettings(BaseModel):
    default: str = "default"
    providers: list[Any] = Field(default_factory=list)


class PermissionsSettings(BaseModel):
    allow_tools: list[str] = Field(default_factory=list)
    deny_tools: list[str] = Field(default_factory=list)


class MemorySettings(BaseModel):
    backend: str = "inmemory"
    path: str | None = None


class ExecutionSettings(BaseModel):
    max_steps: int = 100
    timeout_seconds: int = 60
    workdir: str | None = None


class AgentSettings(BaseModel):
    name: str = ""
    id: str | None = None
    model: str = "default"
    role: str = ""
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    permissions: list[Any] = Field(default_factory=list)
    max_iterations: int = 10
    context_limit_tokens: int = 8000
    memory_enabled: bool = True
    fallback_model: str | None = None

    def model_post_init(self, __context: Any) -> None:  # type: ignore[override]
        if not self.name:
            self.name = self.id or "agent"
        if self.id is None:
            self.id = self.name


class Settings(BaseModel):
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    models: ModelsSettings = Field(default_factory=ModelsSettings)
    permissions: PermissionsSettings = Field(default_factory=PermissionsSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    agents: list[AgentSettings] = Field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Settings:
        return cls.model_validate(data or {})


def _resolve_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path).expanduser()
    env = os.getenv("LUNA_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".luna" / "config.yaml"


def load_config(path: str | Path | None = None) -> Settings:
    resolved = _resolve_path(path)
    data: Any = {}
    if resolved.exists():
        with resolved.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, dict):
            raise ValueError(f"config at {resolved} must contain a mapping")
        data = loaded
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid config at {resolved}: {exc}") from exc


__all__ = [
    "Settings",
    "load_config",
    "RuntimeSettings",
    "ModelsSettings",
    "PermissionsSettings",
    "MemorySettings",
    "ExecutionSettings",
    "AgentSettings",
]
