# Contribuindo — Luna Runtime

## Setup
```bash
uv venv
uv pip install -e ".[dev]"
source .venv/bin/activate
```

## Testes / lint
```bash
ruff check .
pytest -q
```

## Convenções
- Python 3.12+, type hints, ruff (linha 120).
- Evitar inventar métricas; benchmarks devem rodar código real (MockProvider).
- Não commite segredos, `.env`, `~/.luna/`, `benchmarks/results.json`.

## PRs
- Escopo pequeno, testes para mudança de comportamento.
- Atualize docs pertinentes.

## Release
Use `scripts/release.sh` (build sdist/wheel + instruções de tag, sem push).