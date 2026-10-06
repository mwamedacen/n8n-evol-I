# N8N EVOL I

Make n8n workflows easier for coding agents to read and edit. Templates replace bulky embedded code, prompts, and schemas with file references, helping agents work within their context windows.

![Agents edit shared project files. Dev and production each have a separate local workspace and n8n deployment. Deploy sends changes to n8n; review and resync bring changes back.](docs/assets/project-flow.svg)

- **Review focused changes.** Edit reusable code, prompts, schemas, and assets in their own files. Agents can load just what a task needs.
- **Keep environments separate.** Each environment has one workspace and its own n8n deployment, credentials, workflow IDs, builds, and sync history.
- **Use your existing project.** Adoption preserves files and instructions. Choose your layout, language, framework, hosting, and test commands.

Reusable skills and workflow primitives help with deployment, error handling, locks, queues, and rate limits. The design borrows [Twelve-Factor principles](docs/design.md#twelve-factor-influences): separate configuration and dependencies, distinguish build from execution, and keep environments comparable.

Deploy to local n8n or n8n Cloud, then bring n8n edits back into your files. [See actual verification results and remaining limits](docs/testing.md).

## Install

Choose your agent. You need Git and Python 3.11+; helper dependencies are set up automatically on first use.

### Claude Code

Run inside Claude Code:

```text
/plugin marketplace add mwamedacen/n8n-evol-I
/plugin install n8n-evol-I@n8n-evol
```

### Codex

Run in your terminal:

```bash
codex plugin marketplace add mwamedacen/n8n-evol-I
codex plugin add n8n-evol-I@n8n-evol
```

### Hermes

Run in your terminal:

```bash
hermes plugins install mwamedacen/n8n-evol-I --enable
```

Start a new agent session after installation. [Other agents, local checkouts, and optional dependencies](install.md)

## Start

Open your project folder and ask your agent:

**New project:** “Use the n8n skill to create a project here and connect my development deployment.”

**Existing project:** “Use the n8n skill to adopt this project. Preserve its files and instructions, and use its existing conventions.”

Have your local n8n or n8n Cloud URL and API key ready. Enter the key through the setup helper's hidden prompt. Each environment connects to a separate deployment. [Environment setup](docs/environments.md)

## Daily work

Work from the project folder or any subdirectory. For example:

- “Create a webhook workflow in dev that validates incoming orders.”
- “Preview the changes, deploy to dev, and run it with a sample order.”
- “I edited the workflow in n8n. Review and resync those changes into the project.”

Deployment builds current source. Resync checks local and remote changes against a saved baseline; conflicting edits stop for review. [Deployment and resync](docs/sync.md)

## More

- [All skills and capabilities](docs/capabilities.md): debugging, locks, queues, rate limits, credentials, variables, cloud functions, prompt optimization, integrations, and tests.
- [Adoption and migration](docs/migration.md): custom paths, compatibility, and recovery.
- [Architecture and design decisions](docs/design.md): boundaries, Twelve-Factor influences, gaps, and migration stages.
- [Changelog](CHANGELOG.md) · [MIT license](LICENSE)
