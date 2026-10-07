---
description: Roll out an entire env in tier order.
---

# deploy_all

Path examples use bundled defaults. Resolve source and environment locations from [project configuration](../configuration.md); preserve user preferences and existing conventions.

## When

Bulk deploy or initial deployment for an env.

## How

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/deploy_all.py --env <env> [--preview] [--activate] [--strict-activate] [--keep-active] [--continue-on-failure]
```

## Side effects

- Reads the configured `deployment_order.yml`, combines natural tier order with workflow-reference dependencies, and rejects cycles or missing dependencies before remote mutation.
- Preflights the complete plan, then calls `deploy.py` for each workflow in dependency order. `--preview` stops after preflight; `--activate` requests publication.
- Manifest projects keep the explicit activation policy. Legacy dev behavior can deactivate external triggers unless `--keep-active` or `--activate` is supplied; subworkflows and handlers remain available.
- PUT failures return nonzero, including when `--continue-on-failure` finishes remaining workflows. Activation-only failures warn and continue unless `--strict-activate` is set. A rollout is not a remote transaction; inspect partial results before retrying.
