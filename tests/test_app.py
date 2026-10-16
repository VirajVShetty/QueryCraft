"""HTTP contract and local-only request boundary tests."""
import pytest


@pytest.mark.parametrize("headers", [
    {"Host": "attacker.example"},
    {"Host": "localhost", "Origin": "https://attacker.example"},
    {"Host": "localhost", "Sec-Fetch-Site": "cross-site"},
])
def test_rejects_nonlocal_or_cross_origin_requests(tmp_path, headers):
    from querycraft.web import create_app
    client = create_app({"TESTING": True, "DATABASE": str(tmp_path / "demo.sqlite")}).test_client()
    response = client.get("/api/health", headers=headers)
    assert response.status_code == 403
    assert "error" in response.json


@pytest.mark.parametrize("route,payload", [
    ("/api/generate", {}), ("/api/generate", {"question": 2}),
    ("/api/generate", {"question": "x", "mode": "other"}),
    ("/api/generate", {"question": "x" * 4001}),
    ("/api/execute", {}), ("/api/execute", {"sql": []}),
    ("/api/execute", {"sql": " "}),
])
def test_bad_input_returns_json_without_database_access(tmp_path, route, payload):
    from querycraft.web import create_app
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "missing.sqlite"), "IS_DEMO": False})
    response = app.test_client().post(route, json=payload)
    assert response.status_code == 400
    assert isinstance(response.json["error"], str)
    assert not (tmp_path / "missing.sqlite").exists()


def test_nonjson_and_oversized_input_are_json_errors(tmp_path):
    from querycraft.web import create_app
    client = create_app({"TESTING": True, "DATABASE": str(tmp_path / "demo.sqlite")}).test_client()
    assert client.post("/api/generate", data="question=x").status_code == 415
    response = client.post("/api/generate", data='{"question":"' + 'x'*70000 + '"}', content_type="application/json")
    assert response.status_code == 413
    assert "error" in response.json


def test_status_identifies_demo_and_never_exposes_secret(tmp_path, monkeypatch):
    from querycraft.web import create_app
    monkeypatch.setenv("LLM_API_KEY", "not-a-real-key-private-marker")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "demo.sqlite"), "IS_DEMO": True})
    response = app.test_client().get("/api/status")
    assert response.status_code == 200
    assert response.json["database"] == {"name": "Demo store", "kind": "demo"}
    assert response.json["max_rows"] == 200
    assert len(response.json["examples"]) == 5
    assert response.json["llm_configured"] is True
    assert "not-a-real-key" not in response.get_data(as_text=True)


def test_schema_endpoint_discovers_demo_tables(tmp_path):
    from querycraft.web import create_app
    client = create_app({"TESTING": True, "DATABASE": str(tmp_path / "demo.sqlite"), "IS_DEMO": True}).test_client()
    response = client.get("/api/schema")
    assert response.status_code == 200
    assert {t["name"] for t in response.json["tables"]} == {"customers", "products", "orders", "order_items"}
    assert all(t["columns"] for t in response.json["tables"])


def test_home_serves_workspace_markup(tmp_path):
    from querycraft.web import create_app
    from jinja2 import DictLoader
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "demo.sqlite")})
    app.jinja_loader = DictLoader({"index.html": "<!doctype html><title>Querycraft</title>"})
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert b"Querycraft" in response.data
    assert response.mimetype == "text/html"


def test_health_endpoint_has_security_headers(tmp_path):
    from querycraft.web import create_app
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "demo.sqlite"), "IS_DEMO": True})
    response = app.test_client().get("/api/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
