from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class AgentCreateBody(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    model: str = "default"
    fallback_model: str | None = None
    tools: list[str] = []
    permissions: list[Any] = []
    max_iterations: int = 10
    context_limit_tokens: int = 8000
    memory_enabled: bool = True
    extra: dict[str, Any] = {}


class SessionCreateBody(BaseModel):
    id: str | None = None
    agent_name: str | None = None
    metadata: dict[str, Any] = {}


class RunBody(BaseModel):
    task: str
    session_id: str | None = None


class ApprovalDecisionBody(BaseModel):
    decision: Any = True
    approved: bool | None = None


def _agent_payload(agent: Any) -> dict[str, Any]:
    cfg = getattr(agent, "config", None)
    return {
        "id": getattr(cfg, "name", None),
        "name": getattr(cfg, "name", None),
        "description": getattr(cfg, "description", ""),
        "model": getattr(cfg, "model", "default"),
        "tools": getattr(cfg, "tools", []),
        "max_iterations": getattr(cfg, "max_iterations", 10),
    }


def create_app(runtime: Any) -> FastAPI:
    app = FastAPI(title="Luna Runtime", version="0.1.0")
    metrics: dict[str, int] = {"requests": 0, "errors": 0, "runs": 0}

    @app.middleware("http")
    async def _count(request, call_next):
        metrics["requests"] += 1
        try:
            response = await call_next(request)
            return response
        except Exception:
            metrics["errors"] += 1
            raise

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "luna-runtime"}

    @app.get("/v1/models")
    async def list_models():
        gw = getattr(runtime, "gateway", None)
        if gw is None:
            from luna.models.gateway import ModelGateway

            gw = ModelGateway(providers=list(runtime.providers.values()))
        try:
            models = await gw.list_models()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"providers": models}

    @app.get("/v1/tools")
    def list_tools():
        reg = getattr(runtime, "tool_registry", None)
        tools = []
        if reg is not None and hasattr(reg, "list_specs"):
            for spec in reg.list_specs():
                tools.append(
                    {
                        "id": spec.id,
                        "name": spec.name,
                        "description": spec.description,
                        "risk_level": getattr(spec, "risk_level", "low"),
                    }
                )
        return {"tools": tools}

    @app.get("/v1/agents")
    def list_agents():
        agents = list(runtime.agents.values())
        return {"agents": [_agent_payload(a) for a in agents]}

    @app.post("/v1/agents", status_code=201)
    def create_agent(body: AgentCreateBody):
        config_dict = body.model_dump(exclude={"extra"})
        config_dict.update(body.extra or {})
        agent = runtime.create_agent(config_dict)
        return _agent_payload(agent)

    @app.get("/v1/agents/{agent_id}")
    def get_agent(agent_id: str):
        agent = runtime.agents.get(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="agent not found")
        return _agent_payload(agent)

    @app.post("/v1/agents/{agent_id}/run")
    async def run_agent(agent_id: str, body: RunBody):
        agent = runtime.agents.get(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="agent not found")
        metrics["runs"] += 1
        try:
            result = await agent.run(body.task, session_id=body.session_id)
        except Exception as exc:
            metrics["errors"] += 1
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        return data

    @app.get("/v1/sessions")
    async def list_sessions():
        sm = getattr(runtime, "session_manager", None)
        if sm is None:
            return {"sessions": []}
        await sm.init()
        rows = await sm.list_sessions()
        return {"sessions": [r.to_dict() if hasattr(r, "to_dict") else r for r in rows]}

    @app.post("/v1/sessions", status_code=201)
    async def create_session(body: SessionCreateBody):
        sm = getattr(runtime, "session_manager", None)
        if sm is None:
            raise HTTPException(status_code=500, detail="no session manager")
        await sm.init()
        sid = await sm.create_session(session_id=body.id, agent_name=body.agent_name, metadata=body.metadata)
        return {"id": sid}

    @app.get("/v1/sessions/{session_id}")
    async def get_session(session_id: str):
        sm = getattr(runtime, "session_manager", None)
        if sm is None:
            raise HTTPException(status_code=500, detail="no session manager")
        await sm.init()
        rec = await sm.get_session(session_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="session not found")
        msgs = await sm.get_messages(session_id)
        data = rec.to_dict() if hasattr(rec, "to_dict") else rec
        data["messages"] = [m.model_dump() if hasattr(m, "model_dump") else m for m in msgs]
        return data

    @app.get("/v1/approvals")
    def list_approvals():
        out = []
        engines = [getattr(runtime, "permission_engine", None)]
        for a in runtime.agents.values():
            pe = getattr(a, "permission_engine", None)
            if pe is not None:
                engines.append(pe)
        for pe in engines:
            if pe is None:
                continue
            for aid, req in getattr(pe, "approvals", {}).items():
                out.append(
                    {
                        "id": aid,
                        "tool": getattr(req, "tool", None),
                        "args": getattr(req, "args", {}),
                        "resolved": getattr(req, "resolved", None),
                    }
                )
        # deduplicate
        seen = set()
        uniq = []
        for item in out:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            uniq.append(item)
        return {"approvals": uniq}

    @app.post("/v1/approvals/{approval_id}/decision")
    def decide_approval(approval_id: str, body: ApprovalDecisionBody):
        decision = body.approved if body.approved is not None else body.decision
        engines = [getattr(runtime, "permission_engine", None)]
        for a in runtime.agents.values():
            pe = getattr(a, "permission_engine", None)
            if pe is not None:
                engines.append(pe)
        found = False
        for pe in engines:
            if pe is None:
                continue
            req = pe.resolve(approval_id, decision)
            if req is not None:
                found = True
        if not found:
            raise HTTPException(status_code=404, detail="approval not found")
        return {"id": approval_id, "decision": decision}

    @app.get("/v1/metrics")
    def metrics_endpoint():
        return metrics

    app.state.metrics = metrics
    return app


__all__ = ["create_app"]
