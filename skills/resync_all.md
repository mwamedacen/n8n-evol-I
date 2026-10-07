---
description: Snapshot a full env back to templates.
---

# resync_all

Path examples use bundled defaults. Resolve source and environment locations from [project configuration](../configuration.md); preserve user preferences and existing conventions.

## When

A periodic backup of all live workflows, or after a UI editing session that touched many workflows.

## How

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/resync_all.py --env <env> [--preview]
```

Plans every workflow registered in the selected environment before applying any source changes. Shared-file disagreements or local/remote conflicts stop the batch. `--preview` reports the combined file list; apply writes accepted files with backups and records each baseline. Private snapshots remain in the environment state directory even when review stops the operation.
