# Competitive comparison — n8n-evol-I vs n8n-as-code vs @n8n/workflow-sdk

> **Date**: 2026-05-02
> **Reviewer**: Claude Opus 4.7
> **Scope**: side-by-side architectural comparison of three projects in the n8n authoring/ops space — read-only, code-and-design driven.
> **Methodology**: code + docs only (no live signals)

---

## TL;DR

These three projects sit at **different layers of the same stack**, not on the same axis:

- **`@n8n/workflow-sdk`** (path: `n8n-io/n8n/packages/@n8n/workflow-sdk`, npm `@n8n/workflow-sdk`, currently shipping 0.10.x stable / 0.11.x latest / 0.12.x beta — pinned at 0.10.2 inside this repo at `helpers/package.json:1` and `helpers/tidy_workflow.py:23`) is **infrastructure**: n8n's own TypeScript fluent-builder for workflow JSON, with type-safe nodes, AI subnode builders, codegen, validation, layout, and embedded LLM prompts. n8n's in-product AI workflow builder uses it. So does `n8n-evol-I`'s own `tidy_workflow.py` (via `helpers/tidy_shim.mjs:3`).
- **`EtienneLescot/n8n-as-code`** is a **product**: an "installable ontology" + multi-IDE plugin (VS Code, Open VSX, Claude Code, OpenClaw) that grounds an AI agent in every n8n node + property, with TS-decorator-style authoring and 3-way-merge bidirectional sync to a live instance.
- **`n8n-evol-I`** is a **product**: a Python skill-pack for the *operations* phase — multi-env promotion, dependency-tier deploy, Redis lock/rate-limit primitives, FastAPI cloud-function escape hatch, DSPy prompt iteration, execution-debug helpers — built *on top of* the official SDK rather than instead of it.

The honest framing: this is not three competitors. **`@n8n/workflow-sdk` is the foundation** that the other two can both consume. **`n8n-as-code` and `n8n-evol-I` are the actual peers** — and they target different lifecycle phases (authoring + agent-grounding vs. ops + multi-env). The interesting design question per axis is "what does each project add that the SDK alone doesn't, and where does each lose to the other."

---

## Per-axis comparison

### 1. Positioning

- **`@n8n/workflow-sdk`** — own words: *"TypeScript SDK for programmatically creating n8n workflows."* My read: the canonical workflow-construction engine n8n itself uses; ships the prompt assets that LLM-driven builders need; nothing about deploy/ops.
- **`n8n-as-code`** — own words: *"The AI Skill that gives your coding agent n8n superpowers… Zero external calls. Zero latency. Zero hallucination."* My read: agent-grounding-first, distribution-heavy; the ontology *is* the product, the TS-builder is the surface.
- **`n8n-evol-I`** — own words: *"A harness to help coding agents build, deploy, maintain, and debug multi-workflow n8n-powered automation systems."* My read: ops-discipline-first; the workspace layout, the validator, and the dependency-tier deploy *are* the product.

### 2. Scope (lifecycle phases owned)

- SDK: author + serialize/deserialize + validate + layout. *Construction only.*
- n8n-as-code: author + agent-knowledge layer + bidirectional sync + multi-IDE distribution.
- n8n-evol-I: author (template-with-placeholders), validate, deploy (tiered, multi-env), promote, lock, rate-limit, debug, prompt-iterate, scaffold serverless. *Most of the ops phase the other two skip.*

### 3. Abstractions (the unit of work)

- SDK: fluent builder. `workflow().withName(…).addTrigger(manual()).then(httpRequest({…})).build()` — exported as `workflow`, `node`, `trigger`, `ifElse`, `switchCase`, `merge`, `splitInBatches`, plus AI subnode builders (`languageModel`, `memory`, `tool`, `outputParser`, `embedding`, `vectorStore`, `retriever`, `documentLoader`, `textSplitter`, `fromAi`).
- n8n-as-code: TypeScript classes with `@workflow` / `@node` decorators (older framing) bridged to an installable ontology of every node and property (current framing). Effectively a typed builder *plus* embedded reference data.
- n8n-evol-I: JSON template files with `{{@js|py|txt|json|html|env|uuid:...}}` placeholders that hydrate at deploy time. Lower-level than a typed builder; higher-level than raw n8n JSON because of the placeholder layer.

### 4. Code-and-data segmentation

- SDK: none enforced. You put code-node JS/Python wherever you want in your TS program.
- n8n-as-code: none enforced; code lives in the TS source by default.
- n8n-evol-I: **strongest of the three.** Code (JS/Py), prompts, schemas, HTML, datasets all in their own files; `validate.py` rejects inlined code; auto-tidy hook re-extracts on every save. This is a deliberate discipline that neither peer matches.

### 5. Multi-environment support

- SDK: out of scope.
- n8n-as-code: multi-instance push/pull; less prescriptive about env config layout; no documented dependency-tier promotion flow.
- n8n-evol-I: **first-class.** `n8n-config/<env>.yml` + `.env.<env>` per environment, `--env` flag on every helper, `bootstrap_env.py` provisions a new env, `deploy_all.py` rolls a whole env in tier order. Explicitly addresses n8n's documented credential-non-portability.

### 6. Atomic primitives (locking, rate-limit, error-handler patterns)

- SDK: none.
- n8n-as-code: none.
- n8n-evol-I: **unique.** Real Redis INCR-with-TTL `lock_acquisition` / `lock_release` workflow templates with wait-loop, fixed-window `rate_limit_check` template, `register_error_handler.py` for wiring `settings.errorWorkflow`. None of this is in the SDK or in n8n-as-code. It's also not something the SDK should add — these are operational concerns, not authoring.

### 7. Deploy mechanics

- SDK: produces JSON; no deploy. `code-to-json` / `json-to-code` CLI for serialization. You hand the result to n8n's REST API yourself.
- n8n-as-code: CLI (`@n8n-as-code/cli`) + IDE extension push/pull; v2 introduces an `n8n-manager` runtime under the hood.
- n8n-evol-I: Python helpers calling n8n's REST API directly; tier-ordered deploy via `deployment_order.yml`; explicit activation/deactivation helpers. No JS toolchain except for the SDK shim used in `tidy_workflow.py`.

### 8. Round-trip stability

- SDK: explicit goal — `parseWorkflowCode` (code→builder) and `generateWorkflowCode` (json→code) are first-class exports; the test tree includes `merge.test.ts`, `real-workflow.test.ts`, `deterministic-ids.test.ts`. **Best engineered round-trip of the three** because round-trip is its product.
- n8n-as-code: pull/push with **3-way merge** + conflict detection. Most sophisticated *user-facing* sync semantics.
- n8n-evol-I: `resync.py` / `dehydrate.py` re-extract live workflow back to template; round-trip discipline limited to env+uuid placeholders in tests, with js/py/html/txt/json paths exercised at runtime but not under test.

### 9. Validation

- SDK: `validateWorkflow`, `ValidationError`, `ValidationWarning`, `ValidationErrorCode`, `setSchemaBaseDirs`, plugin-extensible (`ValidatorPlugin`), and a recent feature *"Validate workflow-sdk output topology against mode (#29363)"* — validation is mode-aware (per-target n8n version). Strongest typed validation of the three.
- n8n-as-code: TS type-checking on decorators; ontology-driven property validation per the README.
- n8n-evol-I: `validate.py` enforces *segmentation* discipline (code-node → file reference → file exists → JS export trailer → paired test file required). Different shape — it's a hygiene checker, not a topology checker.

### 10. Observability / debug

- SDK: not its job — it builds JSON, doesn't introspect runs.
- n8n-as-code: agent-driven inspection via skills.
- n8n-evol-I: **unique** for execution-time diagnostics — `list_executions.py` (cursor pagination + tally), `inspect_execution.py` (`--include-data`, `--max-size-kb`), `dependency_graph.py` extracts call/error-handler/credential edges from templates + live.

### 11. Cloud function / serverless support (post-Pyodide)

- SDK: none.
- n8n-as-code: none.
- n8n-evol-I: **unique.** `add_cloud_function.py` scaffolds a Python function into a FastAPI service in `cloud-functions/`, auto-registers in router, ships `railpack.json` for Railway. Load-bearing for n8n Cloud users post-CVE-2025-68668 hardening (Cloud's Python sandbox no longer allows arbitrary library imports).

### 12. Prompt iteration

- SDK: provides prompt *assets* (`prompts/sdk-reference`, `prompts/node-guidance/parameter-guides`, `prompts/best-practices`, `prompts/node-selection`) but no iteration framework — these are static prompts shipped for downstream LLM consumers.
- n8n-as-code: none.
- n8n-evol-I: `iterate_prompt.py` runs DSPy `BootstrapFewShot` / `MIPROv2` against a workspace prompt + paired schema + dataset, writes optimized prompt back to disk. **Unique iteration loop, but its eval metric is shallow** (key-presence/truthy, per the prior internal review).

### 13. Agent ergonomics

- SDK: imports cleanly into any TS program; ships LLM-ready prompt strings as importable submodules. The official **`n8n-mcp` MCP server** wraps the SDK with `get_sdk_reference`, `search_nodes`, `get_node_types`, `validate_workflow`, `create_workflow_from_code`, `update_workflow` — making the SDK directly addressable from any MCP-aware agent. Most natively agent-shaped.
- n8n-as-code: broadest *distribution* — VS Code Marketplace, Open VSX, Claude Code marketplace, OpenClaw plugin, npm, dedicated docs site (n8nascode.dev). Markets itself explicitly as an "AI Skill" with embedded ontology to eliminate hallucination.
- n8n-evol-I: Skill mode + Claude Code plugin mode. No MCP server, no IDE extension, no marketplace presence beyond a GitHub clone. Designed for agent runtimes via skill markdowns rather than a native MCP server.

### 14. Audience

- SDK: **infrastructure consumers.** Tools building n8n workflows programmatically. n8n itself, n8n-mcp, n8n-evol-I (already), and any future builder. Asymmetric vs. the other two: it has no end-user audience, only a builder audience.
- n8n-as-code: **solo devs + small teams** in any major IDE who want their agent to actually *know* n8n. Distribution-led pitch.
- n8n-evol-I: **agency / consultancy / enterprise operator** running the same workflow set across multiple owned + tenant n8n instances; coding-agent-driven; cares about race conditions and 2 a.m. failures.

### 15. Honest tradeoffs (what each sacrifices)

- **SDK** sacrifices everything outside of authoring (no env, no deploy, no ops, no debug) to be a clean, typed construction library that n8n itself can ship. Also: TS-only, fair-code license.
- **n8n-as-code** sacrifices distributed-systems primitives, env-promotion structure, and serverless-function escape hatches for *agent grounding* + *IDE distribution*. Bets the value is in eliminating hallucinations and meeting devs where they already work.
- **n8n-evol-I** sacrifices type safety, multi-IDE distribution, and packaged node-schema knowledge for *operational primitives* the others don't have. Bets the value is in deploy/lock/debug/iterate, not in authoring fluency. Also accepts a JS-toolchain dependency for `@n8n/workflow-sdk` layout (pinned 0.10.2 at `helpers/package.json:1`, version constant at `helpers/tidy_workflow.py:23`, install path at `helpers/tidy_workflow.py:34`) sitting under a Python harness.

---

## Where each project loses

- **`n8n-evol-I` loses to `@n8n/workflow-sdk` on authoring fidelity.** Placeholder-substituted JSON templates are coarser than a typed builder backed by n8n's real schemas, an AST interpreter, and the same validation engine n8n's own AI builder uses. There is no equivalent in n8n-evol-I to `validateWorkflow` topology-mode checks. n8n-evol-I already concedes this — it imports the SDK for layout (`helpers/tidy_shim.mjs:3-4`). **Possible direction**: hydrate to SDK builder calls instead of raw JSON, then call `validateWorkflow` before deploy.
- **`n8n-evol-I` loses to `n8n-as-code` on distribution and agent grounding.** VS Code Marketplace + Open VSX + Claude Code marketplace + OpenClaw + npm vs. a single GitHub clone; an installable ontology of every node + property vs. no built-in schema knowledge.
- **`n8n-evol-I` loses to both on type safety.** Placeholder strings vs. TS types end-to-end.
- **`n8n-as-code` loses to `@n8n/workflow-sdk` on canonicality.** Its node knowledge is rebuilt against each n8n release ("knowledge base for n8n@2.18.5"). The official SDK ships from the same monorepo n8n itself ships from; it cannot drift.
- **`n8n-as-code` loses to `n8n-evol-I` on production-ops.** No Redis locking, no rate-limit primitive, no tier-ordered multi-env deploy, no DSPy iteration, no FastAPI cloud-function escape hatch (which is load-bearing for any n8n Cloud user wanting libraries Cloud's Python sandbox blocks).
- **`@n8n/workflow-sdk` loses to both peers on lifecycle scope.** It owns construction only. No env, no deploy, no resync, no debug, no locking, no rate-limit, no prompt iteration, no cloud-function. It is also TS-only (Python-shop teams must call out via a shim, exactly as n8n-evol-I does at `helpers/tidy_shim.mjs:3-4`), pre-1.0 (0.12.0-beta), and licensed under n8n's Sustainable Use License — fair-code, not OSI-MIT.
- **`@n8n/workflow-sdk` loses to `n8n-as-code` on agent integration breadth.** Its prompts ship as importable strings, but there is no IDE plugin or marketplace presence; you have to wire it up yourself (n8n-mcp does, but that's a separate package).

---

## Recommendation by audience

- **Solo indie / hacker** → `n8n-as-code`. Marketplace install + embedded ontology gets you productive in your IDE in minutes. Direct SDK use requires you to build the agent UX yourself; n8n-evol-I requires a Python toolchain and reading 50 markdown skills first.
- **Consultancy / agency running multiple clients** → `n8n-evol-I`. Per-env YAML + per-env `.env.<env>` + `bootstrap_env.py` + tiered `deploy_all.py` is the only one of the three with a real client-tenancy promotion story. Locking + rate-limit + error-handler matter when one workflow set runs across N tenants with different SLAs.
- **Enterprise n8n team building their own internal tooling** → start with `@n8n/workflow-sdk` (canonical, typed, n8n-blessed) for authoring; layer `n8n-evol-I`-style operational discipline (env config, dependency-tier deploy, locking, dependency graph) on top. None of the three alone covers enterprise needs.
- **Claude-Code / agent-driven development** → `@n8n/workflow-sdk` via the official `n8n-mcp` MCP server is the most directly addressable; `n8n-as-code` is the most plug-and-play across IDEs; `n8n-evol-I` is the most ops-savvy but Claude-Code-skill-mode-only.
- **Type-safety zealot** → `@n8n/workflow-sdk`. Closest peer is `n8n-as-code`; `n8n-evol-I` is JSON-with-placeholders only.
- **n8n Cloud user (post-Pyodide-removal)** → `n8n-evol-I`. Its `add_cloud_function.py` + FastAPI scaffold + Railway config is the only one of the three that addresses the Cloud-only Python-import-restriction gap.

---

## Methodology footer

**`n8n-evol-I`** — read first-hand from the repository checkout: `README.md`, `docs/independent-review-2026-04-30.md`, `helpers/package.json`, `helpers/tidy_workflow.py`, `helpers/tidy_shim.mjs`, plus directory listings of `helpers/`, `skills/`, `primitives/`, `meta-evals/`. The prior internal review's first-hand evidence (cited at file:line) backs claims that I did not re-verify in this pass.

**`@n8n/workflow-sdk`** — read source files at `n8n-io/n8n` monorepo path `packages/@n8n/workflow-sdk/`, sibling to `packages/workflow` and 40+ other `@n8n/*` packages. Files inspected: `package.json`, `README.md`, `src/index.ts`, `src/workflow-builder.ts`. **Cross-confirmed** by `grep` against n8n-evol-I's own source: `helpers/package.json:1` pins `"@n8n/workflow-sdk":"0.10.2"`; `helpers/tidy_shim.mjs:3-4` does `import sdk from '@n8n/workflow-sdk'; const { layoutWorkflowJSON } = sdk;`; `helpers/tidy_workflow.py:11` documents the SDK pin in the module docstring; `helpers/tidy_workflow.py:23` declares `_SDK_VERSION = "0.10.2"`; `helpers/tidy_workflow.py:34,41` install `@n8n/workflow-sdk@{_SDK_VERSION}` into `helpers/node_modules/@n8n/workflow-sdk`. n8n-evol-I is a literal consumer of the SDK.

**`n8n-as-code`** — read current `README.md` from the project's main branch. Architecture details (decorator-based authoring, 3-way merge sync, 537-node schema package, 7,700-template index) carried forward from prior internal review's code-level investigation; current README confirms the rebrand toward "installable ontology" / multi-IDE distribution but the underlying TS-builder + push/pull mechanics remain.

**`n8n-mcp`** detail (called out for the agent-ergonomics axis) — confirmed via the MCP server's own self-described instructions: `get_sdk_reference`, `search_nodes`, `get_node_types`, `validate_workflow`, `create_workflow_from_code`, `update_workflow`. This is the official MCP wrapper around `@n8n/workflow-sdk`.

No live-signals (stars, forks, last-push, open-issues) collected for this revision — the comparison is intentionally architectural and will not date as quickly.

— *comparator*, n8n-evol-audit team, 2026-05-02
