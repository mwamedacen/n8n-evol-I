#!/usr/bin/env python3
"""Scaffold a brand-new workflow: write template + register IDs in env YAML(s) + mint placeholder n8n workflow."""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from helpers.workspace import workspace_root, harness_root, workspace_path, validate_environment_name, validate_workflow_key
from helpers.config import load_yaml, save_yaml, environment_names, atomic_write, configuration_snapshot
from helpers.n8n_client import ensure_client


def _seed_minimal_template(workflow_key: str, name: str) -> str:
    seed = (harness_root() / "primitives" / "workflows" / "_minimal.template.json").read_text()
    seed = seed.replace("__NAME__", json.dumps(name)[1:-1])
    safe_path = re.sub(r"[^a-zA-Z0-9_-]+", "-", workflow_key).strip("-").lower() or "workflow"
    seed = seed.replace("__PATH__", safe_path)
    return seed


def _list_envs(workspace: Path) -> list[str]:
    return environment_names(workspace)


def _ensure_workflow_row(workspace: Path, env_name: str, key: str, name: str, mint: bool) -> None:
    data = load_yaml(env_name, workspace)
    workflows = data.setdefault("workflows", {}) or {}
    data["workflows"] = workflows  # ensure not None
    if key not in workflows or not isinstance(workflows[key], dict):
        workflows[key] = {"id": "", "name": name}

    wf = workflows[key]
    needs_mint = mint and (not wf.get("id") or str(wf.get("id", "")).startswith("your-") or wf.get("id") == "placeholder")

    if needs_mint:
        client = ensure_client(env_name, workspace)
        full_name = f"{data.get('displayName', '')} {name}{data.get('workflowNamePostfix', '')}".strip()
        resp = client.create_workflow({"name": full_name, "nodes": [], "connections": {}, "settings": {}},
                                      project_id=data.get("n8n", {}).get("projectId"))
        wf["id"] = resp.get("id", "")
        print(f"  Minted '{full_name}' → id={wf['id']} on env '{env_name}'")
    save_yaml(env_name, workspace, data)


def _add_to_deployment_order(workspace: Path, key: str, tier: str) -> None:
    order_file = workspace_path(workspace, "config", "deployment_order.yml")
    data: dict = {}
    if order_file.exists():
        data = yaml.safe_load(order_file.read_text()) or {}
    tiers = data.setdefault("tiers", {})
    members = tiers.setdefault(tier, []) or []
    if key not in members:
        members.append(key)
    tiers[tier] = members
    atomic_write(order_file, yaml.safe_dump(data, sort_keys=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", "--project", dest="workspace", default=None)
    parser.add_argument("--key", required=True, help="Workflow key (e.g. report_v2)")
    parser.add_argument("--name", required=True, help="Display name (e.g. 'Daily Report')")
    parser.add_argument("--register-in", default=None, dest="register_in",
                        help="Comma-separated env names; required when more than one environment exists")
    parser.add_argument("--with-error-handler", default=None, dest="with_error_handler",
                        help="Workflow key of an existing error handler to wire as settings.errorWorkflow")
    parser.add_argument("--tier", default="Tier 1",
                        help="Tier name in deployment_order.yml. Defaults to 'Tier 1' so deploy_all.py "
                             "picks the workflow up out of the box. Pass an explicit tier name "
                             "('Tier 0a: leaves' for primitives, 'Tier 2' for downstream callers, etc.) "
                             "or 'none' to skip deployment_order registration entirely.")
    parser.add_argument("--no-mint", action="store_true", help="Skip n8n calls; with no environments, scaffold source only")
    parser.add_argument("--no-template", action="store_true", help="Skip the template-write step")
    args = parser.parse_args()

    ws = workspace_root(args.workspace)

    # Resolve and validate every destination before touching files or n8n.
    explicit_environments = args.register_in is not None
    envs = list(dict.fromkeys(e.strip() for e in args.register_in.split(",") if e.strip())) if explicit_environments else _list_envs(ws)
    source_only = not envs and args.no_mint and not explicit_environments
    if not source_only and (not envs or (not explicit_environments and len(envs) != 1)):
        parser.error("Choose --register-in <env>; creation requires exactly one default environment")
    if source_only and args.with_error_handler:
        parser.error("--with-error-handler requires a configured environment")
    try:
        validate_workflow_key(args.key)
    except ValueError as error:
        parser.error(str(error))
    # Check the complete filename before any mutation; a dangling symlink also
    # must not redirect scaffolding outside the configured template directory.
    template_path = workspace_path(ws, "templates", f"{args.key}.template.json")
    observed_config = configuration_snapshot(ws, envs)
    for env in envs:
        validate_environment_name(env)
        data = load_yaml(env, ws)
        if not args.no_mint:
            client = ensure_client(env, ws)
            if data.get("n8n", {}).get("projectId"):
                client.require_project(data["n8n"]["projectId"])

    from helpers.sync_state import operation_lock
    with operation_lock(ws, envs[0] if envs else None):
        if configuration_snapshot(ws, envs) != observed_config:
            raise SystemExit("Environment configuration changed during creation; review it and retry")
        # Step 1: write template
        template_dir = workspace_path(ws, "templates")
        template_dir.mkdir(parents=True, exist_ok=True)
        template_path = workspace_path(ws, "templates", f"{args.key}.template.json")
        if not args.no_template:
            if template_path.exists():
                print(f"  Template exists at {template_path}, leaving in place")
            else:
                atomic_write(template_path, _seed_minimal_template(args.key, args.name))
                print(f"  Wrote {template_path}")

        # Step 2: register in env YAML(s) and (optionally) mint
        if source_only:
            print("  Created offline source; configure an environment and rerun with --register-in to register it")
        for env in envs:
            try:
                _ensure_workflow_row(ws, env, args.key, args.name, mint=not args.no_mint)
            except Exception as e:
                print(f"  ERROR registering in env '{env}': {e}", file=sys.stderr)
                sys.exit(1)

        # Step 3: deployment order. `--tier none` opts out (e.g. workflows you
        # deploy manually outside deploy_all.py); any other value registers.
        if args.tier and args.tier.lower() != "none":
            _add_to_deployment_order(ws, args.key, args.tier)
            print(f"  Added '{args.key}' to deployment_order.yml under '{args.tier}'")

        # Step 4: error-handler wiring
        if args.with_error_handler:
            import subprocess
            cmd = [
                sys.executable,
                str(Path(__file__).parent / "register_error_handler.py"),
                "--workspace", str(ws),
                "--register-in", ",".join(envs),
                "--workflow-key", args.key,
                "--handler-key", args.with_error_handler,
            ]
            subprocess.run(cmd, check=True)

        print(f"create-workflow complete for '{args.key}'.")



if __name__ == "__main__":
    main()
