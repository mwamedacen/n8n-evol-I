"""Credential data uses the real API schema's types without exposing secrets."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from helpers import manage_credentials


REDIS_SCHEMA = {
    'type': 'object',
    'properties': {
        'password': {'type': 'string'}, 'user': {'type': 'string'},
        'host': {'type': 'string'}, 'port': {'type': 'number'},
        'database': {'type': 'number'}, 'ssl': {'type': 'boolean'},
        'disableTlsVerification': {'type': 'boolean'},
    },
    'additionalProperties': False, 'required': [],
}


def test_redis_schema_converts_only_typed_values():
    values = {'PASSWORD': '  000123 true secret  ', 'HOST': 'localhost',
              'PORT': '6379', 'DB': '0', 'SSL': 'false', 'DISABLE_TLS': 'true'}
    result = manage_credentials._build_data_payload(
        ['password=PASSWORD', 'host=HOST', 'port=PORT', 'database=DB',
         'ssl=SSL', 'disableTlsVerification=DISABLE_TLS'], values, REDIS_SCHEMA)
    assert result == {'password': values['PASSWORD'], 'host': 'localhost',
                      'port': 6379, 'database': 0, 'ssl': False,
                      'disableTlsVerification': True}
    assert type(result['port']) is int and type(result['ssl']) is bool


@pytest.mark.parametrize(('kind', 'text', 'expected'), [
    ('integer', '0', 0), ('integer', '-3', -3), ('number', '1.5', 1.5),
    ('number', '1e2', 100), ('object', '{"key":"value"}', {'key': 'value'}),
    ('array', '[1,false,"x"]', [1, False, 'x']), ('boolean', ' false ', False),
])
def test_supported_schema_types(kind, text, expected):
    assert manage_credentials._credential_value('field', text, {'type': kind}) == expected


@pytest.mark.parametrize(('kind', 'text'), [
    ('boolean', 'yes'), ('boolean', '1'), ('boolean', '"false"'),
    ('integer', '1.2'), ('integer', 'true'), ('number', 'true'),
    ('number', 'NaN'), ('number', 'Infinity'), ('number', '1e999'),
    ('object', '[]'), ('array', '{}'), ('object', '{"x":NaN}'),
    ('array', '[1e999]'), ('number', 'do-not-print-this-secret'),
])
def test_invalid_values_fail_without_secret_in_error(kind, text):
    with pytest.raises(ValueError) as captured:
        manage_credentials._credential_value('field', text, {'type': kind})
    assert str(captured.value) == f"Credential field 'field' requires schema type {kind}; check its selected environment value"
    assert captured.value.__suppress_context__ or captured.value.__context__ is None


def test_missing_or_string_schema_preserves_secret_verbatim():
    secret = ' 001 false {secret} '
    for schema in ({}, {'type': 'string'}, {'type': ['string', 'null']}):
        assert manage_credentials._credential_value('password', secret, schema) == secret


def credential_fixture(tmp_path, monkeypatch, ssl='false'):
    config = tmp_path / 'n8n-config'
    config.mkdir()
    (config / 'dev.yml').write_text('name: dev\ndisplayName: Dev\nn8n:\n  instanceName: http://localhost:5678\ncredentials: {}\nworkflows: {}\n')
    (config / '.env.dev').write_text(f'N8N_API_KEY=test-only\nPORT=6379\nDB=0\nSSL={ssl}\nPASSWORD=secret-only\n')
    client = Mock()
    client.get.return_value = REDIS_SCHEMA
    client.post.return_value = {'id': 'redis-id', 'name': 'Redis test'}
    monkeypatch.setattr(manage_credentials, '_client_for', lambda *_: client)
    args = SimpleNamespace(workspace=str(tmp_path), env='dev',
        env_vars='password=PASSWORD,port=PORT,database=DB,ssl=SSL',
        name='Redis test', type='redis', key='redis', dry_run=False)
    return args, client


def test_create_fetches_schema_and_posts_typed_payload(tmp_path, monkeypatch):
    args, client = credential_fixture(tmp_path, monkeypatch)
    manage_credentials.cmd_create(args)
    client.get.assert_called_once_with('credentials/schema/redis')
    client.post.assert_called_once_with('credentials', {
        'name': 'Redis test', 'type': 'redis',
        'data': {'password': 'secret-only', 'port': 6379, 'database': 0, 'ssl': False},
    })
    assert 'secret-only' not in (tmp_path / 'n8n-config/dev.yml').read_text()


def test_create_invalid_type_refuses_before_post_or_local_write(tmp_path, monkeypatch):
    args, client = credential_fixture(tmp_path, monkeypatch, ssl='secret-invalid-bool')
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    with pytest.raises(ValueError, match="Credential field 'ssl' requires schema type boolean") as captured:
        manage_credentials.cmd_create(args)
    assert 'secret-invalid-bool' not in str(captured.value)
    client.post.assert_not_called()
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    assert after == before
