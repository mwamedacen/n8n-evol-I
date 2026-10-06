---
name: activate-single-workflow-in-env
description: Activate an already-deployed workflow.
user-invocable: false
---

# activate-single-workflow-in-env

Path examples use bundled defaults. Resolve source and environment locations from [project configuration](../configuration.md); preserve user preferences and existing conventions.

## When

Activate a workflow that was deployed with `--no-activate`, or re-activate after a deactivate.

## How

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/activate.py --env <env> --workflow-key <key>
```

POST `/api/v1/workflows/<id>/activate`. Idempotent on the n8n side.
