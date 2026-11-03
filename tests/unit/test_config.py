from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from luna.core.config import Settings, load_config


def test_load_defaults_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "nope.yaml"
    settings = load_config(path)
    assert isinstance(settings, Settings)
    assert settings.runtime.name == "luna"
    assert settings.execution.max_steps == 100


def test_load_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "runtime": {"name": "x", "debug": True},
                "execution": {"max_steps": 5},
            }
        ),
        encoding="utf-8",
    )
    settings = load_config(path)
    assert settings.runtime.name == "x"
    assert settings.runtime.debug is True
    assert settings.execution.max_steps == 5


def test_invalid_config_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("runtime: not-a-mapping\n", encoding="utf-8") if False else None
    path.write_text("runtime: 42\n", encoding="utf-8")
    with pytest.raises((ValueError, Exception)):
        load_config(path)


def test_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "env.yaml"
    path.write_text("runtime:\n  name: envname\n", encoding="utf-8")
    monkeypatch.setenv("LUNA_CONFIG", str(path))
    settings = load_config()
    assert settings.runtime.name == "envname"
    monkeypatch.delenv("LUNA_CONFIG", raising=False)
