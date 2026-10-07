"""Project preferences override bundled runners/scaffolds without network calls."""
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from helpers.init import _scaffold
from helpers.test_functions import project_test_command
from helpers.validate import validate_workflow_json
from helpers.workspace import MANIFEST_NAME, require_project


def _project(tmp_path, **values):
    project = tmp_path / "project"
    _scaffold(project)
    manifest = yaml.safe_load((project / MANIFEST_NAME).read_text())
    manifest.update(values)
    (project / MANIFEST_NAME).write_text(yaml.safe_dump(manifest))
    return project


def test_explicit_test_command_executes_without_bundled_test_naming(tmp_path):
    command = [sys.executable, "-c", "from pathlib import Path; Path('custom-test-ran').write_text('ok')"]
    project = _project(tmp_path, commands={"test": {"n8n": command}})
    (project / "package.json").write_text(json.dumps({"scripts": {"test": "false"}}))
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "helpers/test_functions.py"), "--project", str(project), "--target", "n8n"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (project / "custom-test-ran").read_text() == "ok"


def test_existing_package_runner_convention_used_before_defaults(tmp_path):
    project = _project(tmp_path)
    (project / "package.json").write_text(json.dumps({"packageManager": "pnpm@9.0.0", "scripts": {"test": "vitest run"}}))
    assert project_test_command(project, "n8n") == (["pnpm", "run", "test"], project)


def test_custom_test_contract_keeps_structural_validation_without_cjs_rule(tmp_path):
    project = _project(tmp_path, commands={"test": {"n8n": [sys.executable, "checks.py"]}})
    source = project / "n8n-functions/js/normalize.js"
    source.write_text("const normalize = (items) => items;\n")
    workflow = {"name": "Custom", "nodes": [{"name": "Code", "type": "n8n-nodes-base.code", "parameters": {"jsCode": "{{@js:n8n-functions/js/normalize.js}}\nreturn normalize(items);"}}], "connections": {}, "settings": {}}
    valid, errors = validate_workflow_json(json.dumps(workflow), workspace=project)
    assert valid, errors
    source.unlink()
    valid, errors = validate_workflow_json(json.dumps(workflow), workspace=project)
    assert not valid
    assert any("not found" in error for error in errors)


def test_custom_scaffold_creates_user_language_without_fastapi_files(tmp_path):
    command = [sys.executable, "-c", "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('export default () => 42;')", "{output}/{name}.ts"]
    project = _project(tmp_path, commands={"scaffold": command})
    helper = Path(__file__).resolve().parents[1] / "helpers/add_cloud_function.py"
    result = subprocess.run([sys.executable, str(helper), "--project", str(project), "--name", "my-handler"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (project / "cloud-functions/my-handler.ts").is_file()
    assert not (project / "cloud-functions/app.py").exists()
    assert not (project / "cloud-functions/railway.toml").exists()


def test_unrecognized_existing_service_is_preserved(tmp_path):
    project = _project(tmp_path)
    service = project / "cloud-functions/index.ts"
    service.write_text("user-owned service")
    helper = Path(__file__).resolve().parents[1] / "helpers/add_cloud_function.py"
    result = subprocess.run([sys.executable, str(helper), "--project", str(project), "--name", "handler"], capture_output=True, text=True)
    assert result.returncode != 0
    assert "Existing service preserved" in result.stderr
    assert service.read_text() == "user-owned service"
    assert not (project / "cloud-functions/app.py").exists()


def test_python_preset_still_available_for_new_service(tmp_path):
    project = _project(tmp_path)
    helper = Path(__file__).resolve().parents[1] / "helpers/add_cloud_function.py"
    result = subprocess.run([sys.executable, str(helper), "--project", str(project), "--name", "handler", "--platform", "generic"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (project / "cloud-functions/functions/handler.py").is_file()
    assert '"handler": handler' in (project / "cloud-functions/registry.py").read_text()
    assert not (project / "cloud-functions/railway.toml").exists()


def test_auto_tidy_uses_manifest_mapping_and_nested_key(tmp_path, monkeypatch):
    import hooks.auto_tidy as hook
    project = _project(tmp_path)
    manifest = yaml.safe_load((project / MANIFEST_NAME).read_text())
    manifest["paths"]["templates"] = "automation/flows"
    (project / MANIFEST_NAME).write_text(yaml.safe_dump(manifest))
    template = project / "automation/flows/group/hello.template.json"
    template.parent.mkdir(parents=True)
    template.write_text("{}")
    calls = []
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps({"cwd": str(project), "tool_input": {"file_path": str(template)}})))
    monkeypatch.setattr(hook.subprocess, "run", lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0, stderr=""))
    hook.main()
    assert calls[0][calls[0].index("--workspace") + 1] == str(project)
    assert calls[0][calls[0].index("--workflow-key") + 1] == "group/hello"


def test_sdk_install_uses_cache_and_never_tooling(tmp_path, monkeypatch):
    import helpers.tidy_workflow as tidy
    monkeypatch.setenv("N8N_EVOL_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(tidy.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls = []
    def fake_install(argv, **kwargs):
        calls.append(argv)
        prefix = Path(argv[argv.index("--prefix") + 1])
        (prefix / "node_modules/@n8n/workflow-sdk").mkdir(parents=True)
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(tidy.subprocess, "run", fake_install)
    assert tidy._ensure_sdk()
    assert str(tmp_path / "cache") in calls[0][calls[0].index("--prefix") + 1]
    assert "--ignore-scripts" in calls[0]
    assert str(tidy._HARNESS_ROOT) not in " ".join(calls[0])


def test_ordinary_operations_do_not_create_missing_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="incomplete or missing"):
        require_project()
    assert list(tmp_path.iterdir()) == []


def test_auto_tidy_prefers_edited_nested_project_over_outer_cwd(tmp_path, monkeypatch):
    import hooks.auto_tidy as hook
    outer = _project(tmp_path)
    nested = outer / "nested"
    _scaffold(nested)
    template = nested / "n8n-workflows-template/hello.template.json"
    template.write_text("{}")
    calls = []
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps({"cwd": str(outer), "tool_input": {"file_path": str(template)}})))
    monkeypatch.setattr(hook.subprocess, "run", lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0, stderr=""))
    hook.main()
    assert len(calls) == 1
    assert calls[0][calls[0].index("--workspace") + 1] == str(nested)


def test_auto_tidy_uses_cwd_for_explicit_external_template_mapping(tmp_path, monkeypatch):
    import hooks.auto_tidy as hook
    project = _project(tmp_path)
    external = tmp_path / "shared-flows"
    external.mkdir()
    manifest = yaml.safe_load((project / MANIFEST_NAME).read_text())
    manifest["paths"]["templates"] = "../shared-flows"
    (project / MANIFEST_NAME).write_text(yaml.safe_dump(manifest))
    template = external / "hello.template.json"
    template.write_text("{}")
    calls = []
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps({"cwd": str(project), "tool_input": {"file_path": str(template)}})))
    monkeypatch.setattr(hook.subprocess, "run", lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0, stderr=""))
    hook.main()
    assert len(calls) == 1
    assert calls[0][calls[0].index("--workspace") + 1] == str(project)


def test_inferred_pytest_runner_also_executes_existing_javascript_suite(tmp_path):
    import shutil
    if shutil.which("node") is None:
        pytest.skip("Node required for the real mixed-runner regression")
    project = _project(tmp_path)
    tests = project / "n8n-functions-tests"
    (project / "pytest.ini").write_text("[pytest]\ntestpaths = n8n-functions-tests\n")
    (tests / "test_python.py").write_text("from pathlib import Path\ndef test_python():\n    Path(__file__).with_name('python-ran').write_text('yes')\n")
    (tests / "javascript.test.js").write_text("const fs = require('node:fs'); const path = require('node:path'); fs.writeFileSync(path.join(__dirname, 'javascript-ran'), 'yes'); throw new Error('deliberate JS failure');\n")
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "helpers/test_functions.py"), "--project", str(project), "--target", "n8n"], capture_output=True, text=True)
    assert result.returncode == 1
    assert (tests / "python-ran").read_text() == "yes"
    assert (tests / "javascript-ran").read_text() == "yes"


@pytest.mark.parametrize("target", ["cloud", "all"])
def test_inferred_package_runner_also_executes_cloud_python_suite(tmp_path, target):
    import os
    import shutil
    if shutil.which("node") is None or shutil.which("npm") is None:
        pytest.skip("Node/npm required for the real mixed-runner regression")
    project = _project(tmp_path)
    tests = project / "cloud-functions-tests"
    (project / "package.json").write_text(json.dumps({"scripts": {"test": "node -e \"require('node:fs').appendFileSync('javascript-runs', 'x')\""}}))
    (tests / "test_python.py").write_text("from pathlib import Path\ndef test_python():\n    Path(__file__).with_name('python-ran').write_text('yes')\n    assert False, 'deliberate Python failure'\n")
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "helpers/test_functions.py"), "--project", str(project), "--target", target], env={**os.environ, "npm_config_cache": str(tmp_path / "npm-cache")}, capture_output=True, text=True)
    assert result.returncode == 1
    assert (project / "javascript-runs").read_text() == "x"
    assert (tests / "python-ran").read_text() == "yes"
