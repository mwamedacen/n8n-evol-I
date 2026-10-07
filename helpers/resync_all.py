#!/usr/bin/env python3
"""Stage all environment workflows before applying any resynchronized source."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from helpers.workspace import workspace_root
from helpers.config import load_yaml
from helpers.resync import resync_many


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', '--project', dest='workspace')
    p.add_argument('--env', required=True)
    p.add_argument('--preview', action='store_true')
    args = p.parse_args()
    ws = workspace_root(args.workspace)
    from helpers.workspace import ensure_workspace
    ensure_workspace(ws)
    try:
        resync_many(ws, args.env, sorted((load_yaml(args.env, ws).get('workflows') or {})), args.preview)
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(f'Resync stopped: {exc}')


if __name__ == '__main__':
    main()
