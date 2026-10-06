---
name: bootstrap-env
description: Connect one environment to n8n and maintain its isolated configuration and workflow bindings.
user-invocable: false
---

# bootstrap-env

Path examples use bundled defaults. Resolve source and environment locations from [project configuration](../configuration.md); preserve user preferences and existing conventions.

Connect a new environment or mint IDs for its registered placeholder workflows. Use a separate n8n deployment for each environment; local HTTP and Cloud HTTPS endpoints use the same helper.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/bootstrap_env.py \
  --workspace <project> --env <env> --instance <url>
```

Enter the API key at the hidden prompt or provide it through `--api-key-stdin`. A generic `N8N_API_KEY` is initial-bootstrap input only; subsequent operations use the selected environment's private secret source or explicitly scoped process variables. Existing `--api-key` invocations remain compatible.

The helper validates the target before writing configuration, creates missing files, then mints only registered placeholder IDs. Each returned ID is persisted so retries retain earlier successful work. `--dry-run` reports planned work without writing or POSTing. `--postfix` and `--display-name` remain available.

In manifest projects, the mapped environment directory contains `workspace.yml` (non-secret configuration), `.env` (private secrets), and `bindings.json` (private workflow and credential IDs). Existing legacy projects retain `<config>/<env>.yml` and `<config>/.env.<env>` until migrated. See [project configuration](../configuration.md).

Use `--migrate` to copy a legacy environment into the new layout while retaining originals. Changing deployment URL or project identity requires `--rebind` and explicit replacement credentials; prior configuration, bindings and runtime state are backed up privately. Never copy another environment's IDs to the new deployment.

There is no automatic environment teardown. Preserve configuration, secret sources, bindings and backups until the replacement is verified; retire remote resources only within the user's requested scope.
