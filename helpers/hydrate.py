#!/usr/bin/env python3
"""Resolve all {{INTERPOLATE_...}} / {{@...}} placeholders in a workflow template for one env."""
import argparse
import json
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.workspace import workspace_root, ensure_workspace, workspace_path, build_path
from helpers.placeholder import env_resolver, file_resolver, js_resolver, py_resolver, uuid_resolver, validator
from helpers.placeholder.paths import source_file
from helpers.sync_state import atomic_write, digest, identity, node_namespace
from helpers.workspace import validate_workflow_key


def hydrate(env_name: str, workflow_key: str, workspace: Path, strict: bool = False) -> Path:
    """Hydrate a template and return the path to the generated JSON."""
    ensure_workspace(workspace)
    validate_workflow_key(workflow_key)

    template_dir = workspace_path(workspace, "templates")
    template_file = workspace_path(workspace, 'templates', f"{workflow_key}.template.json")
    if not template_file.exists():
        raise FileNotFoundError(f"Template not found: {template_file}")

    text = template_file.read_text(encoding="utf-8")
    source = json.loads(text)
    refs = re.findall(r'\{\{(?:INTERPOLATE_|@)(?:js|py|md|txt|json|html):([^}]+)\}\}', text)
    files = {p.strip(): source_file(workspace, p.strip()).read_text() for p in refs}

    # Run resolvers in order
    text = env_resolver.resolve(text, env_name, workspace)
    text = file_resolver.resolve(text, workspace)
    text = js_resolver.resolve(text, workspace)
    text = py_resolver.resolve(text, workspace)
    namespace = node_namespace(workspace, env_name, workflow_key)
    text = uuid_resolver.resolve(text, namespace=namespace)

    # Validate no residuals
    validator.validate_no_absolute_paths(text)
    residuals = validator.check_residuals(text)
    if residuals:
        if strict:
            raise ValueError(
                f"Residual placeholders after hydration in '{workflow_key}':\n"
                + "\n".join(f"  {r}" for r in residuals)
            )
        else:
            print(f"WARNING: {len(residuals)} residual placeholder(s) in '{workflow_key}': {residuals}", file=sys.stderr)

    # Validate JSON parses
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Generated JSON is invalid for '{workflow_key}': {e}")

    out_dir = build_path(workspace, env_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{workflow_key}.generated.json"
    if out_file.is_symlink() or out_file.with_suffix('.meta.json').is_symlink():
        raise ValueError('Generated output paths must not be symlinks')
    atomic_write(out_file, json.dumps(data, indent=2), private=True)
    metadata = {'source': source, 'files': files, 'identity': identity(workspace, env_name),
                'nodeNamespace': namespace,
                'fingerprint': digest([source, files, data])}
    atomic_write(out_file.with_suffix('.meta.json'), json.dumps(metadata, indent=2), private=True)
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--env", required=True)
    parser.add_argument("--workflow-key", required=True, dest="workflow_key")
    parser.add_argument("--strict", action="store_true", help="Error (not warn) on residual placeholders")
    args = parser.parse_args()

    ws = workspace_root(args.workspace)
    from helpers.workspace import ensure_workspace
    ensure_workspace(ws)
    out = hydrate(args.env, args.workflow_key, ws, strict=args.strict)
    print(f"Hydrated: {out}")


if __name__ == "__main__":
    main()
