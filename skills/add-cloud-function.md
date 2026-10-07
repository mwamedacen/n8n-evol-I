---
name: add-cloud-function
description: Extend a project's chosen service or use the optional Python/FastAPI serverless preset.
user-invocable: false
---

# add-cloud-function

Path examples use bundled defaults. Resolve source and environment locations from [project configuration](../configuration.md); preserve user preferences and existing conventions.

Add a function callable from n8n over HTTP. Use the user's language, framework and host choices, then existing service conventions, then the bundled preset.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/add_cloud_function.py \
  --workspace <project> --name <name> [--preset python-fastapi] [--platform <host>]
```

A project can supply its own generator:

```yaml
# n8n-project.yml
paths:
  cloud_functions: services/automation
commands:
  scaffold: [node, tools/add-function.mjs, "{name}", "{output}"]
```

The command is an argument list run from the project. Supported substitutions are `{name}`, `{project}`, `{output}` and `{platform}`. `--scaffold-command <argv...>` supplies a one-off command and must appear last. No bundled framework files are added when a custom generator runs.

The `python-fastapi` preset remains available. It seeds missing `app.py`, `registry.py`, `requirements.txt`, a named Python function and a smoke test, then registers the function. Existing files are preserved; a recognized preset registry is extended. Unknown existing services require their own generator or an explicit preset choice.

Bundled host options are `railway` (Railway config), `supabase` (user-supplied hosting config), and `generic` (no host config). Set defaults with `cloud_function: {preset: python-fastapi, platform: generic}`. Use a custom command for other languages or hosts.

Service deployment follows the project's chosen hosting workflow. This helper scaffolds files; it does not deploy the service.
