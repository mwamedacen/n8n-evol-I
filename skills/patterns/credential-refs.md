---
name: pattern-credential-refs
description: How workflow templates reference credentials — YAML shape and placeholder syntax.
user-invocable: false
---

# Pattern: credential refs (reference)

Paths and examples use bundled defaults; resolve actual paths and environment storage through [project configuration](../../configuration.md).

This is a **reference pattern** documenting the YAML shape and the `{{@env:credentials.<key>....}}` placeholder syntax. The actual creation/linking flow lives in [`skills/manage-credentials.md`](../manage-credentials.md).

## YAML shape

The helper presents a merged `credentials` mapping. Manifest projects persist it privately in `<env-path>/bindings.json`; legacy projects use `<config>/<env>.yml`. This YAML example shows the effective shape:

```yaml
credentials:
  microsoft_oauth:
    id: "abcdef123456"
    name: "Microsoft 365 OAuth (Dev)"
    type: "microsoftOAuth2Api"
  redis_local:
    id: "ghijkl789012"
    name: "Redis Localhost"
    type: "redis"
```

The `id` and `name` fields are populated by `manage_credentials.py` (Path A or Path B). The `type` field is the n8n-side credential type string.

## Workflow template usage

Workflow templates reference credentials via the `credentials` block on each node:

```json
{
  "type": "n8n-nodes-base.microsoftExcel",
  "credentials": {
    "microsoftExcelOAuth2Api": {
      "id": "{{@env:credentials.microsoft_oauth.id}}",
      "name": "{{@env:credentials.microsoft_oauth.name}}"
    }
  }
}
```

## Why both `id` AND `name`

Keep the ID and display name consistent with the selected deployment. A renamed or replaced credential may require refreshing the binding before deployment.

Re-link the verified credential with `manage_credentials.py list-link`; use `doctor` and deployment preflight to inspect failures. Resync preserves logical references and does not promise to update credential bindings automatically.

## Adding credentials

For selecting the private secret source, creating or linking a credential, and persisting its environment binding, see [`skills/manage-credentials.md`](../manage-credentials.md).

## Per-service quirks

Per-service `type`-string and field-shape quirks live in `skills/integrations/<service>/...md`.
