"""Benchmark simples de execução de agente usando MockProvider.

Roda medições reais (sem números inventados) e escreve benchmarks/results.json.
Execute: python benchmarks/run_simple.py
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

from luna.agents import Agent, AgentConfig
from luna.context.engine import ContextEngine
from luna.models.gateway import ModelGateway
from luna.permissions.permissions import ExecutionMode, PermissionEngine
from luna.sessions.manager import SessionManager
from luna.tools.base import ToolRegistry
from tests.fixtures.mock_provider import MockProvider

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks" / "results.json"
WARMUP = 5
N = 50


async def one_run() -> tuple[float, int, int]:
    provider = MockProvider()
    gw = ModelGateway(providers=[provider])
    sessions = SessionManager(db_url="sqlite+aiosqlite:///:memory:")
    await sessions.init()
    config = AgentConfig(name="bench", model="mock/m1", tools=[], max_iterations=3, context_limit_tokens=1000)
    agent = Agent(
        config,
        gateway=gw,
        tool_registry=ToolRegistry(),
        permission_engine=PermissionEngine(mode=ExecutionMode.CONTROLLED),
        session_manager=sessions,
        context_engine=ContextEngine(default_budget_tokens=1000),
    )
    start = time.perf_counter()
    result = await agent.run("ping")
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return elapsed_ms, result.iterations, provider.calls


async def main() -> dict:
    # warmup
    for _ in range(WARMUP):
        await one_run()

    latencies: list[float] = []
    iterations: list[int] = []
    provider_calls: list[int] = []
    for _ in range(N):
        ms, it, calls = await one_run()
        latencies.append(ms)
        iterations.append(it)
        provider_calls.append(calls)

    def pct(values, p):
        s = sorted(values)
        idx = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
        return s[idx]

    result = {
        "runtime": "luna-runtime",
        "provider": "MockProvider",
        "runs": N,
        "warmup": WARMUP,
        "latency_ms": {
            "min": min(latencies),
            "max": max(latencies),
            "mean": statistics.fmean(latencies),
            "median": statistics.median(latencies),
            "p95": pct(latencies, 95),
        },
        "iterations_per_run": {
            "min": min(iterations),
            "max": max(iterations),
            "mean": statistics.fmean(iterations),
        },
        "provider_calls_per_run": {
            "min": min(provider_calls),
            "max": max(provider_calls),
            "mean": statistics.fmean(provider_calls),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    asyncio.run(main())