#!/usr/bin/env python3
"""Walk deployment_order.yml tiers and deploy each workflow per tier."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from helpers.workspace import workspace_root, workspace_path, build_path, has_project_manifest
from helpers.config import load_yaml, is_legacy_environment


_EXTERNAL_TRIGGER_TYPES = frozenset({
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.cron",
    "n8n-nodes-base.formTrigger",
    "n8n-nodes-base.emailReadImap",
})


def _has_external_trigger(template: dict) -> bool:
    """True if the workflow has a Webhook / Schedule / Cron-style trigger.

    Sub-workflow triggers (executeWorkflowTrigger) and Error Trigger don't fire on their own,
    so they stay active in dev (parent workflows need them published to activate).
    """
    for node in template.get("nodes", []):
        if node.get("type") in _EXTERNAL_TRIGGER_TYPES:
            return True
    return False


def _load_order(workspace: Path) -> dict:
    order_file = workspace_path(workspace, "config") / "deployment_order.yml"
    if not order_file.exists():
        return {"tiers": {}}
    return yaml.safe_load(order_file.read_text()) or {"tiers": {}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--env", required=True)
    parser.add_argument("--activate", action="store_true", help="Publish each deployed workflow")
    parser.add_argument("--preview", action="store_true", help="Preflight all workflows without deployment")
    parser.add_argument("--keep-active", action="store_true", dest="keep_active")
    parser.add_argument("--continue-on-failure", action="store_true", dest="continue_on_failure",
                        help="Continue past PUT failures (exit=1). Activate-only failures (exit=2) "
                             "are warned-and-continued by default; pass --strict-activate to escalate.")
    parser.add_argument("--strict-activate", action="store_true", dest="strict_activate",
                        help="Treat 'deployed-but-not-activated' (deploy.py exit=2) as a hard tier-stop "
                             "failure. Without this flag, activate failures are warned and the rollout "
                             "continues — a workflow whose PUT succeeded is fine to leave inactive while "
                             "the operator follows up (e.g. activate sub-workflows manually first).")
    args = parser.parse_args()

    ws = workspace_root(args.workspace)
    from helpers.workspace import ensure_workspace
    ensure_workspace(ws)
    order = _load_order(ws)
    tiers = order.get("tiers") or {}
    helpers = Path(__file__).parent

    failures: list[tuple[str, int]] = []
    activate_warnings: list[str] = []
    registered = load_yaml(args.env, ws).get('workflows') or {}
    priority = [key for tier in sorted(tiers, key=lambda x: [int(v) if v.isdigit() else v for v in re.split(r'(\d+)', x)]) for key in (tiers[tier] or []) if key in registered]
    definitions = {}
    for key in priority:
        definitions[key] = json.loads(workspace_path(ws, 'templates', key + '.template.json').read_text())
    dependencies = {key: set(re.findall(r'\{\{(?:INTERPOLATE_|@)env:workflows\.([\w/-]+)\.id\}\}', json.dumps(value))) - {key} for key,value in definitions.items()}
    ordered, visiting, visited = [], set(), set()
    def visit(key):
        if key in visited: return
        if key in visiting: raise SystemExit('Workflow dependency cycle: ' + key)
        visiting.add(key)
        for dep in sorted(dependencies[key]):
            if dep not in registered:
                raise SystemExit(f"Dependency '{dep}' of '{key}' is not registered in environment '{args.env}'")
            if dep not in definitions:
                raise SystemExit(f"Dependency '{dep}' of '{key}' is absent from deployment_order.yml")
            visit(dep)
        visiting.remove(key); visited.add(key); ordered.append(key)
    for key in priority: visit(key)
    def deployment_command(key):
        command = [sys.executable, str(helpers / 'deploy.py'), '--workspace', str(ws),
                   '--env', args.env, '--workflow-key', key]
        if args.activate:
            command.append('--activate')
        elif args.env == 'dev' and not args.keep_active and _has_external_trigger(definitions[key]):
            command.append('--no-activate')
        return command
    # Entire-plan validation before the first remote mutation.
    for key in ordered:
        command = deployment_command(key) + ['--preview']
        result = subprocess.run(command)
        if result.returncode: raise SystemExit(result.returncode)
    if args.preview: return
    for key in ordered:
            cmd = deployment_command(key)
            r = subprocess.run(cmd)
            if r.returncode == 2 and not args.strict_activate:
                # PUT succeeded; only activate failed. Warn and continue —
                # downstream tiers may not need this workflow to be active
                # (e.g. it's a sub-workflow whose parent will trigger a retry
                # at activate time once dependencies are publish/active).
                activate_warnings.append(key)
                print(f"WARN: '{key}' deployed but not activated (continuing; pass "
                      f"--strict-activate to fail-fast).", file=sys.stderr)
                continue
            if r.returncode != 0:
                failures.append((key, r.returncode))
                if not args.continue_on_failure:
                    print(f"FAIL: deploy '{key}' exit={r.returncode}", file=sys.stderr)
                    sys.exit(r.returncode)

    # Auto-deactivate after dev deploys unless --keep-active.
    # Only deactivate workflows with external triggers (webhook/schedule/cron) — those fire
    # on their own. Sub-workflows and error handlers must stay active so parent workflows
    # remain valid; deactivating them would invalidate any source workflow that references them.
    if args.env == "dev" and not args.keep_active and not args.activate and is_legacy_environment(ws, args.env):
        all_keys = ordered
        template_dir = workspace_path(ws, "templates")
        for key in all_keys:
            template_path = template_dir / f"{key}.template.json"
            if not template_path.exists():
                continue
            try:
                template = json.loads(template_path.read_text())
            except json.JSONDecodeError:
                continue
            if not _has_external_trigger(template):
                continue
            cmd = [sys.executable, str(helpers / "deactivate.py"),
                   "--workspace", str(ws), "--env", args.env, "--workflow-key", key]
            subprocess.run(cmd)

    if activate_warnings:
        print(f"deploy_all: {len(activate_warnings)} workflow(s) deployed but not activated: "
              f"{activate_warnings}", file=sys.stderr)
    if failures:
        print(f"deploy_all complete with {len(failures)} failure(s): {failures}", file=sys.stderr)
        sys.exit(1)
    print("deploy_all complete.")


if __name__ == "__main__":
    main()
