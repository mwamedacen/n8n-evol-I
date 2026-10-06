"""Resolve project sources, environment workspaces and immutable installed tooling."""
import re
import sys
from pathlib import Path

import yaml

MANIFEST_NAME = "n8n-project.yml"
_DEFAULT_WS_NAME = "n8n-evol-I-workspace"
DEFAULT_PATHS = {
    "config": "n8n-config",
    "templates": "n8n-workflows-template",
    "functions": "n8n-functions",
    "function_tests": "n8n-functions-tests",
    "prompts": "n8n-prompts",
    "assets": "n8n-assets",
    "cloud_functions": "cloud-functions",
    "cloud_tests": "cloud-functions-tests",
}
_announced = False


def harness_root() -> Path:
    """Return the installed package root independently of cwd and symlinks."""
    return Path(__file__).resolve().parent.parent


def assert_not_in_harness(out_path: Path) -> None:
    """Refuse project writes inside installed tooling, including through symlinks."""
    if Path(out_path).resolve().is_relative_to(harness_root()):
        raise RuntimeError(
            f"Refusing to write inside the harness directory: {out_path}\n"
            "Helpers must only write to project/environment paths."
        )


def validate_environment_name(env: str) -> str:
    if not isinstance(env, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", env):
        raise ValueError("Environment names must contain only letters, digits, '_' or '-' and start with a letter or digit")
    return env


def validate_workflow_key(key: str) -> str:
    """Validate a portable workflow key, including nested source directories."""
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*(?:/[A-Za-z0-9][A-Za-z0-9_-]*)*", key):
        raise ValueError("Workflow keys must contain slash-separated names using letters, digits, '_' or '-', with no empty, '.' or '..' component")
    return key


def has_project_manifest(workspace: Path) -> bool:
    return (Path(workspace).resolve() / MANIFEST_NAME).is_file()


def _relative_path(root: Path, value: str, label: str, *, confined: bool = False) -> Path:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{label} must be a nonempty relative path")
    candidate = Path(value)
    if candidate.is_absolute() or "\\" in value:
        raise ValueError(f"{label} must be a portable path relative to {MANIFEST_NAME}")
    resolved = (root / candidate).resolve()
    if confined and (resolved == root or not resolved.is_relative_to(root)):
        raise ValueError(f"{label} must stay inside the project directory")
    assert_not_in_harness(resolved)
    return resolved


def load_project_manifest(workspace: Path) -> dict:
    """Load and validate configuration without mutating it; absent means legacy."""
    root = Path(workspace).resolve()
    manifest = root / MANIFEST_NAME
    if not manifest.exists():
        return {}
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{manifest} must contain a mapping")
    if data.get("version", 1) != 1:
        raise ValueError(f"Unsupported project version in {manifest}: {data.get('version')}")
    paths = data.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError(f"paths in {manifest} must be a mapping")
    for kind, value in paths.items():
        if kind not in DEFAULT_PATHS:
            raise ValueError(f"Unknown project path kind: {kind}")
        _relative_path(root, value, f"paths.{kind}")
    environments = data.get("environments", {})
    if not isinstance(environments, dict):
        raise ValueError(f"environments in {manifest} must be a mapping")
    occupied: dict[Path, str] = {}
    scoped_names: dict[str, str] = {}
    for env, entry in environments.items():
        validate_environment_name(env)
        scoped = env.upper().replace("-", "_")
        if scoped in scoped_names:
            raise ValueError(f"Environment names share a secret-variable namespace: {scoped_names[scoped]} and {env}")
        scoped_names[scoped] = env
        if not isinstance(entry, (dict, str)):
            raise ValueError(f"environments.{env} must be a path or mapping")
        value = entry.get("path", f"environments/{env}") if isinstance(entry, dict) else entry
        path = _relative_path(root, value, f"environments.{env}.path", confined=True)
        for previous, name in occupied.items():
            if path.is_relative_to(previous) or previous.is_relative_to(path):
                raise ValueError(f"Environment paths overlap: {name} and {env}")
        occupied[path] = env
    return data


def _is_legacy_root(path: Path) -> bool:
    return path.name == _DEFAULT_WS_NAME or (
        (path / "n8n-config").is_dir() and (path / "n8n-workflows-template").is_dir()
    )


def discover_project(start: Path | None = None) -> Path | None:
    """Find the nearest project, respecting Git repository/worktree boundaries."""
    current = Path(start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if has_project_manifest(candidate) or _is_legacy_root(candidate):
            return candidate
        child = candidate / _DEFAULT_WS_NAME
        if child.is_dir() and (has_project_manifest(child) or _is_legacy_root(child)):
            return child.resolve()
        # A worktree uses a .git file; never accidentally adopt its parent repo.
        if (candidate / ".git").exists():
            break
    return None


def workspace_root(override=None) -> Path:
    """Explicit root, nearest manifest/legacy workspace, then legacy default.

    This function never creates directories. Operations must use ensure_workspace
    before mutating an undiscovered project; setup is responsible for creation.
    """
    global _announced
    if override is not None:
        path = Path(override).expanduser().resolve()
        if path.name == MANIFEST_NAME and path.is_file():
            path = path.parent
    else:
        path = discover_project() or (Path.cwd() / _DEFAULT_WS_NAME).resolve()
    if not _announced:
        print(f"[n8n-evol-I] project: {path}", file=sys.stderr)
        _announced = True
    return path


def workspace_path(workspace: Path, kind: str, *parts: str) -> Path:
    """Return a configured source path. Explicit mappings may share external sources."""
    if kind not in DEFAULT_PATHS:
        raise ValueError(f"Unknown project path kind: {kind}")
    root = Path(workspace).resolve()
    manifest = load_project_manifest(root)
    value = manifest.get("paths", {}).get(kind, DEFAULT_PATHS[kind])
    base = _relative_path(root, value, f"paths.{kind}")
    path = base
    for part in parts:
        component = Path(part)
        if component.is_absolute() or ".." in component.parts or "\\" in str(part):
            raise ValueError(f"Unsafe path component: {part}")
        path = path / component
    resolved = path.resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"Source path escapes its configured root: {path}")
    assert_not_in_harness(resolved)
    return resolved


def environment_path(workspace: Path, env: str) -> Path:
    """Resolve one environment workspace, or the legacy shared config directory."""
    validate_environment_name(env)
    root = Path(workspace).resolve()
    manifest = load_project_manifest(root)
    if not has_project_manifest(root):
        return workspace_path(root, "config")
    entry = manifest.get("environments", {}).get(env, {})
    value = entry.get("path", f"environments/{env}") if isinstance(entry, dict) else entry
    requested = _relative_path(root, value, f"environments.{env}.path", confined=True)
    # An undeclared environment's default is still a real destination. Check it
    # against declared mappings before bootstrap can create or read any files.
    for other, other_entry in manifest.get("environments", {}).items():
        if other == env:
            continue
        other_value = other_entry.get("path", f"environments/{other}") if isinstance(other_entry, dict) else other_entry
        other_path = _relative_path(root, other_value, f"environments.{other}.path", confined=True)
        if requested.is_relative_to(other_path) or other_path.is_relative_to(requested):
            raise ValueError(f"Environment paths overlap: {env} and {other}")
    return requested


def _legacy_environment(workspace: Path, env: str) -> bool:
    manifest = load_project_manifest(workspace)
    entry = manifest.get("environments", {}).get(env, {})
    explicit_legacy = isinstance(entry, dict) and entry.get("legacy") is True
    unregistered_legacy = env not in manifest.get("environments", {}) and (workspace_path(workspace, "config") / f"{env}.yml").is_file()
    return not has_project_manifest(workspace) or explicit_legacy or unregistered_legacy


def state_path(workspace: Path, env: str) -> Path:
    validate_environment_name(env)
    root = Path(workspace).resolve()
    path = root / ".n8n-state" / env if _legacy_environment(root, env) else environment_path(root, env) / "state"
    return _runtime_path(path, root)


def build_path(workspace: Path, env: str) -> Path:
    validate_environment_name(env)
    root = Path(workspace).resolve()
    path = root / "n8n-build" / env if _legacy_environment(root, env) else environment_path(root, env) / "build"
    return _runtime_path(path, root)


def _runtime_path(path: Path, root: Path) -> Path:
    """Runtime directories cannot redirect writes into another workspace."""
    resolved = path.resolve()
    if resolved != path or not resolved.is_relative_to(root):
        raise ValueError(f"Runtime path must not escape or redirect through symlinks: {path}")
    assert_not_in_harness(resolved)
    return resolved


def ensure_workspace(path: Path) -> None:
    """Check the project exists and required source directories are present."""
    required = [workspace_path(path, "config"), workspace_path(path, "templates")]
    missing = [str(directory) for directory in required if not directory.is_dir()]
    if missing:
        raise SystemExit(
            f"Workspace at {path} is incomplete or missing.\n"
            f"Missing: {', '.join(missing)}\n"
            "Run `python3 <harness>/helpers/init.py --project <path>` first."
        )


def require_project(override=None) -> Path:
    """Resolve an operational project and fail without creating missing paths."""
    root = workspace_root(override)
    ensure_workspace(root)
    return root
