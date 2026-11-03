from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "Dockerfile",
    "docker-compose.yml",
    ".github/workflows/ci.yml",
    "benchmarks/run_simple.py",
    "docs/architecture.md",
    "docs/permissions.md",
    "docs/tools.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "scripts/release.sh",
]


def test_release_files_exist() -> None:
    for rel in REQUIRED:
        assert (ROOT / rel).is_file(), f"missing: {rel}"