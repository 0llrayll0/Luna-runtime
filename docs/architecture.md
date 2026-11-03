# Arquitetura — Luna Runtime

Camadas (código real em `luna/`):

- `core/` — `Settings` (YAML/env), validação via Pydantic; path `~/.luna/config.yaml`.
- `runtime/core.py` — `LunaRuntime`: agrega providers, agents, tool_registry, permission_engine, session_manager, gateway, event_bus.
- `models/` — `ModelGateway` + providers (`ollama`, `openai_compat`, `anthropic` (stub), base). schemas de request/response.
- `agents/` — `Agent` ciclo de execução (`run`), `AgentConfig`, `AgentResult`. Integra context, tools, permissions, sessions.
- `context/` — `ContextEngine` (truncagem por budget de tokens).
- `sessions/` — `SessionManager` SQLite (aiosqlite) com histórico de mensagens.
- `tools/` — `ToolRegistry`, `ToolSpec`, tools de filesystem/git/terminal; risco e permissões.
- `permissions/` — `PermissionEngine`, `ExecutionMode` (READ/WRITE/EXECUTE/...).
- `events/` — `SimpleEventBus`.
- `mcp/` — cliente STDIO + manager; descoberta de tools MCP.
- `orchestration/` — roles e orchestrator (waves/paralelismo/cancelamento).
- `api/` — FastAPI (`/health`, models, agents, sessions, tools, metrics), factory `create_app`.
- `sdk/` — cliente Python assíncrono.
- `cli/` — Typer CLI.

Fluxo de execução:
1. CLI/API recebe tarefa.
2. `LunaRuntime` fornece agent + registry + gateway.
3. `Agent.run` cria/reutiliza sessão, monta mensagens, chama gateway.
4. Se tool_calls, valida permissão, executa tool, anexa resultado, repete até stop ou max_iterations.
5. Retorna `AgentResult` com output/iterations/tool_calls/usage/session_id.

Persistência local: SQLite (sessões) e arquivos de config em `~/.luna`. MCP sob demanda.

Limites atuais: ver README (sandbox subprocess; MCP HTTP pendente; SSE pendente).