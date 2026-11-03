"""Lightweight multi-agent orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class TaskResult:
    id: str
    status: str = "pending"
    result: Any = None
    error: str | None = None


class Coordinator:
    def __init__(self, max_parallel_tasks: int = 4):
        self.max_parallel_tasks = max_parallel_tasks
        self._factories: dict[str, Callable] = {}
        self._sem = asyncio.Semaphore(max_parallel_tasks)
        self._current: set[asyncio.Task] = set()
        self._cancelled: bool = False

    def register_agent(self, role: str, factory: Callable) -> None:
        self._factories[role] = factory

    def register_agent_factory(self, role: str, factory: Callable) -> None:
        self.register_agent(role, factory)

    def cancel(self) -> None:
        self._cancelled = True
        for t in list(self._current):
            t.cancel()

    def _get(self, t, key, default=None):
        if isinstance(t, dict):
            return t.get(key, default)
        return getattr(t, key, default)

    async def _run_one(self, spec, results: dict[str, TaskResult]) -> None:
        tid = self._get(spec, "id")
        result = results[tid]
        result.status = "running"
        factory = self._factories.get(self._get(spec, "agent_role"))
        if factory is None:
            result.status = "failed"
            result.error = f"no agent registered for role {self._get(spec, 'agent_role')}"
            return
        try:
            agent = factory()
            if asyncio.iscoroutine(agent):
                agent = await agent
            coro = agent.run(self._get(spec, "input", "")) if hasattr(agent, "run") else agent(self._get(spec, "input", ""))
            async with self._sem:
                out = await coro
            result.result = out
            result.status = "completed"
        except asyncio.CancelledError:
            result.status = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001
            result.status = "failed"
            result.error = str(exc)

    async def run_plan(self, tasks: list[Any]) -> dict[str, TaskResult]:
        self._cancelled = False
        specs = list(tasks)
        results: dict[str, TaskResult] = {}
        for t in specs:
            tid = self._get(t, "id")
            results[tid] = TaskResult(id=tid)

        remaining = list(specs)
        failed_ids: set[str] = set()
        finished: set[str] = set()
        while remaining and not self._cancelled:
            ready = []
            for t in remaining:
                tid = self._get(t, "id")
                deps = self._get(t, "depends_on", []) or []
                if all(d in finished for d in deps):
                    if any(d in failed_ids for d in deps):
                        results[tid].status = "failed"
                        results[tid].error = "dependency failed"
                        failed_ids.add(tid)
                        finished.add(tid)
                    else:
                        ready.append(t)
            remaining = [t for t in remaining if self._get(t, "id") not in finished]

            if not ready and remaining:
                for t in list(remaining):
                    tid = self._get(t, "id")
                    results[tid].status = "failed"
                    results[tid].error = "unresolvable dependencies"
                    failed_ids.add(tid)
                    finished.add(tid)
                remaining = []
                continue

            async def runner(t):
                await self._run_one(t, results)

            wave_tasks = []
            for t in ready:
                at = asyncio.create_task(runner(t))
                self._current.add(at)
                wave_tasks.append(at)
            await asyncio.gather(*wave_tasks, return_exceptions=True)
            for at in wave_tasks:
                self._current.discard(at)
            for t in ready:
                tid = self._get(t, "id")
                finished.add(tid)
                if results[tid].status == "failed":
                    failed_ids.add(tid)
            remaining = [t for t in remaining if self._get(t, "id") not in finished]

        if self._cancelled:
            for t in remaining:
                tid = self._get(t, "id")
                results[tid].status = "cancelled"
        return results


__all__ = ["Coordinator", "TaskResult"]
