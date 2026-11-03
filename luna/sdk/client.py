from __future__ import annotations

from typing import Any

from luna.agents.schema import AgentConfig
from luna.core.config import Settings
from luna.runtime.core import LunaRuntime as CoreRuntime
from luna.sdk.exceptions import LunaError


class LunaRuntime:
    """SDK wrapper around the core runtime."""

    def __init__(self, config: Settings | None = None, *, config_path: str | None = None) -> None:
        self._runtime = CoreRuntime(config=config, config_path=config_path)
        if config is None:
            # ensure loading doesn't fail
            pass

    @property
    def runtime(self) -> CoreRuntime:
        return self._runtime

    @property
    def agents(self) -> dict[str, Any]:
        return self._runtime.agents

    @property
    def providers(self) -> dict[str, Any]:
        return self._runtime.providers

    async def start(self) -> None:
        await self._runtime.start()

    async def shutdown(self) -> None:
        await self._runtime.shutdown()

    async def __aenter__(self) -> LunaRuntime:
        await self.start()
        return self

    async def __aexit__(self, *exc) -> bool:
        await self.shutdown()
        return False

    def register_provider(self, name: str, provider: Any) -> None:
        self._runtime.register_provider(name, provider)

    def create_agent(self, config: Any, **kwargs: Any) -> Any:
        try:
            return self._runtime.create_agent(config, **kwargs)
        except Exception as exc:
            raise LunaError(str(exc)) from exc

    def list_agents(self) -> list[Any]:
        return list(self._runtime.agents.values())

    async def run(
        self,
        task: str,
        *,
        agent: Any = None,
        agent_name: str | None = None,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        if agent is None and agent_name is not None:
            agent = self._runtime.agents.get(agent_name)
        if agent is None and self._runtime.agents:
            agent = next(iter(self._runtime.agents.values()))
        if agent is None:
            agent = self.create_agent(AgentConfig(name="default", model="default", **{k: v for k, v in kwargs.items()}))
        await self._runtime.start()
        try:
            return await agent.run(task, session_id=session_id)
        except Exception as exc:
            raise LunaError(str(exc)) from exc


# alias
LunaClient = LunaRuntime


__all__ = ["LunaRuntime", "LunaClient", "LunaError"]
