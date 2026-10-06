---
description: Pull live state of one workflow back into its template.
---

# resync

Path examples use bundled defaults. Resolve source and environment locations from [project configuration](../configuration.md); preserve user preferences and existing conventions.

## Current behavior

Use `--preview` to inspect the proposed file list. Resync compares the deployed baseline, local source and remote content. Conflicts stop without overwriting files; inspect the private environment state/incoming snapshot. All workflows are staged before resync_all applies shared source updates.

## When

After someone edits a workflow in the n8n UI and you want the template to reflect those changes.

## How

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/resync.py --env <env> --workflow-key <key> [--preview]
```

## Side effects

Reads the remote workflow and saves a private incoming snapshot. With a baseline, it compares remote content, prior source and current local source, preserving logical environment references and restoring accepted edits to external code/prompt/asset files. Without a baseline, it can import into an absent template; an existing differing template stops for review.

`--preview` reports proposed files without changing source. On apply, source changes are staged together with backups. Conflicts preserve local files. Baselines and snapshots live in the environment state directory; see [project configuration](../configuration.md). Raw snapshots retain remote metadata separately from reusable definitions.
