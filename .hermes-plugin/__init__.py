"""Thin native Hermes adapter; the root skill owns the workflow guidance."""
from pathlib import Path


def register(ctx):
    root = Path(__file__).resolve().parent.parent
    skill = root / "SKILL.md"
    if not skill.is_file():
        raise RuntimeError("n8n-evol-I installation is incomplete: missing root SKILL.md")
    ctx.register_skill("n8n", skill, description="Create, adopt, deploy and resynchronize n8n projects")
    ctx.register_system_prompt_section(
        "n8n-evol-i.router",
        "For n8n project work, load skill_view('n8n-evol-I:n8n') and follow its relevant references. "
        f"Toolkit root: {root}. Invoke helpers with {root / 'scripts/python'}; "
        "it supplies dependencies in a machine cache. Preserve user instructions and project conventions.",
        max_chars=1200,
    )
