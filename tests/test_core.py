import json
import sqlite3

import httpx
import pytest


@pytest.fixture
def demo(tmp_path):
    from querycraft.core import initialize_demo
    path = tmp_path / 'demo.sqlite'
    initialize_demo(path)
    return path


def test_schema_inspection_is_metadata_only_and_missing_is_not_created(demo, tmp_path):
    from querycraft.core import inspect_schema, QueryError
    schema = inspect_schema(demo)
    assert {t['name'] for t in schema} == {'customers', 'products', 'orders', 'order_items'}
    orders = next(t for t in schema if t['name'] == 'orders')
    assert orders['columns'][0] == {'name': 'id', 'type': 'INTEGER', 'primary_key': True}
    assert orders['foreign_keys'] == [{'from': 'customer_id', 'table': 'customers', 'to': 'id'}]
    assert 'Synthetic' not in json.dumps(schema)
    missing = tmp_path / 'missing.sqlite'
    with pytest.raises(QueryError):
        inspect_schema(missing)
    assert not missing.exists()


def test_read_only_query_execution_and_bounds(demo):
    from querycraft.core import execute_query
    result = execute_query(demo, 'WITH c AS (SELECT name FROM customers) SELECT * FROM c', row_limit=2)
    assert result['columns'] == ['name']
    assert len(result['rows']) == result['row_count'] == 2
    assert result['truncated'] is True
    assert result['elapsed_ms'] >= 0
    assert result['sql'].startswith('WITH')
    assert execute_query(demo, 'SELECT 1 AS value')['rows'] == [[1]]


@pytest.mark.parametrize('sql', [
    'DELETE FROM customers', 'SELECT 1; SELECT 2',
    'WITH gone AS (DELETE FROM customers RETURNING *) SELECT * FROM gone',
    'PRAGMA user_version', "ATTACH DATABASE ':memory:' AS other",
    "SELECT load_extension('x')", "SELECT readfile('x')", "SELECT writefile('x','y')",
    "SELECT * FROM pragma_table_info('customers')", 'SELECT nope FROM customers',
    'SELECT * FROM missing', 'SELECT (', 'VACUUM', '', 'SELECT 1' + ' ' * 20001,
])
def test_rejects_unsafe_or_invalid_sql(demo, sql):
    from querycraft.core import execute_query, QueryError
    with pytest.raises(QueryError):
        execute_query(demo, sql)


@pytest.mark.parametrize('options', [{'row_limit': 0}, {'row_limit': 1001}, {'row_limit': True}, {'timeout': 0}, {'timeout': 11}])
def test_rejects_unbounded_options(demo, options):
    from querycraft.core import execute_query, QueryError
    with pytest.raises(QueryError):
        execute_query(demo, 'SELECT 1', **options)


def test_query_deadline_and_result_size(demo):
    from querycraft.core import execute_query, QueryError
    with pytest.raises(QueryError, match='time|limit'):
        execute_query(demo, 'WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n', timeout=0.005)
    with pytest.raises(QueryError, match='limit|large'):
        execute_query(demo, 'SELECT hex(zeroblob(3000000))')


def test_demo_examples_compile_and_execute_with_completed_line_revenue(demo, monkeypatch):
    from querycraft import core
    assert core.EXAMPLES == ['What is the total revenue?', 'Show revenue by month', 'Who are the top 5 customers by revenue?', 'Which products sell the most?', 'How many orders have each status?']
    # Generation must not run the resulting SELECT.
    def forbidden(*args, **kwargs):
        raise AssertionError('generation executed result rows')
    monkeypatch.setattr(core, 'execute_query', forbidden)
    generated = [core.generate(q, demo) for q in core.EXAMPLES]
    monkeypatch.undo()
    results = [core.execute_query(demo, item['sql']) for item in generated]
    assert results[0]['rows'] == [[110.0]]
    assert results[1]['rows'] == [['2025-01', 40.0], ['2025-02', 30.0], ['2025-03', 40.0]]
    assert results[3]['rows'][0][1] == 6
    assert dict(results[4]['rows']) == {'cancelled': 1, 'completed': 3, 'pending': 1}
    for item in generated:
        assert item['provider'] == 'Deterministic demo (not AI)'
        assert item['explanation'] and isinstance(item['assumptions'], list)
    assert 'completed' in ' '.join(generated[0]['assumptions']).lower()
    assert 'unit_price' in ' '.join(generated[0]['assumptions'])


@pytest.mark.parametrize('question,mode', [('forecast revenue', 'demo'), ('', 'demo'), ('x' * 4001, 'demo'), ('hello', 'other'), (None, 'demo')])
def test_generation_rejects_unsupported_input(demo, question, mode):
    from querycraft.core import generate, QueryError
    with pytest.raises(QueryError):
        generate(question, demo, mode)


def test_demo_requires_matching_schema(tmp_path):
    from querycraft.core import generate, QueryError
    path = tmp_path / 'other.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE other(id INTEGER)')
    with pytest.raises(QueryError, match='schema'):
        generate('What is the total revenue?', path)


def test_llm_configuration_is_server_only_and_loopback_key_is_optional(demo, monkeypatch):
    from querycraft.core import settings_status, generate, QueryError
    for key in ('LLM_MODEL', 'LLM_BASE_URL', 'LLM_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    assert settings_status() == {'llm_configured': False, 'model': None, 'provider': 'OpenAI-compatible'}
    with pytest.raises(QueryError, match='LLM_MODEL'):
        generate('Count customers', demo, 'llm')
    monkeypatch.setenv('LLM_MODEL', 'local-model')
    assert settings_status()['llm_configured'] is False
    with pytest.raises(QueryError, match='API key'):
        generate('Count customers', demo, 'llm')
    monkeypatch.setenv('LLM_BASE_URL', 'http://localhost:1234/v1')
    assert settings_status()['llm_configured'] is True
    monkeypatch.setenv('LLM_BASE_URL', 'http://localhost.evil.test/v1')
    assert settings_status()['llm_configured'] is False
    monkeypatch.setenv('LLM_API_KEY', 'secret-never-expose')
    monkeypatch.setenv('LLM_BASE_URL', 'https://example.com/v1')
    assert settings_status()['llm_configured'] is True
    assert 'secret-never-expose' not in json.dumps(settings_status())


@pytest.fixture
def provider(monkeypatch):
    # Explicit HTTP test double, not evidence of a live LLM call.
    from querycraft import core
    monkeypatch.setenv('LLM_MODEL', 'test-model')
    monkeypatch.setenv('LLM_BASE_URL', 'https://provider.example/v1')
    monkeypatch.setenv('LLM_API_KEY', 'secret-never-expose')
    original = httpx.Client
    def install(handler):
        monkeypatch.setattr(core.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return install


def test_llm_posts_schema_only_parses_fenced_json_and_compiles(demo, provider, monkeypatch):
    from querycraft import core
    def handle(request):
        assert str(request.url) == 'https://provider.example/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer secret-never-expose'
        payload = json.loads(request.content)
        assert set(payload) == {'model', 'messages'}
        assert payload['model'] == 'test-model'
        assert payload['messages'][0]['role'] == 'system'
        assert 'untrusted' in payload['messages'][0]['content'].lower()
        assert 'Synthetic Alice' not in json.dumps(payload)
        assert 'customer_id' in json.dumps(payload)
        content = '```json\n' + json.dumps({'sql': 'SELECT COUNT(*) AS n FROM customers', 'explanation': 'Count customers.', 'assumptions': []}) + '\n```'
        return httpx.Response(200, json={'choices': [{'message': {'content': content}}]})
    provider(handle)
    monkeypatch.setattr(core, 'execute_query', lambda *a, **k: pytest.fail('generation executed result rows'))
    result = core.generate('Count customers', demo, 'llm')
    assert result == {'sql': 'SELECT COUNT(*) AS n FROM customers', 'explanation': 'Count customers.', 'assumptions': [], 'provider': 'OpenAI-compatible'}


@pytest.mark.parametrize('content', [
    'not json', '[]', '{}',
    json.dumps({'sql': 'SELECT 1', 'explanation': 1, 'assumptions': []}),
    json.dumps({'sql': 'SELECT 1', 'explanation': 'ok', 'assumptions': 'none'}),
    json.dumps({'sql': 'SELECT 1', 'explanation': 'ok', 'assumptions': [2]}),
    json.dumps({'sql': 'SELECT 1', 'explanation': 'ok', 'assumptions': [], 'extra': 'bad'}),
    json.dumps({'sql': 'SELECT 1', 'explanation': 'x' * 4001, 'assumptions': []}),
    json.dumps({'sql': 'SELECT 1', 'explanation': 'ok', 'assumptions': ['x'] * 21}),
    json.dumps({'sql': 'SELECT 1', 'explanation': 'ok', 'assumptions': ['x' * 1001]}),
    json.dumps({'sql': 1, 'explanation': 'ok', 'assumptions': []}),
], ids=['non-json', 'list', 'missing', 'explanation-type', 'assumptions-type', 'assumption-type', 'extra', 'long-explanation', 'many-assumptions', 'long-assumption', 'sql-type'])
def test_llm_rejects_malformed_output(demo, provider, content):
    from querycraft.core import generate, QueryError
    provider(lambda request: httpx.Response(200, json={'choices': [{'message': {'content': content}}]}))
    with pytest.raises(QueryError, match='provider|response'):
        generate('Count customers', demo, 'llm')


@pytest.mark.parametrize('failure', ['timeout', 'upstream', 'bad-envelope', 'huge-response'])
def test_llm_sanitizes_provider_failures(demo, provider, failure):
    from querycraft.core import generate, QueryError
    def handle(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('secret-never-expose provider details', request=request)
        if failure == 'upstream':
            return httpx.Response(500, text='secret-never-expose provider details')
        if failure == 'huge-response':
            return httpx.Response(200, text='secret-never-expose' * 10000)
        return httpx.Response(200, json={'secret-never-expose': 'bad'})
    provider(handle)
    with pytest.raises(QueryError) as error:
        generate('Count customers', demo, 'llm')
    assert 'secret-never-expose' not in str(error.value)
    assert 'provider details' not in str(error.value)


@pytest.mark.parametrize('sql', ['DELETE FROM customers', 'SELECT not_real FROM customers', "WITH x AS (DELETE FROM customers RETURNING *) SELECT * FROM x", "SELECT load_extension('oops')"])
def test_llm_sql_is_validated_before_return(demo, provider, sql):
    from querycraft.core import generate, QueryError
    content = json.dumps({'sql': sql, 'explanation': 'Not trusted.', 'assumptions': []})
    provider(lambda request: httpx.Response(200, json={'choices': [{'message': {'content': content}}]}))
    with pytest.raises(QueryError):
        generate('Any question', demo, 'llm')


def test_configuration_rejects_invalid_provider_port(monkeypatch):
    from querycraft.core import settings_status
    monkeypatch.setenv('LLM_MODEL', 'test-model')
    monkeypatch.setenv('LLM_API_KEY', 'private-marker')
    monkeypatch.setenv('LLM_BASE_URL', 'https://example.com:bad/v1')
    assert settings_status()['llm_configured'] is False


def test_initialize_demo_is_deterministic_labeled_and_never_overwrites(tmp_path):
    from querycraft.core import initialize_demo

    a, b = tmp_path / 'a.sqlite', tmp_path / 'b.sqlite'
    initialize_demo(a)
    initialize_demo(b)
    with sqlite3.connect(a) as db, sqlite3.connect(b) as other:
        for table in ('customers', 'products', 'orders', 'order_items'):
            rows = db.execute('SELECT * FROM ' + table).fetchall()
            assert rows and rows == other.execute('SELECT * FROM ' + table).fetchall()
        assert all('synthetic' in r[0].lower() for r in db.execute('SELECT name FROM customers'))
        assert all(r[0].startswith('2025-') for r in db.execute('SELECT order_date FROM orders'))
        db.execute("UPDATE customers SET name='preserved' WHERE id=1")
    initialize_demo(a)
    with sqlite3.connect(a) as db:
        assert db.execute('SELECT name FROM customers WHERE id=1').fetchone()[0] == 'preserved'
