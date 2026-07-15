# ChatGPT 5.6 Model Routing Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Update `amplifier-module-provider-openai-chatgpt` so default provider behavior, fallback model catalog, routing matrix, tests, and docs support the new ChatGPT 5.6 Sol/Terra/Luna models without breaking explicit legacy model requests.

**Architecture:** Keep the change provider-local: update the provider module's default model, static fallback catalog, routing matrix, and documentation. Preserve the live ChatGPT `/backend-api/codex/models` catalog as the source of truth; the static catalog remains only a resilience fallback when live fetch fails. Do not add new kernel, foundation, orchestrator, or routing subsystem concepts.

**Tech Stack:** Python 3.11+, `uv`, `pytest`, `pytest-asyncio`, `ruff`, Amplifier provider protocol, YAML routing matrix, ChatGPT backend Responses API via raw `httpx` + manual SSE.

## Global Constraints

- Do not modify `amplifier-core`, `amplifier-foundation`, or any other repository.
- Do not add a registry package, abstraction layer, provider aliasing subsystem, or new orchestrator behavior.
- Live model catalog remains authoritative; `FALLBACK_MODELS` is only a fallback for fetch failure or empty live catalog.
- Runtime provider default must become `gpt-5.6-sol`, matching official docs where `gpt-5.6` aliases to Sol and preserving the old behavior of defaulting to the strongest current model.
- User-supplied `request.model` must remain exact. Do not silently rewrite `gpt-5.5` to `gpt-5.6-*`.
- Keep legacy `gpt-5.5` and `gpt-5.4` as fallback candidates during rollout if still supported.
- Keep `-fast` behavior unchanged: `{model}-fast` strips to `{model}` and adds `service_tier: "priority"`; only expose synthetic fast variants when model metadata says `additional_speed_tiers` contains `fast`.
- Do not invent `gpt-5.6-pro` or speculative per-model validation rules. Only add model-specific effort constraints if the live catalog or official docs prove a real constraint.
- Preserve existing unrelated user modifications in `tests/test_oauth.py` and `tests/test_provider.py`. Inspect diffs before editing; do not overwrite unrelated changes.
- All file I/O in any helper scripts/snippets must use `encoding="utf-8"`.
- Every task below should be implemented test-first, with a commit after the task passes. Git operations are for the later implementation/finish workflow, not for this planning step.

---

## Design Decisions and Tradeoffs

### 1. Provider-local update only

This repository is an Amplifier Provider module. It registers `openai-chatgpt` through the entry point in `pyproject.toml`:

```toml
[project.entry-points."amplifier.modules"]
provider-openai-chatgpt = "amplifier_module_provider_openai_chatgpt:mount"
```

The correct boundary is therefore this module's model selection, model listing, routing matrix, tests, and docs. Changing the kernel or foundation would be policy leakage: model names and routing preferences are provider/module concerns, not core mechanisms.

### 2. Default to `gpt-5.6-sol`

Use `gpt-5.6-sol` as the runtime default, not Terra. Terra is useful for cost/performance routing, but the existing provider default was the strongest current model (`gpt-5.5`). Sol is the strongest/general model and is also the target of the official `gpt-5.6` alias, so it best preserves default behavior for users who did not explicitly configure a model.

Tradeoff: this may cost more than Terra for default use. That is acceptable because the routing matrix can choose Terra/Luna for roles where cost or latency matters, while the provider default should remain the safest strongest default.

### 3. No silent legacy aliasing

Do not map `gpt-5.5` to `gpt-5.6-terra` or any other 5.6 model inside `_build_payload()`. Existing configs that explicitly name `gpt-5.5` are making an exact model request. Rewriting exact user input would be surprising and would make debugging provider behavior harder.

Compatibility is handled by leaving `gpt-5.5` in fallback catalogs and routing fallback chains while it remains supported. Users without explicit `default_model` config get the new `gpt-5.6-sol` default.

### 4. Live catalog first, static fallback second

The live `/backend-api/codex/models` endpoint already returns account-specific model metadata: slug, display name, context windows, speed tiers, reasoning levels, `supported_in_api`, and visibility. Keep that as the source of truth. Add 5.6 entries to `FALLBACK_MODELS` only so `list_models()` remains useful if live catalog fetch fails.

### 5. Routing matrix chooses concrete 5.6 models

Update all 13 Amplifier model roles to prefer 5.6. The chosen mapping is:

| Role | Primary selection |
|------|-------------------|
| `general` | `gpt-5.6-sol` |
| `fast` | `gpt-5.6-luna` |
| `coding` | existing `gpt-?.?-codex*` first, then `gpt-5.6-terra` |
| `ui-coding` | `gpt-5.6-sol` |
| `security-audit` | `gpt-5.6-sol` + `reasoning_effort: high` |
| `reasoning` | `gpt-5.6-sol` + `reasoning_effort: high` |
| `critique` | `gpt-5.6-sol` + `reasoning_effort: xhigh` |
| `creative` | `gpt-5.6-sol` |
| `writing` | `gpt-5.6-sol` |
| `research` | `gpt-5.6-sol` + `reasoning_effort: high` |
| `vision` | `gpt-5.6-sol` |
| `image-gen` | `gpt-5.6-sol` degraded prompt/SVG planning |
| `critical-ops` | `gpt-5.6-sol` + `reasoning_effort: high` |

Coding keeps the current Codex glob first because Codex-tuned models are purpose-built for coding when available. The second candidate becomes `gpt-5.6-terra` because official guidance describes Terra as lower-cost strong performance, which fits coding workloads better than always using Sol.

### 6. GPT-5.5-pro validation stays legacy unless proven obsolete

`provider.py` has `_validate_gpt_5_5_pro_effort()` for `gpt-5.5-pro*`. Do not create a speculative GPT-5.6-pro validator. During implementation, verify whether live catalog includes any `gpt-5.5-pro*` or `gpt-5.6-pro*` entries. If no pro variants exist, leave the legacy validator in place for backward compatibility and update tests to label it legacy. Only replace it with a data-driven per-model effort rule if real catalog metadata exposes documented constraints.

---

## File Map

### Must modify

- `amplifier_module_provider_openai_chatgpt/models.py`
  - Add fallback entries for `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` in that order.
  - Keep legacy `gpt-5.5` and `gpt-5.4` after 5.6 entries.
  - Preserve `to_model_infos()` fast-variant behavior.

- `amplifier_module_provider_openai_chatgpt/provider.py`
  - Change `ChatGPTProvider.__init__()` default from `gpt-5.5` to `gpt-5.6-sol`.
  - Keep request model override behavior unchanged.
  - Keep `-fast` suffix behavior unchanged.
  - Keep or narrowly update `_validate_gpt_5_5_pro_effort()` based on live catalog evidence; do not add speculative 5.6-pro validation.

- `routing/openai-chatgpt.yaml`
  - Update header catalog notes to 5.6.
  - Update all 13 model roles to prefer Sol/Terra/Luna as specified above.
  - Include 5.5 fallback after 5.6 candidates.

- `README.md`
  - Stop naming `gpt-5.5` as the default.
  - Document `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, and `gpt-5.6` alias behavior.
  - Explain that explicit `gpt-5.5` configs remain exact legacy requests, not aliases.

- `tests/test_models.py`
  - Update fallback first-entry tests.
  - Add tests for all three 5.6 fallback entries.
  - Keep tests for fast synthetic variants using a 5.6 entry that supports `fast` if verified/fallback metadata says it does.

- `tests/test_provider.py`
  - Update fallback tests.
  - Add provider default test for `gpt-5.6-sol`.
  - Update fast suffix examples from `gpt-5.4-fast` to a 5.6 fast-supported model if verified/fallback metadata supports fast; otherwise keep fast behavior tests model-agnostic with `gpt-5.5-fast` or a synthetic request model and explicitly test suffix mechanics.
  - Keep request override exactness tests.
  - Keep GPT-5.5-pro validator tests as legacy unless implementation removes validator with explicit evidence.

### Possibly modify only if assertions are found

- `docs/DTU_VALIDATION.md`
  - Currently states model name assertions are intentionally excluded. Update only if implementation adds or changes validation around model catalog expectations.

- `.amplifier/digital-twin-universe/profiles/chatgpt-provider-reality-check.yaml`
  - Update only if the profile hard-codes old model assertions or if provider config should explicitly smoke-test `gpt-5.6-sol`.

- `.amplifier/digital-twin-universe/acceptance-tests/chatgpt-provider.yaml`
  - Current file excludes model-catalog name assertions. Update only if adding a model-listing smoke test that checks for at least one `gpt-5.6-*` when OAuth account exposes it.

### Optional new test file during implementation

- `tests/test_routing.py`
  - Create only if routing YAML validation would make `tests/test_provider.py` too large or muddled. A focused routing test is justified because routing is a separate shipped artifact and old route candidates would keep agents on stale models even after provider defaults change.

---

## Implementation Tasks

### Task 0: Baseline and live catalog evidence

**Files:**
- Read/inspect: `tests/test_oauth.py`
- Read/inspect: `tests/test_provider.py`
- Read/inspect: `amplifier_module_provider_openai_chatgpt/models.py`
- Read/inspect: `routing/openai-chatgpt.yaml`
- No code changes in this task unless recording evidence in commit message notes later.

**Interfaces:**
- Consumes: existing repository state.
- Produces: concrete evidence of live account model metadata used to finalize fallback fields and test expectations.

- [ ] **Step 1: Inspect unrelated working tree changes**

Run:

```bash
git status --short
git diff -- tests/test_oauth.py tests/test_provider.py
```

Expected:

- Output shows existing modifications in `tests/test_oauth.py` and `tests/test_provider.py`.
- Read the diff and identify which hunks are unrelated user work.
- Do not revert, overwrite, or reformat unrelated hunks.

- [ ] **Step 2: Run baseline tests before changing anything**

Run:

```bash
uv run pytest tests/test_models.py -v
uv run pytest tests/test_provider.py -v
```

Expected:

- Record whether tests pass or fail before this change.
- If tests fail due to pre-existing local user changes, record the failing test names and exact failure summaries. Continue only after understanding that failures are unrelated to the 5.6 plan.

- [ ] **Step 3: Verify live ChatGPT catalog contains the documented 5.6 models**

Use the provider's existing OAuth token path. Run a short Python snippet that calls existing module code rather than reimplementing headers:

```bash
uv run python - <<'PY'
import asyncio
import json
from amplifier_module_provider_openai_chatgpt.models import fetch_models
from amplifier_module_provider_openai_chatgpt.oauth import load_tokens

async def main() -> None:
    tokens = load_tokens()
    entries = await fetch_models(
        access_token=tokens["access_token"],
        account_id=tokens["account_id"],
    )
    wanted = {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6"}
    found = [entry for entry in entries if entry.get("slug") in wanted or str(entry.get("slug", "")).startswith("gpt-5.6")]
    print(json.dumps(found, indent=2, sort_keys=True))

asyncio.run(main())
PY
```

Expected if OAuth token is available and account has 5.6 access:

- Exit code 0.
- JSON includes `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`.
- For each visible entry, record these exact fields from output for fallback accuracy:
  - `slug`
  - `display_name`
  - `context_window`
  - `max_context_window`
  - `additional_speed_tiers`
  - `supported_reasoning_levels`
  - `supported_in_api`
  - `visibility`

Expected if OAuth token is unavailable:

- The command fails with a clear token/auth error.
- Do not invent metadata. Use official model IDs and conservative fallback metadata from existing 5.5 patterns, and mark live DTU validation as required before merge.

- [ ] **Step 4: Check for real pro variants before touching validator**

Run:

```bash
uv run python - <<'PY'
import asyncio
import json
from amplifier_module_provider_openai_chatgpt.models import fetch_models
from amplifier_module_provider_openai_chatgpt.oauth import load_tokens

async def main() -> None:
    tokens = load_tokens()
    entries = await fetch_models(
        access_token=tokens["access_token"],
        account_id=tokens["account_id"],
    )
    pro_entries = [entry for entry in entries if "pro" in str(entry.get("slug", ""))]
    print(json.dumps(pro_entries, indent=2, sort_keys=True))

asyncio.run(main())
PY
```

Expected:

- If no pro entries appear, keep `_validate_gpt_5_5_pro_effort()` as a legacy guard and update tests/documentation wording only.
- If real pro entries appear with documented constraints, design the smallest data-driven validation rule for those actual slugs only. Do not infer constraints for non-pro 5.6 models.

- [ ] **Step 5: Commit baseline evidence only if a project convention exists for evidence commits**

Normally skip a commit for this no-code task. If the implementation workflow requires checkpoint commits, use an empty commit only after discussing with the user:

```bash
git commit --allow-empty -m "chore: record chatgpt 5.6 catalog baseline"
```

Expected: no source files changed by this task.

---

### Task 1: Update fallback catalog tests first

**Files:**
- Modify tests: `tests/test_models.py`
- Modify tests: `tests/test_provider.py`
- Implementation later: `amplifier_module_provider_openai_chatgpt/models.py`

**Interfaces:**
- Consumes: `FALLBACK_MODELS: list[dict[str, Any]]` from `models.py`.
- Produces: tests requiring fallback order `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, then legacy models.

- [ ] **Step 1: Write failing fallback tests in `tests/test_models.py`**

Replace `test_fallback_first_entry_is_gpt_55` with tests like:

```python
def test_fallback_first_entries_are_gpt_56_variants(self) -> None:
    """FALLBACK_MODELS must prefer current ChatGPT 5.6 variants before legacy models."""
    from amplifier_module_provider_openai_chatgpt.models import FALLBACK_MODELS

    slugs = [entry["slug"] for entry in FALLBACK_MODELS]
    assert slugs[:3] == ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]


def test_fallback_keeps_legacy_models_after_gpt_56(self) -> None:
    """Legacy 5.5/5.4 remain available as fallback during rollout."""
    from amplifier_module_provider_openai_chatgpt.models import FALLBACK_MODELS

    slugs = [entry["slug"] for entry in FALLBACK_MODELS]
    assert "gpt-5.5" in slugs
    assert "gpt-5.4" in slugs
    assert slugs.index("gpt-5.5") > slugs.index("gpt-5.6-luna")
    assert slugs.index("gpt-5.4") > slugs.index("gpt-5.6-luna")
```

Add metadata shape checks:

```python
@pytest.mark.parametrize("slug", ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"])
def test_fallback_gpt_56_entries_are_api_visible(slug: str) -> None:
    """Each GPT-5.6 fallback entry must be visible and API-supported."""
    from amplifier_module_provider_openai_chatgpt.models import FALLBACK_MODELS

    entry = next(model for model in FALLBACK_MODELS if model["slug"] == slug)
    assert entry["display_name"]
    assert entry["context_window"] > 0
    assert entry["max_context_window"] >= entry["context_window"]
    assert entry["visibility"] == "list"
    assert entry["supported_in_api"] is True
    assert set(entry["supported_reasoning_levels"]) >= {"none", "low", "medium", "high"}
```

- [ ] **Step 2: Write failing fallback tests in `tests/test_provider.py`**

Replace `TestFallbackCatalog.test_fallback_first_entry_is_gpt_55` with:

```python
def test_fallback_first_entries_are_gpt_56_variants(self) -> None:
    from amplifier_module_provider_openai_chatgpt.models import FALLBACK_MODELS

    assert len(FALLBACK_MODELS) >= 3, "FALLBACK_MODELS must include GPT-5.6 variants"
    assert [entry["slug"] for entry in FALLBACK_MODELS[:3]] == [
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
    ]
```

Keep `test_fallback_contains_gpt_52` if the fallback catalog still contains `gpt-5.2`. If implementation decides to remove `gpt-5.2`, first rewrite that test to assert the intentional legacy floor, for example:

```python
def test_fallback_contains_legacy_rollout_models(self) -> None:
    from amplifier_module_provider_openai_chatgpt.models import FALLBACK_MODELS

    slugs = [m["slug"] for m in FALLBACK_MODELS]
    assert "gpt-5.5" in slugs
    assert "gpt-5.4" in slugs
```

- [ ] **Step 3: Run tests to verify they fail for the right reason**

Run:

```bash
uv run pytest tests/test_models.py::TestToModelInfos::test_fallback_first_entries_are_gpt_56_variants -v
uv run pytest tests/test_provider.py::TestFallbackCatalog::test_fallback_first_entries_are_gpt_56_variants -v
```

Expected:

- Both fail because current first fallback slug is `gpt-5.5`, not `gpt-5.6-sol`.
- Failure should not be import errors or syntax errors.

- [ ] **Step 4: Commit failing tests only if the implementation workflow uses red commits**

Usually do not commit red tests to `main`. If working in a TDD worktree with local commits per task, commit after the green implementation in Task 2 instead.

---

### Task 2: Update `FALLBACK_MODELS` to include ChatGPT 5.6

**Files:**
- Modify: `amplifier_module_provider_openai_chatgpt/models.py`
- Tests: `tests/test_models.py`, `tests/test_provider.py`

**Interfaces:**
- Consumes: tests from Task 1.
- Produces: updated `FALLBACK_MODELS` with 5.6 variants first.

- [ ] **Step 1: Implement minimal fallback catalog update**

In `amplifier_module_provider_openai_chatgpt/models.py`, update `FALLBACK_MODELS` so the first three entries are:

```python
FALLBACK_MODELS: list[dict[str, Any]] = [
    {
        "slug": "gpt-5.6-sol",
        "display_name": "GPT 5.6 Sol",
        "context_window": 1_000_000,
        "max_context_window": 1_000_000,
        "additional_speed_tiers": ["fast"],
        "supported_reasoning_levels": ["none", "low", "medium", "high", "xhigh"],
        "visibility": "list",
        "supported_in_api": True,
    },
    {
        "slug": "gpt-5.6-terra",
        "display_name": "GPT 5.6 Terra",
        "context_window": 1_000_000,
        "max_context_window": 1_000_000,
        "additional_speed_tiers": ["fast"],
        "supported_reasoning_levels": ["none", "low", "medium", "high", "xhigh"],
        "visibility": "list",
        "supported_in_api": True,
    },
    {
        "slug": "gpt-5.6-luna",
        "display_name": "GPT 5.6 Luna",
        "context_window": 1_000_000,
        "max_context_window": 1_000_000,
        "additional_speed_tiers": [],
        "supported_reasoning_levels": ["none", "low", "medium", "high"],
        "visibility": "list",
        "supported_in_api": True,
    },
    # Keep existing gpt-5.5, gpt-5.4, gpt-5.4-mini, gpt-5.3-codex, gpt-5.2 entries below.
]
```

If Task 0 live catalog evidence shows different context windows, speed tiers, or reasoning levels, use the live values exactly. If Task 0 could not run due to missing OAuth, use the conservative values above and require DTU/live validation before merge.

Rationale for conservative fallback metadata:

- `context_window`/`max_context_window`: preserves existing 5.5 fallback capacity shape.
- `Sol`/`Terra` `fast`: expose synthetic fast variants only if live metadata confirms fast; if not confirmed, set `additional_speed_tiers: []` and adjust tests accordingly.
- `Luna` no fast by default: Luna is already the efficient variant; do not invent priority suffix support unless live catalog says it exists.

- [ ] **Step 2: Run targeted fallback tests**

Run:

```bash
uv run pytest tests/test_models.py -v
uv run pytest tests/test_provider.py::TestFallbackCatalog -v
```

Expected:

- All fallback/model conversion tests pass.
- If `test_to_model_infos_emits_fast_variant` still uses `gpt-5.2`, leave it if `gpt-5.2` remains in fallback. Prefer adding a second fast test with `gpt-5.6-sol` rather than deleting legacy coverage.

- [ ] **Step 3: Commit catalog update**

Run:

```bash
git add amplifier_module_provider_openai_chatgpt/models.py tests/test_models.py tests/test_provider.py
git commit -m "feat: add chatgpt 5.6 fallback models"
```

Expected:

- Commit includes only fallback catalog and fallback tests.
- Unrelated `tests/test_oauth.py` changes are not included.

---

### Task 3: Update provider default and preserve exact model override semantics

**Files:**
- Modify: `tests/test_provider.py`
- Modify: `amplifier_module_provider_openai_chatgpt/provider.py`

**Interfaces:**
- Consumes: `ChatGPTProvider(config, coordinator, tokens)`.
- Produces: `ChatGPTProvider.default_model == "gpt-5.6-sol"` when config omits `default_model`.

- [ ] **Step 1: Write failing provider default test**

In `tests/test_provider.py`, add to `TestBuildPayload` or a small nearby provider initialization test class:

```python
def test_provider_default_model_is_gpt_56_sol_when_unconfigured(self) -> None:
    """Unconfigured provider should default to strongest current ChatGPT 5.6 model."""
    from amplifier_core.message_models import Message
    from amplifier_module_provider_openai_chatgpt.provider import ChatGPTProvider

    provider = ChatGPTProvider({}, MagicMock(), tokens=None)
    request = self._make_request(messages=[Message(role="user", content="hi")])

    payload = provider._build_payload(request)

    assert payload["model"] == "gpt-5.6-sol"
```

Add explicit exact override test if not already present:

```python
def test_legacy_request_model_is_not_rewritten_to_gpt_56(self) -> None:
    """Explicit legacy model requests remain exact for backward compatibility."""
    from amplifier_core.message_models import Message

    provider = self._make_provider(default_model="gpt-5.6-sol")
    request = self._make_request(
        messages=[Message(role="user", content="hi")],
        model="gpt-5.5",
    )

    payload = provider._build_payload(request)

    assert payload["model"] == "gpt-5.5"
```

- [ ] **Step 2: Run tests to verify default test fails**

Run:

```bash
uv run pytest tests/test_provider.py::TestBuildPayload::test_provider_default_model_is_gpt_56_sol_when_unconfigured -v
```

Expected:

- Fails because payload model is currently `gpt-5.5`.
- Exact override test should pass if added before implementation; it documents unchanged behavior.

- [ ] **Step 3: Change default model in provider**

In `amplifier_module_provider_openai_chatgpt/provider.py`, change only the default value in `ChatGPTProvider.__init__()`:

```python
self.default_model: str = self._config.get("default_model", "gpt-5.6-sol")
```

Do not change:

```python
model: str = request.model or self.default_model
```

Do not add alias mapping for `gpt-5.5`.

- [ ] **Step 4: Run provider payload tests**

Run:

```bash
uv run pytest tests/test_provider.py::TestBuildPayload -v
```

Expected:

- Default test passes.
- Existing override tests pass.
- Fast suffix tests still pass.

- [ ] **Step 5: Commit provider default update**

Run:

```bash
git add amplifier_module_provider_openai_chatgpt/provider.py tests/test_provider.py
git commit -m "feat: default chatgpt provider to gpt-5.6-sol"
```

Expected:

- Commit does not include routing or README changes yet.

---

### Task 4: Preserve `-fast` suffix mechanics with 5.6 coverage

**Files:**
- Modify: `tests/test_models.py`
- Modify: `tests/test_provider.py`
- Possibly modify: `amplifier_module_provider_openai_chatgpt/models.py` only if Task 0 proves different speed-tier metadata.

**Interfaces:**
- Consumes: `to_model_infos(entries)` and `ChatGPTProvider._build_payload(request)`.
- Produces: tests proving fast variants are metadata-driven and payload suffix stripping remains unchanged.

- [ ] **Step 1: Add 5.6 fast variant conversion test**

In `tests/test_models.py`, add:

```python
def test_to_model_infos_emits_gpt_56_fast_variant_when_metadata_supports_fast(self) -> None:
    """GPT-5.6 entries emit synthetic -fast variants only when speed tier metadata says so."""
    from amplifier_module_provider_openai_chatgpt.models import to_model_infos

    entries = [
        _make_entry(
            "gpt-5.6-sol",
            display_name="GPT 5.6 Sol",
            context_window=1_000_000,
            speed_tiers=["fast"],
        )
    ]

    result = to_model_infos(entries)

    ids = [model.id for model in result]
    assert ids == ["gpt-5.6-sol", "gpt-5.6-sol-fast"]
    fast = result[1]
    assert fast.display_name == "GPT 5.6 Sol (fast)"
    assert fast.context_window == 1_000_000
```

Also add no-fast coverage for Luna:

```python
def test_to_model_infos_does_not_emit_luna_fast_without_metadata(self) -> None:
    """Luna should not get a speculative -fast variant unless catalog metadata supports it."""
    from amplifier_module_provider_openai_chatgpt.models import to_model_infos

    result = to_model_infos([
        _make_entry("gpt-5.6-luna", display_name="GPT 5.6 Luna", speed_tiers=[])
    ])

    assert [model.id for model in result] == ["gpt-5.6-luna"]
```

- [ ] **Step 2: Update provider fast suffix tests to 5.6 examples**

In `tests/test_provider.py`, change fast suffix examples from `gpt-5.4-fast` to `gpt-5.6-sol-fast` only if `gpt-5.6-sol` supports fast in fallback/live metadata. The expected payload remains stripped base model:

```python
provider = self._make_provider(default_model="gpt-5.6-sol-fast")
# ...
assert payload["model"] == "gpt-5.6-sol"
assert payload.get("service_tier") == "priority"
```

For request override:

```python
request = self._make_request(
    messages=[Message(role="user", content="hi")],
    model="gpt-5.6-terra-fast",
)
assert payload["model"] == "gpt-5.6-terra"
assert payload.get("service_tier") == "priority"
```

If live metadata does not show fast support for Sol/Terra, keep a model-agnostic suffix test using a synthetic string:

```python
provider = self._make_provider(default_model="example-model-fast")
assert payload["model"] == "example-model"
assert payload.get("service_tier") == "priority"
```

- [ ] **Step 3: Run fast-related tests**

Run:

```bash
uv run pytest tests/test_models.py::TestToModelInfos -v
uv run pytest tests/test_provider.py::TestBuildPayload -v
```

Expected:

- Tests prove `-fast` is not hard-coded to old model names.
- No production behavior changes beyond any speed-tier metadata confirmed by Task 0.

- [ ] **Step 4: Commit fast coverage update**

Run:

```bash
git add tests/test_models.py tests/test_provider.py amplifier_module_provider_openai_chatgpt/models.py
git commit -m "test: cover chatgpt 5.6 fast tier handling"
```

Expected:

- If `models.py` was not changed in this task, omit it from `git add`.

---

### Task 5: Keep GPT-5.5-pro validation legacy and non-speculative

**Files:**
- Modify: `tests/test_provider.py`
- Possibly modify: `amplifier_module_provider_openai_chatgpt/provider.py` only if Task 0 proves real pro constraints.

**Interfaces:**
- Consumes: `_validate_gpt_5_5_pro_effort(model_id: str, reasoning_param: Any) -> None`.
- Produces: tests documenting that validation is legacy and no GPT-5.6-pro constraint is invented.

- [ ] **Step 1: Rename/comment tests to legacy wording without changing behavior**

In `tests/test_provider.py`, keep the validator class if `_validate_gpt_5_5_pro_effort()` remains. Update comments/docstrings from "current pro validation" language to legacy compatibility language:

```python
# TestLegacyGpt55ProValidator — _validate_gpt_5_5_pro_effort()

class TestLegacyGpt55ProValidator:
    """Legacy guard for old gpt-5.5-pro constraints; do not extend speculatively to GPT-5.6."""
```

Add a test proving non-pro 5.6 models are not blocked:

```python
@pytest.mark.parametrize("model", ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"])
def test_gpt_56_non_pro_models_accept_low_effort(self, model: str) -> None:
    """GPT-5.6 non-pro models must not inherit legacy gpt-5.5-pro restrictions."""
    self._validate(model, "low")  # no error expected
```

- [ ] **Step 2: Run validator tests**

Run:

```bash
uv run pytest tests/test_provider.py::TestLegacyGpt55ProValidator -v
```

Expected:

- Existing legacy behavior remains green.
- 5.6 non-pro models with low effort do not raise.

- [ ] **Step 3: Only if live catalog proves real pro constraints, replace with data-driven validator**

Skip this step unless Task 0 found real pro entries with documented constraints. If required, replace `_validate_gpt_5_5_pro_effort()` with a minimal mapping:

```python
_MIN_REASONING_EFFORT_BY_PREFIX = {
    "gpt-5.5-pro": "medium",
    # Add a gpt-5.6-pro prefix only if live/docs prove it exists and has this constraint.
}
_REASONING_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "xhigh": 4}
```

Then validate only prefixes present in that mapping. Do not add non-pro 5.6 entries.

- [ ] **Step 4: Commit validator documentation/tests**

Run:

```bash
git add tests/test_provider.py amplifier_module_provider_openai_chatgpt/provider.py
git commit -m "test: document legacy gpt-5.5 pro effort guard"
```

Expected:

- `provider.py` included only if implementation genuinely changed it.

---

### Task 6: Update routing matrix to prefer ChatGPT 5.6

**Files:**
- Modify: `routing/openai-chatgpt.yaml`
- Create or modify test: `tests/test_routing.py` preferred, or `tests/test_provider.py` if keeping tests in one file.

**Interfaces:**
- Consumes: YAML routing matrix with top-level `roles` mapping.
- Produces: all 13 roles have 5.6 primary candidates and legacy 5.5 fallback.

- [ ] **Step 1: Add failing routing matrix tests**

Create `tests/test_routing.py` if the repo permits focused test files. Use this complete test scaffold:

```python
"""Tests for routing/openai-chatgpt.yaml."""

from pathlib import Path
from typing import Any

import yaml


ROUTING_PATH = Path(__file__).resolve().parents[1] / "routing" / "openai-chatgpt.yaml"
EXPECTED_ROLES = {
    "general",
    "fast",
    "coding",
    "ui-coding",
    "security-audit",
    "reasoning",
    "critique",
    "creative",
    "writing",
    "research",
    "vision",
    "image-gen",
    "critical-ops",
}


def _load_routing() -> dict[str, Any]:
    return yaml.safe_load(ROUTING_PATH.read_text(encoding="utf-8"))


def _models_for_role(matrix: dict[str, Any], role: str) -> list[str]:
    return [candidate["model"] for candidate in matrix["roles"][role]["candidates"]]


def test_routing_defines_all_13_amplifier_roles() -> None:
    matrix = _load_routing()
    assert set(matrix["roles"]) == EXPECTED_ROLES


def test_general_roles_prefer_gpt_56_sol() -> None:
    matrix = _load_routing()
    for role in ["general", "ui-coding", "creative", "writing", "vision", "image-gen"]:
        assert _models_for_role(matrix, role)[0] == "gpt-5.6-sol"


def test_reasoning_roles_prefer_gpt_56_sol_with_high_effort() -> None:
    matrix = _load_routing()
    for role in ["security-audit", "reasoning", "research", "critical-ops"]:
        first = matrix["roles"][role]["candidates"][0]
        assert first["model"] == "gpt-5.6-sol"
        assert first["config"]["reasoning_effort"] == "high"


def test_critique_prefers_gpt_56_sol_with_xhigh_effort() -> None:
    matrix = _load_routing()
    first = matrix["roles"]["critique"]["candidates"][0]
    assert first["model"] == "gpt-5.6-sol"
    assert first["config"]["reasoning_effort"] == "xhigh"


def test_fast_prefers_gpt_56_luna() -> None:
    matrix = _load_routing()
    assert _models_for_role(matrix, "fast")[0] == "gpt-5.6-luna"


def test_coding_keeps_codex_glob_then_gpt_56_terra() -> None:
    matrix = _load_routing()
    models = _models_for_role(matrix, "coding")
    assert models[0] == "gpt-?.?-codex*"
    assert models[1] == "gpt-5.6-terra"


def test_every_role_has_legacy_gpt_55_fallback() -> None:
    matrix = _load_routing()
    for role in EXPECTED_ROLES:
        assert "gpt-5.5" in _models_for_role(matrix, role), role
```

If `pyyaml` is not available outside runtime dependencies, either add it to the dev dependency group only if already used elsewhere, or parse with `yaml` from existing environment. Since `pyproject.toml` currently does not list `pyyaml`, first try the test; if import fails, place this routing validation in a small Python snippet in docs instead of adding a dependency. Do not add runtime dependencies for a test-only parser unless the project already accepts PyYAML via Amplifier dependencies.

- [ ] **Step 2: Run routing tests to verify they fail**

Run:

```bash
uv run pytest tests/test_routing.py -v
```

Expected:

- Fails because current matrix still starts with `gpt-5.5`/`gpt-5.4`.
- If it fails with `ModuleNotFoundError: No module named 'yaml'`, stop and decide whether to add `pyyaml` as a dev dependency or move the routing assertions into a no-dependency parser test. Prefer adding `pyyaml` to `dependency-groups.dev` only if this repo already relies on YAML validation elsewhere.

- [ ] **Step 3: Update `routing/openai-chatgpt.yaml` header**

Rewrite header facts to describe 5.6. The header must include:

```yaml
# Catalog (as of 2026-07, verify against /backend-api/codex/models for each account):
#   gpt-5.6-sol    — strongest/default, official gpt-5.6 alias target
#   gpt-5.6-terra  — lower-cost strong performance; preferred after codex for coding
#   gpt-5.6-luna   — efficient high-volume work; preferred for fast role
#   gpt-5.5        — legacy fallback during rollout
#   gpt-5.4        — deeper legacy fallback during rollout
```

Update fallback philosophy:

```yaml
# Fallback chain:
#   Roles prefer GPT-5.6 variants first, then legacy gpt-5.5/gpt-5.4.
#   Explicit user configs naming gpt-5.5 are not aliased; fallback candidates
#   only help routing resolve on accounts that have not fully rotated.
```

Update `updated:` to the implementation date.

- [ ] **Step 4: Update role candidates exactly**

Use this concrete role mapping:

```yaml
roles:
  general:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
      - provider: openai-chatgpt
        model: gpt-5.5
      - provider: openai-chatgpt
        model: gpt-5.4

  fast:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-luna
      - provider: openai-chatgpt
        model: gpt-5.6-terra
      - provider: openai-chatgpt
        model: gpt-5.5

  coding:
    candidates:
      - provider: openai-chatgpt
        model: gpt-?.?-codex*
      - provider: openai-chatgpt
        model: gpt-5.6-terra
      - provider: openai-chatgpt
        model: gpt-5.6-sol
      - provider: openai-chatgpt
        model: gpt-5.5

  ui-coding:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
      - provider: openai-chatgpt
        model: gpt-5.6-terra
      - provider: openai-chatgpt
        model: gpt-5.5

  security-audit:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
        config:
          reasoning_effort: high
      - provider: openai-chatgpt
        model: gpt-5.5
        config:
          reasoning_effort: high

  reasoning:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
        config:
          reasoning_effort: high
      - provider: openai-chatgpt
        model: gpt-5.5
        config:
          reasoning_effort: high

  critique:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
        config:
          reasoning_effort: xhigh
      - provider: openai-chatgpt
        model: gpt-5.5
        config:
          reasoning_effort: xhigh

  creative:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
      - provider: openai-chatgpt
        model: gpt-5.5

  writing:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
      - provider: openai-chatgpt
        model: gpt-5.5

  research:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
        config:
          reasoning_effort: high
      - provider: openai-chatgpt
        model: gpt-5.5
        config:
          reasoning_effort: high

  vision:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
      - provider: openai-chatgpt
        model: gpt-5.5

  image-gen:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
      - provider: openai-chatgpt
        model: gpt-5.5

  critical-ops:
    candidates:
      - provider: openai-chatgpt
        model: gpt-5.6-sol
        config:
          reasoning_effort: high
      - provider: openai-chatgpt
        model: gpt-5.5
        config:
          reasoning_effort: high
```

Preserve descriptions and explanatory comments from the current file where still accurate, especially the degraded `image-gen` note.

- [ ] **Step 5: Run routing tests**

Run:

```bash
uv run pytest tests/test_routing.py -v
```

Expected:

- All routing tests pass.

- [ ] **Step 6: Commit routing update**

Run:

```bash
git add routing/openai-chatgpt.yaml tests/test_routing.py pyproject.toml uv.lock
git commit -m "feat: route chatgpt roles to gpt-5.6 models"
```

Expected:

- Include `pyproject.toml` and `uv.lock` only if a dev dependency was added.
- Do not include unrelated user test changes.

---

### Task 7: Update README documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: implemented defaults and routing decisions.
- Produces: user-facing documentation that no longer names `gpt-5.5` as default.

- [ ] **Step 1: Update configuration examples**

In `README.md`, change:

```toml
[providers.provider-openai-chatgpt]
default_model = "gpt-5.5"
```

to:

```toml
[providers.provider-openai-chatgpt]
default_model = "gpt-5.6-sol"
```

Update config table:

```markdown
| `default_model` | str | `"gpt-5.6-sol"` | Model to use for inference when a request does not specify one |
```

- [ ] **Step 2: Update feature bullets**

Change the fast suffix bullet to avoid old default examples:

```markdown
- `-fast` model suffix support when model catalog metadata exposes a `fast` speed tier (for example, `gpt-5.6-sol-fast` -> `gpt-5.6-sol` with `service_tier: "priority"`)
```

If live metadata does not support `fast` for Sol, use a generic example:

```markdown
- `-fast` model suffix support when model catalog metadata exposes a `fast` speed tier (`{model}-fast` -> `{model}` with `service_tier: "priority"`)
```

- [ ] **Step 3: Update inline bundle example**

Change:

```yaml
default_model: gpt-5.5
```

to:

```yaml
default_model: gpt-5.6-sol
```

- [ ] **Step 4: Update Routing Matrix section**

Replace the old two-tier fallback paragraph and role table with:

```markdown
The matrix prefers ChatGPT 5.6 models and keeps `gpt-5.5`/`gpt-5.4` as legacy fallback candidates during rollout. Explicit user configs naming `gpt-5.5` are not rewritten; fallback candidates only affect routing resolution.

| Role | Primary Model | Config |
|------|--------------|--------|
| `general`, `creative`, `writing`, `vision`, `ui-coding` | `gpt-5.6-sol` | -- |
| `fast` | `gpt-5.6-luna` | -- |
| `coding` | `gpt-?.?-codex*`, then `gpt-5.6-terra` | -- |
| `reasoning`, `research`, `security-audit`, `critical-ops` | `gpt-5.6-sol` | `reasoning_effort: high` |
| `critique` | `gpt-5.6-sol` | `reasoning_effort: xhigh` |
```

- [ ] **Step 5: Update Supported Models section**

Replace the stale April 2026 catalog with:

```markdown
Official OpenAI documentation lists these ChatGPT 5.6 model IDs:

| Model | Intended use |
|-------|--------------|
| `gpt-5.6-sol` | Strongest/general model; provider default; target of the `gpt-5.6` alias |
| `gpt-5.6-terra` | Lower-cost strong performance; preferred routing fallback for coding after Codex-tuned models |
| `gpt-5.6-luna` | Efficient high-volume workloads; preferred for the `fast` role |

The provider fetches the account-specific live catalog from `GET /backend-api/codex/models`. Available models, context windows, speed tiers, and reasoning levels depend on your subscription tier and backend rollout state.
```

Update fallback description:

```markdown
If the live API is unreachable, the fallback catalog starts with `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`, followed by legacy `gpt-5.5`/`gpt-5.4` entries. The fallback is not cached, so the next `list_models()` call retries the live API.
```

- [ ] **Step 6: Verify docs have no stale default references**

Run:

```bash
grep -n "default.*gpt-5\.5\|gpt-5\.5.*default" README.md || true
grep -n "gpt-5\.4-fast" README.md || true
```

Expected:

- No output.
- References to `gpt-5.5` may remain only as legacy fallback/explicit compatibility text.

- [ ] **Step 7: Commit README update**

Run:

```bash
git add README.md
git commit -m "docs: document chatgpt 5.6 model routing"
```

Expected:

- Documentation commit only.

---

### Task 8: Inspect and update DTU docs/profile only if needed

**Files:**
- Possibly modify: `docs/DTU_VALIDATION.md`
- Possibly modify: `.amplifier/digital-twin-universe/profiles/chatgpt-provider-reality-check.yaml`
- Possibly modify: `.amplifier/digital-twin-universe/acceptance-tests/chatgpt-provider.yaml`

**Interfaces:**
- Consumes: current DTU validation workflow.
- Produces: DTU docs that remain accurate after 5.6 changes.

- [ ] **Step 1: Search DTU files for stale model assertions**

Run:

```bash
grep -R "gpt-5\.5\|gpt-5\.4\|model-catalog" docs/DTU_VALIDATION.md .amplifier/digital-twin-universe -n
```

Expected:

- `docs/DTU_VALIDATION.md` currently says model catalog name assertions are excluded because model names change with subscription tier.
- Acceptance tests currently exclude model-catalog assertions.
- If no stale default assertion is found, make no changes in this task.

- [ ] **Step 2: If adding model catalog validation, keep it rollout-safe**

Only add a test if product owners require live 5.6 verification. The test must not fail accounts without completed rollout unless the release explicitly requires 5.6 access. A safe manual command is:

```bash
amplifier-digital-twin exec <id> -- amplifier run --mode single "List the current provider model names and confirm whether any gpt-5.6 model is available."
```

Do not add brittle acceptance YAML that assumes every subscription tier exposes every model unless that is the release gate.

- [ ] **Step 3: Commit only if files changed**

Run if needed:

```bash
git add docs/DTU_VALIDATION.md .amplifier/digital-twin-universe/profiles/chatgpt-provider-reality-check.yaml .amplifier/digital-twin-universe/acceptance-tests/chatgpt-provider.yaml
git commit -m "docs: align dtu validation with chatgpt 5.6 rollout"
```

Expected:

- Skip commit if grep confirms no change is needed.

---

### Task 9: Full local validation

**Files:**
- No planned code changes.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: evidence that unit tests and static checks pass locally.

- [ ] **Step 1: Run focused model tests**

Run:

```bash
uv run pytest tests/test_models.py -v
```

Expected:

- Exit code 0.
- Tests include 5.6 fallback order and conversion coverage.

- [ ] **Step 2: Run focused provider tests**

Run:

```bash
uv run pytest tests/test_provider.py -v
```

Expected:

- Exit code 0.
- Tests include default `gpt-5.6-sol`, exact legacy model override, and `-fast` suffix behavior.

- [ ] **Step 3: Run routing tests if created**

Run:

```bash
uv run pytest tests/test_routing.py -v
```

Expected:

- Exit code 0.
- All 13 roles prefer 5.6 candidates and include legacy `gpt-5.5` fallback.

- [ ] **Step 4: Run full test suite**

Run:

```bash
uv run pytest tests/ -v
```

Expected:

- Exit code 0.
- If failures occur in pre-existing modified `tests/test_oauth.py` or unrelated local changes, inspect and separate them from this work before claiming success.

- [ ] **Step 5: Run lint**

Run:

```bash
uv run ruff check .
```

Expected:

- Exit code 0.

- [ ] **Step 6: Run format check**

Run:

```bash
uv run ruff format --check .
```

Expected:

- Exit code 0.

- [ ] **Step 7: Commit any validation-only fixes**

If lint/format required changes, commit them:

```bash
git add <changed-files>
git commit -m "chore: satisfy lint after chatgpt 5.6 update"
```

Expected:

- No commit if no files changed.

---

### Task 10: DTU validation with live OAuth token

**Files:**
- No planned source changes.

**Interfaces:**
- Consumes: existing DTU profile `.amplifier/digital-twin-universe/profiles/chatgpt-provider-reality-check.yaml`.
- Produces: end-to-end evidence that the provider mounts, routes, and completes against the live ChatGPT backend.

- [ ] **Step 1: Verify OAuth token exists**

Run:

```bash
test -f "$HOME/.amplifier/openai-chatgpt-oauth.json" && echo "OAuth token present"
```

Expected:

- If present, continue.
- If absent, record that DTU live validation cannot run until a user completes device code login. Do not fake this evidence.

- [ ] **Step 2: Launch DTU using existing documented profile**

Run only after verifying current DTU command syntax from `docs/DTU_VALIDATION.md`:

```bash
amplifier-digital-twin launch \
  .amplifier/digital-twin-universe/profiles/chatgpt-provider-reality-check.yaml \
  --var OAUTH_TOKEN_FILE=$HOME/.amplifier/openai-chatgpt-oauth.json
```

Expected:

- Command returns a DTU ID.

- [ ] **Step 3: Check readiness**

Run:

```bash
amplifier-digital-twin check-readiness <id>
```

Expected:

- `amplifier-installed` passes.
- `token-present` passes.
- `routing-matrix-present` passes.

- [ ] **Step 4: Run live default inference smoke test**

Run:

```bash
amplifier-digital-twin exec <id> -- amplifier run --mode single "What is 2+2? Reply with ONLY the number."
```

Expected:

- Exit code 0.
- Output contains `4`.

- [ ] **Step 5: Run live tool dispatch smoke test**

Run:

```bash
amplifier-digital-twin exec <id> -- amplifier run --mode single "Run the command echo TOOL_DISPATCH_OK in bash and tell me the output"
```

Expected:

- Exit code 0.
- Output contains `TOOL_DISPATCH_OK`.

- [ ] **Step 6: Verify routing matrix is installed and mentions 5.6**

Run:

```bash
amplifier-digital-twin exec <id> -- grep -n "gpt-5.6" /root/.amplifier/routing/openai-chatgpt.yaml
```

Expected:

- Exit code 0.
- Output includes `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`.

- [ ] **Step 7: Destroy DTU**

Run:

```bash
amplifier-digital-twin destroy <id>
```

Expected:

- Environment is destroyed.

- [ ] **Step 8: Record validation evidence in PR/finish notes**

Do not commit generated DTU artifacts. Capture command exit codes and key output snippets for the final PR or issue response.

---

## Final Verification Checklist

Before presenting this as complete, verify all items below with real command output:

- [ ] `uv run pytest tests/test_models.py -v` exits 0.
- [ ] `uv run pytest tests/test_provider.py -v` exits 0.
- [ ] `uv run pytest tests/test_routing.py -v` exits 0 if `tests/test_routing.py` was created.
- [ ] `uv run pytest tests/ -v` exits 0.
- [ ] `uv run ruff check .` exits 0.
- [ ] `uv run ruff format --check .` exits 0.
- [ ] `README.md` no longer names `gpt-5.5` as the default.
- [ ] `provider.py` defaults to `gpt-5.6-sol`.
- [ ] `models.py` fallback catalog starts with `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`.
- [ ] `routing/openai-chatgpt.yaml` routes all 13 roles to 5.6 first, with legacy `gpt-5.5` fallback.
- [ ] Explicit `request.model="gpt-5.5"` remains exact and is not rewritten.
- [ ] DTU validation either passed with evidence or is honestly reported as blocked by missing OAuth token/DTU prerequisites.
- [ ] `git diff -- tests/test_oauth.py` confirms unrelated user changes were not overwritten.

## Notes for the Implementer

- Treat `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna` as documented model IDs.
- Treat live catalog metadata as stronger evidence than static guesses. If live catalog values differ from this plan's conservative fallback snippets, use live values and explain the difference in the commit message.
- Do not normalize user-supplied model IDs. Exact request model selection is a contract.
- Do not remove legacy model support just because default routing changed. Removal is a separate compatibility decision.
- Keep the implementation boring. This is a catalog/default/routing update, not a model management framework.
