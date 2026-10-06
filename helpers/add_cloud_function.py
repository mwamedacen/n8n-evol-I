#!/usr/bin/env python3
"""Scaffold a new cloud function in <workspace>/cloud-functions/."""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.workspace import require_project, harness_root, workspace_path, load_project_manifest


_PRIMITIVE_FILES = ("app.py", "registry.py", "requirements.txt")
_PLATFORM_FILES = {
    "railway": ("railway.toml", "railpack.json"),
    "supabase": (),  # users supply supabase.toml manually for now
    "generic": (),
}


def _copy_if_absent(src: Path, dst: Path) -> bool:
    if dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def _seed_function_file(name: str, dst: Path) -> None:
    src = harness_root() / "primitives" / "cloud-functions" / "functions" / "hello_world.py"
    template = src.read_text().replace("hello_world", name)
    template = template.replace("Smoke-test cloud function. Echoes back a greeting.",
                                f"Cloud function '{name}'.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(template)


def _ensure_registry_imports(registry: Path, name: str) -> None:
    text = registry.read_text() if registry.exists() else ""
    import_line = f"from functions.{name} import {name}"
    if import_line in text:
        return
    if not text:
        seed = (harness_root() / "primitives" / "cloud-functions" / "registry.py").read_text()
        text = seed
    if import_line not in text:
        # Insert after last existing `from functions.X import X` line
        lines = text.split("\n")
        last_import = -1
        for i, line in enumerate(lines):
            if line.startswith("from functions."):
                last_import = i
        if last_import >= 0:
            lines.insert(last_import + 1, import_line)
        else:
            lines.insert(0, import_line)
        text = "\n".join(lines)
    # Add to EXPOSED_FUNCTIONS dict
    if f'"{name}": {name}' not in text:
        text = text.replace(
            "EXPOSED_FUNCTIONS = {",
            f'EXPOSED_FUNCTIONS = {{\n    "{name}": {name},',
        )
    registry.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", "--workspace", dest="workspace", default=None)
    parser.add_argument("--name", required=True, help="Function name (snake_case)")
    parser.add_argument("--platform", default=None, help="Host for the selected preset/command")
    parser.add_argument("--preset", choices=("python-fastapi",), help="Explicitly choose a bundled scaffold")
    parser.add_argument("--scaffold-command", nargs=argparse.REMAINDER, help="Custom argv command; place last. Supports {name}, {project}, {output}, {platform}")
    args = parser.parse_args()

    ws = require_project(args.workspace)
    cf_dir = workspace_path(ws, "cloud_functions")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]*", args.name):
        parser.error("Function name must contain only letters, digits, '_' or '-'")
    manifest = load_project_manifest(ws)
    preferences = manifest.get("cloud_function", {})
    commands = manifest.get("commands", {})
    if not isinstance(preferences, dict) or not isinstance(commands, dict):
        parser.error("cloud_function and commands must be mappings in n8n-project.yml")
    custom = args.scaffold_command
    if custom is None and args.preset is None:
        custom = commands.get("scaffold")
    if custom is not None:
        if not isinstance(custom, list) or not custom or any(not isinstance(arg, str) or not arg for arg in custom):
            parser.error("scaffold command must be a nonempty argument list")
        platform = args.platform or preferences.get("platform", "generic")
        replacements = {"{name}": args.name, "{project}": str(ws), "{output}": str(cf_dir), "{platform}": str(platform)}
        argv = list(custom)
        for token, value in replacements.items():
            argv = [arg.replace(token, value) for arg in argv]
        cf_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(argv, cwd=ws)
        if result.returncode:
            raise SystemExit(result.returncode)
        print(f"Project scaffold command completed for '{args.name}'.")
        return

    preset = args.preset or preferences.get("preset")
    registry = cf_dir / "registry.py"
    known_registry = registry.is_file() and "EXPOSED_FUNCTIONS = {" in registry.read_text()
    existing_service = cf_dir.is_dir() and any(p.is_file() and p.name not in (".gitignore", "__init__.py") for p in cf_dir.rglob("*"))
    if preset is None and existing_service and not known_registry:
        parser.error("Existing service preserved. Set commands.scaffold to its generator, or explicitly select --preset python-fastapi.")
    if preset not in (None, "python-fastapi"):
        parser.error(f"Unknown preset {preset!r}; use commands.scaffold for your existing language/framework")
    if not args.name.isidentifier():
        parser.error("The python-fastapi preset requires a Python identifier for --name")
    if registry.exists() and not known_registry:
        parser.error("Existing registry.py preserved: use commands.scaffold to extend its registration convention")
    platform = args.platform or preferences.get("platform")
    if platform is None:
        platform = "railway" if not existing_service or (cf_dir / "railway.toml").exists() else "generic"
    if platform not in _PLATFORM_FILES:
        parser.error(f"Host {platform!r} has no bundled config; select generic or provide commands.scaffold")
    cf_dir.mkdir(parents=True, exist_ok=True)

    # 1. Seed framework files (app.py, registry.py, requirements.txt) if absent
    src_dir = harness_root() / "primitives" / "cloud-functions"
    for fn in _PRIMITIVE_FILES:
        copied = _copy_if_absent(src_dir / fn, cf_dir / fn)
        if copied:
            print(f"  Wrote {cf_dir / fn}")

    # 2. Platform config files (only if absent)
    for fn in _PLATFORM_FILES[platform]:
        copied = _copy_if_absent(src_dir / fn, cf_dir / fn)
        if copied:
            print(f"  Wrote {cf_dir / fn}")

    # 3. functions/__init__.py
    init_dst = cf_dir / "functions" / "__init__.py"
    if not init_dst.exists():
        init_dst.parent.mkdir(parents=True, exist_ok=True)
        init_dst.write_text("")
        print(f"  Wrote {init_dst}")

    # 4. functions/hello_world.py — seed alongside since registry.py imports it
    hello_dst = cf_dir / "functions" / "hello_world.py"
    if not hello_dst.exists():
        _copy_if_absent(src_dir / "functions" / "hello_world.py", hello_dst)
        print(f"  Wrote {hello_dst}")

    # 5. functions/<name>.py (seed if absent)
    fn_dst = cf_dir / "functions" / f"{args.name}.py"
    if not fn_dst.exists():
        _seed_function_file(args.name, fn_dst)
        print(f"  Wrote {fn_dst}")
    else:
        print(f"  functions/{args.name}.py already exists; leaving in place")

    # 5. Wire into registry.py
    _ensure_registry_imports(cf_dir / "registry.py", args.name)
    print(f"  Wired '{args.name}' into registry.py")

    # 6. Add a paired test stub in cloud-functions-tests/
    tests_dir = workspace_path(ws, "cloud_tests")
    tests_dir.mkdir(parents=True, exist_ok=True)
    test_file = tests_dir / f"test_{args.name}.py"
    if not test_file.exists():
        test_file.write_text(
            f'def test_{args.name}_smoke():\n'
            f'    from functions.{args.name} import {args.name}\n'
            f'    result = {args.name}({{}})\n'
            f'    assert isinstance(result, dict)\n'
        )
        print(f"  Wrote {test_file}")

    print(f"add-cloud-function complete for '{args.name}'.")


if __name__ == "__main__":
    main()
