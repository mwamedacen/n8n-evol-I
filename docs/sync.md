# Deploy and resynchronize

Reusable templates are shared project source. Every environment has its own bindings, builds and durable synchronization baseline.

## Deploy

`deploy.py --env <env> --workflow-key <key> --preview` builds current source, checks the selected target and reports the intended activation. Use the same command without `--preview` to deploy; add `--activate` when publication is intended.

Deployment refuses remote drift since the last baseline. An existing populated remote workflow without a baseline must be imported/reviewed first. The helper retains a private remote snapshot and records the deployed source, source files, and returned definition. It always rebuilds and validates the actual outgoing payload.

New-format projects do not request automatic activation unless configured. Updating an already active workflow can publish on some n8n versions: a draft-only update is refused until the workflow is deactivated, or publication is explicitly requested. There is no promise of draft isolation across unknown n8n versions.

Bulk deployment preflights every workflow and resolves dependencies before mutation. A selected workflow without a minted ID stops the whole plan before any deployment; use environment bootstrap to mint its draft ID first. Drafts belonging only to other environments are excluded. A multi-workflow rollout is not transactional; failures report partial completion, and each successful workflow retains its own baseline.

## Execute

`run.py` injects a unique request header and finds that nonce in the saved execution data. It reports the matched execution ID and terminal status. Enable execution-data retention for verification; a successful HTTP response or unrelated recent execution is insufficient. Error-handler dispatch has separate correlation limits and must be independently verified for a production acceptance test.

## Resync

Use `resync.py ... --preview`, then `resync.py ...` to apply. `resync_all.py` stages every workflow before writing shared source.

| Local since baseline | Remote since baseline | Result |
|---|---|---|
| Unchanged | Changed | Apply remote changes |
| Changed | Unchanged | Preserve local edits |
| Same change | Same change | Keep the shared result |
| Different changes | Different changes | Stop with a conflict |

The implementation conservatively treats competing template edits as a conflict; it does not claim a general automatic merge. Environment references and node identities are restored from provenance. Changed standalone prompts/assets and marked code bodies become source-file updates. Removed markers, changed environment bindings, unknown mappings, or ambiguous composite asset edits stop for review instead of dropping content.

Raw incoming snapshots are private. First imports never overwrite an existing local definition without a reviewed baseline. Unknown server metadata stays in the snapshot; not every n8n field is an editable template field.

A project operation lock serializes local deploy/resync operations, including changes shared between environments. The helper checks the remote again before writing, but n8n's public API does not provide a portable conditional-write contract. Avoid simultaneous UI editing during deployment; a small remote race window remains.
