# Day 2 immutable API/worker build identity

## Goal

Close the Prompt 01 D02.T06 evidence gap: the current freeze records free-text build/deployment references, while runtime schema v2 and the worker registry expose no comparable build digest or schema identity. The current verifier can therefore freeze an API source revision without proving that the active worker fleet runs the same built artifact, schema head, model identity, or runtime capability set.

## Constraints

- Base is the verified main SHA 2262f9e694f9089866fa6476f5afa48fb78a8294; work stays on fix/day2-release-build-identity-20261128.
- Preserve the existing v2 runtime-manifest endpoint for compatibility. Add an explicit v3 endpoint and make only the staging freeze path consume v3.
- Add an additive migration after 0072_merge_0071_heads; do not apply it to hosted Supabase.
- Legacy worker rows remain readable but cannot qualify a v3 freeze. PostgreSQL trigger rejects new un-attested worker registrations after migration.
- Runtime identity contains no credentials, owner IDs, worker IDs, tokens, or user content.
- Build digest is a deterministic runtime build fingerprint over source SHA, project/lockfile hashes, interpreter identity and installed distribution inventory. It is not claimed to be a signed OCI image digest.
- Do not change Render, Supabase, GitHub rulesets, production, telemetry, or provider state. No deploy, migration, paid provisioning, or external action.

## Implementation sequence

1. Tests first: deterministic build fingerprint, tamper/symlink/invalid metadata rejection, runtime v3 exact schema, worker fleet mismatch/stale/legacy rejection, prepared-state build/schema/model binding, Day 2 receipt propagation, and 0073 migration graph.
2. Build fingerprint: add a pure shared runtime identity module that hashes the actual source/build inputs and computes the canonical 43-flag capability fingerprint and configured provider/model identity.
3. Worker registry: add nullable identity columns for legacy rows; add a PostgreSQL check constraint and replace the source-revision trigger with a fixed-search-path trigger that also requires matching transaction-local build/schema/model/capability attestation; pass runtime identity from the worker; expose only non-sensitive identity fields from worker inventory.
4. API v3: preserve /api/v1/runtime-manifest v2. Add /api/v1/runtime-manifest/v3, staging-only and cohort-gated, returning API build/schema/model/capability identity plus a sanitized, deterministic, healthy-worker identity set and fleet-ready status. No IDs or timestamps.
5. Release freeze: require the expected build digest, schema head and model identity in prepared state; fetch v3; validate exact schema, all active worker identities, heartbeat/lifecycle state, and API/worker parity; bind the stable worker inventory digest and v3 runtime-manifest digest into freeze evidence.
6. Day 2 execution/acceptance: use v3 and propagate the same immutable identity through run, recovery, restore and acceptance receipts. Reject v2-only, missing, changed, stale, or cross-release identity.
7. Migration verification: exercise the complete 0070 → both 0071 branches → 0072 merge → 0073 path in disposable PostgreSQL 17 and 18 CI. Keep the existing PostgreSQL 18 compatibility check; add PG17 without weakening any current gate.
8. Documentation: record exact test results, migration hold, and external gates in the Day 2 contract and progress ledger.

## Verification

- RED before implementation on exact-main source.
- Focused tests for build identity, API v3, worker registry, freeze, Day 2 execution/acceptance and migration graph.
- Full Coworker and application CI; PostgreSQL 17 and 18 migration rehearsal.
- Inspect actual logs and test output; no skips or altered thresholds.
- Verify exact final branch SHA and remote file blobs.
- PR remains draft until exact-head CI, native ruleset enforcement and independent review are complete.

## Rollback

Source-only revert through a protected, independently reviewed PR. The additive migration is not applied to hosted staging; if it is later applied, rollback requires a separately reviewed schema/data recovery plan. Do not remove new identity columns or weaken the trigger to make legacy workers register.
