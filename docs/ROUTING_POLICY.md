# GPT-5.6 routing policy

This document is the change record for `routing/openai-chatgpt.yaml`. The matrix
is policy, not a claim that one model is universally best. Maintainers should
change the matrix, this rationale, and `tests/test_routing.py` together.

## Decision framework

Candidate order balances five concerns:

1. **Capability:** use a specialist where the role aligns with its specialization.
2. **Latency:** avoid spending maximum-model latency on short, mechanical work.
3. **Cost:** this provider uses a ChatGPT subscription rather than per-token API
   billing, so “cost” means quota/priority capacity and user wait time. There is
   no stable per-token price exposed by this backend on which to base routing.
4. **Availability:** subscription tier and staged rollout can expose different
   catalogs. A candidate is skipped when the resolver cannot find it.
5. **Fallback quality:** fallbacks broaden availability while remaining suitable
   for the role; they are not aliases and can change output or latency.

## Choices and tradeoffs

### Sol is the provider and general-purpose default

`gpt-5.6-sol` is the quality-first, broad-capability choice. A request that does
not declare a role should fail toward general usefulness rather than silently
opt into a speed- or code-specialized model. This costs more latency and likely
more subscription capacity than Luna; callers optimizing throughput should use
the `fast` role. Terra is the general fallback when Sol is unavailable.

### Luna leads the `fast` role

`gpt-5.6-luna` is selected for parsing, classification, file operations, and
other short utility work because rollout evaluation treats it as the
latency/capacity-optimized variant. Terra follows because it offers a better
general capability/latency compromise than escalating immediately to Sol. Sol
is last so the role remains available during partial rollouts, at the expense
of the very latency and capacity savings requested by `fast`.

### Coding routes Codex → Terra → Sol

Codex is first because its specialization matches implementation, debugging,
and repository work. Terra is the first fallback: coding usually benefits more
from its balanced throughput than from paying Sol's deliberation overhead. Sol
is the availability backstop and may be preferable for architecture-heavy code,
but making it second would increase routine coding latency. `ui-coding` starts
with Sol instead because visual interpretation and broad design judgment are
more important there than code specialization.

### Reasoning-heavy roles use elevated-effort Sol

`reasoning`, `research`, `security-audit`, and `critical-ops` choose Sol with
`reasoning_effort: high`; these roles have higher error costs and benefit from
deliberation enough to accept extra latency/capacity use. `critique` uses
`xhigh`, since its purpose is adversarially finding non-obvious flaws. Terra
retains the same effort as fallback so an availability fallback does not also
silently weaken the requested deliberation level.

Creative, writing, vision, and general UI work also prefer Sol for broad quality
and multimodal judgment, but do not force elevated effort. `image-gen` is only a
degraded text/SVG planning route: this provider does not expose native image
generation, so another image provider is required for raster synthesis.

## Evidence status

The following are **API/catalog facts** that can be checked against the live
`/backend-api/codex/models` response: model visibility for the authenticated
subscription, supported reasoning levels, context limits, input modalities,
and speed-tier metadata. The provider dynamically reads that catalog, and
catalog availability is known to vary by account and rollout.

The relative labels used above—Sol as broadest quality, Luna as fastest, Terra
as balanced, Codex as coding-specialized—and every candidate ordering are
**provisional rollout policy**. They are based on current naming, observed
behavior, and intended role fit, not a published benchmark or contractual SLA.
Relative quota consumption is also provisional because the backend publishes
no stable per-model price here. Do not turn these judgments into “facts” without
reproducible evaluation data.

## Revising the policy

Before changing an order, capture representative role prompts and compare task
success, p50/p95 latency, and quota/rate-limit behavior on every subscription
tier available for testing. Prefer an explicit model name during a staged
rollout; use globs only when suffix semantics are stable. Preserve at least one
broad-capability fallback, update the date in the matrix, revise the tradeoff
text here, and update the exact-order assertions in `tests/test_routing.py`.
