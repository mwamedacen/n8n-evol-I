# Capabilities

The [skill router](../SKILL.md) links every action and reference. Concise onboarding does not remove advanced features.

| Task | Skills |
|---|---|
| Create or adopt a project | [Setup](../skills/init.md), [environments](../skills/bootstrap-env.md), [doctor](../skills/doctor.md) |
| Author reusable workflows | [Create](../skills/create-new-workflow.md), [primitives](../skills/copy-primitive.md), [code](../skills/patterns/code-node-discipline.md), [prompts/schemas](../skills/patterns/prompt-and-schema-conventions.md), [canvas layout](../skills/tidy-workflow.md) |
| Deploy and operate | [Deploy](../skills/deploy.md), [bulk deploy](../skills/deploy_all.md), [activation](../skills/activate-single-workflow-in-env.md), [deactivation](../skills/deactivate-single-workflow-in-env.md), [archive](../skills/archive-workflow.md), [restore](../skills/unarchive-workflow.md) |
| Synchronize and verify | [Resync](../skills/resync.md), [bulk resync](../skills/resync_all.md), [import](../skills/dehydrate-workflow.md), [validate](../skills/validate.md), [run](../skills/run.md), [deploy/run/assert](../skills/deploy-run-assert.md), [tests](../skills/test.md) |
| Diagnose failures | [Debug](../skills/debug.md), [investigation discipline](../skills/patterns/investigation-discipline.md), execution listing/inspection/stopping, live/source dependency graphs |
| Coordinate work | [Locks](../skills/patterns/locking.md), [queues](../skills/patterns/queues.md), [rate limits](../skills/add-rate-limit-to-workflow.md), [error handling](../skills/patterns/error-handling.md) |
| Manage services | [Credentials](../skills/manage-credentials.md), [variables](../skills/manage-variables.md), [cloud functions](../skills/add-cloud-function.md), [DSPy prompt optimization](../skills/iterate-prompt.md) |
| Integrate services | Microsoft 365, Gmail, Redis, Sentry, Datadog, Slack, Google Drive, Notion, Airtable, webhooks—linked in the router |

The [skill router](../SKILL.md) retains 58 action, pattern, and integration documents plus the `skills/n8n` router alias, the helper scripts, 11 workflow primitive templates, service and prompt seeds, 10 plugin commands, hooks, and the evaluation scenarios. Features involving external services need their own credentials and live verification; the core workflow test does not verify every integration.
