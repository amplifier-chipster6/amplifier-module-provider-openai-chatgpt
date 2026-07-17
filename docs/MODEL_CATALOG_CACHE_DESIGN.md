# Validated Persistent Model Catalog Design

**Status:** Proposed

**Issue:** AMP-10

**Scope:** Design only; implementation is intentionally separate from the GPT-5.6
provider pull request. Nothing in this proposal blocks that pull request.

## Goals and non-goals

The provider should normally discover the models available to the currently
authenticated ChatGPT account from the live catalog endpoint. A validated,
last-known-good (LKG) response should survive provider and process restarts so a
temporary backend failure does not immediately expand the hardcoded model list.
The built-in catalog remains only a small bootstrap/emergency option.

The persistent catalog is a discovery aid, not an entitlement or routing
authority. A cached model may have been removed or the account's subscription
may have changed; the inference endpoint remains authoritative and its errors
must be returned normally. This design does not make a stale catalog fresh,
merge catalogs between accounts, infer access from plan names, or cache OAuth
credentials.

## Current state

Each `ChatGPTProvider` instance keeps `(time.monotonic(), list[ModelInfo])` in
memory for `models_cache_ttl` (one hour by default). After expiration it fetches
`GET /backend-api/codex/models`. Any exception or an empty filtered response
returns the full static `FALLBACK_MODELS`; fallback data is not cached. The
in-memory cache has no schema validation beyond conversion, does not survive a
restart, and has no account identity attached to it.

## Proposed data flow

Catalog selection returns an internal result containing `models`, `source`
(`live`, `memory`, `disk_fresh`, `disk_stale`, or `emergency`), `fetched_at`,
and `age_seconds`. Only `models` is exposed through the existing provider
protocol; the remaining fields feed structured diagnostics.

1. Ensure valid tokens and obtain the current `account_id`. If a stable account
   identity is unavailable, do not read or write persistent catalog data.
2. Derive the account-scoped cache key and check the validated in-memory entry.
   A fresh entry is returned immediately.
3. Under the existing per-provider asynchronous lock, read and validate the
   account's disk entry. Return it if fresh. A valid but stale entry is retained
   only as a candidate; it is not yet returned.
4. Fetch the live catalog using the current access token and account header.
   Validate and normalize the complete response before changing either cache.
5. Atomically persist the validated envelope, then update memory and return the
   live catalog. A failed disk write does not discard a valid live response.
6. If the fetch has a stale-eligible failure, return the validated stale
   candidate. If there is no candidate, return the minimal emergency catalog.
7. If the failure is not stale-eligible, do not use stale account metadata.
   Preserve current API compatibility by returning the emergency catalog from
   `list_models()`, while recording the precise failure class. Authentication
   and inference operations remain unaffected and must still surface their own
   errors.

The lock is double-checked after acquisition. A later implementation may add a
cross-process advisory lock to reduce duplicate fetches, but correctness does
not depend on it: atomic replacement and independent validation make concurrent
writers safe, and the last complete valid response wins.

```text
list_models
    -> current account identity
    -> fresh memory? ------------------------------> return memory
    -> valid account-scoped disk
         -> fresh? --------------------------------> return disk_fresh
         -> stale? retain candidate
    -> live fetch -> validate -> atomic persist ---> return live
         | temporary/invalid response + candidate -> return disk_stale
         | otherwise ------------------------------> return emergency
```

## Cache location and ownership

Add an optional `models_cache_path` configuration. Its default is
`~/.amplifier/cache/openai-chatgpt/model-catalog-v1/`. The **provider module**,
not Amplifier core and not the OAuth helper, owns the format, validation,
retention, migration, and diagnostics. Keeping it separate from the token file
allows token cleanup without silently changing catalog policy and prevents a
catalog write from damaging credentials.

Each file is named `<account-key>.json`, where `account-key` is the lowercase
hex SHA-256 digest of a domain-separated string containing the OAuth issuer and
exact `account_id` (for example,
`openai-chatgpt-model-catalog-v1\0https://auth.openai.com\0<account_id>`). The
raw account ID, access token, refresh token, email, and token-file path are never
stored in the envelope or emitted in logs. A custom cache path is a directory,
not a shared single file.

The directory is created for the current OS user with mode `0700`; cache files
and temporary files use `0600`. Existing files with broader permissions are
rejected and quarantined rather than silently trusted. Symlinks are not
followed when opening an existing cache entry. Deployments that intentionally
share a Unix account also share its local trust boundary, but entries still
remain separated by authenticated ChatGPT account ID.

## Versioned envelope and validation

Persist JSON rather than serialized Python objects. Version 1 has this logical
shape:

```json
{
  "schema_version": 1,
  "provider": "openai-chatgpt",
  "account_key": "64 lowercase hexadecimal characters",
  "fetched_at": "2026-07-16T12:34:56Z",
  "models": [
    {
      "slug": "gpt-5.6",
      "display_name": "GPT-5.6",
      "context_window": 272000,
      "max_context_window": 272000,
      "additional_speed_tiers": ["fast"],
      "supported_reasoning_levels": ["low", "medium", "high"],
      "visibility": "list",
      "supported_in_api": true
    }
  ]
}
```

Validation happens after live fetch and again on every disk load:

- The top level must be an object with exactly the understood schema version,
  provider ID, recomputed account key, parseable UTC timestamp, and model list.
- The document is bounded (proposed maximum 1 MiB and 500 entries) before full
  processing. The catalog must contain at least one usable entry.
- Every entry must be an object with a non-empty, bounded `slug` matching a
  conservative ASCII model-ID pattern, a bounded display name, positive bounded
  integer context windows, and correctly typed lists of bounded strings.
  Boolean values are not accepted as integers.
- Entries with `visibility == "hide"` or `supported_in_api != true` are not
  usable. Duplicate slugs, invalid fields, invalid synthetic `-fast` collisions,
  or zero usable entries reject the **whole** response; partial responses are
  never promoted to LKG.
- Only the allowlisted normalized fields shown above are persisted. Unknown
  backend fields are ignored, preventing accidental storage of sensitive or
  unbounded response data. Conversion to `ModelInfo` happens only after this
  validation.

An unsupported future schema is a cache miss, not an attempted best-effort
parse. A schema upgrade should use a new directory or explicit reader migration;
old files remain non-authoritative until successfully revalidated under the new
schema.

## Freshness, staleness, and invalidation

Keep `models_cache_ttl` as the **fresh TTL**, defaulting to one hour, and add
`models_cache_max_stale`, defaulting to seven days. Age is calculated from the
persisted UTC `fetched_at` using a wall clock; negative age beyond a small clock
skew allowance is invalid. In-memory elapsed time may continue using a monotonic
clock. Recommended configuration constraints are `fresh TTL >= 0` and
`max stale >= fresh TTL`; zero max-stale disables stale reuse.

A catalog older than the fresh TTL triggers revalidation. It may be served up to
the max-stale boundary only for timeouts, DNS/connection errors, HTTP `408`,
`429`, or `5xx`, and structurally invalid/empty successful backend responses.
The last category is treated as a backend regression and must never replace the
LKG. Apply bounded retry backoff in memory so repeated callers do not hammer an
unhealthy endpoint; backoff must never extend the persisted timestamps.

Do **not** serve stale data after `401`/`403`, a missing or changed account ID,
an account-key mismatch, local permission failure, corruption, unsupported
schema, or expiration beyond max-stale. These conditions use the emergency
catalog (or a future explicit unavailable result) and retain a diagnostic. In
particular, a successful token refresh that resolves to another account selects
a different file immediately; it never relabels or copies the old catalog.

There is no push invalidation signal from the backend, so TTL refresh is the
normal invalidation mechanism. Operators can invalidate safely by deleting the
account file or cache directory. A future `clear_model_cache()` should accept
the current account only by default and require an explicit option to clear all
accounts. Changing validation schema or the backend's catalog semantics also
requires a schema/directory version bump.

## Atomic writes and corruption recovery

Persistence uses the standard same-filesystem replace sequence:

1. Serialize canonical JSON completely and enforce the size limit.
2. Create a uniquely named temporary file in the cache directory with exclusive
   creation and mode `0600`.
3. Write all bytes, flush, and `fsync` the temporary file.
4. Revalidate the serialized payload (or equivalently validate before and verify
   the complete byte count), then `os.replace(temp, destination)`.
5. `fsync` the directory where supported. Always remove abandoned temporary
   files on error.

Readers open without following symlinks where the platform supports it, bound
the bytes read, parse, and validate before use. Malformed, truncated,
permission-invalid, or schema-invalid files are atomically renamed to a unique
`*.corrupt-<timestamp>` name when safe, with a bounded retention count. If
quarantine fails, the entry is still ignored. Recovery then follows the normal
live-fetch/emergency path; corrupt content is never merged with live data.

## Trust boundaries and security properties

- **Remote boundary:** The undocumented ChatGPT endpoint is authenticated but
  still untrusted input. HTTP success alone does not make its JSON cacheable.
- **Identity boundary:** The current token's exact account ID determines the
  cache namespace. Plan type is descriptive and is never an identity key.
- **Local boundary:** The cache contains capability/availability metadata, not
  secrets, but it can influence model discovery. Restrictive permissions,
  no-symlink opens, bounded parsing, and atomic replacement reduce local
  tampering and denial-of-service risks. A hostile process running as the same
  OS user remains outside the protection this file cache can provide.
- **Authority boundary:** Fresh live metadata is preferred, stale metadata is
  explicitly labeled and temporary, and neither bypasses backend authorization.
  Callers must not use catalog presence as proof that a request will succeed.

## Failure modes and required behavior

| Condition | Cache mutation | Result |
|---|---|---|
| Valid non-empty live response | Atomically replace this account's LKG | Live models |
| Live response valid; disk write fails | Memory only; preserve old disk LKG | Live models plus write diagnostic |
| Timeout, connection error, 408/429/5xx | None | Valid in-window stale LKG, else emergency |
| HTTP 200 with invalid or empty catalog | Never promote response | Valid in-window stale LKG, else emergency |
| HTTP 401/403 | None | Never stale; emergency with auth diagnostic |
| Account ID missing or changed | Never access another key | Live fetch if identity exists, otherwise emergency |
| Disk file corrupt, oversized, unsafe, or wrong version | Quarantine/ignore | Live fetch, then emergency if it fails |
| LKG older than max-stale | None (optional later cleanup) | Never stale; live or emergency |
| Concurrent process writes | Complete atomic files only | Validate whichever complete file is observed |

The emergency catalog should be reduced to the smallest compatibility set that
the maintainers are prepared to support, ideally one conservative baseline
model without account-specific speed tiers or claims. Its entries pass the same
normalization validator at build/test time. It is labeled `emergency` in
diagnostics and is never persisted or inserted into the LKG memory slot, so the
next eligible call can retry live discovery.

## Observability and diagnostics

Emit one structured event (or structured log until provider metrics exist) per
catalog decision with: provider, source, freshness bucket, age rounded to
seconds, entry count, schema version, fetch duration, HTTP status class, and a
low-cardinality reason code such as `fresh_hit`, `stale_timeout`,
`validation_rejected`, `auth_rejected`, `cache_corrupt`, or `write_failed`.
Include a short prefix of `account_key` only if correlation is necessary; never
include raw account IDs, URLs with query data, response bodies, or tokens.

Recommended counters are fetch outcomes, source selections, validation
rejections, corrupt quarantines, and write failures. Recommended histograms are
fetch latency and served-cache age. Debug logs may include the configured cache
directory and schema version but not filenames containing anything other than
the opaque digest. Repeated identical failures should be rate-limited while the
counter continues to advance.

Expose catalog provenance in an internal diagnostic method or hook payload, not
by changing `ModelInfo`. This keeps the provider protocol stable while allowing
support tooling to say clearly that a list is stale or emergency-derived.

## Migration and rollout

1. Introduce a pure catalog-envelope validator and account-key derivation with
   no runtime behavior change. Validate the emergency constant in tests.
2. Add the disk store behind an opt-in `models_persistent_cache_enabled` flag.
   On first use there is no migration artifact: the existing in-memory entry has
   no account binding, so it must **not** be written to disk. Fetch live, validate,
   and seed the account-scoped LKG.
3. Make memory entries carry account key, source, and timestamps, then enable
   read-through/write-through persistence by default. Preserve
   `models_cache_ttl` semantics as the fresh TTL and document the new max-stale
   option and path.
4. Observe source/failure counters for at least one release. Reduce
   `FALLBACK_MODELS` only after stale recovery is proven, and keep an escape hatch
   to disable persistent reads/writes without disabling live discovery.
5. Remove the feature flag only after upgrade, downgrade, corrupt-file, and
   multi-account behavior has been exercised. Downgrade readers must treat the
   new cache as inert; no credential format changes are involved.

This migration deliberately does not serialize the current process cache and
does not prepopulate every account from the static list. Only a successful,
validated response fetched for the current account can establish an LKG.

## Implementation tasks

- Add typed normalized entry/envelope models and bounded validation, including
  synthetic variant collision checks.
- Add account-key derivation and an account-scoped `CatalogStore` abstraction
  with secure reads, atomic writes, quarantine, and retention cleanup.
- Refactor fetching to preserve failure categories/status codes rather than
  catching every exception identically.
- Refactor `_get_catalog()` to carry provenance, bind memory entries to account
  keys, apply fresh/max-stale policy, and add retry backoff.
- Add configuration parsing for cache path, max-stale, and rollout flag, with
  validation and README documentation.
- Add structured logging/hooks and low-cardinality metrics; document an
  operator cache-clear and diagnostics workflow.
- Shrink and build-time validate the emergency catalog only after the persistent
  path has shipped and been observed.

## Test plan

**Unit tests**

- Accept a minimal valid v1 envelope; reject wrong types, booleans-as-integers,
  missing/unknown schema versions, wrong provider/account key, duplicates,
  collisions, hidden-only, empty, oversized, over-count, and future timestamps.
- Prove account keys are deterministic, domain-separated, and different for two
  account IDs; prove raw identity and credentials never appear in stored JSON or
  logs.
- Exercise fresh, stale-eligible, max-stale-expired, zero-TTL, and clock-skew
  boundaries with a fake clock.
- Parameterize HTTP/network/validation failures to verify the table above,
  especially that 401/403 and account changes never return stale metadata.
- Simulate short writes, serialization errors, replace failures, crashes before
  replace, corrupt JSON, unsafe permissions, and symlinks. Assert the previous
  LKG remains complete and usable when appropriate.
- Verify emergency results are neither persisted nor installed as LKG and the
  next call retries live discovery.

**Concurrency and integration tests**

- Run concurrent callers in one provider and assert one live fetch; run two
  provider instances/processes writing the same account and assert every
  observed file is a complete valid envelope.
- Restart the provider with the backend unavailable and assert a valid
  account-matched LKG is selected; repeat beyond max-stale and assert emergency.
- Switch tokens between two accounts (including the same plan type) and assert
  no memory or disk catalog crosses the boundary.
- Seed corrupt, truncated, old-schema, over-permissive, and wrong-account files;
  assert quarantine/ignore, diagnostic reason, and successful live recovery.
- Verify a backend entitlement rejection during inference is surfaced even when
  the requested model appeared in a cached catalog.
- Verify opt-in/opt-out rollout, custom cache paths, upgrade from no cache, and
  downgrade behavior.

**Acceptance/operational tests**

- In an isolated home directory, fetch once, stop the provider, block the model
  endpoint, restart, and observe `disk_stale` without exposing credentials.
- Inspect file and directory permissions and interrupt a writer at each atomic
  write phase; no partial destination may be served.
- Confirm dashboards/log queries distinguish live, fresh, stale, and emergency
  selections and that reason labels remain bounded.

## Decisions to confirm during implementation

The proposed one-hour fresh TTL, seven-day maximum stale age, 1 MiB/500-entry
limits, quarantine retention count, and exact minimal emergency model are
operational defaults rather than protocol requirements. They should be reviewed
against observed catalog size and outage history before the feature flag becomes
default-on. The invariants that are not negotiable are complete validation,
atomic replacement, exact account separation, explicit stale provenance, and
never treating cached metadata as authorization.
