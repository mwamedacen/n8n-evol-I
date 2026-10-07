---
name: n8n-evol-I
description: A harness to help coding agents build, deploy, maintain, and debug multi-workflow n8n-powered automation systems. No lock-in — work from the agent, continue from the n8n UI, hand back to the agent at any time.
---

# n8n-evol-I skill router

This is the entry point. When the user asks anything n8n-related, route to the matching sub-skill.

## Mental model

- User preferences first, existing project conventions second, bundled defaults last. See [project configuration](configuration.md) for path mappings, environment storage and command overrides.
- The installed toolkit is read-only. Resolve it from the skill/plugin location, never from the project's current directory.
- Project files are reusable source. `n8n-project.yml` maps their paths and one environment workspace per deployment. Helpers find the nearest project from subdirectories; `--workspace <project>` remains an explicit override.
- Each environment owns its credential bindings, remote workflow IDs, build output, synchronization baseline and execution state. Local n8n and n8n Cloud use the same helpers. Use distinct deployments for separate environments.
- For a new project use `helpers/init.py --project <path>`; for an existing project add `--adopt` and preserve its instructions, secrets, files and data. `--path KIND=relative/path` maps existing layouts. Setup is additive, including the deprecated `--force` flag.
- Read existing instructions and `N8N-WORKSPACE-MEMORY.md` if present. Append durable project findings without rewriting history or storing secrets.
- Select the environment explicitly. Creation must not silently write to every deployment. New-format deploys require `--activate` to publish; legacy projects retain their documented activation default.
- Use `resync.py --preview` to inspect remote changes. Conflicts stop without overwriting local source. Raw incoming snapshots and deployment baselines are private environment state.
- Invoke helpers with `"<installed-toolkit>/scripts/python" "<installed-toolkit>/helpers/<name>.py"`. The launcher uses a suitable existing Python or prepares dependencies in the tool cache; no manual virtual environment setup is needed. Where linked skills show `python3`, use this launcher. In Claude plugin mode `<installed-toolkit>` is `${CLAUDE_PLUGIN_ROOT}`; other adapters provide the absolute installation path.

## Lifecycle skills (use when the user wants to do X)

| Skill | When |
|---|---|
| [init.md](skills/init.md) | Create or safely adopt a project; preserve existing files and map its layout. |
| [bootstrap-env.md](skills/bootstrap-env.md) | Configure an environment (`dev` / `staging` / `prod`). Validates a deployment, isolates its configuration/secrets/bindings, and mints requested placeholder workflow IDs. |
| [doctor.md](skills/doctor.md) | Health check. Run before/after major changes. |
| [create-new-workflow.md](skills/create-new-workflow.md) | Author a brand-new workflow. |
| [register-workflow-to-error-handler.md](skills/register-workflow-to-error-handler.md) | Wire `settings.errorWorkflow`. |
| [create-lock.md](skills/create-lock.md) | First-time setup for distributed locking (Redis-backed primitives). |
| [copy-primitive.md](skills/copy-primitive.md) | Copy a single primitive (any) into the workspace. General-purpose; doesn't register. |
| [add-lock-to-workflow.md](skills/add-lock-to-workflow.md) | Wrap a workflow's main flow in lock acquire/release. |
| [add-rate-limit-to-workflow.md](skills/add-rate-limit-to-workflow.md) | Gate a workflow's main flow with a Redis-backed fixed-window rate-limit check. |
| [create-queue.md](skills/create-queue.md) | First-time setup for queue primitive (Redis Streams + atomic-INCR semaphore). |
| [add-queue-publish-to-workflow.md](skills/add-queue-publish-to-workflow.md) | Wrap a workflow with a producer-side XADD call. |
| [add-queue-consumer-to-workflow.md](skills/add-queue-consumer-to-workflow.md) | Turn a workflow into a schedule-polled queue consumer with bounded concurrency. |
| [tidyup.md](skills/tidyup.md) | Compatibility alias for canvas layout. |
| [tidy-workflow.md](skills/tidy-workflow.md) | Apply n8n's canvas-layout algorithm to a workflow template to clean up node positions. |
| [deploy.md](skills/deploy.md) | Deploy one workflow to one env. |
| [activate-single-workflow-in-env.md](skills/activate-single-workflow-in-env.md) | Activate after deploy. |
| [deactivate-single-workflow-in-env.md](skills/deactivate-single-workflow-in-env.md) | Pause triggers (commonly during dev). |
| [archive-workflow.md](skills/archive-workflow.md) | Retire a deployed workflow (hidden + read-only on the live instance). |
| [unarchive-workflow.md](skills/unarchive-workflow.md) | Restore a previously-archived workflow so it accepts updates again. |
| [deploy_all.md](skills/deploy_all.md) | Roll out an entire env in tier order. |
| [resync.md](skills/resync.md) | Pull live state of one workflow back into its template. |
| [resync_all.md](skills/resync_all.md) | Snapshot a full env back to templates. |
| [dehydrate-workflow.md](skills/dehydrate-workflow.md) | Convert raw exported JSON into a template. |
| [validate.md](skills/validate.md) | Structural REST validation before deploy. |
| [run.md](skills/run.md) | Fire a webhook + assert terminal status. |
| [debug.md](skills/debug.md) | Investigate a failing or missing execution — from vague symptom to root-cause with evidence. |
| [deploy-run-assert.md](skills/deploy-run-assert.md) | One-shot validate → deploy → run verify. |
| [find-skills.md](skills/find-skills.md) | While authoring, find applicable patterns/integrations. |
| [manage-credentials.md](skills/manage-credentials.md) | Create or link n8n credentials (Path A from `.env.<env>` / Path B from existing UI credential). |
| [manage-variables.md](skills/manage-variables.md) | Lifecycle for n8n Variables (`$vars.*` — non-credential runtime values, or secret fallback when `$env` is blocked). |
| [add-cloud-function.md](skills/add-cloud-function.md) | Scaffold a Python serverless function / cloud function / serverless API under `<workspace>/cloud-functions/`. |
| [iterate-prompt.md](skills/iterate-prompt.md) | Optimize a prompt against a paired schema + dataset using DSPy. |
| [test.md](skills/test.md) | Run unit tests over n8n Code-node JS and / or cloud-function Python. |

## Pattern skills (read-only knowledge)

These are reference docs, not action triggers. Read them while authoring.

- [skills/patterns/subworkflows.md](skills/patterns/subworkflows.md)
- [skills/patterns/error-handling.md](skills/patterns/error-handling.md)
- [skills/patterns/credential-refs.md](skills/patterns/credential-refs.md)
- [skills/patterns/multi-env-uuid-collision.md](skills/patterns/multi-env-uuid-collision.md)
- [skills/patterns/validate-deploy.md](skills/patterns/validate-deploy.md)
- [skills/patterns/code-node-discipline.md](skills/patterns/code-node-discipline.md)
- [skills/patterns/llm-providers.md](skills/patterns/llm-providers.md)
- [skills/patterns/locking.md](skills/patterns/locking.md)
- [skills/patterns/queues.md](skills/patterns/queues.md)
- [skills/patterns/pindata-hygiene.md](skills/patterns/pindata-hygiene.md)
- [skills/patterns/position-recalculation.md](skills/patterns/position-recalculation.md)
- [skills/patterns/prompt-and-schema-conventions.md](skills/patterns/prompt-and-schema-conventions.md)
- [skills/patterns/agent-api-discipline.md](skills/patterns/agent-api-discipline.md)
- [skills/patterns/investigation-discipline.md](skills/patterns/investigation-discipline.md)

## Integration skills (per-service quirks)

- [skills/integrations/microsoft-365/excel-and-sharepoint.md](skills/integrations/microsoft-365/excel-and-sharepoint.md)
- [skills/integrations/gmail/sending-email.md](skills/integrations/gmail/sending-email.md)
- [skills/integrations/redis/lock-pattern.md](skills/integrations/redis/lock-pattern.md)
- [skills/integrations/redis/queue-pattern.md](skills/integrations/redis/queue-pattern.md)
- [skills/integrations/sentry/README.md](skills/integrations/sentry/README.md)
- [skills/integrations/datadog/README.md](skills/integrations/datadog/README.md)
- [skills/integrations/slack/README.md](skills/integrations/slack/README.md)
- [skills/integrations/google-drive/README.md](skills/integrations/google-drive/README.md)
- [skills/integrations/notion/README.md](skills/integrations/notion/README.md)
- [skills/integrations/airtable/README.md](skills/integrations/airtable/README.md)
- [skills/integrations/webhooks/README.md](skills/integrations/webhooks/README.md)

## Placeholder syntax (workflow templates)

Templates use `{{@type:path}}` (preferred form) or the canonical long form `{{INTERPOLATE_type:path}}`. The two are equivalent — `@` is an alias for `INTERPOLATE_`. Examples below use the `@` form.

| Type | Syntax | Source |
|---|---|---|
| `env` | `{{@env:key.path}}` | YAML config value (dot notation) |
| `txt` | `{{@txt:relative/path.txt}}` | Plain-text file in workspace |
| `md` | `{{@md:relative/path.md}}` | Markdown file (preferred for prompts) |
| `json` | `{{@json:relative/path.json}}` | JSON file (stringified) |
| `html` | `{{@html:relative/path.html}}` | HTML file |
| `js` | `{{@js:relative/path.js}}` | JavaScript file |
| `py` | `{{@py:relative/path.py}}` | Python file (Code-node `language: python`) |
| `uuid` | `{{@uuid:identifier}}` | Stable UUID for this workflow and environment; distinct across environments |
