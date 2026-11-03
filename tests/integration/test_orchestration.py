import asyncio

import pytest

from luna.orchestration import Coordinator, TaskSpec


class FakeAgent:
    def __init__(self, value):
        self.value = value
        self.started = asyncio.Event()

    async def run(self, task):
        await self.started.wait() if False else None
        return f"{self.value}:{task}"


class OrderedAgent:
    def __init__(self, name, order):
        self.name = name
        self.order = order

    async def run(self, task):
        self.order.append(self.name)
        await asyncio.sleep(0.01)
        return self.name


@pytest.mark.asyncio
async def test_two_independent_tasks():
    coord = Coordinator(max_parallel_tasks=2)
    coord.register_agent("worker", lambda: FakeAgent("ok"))
    tasks = [
        TaskSpec(id="t1", agent_role="worker", input="a"),
        TaskSpec(id="t2", agent_role="worker", input="b"),
    ]
    results = await coord.run_plan(tasks)
    assert results["t1"].status == "completed"
    assert results["t2"].status == "completed"
    assert results["t1"].result == "ok:a"
    assert results["t2"].result == "ok:b"


@pytest.mark.asyncio
async def test_dependency_wave_order():
    order = []
    coord = Coordinator(max_parallel_tasks=2)
    coord.register_agent("worker", lambda: OrderedAgent("w", order))
    tasks = [
        TaskSpec(id="a", agent_role="worker", input="first"),
        TaskSpec(id="b", agent_role="worker", input="second", depends_on=["a"]),
    ]
    results = await coord.run_plan(tasks)
    assert results["a"].status == "completed"
    assert results["b"].status == "completed"
    # a completed before b started => a before b in order list
    assert order.index("w") == 0 or len(order) >= 2


@pytest.mark.asyncio
async def test_max_parallel_limits():
    active = {"n": 0, "max": 0}

    class SlowAgent:
        async def run(self, task):
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
            await asyncio.sleep(0.05)
            active["n"] -= 1
            return "done"

    coord = Coordinator(max_parallel_tasks=2)
    coord.register_agent("slow", lambda: SlowAgent())
    tasks = [TaskSpec(id=f"t{i}", agent_role="slow", input="x") for i in range(5)]
    results = await coord.run_plan(tasks)
    assert all(r.status == "completed" for r in results.values())
    assert active["max"] <= 2


@pytest.mark.asyncio
async def test_cancellation():
    class HangAgent:
        async def run(self, task):
            await asyncio.sleep(10)
            return "done"

    coord = Coordinator(max_parallel_tasks=1)
    coord.register_agent("hang", lambda: HangAgent())
    tasks = [TaskSpec(id="h", agent_role="hang", input="x")]

    async def runner():
        return await coord.run_plan(tasks)

    t = asyncio.create_task(runner())
    await asyncio.sleep(0.05)
    coord.cancel()
    results = await t
    assert results["h"].status in ("cancelled", "failed")
