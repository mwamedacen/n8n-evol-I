"""Private deployment baselines and recoverable local file updates."""
import contextlib
import copy
import fcntl
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from helpers.config import load_yaml, target_identity
from helpers.workspace import state_path, workspace_path, assert_not_in_harness, load_project_manifest, validate_workflow_key


def protect_private_directory(directory: Path) -> None:
    """Preserve existing ignore rules while protecting private generated files."""
    ignore = directory / '.gitignore'
    if ignore.is_symlink():
        raise ValueError('Private .gitignore must not be a symlink')
    previous = ignore.read_text() if ignore.exists() else ''
    # A final wildcard overrides earlier negation rules without discarding them.
    if previous.splitlines() and previous.splitlines()[-1] == '*':
        return
    content = previous + ('\n' if previous and not previous.endswith('\n') else '') + '*\n'
    fd, temporary = tempfile.mkstemp(prefix='.gitignore.', dir=directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, ignore)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write(path: Path, text: str, private: bool = False) -> None:
    assert_not_in_harness(path)
    if private and (path.is_symlink() or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError('Private runtime files must not traverse symlinks')
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o600 if private else (path.stat().st_mode & 0o777 if path.exists() else 0o644)
    if private:
        protect_private_directory(path.parent)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def identity(ws, env):
    cfg = load_yaml(env, ws)
    target = target_identity(cfg)
    return {'project': load_project_manifest(ws).get('projectId', str(ws.resolve())), 'environment': env,
            'target': target['instanceName'], 'projectId': target['projectId']}


def baseline_path(ws, env, key):
    validate_workflow_key(key)
    root = state_path(ws, env)
    path = root / 'baselines' / (key + '.json')
    if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Synchronization baseline escapes its environment state')
    return path


def load_baseline(ws, env, key):
    p = baseline_path(ws, env, key)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    previous = dict(data['identity'])
    current = identity(ws, env)
    previous['target'] = target_identity({'n8n': {'instanceName': previous['target']}})['instanceName']
    # Additive adoption may assign a stable project ID to an existing legacy
    # checkout. A baseline recorded at exactly this root remains attributable.
    if previous.get('project') == str(ws.resolve()):
        previous['project'] = current['project']
    if previous != current:
        raise ValueError('Deployment binding changed; explicitly rebind before using stored state')
    expected_id = str(load_yaml(env, ws).get('workflows', {}).get(key, {}).get('id', ''))
    recorded_id = str(data.get('workflowId', data.get('remote', {}).get('id', '')))
    if not recorded_id or recorded_id != expected_id:
        raise ValueError('Workflow binding changed; establish a reviewed baseline for this remote workflow')
    return data


def node_namespace(ws, env, key):
    """Retain deployed node identities through equivalent URLs and additive adoption."""
    baseline = load_baseline(ws, env, key)
    if baseline:
        # Older records used their literal identity as the UUID namespace. Carry
        # it forward unchanged while canonicalizing target comparisons separately.
        return baseline.get('nodeNamespace') or json.dumps(baseline['identity'], sort_keys=True) + ':' + key
    return json.dumps(identity(ws, env), sort_keys=True) + ':' + key


def save_baseline(ws, env, key, source, remote, files, namespace=None):
    data = {'identity': identity(ws, env),
            'nodeNamespace': namespace or node_namespace(ws, env, key),
            'workflowId': str(load_yaml(env, ws).get('workflows', {}).get(key, {}).get('id', '')),
            'source': source, 'remote': remote,
            'files': files, 'recordedAt': time.time()}
    atomic_write(baseline_path(ws, env, key), json.dumps(data, indent=2), private=True)


def semantic(raw):
    """Only editable definition fields; retain node IDs and all node parameters."""
    return {k: copy.deepcopy(raw[k]) for k in ('name', 'nodes', 'connections', 'settings') if k in raw}


@contextlib.contextmanager
def operation_lock(ws, env):
    # Project-level lock also protects shared source against two environment resyncs.
    p = Path(ws) / '.n8n-state' / '.operations.lock'
    if (Path(ws) / '.n8n-state').is_symlink() or p.is_symlink():
        raise ValueError('Project operation state/lock must not be a symlink')
    if not p.resolve().is_relative_to(Path(ws).resolve()):
        raise ValueError('Project operation lock escapes project')
    assert_not_in_harness(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    protect_private_directory(p.parent)
    with p.open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another project operation is running; retry after it completes')
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def apply_files(ws, env, changes):
    """Journal originals first; roll back a partial local apply on an exception."""
    originals = {str(p): p.read_text() if p.exists() else None for p in changes}
    receipt = state_path(ws, env) / 'operations' / (str(time.time_ns()) + '.json')
    journal = {'status': 'prepared', 'originals': originals,
               'proposed': {str(p): text for p, text in changes.items()}}
    atomic_write(receipt, json.dumps(journal, indent=2), private=True)
    written = []
    try:
        for p, text in changes.items():
            atomic_write(p, text)
            written.append(p)
    except BaseException:
        for p in reversed(written):
            before = originals[str(p)]
            if before is None:
                p.unlink(missing_ok=True)
            else:
                atomic_write(p, before)
        journal['status'] = 'rolled-back'
        atomic_write(receipt, json.dumps(journal, indent=2), private=True)
        raise
    journal['status'] = 'applied'
    atomic_write(receipt, json.dumps(journal, indent=2), private=True)
    return receipt
