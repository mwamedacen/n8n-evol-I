# Features

This page is the feature overview. The [skill router](../SKILL.md) still links every action. The catalog below keeps the full task list. Advanced steps stay in the linked skills. [Verification results and remaining limits](testing.md) are separate from this overview.

Run helpers from the project or any subdirectory. They use the nearest `n8n-project.yml`. Pass `--workspace <project>` to override that discovery. A project without that manifest stays on the legacy layout. Paths below are bundled defaults; the manifest can map them. See [project configuration](../configuration.md).

## Multi-environment workflows

One environment is one local workspace bound to one n8n deployment. A workflow-name suffix is not isolation. Development, staging, and production use separate deployments, IDs, secrets, and sync state.

Project creation writes `n8n-project.yml` (version 1, a stable `projectId`, relative paths, and `environments.<name>.path`) and the environments directory. `workspace.yml` (non-secret target settings), private `bindings.json` (remote IDs), and private `.env` (secrets) are written only when that environment is connected. An existing project can be adopted without rewriting its files. Legacy `n8n-config/<env>.yml` remains valid until that environment is migrated. [Environments](environments.md), [bootstrap an environment](../skills/bootstrap-env.md).

After the environment is connected:

```text
environments/dev/workspace.yml    target and non-secret settings
environments/dev/bindings.json    private workflow and credential IDs
environments/dev/.env             private secrets
```

Templates refer to those IDs with `{{@env:workflows.<key>.id}}`. Do not copy live IDs from one deployment to another.

## Split source and build-time substitution

Agents edit code, prompts, schemas, and assets in project files, then compose them through compact workflow templates. At build time, `{{@type:path}}` (the same as `{{INTERPOLATE_type:path}}`) inlines a referenced file or value. Supported types are `env`, `txt`, `md`, `json`, `html`, `js`, `py`, and `uuid`. File paths are relative to the project and are not automatically prefixed with a functions directory. Remote IDs use `{{@env:workflows.<key>.id}}` and `{{@env:credentials.<key>.id}}`. [Code-node discipline](../skills/patterns/code-node-discipline.md), [prompt and schema files](../skills/patterns/prompt-and-schema-conventions.md).

```jsonc
"jsCode": "{{@js:automation/code/normalize.js}}\n\nreturn normalize(items);"
```

Use the project's configured source path in place of that example. Resync can bring accepted n8n edits back into those files. Conflicting edits stop for review.

## Dependency-ordered deployment and activation

Bulk deploy orders the workflows registered in `deployment_order.yml`. It follows `{{@env:workflows.<key>.id}}` references among those registered keys, deploys callees before callers, and stops before any remote change when a dependency is unregistered, absent from that order file, or part of a cycle. It does not deploy a free graph of planned-only references. A rollout is not a remote transaction. [Bulk deploy](../skills/deploy_all.md).

Manifest projects activate only with `--activate` or the environment setting `activation: automatic`. `--no-activate` suppresses that request. A project with no manifest keeps automatic activation. On a legacy dev environment, external triggers can stay inactive unless `--keep-active` or `--activate` is set; sub-workflows and error handlers stay available. On n8n Cloud, a parent workflow cannot be activated until each referenced workflow is already active. An activation-only failure exits 2 and the rollout continues unless `--strict-activate` is set. [Deploy one workflow](../skills/deploy.md), [activate one workflow](../skills/activate-single-workflow-in-env.md).

## Execution debugging

Ask the agent to list or inspect a failed execution and to follow the dependency graph from templates, live workflows, or both. It reports back in the session. This is not a built-in unattended alert. [Debug](../skills/debug.md), [investigation discipline](../skills/patterns/investigation-discipline.md).

## Locks, rate limits, and error handling

Shipped primitives are `lock_acquisition`, `lock_release`, `rate_limit_check`, `queue_publish`, `queue_pop`, `queue_ack`, `queue_sample_producer`, `queue_sample_consumer`, `error_handler_lock_cleanup`, `error_handler_queue_cleanup`, and `_minimal`. Copy or extend the one you need. The queue samples and `_minimal` are not required production workflows. [Copy a primitive](../skills/copy-primitive.md), [locks](../skills/patterns/locking.md), [queues](../skills/patterns/queues.md), [rate limits](../skills/add-rate-limit-to-workflow.md).

An error handler is a workflow with an Error Trigger. Pair it with the source workflow in `common.yml` under `error_source_to_handler`. Sentry, Datadog, and Slack are optional sinks you configure; they are not a built-in notification channel. [Error handling](../skills/patterns/error-handling.md).

## Cloud functions

Add a function the workflow can call over HTTP. Use the project's own generator when it has one, or the optional Python/FastAPI preset. [Add a cloud function](../skills/add-cloud-function.md).

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/add_cloud_function.py \
  --workspace <project> --name <name> --preset python-fastapi
```

A custom generator replaces that preset. Existing service files are kept.

## Prompt checks and optimization

Pair a prompt and schema with a dataset of input/expected examples. Optimization is an optional DSPy extra; its built-in score only checks that expected fields are present and truthy, not their values or semantic correctness. A custom eval file can live beside the dataset, but nothing runs it. Export writes a separate file only when the optimized score is at least the baseline. [Iterate a prompt](../skills/iterate-prompt.md).

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/iterate_prompt.py --prompt <name> --dataset <name> --optimizer bootstrap
```

## Catalog

The [skill router](../SKILL.md) links every action and reference. Concise onboarding does not remove advanced features.

| Task | Skills |
|---|---|
| Create or adopt a project | [Setup](../skills/init.md), [environments](../skills/bootstrap-env.md), [doctor](../skills/doctor.md) |
| Author reusable workflows | [Create](../skills/create-new-workflow.md), [primitives](../skills/copy-primitive.md), [code](../skills/patterns/code-node-discipline.md), [prompts/schemas](../skills/patterns/prompt-and-schema-conventions.md), [canvas layout](../skills/tidy-workflow.md) |
| Deploy and operate | [Deploy](../skills/deploy.md), [bulk deploy](../skills/deploy_all.md), [activation](../skills/activate-single-workflow-in-env.md), [deactivation](../skills/deactivate-single-workflow-in-env.md), [archive](../skills/archive-workflow.md), [restore](../skills/unarchive-workflow.md) |
| Synchronize and verify | [Resync](../skills/resync.md), [bulk resync](../skills/resync_all.md), [import](../skills/dehydrate-workflow.md), [validate](../skills/validate.md), [run](../skills/run.md), [deploy/run/assert](../skills/deploy-run-assert.md), [tests](../skills/test.md) |
| Diagnose failures | [Debug](../skills/debug.md), [investigation discipline](../skills/patterns/investigation-discipline.md), execution listing/inspection/stopping, live/source dependency graphs |
| Coordinate work | [Locks](../skills/patterns/locking.md), [queues](../skills/patterns/queues.md), [rate limits](../skills/add-rate-limit-to-workflow.md), [error handling](../skills/patterns/error-handling.md) |
| Manage services | [Credentials](../skills/manage-credentials.md), [variables](../skills/manage-variables.md), [cloud functions](../skills/add-cloud-function.md), [prompt checks](../skills/iterate-prompt.md) |
| Integrate services | Microsoft 365, Gmail, Redis, Sentry, Datadog, Slack, Google Drive, Notion, Airtable, webhooks—linked in the router |

The [skill router](../SKILL.md) retains 58 action, pattern, and integration documents plus the `skills/n8n` router alias, the helper scripts, 11 workflow primitive templates, service and prompt seeds, 10 plugin commands, and hooks. Features involving external services need their own credentials and live verification; the core workflow test does not verify every integration. [Verification results and remaining limits](testing.md).
