# Environments

One environment means one local workspace bound to one n8n deployment. Use distinct deployments for development, staging, and production. Both local HTTP URLs and n8n Cloud HTTPS URLs work through the same public API client.

```text
project/
  n8n-project.yml
  n8n-workflows-template/          reusable definitions
  environments/dev/
    workspace.yml                 target and non-secret config
    .env                          private secrets
    bindings.json                 private remote IDs and credential bindings
    state/                        private baselines, snapshots and receipts
    build/                        generated payloads; safe to regenerate
```

The project manifest maps source paths and environment workspace locations. Paths are relative to that manifest. Existing legacy `n8n-config/<env>.yml` projects still work. `bootstrap_env.py --migrate` copies a selected legacy environment into the new format and retains its originals.

## Connect

Run `bootstrap_env.py --workspace <project> --env dev --instance <url>` and enter the key at the hidden prompt, or supply `--api-key-stdin`. Environment files have restricted permissions. The helper checks the target before writing configuration.

API keys come only from the selected environment's `.env` or explicitly scoped process variables. `N8N_ENV_DEV_API_KEY` overrides dev's key; `N8N_ENV_DEV__NAME` overrides another value. A generic ambient `N8N_API_KEY` is accepted only as initial bootstrap input, never as a fallback for an already selected environment. Names that collide under scoped-variable normalization must not coexist.

`bindings.json` stores workflow and credential IDs separately from source. Source references use `{{@env:workflows.<key>.id}}` and `{{@env:credentials.<key>.id}}`. Do not copy live IDs between deployments. `manage_credentials.py` creates or links the environment's credentials; secret values remain in n8n or the private secret source.

A target URL or remote project change requires `--rebind` and explicit new credentials. Rebinding archives the old configuration, secrets, bindings, state and builds instead of reusing another deployment's IDs. Keep this private backup until the new target is verified.

## Runtime isolation

Separate local deployments need separate databases/volumes and encryption keys. n8n Cloud instances have their own deployment URLs and API credentials. Scope external backing resources as well: use separate Redis/queue namespaces, databases, buckets and webhook consumers where appropriate. A workflow-name suffix does not provide isolation.

An n8n UI project is a remote ownership scope, not an environment. If configured, its ID is part of the target binding. Existing resources are never moved between projects automatically.

Build output is disposable. Bindings and synchronization history are durable state: back them up privately. If lost, attach verified IDs and re-establish a baseline; do not blindly create replacement workflows. Generated artifacts and private state have local ignore rules; adoption does not rewrite existing root `.gitignore` files.
