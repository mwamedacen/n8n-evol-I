"""Restore source references using a deployed baseline, without discarding UI edits."""
import copy
import json
import re
from pathlib import Path

from helpers.config import flatten_config, load_yaml
from helpers.placeholder import js_resolver, py_resolver
from helpers.placeholder.paths import source_file
from helpers.sync_state import semantic

TOKEN = re.compile(r'\{\{(?:INTERPOLATE_|@)(\w+):([^}]+)\}\}')


class SyncConflict(ValueError):
    pass


def restore(raw, baseline, ws, env):
    """Return the remote definition expressed as reusable source and extracted files.

    Unknown composite edits fail with a conflict, retaining raw data in the caller's
    snapshot. This deliberately prefers an actionable conflict to lossy guessing.
    """
    cfg = flatten_config(load_yaml(env, ws))
    files = dict(baseline.get('files', {}))
    extracted = {}
    old_source = baseline['source']
    old_remote = semantic(baseline['remote'])
    remote = semantic(raw)

    def record(path, content):
        source_file(ws, path)  # containment check, even when remote supplies markers
        if path not in files:
            raise SyncConflict(f'Unrecognized remote source marker: {path}')
        if path in extracted and extracted[path] != content:
            raise SyncConflict(f'Conflicting remote edits to shared source file: {path}')
        extracted[path] = content

    def string(value, original, deployed):
        if value == deployed:
            return original
        tokens = list(TOKEN.finditer(original)) if isinstance(original, str) else []
        if not tokens:
            return value
        # Code marker content is real edited source, not merely a placeholder hint.
        for kind, pattern in [('js', js_resolver._MARKER_PATTERN), ('py', py_resolver._MARKER_PATTERN)]:
            def collapse(match):
                path = match.group(2).strip()
                previous = files.get(path, '')
                body = match.group(3)
                if kind == 'js':
                    body = body.removeprefix('\n').removesuffix('\n')
                content = body + ('\n' if previous.endswith('\n') else '')
                record(path, content)
                token = next((m.group(0) for m in tokens if m.group(1) == kind and m.group(2).strip() == path), None)
                if not token:
                    raise SyncConflict(f'Remote code marker not present in source: {path}')
                return token
            value = pattern.sub(collapse, value)
        for token in tokens:
            whole, kind, key = token.group(0), token.group(1), token.group(2).strip()
            if whole in value:
                continue
            if kind in ('js', 'py'):
                raise SyncConflict(f'Remote edit removed source markers for {key}')
            if kind in ('md', 'txt', 'json', 'html'):
                if original == whole:
                    if kind == 'json':
                        json.loads(value)
                    record(key, value)
                    return whole
                prior = files.get(key)
                if prior and value.count(prior) == 1:
                    value = value.replace(prior, whole, 1)
                else:
                    raise SyncConflict(f'Review composite asset edit for {key}; extraction is ambiguous')
            elif kind == 'env':
                bound = cfg.get(key)
                encoded = json.dumps(bound) if isinstance(bound, (list, dict)) else str(bound)
                if encoded and value.count(encoded) == 1:
                    value = value.replace(encoded, whole, 1)
                else:
                    raise SyncConflict(f'Remote edit changed environment binding {key}; bind explicitly')
            elif kind == 'uuid':
                raise SyncConflict(f'Remote edit changed node identity {key}')
        return value

    def walk(value, original, deployed):
        if isinstance(value, dict):
            original = original if isinstance(original, dict) else {}
            deployed = deployed if isinstance(deployed, dict) else {}
            return {k: walk(v, original.get(k), deployed.get(k)) for k, v in value.items()}
        if isinstance(value, list):
            original = original if isinstance(original, list) else []
            deployed = deployed if isinstance(deployed, list) else []
            # Nodes survive remote rename/reorder through their stable deployed ID.
            if value and all(isinstance(v, dict) and 'id' in v for v in value):
                by_id = {v.get('id'): i for i, v in enumerate(deployed) if isinstance(v, dict)}
                return [walk(v, original[by_id[v['id']]] if v['id'] in by_id and by_id[v['id']] < len(original) else None,
                             deployed[by_id[v['id']]] if v['id'] in by_id else None) for v in value]
            return [walk(v, original[i] if i < len(original) else None,
                         deployed[i] if i < len(deployed) else None) for i, v in enumerate(value)]
        if isinstance(value, str) and isinstance(original, str):
            return string(value, original, deployed)
        if isinstance(value, str):
            # New remote fields: reverse only exact known remote identity values.
            candidates = [k for k, v in cfg.items() if k.startswith(('workflows.', 'credentials.')) and v == value]
            if len(candidates) == 1:
                return '{{@env:' + candidates[0] + '}}'
            if len(candidates) > 1:
                raise SyncConflict('Ambiguous environment reference in a new remote field')
        return copy.deepcopy(value)

    restored = walk(remote, old_source, old_remote)
    def portable_ref(value, namespace):
        if not value or str(value).startswith(('{{@env:' + namespace, '{{INTERPOLATE_env:' + namespace, '=')):
            return value
        candidates = [k for k, v in cfg.items() if k.startswith(namespace) and v == value]
        if len(candidates) != 1:
            raise SyncConflict(f'Register the remote {namespace.rstrip(".")} reference before resynchronizing')
        return '{{@env:' + candidates[0] + '}}'
    for node in restored.get('nodes', []):
        for credential in (node.get('credentials') or {}).values():
            if isinstance(credential, dict):
                credential['id'] = portable_ref(credential.get('id'), 'credentials.')
        if node.get('type') == 'n8n-nodes-base.executeWorkflow':
            params = node.get('parameters') or {}
            ref = params.get('workflowId')
            if isinstance(ref, dict):
                ref['value'] = portable_ref(ref.get('value'), 'workflows.')
            elif ref:
                params['workflowId'] = portable_ref(ref, 'workflows.')
    settings = restored.get('settings') or {}
    if settings.get('errorWorkflow'):
        settings['errorWorkflow'] = portable_ref(settings['errorWorkflow'], 'workflows.')
    files.update(extracted)
    return restored, files
