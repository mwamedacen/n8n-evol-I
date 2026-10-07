#!/usr/bin/env python3
"""Connect one environment to n8n; preserve existing files and isolate its bindings."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from helpers.config import (
    atomic_write, env_config_path, env_file_path, is_legacy_environment,
    load_env, load_yaml, save_yaml, target_identity, environment_names, validate_environment_aliases,
    configuration_snapshot, checked_environment_file, env_bindings_path,
)
from helpers.workspace import (
    MANIFEST_NAME, workspace_root, environment_path, state_path, build_path,
    has_project_manifest, load_project_manifest, validate_environment_name,
)
from helpers.n8n_client import N8nClient


def _is_placeholder_id(id_val) -> bool:
    return not id_val or str(id_val).startswith("your-") or id_val == "placeholder"


def _write_env_file(env_file: Path, api_key: str) -> None:
    if "\n" in api_key or "\r" in api_key:
        raise ValueError("API key must be a single line")
    atomic_write(env_file, f"N8N_API_KEY={api_key}\n", mode=0o600)


def _validate_instance(instance: str, api_key: str) -> None:
    N8nClient(base_url=instance, api_key=api_key).get("workflows", params={"limit": 1})


def _workflow_name_length(name: str) -> int:
    """Match n8n's validator count for surrogate pairs and presentation sequences."""
    return (len(name)
            - len(re.findall(r"[\uD800-\uDBFF][\uDC00-\uDFFF]", name))
            - len(re.findall(r"[^\uFE0F\uFE0E][\uFE0F\uFE0E]", name)))


def _mint_placeholder_workflows(workspace: Path, env_name: str, data: dict,
                                api_key: str, dry_run: bool) -> None:
    planned = []
    for key, workflow in (data.get("workflows") or {}).items():
        if not isinstance(workflow, dict) or not _is_placeholder_id(workflow.get("id")):
            continue
        full_name = f"{data.get('displayName', '')} {workflow.get('name', key)}{data.get('workflowNamePostfix', '')}".strip()
        name_length = _workflow_name_length(full_name)
        if not 1 <= name_length <= 128:
            raise ValueError(
                f"Workflow {key!r} planned name must be 1 to 128 characters long "
                f"(got {name_length}); adjust its label, display name or postfix"
            )
        planned.append((key, workflow, full_name))
    client = None
    for key, workflow, full_name in planned:
        if dry_run:
            print(f"  [dry-run] would mint workflow '{full_name}' for key '{key}'")
            continue
        client = client or N8nClient(data["n8n"]["instanceName"], api_key)
        result = client.create_workflow({"name": full_name, "nodes": [], "connections": {}, "settings": {}},
                                        project_id=data["n8n"].get("projectId"))
        workflow["id"] = result["id"]
        # Persist each minted ID so a later failure cannot lose earlier mappings.
        save_yaml(env_name, workspace, data)
        print(f"  Minted workflow '{full_name}' → id={result['id']} (key={key})")


def _protect_environment(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    ignore = checked_environment_file(directory, ".gitignore")
    existing = ignore.read_text() if ignore.exists() else ""
    rules = [".env", ".env.*", "bindings.json", "state/", "build/", ".rebind-backups/"]
    # Git applies the last matching rule. Merely finding an earlier exclusion
    # does not protect a file when a later user rule negates it.
    if existing.splitlines()[-len(rules):] != rules:
        atomic_write(ignore, existing + ("\n" if existing and not existing.endswith("\n") else "") + "\n".join(rules) + "\n")


def _backup_for_rebind(workspace: Path, env_name: str) -> Path:
    directory = environment_path(workspace, env_name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = checked_environment_file(directory, ".rebind-backups") / f"{env_name}-{stamp}"
    backup.mkdir(parents=True, mode=0o700)
    for source in (env_config_path(workspace, env_name), env_file_path(workspace, env_name), env_bindings_path(workspace, env_name)):
        if source.exists():
            shutil.copy2(source, backup / source.name)
            (backup / source.name).chmod(0o600)
    for label, source in (("state", state_path(workspace, env_name)), ("build", build_path(workspace, env_name))):
        if source.exists():
            shutil.move(str(source), backup / label)
    if not is_legacy_environment(workspace, env_name):
        env_bindings_path(workspace, env_name).unlink(missing_ok=True)
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", "--project", dest="workspace", default=None, help="Project path; discovered from parent directories by default")
    parser.add_argument("--env", required=True)
    parser.add_argument("--instance", default=None, help="n8n deployment URL")
    parser.add_argument("--project-id", default=None, help="Optional n8n project ID; checked before creating workflows")
    keys = parser.add_mutually_exclusive_group()
    keys.add_argument("--api-key", default=None, help="API key (prefer --api-key-stdin)")
    keys.add_argument("--api-key-stdin", action="store_true", help="Read API key from standard input")
    parser.add_argument("--postfix", default=None)
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rebind", action="store_true", help="Back up this environment and reset bindings/state for a different target")
    parser.add_argument("--migrate", action="store_true", help="Copy a legacy environment into its manifest workspace, retaining the original files")
    parser.add_argument("--force-update-instance", action="store_true", help="Deprecated: use --rebind, which resets old target bindings")
    args = parser.parse_args()
    validate_environment_name(args.env)
    ws = workspace_root(args.workspace)
    validate_environment_aliases([*environment_names(ws), args.env])
    observed_names = [*environment_names(ws), args.env]
    observed_config = configuration_snapshot(ws, observed_names)
    config_file = env_config_path(ws, args.env)
    existing = config_file.exists()
    legacy = is_legacy_environment(ws, args.env)
    if args.force_update_instance and not args.rebind:
        parser.error("--force-update-instance cannot safely reuse target IDs; use --rebind with the new API key")
    if args.migrate and not has_project_manifest(ws):
        parser.error("--migrate requires n8n-project.yml; run init.py --adopt first")
    if args.migrate and args.rebind:
        parser.error("Migrate the existing target first, then rebind separately")
    if args.migrate and legacy:
        destination = environment_path(ws, args.env)
        destinations = [checked_environment_file(destination, name) for name in ("workspace.yml", "bindings.json", ".env", "state", "build")]
        collisions = [path for path in destinations if path.exists()]
        if collisions:
            parser.error("Migration destination already has data; preserve and reconcile it first: " + ", ".join(str(path) for path in collisions))
    try:
        data = load_yaml(args.env, ws) if existing else {
            "name": args.env, "displayName": args.display_name or args.env.title(),
            "workflowNamePostfix": args.postfix if args.postfix is not None else ("" if args.env == "prod" else f" [{args.env.upper()}]"),
            "n8n": {"instanceName": args.instance or ""}, "credentials": {}, "workflows": {},
        }
    except ValueError:
        if not args.rebind:
            raise
        data = yaml.safe_load(config_file.read_text())
        bindings_file = env_bindings_path(ws, args.env)
        if bindings_file.exists():
            bindings = json.loads(bindings_file.read_text())
            data.update({key: bindings.get(key, {}) for key in ("workflows", "credentials")})
    original = deepcopy(data)
    if args.migrate and legacy:
        # Legacy deployment activated by default. Make that implicit behavior
        # explicit before switching formats, preserving any chosen policy.
        data.setdefault("activation", "automatic")
    if args.display_name is not None:
        data["displayName"] = args.display_name
    if args.postfix is not None:
        data["workflowNamePostfix"] = args.postfix
    if args.instance:
        data["n8n"]["instanceName"] = args.instance
    if args.project_id:
        data["n8n"]["projectId"] = args.project_id
    changed_target = existing and target_identity(data) != target_identity(original)
    if changed_target and not args.rebind:
        parser.error("Target differs from existing environment; use --rebind with credentials for the new target")
    if not data["n8n"].get("instanceName"):
        if args.dry_run:
            parser.error("--instance is required to preview a new environment")
        data["n8n"]["instanceName"] = input(f"n8n URL for '{args.env}': ").strip()
    target_url = target_identity(data)["instanceName"]
    for other in environment_names(ws):
        if other == args.env:
            continue
        other_data = load_yaml(other, ws)
        if target_identity(other_data)["instanceName"] == target_url:
            parser.error(f"Environment '{other}' already uses this n8n deployment; each environment requires a separate deployment URL")
    api_key = sys.stdin.read().strip() if args.api_key_stdin else args.api_key
    if args.rebind:
        if not api_key and not args.dry_run:
            parser.error("--rebind requires a new explicit --api-key-stdin or --api-key")
        data["credentials"] = {}
        for workflow in (data.get("workflows") or {}).values():
            if isinstance(workflow, dict):
                workflow["id"] = ""
    elif not api_key:
        api_key = load_env(args.env, ws).get("N8N_API_KEY")
    if not api_key and not existing:
        # Backward-compatible bootstrap input, used only for this explicit env.
        api_key = os.environ.get("N8N_API_KEY")
    if args.dry_run:
        print(f"[dry-run] would configure environment '{args.env}' at {data['n8n']['instanceName']}")
        if args.rebind:
            print("  [dry-run] would preserve old state in a private backup and reset target bindings")
        if args.migrate:
            print("  [dry-run] would copy legacy configuration and secrets; original files remain")
        _mint_placeholder_workflows(ws, args.env, data, api_key or "", True)
        print("Dry-run complete. No files written.")
        return
    if not api_key:
        if not sys.stdin.isatty():
            parser.error(f"Missing API key for '{args.env}'; use --api-key-stdin")
        api_key = getpass.getpass(f"API key for '{args.env}': ")
    if "\n" in api_key or "\r" in api_key:
        parser.error("API key must be a single line")
    try:
        _validate_instance(data["n8n"]["instanceName"], api_key)
        if data["n8n"].get("projectId"):
            N8nClient(data["n8n"]["instanceName"], api_key).require_project(data["n8n"]["projectId"])
    except Exception as error:
        print(f"ERROR: Could not validate n8n target: {error}", file=sys.stderr)
        print("No local configuration or secrets changed.", file=sys.stderr)
        raise SystemExit(1)
    from helpers.sync_state import operation_lock
    with operation_lock(ws, args.env):
        if configuration_snapshot(ws, observed_names) != observed_config:
            raise SystemExit("Environment configuration changed during bootstrap; review it and retry")
        old_secret = env_file_path(ws, args.env)
        old_secret_bytes = old_secret.read_bytes() if old_secret.exists() else None
        old_state, old_build = state_path(ws, args.env), build_path(ws, args.env)
        if args.rebind:
            _protect_environment(environment_path(ws, args.env))
            backup = _backup_for_rebind(ws, args.env)
            print(f"  Preserved previous target files at {backup}")
        if has_project_manifest(ws) and (not existing or args.migrate):
            manifest = load_project_manifest(ws)
            environments = manifest.setdefault("environments", {})
            entry = environments.get(args.env)
            entry = dict(entry) if isinstance(entry, dict) else {"path": entry or f"environments/{args.env}"}
            entry.pop("legacy", None)
            environments[args.env] = entry
            atomic_write(ws / MANIFEST_NAME, yaml.safe_dump(manifest, sort_keys=False))
        target_dir = environment_path(ws, args.env)
        _protect_environment(target_dir)
        if is_legacy_environment(ws, args.env):
            ignore = target_dir / ".gitignore"
            contents = ignore.read_text()
            if ".env.*" not in contents.splitlines():
                atomic_write(ignore, contents + ".env.*\n")
        save_yaml(args.env, ws, data)
        secret_file = env_file_path(ws, args.env)
        if args.migrate and legacy and old_secret_bytes is not None:
            atomic_write(secret_file, old_secret_bytes.decode(), mode=0o600)
        elif not secret_file.exists() or args.rebind:
            _write_env_file(secret_file, api_key)
        if (args.api_key or args.api_key_stdin) and not args.rebind:
            # Update only this key, preserving other values and comments verbatim.
            from dotenv import set_key
            set_key(str(secret_file), "N8N_API_KEY", api_key, quote_mode="never")
            secret_file.chmod(0o600)
        for old, new in ((old_state, state_path(ws, args.env)), (old_build, build_path(ws, args.env))):
            if args.migrate and legacy and old.exists() and old != new:
                if new.exists() and any(new.iterdir()):
                    raise ValueError(f"Migration destination is not empty: {new}; original files retained")
                shutil.copytree(old, new, dirs_exist_ok=True)
            new.mkdir(parents=True, exist_ok=True)
        _mint_placeholder_workflows(ws, args.env, data, api_key, False)
        print(f"bootstrap-env complete: {args.env} → {env_config_path(ws, args.env)}")



if __name__ == "__main__":
    main()
