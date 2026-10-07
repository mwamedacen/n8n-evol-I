---
name: tidy-workflow
description: Apply n8n's canvas-layout algorithm to a workflow template so node positions are clean and consistent.
user-invocable: false
---

# tidy-workflow

Path examples use bundled defaults. Resolve source and environment locations from [project configuration](../configuration.md); preserve user preferences and existing conventions.

## When

After authoring or editing a workflow template — especially after `add-lock-to-workflow.md`, `add-rate-limit-to-workflow.md`, or any operation that shifts node positions. Also useful before committing templates to version control.

## How

```bash
# plugin mode
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/tidy_workflow.py \
  --workspace <ws> --workflow-key <key> [--in-place]

# standalone skill mode (run from harness repo root)
python3 helpers/tidy_workflow.py \
  --workspace <ws> --workflow-key <key> [--in-place]
```

- Default: prints the tidied JSON to stdout.
- `--in-place`: writes the result back to `<ws>/n8n-workflows-template/<key>.template.json`.

## Side effects

On first run, installs the pinned `@n8n/workflow-sdk@0.10.2` into the user cache described in [project configuration](../configuration.md). The installed toolkit stays unchanged. If `node`/`npm` are unavailable or the install fails, the helper falls back to a pure-Python BFS layout — less faithful than dagre but idempotent and crash-free.

Sticky notes (`type: n8n-nodes-base.stickyNote`) are never moved.

## Idempotence

Running tidy twice on the same input produces byte-identical output when using the BFS fallback. SDK-path idempotence depends on `layoutWorkflowJSON` being deterministic, which is expected but not verified by offline tests.

## Auto-tidy hook (plugin mode only)

When n8n-evol-I is installed as a Claude Code plugin, a PostToolUse hook fires `tidy_workflow.py --in-place` automatically after every `*.template.json` Write/Edit/MultiEdit. Standalone-skill-mode users who want auto-tidy can configure a hook manually in `~/.claude/settings.json`.

To disable the hook after plugin install: use the agent runtime's hook/plugin settings; do not edit the installed package.

## License

`@n8n/workflow-sdk` is published under the **n8n Sustainable Use License (SUL)**, not MIT. n8n-evol-I does not redistribute the SDK — your machine fetches it from npm at first run. n8n-evol-I itself remains MIT.

## Install size

First use downloads the pinned SDK and its dependencies. Later runs reuse its versioned cache. Missing Node/npm or a failed download keeps the Python fallback available.

## See also

- `create-new-workflow.md` — scaffold a new workflow (tidy after editing)
- `add-lock-to-workflow.md` — adds nodes that shift positions (run tidy after)
- `add-rate-limit-to-workflow.md` — same
