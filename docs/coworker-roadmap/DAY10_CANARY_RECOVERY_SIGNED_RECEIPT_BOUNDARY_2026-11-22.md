# Part 05 / Day 10 — signed recovery receipt read boundary

**Date:** 2026-11-22. **State:** source-only PR #897; independent review and operated release remain **NO-GO**. Base source SHA `4eee61c4389b507b95670203618c0ed980d5ccf8`.

## Scope and authority

The independent-human Part 05 Day 9 recovery matrix and Day 10 controlled-cohort handoff require authenticated, immutable first evidence. A release HMAC chain authenticates the bytes signed; it does not make a permissive parser safe or prove the signed bytes were the bytes from which an expansion epoch was computed.

This change is limited to `scripts/cohort_canary_progression.load_recovery_epoch`: an existing signed `recovery_verified` ledger entry can establish a *new health observation epoch* only if its verified recovery artifact is unambiguous, bounded, an ordinary unlinked file, and its digest matches **the same bytes consumed by the parser**.

## Before/after

Before: `json.loads(recovery_path.read_text())` accepted duplicate keys, symlinked final components and unbounded reports; later `file_sha256(recovery_path)` independently reopened the pathname. An intervening file switch could make a new timestamp in the parsed object appear to be attested by the HMAC digest of a different, older recovery file.

After: the operator delegates recovery parsing and hashing to existing `scripts.ruke_pilot_eval._read_json_and_sha256`, which reads a single bounded regular descriptor with `O_NOFOLLOW`, rejects duplicate/nonfinite JSON and computes SHA-256 from the exact bytes parsed. The ledger `artifact_sha256.recovery_verification` comparison uses that saved digest rather than reopening the path.

No change to schema 1/v12 predicate meanings, ledger/HMAC key, stop/rollback/recovery order, cohort limits, history windows, STOP/HOLD, or pilot enrollment.

## Real test-first cycle

The four tests in `tests/test_cohort_canary_progression.py` were committed **before** the production correction, commit `74fdbb97c9b019c1cff8e2850464e2368c2fbc67`. They build and verify a real **synthetic signed release ledger**, including HMAC evidence hashes:
- A valid signed receipt containing two `verified_at` keys must be rejected.
- A signed receipt accessed through a symlink must not create an epoch.
- A validly signed but oversized receipt cannot bypass parser bounds.
- A controlled after-parse replacement must not let a newly read timestamp be validated by a separately opened earlier signed file. The test patches the later SHA call rather than the strict reader.

[Test-only GitHub Actions #45050033627](https://github.com/rumman52/Shuddho/actions/runs/45050033627) yielded **4 FAILED / 3,683 PASSED / 107 SKIPPED / 6 WARNINGS** in the Python build job, all four from these regressions, each reporting the expected “DID NOT RAISE.” No mock-custodian trace is credited as operated evidence.

Minimal production source commit: `3d1c59b303a0b6da74ab81a4ec206dcbaf463c06`. Require exact-final-head GitHub Actions (Python, Coworker, browser, frontend, PG18) before calling source verification green.

## Residual review limits

The rollout manifest for canary evaluation and the separate v12 rollout hash are still accepted by different calls on the generic caller path. This narrow patch binds the **recovery-verification** receipt, not every separately read source. Evaluate the rollout read/hash TOCTOU on its own bounded review before relying on a v12 expansion; direct rollout validation is being separately hardened in draft PR #895. A native repo admin must enforce required checks and independent review; as of this checkpoint the main ruleset required 0 reviews and no required CI contexts.

The operator's HMAC chain is a cryptographic source-evidence check, **not proof of owner C's real staging restoration**. The required 40 protected first attempts/80 blind scores and 20 distinct operated PostgreSQL/Temporal/private storage scenarios, exact 43 flags and authenticated API/worker/schema/model, live quality, Founder+C separate signoff and separately authorized 5–10 admission remain unobserved. Staging Supabase read-only `shuddho-staging` was PG17 migration `0070`. Render read-only inventory located `shuddho-api-staging` at live deploy `0e0b662fad0a02817a79a4514abba8f94e0ad022` (2026-11-14) and `shuddho-api` at live deploy `1f6dae72e1de6f38ec4d9cf60180d856dbecb403` (2026-11-09); **neither matches current main `4eee61c4389b507b95670203618c0ed980d5ccf8`**, and no worker/source/schema runtime equality was attested. Staging auto-deploy is disabled. Vercel connected to unrelated `ali` repo and ProductOS to unrelated `Dust2Glow`; PostHog project 675660 reported no ingested event. Do not deploy or fabricate activation from these inventories.

**D10.G01–G08, D09.G01–G06 and pilot GO remain blocked on independent owner-operated evidence.** Historic v4 baseline 18/100 tasks, 5/54 exits, 0/10 days remains historical.
