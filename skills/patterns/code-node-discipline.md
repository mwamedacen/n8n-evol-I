---
name: pattern-code-node-discipline
description: Externalized Code-node logic with project-selected tests and module conventions; bundled pure-function defaults remain available.
user-invocable: false
---

# Pattern: Code-node discipline

Keep Code-node logic in source files, referenced by placeholders. The bundled default uses pure functions under `n8n-functions/{js,py}/` and paired tests under `n8n-functions-tests/`; configured paths and the project test contract take precedence. The Code-node body keeps only the placeholder + thin n8n glue (`$input` / `items` / `return [{json:...}]`).

`validate.py` checks source existence and placeholders for any `n8n-nodes-base.code` node in a template. Without a configured or detected project test runner, it also enforces the bundled purity, CommonJS trailer and paired-test conventions. Inlined Code-node logic is rejected. The deprecated `n8n-nodes-base.function` node type is forbidden entirely.

## Why

- **Testable**: the pure function takes plain values and returns plain values, so `node --test` (JS) or `pytest` (Py) can exercise it without an n8n runtime.
- **Re-usable**: the same function file can be referenced from multiple workflows.
- **Reviewable**: diffs show real logic changes, not whitespace inside JSON-escaped strings.
- **Round-trippable**: `js_resolver` / `py_resolver` wrap the injected content in round-trip markers (`#:js:` for JS, `MATCH:py:` for Python; legacy `DEHYDRATE:` markers also accepted on read); `resync.py` collapses those markers back to placeholders so accepted UI edits update the external source file while templates keep their placeholders. Concurrent edits stop for conflict resolution.

## Layout

```
<workspace>/
├── n8n-functions/
│   ├── js/<camelCaseName>.js
│   └── py/<snake_case_name>.py
├── n8n-functions-tests/
│   ├── conftest.py            (scaffolded by init.py — adds n8n-functions/py to sys.path)
│   ├── <camelCaseName>.test.js
│   └── test_<snake_case_name>.py
└── n8n-workflows-template/<key>.template.json
```

Naming:
- **JS**: `camelCase` for the function name, file matches: `calculateStatsByCategory.js` ↔ `calculateStatsByCategory.test.js`.
- **Python**: `snake_case` for the function name, file matches: `calculate_stats_by_category.py` ↔ `test_calculate_stats_by_category.py`.

The bundled convention requires paired test files. Map `paths.functions` and `paths.function_tests` in `n8n-project.yml` for an existing layout. `commands.test.n8n` or an existing project runner owns its own test naming and module rules; see [project configuration](../../configuration.md).

### Path resolution

`{{@js:...}}`, `{{@py:...}}`, `{{@txt:...}}`, `{{@md:...}}`, `{{@json:...}}`, `{{@html:...}}` placeholder paths are **relative to the workspace root** (the directory containing `n8n-config/`, `n8n-functions/`, `cloud-functions/`, …). They are NOT relative to a default `n8n-functions/js/` prefix.

So `{{@js:n8n-functions/js/aggregate.js}}` resolves to `<workspace>/n8n-functions/js/aggregate.js`. Writing `{{@js:aggregate.js}}` would look for `<workspace>/aggregate.js` — usually a mistake. The validator's `referenced file not found` error reports the full resolved path, so include the actual project-relative source path, using the configured layout.

---

## JavaScript example

### Pure function — `n8n-functions/js/calculateStatsByCategory.js`

```js
function calculateStatsByCategory(articles) {
  const stats = {};
  for (const article of articles) {
    const cat = article.category || "uncategorized";
    stats[cat] = (stats[cat] || 0) + 1;
  }
  return stats;
}
if (typeof module !== "undefined") module.exports = { calculateStatsByCategory };
```

The `if (typeof module !== "undefined")` trailer:
- **No-op in n8n's vm sandbox** — `module` is undefined, the condition is false, the line is skipped.
- **Active under `node --test`** — `module` is defined, the function is exported, the test can `require` it.

The trailer is required only by the bundled CommonJS test convention. A project-selected runner may use another module/test contract. Ensure the embedded source remains executable by the selected n8n Code-node runtime; hydration does not transpile ESM or TypeScript.

### Code-node body (before hydrate)

`parameters.jsCode`:

```
{{@js:n8n-functions/js/calculateStatsByCategory.js}}

const body = $input.body || {};
const articles = Array.isArray(body.articles) ? body.articles : [];
const stats = calculateStatsByCategory(articles);

try {
  return { json: { stats } };
} catch(e) {
  return { error: e.message };
}
```

### Code-node body (after hydrate)

```
/* #:js:n8n-functions/js/calculateStatsByCategory.js */
function calculateStatsByCategory(articles) {
  const stats = {};
  for (const article of articles) {
    const cat = article.category || "uncategorized";
    stats[cat] = (stats[cat] || 0) + 1;
  }
  return stats;
}
if (typeof module !== "undefined") module.exports = { calculateStatsByCategory };
/* /#:js:n8n-functions/js/calculateStatsByCategory.js */

const body = $input.body || {};
const articles = Array.isArray(body.articles) ? body.articles : [];
const stats = calculateStatsByCategory(articles);

try {
  return { json: { stats } };
} catch(e) {
  return { error: e.message };
}
```

### Test — `n8n-functions-tests/calculateStatsByCategory.test.js`

```js
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { calculateStatsByCategory } = require("../n8n-functions/js/calculateStatsByCategory.js");

test("groups articles by category", () => {
  const result = calculateStatsByCategory([
    { category: "sports" }, { category: "sports" }, { category: "tech" }
  ]);
  assert.deepEqual(result, { sports: 2, tech: 1 });
});
```

This example uses CommonJS. Preserve an existing project's module convention and test runner instead of changing its `package.json` to match this example.

---

## Python example

### Pure function — `n8n-functions/py/calculate_stats_by_category.py`

```python
def calculate_stats_by_category(articles):
    stats = {}
    for article in articles:
        cat = article.get("category", "uncategorized")
        stats[cat] = stats.get(cat, 0) + 1
    return stats
```

No guards, no exports — Python files are always importable as modules.

### Code-node body (before hydrate)

`parameters.pythonCode` (with `parameters.language == "python"`):

```
{{@py:n8n-functions/py/calculate_stats_by_category.py}}

body = items[0]["json"]
articles = body.get("articles", [])
stats = calculate_stats_by_category(articles)
return [{"json": {"stats": stats}}]
```

### Code-node body (after hydrate)

```
# MATCH:py:n8n-functions/py/calculate_stats_by_category.py
def calculate_stats_by_category(articles):
    stats = {}
    for article in articles:
        cat = article.get("category", "uncategorized")
        stats[cat] = stats.get(cat, 0) + 1
    return stats
# /MATCH:py:n8n-functions/py/calculate_stats_by_category.py

body = items[0]["json"]
articles = body.get("articles", [])
stats = calculate_stats_by_category(articles)
return [{"json": {"stats": stats}}]
```

### Test — `n8n-functions-tests/test_calculate_stats_by_category.py`

```python
from calculate_stats_by_category import calculate_stats_by_category

def test_groups_by_category():
    result = calculate_stats_by_category([
        {"category": "sports"}, {"category": "sports"}, {"category": "tech"}
    ])
    assert result == {"sports": 2, "tech": 1}
```

For a fresh default project, `init.py` can scaffold the convenience imports below. Adoption and existing runner configurations keep their own setup:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "n8n-functions" / "py"))
```

The hyphenated dir name `n8n-functions` cannot be imported as a Python package (hyphens are forbidden in module names), so pytest's `conftest.py` is where the `sys.path` insert lives.

The Python source file must **not** contain any of the substrings `# MATCH:py:`, `# /MATCH:py:`, `# DEHYDRATE:py:`, or `# /DEHYDRATE:py:` — those would corrupt the round-trip. `py_resolver.resolve()` raises `ValueError` on encounter.

---

## Structure rules

Under the bundled default contract, function files contain function declarations plus the conditional JS export trailer. These style checks yield to a configured or detected project test contract.

**JavaScript** — at brace-depth 0, the only allowed line shapes are:
- Blank lines.
- Line comments (`//`) and block comments (`/* */`, including JSDoc above a function).
- `function <name>(...)` and `async function <name>(...)` declarations (with the body indented inside `{ ... }`).
- The conditional export trailer: `if (typeof module !== "undefined") module.exports = { ... };`.
- Bare `module.exports = { ... };` / `exports.<name> = ...;` lines (allowed but not required if the trailer wraps them).

Anything else at depth 0 — `const`/`let`/`var`, top-level `return`, top-level `for`/`if`/`while`, function calls, bare expressions — is a violation.

**Python** — at column 0, the only allowed line shapes are:
- Blank lines.
- Comment lines (`#`).
- A module-level docstring (a triple-quoted string as the first non-blank, non-comment line). Python convention; allowed.
- `import ...` and `from ... import ...`.
- `def <name>(...)` and `async def <name>(...)` (with the body indented).

Anything else at column 0 — assignments, `for`/`if`/`while` blocks, top-level function calls, bare strings *anywhere else* in the file — is a violation.

The error message includes the offending line number and an excerpt:

```
node 'Code': n8n-functions/js/aggregate.js contains top-level code outside function declarations
(line 1: 'const articles = items[0].json.body || [];'). Pure-function files must declare functions
only — n8n-glue belongs in the Code-node body, not the file.
```

The structural check makes "pure functions only" enforceable, not aspirational. An agent who tries to satisfy the trailer + test rules by pasting the n8n-glue into the function file will fail this check on the first non-`function` line.

---

## Validator checks (template only)

`validate.py` checks Code-node structure and source references in templates. The trailer, purity and paired-filename rows below apply only to the bundled test contract. Failures are errors. Built JSON skips placeholder/source-style checks because hydration has already replaced placeholders.

| Rule | Error |
|---|---|
| Node type is `n8n-nodes-base.function` | Deprecated; switch to `n8n-nodes-base.code`. |
| `jsCode` (or `pythonCode` when `language == "python"`) is empty | Cannot validate without code. |
| No `{{@js:...}}` (or `{{@py:...}}`) placeholder in the code field | Inlined logic is rejected — extract to `n8n-functions/{js,py}/`. |
| Placeholder points to a file that doesn't exist | Bad path — fix or remove. |
| JS file is missing `if (typeof module !== "undefined")` trailer | Tests cannot `require` the function. |
| Function file contains top-level code outside function declarations | The file must be a pure-function library; n8n-glue belongs in the Code-node body. See **Structure rules** above. |
| No paired test file at `n8n-functions-tests/<stem>.test.js` (JS) or `test_<stem>.py` (Py) | Pure function ships untested. |

Keep source externalization even for small Code nodes. Customize the test/module contract through project configuration, rather than marking user code as a bundled primitive.

## Running the tests

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/test_functions.py --target n8n
```

Runs `commands.test.n8n` first, otherwise an existing project runner. With neither configured, runs `node --test` over `*.test.js` and pytest over `test_*.py` in the configured function-test directory.

For the bundled Python test path, pytest must be installed in the project's chosen environment. The runner reports the failure cleanly via subprocess exit code.

---

## Primitive exemption

Harness-maintained primitive Code nodes (lock acquisition, lock release, rate-limit check, error-handler cleanup) begin their body with `// @n8n-evol-I:primitive`. This marker suppresses the placeholder and purity checks in `validate.py` — the validator's `_validate_code_node` short-circuits with no errors as soon as it sees the marker as the first non-whitespace characters of the code field.

Only primitives under `primitives/workflows/` should use this marker. User Code nodes must follow their project's source and testing contract; using the marker in a user workflow will silently bypass validation, defeating the whole point of the rule.

The marker exists because the primitive bodies legitimately use `this.helpers.redis` and have top-level statements (SETNX with TTL, INCR + EXPIRE, owner-pointer writes) — they're not pure functions and can't be written as such without losing atomicity. The marker is the explicit, narrow opt-out for this case.
