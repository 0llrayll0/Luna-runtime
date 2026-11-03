#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python -m build --sdist --wheel 2>/dev/null || python -m pip install build >/dev/null && python -m build --sdist --wheel

echo ""
echo "Artefatos gerados em dist/"
echo "Para criar tag (sem push):"
echo "  git tag -a v$(python -c 'import tomllib;print(tomllib.load(open(\"pyproject.toml\",\"rb\"))[\"project\"][\"version\"])') -m \"release\""
echo "Revise dist/ e execute push manualmente quando apropriado."