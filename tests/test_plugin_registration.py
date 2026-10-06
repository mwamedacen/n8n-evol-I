"""Native plugin loading and the real hook process; no model/API calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_claude_registers_router_and_all_advertised_commands(tmp_path):
    executable = shutil.which("claude")
    if executable is None:
        pytest.skip("Claude Code is not installed; separate live load evidence required")
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"}}
    env.update(CLAUDE_CONFIG_DIR=str(tmp_path / "claude-config"), CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
    result = subprocess.run([executable, "--plugin-dir", str(ROOT), "--setting-sources", "", "plugin", "details", "n8n-evol-I"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    line = next(line for line in result.stdout.splitlines() if "Skills (" in line)
    names = set(line.split(")", 1)[1].strip().split(", "))
    assert names == {"n8n", "deploy", "deploy_all", "resync", "resync_all", "tidyup", "debug", "run", "doctor", "validate", "test"}
    assert "Hooks (1)" in result.stdout and "PostToolUse" in result.stdout


def test_hook_executes_real_layout_from_installation_path_with_spaces(tmp_path):
    toolkit = tmp_path / "installed toolkit"
    for directory in ("helpers", "hooks", "scripts"):
        shutil.copytree(ROOT / directory, toolkit / directory, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    shutil.copyfile(ROOT / 'requirements.txt', toolkit / 'requirements.txt')
    project = tmp_path / "project"
    templates = project / "workflows"
    templates.mkdir(parents=True)
    (project / "config").mkdir()
    (project / "n8n-project.yml").write_text("version: 1\npaths:\n  templates: workflows\n  config: config\nenvironments: {}\n")
    workflow = {"name": "Hook test", "nodes": [
        {"id": "a", "name": "Start", "type": "n8n-nodes-base.manualTrigger", "position": [0, 0], "parameters": {}},
        {"id": "b", "name": "Next", "type": "n8n-nodes-base.set", "position": [0, 0], "parameters": {}},
    ], "connections": {"Start": {"main": [[{"node": "Next", "type": "main", "index": 0}]]}}, "settings": {}}
    target = templates / "hello.template.json"
    target.write_text(json.dumps(workflow))
    # A Python-only PATH exercises the supported layout fallback without any
    # package download or global dependency/cache write.
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "python3").symlink_to(sys.executable)
    env = {"PATH": str(binaries), "CLAUDE_PLUGIN_ROOT": str(toolkit), "PYTHONDONTWRITEBYTECODE": "1", "N8N_EVOL_PYTHON": sys.executable}
    hook = json.loads((toolkit / "hooks/hooks.json").read_text())["hooks"]["PostToolUse"][0]["hooks"][0]
    result = subprocess.run(["/bin/sh", "-c", hook["command"]], input=json.dumps({"cwd": str(project), "tool_input": {"file_path": str(target)}}), cwd=project, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "exited" not in result.stderr
    updated = json.loads(target.read_text())
    assert updated["nodes"][0]["position"] != updated["nodes"][1]["position"]
    for node in updated["nodes"]:
        node["position"] = [0, 0]
    assert updated == workflow
