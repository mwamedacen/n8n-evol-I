---
name: create-new-workflow
description: Author a brand-new workflow — scaffold template + register IDs in env YAMLs + mint placeholder n8n workflow.
user-invocable: false
---

# create-new-workflow

Path examples use bundled defaults. Resolve source and environment locations from [project configuration](../configuration.md); preserve user preferences and existing conventions.

## When

The user asks to create a new workflow.

## How

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/create_workflow.py --key <key> --name "<display name>" --register-in <env> [--with-error-handler <handler-key>] [--tier <tier-name>]
```

## Side effects

1. Writes `<workspace>/n8n-workflows-template/<key>.template.json` (a Webhook + Set seed).
2. Registers the key in the selected environment's private bindings (legacy projects retain YAML rows).
3. POSTs to each env's `/workflows` to mint a placeholder, captures the returned ID, writes it back to that environment's bindings.
4. Adds the key to the configured `deployment_order.yml` at `Tier 1` by default; `--tier none` opts out.
5. (Optional) Calls `register_error_handler.py` to wire `settings.errorWorkflow`.

Omit `--register-in` when exactly one environment exists. An explicit comma-separated list opts into several deployments. `--no-mint` registers without contacting n8n; before any environment is configured, it creates only the template and deployment order. After bootstrap, rerun with `--register-in <env>` to register that template. Error-handler wiring requires an environment. `--no-template` preserves an existing imported template.

Idempotent: skips entries that already have a non-placeholder ID; n8n POST is skipped if the ID is already real.

## Next steps

- Edit the new template at `n8n-workflows-template/<key>.template.json` to add the actual nodes.
- `tidy-workflow.md` to clean up node positions after editing.
- `validate.md` to sanity-check.
- `deploy.md` to ship it.

### Code nodes

Follow [Code-node discipline](patterns/code-node-discipline.md): externalize reusable source, reference it with `{{@js:...}}` or `{{@py:...}}`, and use the project's selected test contract. The default pure-function/paired-test convention applies when no project runner exists.
