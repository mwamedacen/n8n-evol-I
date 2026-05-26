#!/usr/bin/env bash
# Build skill-dist/ — a clean copy of the repo containing only the skill
# distribution (SKILL.md, helpers, skills, primitives, top-level docs).
# Excludes: docs/, meta-evals/, tests/, hooks/, plugin manifest, VCS, caches.

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
  --exclude='/.claude/' \
  --exclude='/.claude-plugin/' \
  --exclude='/.git/' \
  --exclude='.gitignore' \
  --exclude='.gitattributes' \
  --exclude='.markdownlint.json' \
  --exclude='.DS_Store' \
  --exclude='.env*' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='*.egg-info/' \
  --exclude='*.pdf' \
  --exclude='build-skill-dist.sh' \
  --exclude='/CHANGELOG.md' \
  --exclude='/LICENSE' \
  "$SRC/" "$DEST/"

echo "Built $DEST"
( cd "$DEST" && find . -maxdepth 2 -mindepth 1 | sort )
