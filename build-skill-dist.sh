#!/usr/bin/env bash
# Build skill-dist/ — a clean copy of the repo containing only the skill
# distribution (SKILL.md, helpers, skills, primitives, top-level docs).
# Includes published user docs; excludes research/eval evidence, tests, hooks,
# plugin manifest, VCS and caches. The installed skill does not need eval inputs.

set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$SRC/skill-dist"

rm -rf "$DEST"
mkdir -p "$DEST"

rsync -a \
  --exclude='/skill-dist/' \
  --exclude='/docs/' \
  --exclude='/meta-evals/' \
  --exclude='/tests/' \
  --exclude='/hooks/' \
  --exclude='/commands/' \
  --exclude='/skills/n8n/' \
  --exclude='/.agents/' \
  --exclude='/.codex-plugin/' \
  --exclude='/.hermes-plugin/' \
  --exclude='/plugin.yaml' \
  --exclude='/__init__.py' \
  --exclude='/.claude/' \
  --exclude='/.claude-plugin/' \
  --exclude='/.git/' \
  --exclude='.gitignore' \
  --exclude='.gitattributes' \
  --exclude='.markdownlint.json' \
  --exclude='.DS_Store' \
  --exclude='.env*' \
  --exclude='__pycache__/' \
  --exclude='node_modules/' \
  --exclude='.cache/' \
  --exclude='.pytest_cache/' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='*.egg-info/' \
  --exclude='*.pdf' \
  --exclude='build-skill-dist.sh' \
  "$SRC/" "$DEST/"

# Copy only the maintained user documentation, not local research, prompts or
# evaluation traces. These files are linked by README and available offline.
mkdir -p "$DEST/docs/assets"
for doc in capabilities.md environments.md migration.md sync.md testing.md; do
  if [ -f "$SRC/docs/$doc" ]; then
    cp "$SRC/docs/$doc" "$DEST/docs/$doc"
  fi
done
if [ -f "$SRC/docs/assets/project-flow.svg" ]; then
  cp "$SRC/docs/assets/project-flow.svg" "$DEST/docs/assets/project-flow.svg"
fi

# Keep research/evaluation evidence out of installed tooling while making its
# supporting links usable from the published distribution.
python3 - "$DEST" <<'PY'
import posixpath
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
repository = "https://github.com/mwamedacen/n8n-evol-I/blob/main/"
for document in root.rglob("*.md"):
    parent = document.relative_to(root).parent.as_posix()

    def published_link(match):
        target = match.group(1)
        relative = posixpath.normpath(posixpath.join(parent, target))
        if relative.startswith("docs/review-"):
            return "](" + repository + relative + ")"
        return match.group(0)

    original = document.read_text(encoding="utf-8")
    updated = re.sub(r"\]\(([^\s)]+)\)", published_link, original)
    if updated != original:
        document.write_text(updated, encoding="utf-8")
PY

echo "Built $DEST"
( cd "$DEST" && find . -maxdepth 2 -mindepth 1 | sort )
