"""Project discovery/adoption contracts; no network or external services."""
import hashlib
import uuid
from pathlib import Path

import pytest
import yaml

from helpers.init import _scaffold
from helpers.workspace import (
    MANIFEST_NAME, build_path, discover_project, environment_path,
    load_project_manifest, state_path, validate_workflow_key, workspace_path, workspace_root,
)


def _manifest(root, **overrides):
    root.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "paths": {}, "environments": {}}
    data.update(overrides)
    (root / MANIFEST_NAME).write_text(yaml.safe_dump(data))
    return root


def _snapshot(root):
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode)
            for p in root.rglob("*") if p.is_file()}


def test_discover_from_deep_subdirectory_and_symlink(tmp_path, monkeypatch):
    project = _manifest(tmp_path / "project")
    nested = project / "src" / "functions" / "deep"
    nested.mkdir(parents=True)
    alias = tmp_path / "linked-project"
    alias.symlink_to(project, target_is_directory=True)
    monkeypatch.chdir(alias / "src" / "functions" / "deep")
    assert workspace_root() == project.resolve()


def test_worktree_marker_is_a_file_and_stops_parent_discovery(tmp_path, monkeypatch):
    parent = _manifest(tmp_path / "parent")
    worktree = parent / "nested-worktree"
    nested = worktree / "src"
    nested.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: /not/needed/for/discovery\n")
    monkeypatch.chdir(nested)
    assert discover_project() is None
    _manifest(worktree)
    assert workspace_root() == worktree


def test_arbitrarily_named_legacy_project_discovered_from_subdir(tmp_path, monkeypatch):
    project = tmp_path / "legacy-app"
    (project / "n8n-config").mkdir(parents=True)
    nested = project / "n8n-workflows-template" / "nested"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert workspace_root() == project
    assert environment_path(project, "dev") == project / "n8n-config"
    assert build_path(project, "dev") == project / "n8n-build" / "dev"


def test_source_paths_and_environment_workspaces_are_distinct(tmp_path):
    project = _manifest(tmp_path / "project", paths={"templates": "automation/flows"}, environments={
        "dev": {"path": "envs/development"}, "prod": {"path": "envs/production"},
    })
    assert workspace_path(project, "templates", "hello.template.json") == project / "automation/flows/hello.template.json"
    assert environment_path(project, "dev") == project / "envs/development"
    assert state_path(project, "dev") == project / "envs/development/state"
    assert build_path(project, "prod") == project / "envs/production/build"
    assert not (project / "envs").exists()  # resolution does not create state


def test_explicit_external_source_mapping_allowed_but_dynamic_escape_refused(tmp_path):
    project = _manifest(tmp_path / "project", paths={"templates": "../shared"})
    assert workspace_path(project, "templates", "workflow.json") == tmp_path / "shared/workflow.json"
    with pytest.raises(ValueError, match="Unsafe"):
        workspace_path(project, "templates", "../secrets")
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "escape").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        workspace_path(project, "templates", "escape", "secret")


def test_nested_workflow_key_preserves_source_directory(tmp_path):
    project = _manifest(tmp_path, paths={"templates": "automation"})
    key = validate_workflow_key("group/hello-world_2")
    assert workspace_path(project, "templates", key + ".template.json") == project / "automation/group/hello-world_2.template.json"


@pytest.mark.parametrize("key", ["", ".", "..", "../hello", "group/../hello", "/hello", "group//hello", "group/", "group\\hello", "a/b.json"])
def test_workflow_key_rejects_ambiguous_or_escaping_paths(key):
    with pytest.raises(ValueError, match="Workflow keys"):
        validate_workflow_key(key)


@pytest.mark.parametrize("env", ["../prod", "/prod", "dev/prod", "", "..", "dev\\prod"])
def test_invalid_environment_names_rejected(tmp_path, env):
    with pytest.raises(ValueError, match="Environment names"):
        environment_path(tmp_path, env)


def test_overlapping_environment_paths_rejected(tmp_path):
    project = _manifest(tmp_path, environments={"dev": "env", "prod": "env/nested"})
    with pytest.raises(ValueError, match="overlap"):
        load_project_manifest(project)


@pytest.mark.parametrize("names", [("dev-1", "dev_1"), ("Dev", "dev")])
def test_environment_secret_namespaces_cannot_collide(tmp_path, names):
    project = _manifest(tmp_path, environments={name: f"envs/{index}" for index, name in enumerate(names)})
    with pytest.raises(ValueError, match="namespace"):
        load_project_manifest(project)


def test_environment_symlink_cannot_escape_project(tmp_path):
    project = _manifest(tmp_path / "project", environments={"dev": "env"})
    (project / "env").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="inside"):
        environment_path(project, "dev")


@pytest.mark.parametrize("mapped", ["environments/staging", "environments/staging/nested"])
def test_undeclared_environment_default_cannot_alias_existing_mapping(tmp_path, mapped):
    project = _manifest(tmp_path / "project", environments={"dev": {"path": mapped}})
    with pytest.raises(ValueError, match="overlap"):
        environment_path(project, "staging")
    assert not (project / "environments").exists()


def test_additive_adoption_preserves_files_permissions_and_runner(tmp_path):
    project = tmp_path / "existing"
    project.mkdir()
    files = {
        "AGENTS.md": "Existing agent instructions\n",
        "CLAUDE.md": "Existing Claude instructions\n",
        ".gitignore": "user-rules-only\n",
        "pyproject.toml": "[tool.pytest.ini_options]\n",
        ".env": "SENTINEL_SECRET=preserve-me\n",
        "database.bin": "opaque user data\n",
        "n8n-config/dev.yml": "name: dev\ndisplayName: Development\nn8n:\n  instanceName: localhost\n",
        "n8n-config/.env.dev": "N8N_API_KEY=sentinel-not-real\n",
        "automation/flows/existing.template.json": "{}\n",
    }
    for name, text in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (project / ".env").chmod(0o600)
    before = _snapshot(project)
    _scaffold(project, adopt=True, paths={"templates": "automation/flows"})
    after_first = _snapshot(project)
    for name, original in before.items():
        assert after_first[name] == original
    assert (project / "N8N-AGENTS.md").is_file()
    assert not (project / "n8n-functions-tests/conftest.py").exists()
    assert load_project_manifest(project)["environments"]["dev"]["legacy"] is True
    assert state_path(project, "dev") == project / ".n8n-state/dev"
    _scaffold(project, force=True, adopt=True)
    assert _snapshot(project) == after_first


def test_force_never_deletes_existing_workspace(tmp_path):
    project = tmp_path / "existing"
    project.mkdir()
    sentinel = project / "important.dat"
    sentinel.write_bytes(b"preserve\x00opaque")
    _scaffold(project, force=True)
    assert sentinel.read_bytes() == b"preserve\x00opaque"


def test_fresh_setup_is_idempotent(tmp_path):
    project = tmp_path / "fresh"
    _scaffold(project)
    assert uuid.UUID(load_project_manifest(project)["projectId"])
    before = _snapshot(project)
    _scaffold(project)
    assert _snapshot(project) == before


def test_adoption_keeps_legacy_layout_before_bundled_defaults(tmp_path):
    project = tmp_path / "legacy"
    (project / "n8n-config").mkdir(parents=True)
    common = project / "n8n-config/common.yml"
    common.write_text(yaml.safe_dump({"workspace_layout": {
        "n8n_functions_tests_dir": "existing-tests/automation",
        "cloud_functions_tests_dir": "existing-tests/cloud",
    }}))
    original = common.read_bytes()
    _scaffold(project, adopt=True, paths={"cloud_tests": "user-selected-tests"})
    assert workspace_path(project, "function_tests") == project / "existing-tests/automation"
    assert workspace_path(project, "cloud_tests") == project / "user-selected-tests"
    assert common.read_bytes() == original


def test_runtime_state_cannot_redirect_to_another_environment(tmp_path):
    project = _manifest(tmp_path / "project")
    dev = environment_path(project, "dev")
    prod = environment_path(project, "prod")
    dev.mkdir(parents=True)
    prod.mkdir(parents=True)
    (dev / "state").symlink_to(prod, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        state_path(project, "dev")


def test_collision_fails_before_scaffolding(tmp_path):
    project = tmp_path / "existing"
    project.mkdir()
    (project / "n8n-functions").write_text("user-owned file")
    before = _snapshot(project)
    with pytest.raises(ValueError, match="Preserved existing file"):
        _scaffold(project, adopt=True)
    assert _snapshot(project) == before
    assert not (project / MANIFEST_NAME).exists()


def test_setup_refuses_installed_tooling(tmp_path, monkeypatch):
    import helpers.workspace as workspace
    monkeypatch.setattr(workspace, "harness_root", lambda: tmp_path)
    with pytest.raises(RuntimeError, match="harness"):
        _scaffold(tmp_path / "unwanted")
    assert not (tmp_path / "unwanted").exists()
