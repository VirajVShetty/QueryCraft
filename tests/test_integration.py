"""Whole-request integration checks using real SQLite, not fabricated results."""
import hashlib
import sqlite3
import pytest
from querycraft.web import create_app


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    for key in ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "demo.sqlite"
    client = create_app({"TESTING": True, "DATABASE": str(path), "IS_DEMO": True}).test_client()
    assert client.get("/api/schema").status_code == 200
    return client, path


def test_all_examples_generate_reviewable_sql_and_execute_real_data(workspace):
    client, path = workspace
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    examples = client.get("/api/status").json["examples"]
    for question in examples:
        generated = client.post("/api/generate", json={"question": question, "mode": "demo"})
        assert generated.status_code == 200, generated.json
        assert isinstance(generated.json["sql"], str)
        assert generated.json["explanation"]
        assert isinstance(generated.json["assumptions"], list)
        executed = client.post("/api/execute", json={"sql": generated.json["sql"]})
        assert executed.status_code == 200, executed.json
        assert executed.json["columns"]
        assert executed.json["rows"]
        assert executed.json["row_count"] == len(executed.json["rows"])
        assert executed.json["elapsed_ms"] >= 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_generation_does_not_call_result_execution(workspace, monkeypatch):
    client, _ = workspace
    def forbidden_execution(*args, **kwargs):
        raise AssertionError("Generation must never run result queries")
    monkeypatch.setattr("querycraft.core.execute_query", forbidden_execution)
    response = client.post("/api/generate", json={"question": "What is the total revenue?", "mode": "demo"})
    assert response.status_code == 200, response.json


@pytest.mark.parametrize("sql", [
    "DELETE FROM customers", "DROP TABLE customers", "SELECT 1; DELETE FROM customers", 
    "PRAGMA user_version=5", "ATTACH DATABASE '/tmp/x' AS other", "SELECT load_extension('x')",
])
def test_http_rejects_mutations_and_keeps_database_unchanged(workspace, sql):
    client, path = workspace
    before = path.read_bytes()
    response = client.post("/api/execute", json={"sql": sql})
    assert response.status_code == 400, response.json
    assert isinstance(response.json["error"], str)
    assert path.read_bytes() == before


def test_unknown_demo_question_is_not_a_fabricated_answer(workspace):
    client, _ = workspace
    response = client.post("/api/generate", json={"question": "What will sales be next year?"})
    assert response.status_code == 400
    assert "sql" not in response.json


def test_own_database_can_be_queried_but_not_seeded(tmp_path):
    path = tmp_path / "own.sqlite"
    with sqlite3.connect(str(path)) as conn:
        conn.execute('CREATE TABLE metrics (label TEXT, value REAL)')
        conn.execute('INSERT INTO metrics VALUES (?, ?)', ("real fixture", 42.5))
    before = path.read_bytes()
    client = create_app({"TESTING": True, "DATABASE": str(path), "IS_DEMO": False}).test_client()
    status = client.get("/api/status").json
    assert status["database"] == {"kind": "custom", "name": "own.sqlite"}
    assert status["examples"] == []
    schema = client.get("/api/schema")
    assert [t["name"] for t in schema.json["tables"]] == ["metrics"]
    response = client.post("/api/execute", json={"sql": "SELECT label, value FROM metrics"})
    assert response.status_code == 200
    assert response.json["rows"] == [["real fixture", 42.5]]
    assert client.post("/api/generate", json={"question": "What is the total revenue?", "mode": "demo"}).status_code == 400
    assert path.read_bytes() == before


def test_missing_custom_database_is_not_created(tmp_path):
    path = tmp_path / "missing.sqlite"
    client = create_app({"TESTING": True, "DATABASE": str(path), "IS_DEMO": False}).test_client()
    assert client.get("/api/schema").status_code == 400
    assert not path.exists()


def test_sql_numeric_overflow_remains_valid_browser_json(workspace):
    import json
    client, _ = workspace
    response = client.post("/api/execute", json={"sql": "SELECT 1e999 AS positive, -1e999 AS negative"})
    assert response.status_code == 200
    def invalid_constant(value):
        raise AssertionError("Nonstandard JSON constant: " + value)
    body = json.loads(response.get_data(as_text=True), parse_constant=invalid_constant)
    assert body["rows"] == [["Infinity", "-Infinity"]]


def test_llm_mode_without_configuration_reports_setup_needed(workspace):
    client, _ = workspace
    assert client.get("/api/status").json["llm_configured"] is False
    response = client.post("/api/generate", json={"question": "Show all customers", "mode": "llm"})
    assert response.status_code == 400
    assert "sql" not in response.json
