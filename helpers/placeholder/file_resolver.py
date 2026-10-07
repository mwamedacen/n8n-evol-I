"""Resolve {{INTERPOLATE_txt|md|json|html:path}} (alias `{{@...}}`) placeholders against workspace files."""
import json
import re
from pathlib import Path
from helpers.placeholder.paths import source_file

PATTERN = re.compile(r"\{\{(?:INTERPOLATE_|@)(txt|md|json|html):([^}]+)\}\}")


def resolve(text: str, workspace: Path) -> str:
    """Replace all {{INTERPOLATE_txt|md|json|html:...}} / {{@...}} tokens with file contents."""

    def _replace(match: re.Match) -> str:
        kind = match.group(1)
        rel_path = match.group(2).strip()
        if rel_path.startswith("/"):
            raise ValueError(
                f"Absolute paths in placeholders are forbidden: {{{{@{kind}:{rel_path}}}}}"
            )
        full = source_file(workspace, rel_path)
        if not full.exists():
            placeholder = "{{@" + kind + ":" + rel_path + "}}"
            raise FileNotFoundError(f"Placeholder file not found: {full} (from {placeholder})")
        content = full.read_text(encoding="utf-8")
        if kind == "json":
            json.loads(content)  # schema/assets must themselves be valid JSON
        # Tokens live inside JSON string fields. Escape once, without outer quotes.
        return json.dumps(content)[1:-1]

    return PATTERN.sub(_replace, text)
