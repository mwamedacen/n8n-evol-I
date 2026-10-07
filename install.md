# Install

Install through your agent's plugin manager, then ask it to create a new n8n project or adopt an existing one. You need Git and Python 3.11+; helper dependencies are prepared automatically in a machine cache. Node.js is optional for JavaScript tests and SDK layout. [Tested runtimes and targets](docs/testing.md)

## Claude Code

Run inside Claude Code:

```text
/plugin marketplace add mwamedacen/n8n-evol-I
/plugin install n8n-evol-I@n8n-evol
```

Restart Claude Code. The plugin exposes an n8n router, ten `/n8n-evol-I:<name>` commands (`deploy`, `deploy_all`, `resync`, `resync_all`, `tidyup`, `debug`, `run`, `doctor`, `validate`, `test`) and the canvas-tidy hook.

## Codex

```bash
codex plugin marketplace add mwamedacen/n8n-evol-I
codex plugin add n8n-evol-I@n8n-evol
```

Start a new Codex session and use the n8n skill. This repository supplies its own marketplace; it is not an official marketplace listing.

## Hermes

```bash
hermes plugins install mwamedacen/n8n-evol-I --enable
```

Review the installer's trust prompt, then start a new Hermes session. The plugin registers `n8n-evol-I:n8n` and a short routing hint. It runs helpers in the toolkit's own cached Python environment, without adding toolkit dependencies to Hermes' environment.

## First project

Ask your agent: “Use the n8n skill to create `./my-project`” or “Adopt this existing project and preserve its files and conventions.” Connect each environment to its own local or Cloud n8n deployment. Enter its API key through the helper's hidden prompt; CI can pipe a secret manager's output to `--api-key-stdin`. Keep keys out of command arguments, chat and Git. [Environment setup](docs/environments.md) · [Adoption and migration](docs/migration.md)

## Local checkout and other agents

For an unpublished checkout, Claude Code supports `claude --plugin-dir /absolute/path/to/n8n-evol-I`; Codex accepts that path instead of the repository name in `plugin marketplace add`. Hermes installs Git repositories, including a local `file://` Git URL. These native flows were checked with isolated runtime profiles; remote installation requires the changes to be published.

Other agents can read the toolkit's root `SKILL.md`:

```bash
git clone https://github.com/mwamedacen/n8n-evol-I.git ~/.local/share/n8n-evol-I
TOOLKIT=~/.local/share/n8n-evol-I
"$TOOLKIT/scripts/python" "$TOOLKIT/helpers/init.py" --project ./my-project
```

Use the same launcher for other helpers. It reuses a compatible interpreter or creates a dependency environment in the machine cache; it does not write into the toolkit or project. `N8N_EVOL_PYTHON` selects an already prepared Python interpreter; `N8N_EVOL_CACHE_HOME` selects the cache directory. Manual venv installation with `python -m pip install /path/to/toolkit` remains supported.

Native installation and the shell launcher were verified on macOS. The launcher requires a POSIX shell and `python3`; native Windows installation is unverified.

The runtime-neutral `build-skill-dist.sh` output keeps the root skill, all original supporting skills, helpers and primitives. Native plugin metadata and hooks are excluded; use the checkout for native plugin installation. User instructions take priority, then existing project conventions, then bundled defaults.

## Optional capabilities and updates

DSPy optimization requires its optional dependencies and a chosen model/provider. JavaScript tests use the project's runner or the bundled Node convention. SDK layout uses a machine cache with a Python fallback. Functions can use the Python/FastAPI preset or a custom scaffold and host.

Update through your plugin manager, or update a manual checkout. Tool updates do not migrate project data. Back up environment state, review migration notes, run doctor and a relevant live smoke test before updating production.
