---
name: pattern-multi-env-uuid-collision
description: Stable node identities within a workflow and distinct UUIDs across environments.
user-invocable: false
---

# Pattern: multi-env UUID collision

Node IDs identify nodes during deployment and resynchronization. Keep those identities stable when rebuilding the same workflow, and keep separate environments from sharing generated identities.

## Solution

Templates use the `{{@uuid:<identifier>}}` placeholder. Hydration resolves it deterministically within the workflow's environment namespace. Repeated identifiers resolve consistently:

- `dev` hydration produces UUID `aaa-...`
- `prod` hydration produces UUID `bbb-...`
- `dev` re-hydration retains UUID `aaa-...`

The synchronization baseline retains the workflow's namespace across adoption and migration. Explicitly rebinding an environment resets its target-specific state. Calling the low-level resolver without a namespace retains its legacy fresh-UUID behavior; normal hydration supplies a namespace.

## When you add a node

Use `{{@uuid:<some-distinct-name>}}` for the new node's `id` field. The identifier just has to be unique within the template (e.g. `webhook-2`, `set-after-merge`).

## Resync preserves UUIDs

With a synchronization baseline, resync matches nodes by their deployed IDs, preserving placeholders across remote renames or reordering. First imports without a baseline have less provenance and require review; standalone dehydration can use existing node names to restore known placeholders.

## Position recalculation when adding mid-flow

When inserting nodes mid-flow (e.g. via `add-lock-to-workflow.md`), shift downstream nodes 220px right per inserted node so the canvas stays legible. See `skills/patterns/position-recalculation.md`.
