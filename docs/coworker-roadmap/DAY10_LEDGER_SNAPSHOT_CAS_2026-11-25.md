# Day 10 — release-ledger evidence snapshot and append CAS (25 November 2026)

**Scope: Part 05 section 2. SOURCE ONLY / controlled pilot NO-GO.** This is a bounded review task, not an activation, staging qualification or claim that CW-17–CW-20 are complete.

## Task contract

- Base: `67d187f972c8069e4369ebc9fdb28dae55c40e3f`; draft [PR #911](https://github.com/rumman52/Shuddho/pull/911).
- Test-only commit `e47a16c382ab997987a131030aaf3b452ca11f6e`.
- Source commit `f0a7b26208c76fa70488f0264ddeb5eda593659d`.
- Additional test commit `5235f11f30b55904d33d7defad77ae9d0b9f3d17`.
- Existing interfaces: signed JSONL, SHA-256/HMAC, strict bounded no-follow receipt parsing, verified history, fsynced atomic replacement. No event/schema/key changes; no new ledger or service.
- Files: scripts/cohort_release_ledger.py; tests/test_cohort_release_ledger_concurrency.py; this contract; PROGRESS.md.
- Acceptance: validated JSON and signed SHA must describe the identical bytes; concurrent writers cannot both report success for an overwritten entry; a stale writer gets an explicit conflict and must revalidate before retry. All 20 append entry points must use the same commit boundary. Preserve prior schema/HMAC validation and existing activation requirements.
- Tests: default `uv run pytest -q` and mandatory CI. Initial deterministic tests deliberately replace a receipt after validation and interleave concurrent readers before writes.

## RED / source implementation

[Actual test-only Actions run 45558085273](https://github.com/rumman52/Shuddho/actions/runs/45558085273), job test-and-build: **2 failed, 3818 passed, 109 skipped, 6 warnings**. The two failures are the new digest-substitution and lost-append regressions, not expected release results. Two successful callers signed different entries with sequence 1, but only one entry was persisted.

The per-append snapshot now uses the existing strict JSON parse-and-SHA reader. Subsequent hash references reuse that digest; hash-only artifacts retain their streaming reader and per-append digest cache. The commit boundary opens a private regular no-follow sidecar, locks it with POSIX flock, rereads the canonical history, rejects a stale expected history, and uses existing atomic write. All 20 append paths use the boundary. Lock files are persistent: never unlink a lock that a different writer may hold. No schema version or historic entry bytes/HMAC semantics have changed.

[Source-head CI 45558319034](https://github.com/rumman52/Shuddho/actions/runs/45558319034): the Run Python tests step reported success before the additional test commit; that is not final-head or mandatory full-CI acceptance. Additional regression coverage includes distinct processes, fresh retry, linked lock rejection, failed write without history mutation, and rollback receipt substitution. Check exact final PR head and all mandatory jobs before any repository-level acceptance. No independent human review has been received.

## Operator boundary

Use a private operator-owned directory on a filesystem that supports POSIX advisory locks and atomic rename. All writers must use the updated append protocol and the same ledger/sidecar; mixed old writers, direct edits, untrusted directory mutation and unverified distributed filesystems are outside this guarantee. Keep lock files with the ledger; do not delete them to clear contention. Preserve original evidence in custody. On conflict, verify the current signed chain using the existing verify command, reacquire fresh inputs/receipts, rerun the relevant release checks and only then issue another authorized append. Never blindly replay stale bundle authorization. Missing, linked, malformed, or oversized parsed evidence remains fail-closed. This patch does not authenticate a human custodian, guarantee a cross-file atomic snapshot or demonstrate real hosted rollback.

## Remaining production qualification gates

Baseline [main CI 45351544500](https://github.com/rumman52/Shuddho/actions/runs/45351544500): frontend, browser, PostgreSQL 18 compatibility, test-and-build, coworker passed; governance and merge gate failed. Audit log explicitly reports missing GitHub App client-id. Native ruleset 27324410 is active but has zero required approving reviews and no required status checks; no bypass or mutation attempted.

Supabase shuddho-staging was ACTIVE_HEALTHY (PostgreSQL 17.11.0.003), read-only SQL `shuddho_coworker.cw_alembic_version=0070`. Render service read requires explicit workspace selection; no service-level claim, deployment or provision. No authorized frozen API/worker pair, provider budget, approved telemetry destination or independently controlled holdout was established.

- CW-17 / V-03: actual matched 40+40 provider executions and economics, fresh protected 40 holdout attempts, 80 original blinded human ratings, adjudication, security checks and independent review remain missing. Comparator 160 judgments only when authorized; no fabricated results.
- CW-18: live capacity/load and defined SLI observation not operated; 99.9% is a target. PostHog remains unapproved (#584); no data captured.
- CW-19: 20 Day 9 recovery receipts and separate transaction 16-case operated qualification, exact golden workflow, rollback/pause/cancel/isolation and isolated restore remain missing.
- CW-20 / V-02 / V-04: source freeze enumerates 43 explicit flags and one derived API indicator, not a deployed attestation. Exact candidate and matching model/worker/schema/build/digests, authentic separate Founder and Owner C approvals, independent D custody (#665), then separate cohort authorization are required. #735, #736 and #737 remain open. No admission or public launch.
- V-01: final exact-head CI, native governance enforcement and independent review remain required; no production changes.

Completion level: proposed source implementation and observed initial RED / source Python GREEN; final repository verification pending, staging not operated, production not qualified, activated no. Keep canonical NO-GO until actual mandatory evidence passes. Historical 18/100 task, 5/54 exit, 0/10 accepted-day credits are not increased by this source patch.

