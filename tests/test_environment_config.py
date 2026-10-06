"""Regression checks for environment boundaries. Live E2E evidence is separate."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
import yaml

from helpers import bootstrap_env, create_workflow
from helpers.config import load_env, load_yaml, save_yaml, env_file_path
from helpers.n8n_client import ensure_client, N8nClient


def project(tmp_path: Path, names=("dev", "prod")) -> Path:
    (tmp_path / "n8n-project.yml").write_text(yaml.safe_dump({
        "version": 1, "environments": {name: {"path": f"environments/{name}"} for name in names},
    }))
    for name in names:
        save_yaml(name, tmp_path, {
            "name": name, "displayName": name.title(),
            "n8n": {"instanceName": f"https://{name}.example.test"},
            "workflows": {"hello": {"id": f"{name}-id", "name": "Hello"}},
            "credentials": {"service": {"id": f"{name}-credential"}},
        })
    return tmp_path


def invoke(monkeypatch, main, *args):
    monkeypatch.setattr(sys, "argv", ["helper", *map(str, args)])
    main()


def snapshot(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def test_selected_secrets_never_fall_back_to_previous_environment(tmp_path, monkeypatch):
    ws = project(tmp_path)
    env_file_path(ws, "dev").write_text("N8N_API_KEY=dev-secret\nCUSTOM=dev-only\n")
    monkeypatch.setenv("N8N_API_KEY", "ambient-secret")
    assert ensure_client("dev", ws)._headers["X-N8N-API-KEY"] == "dev-secret"
    assert load_env("prod", ws) == {}
    with pytest.raises(ValueError, match="Missing N8N_API_KEY.*prod"):
        ensure_client("prod", ws)
    import os
    assert os.environ["N8N_API_KEY"] == "ambient-secret"
    monkeypatch.setenv("N8N_ENV_PROD_API_KEY", "prod-secret")
    assert ensure_client("prod", ws)._headers["X-N8N-API-KEY"] == "prod-secret"
    env_file_path(ws, "dev").write_text("N8N_API_KEY=rotated-secret\n")
    assert ensure_client("dev", ws)._headers["X-N8N-API-KEY"] == "rotated-secret"


def test_bindings_are_private_and_manual_target_change_is_rejected(tmp_path):
    ws = project(tmp_path)
    config_path = ws / "environments/dev/workspace.yml"
    config = yaml.safe_load(config_path.read_text())
    assert "workflows" not in config and "credentials" not in config
    assert (ws / "environments/dev/bindings.json").stat().st_mode & 0o777 == 0o600
    config["n8n"]["instanceName"] = "https://different.example.test"
    config_path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="target changed"):
        load_yaml("dev", ws)


def test_rebind_requires_opt_in_and_preserves_old_state(tmp_path, monkeypatch):
    ws = project(tmp_path)
    env_file_path(ws, "dev").write_text("N8N_API_KEY=old-key\nSERVICE_SECRET=keep-in-backup\n")
    state = ws / "environments/dev/state"
    state.mkdir()
    (state / "uuid.json").write_text('{"node":"old-node-id"}')
    before = snapshot(ws)
    with pytest.raises(SystemExit):
        invoke(monkeypatch, bootstrap_env.main, "--workspace", ws, "--env", "dev",
               "--instance", "https://new.example.test", "--api-key", "new-key")
    assert snapshot(ws) == before
    prod_before = snapshot(ws / "environments/prod")
    with patch.object(N8nClient, "get", return_value={"data": []}), \
         patch.object(N8nClient, "post", return_value={"id": "new-workflow-id"}) as post:
        invoke(monkeypatch, bootstrap_env.main, "--workspace", ws, "--env", "dev",
               "--instance", "https://new.example.test", "--api-key", "new-key", "--rebind")
    current = load_yaml("dev", ws)
    assert current["workflows"]["hello"]["id"] == "new-workflow-id"
    assert current["credentials"] == {}
    assert load_env("dev", ws) == {"N8N_API_KEY": "new-key"}
    assert not (state / "uuid.json").exists()
    backups = list((ws / "environments/dev/.rebind-backups").iterdir())
    assert len(backups) == 1
    assert "old-key" in (backups[0] / ".env").read_text()
    assert (backups[0] / "state/uuid.json").read_text() == '{"node":"old-node-id"}'
    assert json.loads((backups[0] / "bindings.json").read_text())["workflows"]["hello"]["id"] == "dev-id"
    assert snapshot(ws / "environments/prod") == prod_before
    assert post.call_count == 1


@pytest.mark.parametrize("activation", [None, "automatic", "manual"])
def test_migration_keeps_original_secret_and_legacy_bindings(tmp_path, monkeypatch, activation):
    ws = tmp_path
    (ws / "n8n-config").mkdir()
    legacy = {"name": "dev", "displayName": "Dev", "n8n": {"instanceName": "https://dev.example.test"},
              "workflows": {"hello": {"id": "keep-id", "name": "Hello"}}, "credentials": {"service": {"id": "keep-cred"}}}
    if activation is not None:
        legacy["activation"] = activation
    (ws / "n8n-config/dev.yml").write_text(yaml.safe_dump(legacy))
    (ws / "n8n-config/.env.dev").write_text("# user comment\nN8N_API_KEY=dev-key\nCUSTOM=untouched\n")
    (ws / "n8n-project.yml").write_text(yaml.safe_dump({"version": 1, "environments": {"dev": {"path": "environments/dev", "legacy": True}}}))
    before = snapshot(ws / "n8n-config")
    with patch.object(N8nClient, "get", return_value={"data": []}), patch.object(N8nClient, "post") as post:
        invoke(monkeypatch, bootstrap_env.main, "--workspace", ws, "--env", "dev", "--migrate")
    assert snapshot(ws / "n8n-config") == before
    assert load_yaml("dev", ws) == {**legacy, "activation": activation or "automatic"}
    assert env_file_path(ws, "dev").read_bytes() == before[".env.dev"]
    assert not post.called


def test_creation_requires_explicit_environment_before_any_mutation(tmp_path, monkeypatch):
    ws = project(tmp_path)
    before = snapshot(ws)
    with patch.object(N8nClient, "post") as post, pytest.raises(SystemExit):
        invoke(monkeypatch, create_workflow.main, "--workspace", ws, "--key", "new", "--name", "New", "--no-mint")
    assert snapshot(ws) == before
    assert not post.called
    invoke(monkeypatch, create_workflow.main, "--workspace", ws, "--key", "new", "--name", 'New "quoted"',
           "--register-in", "dev", "--no-mint")
    assert "new" in load_yaml("dev", ws)["workflows"]
    assert "new" not in load_yaml("prod", ws)["workflows"]
    json.loads((ws / "n8n-workflows-template/new.template.json").read_text())


def test_failed_bootstrap_does_not_mutate_manifest_or_other_files(tmp_path, monkeypatch):
    ws = project(tmp_path, names=())
    before = snapshot(ws)
    with patch.object(N8nClient, "get", side_effect=RuntimeError("cannot connect")), pytest.raises(SystemExit):
        invoke(monkeypatch, bootstrap_env.main, "--workspace", ws, "--env", "new",
               "--instance", "https://missing.example.test", "--api-key", "key")
    assert snapshot(ws) == before


def test_explicit_project_never_silently_falls_back():
    client = N8nClient("https://n8n.example.test", "key")
    with patch.object(client, "get", return_value={"data": [{"id": "other"}]}), patch.object(client, "post") as post:
        with pytest.raises(ValueError, match="not accessible"):
            client.create_workflow({"name": "hello"}, project_id="wanted")
    assert not post.called


def test_bootstrap_rejects_duplicate_deployment_before_writing(tmp_path, monkeypatch):
    ws = project(tmp_path, names=("dev",))
    before = snapshot(ws)
    with patch.object(N8nClient, "get") as get, pytest.raises(SystemExit):
        invoke(monkeypatch, bootstrap_env.main, "--workspace", ws, "--env", "prod",
               "--instance", "https://DEV.example.test:443/", "--api-key", "new-key")
    assert snapshot(ws) == before
    assert not get.called


def test_legacy_env_names_cannot_share_scoped_secret_namespace(tmp_path):
    config = tmp_path / "n8n-config"
    config.mkdir()
    for name in ("dev-1", "dev_1"):
        (config / f"{name}.yml").write_text(yaml.safe_dump({"name": name}))
    with pytest.raises(ValueError, match="namespace"):
        load_env("dev-1", tmp_path)


def test_status_is_read_only_and_never_returns_secret_values(tmp_path):
    from helpers.status import project_status
    ws = project(tmp_path)
    env_file_path(ws, "dev").write_text("N8N_API_KEY=private-key-123\nSERVICE_SECRET=private-service-456\n")
    before = snapshot(ws)
    status = project_status(ws)
    assert status["liveConnectivityChecked"] is False
    assert [row["status"] for row in status["environments"]] == ["configured", "missing-credentials"]
    text = json.dumps(status)
    assert "private-key-123" not in text and "private-service-456" not in text
    assert snapshot(ws) == before


def test_bootstrap_detects_configuration_edited_during_connectivity_check(tmp_path, monkeypatch):
    ws = project(tmp_path, names=("dev",))
    env_file_path(ws, "dev").write_text("N8N_API_KEY=dev-key\n")
    config_file = ws / "environments/dev/workspace.yml"
    def concurrent_edit(*args):
        data = yaml.safe_load(config_file.read_text())
        data["displayName"] = "User changed this while validation ran"
        config_file.write_text(yaml.safe_dump(data))
    with patch.object(bootstrap_env, "_validate_instance", side_effect=concurrent_edit), \
         patch.object(N8nClient, "post") as post, pytest.raises(SystemExit, match="configuration changed"):
        invoke(monkeypatch, bootstrap_env.main, "--workspace", ws, "--env", "dev", "--display-name", "Would overwrite")
    assert load_yaml("dev", ws)["displayName"] == "User changed this while validation ran"
    assert not post.called


def test_credential_creation_never_borrows_another_environment_secret(tmp_path, monkeypatch):
    from helpers import manage_credentials
    from types import SimpleNamespace
    ws = project(tmp_path, names=("dev",))
    env_file_path(ws, "dev").write_text("N8N_API_KEY=dev-key\n")
    monkeypatch.setenv("SERVICE_SECRET", "ambient-wrong-secret")
    args = SimpleNamespace(workspace=str(ws), env="dev", env_vars="password=SERVICE_SECRET",
                           name="Test", type="httpBasicAuth", key="new", dry_run=False)
    with patch.object(N8nClient, "post") as post, pytest.raises(SystemExit, match="Missing environment values"):
        manage_credentials.cmd_create(args)
    assert not post.called


@pytest.mark.parametrize("filename", [".env", "workspace.yml", "bindings.json"])
@pytest.mark.parametrize("dangling", [False, True])
def test_environment_files_cannot_redirect_to_another_environment(tmp_path, filename, dangling):
    ws = project(tmp_path)
    env_file_path(ws, "prod").write_text("N8N_API_KEY=prod-only\n")
    source = ws / "environments/dev" / filename
    target = ws / "environments/prod" / ("absent" if dangling else filename)
    source.unlink(missing_ok=True)
    source.symlink_to(target)
    before = snapshot(ws / "environments/prod")
    with pytest.raises(ValueError, match="symlink"):
        if filename == ".env":
            load_env("dev", ws)
        else:
            load_yaml("dev", ws)
    assert source.is_symlink()
    assert snapshot(ws / "environments/prod") == before


@pytest.mark.parametrize("filename", [".env.dev", "dev.yml"])
def test_legacy_environment_files_cannot_redirect(tmp_path, filename):
    directory = tmp_path / "n8n-config"
    directory.mkdir()
    target = directory / "prod-private"
    target.write_text("N8N_API_KEY=prod-only\n")
    (directory / filename).symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        (load_env if filename.startswith(".env") else load_yaml)("dev", tmp_path)
    assert target.read_text() == "N8N_API_KEY=prod-only\n"


@pytest.mark.parametrize("stdin_key", [False, True])
def test_migration_explicit_key_rotation_preserves_other_values_and_original(tmp_path, monkeypatch, stdin_key):
    import io
    ws = tmp_path
    directory = ws / "n8n-config"
    directory.mkdir()
    (ws / "n8n-project.yml").write_text(yaml.safe_dump({"version": 1, "environments": {"dev": {"path": "environments/dev", "legacy": True}}}))
    (directory / "dev.yml").write_text(yaml.safe_dump({"name": "dev", "displayName": "Dev", "n8n": {"instanceName": "https://dev.example.test"}, "workflows": {}, "credentials": {}}))
    original = "# Preserve this comment\nN8N_API_KEY=old-key\nSERVICE_SECRET=other-private-value\n"
    (directory / ".env.dev").write_text(original)
    options = ["--api-key", "new-key"]
    if stdin_key:
        monkeypatch.setattr(sys, "stdin", io.StringIO("new-key\n"))
        options = ["--api-key-stdin"]
    with patch.object(bootstrap_env, "_validate_instance") as validate:
        invoke(monkeypatch, bootstrap_env.main, "--workspace", ws, "--env", "dev", "--migrate", *options)
    validate.assert_called_once_with("https://dev.example.test", "new-key")
    assert load_env("dev", ws) == {"N8N_API_KEY": "new-key", "SERVICE_SECRET": "other-private-value"}
    assert env_file_path(ws, "dev").read_text().startswith("# Preserve this comment\n")
    assert env_file_path(ws, "dev").stat().st_mode & 0o777 == 0o600
    assert (directory / ".env.dev").read_text() == original


def test_workflow_creation_rejects_dangling_template_symlink_before_mutation(tmp_path, monkeypatch):
    (tmp_path / "project").mkdir()
    ws = project(tmp_path / "project")
    templates = ws / "n8n-workflows-template"
    templates.mkdir()
    unrelated = tmp_path / "unrelated.json"
    (templates / "new.template.json").symlink_to(unrelated)
    before = snapshot(ws)
    with patch.object(N8nClient, "post") as post, pytest.raises(ValueError, match="escapes"):
        invoke(monkeypatch, create_workflow.main, "--workspace", ws, "--key", "new", "--name", "New", "--register-in", "dev", "--no-mint")
    assert not unrelated.exists()
    assert snapshot(ws) == before
    assert not post.called


def test_nested_workflow_creation_preserves_key_and_selects_only_requested_environment(tmp_path, monkeypatch):
    ws = project(tmp_path)
    prod_before = snapshot(ws / "environments/prod")
    with patch.object(N8nClient, "post") as post:
        invoke(monkeypatch, create_workflow.main, "--workspace", ws, "--key", "group/hello", "--name", "Nested hello", "--register-in", "dev", "--no-mint")
    template = json.loads((ws / "n8n-workflows-template/group/hello.template.json").read_text())
    assert "Nested hello" in template["name"]
    webhook = next(node for node in template["nodes"] if node["type"] == "n8n-nodes-base.webhook")
    assert webhook["parameters"]["path"] == "group-hello"
    assert "group/hello" in load_yaml("dev", ws)["workflows"]
    assert snapshot(ws / "environments/prod") == prod_before
    order = yaml.safe_load((ws / "n8n-config/deployment_order.yml").read_text())
    assert "group/hello" in order["tiers"]["Tier 1"]
    assert not post.called


def test_offline_workflow_scaffold_before_environment_setup(tmp_path, monkeypatch):
    ws = project(tmp_path, names=())
    (ws / "AGENTS.md").write_text("Preserve project instructions\n")
    before = snapshot(ws)
    arguments = ("--workspace", ws, "--key", "group/hello", "--name", "Offline hello", "--no-mint")
    with patch.object(create_workflow, "ensure_client") as client:
        invoke(monkeypatch, create_workflow.main, *arguments)
    assert not client.called
    template_path = ws / "n8n-workflows-template/group/hello.template.json"
    assert "Offline hello" in json.loads(template_path.read_text())["name"]
    assert yaml.safe_load((ws / "n8n-config/deployment_order.yml").read_text())["tiers"]["Tier 1"] == ["group/hello"]
    assert not (ws / "environments").exists()
    assert all((ws / path).read_bytes() == contents for path, contents in before.items())
    template_path.write_text('{"name": "User edited"}\n')
    invoke(monkeypatch, create_workflow.main, *arguments)
    assert template_path.read_text() == '{"name": "User edited"}\n'


@pytest.mark.parametrize("options", [[], ["--no-mint", "--with-error-handler", "handler"], ["--no-mint", "--register-in", ""]])
def test_no_environment_scaffold_rejects_inapplicable_options_before_writes(tmp_path, monkeypatch, options):
    ws = project(tmp_path, names=())
    before = snapshot(ws)
    with patch.object(create_workflow, "ensure_client") as client, pytest.raises(SystemExit):
        invoke(monkeypatch, create_workflow.main, "--workspace", ws, "--key", "hello", "--name", "Hello", *options)
    assert snapshot(ws) == before
    assert not client.called


def test_environment_ignore_rules_override_negation_without_losing_user_text(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    directory = tmp_path / "environments/dev"
    directory.mkdir(parents=True)
    original = "# Keep this user comment\n.env\n!.env\nbindings.json\n!bindings.json\nstate/\n!state/\n"
    ignore = directory / ".gitignore"
    ignore.write_text(original)
    bootstrap_env._protect_environment(directory)
    protected = ignore.read_text()
    assert protected.startswith(original)
    names = [".env", ".env.private", "bindings.json", "state/baseline.json", "build/hello.json", ".rebind-backups/old.json"]
    for name in names:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic-private-data")
        result = subprocess.run(["git", "check-ignore", "--quiet", str(path)], cwd=tmp_path)
        assert result.returncode == 0, name
    bootstrap_env._protect_environment(directory)
    assert ignore.read_text() == protected
