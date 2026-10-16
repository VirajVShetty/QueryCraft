"""Exact result values at the real HTTP JSON boundary."""
import pytest

from querycraft.web import create_app


@pytest.fixture
def client(tmp_path):
    return create_app({
        "TESTING": True, "DATABASE": str(tmp_path / "demo.sqlite"), "IS_DEMO": True,
    }).test_client()


@pytest.mark.parametrize("literal,expected", [
    ("9007199254740993", "9007199254740993"),
    ("-9007199254740993", "-9007199254740993"),
    ("9007199254740992", "9007199254740992"),
    ("-9007199254740992", "-9007199254740992"),
    ("9007199254740991", 9007199254740991),
    ("-9007199254740991", -9007199254740991),
    ("9223372036854775807", "9223372036854775807"),
    ("-9223372036854775808", "-9223372036854775808"),
    ("0", 0), ("1", 1),
])
def test_integer_json_preserves_exact_value_and_safe_numeric_type(client, literal, expected):
    response = client.post("/api/execute", json={"sql": "SELECT " + literal + " AS value"})
    assert response.status_code == 200
    actual = response.get_json()["rows"][0][0]
    assert actual == expected
    assert type(actual) is type(expected)


def test_other_result_types_keep_their_existing_json_contract(client):
    response = client.post("/api/execute", json={
        "sql": "SELECT x'00ff', x'', NULL, 1.25, 9007199254740992.0, 1e999, -1e999, TRUE, FALSE",
    })
    assert response.status_code == 200
    row = response.get_json()["rows"][0]
    assert row == [{"hex": "00ff"}, {"hex": ""}, None, 1.25, 9007199254740992.0,
                   "Infinity", "-Infinity", 1, 0]
    assert type(row[3]) is float
    assert type(row[4]) is float
