# Tools — Luna Runtime

## Registry
`luna/tools/base.py`: `ToolRegistry` + `ToolSpec`. Tools registram-se via `register`.

## Built-ins
- filesystem: `fs_read`, `fs_write`, `fs_list` (workdir restrito).
- terminal: execução de comandos com timeout/cwd/blocklist.
- git: operações básicas (status/diff/log) via subprocesso.

## Spec
Cada tool define:
- `id`, `name`, `description`
- `input_schema` (Pydantic)
- `permissions` (lista de níveis)
- `risk_level`

## MCP
`luna/mcp/`: cliente STDIO descobre tools e cria proxies (`mcp_<server>_<tool>`). Manager isola por servidor. Transport HTTP pendente.

## Descoberta
CLI: `luna tool list`, `luna tool inspect <id>`. API: `GET /v1/tools`. SDK expõe via runtime.

## Adicionar tool
1. Implementar classe com `spec` e método `arun` (ou sync `run`).
2. Registrar no `ToolRegistry`.
3. Declarar em agent config (`tools: [id]`).