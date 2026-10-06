---
description: Run the project's selected tests for workflow code and cloud functions.
---

# test

Path examples use bundled defaults. Resolve source and environment locations from [project configuration](../configuration.md); preserve user preferences and existing conventions.

Run tests after source changes and before deployment.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/test_functions.py \
  --workspace <project> --target {n8n|cloud|all} [--filter <name>]
```

Resolution order is explicit `commands.test.n8n` / `commands.test.cloud`, then existing project scripts or pytest configuration, then bundled Node/pytest defaults. Commands are argument lists executed from the project; use `{filter}` to accept the optional filter. A shared command is run once when selecting `all`.

```yaml
# n8n-project.yml
paths:
  function_tests: tests/automation
  cloud_tests: tests/service
commands:
  test:
    n8n: [pnpm, run, test:automation]
    cloud: [python3, -m, pytest, tests/service]
```

Existing npm/pnpm/yarn/bun test scripts and pytest configuration are respected. Without them, the helper runs `*.test.js` with `node --test`, and `test_*.py` with pytest in the configured test directories. Legacy `common.yml.workspace_layout` mappings remain supported when no manifest path overrides them.

The helper prints results and returns nonzero on failure. A project test contract owns its filenames/module conventions; structural workflow validation and source existence still apply. Passing these tests does not establish real deployment, execution or resynchronization success.
