#!/usr/bin/env python3
"""PostToolUse hook: auto-tidy workflow templates.

Reads stdin JSON from Claude Code's hook event, extracts the file path,
filters to *.template.json, invokes tidy_workflow.py --in-place.

No re-entry guard needed: tidy_workflow.py writes the file via Python
open(..., 'w'), which is not a Claude Code Write/Edit tool call and
thus does not retrigger this hook.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from helpers.workspace import discover_project, workspace_path


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = event.get("tool_input", {}).get("file_path", "")
    if not file_path.endswith(".template.json"):
        sys.exit(0)

    p = Path(file_path).resolve()
    try:
        # An edited nested project owns its files even when the agent's cwd is
        # an outer project. Cwd remains useful for explicit external mappings.
        candidates = (discover_project(p.parent), discover_project(Path(event.get("cwd") or Path.cwd())))
        ws = None
        for candidate in dict.fromkeys(candidates):
            if candidate is None:
                continue
            try:
                relative = p.relative_to(workspace_path(candidate, "templates"))
            except ValueError:
                continue
            ws = candidate
            break
        if ws is None:
            return
        key = relative.as_posix().removesuffix(".template.json")
    except (ValueError, RuntimeError) as error:
        print(f"[auto_tidy] skipping: {error}", file=sys.stderr)
        return

    # Fall back to script-relative root so skill-mode (no CLAUDE_PLUGIN_ROOT) works too
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or str(Path(__file__).resolve().parent.parent)
    helper = Path(plugin_root) / "helpers" / "tidy_workflow.py"

    result = subprocess.run(
        [sys.executable, str(helper),
         "--workspace", str(ws),
         "--workflow-key", key,
         "--in-place"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"[auto_tidy] tidy_workflow.py exited {result.returncode}: {result.stderr}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
