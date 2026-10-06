"""Real loopback activation regression; JSON-object API contract, fictional key."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import threading

import pytest
import yaml


@pytest.mark.parametrize('mode', ['activate', 'draft', 'preview'])
def test_deploy_activation_sends_json_object(tmp_path, monkeypatch, mode):
    from helpers import deploy
    from helpers.n8n_client import N8nClient
    events = []
    state = {'id': 'fixture-id-123', 'nodes': [], 'connections': {}, 'settings': {}, 'active': False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            events.append((self.command, self.path, body))
            return json.loads(body) if body else None

        def do_GET(self):
            self.body()
            self.reply(200, state)

        def do_PUT(self):
            state.update(self.body())
            self.reply(200, state)

        def do_POST(self):
            body = self.body()
            if self.path != '/api/v1/workflows/fixture-id-123/activate' or body != {}:
                self.reply(400, {'message': 'Activation requires a JSON object'})
                return
            state['active'] = True
            self.reply(200, state)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.delenv(name, raising=False)
    workspace = tmp_path / 'workspace'
    (workspace / 'n8n-config').mkdir(parents=True)
    (workspace / 'n8n-workflows-template').mkdir()
    config = {'name': 'test', 'displayName': 'Fixture', 'workflowNamePostfix': ' [TEST]', 'credentials': {},
              'n8n': {'instanceName': f'http://127.0.0.1:{server.server_port}'},
              'workflows': {'fixture': {'id': 'fixture-id-123', 'name': 'Fixture'}}}
    (workspace / 'n8n-config/test.yml').write_text(yaml.safe_dump(config))
    (workspace / 'n8n-config/.env.test').write_text('N8N_API_KEY=fictional-fixture-key\n')
    template = {'name': 'Fixture', 'nodes': [{'name': 'Trigger', 'type': 'n8n-nodes-base.webhook', 'parameters': {}}],
                'connections': {}, 'settings': {}}
    (workspace / 'n8n-workflows-template/fixture.template.json').write_text(json.dumps(template))
    client = N8nClient(f'http://127.0.0.1:{server.server_port}', 'fictional-fixture-key')
    monkeypatch.setattr(deploy, 'ensure_client', lambda *args: client)
    flags = ['--no-activate'] if mode == 'draft' else ['--activate']
    if mode == 'preview':
        flags.append('--preview')
    monkeypatch.setattr(sys, 'argv', ['deploy.py', '--workspace', str(workspace), '--env', 'test', '--workflow-key', 'fixture', *flags])
    try:
        deploy.main()
        posts = [row for row in events if row[0] == 'POST']
        puts = [row for row in events if row[0] == 'PUT']
        if mode == 'activate':
            assert len(posts) == len(puts) == 1
            assert posts[0][2] == b'{}'
            assert state['active'] is True
            assert events.index(puts[0]) < events.index(posts[0])
        elif mode == 'draft':
            assert len(puts) == 1 and posts == [] and state['active'] is False
        else:
            assert puts == posts == [] and state['active'] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
