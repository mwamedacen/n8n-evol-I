"""Actual installed native plugin contracts; no model or n8n request."""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]


def clean_env():
    return {key: value for key, value in os.environ.items()
            if key in {'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL'}}


def fixture_package(tmp_path):
    package = tmp_path / 'plugin with spaces'
    for directory in ('.codex-plugin', '.hermes-plugin'):
        shutil.copytree(ROOT / directory, package / directory)
    for filename in ('SKILL.md', 'plugin.yaml', '__init__.py'):
        shutil.copy2(ROOT / filename, package / filename)
    (package / '.agents/plugins').mkdir(parents=True)
    shutil.copy2(ROOT / '.agents/plugins/marketplace.json', package / '.agents/plugins/marketplace.json')
    return package


def test_codex_native_install_and_runtime_skill_discovery(tmp_path):
    codex = shutil.which('codex')
    if codex is None:
        pytest.skip('Codex CLI not installed; native load evidence required separately')
    package = fixture_package(tmp_path)
    profile = tmp_path / 'codex-profile'
    profile.mkdir()
    env = clean_env() | {'CODEX_HOME': str(profile)}
    for argv in ([codex, 'plugin', 'marketplace', 'add', str(package), '--json'],
                 [codex, 'plugin', 'add', 'n8n-evol-I@n8n-evol', '--json']):
        result = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
    server = subprocess.Popen([codex, 'app-server', '--stdio'], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=tmp_path, env=env, text=True)

    def request(message, expected_id=None):
        server.stdin.write(json.dumps(message) + '\n')
        server.stdin.flush()
        if expected_id is None:
            return
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if select.select([server.stdout], [], [], 1)[0]:
                line = server.stdout.readline()
                assert line, 'Codex app-server closed before responding'
                response = json.loads(line)
                if response.get('id') == expected_id:
                    return response
        raise AssertionError('Codex native skill discovery timed out')

    try:
        initialized = request({'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'native-plugin-test', 'version': '1'}}}, 1)
        assert 'result' in initialized
        request({'method': 'initialized'})
        response = request({'id': 2, 'method': 'skills/list',
            'params': {'cwds': [str(tmp_path)], 'forceReload': True}}, 2)
        skills = [skill for row in response['result']['data'] for skill in row['skills']
                  if skill.get('pluginId') == 'n8n-evol-I@n8n-evol']
        assert len(skills) == 1 and skills[0]['enabled']
        assert skills[0]['name'] == 'n8n-evol-I:n8n'
        installed = Path(skills[0]['path'])
        assert installed.is_file() and profile.resolve() in installed.parents
        assert (installed.parent / '../../../SKILL.md').resolve().is_file()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        for pipe in (server.stdin, server.stdout, server.stderr):
            pipe.close()


def test_hermes_native_registration_contract(tmp_path):
    hermes = shutil.which('hermes')
    if hermes is None:
        pytest.skip('Hermes not installed; native load evidence required separately')
    package = fixture_package(tmp_path)
    env = clean_env() | {'HERMES_HOME': str(tmp_path / 'hermes-profile'), 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([hermes, 'plugins', 'validate', str(package), '--json'],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report['ok']
    checks = {check['name']: check for check in report['checks']}
    assert checks['capability probe']['ok']
    assert checks['loadable']['ok']
    assert 'external runtime' in checks['python dependencies']['detail']
