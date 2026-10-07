"""Real loopback HTTP contracts; no production URL, real credential or mock HTTP."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

import requests
import yaml

from helpers.bootstrap_env import _validate_instance
from helpers.n8n_client import N8nClient
from helpers.run import _fire_webhook_and_poll

STATUSES = (301, 302, 303, 307, 308)
KEY = 'fictional-key-for-loopback-tests'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.server.received.append({'method': self.command, 'path': self.path,
                                     'key_matches': self.headers.get('X-N8N-API-KEY') == KEY,
                                     'body': body})
        if self.server.workflow_metadata and self.path.startswith('/api/v1/workflows/'):
            status, data = 200, {'id': 'owned-loopback-workflow', 'nodes': [
                {'type': 'n8n-nodes-base.webhook', 'parameters': {'path': 'neutral-hook'}}]}
        elif self.server.workflow_metadata and self.path.startswith('/api/v1/executions'):
            status, data = 200, {'data': []}
        elif self.server.mode == 'redirect':
            self.send_response(self.server.redirect_status)
            self.send_header('Location', self.server.redirect_target)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        else:
            status = {'normal': 200, 'empty': 204, 'error': 404}[self.server.mode]
            data = {'accepted': True}
        encoded = b'' if status == 204 else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    do_GET = do_POST = do_PUT = do_DELETE = handle_request


def server():
    result = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    result.received = []
    result.workflow_metadata = False
    result.mode = 'normal'
    result.redirect_status = 307
    result.redirect_target = ''
    threading.Thread(target=result.serve_forever, daemon=True).start()
    return result


class RedirectSafetyTests(unittest.TestCase):
    def setUp(self):
        self.origin, self.other = server(), server()
        self.base = f'http://127.0.0.1:{self.origin.server_port}'
        self.origin.redirect_target = f'http://127.0.0.1:{self.other.server_port}/unintended-origin'
        self.client = N8nClient(self.base, KEY, timeout=1)

    def tearDown(self):
        for item in (self.origin, self.other):
            item.shutdown()
            item.server_close()

    def invoke(self, method):
        call = getattr(self.client, method)
        return call('workflows', {'nonce': 'neutral-body'}) if method in ('post', 'put') else call('workflows')

    def test_every_api_verb_refuses_cross_origin_redirect_without_leaking_key_or_body(self):
        self.origin.mode = 'redirect'
        for status in STATUSES:
            self.origin.redirect_status = status
            for method in ('get', 'post', 'put', 'delete'):
                with self.subTest(status=status, method=method):
                    self.other.received.clear()
                    with self.assertRaisesRegex(ValueError, 'redirect'):
                        self.invoke(method)
                    self.assertEqual(self.other.received, [])

    def test_same_origin_redirect_is_also_refused_before_second_request(self):
        self.origin.mode = 'redirect'
        self.origin.redirect_target = self.base + '/same-origin-other-path'
        with self.assertRaisesRegex(ValueError, 'redirect'):
            self.client.get('workflows')
        self.assertEqual(len(self.origin.received), 1)
        self.assertEqual(self.other.received, [])

    def test_non_redirect_success_keeps_json_headers_method_and_body(self):
        for method in ('get', 'post', 'put', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(self.invoke(method), {'accepted': True})
                request = self.origin.received[-1]
                self.assertEqual(request['method'], method.upper())
                self.assertTrue(request['key_matches'])
                if method in ('post', 'put'):
                    self.assertEqual(json.loads(request['body']), {'nonce': 'neutral-body'})
        self.assertEqual(self.other.received, [])

    def test_empty_success_and_http_errors_keep_existing_contract(self):
        self.origin.mode = 'empty'
        for method in ('get', 'post', 'put', 'delete'):
            with self.subTest(method=method):
                self.assertIsNone(self.invoke(method))
        self.origin.mode = 'error'
        with self.assertRaises(requests.HTTPError):
            self.client.get('workflows')

    def test_bootstrap_target_validation_refuses_redirect(self):
        self.origin.mode = 'redirect'
        with self.assertRaisesRegex(ValueError, 'redirect'):
            _validate_instance(self.base, KEY)
        self.assertEqual(self.other.received, [])

    def test_webhook_redirect_neither_forwards_payload_nor_falls_back_or_polls(self):
        self.origin.mode = 'redirect'
        self.origin.workflow_metadata = True
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            config = workspace / 'n8n-config'
            config.mkdir()
            (workspace / 'n8n-workflows-template').mkdir()
            (config / 'test.yml').write_text(yaml.safe_dump({
                'name': 'test', 'displayName': 'Neutral redirect fixture',
                'n8n': {'instanceName': self.base},
                'workflows': {'neutral': {'id': 'owned-loopback-workflow'}}}))
            (config / '.env.test').write_text('N8N_API_KEY=' + KEY + '\n')
            for status in STATUSES:
                with self.subTest(status=status):
                    self.origin.redirect_status = status
                    self.origin.received.clear()
                    self.other.received.clear()
                    with self.assertRaisesRegex(SystemExit, 'redirect'):
                        _fire_webhook_and_poll(workspace, 'test', 'neutral', {'nonce': 'neutral-body'}, timeout=1)
                    self.assertEqual(self.other.received, [])
                    self.assertEqual([r['path'] for r in self.origin.received],
                                     ['/api/v1/workflows/owned-loopback-workflow', '/webhook/neutral-hook'])


if __name__ == '__main__':
    unittest.main()
