from fastapi.testclient import TestClient

from luna.api.app import create_app
from luna.runtime import LunaRuntime


def test_health():
    runtime = LunaRuntime()
    app = create_app(runtime)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_models_endpoint():
    runtime = LunaRuntime()
    app = create_app(runtime)
    client = TestClient(app)
    r = client.get("/v1/models")
    assert r.status_code == 200


def test_tools_endpoint():
    runtime = LunaRuntime()
    app = create_app(runtime)
    client = TestClient(app)
    r = client.get("/v1/tools")
    assert r.status_code == 200


def test_metrics_endpoint():
    runtime = LunaRuntime()
    app = create_app(runtime)
    client = TestClient(app)
    r = client.get("/v1/metrics")
    assert r.status_code == 200
