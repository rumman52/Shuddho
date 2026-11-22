# Part 01 / D01.T06, D01.G03 — private backup evidence fail-closed input

**22 November 2026 · Asia/Dhaka.** **SOURCE_ONLY / controlled pilot NO-GO.** This is a local evidence-integrity correction, not a live backup or restored-service acceptance receipt.

| Contract | Evidence |
| --- | --- |
| Parent and Day 1 authority | [#737](https://github.com/rumman52/Shuddho/issues/737), [#727](https://github.com/rumman52/Shuddho/issues/727), attached Rukh AI Foundation Part 01, pp. 3–5 |
| Owner / acceptance state | C (platform/security), D independent observer; D01.T06 **ACTIVE → ACTIVE**, D01.G03 **READY → READY** pending operated proof |
| Exact base `main` | `e12f9832fb8b495bb30e6a81e125906b53508832` |
| Branch / PR | `fix/day1-private-restore-evidence-preflight-20261122`; [draft PR #889](https://github.com/rumman52/Shuddho/pull/889) |
| RED test-only commit | `d1eebf6cb00626ae5a1b935651a7dc33f915fbc7`, [Actions #45033865833](https://github.com/rumman52/Shuddho/actions/runs/45033865833) |
| Tested contract | Source-controlled offline recovery receipt intake and local private output preflight; no hosted execution, model use, or API/schema change |
| Prior state → intended behavior | Separate `is_symlink`/`is_file`/`stat` and later `read_text` allowed swapped path and growth; permissive JSON accepted duplicate or nonfinite values; restore verify read prepared/base receipts without secure reader and reached restored target even when output already existed |

## Reproduced original defect

**RED** at exact test-only commit above, mandatory `coworker` job in [CI #45033865833](https://github.com/rumman52/Shuddho/actions/runs/45033865833): **11 expected FAILED, 411 PASSED**. Five negative restore-preflight cases reached the deliberately forbidden target access, and six shared loader cases accepted invalid input when `ArchiveAttestationFailure` was required. The lightweight application test job does not exercise this dependency-gated set; the Coworker job is the relevant proof. These are synthetic local attack simulations, **not** a demonstrated production breach.

The fix in `scripts/staging_day2_archive_attestation.py::_private_json` opens one `O_NOFOLLOW` descriptor, verifies its inode through `fstat`, bounds reads to 2,000,001 bytes and fails if the consumed content exceeds 2,000,000. It parses only those bytes and rejects duplicate keys at any nesting depth and nonfinite JSON values. No second pathname read occurs.

`scripts/staging_backup_restore.py::verify` now uses that same reader for the prepared state and optional prior evidence, and preflights the private immutable output destination **before** it creates the restored target container or invokes managed identities. This preserves the existing source and restored DB+object fingerprint checks, original 0070 preseed baseline, mandatory PostgreSQL/S3 archive/restore receipts, owner A/B HTTPS positive/negative tests, and default-off staging guard.

## Repository verification and independent gates

Reproduce with `uv run --locked --extra coworker pytest -q tests/test_staging_day2_archive_attestation.py tests/test_staging_backup_restore.py tests/test_staging_preseed_baseline.py`, then verify all required exact-head CI. The original RED job must remain visible; source green does not establish operating success. Record final SHA, Python pass/fail/skip, mandatory Coworker steps, browser/frontend/PostgreSQL checks and `ci-merge-gate`. A PR-only governance skip is expected, **not** a main-push governance pass.

**C / administrator**: configure scoped App credentials in protected governance environments, reconcile effective main ruleset `27324410` to require one independent review and strict first-party `test-and-build`, `coworker`, `ci-merge-gate`, then prove rejected unreviewed/failing and accepted independently reviewed passing merges. No native rule mutation in this PR.

**C / Founder**: approve intended Render workspace, private backup/restore destination, capacity, retention, privacy, bounded spend and worker/Temporal/private object resource identity. Connected Supabase `shuddho-staging` is PostgreSQL 17.11 and Alembic **0070** versus source `0072_merge_0071_heads`; staging API on Render remains an older `0e0b662f...` build, autoDeploy off, with no dedicated worker in the connected inventory. Without owner-approved isolated restore and two managed synthetic identities no operated receipt can be recorded. C resumes the reviewed backup/restore runbook from exact release SHA and archives raw operator receipts only in approved private storage.

**Human D**: replace 40 developer-readable candidates with independent access-isolated holdout, prove D access and developer denial, human-score real first attempts and run 20 operated recovery cases ([#665](https://github.com/rumman52/Shuddho/issues/665)). **Founder + C** must separately authorize identical frozen release digest for GO. PostHog telemetry remains off pending privacy approval; connected Vercel/ProductOS contexts do not establish this Shuddho release.

No secrets, private inputs, schema migrations, cloud deployments, paid worker, provider inference, telemetry, pilot enrollment or production flags were changed. Historical v4 18/100 tasks and 5/54 exits remain dated; do not advance unsupported operational PASS credits.
