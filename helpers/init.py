#!/usr/bin/env python3
"""Create or adopt a project without replacing existing files.

New projects default to the current directory. --project and its legacy alias
--workspace select another directory. Existing legacy workspaces are discovered
from subdirectories and remain usable until explicitly migrated.
"""
import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from helpers.workspace import (
    DEFAULT_PATHS, MANIFEST_NAME, assert_not_in_harness, discover_project,
    has_project_manifest, load_project_manifest, validate_environment_name,
)

_AGENTS_MD = """\
# n8n project

Read `n8n-project.yml` for source paths and environment workspaces. Follow the
user's preferences first, existing project conventions second, bundled defaults
last. Preserve existing files, instructions, credentials and data.

Route n8n tasks through the installed harness's `SKILL.md`; invoke helpers from
that installation with `--workspace <this-project>` and an explicit `--env`.
The installation is read-only. Run `doctor.py` before deployment.

Reusable templates, code, prompts and assets belong to project source paths.
Each environment has its own n8n deployment, credentials, workflow IDs, build
and synchronization state. Never copy deployment bindings between environments.
Legacy `n8n-config/<env>.yml` files remain usable until explicitly migrated.

Read `N8N-WORKSPACE-MEMORY.md` at the start of each session. Update that journal
with short dated entries for durable project knowledge; append without erasing
history. Check local and remote changes before deploying or resynchronizing.
"""

_WORKSPACE_MEMORY_MD = """\
# N8N-WORKSPACE-MEMORY

Append dated, durable project knowledge. Do not store secret values.

## Workflows

## Environments

## Investigations

## Workspace notes
"""

_GITIGNORE = """\
# n8n generated/private state
n8n-build/
.n8n-state/
.env*
!.env.example
!**/.env.example
environments/*/bindings.json
environments/*/state/
environments/*/build/
"""
def _write_if_absent(path: Path, content: str, skip_msg: str = "") -> None:
    if path.exists() or path.is_symlink():
        print(f"  {skip_msg or f'Preserved {path}'}")
        return
    assert_not_in_harness(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also preserves a file created concurrently after preflight.
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        print(f"  Preserved {path}")
        return
    print(f"  Wrote {path}")


def _legacy_environments(config: Path) -> dict:
    environments = {}
    for path in sorted(config.glob("*.yml")):
        if path.stem in ("common", "deployment_order"):
            continue
        validate_environment_name(path.stem)
        environments[path.stem] = {"path": f"environments/{path.stem}", "legacy": True}
    return environments


def _scaffold(ws: Path, force: bool = False, *, adopt: bool = False, paths: dict | None = None) -> None:
    """Add absent scaffolding only; --force is retained as a non-destructive alias."""
    ws = Path(ws).expanduser().resolve()
    assert_not_in_harness(ws)
    if ws.exists() and not ws.is_dir():
        raise ValueError(f"Project path is not a directory: {ws}")
    if force:
        print("--force is deprecated: setup is additive and never deletes existing files.", file=sys.stderr)

    existing_manifest = has_project_manifest(ws)
    if existing_manifest:
        manifest = load_project_manifest(ws)
        if paths and any(manifest.get("paths", {}).get(key, DEFAULT_PATHS[key]) != value for key, value in paths.items()):
            raise ValueError(f"Existing {MANIFEST_NAME} preserved; edit its paths explicitly before rerunning setup")
    else:
        configured = dict(DEFAULT_PATHS)
        for key, value in (paths or {}).items():
            if key not in DEFAULT_PATHS:
                raise ValueError(f"Unknown project path kind: {key}")
            if not value or Path(value).is_absolute() or "\\" in value:
                raise ValueError(f"paths.{key} must be relative to the project manifest")
            configured[key] = value
        # Carry forward the layout extension supported before project manifests.
        # A generated bundled default must not outrank this existing convention.
        common_file = ws / configured["config"] / "common.yml"
        if common_file.is_file():
            common = yaml.safe_load(common_file.read_text()) or {}
            legacy_layout = common.get("workspace_layout", {}) if isinstance(common, dict) else {}
            for old_key, kind in (("n8n_functions_tests_dir", "function_tests"),
                                  ("cloud_functions_tests_dir", "cloud_tests")):
                value = legacy_layout.get(old_key) if isinstance(legacy_layout, dict) else None
                if value is not None and kind not in (paths or {}):
                    if not isinstance(value, str) or not value:
                        raise ValueError(f"Legacy workspace_layout.{old_key} must be a path")
                    configured[kind] = os.path.relpath((ws / value).resolve(), ws)
        manifest = {
            "version": 1,
            "projectId": str(uuid.uuid4()),
            "paths": configured,
            "environments": _legacy_environments(ws / configured["config"]),
        }

    configured = {**DEFAULT_PATHS, **manifest.get("paths", {})}
    source_dirs = {kind: (ws / value).resolve() for kind, value in configured.items()}
    dirs = [*source_dirs.values(), ws / "environments"]
    dirs.extend(source_dirs["functions"] / language for language in ("js", "py"))
    dirs.extend(source_dirs["prompts"] / name for name in ("prompts", "datasets", "evals"))
    dirs.extend(source_dirs["assets"] / name for name in ("email-templates", "images", "misc"))
    dirs.append(source_dirs["cloud_functions"] / "functions")
    # Inspect every intended directory before making any changes.
    for directory in dirs:
        assert_not_in_harness(directory)
        if directory.exists() and not directory.is_dir():
            raise ValueError(f"Preserved existing file; cannot create directory at {directory}. Configure another path.")
        for ancestor in directory.parents:
            if ancestor.exists():
                if not ancestor.is_dir():
                    raise ValueError(f"Preserved existing file; parent is not a directory: {ancestor}")
                break
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)

    _write_if_absent(ws / MANIFEST_NAME, yaml.safe_dump(manifest, sort_keys=False))
    load_project_manifest(ws)  # reject invalid mappings before subsequent helper use
    existing_instructions = (ws / "AGENTS.md").exists() and (
        (ws / "AGENTS.md").read_bytes() != _AGENTS_MD.encode("utf-8")
    )
    _write_if_absent(ws / "AGENTS.md", _AGENTS_MD)
    if existing_instructions:
        _write_if_absent(ws / "N8N-AGENTS.md", _AGENTS_MD)
    _write_if_absent(ws / "N8N-WORKSPACE-MEMORY.md", _WORKSPACE_MEMORY_MD)
    _write_if_absent(ws / ".gitignore", _GITIGNORE)
    _write_if_absent(source_dirs["config"] / ".gitignore", ".env*\n!.env.example\n")
    _write_if_absent(ws / "environments" / ".gitignore", "*/.env*\n!*/.env.example\n*/bindings.json\n*/state/\n*/build/\n")
    _write_if_absent(source_dirs["config"] / ".env.example", "# Secret variable names only; configure values per environment.\n")

    # Preserve existing testing conventions. New default projects keep the
    # historical convenience imports; adoption never imposes a test runner.
    has_runner = any((ws / name).exists() for name in ("pyproject.toml", "pytest.ini", "package.json", "Cargo.toml", "go.mod"))
    if not adopt and not has_runner:
        for tests_kind, source_kind, suffix in (
            ("function_tests", "functions", "py"),
            ("cloud_tests", "cloud_functions", ""),
        ):
            target = source_dirs[source_kind] / suffix
            relative = os.path.relpath(target, source_dirs[tests_kind])
            _write_if_absent(source_dirs[tests_kind] / "conftest.py", (
                "import sys\nfrom pathlib import Path\n"
                f"sys.path.insert(0, str((Path(__file__).parent / {relative!r}).resolve()))\n"
            ))

    # Legacy nested workspaces retain parent aliases; other projects get local
    # aliases. Every pre-existing instruction file stays byte-for-byte intact.
    if ws.name == "n8n-evol-I-workspace" and ws.parent == Path.cwd().resolve():
        alias_root, instruction = ws.parent, "n8n-evol-I-workspace/AGENTS.md"
    else:
        alias_root, instruction = ws, "AGENTS.md"
    _write_if_absent(alias_root / "CLAUDE.md", f"@{instruction}\n")
    _write_if_absent(alias_root / ".github" / "copilot-instructions.md", f"Read `{instruction}` for n8n project guidance.\n")
    print(f"Project ready at {ws}; existing files preserved.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", "--workspace", dest="project", help="Project directory (default: discovered project or current directory)")
    parser.add_argument("--adopt", action="store_true", help="Adopt existing sources without imposing a test runner")
    parser.add_argument("--path", action="append", default=[], metavar="KIND=RELATIVE_PATH", help="Source path mapping for a new manifest")
    parser.add_argument("--force", action="store_true", help="Deprecated compatibility flag; existing files are always preserved")
    args = parser.parse_args()
    paths = {}
    for assignment in args.path:
        key, separator, value = assignment.partition("=")
        if not separator or key not in DEFAULT_PATHS or not value:
            parser.error("--path requires a known KIND=RELATIVE_PATH")
        paths[key] = value
    ws = Path(args.project).expanduser().resolve() if args.project else discover_project() or Path.cwd().resolve()
    try:
        _scaffold(ws, args.force, adopt=args.adopt, paths=paths)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
