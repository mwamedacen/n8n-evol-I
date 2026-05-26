# Changelog

## v2.0.0 — Placeholder syntax change + queue primitive

### Breaking

- **Placeholder syntax dropped the colon after the prefix.** Templates must migrate:
  - `{{@:type:path}}` → `{{@type:path}}` (e.g. `{{@:env:displayName}}` → `{{@env:displayName}}`)
  - `{{INTERPOLATE:type:path}}` → `{{INTERPOLATE_type:path}}`

  The colon between type and path (e.g. `env:displayName`) is unchanged. The legacy `{{HYDRATE:type:path}}` form is removed entirely. The validator's residual-detection regex still recognizes all stale forms (`{{HYDRATE:`, `{{INTERPOLATE:`, `{{@:`) so an unmigrated template surfaces as an error rather than passing through silently.

### Added

- **Producer–consumer queue primitive** — Redis Streams backend with semaphore-based concurrency control and a dead-letter queue. New helpers (`create_queue`, `add_queue_publish_to_workflow`, `add_queue_consumer_to_workflow`, `cleanup_queue_state`), workflow templates, and the `create-queue` / `add-queue-*` skills.
- **`{{@md:...}}` placeholder type** alongside `{{@txt:...}}`. Same raw-text semantics, but signals markdown-formatted content to reviewers. Prompt convention is now `<name>_prompt.md` (preferred); `<name>_prompt.txt` still resolves for legacy workspaces. `iterate-prompt --export` mirrors the source extension when writing the optimized variant.

### Build

- `build-skill-dist.sh` now excludes `.pytest_cache/` and `*.pdf` from the distribution.

## v1.0.0 — Read-only skill package + external workspace

The repo is now a **read-only skill package**. All user project state (templates, env config, builds, prompts, JS, assets, cloud functions) lives in a separate workspace at `${PWD}/n8n-evol-I-workspace/`. The harness directory is never modified by the agent at runtime.

### Architecture

- New top-level layout: `SKILL.md` (router), `skills/` (markdown sub-skills), `helpers/` (Python CLI scripts), `primitives/` (seed templates).
- All helpers default to `--workspace ${PWD}/n8n-evol-I-workspace`. They never write inside the harness directory (enforced by `assert_not_in_harness`).
- `n8n-evol-I -c "<python>"` REPL-style CLI is removed. There is no master CLI; each helper is invoked by absolute path.

### New skills (markdown router + sub-skills)

Lifecycle: `init`, `bootstrap-env`, `doctor`, `create-new-workflow`, `register-workflow-to-error-handler`, `create-lock`, `add-lock-to-workflow`, `deploy-{single,all}-workflow{,s}-in-env`, `activate-/deactivate-single-workflow-in-env`, `resync-{single,all}-workflow{,s}-from-env`, `dehydrate-workflow`, `validate-workflow`, `run-workflow`, `deploy-run-assert`, `manage-credentials`, `add-cloud-function`, `iterate-prompt`, `test-functions`, `find-skills`.

Patterns (read-only knowledge): `subworkflows`, `error-handling`, `credential-refs`, `multi-env-uuid-collision`, `validate-deploy`, `llm-providers`, `locking`, `pindata-hygiene`, `position-recalculation`, `prompt-and-schema-conventions`.

Integrations (per-service quirks): `microsoft-365`, `gmail`, `redis`, `slack`, `google-drive`, `notion`, `airtable`, `webhooks`.

### New helpers

`helpers/{init, bootstrap_env, doctor, create_workflow, register_error_handler, create_lock, add_lock_to_workflow, hydrate, dehydrate, deploy, deploy_run_assert, activate, deactivate, deploy_all, resync, resync_all, validate, run, manage_credentials, add_cloud_function, iterate_prompt, test_functions, find_skills, diff}.py`. Plus libraries: `helpers/{workspace, config, n8n_client, _dspy_config}.py` and `helpers/placeholder/{env_resolver, file_resolver, js_resolver, uuid_resolver, validator}.py`.

### New primitives

`primitives/workflows/{_minimal, lock_acquisition, lock_release, error_handler_lock_cleanup}.template.json`. Sub-workflow primitives use `executeWorkflowTrigger` with `inputSource: passthrough` to satisfy n8n's publish validation.

`primitives/cloud-functions/{app, registry}.py + functions/hello_world.py + requirements.txt + railway.toml + railpack.json` — seed for `add-cloud-function`.

`primitives/prompts/{example_summary_prompt.md, example_summary_schema.json}` — seed for `iterate-prompt`.

### New workspace contracts

`n8n-config/common.yml` — workspace-shared config:

- `error_source_to_handler:` map (source-key → handler-key) used by `run.py` for indirect dispatch.
- `workspace_layout:` overrides for non-default directory placement.

### Removed

- `n8n/`, `common/`, `factory/`, `cloud_functions/`, `pattern-skills/`, `integration-skills/` — all replaced by the new `helpers/`, `primitives/`, `skills/` tree.
- `helpers.py`, `admin.py`, `run.py`, `setup.sh`, root `test_*.py` — replaced.
- `n8n-evol-I` console script (`[project.scripts]` removed from `pyproject.toml`).

### Migration from pre-rebuild

See [`docs/migration-from-d6848fd.md`](docs/migration-from-d6848fd.md) for the full mapping from old paths/commands to new equivalents.

### Test methodology

`tests/test_*.py` covers each helper offline (mocked HTTP). The `test-agent-workspace/` self-test in `n8n-harness-rebuild-plan.md` §7 walks all 13 lifecycle steps end-to-end against a real n8n instance.

## Pre-rebuild (≤ d6848fd) — legacy

The previous repo was a workspace, not a tool. Helpers and templates lived intermingled at the repo root. Customizing meant editing the repo's own files. See `git log` from `d6848fd` and earlier for that history.
