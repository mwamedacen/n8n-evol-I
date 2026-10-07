# Project configuration

Follow explicit user preferences, then existing project conventions, then bundled defaults. The installed toolkit stays read-only. Run helpers from the project or a subdirectory; use `--workspace <project>` to override discovery.

`init.py --project <path>` creates missing files. Add `--adopt` for an existing project and `--path templates=automation/workflows` to map its layout. Existing instructions, secrets and data stay intact. New manifests include a stable UUID `projectId`; retain it when moving or checking out the same project. Existing manifests are not silently rewritten: assign and retain an ID as an explicit migration when needed.

```yaml
version: 1
projectId: <stable UUID created by init>
paths:
  templates: automation/workflows
  function_tests: tests/automation
  cloud_functions: services/automation
commands:
  test:
    n8n: [pnpm, run, test:automation]
    cloud: [python3, -m, pytest, tests/service]
  scaffold: [node, tools/add-function.mjs, "{name}", "{output}"]
environments:
  dev:
    path: environments/dev
  production:
    path: environments/production
```

Paths resolve relative to the manifest. Explicit source mappings may reference shared directories outside the project; environment paths must stay inside the project and must not overlap. Symlink escapes and writes into the installed toolkit are rejected. Each environment targets a separate n8n deployment; a display-name suffix is not isolation.

| Path kind | Default |
|---|---|
| `config` | `n8n-config` (shared settings and legacy configuration) |
| `templates` | `n8n-workflows-template` |
| `functions` | `n8n-functions` |
| `function_tests` | `n8n-functions-tests` |
| `prompts` | `n8n-prompts` |
| `assets` | `n8n-assets` |
| `cloud_functions` | `cloud-functions` |
| `cloud_tests` | `cloud-functions-tests` |

Skill examples use these defaults. Substitute configured paths rather than creating parallel default directories. File placeholders remain project-relative, for example `{{@js:automation/code/normalize.js}}`; they do not automatically prepend a functions directory.

| Data | Manifest environment workspace | Legacy environment |
|---|---|---|
| Target/non-secret configuration | `<env-path>/workspace.yml` | `<config>/<env>.yml` |
| Workflow and credential IDs | `<env-path>/bindings.json` (private) | `workflows`/`credentials` in legacy YAML |
| Secrets | `<env-path>/.env` (private) | `<config>/.env.<env>` |
| Generated output | `<env-path>/build/` | `n8n-build/<env>/` |
| Baselines/snapshots | `<env-path>/state/` | `.n8n-state/<env>/` |

Adoption marks existing configurations `legacy: true`. They keep their old paths until `bootstrap_env.py --env <env> --migrate`; originals remain available. An unregistered legacy YAML is also recognized for compatibility. Shared `common.yml` and `deployment_order.yml` remain under the configured `config` path.

`commands.test.n8n` and `.cloud` are argument lists, run directly from the project without a shell. Without an explicit command, existing npm/pnpm/yarn/bun scripts or pytest configuration take precedence over the bundled Node/pytest conventions. Use `{filter}` in a custom command to consume `test_functions.py --filter`; otherwise the full project command runs. A project test contract owns its test filenames and module rules. It does not transpile source for the n8n runtime.

`commands.scaffold` is an argument list with optional `{name}`, `{project}`, `{output}` and `{platform}` substitutions. It can extend the project's chosen language, framework and host. The bundled preset remains available as `cloud_function: {preset: python-fastapi, platform: generic}` or CLI `--preset python-fastapi`; `railway` and `supabase` host options remain compatible. An unknown existing service requires its own generator or an explicit preset choice.

The layout SDK cache uses `N8N_EVOL_CACHE_HOME`, otherwise `$XDG_CACHE_HOME/n8n-evol-I` (or `~/.cache/n8n-evol-I`). Installed tooling, project source, reusable caches and private environment state have separate ownership.
