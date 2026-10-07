<img width="1376" height="768" alt="n8n_evol_I_hero" src="docs/assets/n8n_evol_I_hero.png" />

# N8N EVOL I

Make n8n workflows easier for coding agents to read and edit. Templates replace bulky embedded code, prompts, and schemas with file references, helping agents work within their context windows.

- **Review focused changes.** Edit reusable code, prompts, schemas, and assets in their own files. Agents can load just what a task needs.
- **Multi-environment support.** Reuse the same workflow templates across environments, with YAML settings for local n8n or n8n Cloud.
- **Use your existing project.** Adoption preserves files and instructions. Choose your layout, language, framework, hosting, and test commands.

Reusable skills and workflow primitives help with deployment, error handling, locks, queues, and rate limits. The design borrows [Twelve-Factor principles](docs/design.md#twelve-factor-influences): separate configuration and dependencies, distinguish build from execution, and keep environments comparable.

Deploy to local n8n or n8n Cloud, then bring n8n edits back into your files. [See actual verification results and remaining limits](docs/testing.md).

## How it works

Agents edit templates, code, prompts, and schemas, and reuse primitives. YAML configuration feeds build-time interpolation. Deployment is dependency-first, activation follows selection or recorded policy, and review and resync bring edits back.

![A coding agent follows shipped skills to edit compact templates, code, prompts, and schemas, and to reuse primitives. YAML configuration feeds build-time interpolation. An illustrative graph shows a main workflow calling sub-workflows that share a primitive; deployment is dependency-first, and activation follows selection or recorded policy. The result goes to local n8n or n8n Cloud. Review and resync bring edits back.](docs/assets/project-flow.svg)

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

### Pi

Load the skill from a local checkout. This is not a plugin install.

```bash
git clone https://github.com/mwamedacen/n8n-evol-I.git ~/.local/share/n8n-evol-I
cd /path/to/your-project
pi --skill ~/.local/share/n8n-evol-I/skills/n8n
```

Then ask: “Use the n8n skill to adopt this project. Preserve its files and instructions.”

### OpenCode

Add this path to an existing `opencode.json`. Do not replace other settings. If `skills.paths` already exists, append the path.

```bash
git clone https://github.com/mwamedacen/n8n-evol-I.git ~/.local/share/n8n-evol-I
```

```json
{
  "skills": {
    "paths": ["~/.local/share/n8n-evol-I/skills"]
  }
}
```

Use that home path or an absolute path. A config-relative path is not reliable from a subdirectory. Then run `opencode` in your project and ask: “Use the n8n skill to adopt this project. Preserve its files and instructions.”

Pi and OpenCode load the skill only. They do not gain Claude plugin commands or hooks.

### Muse, GrokBot, and Dots

Paste this prompt:

```text
Install https://github.com/mwamedacen/n8n-evol-I so you can build, monitor, and debug my n8n workflows efficiently. Follow the repository's installation instructions and use its skills, workflow templates, and reusable primitives.
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
- “Monitor workflow errors and notify me when something needs attention.”
- “A run failed. Inspect that execution and tell me what needs fixing.”

These are example prompts. The agent can inspect failed executions and report back in the session. This is not a built-in unattended alert or notification channel.

Deployment builds current source. Resync checks local and remote changes against a saved baseline; conflicting edits stop for review. [Deployment and resync](docs/sync.md)

## More

- [All skills and capabilities](docs/capabilities.md): debugging, locks, queues, rate limits, credentials, variables, cloud functions, prompt optimization, integrations, and tests.
- [Adoption and migration](docs/migration.md): custom paths, compatibility, and recovery.
- [Architecture and design decisions](docs/design.md): boundaries, Twelve-Factor influences, gaps, and migration stages.
- [Changelog](CHANGELOG.md) · [MIT license](LICENSE)
