# Security — Luna Runtime

## Reporte de vulnerabilidades
Abra issue privada ou contate mantenedor. Não publique detalhes antes de correção.

## Escopo
- Sandbox de terminal é subprocess com timeout/cwd/blocklist; **não** é isolamento forte. Não execute código não confiável sem container.
- Aprovações humanas (`PermissionEngine`) são mecanismo de controle, não substituto de sandbox.
- Credenciais via env vars / config local; nunca commite `.env`, `~/.luna/`.

## Boas práticas de deploy
- Rode em container com volume restrito.
- Desative tools de EXECUTE/ADMIN em produção quando possível.
- Use `ExecutionMode.CONTROLLED`.
- Limite workdir a diretório dedicado.
- Monitor `/v1/metrics` e logs.

## Status
Anthropic provider é stub (levanta NotImplementedError). MCP HTTP pendente. Streaming SSE pendente. Consulte README Limitações.