"""Resolve source references without allowing implicit path escapes."""
from pathlib import Path
from helpers.workspace import workspace_path, load_project_manifest


def source_file(workspace: Path, relative: str) -> Path:
    if Path(relative).is_absolute():
        raise ValueError('Absolute paths in placeholders are forbidden')
    path = (workspace / relative).resolve()
    root = workspace.resolve()
    # Reusable files must never hydrate another environment's configuration,
    # credentials, builds, or runtime state into a workflow.
    private = [workspace_path(workspace, 'config'), root / '.n8n-state', root / 'n8n-build', root / 'environments', root / '.git']
    for env, entry in load_project_manifest(workspace).get('environments', {}).items():
        value = entry.get('path', f'environments/{env}') if isinstance(entry, dict) else entry
        private.append((root / value).resolve())
    if any(path.is_relative_to(p.resolve()) for p in private) or any(part.startswith('.env') for part in Path(relative).parts) or path.name.startswith('.env'):
        raise ValueError(f'Placeholder cannot reference private environment/configuration state: {relative}')
    roots = [workspace.resolve()] + [workspace_path(workspace, kind).resolve() for kind in
             ('functions', 'prompts', 'assets', 'templates')]
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError(f'Placeholder escapes project and explicitly mapped source paths: {relative}')
    return path
