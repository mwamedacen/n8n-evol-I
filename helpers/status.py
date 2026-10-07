#!/usr/bin/env python3
"""Report project paths and environment readiness as JSON without exposing secrets."""
import argparse
import json
from pathlib import Path
import sys
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers.config import (
    environment_names, env_config_path, env_file_path, is_legacy_environment,
    load_env, load_yaml, target_identity,
)
from helpers.workspace import (
    DEFAULT_PATHS, workspace_root, workspace_path, harness_root,
    has_project_manifest, environment_path, state_path, build_path,
)


def project_status(workspace: Path, env: str | None = None) -> dict:
    result = {
        "project": str(workspace), "installedTooling": str(harness_root()),
        "format": "manifest" if has_project_manifest(workspace) else "legacy",
        "paths": {kind: str(workspace_path(workspace, kind)) for kind in DEFAULT_PATHS},
        "environments": [],
    }
    for name in [env] if env else environment_names(workspace):
        row = {"name": name, "workspace": str(environment_path(workspace, name)),
               "config": str(env_config_path(workspace, name)),
               "secretFile": str(env_file_path(workspace, name)),
               "state": str(state_path(workspace, name)), "build": str(build_path(workspace, name)),
               "format": "legacy" if is_legacy_environment(workspace, name) else "manifest"}
        try:
            config = load_yaml(name, workspace)
            target = target_identity(config)
            row.update(target=target, workflowCount=len(config.get("workflows") or {}),
                       status="configured" if load_env(name, workspace).get("N8N_API_KEY") else "missing-credentials")
        except (ValueError, FileNotFoundError, TypeError, KeyError, yaml.YAMLError):
            # YAML/JSON parser messages may quote user file contents. Keep them
            # out of the public status record; doctor provides focused checks.
            row["status"] = "invalid-configuration"
        result["environments"].append(row)
    result["liveConnectivityChecked"] = False
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", "--project", dest="workspace")
    parser.add_argument("--env", help="Inspect one environment; otherwise list all")
    parser.add_argument("--json", action="store_true", help="Compatibility flag; output is always JSON")
    args = parser.parse_args()
    try:
        result = project_status(workspace_root(args.workspace), args.env)
    except (ValueError, FileNotFoundError, TypeError, KeyError, yaml.YAMLError):
        print(json.dumps({"status": "invalid-configuration", "liveConnectivityChecked": False}))
        raise SystemExit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
