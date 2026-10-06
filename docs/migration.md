# Adopt and migrate safely

User preferences take precedence over existing conventions; conventions take precedence over bundled defaults. Keep the old helper entrypoints, skills, primitives, and placeholder spellings.

## Adopt an existing project

For direct commands, set `TOOLKIT` to the absolute plugin installation or checkout path and replace `<project>` with your project path. Your agent can locate its installed toolkit for you.

```bash
"$TOOLKIT/scripts/python" "$TOOLKIT/helpers/init.py" --project <project> --adopt \
  --path templates=workflows --path functions=src/functions \
  --path function_tests=tests/workflows
```

The initializer adds a manifest and missing support files. Existing instructions, secrets, source, data and permissions remain unchanged. It prints the files it creates or preserves. Repeating the command is safe; `--force` is now a deprecated additive alias, never a delete operation.

Read the generated manifest and map other established paths before operating. Supported path keys: `config`, `templates`, `functions`, `function_tests`, `prompts`, `assets`, `cloud_functions`, `cloud_tests`. Existing instruction files remain in place; add a pointer yourself if your runtime needs one.

The default filenames remain compatible with legacy projects. Existing YAML environments are marked for legacy reading; they do not suddenly move or lose IDs. Migrate one at a time:

```bash
"$TOOLKIT/scripts/python" "$TOOLKIT/helpers/bootstrap_env.py" --workspace <project> --env dev --migrate --dry-run
"$TOOLKIT/scripts/python" "$TOOLKIT/helpers/bootstrap_env.py" --workspace <project> --env dev --migrate
```

The migration retains original environment files and copies secrets, bindings, state and build output into the mapped environment workspace. It records the legacy automatic activation default explicitly, preserving any configured activation policy. A collision stops the operation. It validates the real deployment before changing the active mapping.

## Adapt commands

In `n8n-project.yml`, `commands.test.n8n` and `commands.test.cloud` can hold argument arrays for your existing runners. A configured scaffold command can create functions using your language/framework; the Python/FastAPI preset remains available. See the helper's `--help` and the generated manifest conventions. Avoid shell-command strings containing secrets.

## Compatibility changes

- `init --force` preserves files instead of recreating the directory.
- Creating a workflow in a project with several environments requires an explicit `--register-in`; it no longer implicitly touches all targets.
- New-format deployment requires `--activate` or the environment's explicit automatic activation policy. Legacy projects retain the previous activation default.
- Resync refuses conflicting local/remote edits or overwriting existing source without a baseline.
- Deploy always rebuilds; `--rehydrate` remains accepted.
- Generic process secrets no longer leak into a selected environment.

Both `{{@type:path}}` and `{{INTERPOLATE_type:path}}` remain supported, including legacy code markers. All skill paths and helper scripts are retained. See [the capability list](capabilities.md).

## Recovery

Keep a source-control snapshot and private state backup before a migration. Setup does not create a durable initialization receipt. Review its output and the before/after file diff; manually remove only confirmed additions that have not changed since adoption. Preserve later user edits. Existing instruction/secret/data files require no rollback because adoption leaves them intact.

Resync records original and proposed contents under environment `state/operations/`. A handled write error restores the original files. A process or machine crash may leave a prepared receipt: inspect it and reconcile file hashes before retrying. Remote snapshots live under `state/before-deploy/` and `state/incoming/`. Restoring local Git files alone does not restore remote n8n definitions or undo workflow executions.
