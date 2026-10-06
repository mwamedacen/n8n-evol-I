#!/usr/bin/env python3
"""Review remote changes and apply a conflict-checked resynchronization."""
import argparse
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from helpers.workspace import workspace_root, workspace_path, state_path
from helpers.config import load_yaml, get_config_value
from helpers.n8n_client import ensure_client
from helpers.dehydrate import dehydrate_data
from helpers.roundtrip import restore, SyncConflict
from helpers.placeholder.paths import source_file
from helpers.sync_state import (atomic_write, load_baseline, save_baseline, semantic,
                                operation_lock, apply_files)


def plan_resync(ws, env, key):
    cfg = load_yaml(env, ws)
    remote_id = str(get_config_value(cfg, f'workflows.{key}.id'))
    raw = ensure_client(env, ws).get_workflow(remote_id)
    out = workspace_path(ws, 'templates', key + '.template.json')
    baseline = load_baseline(ws, env, key)
    snapshot = state_path(ws, env) / 'incoming' / (key + '.json')
    atomic_write(snapshot, json.dumps(raw, indent=2), private=True)
    if baseline:
        proposed, files = restore(raw, baseline, ws, env)
    else:
        proposed = json.loads(dehydrate_data(raw, env, ws, key))
        references = re.findall(r'\{\{(?:INTERPOLATE_|@)(?:js|py|md|txt|json|html):([^}]+)\}\}', json.dumps(proposed))
        files = {path.strip(): source_file(ws, path.strip()).read_text() for path in references}
        for node in proposed.get('nodes', []):
            for credential in (node.get('credentials') or {}).values():
                ref = str(credential.get('id', '')) if isinstance(credential, dict) else ''
                if ref and not ref.startswith(('{{@env:credentials.', '{{INTERPOLATE_env:credentials.')):
                    raise SyncConflict(f'{key}: link credential {credential.get("name", "(unnamed)")} in this environment before importing; raw snapshot: {snapshot}')
            if node.get('type') == 'n8n-nodes-base.executeWorkflow':
                ref = (node.get('parameters') or {}).get('workflowId')
                ref = ref.get('value') if isinstance(ref, dict) else ref
                if ref and not str(ref).startswith(('{{@env:workflows.', '{{INTERPOLATE_env:workflows.', '=')):
                    raise SyncConflict(f'{key}: register the referenced subworkflow before importing; raw snapshot: {snapshot}')
        error_ref = (proposed.get('settings') or {}).get('errorWorkflow')
        if error_ref and not str(error_ref).startswith(('{{@env:workflows.', '{{INTERPOLATE_env:workflows.')):
            raise SyncConflict(f'{key}: register the referenced error workflow before importing; raw snapshot: {snapshot}')
    current = json.loads(out.read_text()) if out.exists() else None
    before = baseline['source'] if baseline else None
    changes = {}
    if current != proposed:
        if current is not None and (before is None or (current != before and proposed != before)):
            raise SyncConflict(f'{key}: local and remote changes conflict (or no baseline). Remote snapshot: {snapshot}')
        if current == before or current is None:
            changes[out] = json.dumps(proposed, indent=2) + '\n'
    for path, content in files.items():
        dest = source_file(ws, path)
        current_file = dest.read_text() if dest.exists() else None
        old_file = baseline.get('files', {}).get(path) if baseline else None
        if current_file != content:
            if current_file != old_file and content != old_file:
                raise SyncConflict(f'{key}: both sides edited {path}; snapshot: {snapshot}')
            if current_file == old_file:
                changes[dest] = content
    return {'key': key, 'source': proposed, 'remote': raw, 'files': files, 'changes': changes}


def resync_many(ws, env, keys, preview=False):
    with operation_lock(ws, env):
        # Fetch/plan everything before modifying any shared source.
        plans = [plan_resync(ws, env, key) for key in keys]
        changes = {}
        for plan in plans:
            for path, text in plan['changes'].items():
                if path in changes and changes[path] != text:
                    raise SyncConflict(f'Workflows disagree on shared source {path}')
                changes[path] = text
        print(json.dumps({'environment': env, 'preview': preview,
                          'files': [str(p) for p in changes]}, indent=2))
        if preview:
            return
        if changes:
            apply_files(ws, env, changes)
        for plan in plans:
            save_baseline(ws, env, plan['key'], plan['source'], plan['remote'], plan['files'])
        print(f'Resynced {len(plans)} workflow(s) from {env}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', '--project', dest='workspace')
    p.add_argument('--env', required=True)
    p.add_argument('--workflow-key', required=True)
    p.add_argument('--preview', action='store_true')
    args = p.parse_args()
    try:
        resync_many(workspace_root(args.workspace), args.env, [args.workflow_key], args.preview)
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(f'Resync stopped: {exc}')


if __name__ == '__main__':
    main()
