"""Primitive installation must never silently fan out to all environments."""
import importlib
import sys
from types import SimpleNamespace

import pytest
import yaml


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / "n8n-config").mkdir(parents=True)
    (root / "n8n-workflows-template").mkdir()
    for env in ("dev", "prod"):
        (root / "n8n-config" / f"{env}.yml").write_text(yaml.safe_dump({
            "name": env, "displayName": env,
            "n8n": {"instanceName": f"https://{env}.invalid"},
        }))
    return root


@pytest.mark.parametrize("name", ["create_lock", "create_queue"])
def test_ambiguous_install_leaves_source_unchanged(project, monkeypatch, name):
    module = importlib.import_module(f"helpers.{name}")
    monkeypatch.setattr(sys, "argv", [name, "--workspace", str(project)])
    with pytest.raises(SystemExit):
        module.main()
    assert list((project / "n8n-workflows-template").iterdir()) == []


@pytest.mark.parametrize("name", ["create_lock", "create_queue"])
@pytest.mark.parametrize("selection", ["dev", "dev,prod"])
def test_only_explicit_selection_is_forwarded(project, monkeypatch, name, selection):
    module = importlib.import_module(f"helpers.{name}")
    calls = []
    monkeypatch.setattr("helpers.create_lock.subprocess.run", lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(sys, "argv", [name, "--workspace", str(project), "--register-in", selection])
    module.main()
    assert calls
    assert all(argv[argv.index("--register-in") + 1] == selection for argv in calls)
