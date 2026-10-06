---
name: pattern-llm-providers
description: LLM provider notes — OpenRouter via openAiApi, Anthropic token-counting quirks.
user-invocable: false
---

# Pattern: LLM providers

Paths and examples use bundled defaults; resolve actual paths and environment storage through [project configuration](../../configuration.md).

## OpenRouter via `openAiApi`

OpenRouter's REST API is OpenAI-API-compatible. n8n's `openAiApi` credential type, OpenAI node, and AI Agent / Chat Model nodes all consume OpenRouter transparently — you just point the credential's `Base URL` at OpenRouter.

To set up an OpenRouter credential:

1. Set `OPENROUTER_API_KEY=...` in the selected environment's private `.env` (legacy: `<config>/.env.<env>`).
2. Run `manage-credentials.md` (Path A):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/helpers/manage_credentials.py create \
  --env dev --key openrouter \
  --type openAiApi \
  --name "OpenRouter (Dev)" \
  --env-vars apiKey=OPENROUTER_API_KEY,url=OPENROUTER_BASE_URL
```

(set `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1` in the same private environment file).

3. The credential's `id`+`name` is recorded under `credentials.openrouter` in the selected environment's private bindings (legacy: environment YAML).

For the actual setup walkthrough, see [`skills/manage-credentials.md`](../manage-credentials.md).

## OpenRouter strict-mode

When using OpenRouter with structured outputs (response_format: json_schema), some models return wrapped responses (with `<output>` tags or extra prose). Test with the actual model you'll deploy. The harness's `iterate-prompt.md` workflow can help measure response quality.

## Anthropic token counting

Anthropic's tokenizer is different from OpenAI's; a prompt that fits in OpenAI's 128k context might exceed Claude's window. When using Anthropic in n8n via the `anthropicApi` credential type, watch for `400 input too long` errors and chunk inputs accordingly.

## See also

- [`skills/manage-credentials.md`](../manage-credentials.md) for credential setup flow.
- `skills/patterns/prompt-and-schema-conventions.md` for prompt + schema file naming.
