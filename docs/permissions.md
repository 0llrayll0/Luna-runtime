# Permissões — Luna Runtime

Implementação real em `luna/permissions/permissions.py`.

## Níveis
`PermissionEngine` opera com níveis ordenados (READ, WRITE, EXECUTE, ADMIN). Ferramentas declaram `permissions` em `ToolSpec`.

## Modos de execução
- `ExecutionMode.CONTROLLED` (default): ações sensíveis exigem aprovação humana (PendingApproval).
- Modos mais permissivos podem ser configurados no runtime/ambiente.

## Fluxo
1. Agent propõe tool_call.
2. `PermissionEngine.check(tool, level)` avalia allow/deny list (config: `permissions.allow_tools` / `deny_tools`).
3. Se `Deny`, retorna erro ao agent.
4. Se requer aprovação, gera `approval_id` e pausa; API/CLI podem decidir via `/v1/approvals` (quando habilitado).
5. Tool só executa após decisão aprovada.

## Sandbox de terminal
`luna/tools/terminal.py` usa subprocess com timeout, cwd restrito e blocklist de comandos perigosos. Não é isolamento forte (containers no roadmap).

## Configuração
`~/.luna/config.yaml`:
```yaml
permissions:
  allow_tools: []
  deny_tools: []
```

## Práticas recomendadas
- Princípio do menor privilégio.
- Negar por padrão tools de execução em produção.
- Revisar aprovações pendentes antes de automações.