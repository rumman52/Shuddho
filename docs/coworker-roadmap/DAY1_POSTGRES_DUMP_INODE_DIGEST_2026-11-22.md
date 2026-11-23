# Day 1 D01.T06 / D01.G03 — stable PostgreSQL dump digest from one inode

**22 November 2026 · Asia/Dhaka. Evidence classification: source/repository CI only; controlled pilot NO-GO.**

## Contract, ownership, and scoped change

- **Parent:** [#737](https://github.com/rumman52/Shuddho/issues/737); [Day 1 #727](https://github.com/rumman52/Shuddho/issues/727); attached `01_Rukh_AI_Foundation(2).docx`, Part 01 pp. 3–5.
- **Owner:** C (platform and backup custodian), A (source code), D (independent reviewer). Existing state **D01.T06 ACTIVE / D01.G03 READY**; **no PASS** credit without actual authorized restore receipt.
- **Base main:** `4eee61c4389b507b95670203618c0ed980d5ccf8`.
- **Branch/PR:** `fix/day1-pg-dump-digest-one-descriptor-20261122`; [#893](https://github.com/rumman52/Shuddho/pull/893).
- **RED test-only:** `50edde5d1c7e6179dd39624942b1672b7993826b`; corrected fixture `531a8a7b4f628ab9d1822d055b12c4acf5dbe836`; [CI #45041258533](https://github.com/rumman52/Shuddho/actions/runs/45041258533) **4 expected FAILED, 424 PASSED** in the mandatory Coworker job. All failures were the newly introduced archive-digest regressions, not test import or collection failures.
- **Failure:** `scripts/staging_day2_archive_attestation.py::_file_sha` used `Path.is_symlink/is_file/stat` followed by an independent `Path.open('rb')`. This permitted a swapped symlink to determine the hash and had no same-inode growth or rewrite detection.
- **Expected behavior:** Open one `O_NOFOLLOW` regular file descriptor, require nonempty source archive, calculate SHA-256 using 1 MiB streaming chunks (no artificial dump-byte ceiling), and reject any size, mtime-ns or ctime-ns changes while reading. Preserve existing hash format, 0070 original baseline and restored-source/archive binding, schema/ACL inventory and independent reviewer gate. Missing `O_NOFOLLOW` fails closed.
- **New regressions:** symlink replacement at descriptor open; append between initial metadata and read; same-size overwrite between metadata and read; legacy `Path.open` substitution after precheck must not affect hash. `tests/test_staging_day2_archive_attestation.py`.
- **Verification:** `uv run --locked --extra coworker pytest -q tests/test_staging_day2_archive_attestation.py tests/test_staging_preseed_baseline.py tests/test_staging_backup_restore.py`; confirm mandatory final-head Actions `test-and-build`, `coworker`, `browser-qualification`, `PostgreSQL 18 staging compatibility`, `Frontend tests and builds`, `PR head ancestry`, `ci-merge-gate`. A PR-only skipped `governance-audit` is not a main-push governance PASS.
- **Compatibility:** No public signature, migration, state schema, provider/model, owner/tenant permissions, UI, flags, budget, or network behavior changed. This digest check alone does not authenticate a dump's creator: C/D must still attest protected immutable receipts and actual hosted backup+restore provenance.

## Operator handoff and exact resume gates

1. **C/repository admin + independent reviewer — governance:** Configure `V01_RULESET_APP_CLIENT_ID` and `V01_RULESET_APP_PRIVATE_KEY` in protected `v01-governance` / `pa10-staging` environments through the approved secret store; run `uv run --locked --extra coworker python scripts/reconcile_main_ruleset.py --repository rumman52/Shuddho --expected-main-sha "$REVIEWED_SHA"` on the newly refreshed `main`. Owner-authorized admin reconciles native ruleset **27324410**, independently verifies one approval and strict three GitHub Actions checks, demonstrates denied unreviewed/failing and accepted independently reviewed changes. Preserve private audit receipt reference.
2. **C + Founder — authorized staging:** Select and approve actual Render workspace/API/worker and Supabase isolated restore DB/private object storage identity, billing, privacy, retention, recovery operator, two managed synthetic accounts, Temporal service and release SHA. Last read-only Supabase Alembic is `0070` while source expects `0072_merge_0071_heads`; staging API deploy is older than source with no dedicated persistent worker. Follow reviewed staging backup/restore runbook only after explicit authorization, run `attest-original` before seeding or migration, and later `prepare` and `verify` on separately approved origins. Store raw PostgreSQL/object/owner A-B HTTPS receipts in approved private location; do not include JWTs, fingerprints identifying accounts or private data in PR.
3. **Independent D — custody/qualification:** Supply outside-repository blinded 40-case holdout and negative developer-access evidence, immutable human scores and 20 operated PostgreSQL/Temporal/storage recovery cases (#665). Founder+C separately sign exact candidate digest GO; without this remain NO-GO. PostHog capture stays off absent privacy authorization.

**No hosted operation, production change, paid worker, schema migration, secret read/write, external send, telemetry activation, D-holdout access, or pilot enrollment.** The last working v4 ledger calculation (**18/100 task passes; 5/54 exit passes; 0/10 accepted days**) is historical and unmodified; do not count source improvements as operated PASS.

## Completion evidence

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Source correction staged in draft PR | See exact head and diff |
| Repository-verified | Pending full exact-head required CI and independent review | [PR #893](https://github.com/rumman52/Shuddho/pull/893) |
| Staging-verified | Blocked — real independent restore, owner A/B, paired API/worker not authorized | C/Founder private receipt ID required |
| Production-qualified | Blocked — blind D, recovery cases, governance, frozen release | Independent D / Founder+C receipts required |
| Activated | No | Controlled pilot NO-GO |

