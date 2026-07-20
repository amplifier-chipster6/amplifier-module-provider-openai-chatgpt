# Amplifier ChatGPT Subscription Provider Module

ChatGPT subscription auth provider for [Amplifier](https://github.com/microsoft/amplifier) -- uses raw HTTP + manual SSE against the ChatGPT backend API (`chatgpt.com/backend-api/codex/responses`).

## Prerequisites

- Python 3.11+
- [UV](https://docs.astral.sh/uv/) package manager
- A ChatGPT Plus/Pro/Team subscription with device code auth enabled in ChatGPT security settings

## Purpose

Connects Amplifier to the ChatGPT backend API using OAuth device code authentication. This is a separate module from `provider-openai` because the ChatGPT backend is a distinct, undocumented API surface that rejects many standard OpenAI API parameters and requires raw HTTP + manual SSE parsing (the OpenAI Python SDK's streaming accumulator does not work against it).

## Contract

| Field | Value |
|-------|-------|
| Module Type | Provider |
| Mount Point | `providers` |
| Entry Point | `amplifier_module_provider_openai_chatgpt:mount` |

## Configuration

```toml
[providers.provider-openai-chatgpt]
default_model = "gpt-5.6-sol"
```

### All Config Options

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_model` | str | `"gpt-5.6-sol"` | Model to use for inference |
| `raw` | bool | `false` | Include full request/response payloads in `llm:request`/`llm:response` hook events (for debugging) |
| `login_on_mount` | bool | `true` | Trigger interactive device code login if tokens are absent or expired. Set `false` for non-interactive environments. |
| `token_file_path` | str | `~/.amplifier/openai-chatgpt-oauth.json` | Path to the OAuth token JSON file |
| `timeout` | float | `300.0` | HTTP timeout in seconds for streaming requests |
| `models_cache_ttl` | float | `3600` | How long (seconds) to cache the live model catalog before re-fetching |

### Authentication

On first use, the provider initiates an OAuth device code flow:

1. Displays a verification URL (`https://auth.openai.com/codex/device`) and a code in the terminal
2. You open the URL in a browser and enter the code
3. Tokens are cached to `~/.amplifier/openai-chatgpt-oauth.json` for subsequent use

Tokens auto-refresh silently when they expire. If the refresh token itself expires, the device code flow runs again.

Requires "Sign in with device code" to be enabled in your ChatGPT account security settings (Settings > Security).

Works in SSH/headless sessions -- the device code flow only requires a browser on any device, not the machine running Amplifier.

## Features

- OAuth device-code authentication with bounded, protocol-aware polling
- Dynamic account-scoped model catalog with a safe retryable fallback
- [Documented GPT-5.6 family](https://developers.openai.com/api/docs/guides/model-guidance?model=gpt-5.6):
  `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`
- Official [Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol),
  [Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra), and
  [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) metadata:
  1,050,000-token context and 128,000-token maximum output; the family guide
  documents reasoning `none`/`low`/`medium`/`high`/`xhigh`/`max`
- Raw httpx SSE streaming, tool calling, and explicit request-model overrides

Public model documentation does not establish what any particular ChatGPT
account can use. At runtime, the provider uses the authenticated backend catalog
only to resolve available candidates; it does not need to collect or document a
user's subscription plan. The fallback does not claim `fast` support, and a
synthetic `-fast` compatibility ID is emitted only when the live catalog reports
that tier. If GPT-5.6 is absent during staged rollout, routing skips those exact
candidates and uses a model exposed by the live catalog. It never invents a
synthetic GPT-5.6 Codex identifier; coding first matches catalog-provided Codex
models, then Terra and Sol.

## Local Development

```bash
# Clone
git clone https://github.com/microsoft/amplifier-module-provider-openai-chatgpt.git
cd amplifier-module-provider-openai-chatgpt

# Install deps (including dev group: amplifier-core, pytest, ruff)
uv sync

# Run tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_sse.py -v

# Lint and format check
uv run ruff check .
uv run ruff format --check .
```

### Testing with Amplifier

Register the module, install it, and add it through the standard provider management flow:

```bash
# 1. Register the module source
amplifier module add provider-openai-chatgpt \
  --source /path/to/amplifier-module-provider-openai-chatgpt

# 2. Install the provider
amplifier provider install openai-chatgpt --force

# 3. Add and configure via the interactive wizard
amplifier provider add openai-chatgpt

# 4. Or use the management dashboard
amplifier provider manage
```

You can also wire it into a bundle directly with an inline `source:` field:

```markdown
---
bundle:
  name: test-openai-chatgpt
  version: 0.1.0

includes:
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main

providers:
  - module: provider-openai-chatgpt
    source: /path/to/amplifier-module-provider-openai-chatgpt
    config:
      default_model: gpt-5.5
---

# Test: provider-openai-chatgpt
```

```bash
amplifier run --bundle ./test-chatgpt.md "Hello, can you hear me?"
```

## Routing Matrix

`routing/openai-chatgpt.yaml` documents the policy and maps all 13 roles. General
roles prefer Sol, Terra, then Luna. Coding uses catalog-based Codex matching,
then Terra/Sol. A final live-catalog glob keeps unconfigured requests usable
when an account has not received GPT-5.6. Explicit `request.model` always wins.

## Supported Models

Only the documented GPT-5.6 identifiers are included in the static fallback:
[Sol (`gpt-5.6-sol`)](https://developers.openai.com/api/docs/models/gpt-5.6-sol),
[Terra (`gpt-5.6-terra`)](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
and [Luna (`gpt-5.6-luna`)](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
Each model page reports a 1,050,000-token context and 128,000-token maximum
output. OpenAI's [GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/model-guidance?model=gpt-5.6)
documents the family roles, reasoning levels, and that the `gpt-5.6` alias routes
to Sol. Runtime visibility and speed-tier data are read from the authenticated
`GET /backend-api/codex/models` response; no speculative `fast` variant or
account entitlement is hardcoded.

## DTU Validation

This module includes a [Digital Twin Universe](https://github.com/microsoft/amplifier-bundle-digital-twin-universe) profile for end-to-end validation in an isolated container. The DTU environment provisions Amplifier with the provider, a pre-authenticated OAuth token, and the routing matrix -- then runs acceptance tests against the live ChatGPT backend API.

```bash
# Launch (requires Incus and a valid OAuth token on the host)
amplifier-digital-twin launch \
  .amplifier/digital-twin-universe/profiles/chatgpt-provider-reality-check.yaml \
  --var OAUTH_TOKEN_FILE=$HOME/.amplifier/openai-chatgpt-oauth.json \
  --var PROVIDER_SHA=<candidate-sha>

# Check readiness
amplifier-digital-twin check-readiness <id>

# Destroy when done
amplifier-digital-twin destroy <id>
```

See [docs/DTU_VALIDATION.md](docs/DTU_VALIDATION.md) for the full guide covering prerequisites, what's tested, what's excluded, and troubleshooting.

## Known Limitations

- **Automatic mid-session 401 recovery** -- if the access token expires mid-session, the provider performs one silent token refresh and retries the request automatically. A second consecutive 401 raises `AuthenticationError`.
- **No `response.incomplete` continuation** -- if a reasoning model hits its output limit, the partial response is lost. Auto-continuation is planned.
- **Streaming is mandatory** -- the ChatGPT backend requires `stream=True`. The provider always streams internally but returns a complete `ChatResponse` to the orchestrator.
- **No `response.content_part.delta` handling** -- only `response.output_item.done` events are accumulated. Streaming delta forwarding is planned.

## Dependencies

- `httpx` - HTTP client for raw API requests

## Contributing

Downstream maintainers must follow the [upstream synchronization and branch strategy](docs/BRANCH_STRATEGY.md); custom pull requests target `downstream`, never the clean `main` mirror.

> [!NOTE]
> This project is not currently accepting external contributions, but we're actively working toward opening this up. We value community input and look forward to collaborating in the future. For now, feel free to fork and experiment!

Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
