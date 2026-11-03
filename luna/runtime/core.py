from __future__ import annotations

import contextlib
import os
from typing import Any

from luna.core.config import Settings, load_config
from luna.core.events import Event, SimpleEventBus


class LunaRuntime:
    def __init__(
        self,
        config: Settings | None = None,
        *,
        config_path: str | None = None,
    ) -> None:
        self.config: Settings = config if config is not None else load_config(config_path)
        self.event_bus: SimpleEventBus = SimpleEventBus()
        self.providers: dict[str, Any] = {}
        self.agents: dict[str, Any] = {}
        from luna.models.gateway import ModelGateway
        from luna.permissions.permissions import ExecutionMode, PermissionEngine
        from luna.sessions.manager import SessionManager
        from luna.tools.base import ToolRegistry
        self.gateway: ModelGateway = ModelGateway()
        self.tool_registry: ToolRegistry = ToolRegistry()
        self.permission_engine: PermissionEngine = PermissionEngine(mode=ExecutionMode.CONTROLLED)
        self.session_manager: SessionManager = SessionManager()
        self.provider_status: dict[str, str] = {}
        self._register_providers_from_config()
        try:
            self.gateway.timeout = max(getattr(self.gateway, "timeout", 30.0) or 30.0, float(getattr(getattr(self.config, "execution", None), "timeout_seconds", 0) or 0))
        except Exception:
            pass
        try:
            from luna.tools.filesystem import register_fs_defaults
            from luna.tools.git import register_git_defaults
            from luna.tools.terminal import register_terminal_defaults
            register_fs_defaults(self.tool_registry, workdir=self.config.execution.workdir)
            register_terminal_defaults(self.tool_registry, workdir=self.config.execution.workdir)
            register_git_defaults(self.tool_registry, permission_engine=self.permission_engine, workdir=self.config.execution.workdir)
        except Exception:
            pass
        self._register_agents_from_config()

    async def start(self) -> None:
        await self.event_bus.emit(
            Event(type="runtime.start", payload={"name": self.config.runtime.name})
        )

    def register_provider(self, name: str, provider: Any) -> None:
        self.providers[name] = provider
        with contextlib.suppress(Exception):
            self.gateway.register_provider(provider)
        ptimeout = getattr(provider, "timeout", None)
        if isinstance(ptimeout, (int, float)):
            self.gateway.timeout = max(getattr(self.gateway, "timeout", 30.0) or 30.0, float(ptimeout))

    async def register_provider_async(self, name: str, provider: Any) -> None:
        self.providers[name] = provider
        with contextlib.suppress(Exception):
            self.gateway.register_provider(provider)
        await self.event_bus.emit(Event(type="provider.registered", payload={"name": name}))

    # ---- provider loading from config ----
    @staticmethod
    def _normalize_provider_specs(providers: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if providers is None:
            return out
        if isinstance(providers, dict):
            for name, value in providers.items():
                spec = value if isinstance(value, dict) else {"base_url": value}
                spec = dict(spec or {})
                spec.setdefault("name", name)
                out.append(spec)
            return out
        if isinstance(providers, (list, tuple)):
            for item in providers:
                if isinstance(item, str):
                    if "://" in item:
                        out.append({"name": item, "base_url": item})
                    else:
                        out.append({"name": item, "type": item})
                elif isinstance(item, dict):
                    out.append(dict(item))
                else:
                    try:
                        out.append(dict(item))
                    except Exception:
                        try:
                            out.append(item.model_dump())
                        except Exception:
                            out.append({"name": str(item)})
            return out
        try:
            return LunaRuntime._normalize_provider_specs(list(providers))
        except Exception:
            return out

    @staticmethod
    def _provider_type(spec: dict[str, Any]) -> str:
        kind = str(spec.get("type") or spec.get("kind") or spec.get("provider") or "").lower().strip()
        name = str(spec.get("name") or "").lower()
        base = str(spec.get("base_url") or spec.get("url") or "").lower()
        if kind in ("ollama",):
            return "ollama"
        if kind in ("anthropic",):
            return "anthropic"
        if kind in ("openai", "openai-compatible", "openai_compat", "openai compatible", "compatible"):
            return "openai"
        if "anthropic" in name:
            return "anthropic"
        if "ollama" in name or "11434" in base:
            return "ollama"
        if kind == "":
            # infer
            if "anthropic" in name:
                return "anthropic"
            if "ollama" in name or "11434" in base:
                return "ollama"
        if kind:
            return kind
        return "openai"

    def _instantiate_provider(self, spec: dict[str, Any]) -> tuple[str, Any] | None:
        name = str(spec.get("name") or spec.get("id") or "").strip()
        kind = self._provider_type(spec)
        if kind == "ollama":
            if not name:
                name = "ollama"
            base_url = spec.get("base_url") or spec.get("url") or "http://localhost:11434"
            timeout = spec.get("timeout", 30.0)
            from luna.providers.ollama import OllamaProvider

            provider = OllamaProvider(base_url=str(base_url), name=name, timeout=float(timeout or 30.0))
            return name, provider
        if kind in ("openai", "openai-compatible", "openai_compat", "compatible"):
            if not name:
                name = "openai-compatible"
            base_url = spec.get("base_url") or spec.get("url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
            timeout = spec.get("timeout", 30.0)
            api_key = spec.get("api_key")
            api_key_env = spec.get("api_key_env") or spec.get("env")
            if api_key is None and isinstance(api_key_env, str):
                api_key = os.getenv(api_key_env)
            if api_key is None:
                default_env = spec.get("api_key_env_default", "OPENAI_API_KEY")
                api_key = os.getenv(str(default_env), None)
            if api_key is None:
                api_key = os.getenv("OPENAI_API_KEY", None)
            from luna.providers.openai_compat import OpenAICompatibleProvider

            provider = OpenAICompatibleProvider(base_url=str(base_url), name=name, api_key=api_key, timeout=float(timeout or 30.0))
            return name, provider
        if kind == "anthropic":
            self.provider_status[name or "anthropic"] = "not available (not implemented)"
            return None
        return None

    def _register_providers_from_config(self) -> None:
        providers = getattr(getattr(self.config, "models", None), "providers", None)
        for spec in self._normalize_provider_specs(providers):
            try:
                result = self._instantiate_provider(spec)
            except Exception as exc:
                nm = str(spec.get("name") or "provider")
                self.provider_status[nm] = f"error: {exc}"
                continue
            if result is None:
                continue
            name, provider = result
            try:
                self.register_provider(name, provider)
                self.provider_status[name] = "registered"
            except Exception as exc:
                self.provider_status[name] = f"error: {exc}"

    def _normalize_agent_spec(self, spec: Any) -> dict[str, Any] | None:
        if spec is None:
            return None
        if isinstance(spec, dict):
            data = dict(spec)
        elif hasattr(spec, "model_dump"):
            data = spec.model_dump()
        else:
            try:
                data = dict(spec)
            except Exception:
                try:
                    data = spec.__dict__
                except Exception:
                    return None
        if "name" not in data and "id" in data:
            data["name"] = data.get("id")
        if not data.get("name"):
            return None
        # map id alias
        if "id" not in data:
            data["id"] = data.get("name")
        return data

    def _register_agents_from_config(self) -> None:
        agents = getattr(self.config, "agents", None)
        if not agents:
            return
        for spec in agents:
            data = self._normalize_agent_spec(spec)
            if not data:
                continue
            try:
                self.create_agent(
                    data,
                    gateway=self.gateway,
                    tool_registry=self.tool_registry,
                    permission_engine=self.permission_engine,
                    session_manager=self.session_manager,
                )
            except Exception:
                continue

    async def load_providers(self) -> dict[str, Any]:
        # reset
        self.providers.clear()
        try:
            self.gateway.providers.clear()
            self.gateway._order.clear()
        except Exception:
            pass
        self.provider_status.clear()
        self._register_providers_from_config()
        try:
            self.gateway.timeout = max(getattr(self.gateway, "timeout", 30.0) or 30.0, float(getattr(getattr(self.config, "execution", None), "timeout_seconds", 0) or 0))
        except Exception:
            pass
        await self.event_bus.emit(
            Event(type="providers.loaded", payload={"providers": list(self.providers.keys())})
        )
        return self.providers

    def create_agent(self, config: Any, **kwargs: Any) -> Any:
        from luna.agents import Agent, AgentConfig
        from luna.context.engine import ContextEngine
        from luna.permissions.permissions import PermissionEngine
        from luna.sessions.manager import SessionManager
        from luna.tools.base import ToolRegistry

        if isinstance(config, dict):
            config = AgentConfig.model_validate(config)
        # resolve default model alias
        try:
            if getattr(config, "model", None) == "default":
                config.model = self.config.models.default
        except Exception:
            pass
        gateway = kwargs.get("gateway")
        if gateway is None:
            gateway = self.gateway
        tool_registry = kwargs.get("tool_registry") or kwargs.get("tools") or ToolRegistry()
        permission_engine = kwargs.get("permission_engine") or kwargs.get("permissions") or PermissionEngine()
        session_manager = kwargs.get("session_manager") or kwargs.get("sessions") or SessionManager()
        context_engine = kwargs.get("context_engine") or kwargs.get("context") or ContextEngine(default_budget_tokens=getattr(config, "context_limit_tokens", 8000))
        agent = Agent(
            config,
            gateway=gateway,
            tool_registry=tool_registry,
            permission_engine=permission_engine,
            session_manager=session_manager,
            context_engine=context_engine,
            **{k: v for k, v in kwargs.items() if k not in ("gateway", "tool_registry", "tools", "permission_engine", "permissions", "session_manager", "sessions", "context_engine", "context")},
        )
        self.agents[config.name] = agent
        return agent

    async def shutdown(self) -> None:
        await self.event_bus.emit(
            Event(type="runtime.stop", payload={"name": self.config.runtime.name})
        )

    async def __aenter__(self) -> LunaRuntime:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        await self.shutdown()
        return False


__all__ = ["LunaRuntime"]
