#!/usr/bin/env python3
"""Build current source and deploy to one environment; explicitly activate new-format projects."""
import argparse
import json
import os
import subprocess
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.workspace import workspace_root, workspace_path, build_path
from helpers.config import load_yaml, load_env, get_config_value, is_legacy_environment
from helpers.n8n_client import ensure_client, redact_for_debug
from helpers.validate import validate_workflow_json


_PUT_FIELDS = ("name", "nodes", "connections", "settings", "staticData")

# Triggers that can stand alone (and thus support the /activate endpoint).
# Sub-workflow triggers (executeWorkflowTrigger, errorTrigger) cannot be activated alone.
_ACTIVATABLE_TRIGGER_TYPES = (
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.cron",
    "n8n-nodes-base.formTrigger",
    "n8n-nodes-base.emailReadImap",
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.errorTrigger",  # Error Trigger workflows DO need activation
)


def _filter_for_put(data: dict) -> dict:
    """n8n's PUT /workflows/{id} accepts only certain fields; drop the rest."""
    return {k: data[k] for k in _PUT_FIELDS if k in data}


def _has_activatable_trigger(workflow: dict) -> bool:
    """A workflow with only ExecuteWorkflowTrigger cannot be activated."""
    for node in workflow.get("nodes", []):
        ntype = node.get("type", "")
        if ntype in _ACTIVATABLE_TRIGGER_TYPES:
            return True
        # Heuristic: any node whose type ends in 'Trigger' BUT isn't a sub-workflow trigger
        if ntype.endswith("Trigger") and ntype != "n8n-nodes-base.executeWorkflowTrigger":
            return True
    return False


def _resolve_workflow_id(env_name: str, workflow_key: str, workspace: Path) -> str:
    data = load_yaml(env_name, workspace)
    try:
        value = get_config_value(data, f"workflows.{workflow_key}.id")
    except KeyError:
        value = None
    workflow_id = str(value).strip() if value is not None else ""
    if not workflow_id or workflow_id == "placeholder" or workflow_id.startswith("your-"):
        raise SystemExit(
            f"No deployed workflow ID for key '{workflow_key}' in env '{env_name}'. "
            "Run bootstrap_env.py for this environment to mint its draft IDs before deployment."
        )
    return workflow_id


def _write_debug(env_name: str, workflow_key: str, payload: dict, response, stage: str) -> None:
    debug_dir = Path.home() / ".cache" / "n8n-evol-I" / "debug" / str(os.getpid())
    debug_dir.mkdir(parents=True, exist_ok=True)
    seq = len(list(debug_dir.glob(f"deploy-*.json"))) + 1
    out = debug_dir / f"deploy-{seq:03d}.json"
    blob = {
        "env": env_name,
        "workflow_key": workflow_key,
        "stage": stage,
        "payload": redact_for_debug(payload),
        "response": redact_for_debug(response if isinstance(response, (dict, list)) else str(response)),
    }
    out.write_text(json.dumps(blob, indent=2))
    out.chmod(0o600)
    print(f"  Debug artifact: {out}", file=sys.stderr)


def _payload_preserved(expected, actual):
    """Permit server-added defaults, but require every requested value to survive."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _payload_preserved(v, actual[k]) for k,v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(_payload_preserved(a,b) for a,b in zip(expected,actual))
    return expected == actual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", "--project", dest="workspace")
    parser.add_argument("--env", required=True)
    parser.add_argument("--workflow-key", required=True, dest="workflow_key")
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument("--activate", action="store_true", help="Explicitly publish/activate after deployment")
    parser.add_argument("--rehydrate", action="store_true", help="Compatibility flag; builds are always fresh")
    parser.add_argument("--preview", action="store_true", help="Build and inspect without remote mutation")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    ws = workspace_root(args.workspace)
    from helpers.workspace import ensure_workspace
    ensure_workspace(ws)
    from helpers.hydrate import hydrate
    from helpers.workspace import has_project_manifest, state_path
    from helpers.sync_state import operation_lock, load_baseline, save_baseline, semantic, atomic_write
    with operation_lock(ws, args.env):
        # An empty ID would GET the workflow collection and falsely pass preview.
        wf_id = _resolve_workflow_id(args.env, args.workflow_key, ws)
        template_path = workspace_path(ws, "templates", args.workflow_key + ".template.json")
        source = template_path.read_text(encoding="utf-8")
        valid, errors = validate_workflow_json(source, source="template", workspace=ws)
        if not valid:
            print("Template validation failed: " + "; ".join(errors), file=sys.stderr)
            raise SystemExit(1)
        generated = hydrate(args.env, args.workflow_key, ws, strict=True)
        payload = _filter_for_put(json.loads(generated.read_text()))
        valid, errors = validate_workflow_json(json.dumps(payload), source="generated", workspace=ws)
        if not valid:
            raise SystemExit("Generated payload invalid: " + "; ".join(errors))
        cfg = load_yaml(args.env, ws)
        client = ensure_client(args.env, ws)
        previous = client.get_workflow(wf_id)
        baseline = load_baseline(ws, args.env, args.workflow_key)
        if baseline and semantic(previous) != semantic(baseline["remote"]):
            raise SystemExit("Remote workflow changed since synchronization. Resync and review before deploying.")
        if not baseline and previous.get("nodes") and semantic(previous) != semantic(payload):
            raise SystemExit("Existing remote workflow has no baseline. Import/resync it before deploying.")
        activate = not args.no_activate and (args.activate or is_legacy_environment(ws, args.env) or cfg.get("activation") == "automatic")
        print(json.dumps({"environment": args.env, "target": client.base_url,
                          "workflowId": wf_id, "activate": activate, "preview": args.preview}))
        if previous.get("active") and not activate:
            raise SystemExit("Target is active; this API may publish updates. Deactivate first for draft-only changes, or explicitly pass --activate.")
        if args.preview:
            return
        snapshot = state_path(ws, args.env) / "before-deploy" / (args.workflow_key + '-' + str(time.time_ns()) + ".json")
        atomic_write(snapshot, json.dumps(previous, indent=2), private=True)
        # Recheck immediately before PUT. Public API lacks a portable compare-and-swap.
        latest = client.get_workflow(wf_id)
        if semantic(latest) != semantic(previous):
            raise SystemExit("Remote changed during deployment preflight; retry after resync")
        resp = client.put(f"workflows/{wf_id}", payload)
        actual = client.get_workflow(wf_id)
        if not _payload_preserved(payload, actual):
            atomic_write(state_path(ws, args.env) / 'unexpected-deploy.json', json.dumps(actual, indent=2), private=True)
            raise SystemExit('n8n returned a definition different from the requested payload; inspect unexpected-deploy.json before retrying')
        meta = json.loads(generated.with_suffix('.meta.json').read_text())
        save_baseline(ws, args.env, args.workflow_key, meta['source'], actual, meta['files'], namespace=meta.get('nodeNamespace'))
        if args.debug:
            atomic_write(state_path(ws, args.env) / 'last-deploy.json',
                         json.dumps(redact_for_debug({'payload': payload, 'response': resp}), indent=2), private=True)
        print(f"Deployed workflow '{args.workflow_key}' (id={wf_id}) on env '{args.env}'")
        if activate:
            try:
                client.post(f"workflows/{wf_id}/activate", {})
                print(f"Activated workflow '{args.workflow_key}'")
            except Exception as e:
                print(f"WARNING: deployed but activation failed: {e}", file=sys.stderr)
                sys.exit(2)


if __name__ == "__main__":
    main()
