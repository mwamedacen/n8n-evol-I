"""Offline tests for helpers/deploy.py — uses unittest.mock for HTTP."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml


@pytest.fixture(autouse=True)
def remote_preflight():
    with patch("helpers.n8n_client.requests.get") as get:
        get.return_value.raise_for_status.return_value = None
        def current():
            from helpers.n8n_client import requests
            saved = requests.put.call_args
            return saved.kwargs["json"] if saved else {"id": "wf-id-123", "nodes": [], "connections": {}, "settings": {}}
        get.return_value.json.side_effect = current
        yield get


def _harness() -> Path:
    return Path(__file__).parent.parent


def _make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "n8n-config").mkdir(parents=True)
    (ws / "n8n-workflows-template").mkdir()

    yaml_data = {
        "name": "dev",
        "displayName": "Development",
        "workflowNamePostfix": " [DEV]",
        "n8n": {"instanceName": "localhost:8080"},
        "credentials": {},
        "workflows": {"smoke": {"id": "wf-id-123", "name": "Smoke"}},
    }
    (ws / "n8n-config" / "dev.yml").write_text(yaml.dump(yaml_data))
    (ws / "n8n-config" / ".env.dev").write_text("N8N_API_KEY=fake\n")

    template = {
        "name": "Smoke {{@env:displayName}}",
        "nodes": [{"name": "T", "type": "n8n-nodes-base.webhook", "parameters": {}}],
        "connections": {},
        "settings": {},
    }
    (ws / "n8n-workflows-template" / "smoke.template.json").write_text(json.dumps(template))
    return ws


def test_bulk_preflight_refuses_active_target_before_any_deployment(tmp_path, monkeypatch):
    from helpers import deploy, deploy_all
    ws = _make_workspace(tmp_path)
    config_path = ws / 'n8n-config/dev.yml'
    config = yaml.safe_load(config_path.read_text())
    config['workflows']['later'] = {'id': 'wf-active', 'name': 'Later'}
    config_path.write_text(yaml.safe_dump(config))
    templates = ws / 'n8n-workflows-template'
    (templates / 'later.template.json').write_bytes((templates / 'smoke.template.json').read_bytes())
    (ws / 'n8n-config/deployment_order.yml').write_text(yaml.safe_dump({'tiers': {'Tier 1': ['smoke', 'later']}}))
    mutations = []

    class Client:
        base_url = 'http://localhost:8080'
        def get_workflow(self, key):
            return {'id': key, 'nodes': [], 'connections': {}, 'settings': {}, 'active': key == 'wf-active'}
        def put(self, *args):
            mutations.append(args)
            raise AssertionError('Bulk preflight must finish before any remote mutation')
        def post(self, *args):
            mutations.append(args)
            raise AssertionError('Preview must not activate a workflow')

    monkeypatch.setattr(deploy, 'ensure_client', lambda *args: Client())
    calls = []
    def run(command):
        calls.append(command)
        with monkeypatch.context() as patcher:
            patcher.setattr(sys, 'argv', command[1:])
            try:
                deploy.main()
            except SystemExit as error:
                return type('Result', (), {'returncode': error.code if isinstance(error.code, int) else 1})()
        return type('Result', (), {'returncode': 0})()
    monkeypatch.setattr(deploy_all.subprocess, 'run', run)
    monkeypatch.setattr(sys, 'argv', ['deploy_all.py', '--workspace', str(ws), '--env', 'dev'])
    with pytest.raises(SystemExit) as error:
        deploy_all.main()
    assert error.value.code == 1
    assert len(calls) == 2
    assert all('--preview' in command and '--no-activate' in command for command in calls)
    assert not mutations


@pytest.mark.parametrize("workflow_id", [None, "", "  ", "placeholder", "your-workflow-id"])
@pytest.mark.parametrize("preview", [False, True])
def test_unminted_draft_refused_before_build_or_network(tmp_path, monkeypatch, workflow_id, preview):
    from helpers import deploy
    ws = _make_workspace(tmp_path)
    path = ws / 'n8n-config/dev.yml'
    config = yaml.safe_load(path.read_text())
    config['workflows']['smoke']['id'] = workflow_id
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(deploy, 'ensure_client', lambda *args: pytest.fail('Draft must not contact n8n'))
    monkeypatch.setattr('helpers.hydrate.hydrate', lambda *args, **kwargs: pytest.fail('Draft must not build'))
    args = ['deploy.py', '--workspace', str(ws), '--env', 'dev', '--workflow-key', 'smoke']
    monkeypatch.setattr(sys, 'argv', args + (['--preview'] if preview else []))
    with pytest.raises(SystemExit, match='No deployed workflow ID'):
        deploy.main()


def test_bulk_unminted_later_draft_refuses_before_any_mutation(tmp_path, monkeypatch):
    from helpers import deploy, deploy_all
    ws = _make_workspace(tmp_path)
    config_path = ws / 'n8n-config/dev.yml'
    config = yaml.safe_load(config_path.read_text())
    config['workflows']['draft'] = {'id': '', 'name': 'Draft'}
    config_path.write_text(yaml.safe_dump(config))
    templates = ws / 'n8n-workflows-template'
    (templates / 'draft.template.json').write_bytes((templates / 'smoke.template.json').read_bytes())
    (ws / 'n8n-config/deployment_order.yml').write_text(yaml.safe_dump({'tiers': {'Tier 1': ['smoke', 'draft']}}))
    reads, mutations, calls = [], [], []

    class Client:
        base_url = 'http://localhost:8080'
        def get_workflow(self, key):
            reads.append(key)
            return {'id': key, 'nodes': [], 'connections': {}, 'settings': {}, 'active': False}
        def put(self, *args):
            mutations.append(args)
            raise AssertionError('An unminted later draft must block the entire rollout')
        def post(self, *args):
            mutations.append(args)
            raise AssertionError('Preflight cannot activate')

    monkeypatch.setattr(deploy, 'ensure_client', lambda *args: Client())
    def run(command):
        calls.append(command)
        with monkeypatch.context() as patcher:
            patcher.setattr(sys, 'argv', command[1:])
            try:
                deploy.main()
            except SystemExit as error:
                return type('Result', (), {'returncode': error.code if isinstance(error.code, int) else 1})()
        return type('Result', (), {'returncode': 0})()
    monkeypatch.setattr(deploy_all.subprocess, 'run', run)
    monkeypatch.setattr(sys, 'argv', ['deploy_all.py', '--workspace', str(ws), '--env', 'dev', '--activate'])
    with pytest.raises(SystemExit) as error:
        deploy_all.main()
    assert error.value.code == 1
    assert len(calls) == 2 and all('--preview' in command for command in calls)
    assert reads == ['wf-id-123']
    assert not mutations


class TestDeploy:
    def test_adoption_retains_selected_legacy_environment_activation(self, tmp_path, monkeypatch):
        from helpers.init import _scaffold
        from helpers import deploy
        ws = _make_workspace(tmp_path)
        _scaffold(ws, adopt=True)
        monkeypatch.setattr(sys, 'argv', ['deploy.py', '--workspace', str(ws), '--env', 'dev', '--workflow-key', 'smoke'])
        with patch('helpers.n8n_client.requests.put') as put, patch('helpers.n8n_client.requests.post') as post:
            put.return_value.raise_for_status.return_value = None
            put.return_value.json.return_value = {'id': 'wf-id-123'}
            post.return_value.raise_for_status.return_value = None
            deploy.main()
        assert post.called
        assert post.call_args[0][0].endswith('/workflows/wf-id-123/activate')

    def test_deploy_calls_put_then_activate(self, tmp_path):
        ws = _make_workspace(tmp_path)

        with patch("helpers.n8n_client.requests.put") as mock_put, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_put.return_value.raise_for_status.return_value = None
            mock_put.return_value.json.return_value = {"id": "wf-id-123", "active": False}
            mock_post.return_value.raise_for_status.return_value = None
            mock_post.return_value.json.return_value = {"id": "wf-id-123", "active": True}

            from helpers import deploy
            import importlib
            importlib.reload(deploy)
            old_argv = sys.argv
            sys.argv = [
                "deploy.py",
                "--workspace", str(ws),
                "--env", "dev",
                "--workflow-key", "smoke",
            ]
            try:
                deploy.main()
            finally:
                sys.argv = old_argv

        # PUT to /workflows/wf-id-123 happened
        assert mock_put.called
        put_url = mock_put.call_args[0][0]
        assert "workflows/wf-id-123" in put_url
        # POST to /activate happened
        assert mock_post.called
        post_url = mock_post.call_args[0][0]
        assert "activate" in post_url

    def test_deploy_no_activate(self, tmp_path):
        ws = _make_workspace(tmp_path)

        with patch("helpers.n8n_client.requests.put") as mock_put, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_put.return_value.raise_for_status.return_value = None
            mock_put.return_value.json.return_value = {"id": "wf-id-123"}

            from helpers import deploy
            import importlib
            importlib.reload(deploy)
            old_argv = sys.argv
            sys.argv = [
                "deploy.py",
                "--workspace", str(ws),
                "--env", "dev",
                "--workflow-key", "smoke",
                "--no-activate",
            ]
            try:
                deploy.main()
            finally:
                sys.argv = old_argv

        assert mock_put.called
        # POST should NOT be called when --no-activate
        assert not mock_post.called

    def test_deploy_aborts_on_inlined_js_template(self, tmp_path):
        """A template with an inlined-JS Code node must abort deploy before any HTTP call."""
        ws = _make_workspace(tmp_path)

        bad_template = {
            "name": "Bad",
            "nodes": [
                {
                    "name": "Code",
                    "type": "n8n-nodes-base.code",
                    "parameters": {
                        "jsCode": "const stats = {}; return { json: { stats } };",
                    },
                }
            ],
            "connections": {},
            "settings": {},
        }
        (ws / "n8n-workflows-template" / "smoke.template.json").write_text(json.dumps(bad_template))

        with patch("helpers.n8n_client.requests.put") as mock_put, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            from helpers import deploy
            import importlib
            importlib.reload(deploy)
            old_argv = sys.argv
            sys.argv = ["deploy.py", "--workspace", str(ws), "--env", "dev", "--workflow-key", "smoke"]
            try:
                with pytest.raises(SystemExit) as exc:
                    deploy.main()
                assert exc.value.code == 1
            finally:
                sys.argv = old_argv

        assert not mock_put.called, "PUT must not happen when template validation fails"
        assert not mock_post.called, "POST must not happen when template validation fails"

    def test_deploy_strips_disallowed_fields_for_put(self, tmp_path):
        """n8n's PUT API rejects fields like 'active', 'tags', 'id'; deploy.py should drop them."""
        ws = _make_workspace(tmp_path)

        # Add disallowed fields to the template
        template_path = ws / "n8n-workflows-template" / "smoke.template.json"
        data = json.loads(template_path.read_text())
        data["active"] = True
        data["tags"] = []
        data["id"] = "should-be-stripped"
        data["versionId"] = "v1"
        template_path.write_text(json.dumps(data))

        with patch("helpers.n8n_client.requests.put") as mock_put, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_put.return_value.raise_for_status.return_value = None
            mock_put.return_value.json.return_value = {"id": "wf-id-123"}
            mock_post.return_value.raise_for_status.return_value = None
            mock_post.return_value.json.return_value = {}

            from helpers import deploy
            import importlib
            importlib.reload(deploy)
            old_argv = sys.argv
            sys.argv = ["deploy.py", "--workspace", str(ws), "--env", "dev", "--workflow-key", "smoke"]
            try:
                deploy.main()
            finally:
                sys.argv = old_argv

        body = mock_put.call_args.kwargs["json"]
        assert "active" not in body
        assert "tags" not in body
        assert "id" not in body
        assert "versionId" not in body
        assert "nodes" in body
        assert "connections" in body
