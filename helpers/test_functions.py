#!/usr/bin/env python3
"""Run unit tests over JS used in n8n Code nodes and/or Python used in cloud functions."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.workspace import load_project_manifest, require_project, workspace_path
from helpers.config import load_common


def _layout(workspace: Path) -> dict:
    common = load_common(workspace)
    return common.get("workspace_layout", {}) or {}


def _resolve(workspace: Path, key: str, default: str) -> Path:
    kind = {"n8n_functions_tests_dir": "function_tests", "cloud_functions_tests_dir": "cloud_tests"}[key]
    if kind in load_project_manifest(workspace).get("paths", {}):
        return workspace_path(workspace, kind)
    layout = _layout(workspace)
    rel = layout.get(key, default).rstrip("/")
    return (workspace / rel).resolve()


def project_test_command(workspace: Path, target: str) -> tuple[list[str], Path] | None:
    """Explicit argv first, then an existing runner, otherwise bundled defaults."""
    manifest = load_project_manifest(workspace)
    commands = manifest.get("commands", {})
    if not isinstance(commands, dict) or not isinstance(commands.get("test", {}), dict):
        raise ValueError("commands.test must map n8n/cloud to argument lists")
    command = commands.get("test", {}).get(target)
    if command is not None:
        if not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg for arg in command):
            raise ValueError(f"commands.test.{target} must be a nonempty list of arguments")
        return command, workspace

    kind = "function_tests" if target == "n8n" else "cloud_tests"
    source_kind = "functions" if target == "n8n" else "cloud_functions"
    for directory in dict.fromkeys((workspace_path(workspace, kind), workspace_path(workspace, source_kind), workspace)):
        package = directory / "package.json"
        if not package.is_file():
            continue
        data = json.loads(package.read_text())
        script = f"test:{target}" if f"test:{target}" in data.get("scripts", {}) else "test"
        if script not in data.get("scripts", {}):
            continue
        manager = str(data.get("packageManager", "")).partition("@")[0]
        if manager not in ("npm", "pnpm", "yarn", "bun"):
            manager = next((manager for lock, manager in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lock", "bun"), ("bun.lockb", "bun")) if (directory / lock).exists()), "npm")
        return [manager, "run", script], directory
    pyproject = workspace / "pyproject.toml"
    if (workspace / "pytest.ini").is_file() or (pyproject.is_file() and "[tool.pytest.ini_options]" in pyproject.read_text()):
        return [sys.executable, "-m", "pytest"], workspace
    return None


def _run_project_command(command: list[str], cwd: Path, target: str, name_filter: str | None) -> tuple[int, str]:
    if name_filter and not any("{filter}" in arg for arg in command):
        print(f"{target}: project command has no {{filter}} placeholder; running its full suite", file=sys.stderr)
    argv = [arg.replace("{filter}", name_filter or "") for arg in command]
    result = subprocess.run(argv, cwd=cwd)
    return result.returncode, f"{target}: project test command (exit={result.returncode})"


def _run_node_tests(tests_dir: Path, name_filter: str | None) -> tuple[int, str]:
    if not tests_dir.is_dir():
        return (0, "n8n: no tests dir")
    tests = sorted(tests_dir.glob("*.test.js"))
    if name_filter:
        tests = [t for t in tests if name_filter in t.stem]
    if not tests:
        return (0, "n8n: no tests")

    if shutil.which("node") is None:
        return (1, "n8n: node binary not found on PATH")

    pkg_json = tests_dir / "package.json"
    if pkg_json.exists():
        # Defer to project's npm test runner
        cmd = ["npm", "test", "--silent"]
        cwd = tests_dir
    else:
        cmd = ["node", "--test", *[str(t) for t in tests]]
        cwd = tests_dir

    r = subprocess.run(cmd, cwd=cwd)
    return (r.returncode, f"n8n: ran {len(tests)} test file(s) (exit={r.returncode})")


def _run_pytest_tests(tests_dir: Path, name_filter: str | None) -> tuple[int, str]:
    if not tests_dir.is_dir():
        return (0, "cloud: no tests dir")
    tests = sorted(tests_dir.glob("test_*.py"))
    if name_filter:
        tests = [t for t in tests if name_filter in t.stem]
    if not tests:
        return (0, "cloud: no tests")

    cmd = [sys.executable, "-m", "pytest", "-v", *[str(t) for t in tests]]
    r = subprocess.run(cmd, cwd=tests_dir)
    return (r.returncode, f"cloud: ran {len(tests)} test file(s) (exit={r.returncode})")


def _run_pytest_n8n_tests(tests_dir: Path, name_filter: str | None) -> tuple[int, str]:
    """Run pytest over test_*.py files in n8n-functions-tests/ (Python pure-function tests)."""
    if not tests_dir.is_dir():
        return (0, "n8n-py: no tests dir")
    tests = sorted(tests_dir.glob("test_*.py"))
    if name_filter:
        tests = [t for t in tests if name_filter in t.stem]
    if not tests:
        return (0, "n8n-py: no tests")

    cmd = [sys.executable, "-m", "pytest", "-v", *[str(t) for t in tests]]
    r = subprocess.run(cmd, cwd=tests_dir)
    return (r.returncode, f"n8n-py: ran {len(tests)} test file(s) (exit={r.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", "--workspace", dest="workspace", default=None)
    parser.add_argument("--target", choices=("n8n", "cloud", "all"), default="all")
    parser.add_argument("--filter", default=None, dest="name_filter")
    args = parser.parse_args()

    ws = require_project(args.workspace)
    n8n_tests = _resolve(ws, "n8n_functions_tests_dir", "n8n-functions-tests")
    cloud_tests = _resolve(ws, "cloud_functions_tests_dir", "cloud-functions-tests")

    summaries: list[tuple[int, str]] = []
    executed = set()
    for target in ("n8n", "cloud") if args.target == "all" else (args.target,):
        configured = project_test_command(ws, target)
        if configured:
            command, cwd = configured
            identity = (tuple(command), cwd)
            if identity not in executed:
                summaries.append(_run_project_command(command, cwd, target, args.name_filter))
                executed.add(identity)
            explicit = load_project_manifest(ws).get("commands", {}).get("test", {}).get(target)
            if explicit is None:
                # An inferred Python runner cannot execute JavaScript tests,
                # and an inferred package runner cannot establish Python test
                # coverage. Only an explicit project command owns the full suite.
                if command[:3] == [sys.executable, "-m", "pytest"]:
                    if target == "n8n":
                        summaries.append(_run_node_tests(n8n_tests, args.name_filter))
                elif target == "n8n":
                    summaries.append(_run_pytest_n8n_tests(n8n_tests, args.name_filter))
                else:
                    summaries.append(_run_pytest_tests(cloud_tests, args.name_filter))
        elif target == "n8n":
            summaries.append(_run_node_tests(n8n_tests, args.name_filter))
            summaries.append(_run_pytest_n8n_tests(n8n_tests, args.name_filter))
        else:
            summaries.append(_run_pytest_tests(cloud_tests, args.name_filter))

    print("\nTest summary:")
    for code, line in summaries:
        print(f"  [{'OK' if code == 0 else 'FAIL'}] {line}")

    sys.exit(0 if all(c == 0 for c, _ in summaries) else 1)


if __name__ == "__main__":
    main()
