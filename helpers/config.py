import os
import json
import re
import tempfile
import hashlib
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from helpers.workspace import (
    environment_path, has_project_manifest, load_project_manifest,
    validate_environment_name, workspace_path, assert_not_in_harness, MANIFEST_NAME,
)


def is_legacy_environment(workspace: Path, env_name: str) -> bool:
    validate_environment_name(env_name)
    if not has_project_manifest(workspace):
        return True
    environments = load_project_manifest(workspace).get("environments", {})
    entry = environments.get(env_name)
    return (isinstance(entry, dict) and entry.get("legacy") is True) or (
        entry is None and (workspace_path(workspace, "config") / f"{env_name}.yml").exists()
    )


def environment_names(workspace: Path) -> list[str]:
    names = set(load_project_manifest(workspace).get("environments", {})) if has_project_manifest(workspace) else set()
    config_dir = workspace_path(workspace, "config")
    names.update(p.stem for p in config_dir.glob("*.yml") if p.stem not in {"common", "deployment_order"})
    validate_environment_aliases(names)
    return sorted(names)


def validate_environment_aliases(names) -> None:
    seen = {}
    for name in names:
        validate_environment_name(name)
        alias = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
        if alias in seen and seen[alias] != name:
            raise ValueError(f"Environment names '{seen[alias]}' and '{name}' share a scoped-variable namespace; choose distinct names")
        seen[alias] = name


list_environments = environment_names


def select_environments(workspace: Path, register_in: str | None = None) -> list[str]:
    """Select explicit destinations or the only environment; never fan out silently."""
    names = list(dict.fromkeys(name.strip() for name in register_in.split(",") if name.strip())) if register_in else environment_names(workspace)
    if not names or (not register_in and len(names) != 1):
        raise ValueError("Choose --env/--register-in explicitly; exactly one default environment is required")
    for name in names:
        validate_environment_name(name)
        if not env_config_path(workspace, name).exists():
            raise ValueError(f"Environment '{name}' is not configured; run bootstrap_env.py first")
    return names


def configuration_snapshot(workspace: Path, names) -> dict:
    """Fingerprints for optimistic validation before acquiring a mutation lock."""
    paths = {workspace / MANIFEST_NAME}
    for name in set(names):
        paths.update((env_config_path(workspace, name), env_file_path(workspace, name),
                      env_bindings_path(workspace, name)))
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            for path in paths}


def checked_environment_file(directory: Path, filename: str) -> Path:
    """Environment-owned files cannot borrow another file through a symlink."""
    path = directory / filename
    if path.is_symlink() or path.resolve() != path:
        raise ValueError(f"Environment file must not redirect through symlinks: {path}")
    assert_not_in_harness(path)
    return path


def env_config_path(workspace: Path, env_name: str) -> Path:
    if is_legacy_environment(workspace, env_name):
        return checked_environment_file(workspace_path(workspace, "config"), f"{env_name}.yml")
    return checked_environment_file(environment_path(workspace, env_name), "workspace.yml")


def env_file_path(workspace: Path, env_name: str) -> Path:
    if is_legacy_environment(workspace, env_name):
        return checked_environment_file(workspace_path(workspace, "config"), f".env.{env_name}")
    return checked_environment_file(environment_path(workspace, env_name), ".env")


def env_bindings_path(workspace: Path, env_name: str) -> Path:
    return checked_environment_file(environment_path(workspace, env_name), "bindings.json")


def atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    """Replace one file atomically without exposing partially written state."""
    assert_not_in_harness(path)
    if path.is_symlink():
        raise ValueError(f"Refusing to replace a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    old_mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, old_mode if mode is None else mode)
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def target_identity(data: dict) -> dict:
    n8n = data.get("n8n", {})
    url = str(n8n.get("instanceName", "")).strip()
    if url and "://" not in url:
        url = "https://" + url
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("n8n.instanceName must be an HTTP(S) deployment URL without embedded credentials, query or fragment")
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    host = f"[{host}]" if ":" in host else host
    if parsed.port and parsed.port != {"http": 80, "https": 443}[scheme]:
        host += f":{parsed.port}"
    url = urlunsplit((scheme, host, parsed.path.rstrip("/"), "", ""))
    return {"instanceName": url, "projectId": n8n.get("projectId")}


def load_env(env_name: str, workspace: Path) -> dict:
    """Return only the selected environment's values; never mutate os.environ.

    Scoped process overrides use N8N_ENV_DEV__NAME. N8N_ENV_DEV_API_KEY is
    a shorthand for N8N_API_KEY. Generic process secrets are not inherited.
    """
    env_file = env_file_path(workspace, env_name)
    validate_environment_aliases([*environment_names(workspace), env_name])
    loaded = dict(dotenv_values(env_file, interpolate=False)) if env_file.exists() else {}
    loaded = {key: val for key, val in loaded.items() if val is not None}
    prefix = "N8N_ENV_" + re.sub(r"[^A-Za-z0-9]", "_", env_name).upper()
    for key, value in os.environ.items():
        if key.startswith(prefix + "__"):
            loaded[key[len(prefix) + 2:]] = value
    if prefix + "_API_KEY" in os.environ:
        loaded["N8N_API_KEY"] = os.environ[prefix + "_API_KEY"]
    return loaded


def load_yaml(env_name: str, workspace: Path, *, validate: bool = True) -> dict:
    """Read environment config and private bindings, or an existing legacy YAML."""
    yaml_file = env_config_path(workspace, env_name)
    if not yaml_file.exists():
        raise FileNotFoundError(
            f"No environment config at {yaml_file}. "
            f"Run `python3 <harness>/helpers/bootstrap_env.py --env {env_name}` first."
        )
    with open(yaml_file) as f:
        data = yaml.safe_load(f) or {}
    if validate:
        _validate_env_yaml(data, yaml_file)
    if not is_legacy_environment(workspace, env_name):
        bindings_file = env_bindings_path(workspace, env_name)
        bindings = json.loads(bindings_file.read_text()) if bindings_file.exists() else {}
        if not isinstance(bindings, dict):
            raise ValueError(f"Expected an object in {bindings_file}")
        if bindings.get("target") is not None and bindings["target"] != target_identity(data):
            raise ValueError(f"Environment '{env_name}' target changed; run bootstrap_env.py --env {env_name} --rebind with the new target and credentials before reusing it.")
        for key in ("workflows", "credentials"):
            data[key] = bindings.get(key, {})
    return data


def save_yaml(env_name: str, workspace: Path, data: dict, *, validate: bool = True) -> None:
    """Save config and environment bindings separately; keep legacy layouts intact."""
    yaml_file = env_config_path(workspace, env_name)
    if validate:
        _validate_env_yaml(data, yaml_file)
    if is_legacy_environment(workspace, env_name):
        atomic_write(yaml_file, yaml.safe_dump(data, sort_keys=False))
        return
    config = {key: value for key, value in data.items() if key not in {"workflows", "credentials"}}
    bindings_file = env_bindings_path(workspace, env_name)
    previous = json.loads(bindings_file.read_text()) if bindings_file.exists() else {}
    target = target_identity(data)
    if previous.get("target") is not None and previous["target"] != target:
        raise ValueError("Target differs from existing bindings; use bootstrap_env.py --rebind")
    bindings = dict(previous, version=1, target=target,
                    workflows=data.get("workflows") or {}, credentials=data.get("credentials") or {})
    atomic_write(bindings_file, json.dumps(bindings, indent=2) + "\n", mode=0o600)
    atomic_write(yaml_file, yaml.safe_dump(config, sort_keys=False))


def _validate_env_yaml(data: dict, path: Path) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    for key in ("name", "displayName", "n8n"):
        if key not in data:
            raise ValueError(f"Missing required key '{key}' in {path}")
    if "instanceName" not in data.get("n8n", {}):
        raise ValueError(f"Missing required key 'n8n.instanceName' in {path}")


def load_common(workspace: Path) -> dict:
    """Read n8n-config/common.yml. Returns {} if absent; raises only on YAML parse error."""
    common_file = workspace_path(workspace, "config", "common.yml")
    if not common_file.exists():
        return {}
    with open(common_file) as f:
        return yaml.safe_load(f) or {}


def get_config_value(config: dict, dot_path: str) -> Any:
    """Look up a dot-notation path in a nested dict. Raises KeyError if not found."""
    parts = dot_path.split(".")
    current = config
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            raise KeyError(f"Path '{dot_path}' not found in config (missing key '{part}')")
        current = current[part]
    return current


def flatten_config(config: dict, prefix: str = "") -> dict:
    """Flatten a nested dict to dot-path keys."""
    result = {}
    for key, val in config.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            result.update(flatten_config(val, full_key))
        else:
            result[full_key] = val
    return result
