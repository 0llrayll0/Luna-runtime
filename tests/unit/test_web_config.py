from pathlib import Path

import yaml

from luna.core.config import load_config
from luna.web.app import create_app


def test_import_web() -> None:
    import luna.web  # noqa: F401
    import luna.web.app  # noqa: F401


def test_health(tmp_path: Path) -> None:
    app = create_app(tmp_path / "config.yaml")
    client = app.test_client()
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"


def test_save_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    app = create_app(path)
    client = app.test_client()
    data = {
        "runtime.name": "webtest",
        "runtime.environment": "dev",
        "runtime.debug": "true",
        "models.default": "ollama/x",
        "models.providers": "ollama\nother",
        "execution.max_steps": "7",
        "execution.timeout_seconds": "30",
        "execution.workdir": "/tmp/wd",
        "memory.backend": "sqlite",
        "memory.path": "/tmp/mem.db",
    }
    r = client.post("/save", data=data)
    assert r.status_code in (200, 302, 303)
    cfg = load_config(path)
    assert cfg.runtime.name == "webtest"
    assert cfg.runtime.debug is True
    assert cfg.execution.max_steps == 7
    assert cfg.memory.backend == "sqlite"


def test_save_preserves_permissions_and_extras(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "runtime": {"name": "existing"},
                "permissions": {"allow_tools": ["foo"], "deny_tools": ["bar"]},
                "extra_key": {"nested": 42},
            }
        ),
        encoding="utf-8",
    )
    app = create_app(path)
    client = app.test_client()
    data = {
        "runtime.name": "updated",
        "runtime.environment": "dev",
        "runtime.debug": "true",
        "models.default": "ollama/x",
        "models.providers": "ollama",
        "execution.max_steps": "7",
        "execution.timeout_seconds": "30",
        "execution.workdir": "/tmp/wd",
        "memory.backend": "sqlite",
        "memory.path": "/tmp/mem.db",
    }
    r = client.post("/save", data=data)
    assert r.status_code in (200, 302, 303)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["permissions"]["allow_tools"] == ["foo"]
    assert raw["permissions"]["deny_tools"] == ["bar"]
    assert raw["extra_key"] == {"nested": 42}
    cfg = load_config(path)
    assert cfg.runtime.name == "updated"
    assert cfg.permissions.allow_tools == ["foo"]


def test_save_invalid_input_returns_400(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    app = create_app(path)
    client = app.test_client()
    data = {
        "runtime.name": "bad",
        "runtime.environment": "dev",
        "models.default": "ollama/x",
        "execution.max_steps": "not-a-number",
        "execution.timeout_seconds": "30",
        "memory.backend": "sqlite",
    }
    r = client.post("/save", data=data)
    assert r.status_code == 400