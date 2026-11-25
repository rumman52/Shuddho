## 25 November 2026 — PA-10 reminder expiry at admission

**Source correction; staging qualification remains blocked.** Inspected main `67d187f972c8069e4369ebc9fdb28dae55c40e3f`; [baseline CI](https://github.com/rumman52/Shuddho/actions/runs/45351544500) reports application and coworker success but governance-audit and ci-merge-gate failure. On `fix/pa10-reminder-expiry-admission-20261125`, [test-first commit](https://github.com/rumman52/Shuddho/commit/cd8869f1a0ff7b23371b3845ca36f4b7a7a045b3) adds two parameterized SQLite/API regression cases for a reminder due before expiry but admitted at or after expiry, including stable replay and zero notifications/runs. [Source commit](https://github.com/rumman52/Shuddho/commit/4c1661a5b010717350470c90d5beba88f39084d9) uses one fresh admission timestamp and rejects expiry at the later of admission and due time, consistent with ordinary scheduled Agent admission.

Isolated Python predicate reproduction: two failing subcases before; two test methods (four cases) passed after. Full integrated pytest and exact-head CI are not yet verified; local clone failed DNS resolution. No staging scenario has been qualified by these tests. No production flags, deployment or billing changed. Render inventory contains no persistent staging worker; Supabase staging is healthy but this alone is not application qualification. Issue #291 requires fresh billing authorization and approved credentials. Next: review PR, run exact-head CI and independently qualify frozen staging before activation. See [bounded task contract](PA10_REMINDER_EXPIRY_ADMISSION_2026-11-25.md).

## 24 November 2026 — Day 10 release-ledger operator-receipt pre-sign boundary ([draft PR #908](https://github.com/rumman52/Shuddho/pull/908))

**SOURCE CORRECTION; controlled pilot remains NO-GO.** Base `main=a3e8dba039436e2553d10f2147f886cdf1877815`. Merged #901 hardened reading signed JSONL *history* but left `scripts/cohort_release_ledger.load_json_object` using permissive, unbounded, link-following JSON at **event-creation time**. An early duplicate `STOP_ROLLOUT` followed by `ELIGIBLE_FOR_EXPANSION` could be shadowed before creating a seemingly valid HMAC-signed `stage_approved` event. Test-only commit `8dfdf9aaab3a35d14e41430e172c522e506d340e` added six synthetic signed-ledger checks. [Actual RED Actions #45246504107](https://github.com/rumman52/Shuddho/actions/runs/45246504107) Python **4 failed / 3,783 passed / 109 skipped / six warnings**, all four from newly exposed missing rejections (duplicate stage decision, symlinked rollout, oversized canary plan, nonfinite cohort cap). Existing directory-to-domain-error and valid signed-history cases passed, so neither is credited as RED. Minimal source fix `ace514e03d114b6f91040904c879e2cb3e804d75` uses the existing 4MB strict bounded, no-follow regular JSON reader with `ReleaseLedgerError` wrapping. [Task contract](DAY10_LEDGER_OPERATOR_RECEIPT_TRUST_BOUNDARY_2026-11-24.md) and [Superpowers execution plan](../superpowers/plans/2026-11-24-day10-ledger-operator-receipt-boundary.md). Source-head and **exact final-head GREEN require independent CI readback**; unverified work is not counted.

Separate `file_sha256` reread and ledger append races remain explicit residual issues; this fix does not prove parse/hash same bytes, prior-event authentication across custody boundaries, or operated restoration. Read-only Supabase `shuddho-staging` ACTIVE_HEALTHY PG17.11.0.003 still Alembic `0070`; Vercel and ProductOS connected only unrelated projects, PostHog default project 675660 reported no ingested events, Render workspace not independently selected for service inspection. GitHub active main ruleset 27324410 still requires **zero approving reviews and no required CI checks**; prior #901 actually merged without review while `ci-merge-gate` failed. Part 05's independent D 40 fresh first attempts/80 blinded judgments, 20 actual C/D operated recoveries, matching 43 explicit flags and release API/worker/schema/model identity, quality/rollback/cancel/pause/golden, Founder+Owner C signed releases, distinct 5–10 authorized HTTPS member admissions remain blocked. No deployment, migration, paid provider run, telemetry capture or pilot admission. Historic v4 baseline **18/100 tasks, 5/54 exits, 0/10 days accepted** unchanged.


**Post-fix regression investigation:** [First implementation final-head CI #45247132455](https://github.com/rumman52/Shuddho/actions/runs/45247132455) exposed **2 failed / 3,785 passed / 109 skipped / 6 warnings** in old `test_cohort_canary_progression` because the legacy test fixture corrupted recovery verification **before** asking the now-strict signer to sign it. The signer correctly rejects that input. Test helper commit `727b5abe8e819c0937f9749cfb862e05760dadd6` now creates a valid HMAC-signed recovery ledger first and mutates its receipt *after* signing, retaining the original downstream canary rejection tests without weakening production. Fresh exact head CI still required before crediting GREEN.

---

## 23 November 2026 — signed release-ledger history trust boundary ([draft PR #901](https://github.com/rumman52/Shuddho/pull/901))

**SOURCE ONLY; production qualification and pilot NO-GO.** Current baseline `main=e8d3e3c8180eaba2065468bf31f2dba96d682664`. `scripts/cohort_release_ledger.read_entries` accepted shadowed JSONL `event_type` keys, nonfinite signed numbers, linked ledger path and oversized file content, and leaked `IsADirectoryError` rather than failing with its contract exception. A later duplicate `hold` could keep the original canonical HMAC valid even with an earlier hidden STOP. Six tests were committed before production (`f9654ef72e317623b6059c17aa28041d11d0c6ef`; corrected valid oversized test `c092becf7a29131ddecd14015eb61afc0aa72adb`). [Corrected test-only RED #45225809032](https://github.com/rumman52/Shuddho/actions/runs/45225809032) **5 failed / 3,727 passed / 107 skipped / 6 warnings** in default Python, all expected missing fail-closed behaviors. Source patch `cfbe50b4ce30431e56d2f991d7119404cd72d28c` reads one regular no-follow inode, applies 4 MB/row and 64 MiB total caps, strict JSON duplicate/nonfinite rejection and domain errors, while preserving old event schemas/HMAC and empty-ledger semantics. [Source-head GREEN #45226323848](https://github.com/rumman52/Shuddho/actions/runs/45226323848) `test-and-build`: **3,732 Python passed / 107 skipped / 6 warnings, 551 JS passed**; other jobs and final doc-head run must be checked separately. See [Day 10 task contract](DAY10_SIGNED_RELEASE_LEDGER_JSONL_BOUNDARY_2026-11-23.md) and [TDD plan](../superpowers/plans/2026-11-23-day10-signed-release-ledger-jsonl-boundary.md).

Repository-level source correction does **not** authenticate operated staging, real custody or launch. GitHub ruleset 27324410 still requires zero approving reviewers and has no required CI contexts; there is no independent review of this PR. Supabase `shuddho-staging` read-only SQL still `0070` on PG17.11.0.003; Render service inventory requires user-confirmed workspace; Vercel and ProductOS linked only unrelated projects; PostHog default 675660 has no ingested events or attested Shuddho link. Part 05 D09/D10 requires protected human D first-run 40-case/80-blind-score/20-real-operated recovery proof, frozen API/worker/schema/model and all 43 explicit capability flags, live quality, rollback/cancellation/pause/golden isolation, separate founder+Owner-C approvals and independent 5–10-member HTTPS admission. **Not performed.** No deployments, migrations, telemetry, paid inference, external sends, release switches or pilot admissions. Historical v4 baseline **18/100 tasks, 5/54 exit checks, 0/10 accepted days** unchanged. Residual: ledger `load_json_object`, separately reopened SHA paths, and mutable append behavior remain separate review areas.

---

## 23 November 2026 — Day 1 rollout-manifest same-inode read stability ([PR #902](https://github.com/rumman52/Shuddho/pull/902))

**SOURCE_ONLY / controlled pilot NO-GO; D01.T06/G03 remain not PASS.** Starting from `e8d3e3c8180eaba2065468bf31f2dba96d682664`, reproduced a distinct `scripts/staging_release_evidence.py::_read_rollout_manifest` integrity gap: even though a single no-follow fd hashes the parsed bytes, concurrent in-place JSON replacement/append/EOF rewrite can return a digest and release ID from unstable source bytes. Test-only `4b1e71485593abf2eb04864545503878bd1fe672` produced **3 expected FAILED / 3,726 PASSED / 107 SKIPPED** in [required `test-and-build` CI #45225593317](https://github.com/rumman52/Shuddho/actions/runs/45225593317). Bounded proposed fix checks final `fstat` before descriptor close, stable metadata and consumed byte count. Full exact-GREEN SHA/CI and independent review are not yet recorded. [Contract](DAY1_ROLLOUT_MANIFEST_STABLE_READ_2026-11-23.md).

Fresh read-only inventory: native ruleset 27324410 still 0 approvals and no required checks; Supabase private schema 0070/84 tables, 0 Auth users/objects; Render API staging deployed old 0e0b662f..., autoDeploy off, no worker in workspace; connected Vercel project points at unrelated repository, ProductOS demo unrelated, PostHog unapproved for capture. No D held-out replacement/custody, isolated operated SQL/S3/Temporal recovery, Founder+C budget/privacy/release GO. No cloud changes, migration, paid worker, external send or user enrollment. Historical v4 credits not altered.

---

## 23 November 2026 — Day 10 canonical cohort release manifest / first evidence read ([draft PR #900](https://github.com/rumman52/Shuddho/pull/900))

**SOURCE FIX / controlled pilot NO-GO.** Baseline main `01314ce5e6502b48d85852324b9208bd1f72873b`. Canonical `scripts/cohort_release_gate.py` used permissive `json.loads(Path.read_text())` for the release manifest, independently reopened the pathname to compute `rollout_sha256` after evidence reads, and overwrote output at 0644 by default. [Contract and residual blockers](DAY10_RELEASE_MANIFEST_EVIDENCE_INTEGRITY_2026-11-23.md), [execution plan](../superpowers/plans/2026-11-23-day10-cohort-release-manifest-receipt-integrity.md). Test-first commit `11e8378d5fbadc8b9020d72c7524557fd9267807` added eight synthetic tests. Observed Python **RED 7 failed / 3,701 passed / 107 skipped / six warnings**, all new expected assertions, in [Actions #45064988770](https://github.com/rumman52/Shuddho/actions/runs/45064988770). Production fix commit `392c3c7e3ed172a425be48bbcb212142fe90f97f` uses existing strict bounded no-follow one-read parse+SHA and exclusive fsynced private output; preserves caller dict API and canonical decision/rollout conditions. **Inspect full exact-final-head CI before marking repository verification green.**

Read-only: Supabase staging ACTIVE_HEALTHY PG17.11.0.003 SQL Alembic `0070`; Vercel / ProductOS mapped to unrelated projects; Render workspace not selected, so no service claims; PostHog default project not ingesting, no privacy approval. GitHub native independent review / status enforcement still missing. No migrations, deployments, paid/owner operations, provider execution, telemetry, 43 runtime flag attestations, protected D custody, 40 first attempts, 80 blind ratings, 20 operated recoveries, founder/Owner C approvals, or 5–10 member admission. Historical baseline 18/100 tasks, 5/54 exits, 0/10 days unchanged. **No pilot GO.**

---

## 22 November 2026 — Day 10 signed canary recovery read and digest boundary ([draft PR #897](https://github.com/rumman52/Shuddho/pull/897))

**SOURCE_FIX ONLY; controlled pilot NO-GO.** Base main `4eee61c4389b507b95670203618c0ed980d5ccf8`. Found that `scripts/cohort_canary_progression.load_recovery_epoch` parsed arbitrary-sized, linked and duplicate-key recovery JSON with `Path.read_text/json.loads`, then separately reopened its path via `file_sha256` for a signed-ledger digest comparison. A pathname swap allowed a parsed later `verified_at` timestamp to be credited against **different** HMAC-signed bytes. Four synthetic real-HMAC-ledger tests were committed first (`74fdbb97c9b019c1cff8e2850464e2368c2fbc67`) and [test-only Actions #45050033627](https://github.com/rumman52/Shuddho/actions/runs/45050033627) **observed 4 failures / 3,683 passes / 107 skips / six warnings**, all the intended missing rejections (duplicate timestamp, symlink, oversized receipt, controlled after-parse replacement). Minimal production fix `3d1c59b303a0b6da74ab81a4ec206dcbaf463c06` uses a single strict bounded no-follow parse+SHA descriptor and compares that digest to the ledger; [scope and residual read/hash review](DAY10_CANARY_RECOVERY_SIGNED_RECEIPT_BOUNDARY_2026-11-22.md). Exact final-head CI **must** be inspected before reporting green.

Earlier [draft PR #895](https://github.com/rumman52/Shuddho/pull/895) remains unmerged pending review despite source checks success; native `ci-merge-gate` failed, `governance-audit` skipped, independent review absent. Native ruleset `27324410` still permits zero approving reviewers and has no required CI contexts. Supabase staging read-only schema `0070` PG17, no operated restore or approved frozen runtime identity. Protected human D 40/80 evaluation and 20 operated traces, exact 43 runtime flags, independent Founder/Owner-C signoffs and separate 5–10 authorized HTTPS admission remain absent. No cloud mutation, paid provisioning, provider calls, telemetry, real cohort, deployment, or false operator receipts. Historical baseline 18/100 tasks, 5/54 exits, 0/10 accepted days unchanged.

---

## 22 November 2026 — Day 2 private-object manifest and blob evidence integrity ([draft PR #896](https://github.com/rumman52/Shuddho/pull/896))

**SOURCE_ONLY / controlled pilot NO-GO.** Based on exact main `4eee61c4389b507b95670203618c0ed980d5ccf8`, uncovered separate archive-intake TOCTOU and ambiguity in `scripts/staging_object_backup.py` (not overlapping [PG dump digest PR #893](https://github.com/rumman52/Shuddho/pull/893)). A symlink substitution could occur after `is_symlink/is_file` checks of `manifest.json`, `objects` and each binary payload; manifest size was unbounded, nested duplicate JSON keys permitted, and concurrent blob changes lacked metadata fences. RED test-only `0c9d66b048a7535d0dc9801f8a4b5eaed787bdce`: mandatory Coworker [CI #45049934543](https://github.com/rumman52/Shuddho/actions/runs/45049934543) **9 expected FAILED / 424 PASSED**, all nine targeted new cases. Proposed minimal fix uses no-follow directory-anchored reads, 16 MiB manifest cap, strict JSON, exact read byte-count and pre/post inode stat. Exact GREEN CI and independent review pending; [task contract](DAY2_PRIVATE_OBJECT_ARCHIVE_INTAKE_2026-11-22.md).

D01.T06 / D01.G03 and D02.T09 / G04 retain prior active/blocked disposition, **no PASS** from local tests. Read-only operator facts: GitHub ruleset 27324410 still 0 mandatory reviews and no strict required-check rule; App governance credentials and independent negative/positive merge controls missing; Supabase staging `0070` vs source `0072_merge_0071_heads`; Render API staging old `0e0b662f...` with no visible dedicated worker; C/Founder have not authorized isolated restore infrastructure or spend; D custody and operated recovery cases pending. No external mutation or telemetry capture. Historical v4 18/100 tasks, 5/54 exits, 0/10 days not increased.

---

## 22 November 2026 — controlled cohort-health trust boundary ([draft PR #895](https://github.com/rumman52/Shuddho/pull/895))

**SOURCE_PATCH ONLY / CONTROLLED PILOT NO-GO.** Based on main `4eee61c4389b507b95670203618c0ed980d5ccf8`, identified permissive JSON and mutable receipt boundaries in `scripts/cohort_release_gate.load_rollout` and `scripts/cohort_health_gate`: duplicate cohort caps and STOP thresholds, linked/oversized evidence, nonfinite rollout values and overwritable world-readable first health decisions. Tests were committed first (`df4a3fa982f7a392fa144ddffaef8611dd4dec90`, `aede08744ba62900ea15b701c6dbf39c96f39626`); the test-only [Actions #45041430584](https://github.com/rumman52/Shuddho/actions/runs/45041430584) Python suite **observed RED: 4 failed / 3,684 passed / 107 skipped / 6 warnings**, specifically the rollout reader. The health-test file has optional `pytest.importorskip("sqlalchemy")`; the lightweight suite does **not** establish those assertions as RED. Source fixes `c29a062343904f3179f531343c2ae6852166c6d0` and `3f6b91284264693163f253271222ed2e65ac341d` delegate to the existing bounded strict no-follow JSON reader, reject output collisions, and write first reports with `O_EXCL`, `0600`, fsync. [Scoped engineering contract](DAY10_COHORT_HEALTH_TRUST_BOUNDARY_2026-11-22.md). Exact final-head tests and independent reviewer approval require readback before merge.

**External operator and release blockers remain unchanged:** GitHub main native ruleset `27324410` requires 0 approvals/no required check despite observed failed `ci-merge-gate` merges; staging Supabase PG17.11 reads `0070`, no approved restore; D-protected 40/80 holdout and twenty actual PG/Temporal/object-storage recoveries, exact 43-flag API/worker/schema/model attestation, independent Founder+C approvals and distinct authorized 5–10 member/nonmember HTTPS proof remain unobserved. No hosted deploy, credential, provider spend, telemetry capture, migration, owner traffic, pilot admission or release action performed. Historical v4 18/100 tasks, 5/54 exits and 0/10 accepted days remain historical, not increased by this PR.

---

## 22 November 2026 — Day 1 PostgreSQL backup dump inode-bound evidence ([draft PR #893](https://github.com/rumman52/Shuddho/pull/893))

**SOURCE_ONLY / pilot NO-GO.** Base `main=4eee61c4389b507b95670203618c0ed980d5ccf8`. After merged #889 secured JSON receipts, `scripts/staging_day2_archive_attestation._file_sha` still prechecked the PostgreSQL dump pathname before reopening via `Path.open('rb')`; a changed symlink could supply a different SHA and file mutations during streaming were not rejected. Four test-first regressions at corrected RED head `531a8a7b4f628ab9d1822d055b12c4acf5dbe836` reproduced **4 expected FAILED / 424 PASSED** in mandatory Coworker [CI #45041258533](https://github.com/rumman52/Shuddho/actions/runs/45041258533); no import/collection failures. Source patch uses one no-follow regular descriptor and 1 MiB chunk hashing with pre/post file metadata + exact-length stability assertions. Exact corrected-head CI and independent review pending; [task contract](DAY1_POSTGRES_DUMP_INODE_DIGEST_2026-11-22.md).

No D01.T06/G03 operational PASS. Read-only native GitHub ruleset 27324410 continues to require zero approvals and no required status-check rule; protected App credentials, exact-head independently reviewed merge controls absent. Supabase staging PG17.11 migration `0070` vs code `0072_merge_0071_heads`; Render staging API on old `0e0b662f...` deploy without connected dedicated worker, auto-deploy off. C/Founder have not provided approved isolated DB/S3+API/worker/Temporal release resources/budget/privacy, D holdout custody and 20 live recoveries missing. Vercel/ProductOS connected projects do not establish Shuddho, PostHog capture unapproved. All source fixes remain distinct from live approval: historical v4 18/100 tasks, 5/54 exits, 0/10 accepted days unchanged. No secret, production/staging mutations, paid provisioning, provider inference, telemetry or pilot admission.

---

## 22 November 2026 — Day 10 canary history/control integrity ([draft PR #891](https://github.com/rumman52/Shuddho/pull/891))

**SOURCE_PATCH / controlled pilot NO-GO.** From base main `e12f9832fb8b495bb30e6a81e125906b53508832`, identified Part 05 pp. 6–7 canary receipt boundary defects in `scripts/cohort_canary_progression.py`: `load_plan` and `load_history` used unbounded `json.loads(Path.read_text())` that accepted duplicate STOP/CONTINUE decision keys, duplicate plan thresholds, symlinked history files/directories and oversized receipts. The CLI output used `Path.write_text`, overwrote the prior decision and created `0644` under `umask 022`. Tests committed **first** at `604d92cae8fa37703b4d66c740908cf1c6131366`; observed actual full Python test **RED: 7 failed / 3,647 passed / 107 skipped / 6 warnings** on [Actions #45034201001](https://github.com/rumman52/Shuddho/actions/runs/45034201001), all seven failures isolated to the newly added canary evidence assertions. Production fix commit `b13908fde0e5e9aea8d5d0cee655081701459873` uses bounded strict plan parsing and descriptor-anchored `dir_fd` history enumeration/open with no-follow and per-report byte cap; output now uses an exclusive, fsynced, private `0600` first-decision writer. [Scoped task contract](DAY10_CANARY_EVIDENCE_INTEGRITY_2026-11-22.md), [execution plan](../superpowers/plans/2026-11-22-day10-canary-evidence-integrity.md). **Exact final-head GREEN and independent review are pending readback**; no source-only test certifies live canary health.

**External blockers untouched:** Existing [PR #887](https://github.com/rumman52/Shuddho/pull/887) merged with `ci-merge-gate` failed and zero independent reviews. GitHub ruleset `27324410` still requires zero approvals and no status checks. Supabase staging `shuddho-staging` is ACTIVE_HEALTHY PG17.11, with actual Alembic `0070` (not source head); Render workspace is available but service identity/approval not selected; connected Vercel `ali` and ProductOS Dust2Glow are not Shuddho projects; Linear MD-5–MD-8 remain open operating queues. Protected independent D custody, 40 first attempts, 80 blind scores, 20 operated PostgreSQL/Temporal/private-storage faults, exact API/worker/schema+43 flags, Founder+C exact release signoffs and authorized 5–10 pilot admission have not been observed. **No migrations, API/worker deployments, paid model/provider use, owner data, PostHog telemetry capture, Render/Vercel changes, native governance modification or pilot activation performed.** Historical v4 18/100 task PASS, 5/54 exits, 0/10 accepted days remain historical, not increased for this source PR.

---

## 22 November 2026 — Day 1 private backup/restore evidence preflight ([draft PR #889](https://github.com/rumman52/Shuddho/pull/889))

**SOURCE_ONLY / controlled pilot NO-GO.** Current base `main=e12f9832fb8b495bb30e6a81e125906b53508832`. `scripts/staging_day2_archive_attestation._private_json` checked `is_symlink/is_file/stat` but reopened the path via `read_text`, enabling race-based substitution or post-stat growth, and permissive JSON decoded ambiguous keys/nonfinite values. `staging_backup_restore.verify` also read prepared state/base evidence permissively and deferred output preflight until after restored API access. 11 test-first cases added at `d1eebf6cb00626ae5a1b935651a7dc33f915fbc7` reproduced **11 expected failures / 411 other passes** in [Coworker CI #45033865833](https://github.com/rumman52/Shuddho/actions/runs/45033865833). Patch uses one `O_NOFOLLOW` bounded descriptor for protected receipts, strict JSON, plus early immutable output preflight before target access. Corrected exact-head CI pending; [task contract](DAY1_PRIVATE_RESTORE_EVIDENCE_PREFLIGHT_2026-11-22.md).

D01.T06 **ACTIVE/not PASS**, D01.G03 **READY/not PASS**. Read-only: connected Supabase staging PostgreSQL 17.11 Alembic `0070` vs checked-in `0072_merge_0071_heads`; Render staging API current live build still historical `0e0b662f...`, autoDeploy off and no dedicated worker. Live GitHub ruleset 27324410 still has zero native review approvals and no required-check rule. C/admin + separate reviewer must provide App identity, effective policy and rejected/accepted merge controls; C+Founder must approve isolated DB/storage restore, worker/Temporal/identity, budget/privacy; D must independently hold blinded corpus and score real operation; Founder+C sign exact-release decision. No operational PASS credited, and historical v4 18/100 tasks / 5/54 exits are not recalculated without private receipts. No hosted or production mutation, inference, paid provisioning, credential change, PostHog, private D access or pilot activation.

---

## 22 November 2026 — Day 10 verified rollout and private pilot-access receipts ([draft PR #887](https://github.com/rumman52/Shuddho/pull/887))

**SOURCE IMPLEMENTED / controlled pilot NO-GO.** From `main b5b7805c37a1a9c2bb3d319bafcec85df8f77e99`, reviewed `scripts/pilot_admission_verify.py` had (1) a TOCTOU mismatch: the rollout JSON used to check the 5–10 member cohort was parsed on one open, then its SHA-256 recomputed on a *second* pathname open; and (2) `immutable_report` wrote first-run access receipts through default-mode `path.open("x")`, creating `0644` under ordinary `umask 022` although report contents are operator evidence. Two synthetic regressions were committed first at `2444c60f8c9c61d672115700b85271b1b0345896`. [Actual RED CI #45019756125](https://github.com/rumman52/Shuddho/actions/runs/45019756125), mandatory Coworker Day 10 source gate: **2 failed / 385 passed** (digest of substituted file vs parsed rollout; mode `0644` instead of `0600`). Production fix `375d9525a861a8c497a8f95fe8636a47913ad090` reuses the already-reviewed single-descriptor JSON-plus-SHA reader and exclusive fsynced `0600` writer without new schema or changing function signatures. [Task contract](DAY10_ADMISSION_VERIFIED_ROLLOUT_PRIVATE_RECEIPT_2026-11-22.md); [TDD plan](../superpowers/plans/2026-11-22-day10-admission-evidence-integrity.md). Exact final-head GREEN and independent review require fresh GitHub readback; **do not mark them PASS based on the patch**.

**No hosted Day 10 acceptance credited.** Supabase staging remains PG17.11, Alembic `0070`, without approved private restore/paired worker identity; PostHog connected project reports `ingested_event=false`, no privacy approval; Vercel connected Git project does not match Shuddho, ProductOS active project is unrelated, Render requires owner workspace selection. Native ruleset `27324410` still does not mandate independent approval or exact-head checks. D-only corpus access, 40 immutable first attempts, 80 blind reviewer scores, 20 operated recovery traces, 43 live runtime flag readbacks, final golden run, separate Founder+C release decisions and actual 5–10-member admissions are absent. Historical v4 **18/100 tasks, 5/54 exits and 0/10 accepted days** are not updated absent independent row-level evidence. No native ruleset edit, production/staging migration, private D read, telemetry capture, third-party provider spend, external transaction, allowlist edit, deployment or pilot activation.

---

## 22 November 2026 — Day 1 same-byte rollout release context ([draft PR #884](https://github.com/rumman52/Shuddho/pull/884))

**SOURCE_ONLY / pilot NO-GO.** Part 01 `D01.T05 / G03` release-identity code parsed a rollout manifest and separately reopened it to hash; intervening writes could associate a different release_id with an unrelated checksum. Python's default JSON decode accepted duplicate keys/nonfinite values, and source lacked no-follow and bounds. Seven test-first regressions at `8c062a373d515bea1b3e2b05aaf44b4bcfbe1357` reproduced the flaws on [CI #45019552298](https://github.com/rumman52/Shuddho/actions/runs/45019552298): **7 expected FAIL / 3,612 PASS / 105 SKIP / 6 WARN**. Base main `b5b7805c37a1a9c2bb3d319bafcec85df8f77e99`. Corrected `scripts/staging_release_evidence.py` now parses and hashes one bounded `O_NOFOLLOW` descriptor's bytes, rejecting ambiguous JSON. Exact corrected-head suite/review **pending verification**; [task contract](DAY1_ROLLOUT_CONTEXT_VERIFIED_BYTES_2026-11-22.md).

Actual operator gates unchanged: Supabase staging source/schema drift (`0070` vs `0072_merge_0071_heads`), Render staging/API-worker pairing, protected GitHub App identity/native one-review+strict-check rules and both negative/positive controls, Founder+C approved resources/restore and release signoff, D-blinded holdout custody and actual recovery scenarios all missing. No staging, production, secrets, paid infrastructure, telemetry, external send, heldout test, or pilot mutation. `D01.T05/G03` remain **ACTIVE / not PASS**; historical v4 18/100 tasks and 5/54 exits are not recomputed without new private receipts.

---

## 22 November 2026 — Day 10 parsed-byte decision receipts and write-once output ([draft PR #881](https://github.com/rumman52/Shuddho/pull/881))

**IMPLEMENTED SOURCE PATCH / repository and controlled pilot UNVERIFIED.** Starting on main `92cdc1a4952239a4a676b754ebc3d1ca044c9cbd` (merged Day 9 PR #876), the canonical `scripts/day10_release_decision.py` still parsed rollout and Day 9 first-run evidence from a bounded descriptor before hashing a separate later pathname read. It also rewrote any existing release decision with `Path.write_text`. A changed pathname could change the reported SHA without changing the decision inputs; a rerun could destroy the first decision. Four synthetic regression tests first committed `7b7d1337b2e9ceb16e017b1179be124dcd40c33a`; their CI was superseded so no observed RED is claimed. Fix reuses Day 9 same-buffer JSON+SHA and exclusive 0600 `immutable_write`; collision now fails closed, and first-run reporting requires a new path. No runtime schema, API, worker, feature flag or provider change. [Scoped task contract](DAY10_DECISION_IMMUTABLE_EVIDENCE_2026-11-22.md).

**Release remains NO-GO.** Source PR is not real human-D possession, 40 genuine first attempts, 80 blind score records, 20 live PostgreSQL/Temporal/object-storage recovery traces, final-head native review controls, paired rollout identity, 43 verified flags, live model/curated quality, reversible worker restore, founder/C approvals or 5–10 admitted users. Existing historical v4 baseline (18/100 task PASS; 5/54 exits; 0/10 accepted days) is not upgraded from tests. Verify exact final PR checks and independently enforce human review before merge; no admin policy, Supabase, Render, Vercel, ProductOS, PostHog, provider spend, staging restore, D private material or admission changed in this source patch.

---

## 22 November 2026 — Day 1 atomic staging readback input ([draft PR #882](https://github.com/rumman52/Shuddho/pull/882))

**SOURCE_ONLY / controlled pilot NO-GO.** The Part 01 Foundation `D01.T06 / D01.G03` staging readback used `lstat/resolve/stat` then reopened `Path.read_text`. It could accept a switched symlink's different evidence or an oversized file grown after the pre-read size check. Two tests committed first at `551325923d3e173f1fde85fb16c4dd9909e4dd40` reproduced both cases in [CI #45014367909](https://github.com/rumman52/Shuddho/actions/runs/45014367909): **2 expected FAIL / 3,574 PASS / 105 SKIP / 6 WARN**. Base main `92cdc1a4952239a4a676b754ebc3d1ca044c9cbd`. The fix reads the external regular file via one `O_NOFOLLOW` descriptor, `fstat`, and bounded `os.read`, preserving duplicate/non-finite JSON checks, the 32 KiB ceiling and all nonqualification flags. Corrected exact-head suite/review **pending verification**; [task contract](DAY1_STAGING_READBACK_ATOMIC_2026-11-22.md).

Read-only: Supabase staging PG17.11 Alembic `0070` behind source `0072_merge_0071_heads`; Render staging API autoDeploy off with no dedicated worker in connected workspace; native ruleset 27324410 still has zero required approvals/status checks. Founder+C approved isolated restore/worker/budget, D access isolation, protected GitHub App, independent human review and Founder+C release signoff remain absent. No hosted schema/service, secrets, inference, paid resources, telemetry, production or pilot mutation. Historical v4 task/exit counts remain dated; D01.T06 and D01.G03 remain **ACTIVE / not PASS** pending operated evidence.

---

## 22 November 2026 — Day 9 evidence single-read integrity ([draft PR #876](https://github.com/rumman52/Shuddho/pull/876))

**SOURCE_ONLY / controlled pilot NO-GO.** Against base `main=4b055bcaab83151cca1478ab52ee121f5b2f74f7`, reviewed `scripts/ruke_pilot_eval.py` exposed a file substitution window between the checked SHA/mode and a second pathname read of JSON, JSONL or the independent heldout. Three synthetic regressions were committed first (`e230ca0d3fd8cbeed708288155db6735f84cfd5b`), followed by three more tests for same-buffer manifest/candidate hashes and the D-only blind key. A descriptor-scoped, bounded no-follow reader now supplies bytes to parsing, digest computation, heldout validation and protected key readback. The frozen heldout SHA and exported release report hashes now cover the **same bytes parsed**. Exact final-head CI and independent review must be inspected before claiming repository verification. [Task contract](DAY9_EVIDENCE_BYTE_READ_INTEGRITY_2026-11-22.md).

No real protected D custody, 40 first model attempts, 80 human reviews, 20 operated recovery traces, release-bound staging identity, 43 runtime flag freeze, native reviewed-and-protected merge, Founder/Owner C authorization or pilot membership is asserted. Do not increase per-day task/exit PASS denominators from this PR. No Supabase migration, Render/Vercel deployment, PostHog telemetry, provider expenditure, owner traffic or allowlist changes occurred in this source patch.

---

## 22 November 2026 — Day 1 frozen holdout checksum record ([draft PR #873](https://github.com/rumman52/Shuddho/pull/873))

**SOURCE_ONLY / controlled pilot NO-GO.** Starting main `4b055bcaab83151cca1478ab52ee121f5b2f74f7`. New checksum input defect in `scripts/pilot_workflow_eval.py::load_suite`: checking only `.split()[0]` accepted a wrong filename, missing filename, appended checksum record and trailing fields; an empty checksum crashed with `IndexError`. Five targeted regression cases reproduced **RED** on test-only `41ea1b143521a7bf346e6df5e814a91b67e35533`, [CI #44938484991](https://github.com/rumman52/Shuddho/actions/runs/44938484991): **5 failed / 3,541 passed / 105 skipped / 6 warnings**. This change compares the entire canonical one-line checksum record; no corpus, permissions, model, worker, privacy, production or API change. **Final-head GREEN and independent review are pending**, no row credited solely by a source PR. [Task contract](DAY1_HOLDOUT_CHECKSUM_RECORD_2026-11-22.md).

Read-only operator inventory: staging Supabase PG17.11 revision `0070` vs source `0072_merge_0071_heads`; Render staging API last deployed `0e0b662f`, autoDeploy off, no dedicated worker in the available workspace; connected Vercel lacks a Shuddho-linked project. Native governance, owner-controlled staging restore, D-only external holdout, spend/privacy and separate Founder+Owner C approval remain unmet. No cloud mutation or pilot activation. Historical v4 18/100 task PASS, 5/54 exits, 0/10 accepted days are unchanged until private row receipts justify recalculation.

---

## 21 November 2026 — Day 1 bilingual research citation padding ([draft PR #872](https://github.com/rumman52/Shuddho/pull/872))

**SOURCE_ONLY / pilot NO-GO.** Reviewed the user's five-part Rukh AI instruction prompt, [primary 10-day Day 1 plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) ¶141–152, board [#737](https://github.com/rumman52/Shuddho/issues/737), Day 1 [#727](https://github.com/rumman52/Shuddho/issues/727), independent D custody [#665](https://github.com/rumman52/Shuddho/issues/665), `AGENTS.md`, `SPEC.md`, and actual `scripts/pilot_workflow_eval.py::score` and production `ResearchCitation` schema. Base `main=05e582d6a5e6174668b3287685966929d3b87460` includes prior exact-byte evaluator PR #870, so it is not duplicated.

**Reproduced bug:** The scorer's research quote matching checked `_norm(quote) in _norm(source)` without requiring the quote to *remain* substantively long after whitespace normalization. Production `ResearchCitation.quote` strips leading/trailing whitespace and has 20-character raw minimum, but internal whitespace padding of a short `Keep the` source fragment passes the schema and collapses to only 8 normalized characters. A newly appended unrelated finding with that padded source-id citation passed `citation_grounding`. **TDD RED** test-only commit `564a8c2191c643cdfde885c7eb95a2cb43c718a1`, [Actions #44923376923](https://github.com/rumman52/Shuddho/actions/runs/44923376923): **4 expected FAILED / 3,537 PASSED / 105 SKIPPED / 6 WARN**; exact cases spaces/newlines × English/Bangla all returned `True` where `citation_grounding=False` was required, with schema validation succeeding. **Smallest fix** `4ae1afcaacef7403f14669b3e7c6b84ae5308d03`: require `len(_norm(c.quote)) >= 20` before matching to the verified source. Production `ResearchCitation` and normal references unchanged; no network, paid model, data, public output schema or runtime change. [Task contract](DAY1_PILOT_RESEARCH_CITATION_SUBSTANCE_2026-11-21.md), [implementation plan](../superpowers/plans/2026-11-21-day1-research-citation-substance.md). Exact final-head GREEN **pending readback**.

**Critical operating blocker:** Prior [PR #870](https://github.com/rumman52/Shuddho/pull/870) actually merged with `ci-merge-gate` FAILED, PR `governance-audit` SKIPPED, and zero submitted independent reviews; required PG18/Coworker jobs were cancelled during merging. Similarly #863 had a failed merge gate and zero submitted reviews before merge. Do not credit native protected-main enforcement. C/repository admin must configure and test real protected App/ruleset `27324410` with denied unreviewed/failing and permitted independently reviewed merge controls. Founder+C must approve staging DB/objects isolated backup and operated restore, exact API-worker/Temporal rollout with bounded resource/model/retention and spending; independent human D must replace readable 40 heldout candidates, prove developer-negative custodian-positive access and operate 20 recovery scenarios; independent Founder + Owner C exact-release GO/NO-GO. No live GitHub rule, Supabase staging `0070` migration, Render worker, Vercel deployment, ProductOS demo, PostHog capture, provider cost, private D data or pilot flag changed. Historical v4 18/100 task PASS, 5/54 gates, 0/10 accepted days remains a dated baseline and is not extrapolated.

---

## 21 November 2026 — Day 1 evaluator exact-byte provenance ([draft PR #870](https://github.com/rumman52/Shuddho/pull/870))

**SOURCE_ONLY; controlled pilot NO-GO.** Re-read the user's five-part Rukh AI instruction documents, [Day 1 ten-day plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) ¶141–152, [#737](https://github.com/rumman52/Shuddho/issues/737), [#727](https://github.com/rumman52/Shuddho/issues/727), [D custody #665](https://github.com/rumman52/Shuddho/issues/665), `AGENTS.md`, `SPEC.md` and actual evaluator. Base main `57b0cbce15eaf5517cc6e78fff399d93faee87ad`; all earlier Day 6 three export manifest rejections are already in `tests/test_export_manifest_rejections.py` and previous Day 1 governance reader nofollow [PR #863](https://github.com/rumman52/Shuddho/pull/863) merged. No duplicate work.

**Root cause:** `scripts/pilot_workflow_eval.py::_verified` hashed source/case/reference bytes then returned only `Path` for a *second open* in `load_suite`; case/source reads could incorporate unreviewed bytes whose digest was not checked. Standalone evaluator input used `stat/read_text`, following direct symlinks and checking size only before read. **TDD RED:** test-only `b93587ed3f987356e5285c1cfc1be5f505764647`, [Actions #44921905522](https://github.com/rumman52/Shuddho/actions/runs/44921905522) `test-and-build`: **3 targeted expected FAIL / 3,494 PASS / 105 SKIP / 6 WARN**. Observed three failures: exact digest mismatch on consumed source, unreviewed case metadata accepted and symlink submission not rejected. Test-only predecessor `fbeaf1f9c074617bafa968f38e7746636bad4f63` cancelled by new test run, not independent RED. **Minimal fix** `3bfc83d98364080024c6eedf6db9327e986c30ff` unifies the bounded no-follow regular descriptor read, returns verified bytes, and parses source/case/reference/frozen manifest/holdout from those same buffers. No provider call, live credential, schema, worker, storage, telemetry or deployment mutation. [Task contract](DAY1_EVALUATOR_VERIFIED_BYTES_2026-11-21.md), [plan](../superpowers/plans/2026-11-21-day1-evaluator-verified-byte-provenance.md), [draft PR #870](https://github.com/rumman52/Shuddho/pull/870). **Exact-final-head GREEN pending GitHub CI**.

**Read-only operating status:** connected Supabase `shuddho-staging` ACTIVE_HEALTHY PG17.11.0.003 with actual migration `0070`, source head `0072_merge_0071_heads`. Render accessible `Rumman` workspace without owner-selected Shuddho service. Vercel `shuddho` search returned 0 projects. ProductOS only unrelated Dust2Glow, untouched. PostHog identity/telemetry privacy approval not established. No staging restore, schema migration, protected App changes, native ruleset operations, paid worker, production deploy, provider spend, D private case access or pilot admission.

**External gates:** Owner C/admin must confirm protected GitHub App and reconcile native ruleset `27324410`; independent reviewer must actually prove blocked unreviewed/failing + permitted independently reviewed merge and submit PR approval. Founder+C approve bounded model/provider/resources, staging DB+storage retention and perform isolated backup+restore/paired API-worker-Temporal deployment; independent D replaces developer-exposed 40 candidates with access-isolated blinded cases and runs actual 20 recovery drills; Founder and C independently sign the identical release digest. The historical v4 ledger 18/100 tasks, 5/54 exits and 0/10 accepted days is **not refreshed** without per-row receipts.

---

## 21 November 2026 — Day 1 governance JSON no-follow evidence ([draft PR #863](https://github.com/rumman52/Shuddho/pull/863))

**SOURCE_ONLY / pilot NO-GO.** Reopened [authoritative Ruke AI Ten-Day Completion Plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 ¶141–152 and repository `AGENTS.md`, `SPEC.md`, original `scripts/day1_ruleset_drift.py` plus tests. Base `main` `500afb5c0c08d6988fd55959a6a1185bc0b98c9e` (earlier exact native ruleset scope [PR #861](https://github.com/rumman52/Shuddho/pull/861) had already merged; do not duplicate). The offline evidence reader used `path.is_symlink()/is_file()/stat()/read_bytes()`, making the checked path swappable to a direct symlink before the actual open. A valid substituted JSON file could yield `configuration_candidate`, defeating the input integrity assumption despite preserving a hash of substituted bytes. Its post-read byte limit also allowed unbounded pre-rejection reading of an unexpectedly grown file.

**TDD RED:** Test-only SHA `d70664d3b38f84a3fdc02ee2c79b2680405ad1a1`, [GitHub Actions #44916640894](https://github.com/rumman52/Shuddho/actions/runs/44916640894) `test-and-build`: **3 targeted expected FAIL / 3,359 PASS / 105 SKIP / 6 WARN**. Three actual `test_input_replaced_by_symlink_at_open_is_rejected` cases for branch/ruleset/policy returned code `0` instead of required `2`; no import or missing-dependency error. **Smallest correction:** `84c09b339b5a50de079419485ed138effe0101db` uses one `O_NOFOLLOW` file descriptor, `fstat` regular inode/size, reads at most `MAX_READ_BYTES+1`, closes FD in all paths and preserves existing JSON duplicate/nonfinite guards and raw SHA-256. No external state was changed. [Task contract](DAY1_OFFLINE_EVIDENCE_NOFOLLOW_2026-11-21.md), [implementation plan](../superpowers/plans/2026-11-21-day1-offline-evidence-nofollow.md), [draft #863](https://github.com/rumman52/Shuddho/pull/863). **Exact-final-head GREEN remains unverified pending fresh CI**; never misreport the intentional RED job as success.

**Cross-platform read-only:** Connected Supabase `shuddho-staging` still ACTIVE_HEALTHY PostgreSQL 17.11.0.003, actual `cw_alembic_version=0070` behind repository migration head `0072_merge_0071_heads`. Render has one visible workspace `Rumman` but no owner-selected service; Vercel Shuddho search zero projects; ProductOS sole connected project unrelated Dust2Glow left untouched; PostHog private capture not approved. No native GitHub ruleset PUT, protected App credential change, Supabase migration, Render worker/Temporal provisioning, Vercel deployment, ProductOS mutation, PostHog ingestion, provider inference spend, D private holdout read or pilot flag change.

**External owner gates:** GitHub administrator/Owner C protected App and ruleset `27324410` readback plus *operated* denied/unreviewed and permitted/independently-reviewed merge controls; distinct real PR review. Founder+C approve bounded model/inference/resources/retention and *perform* isolated staging backup+restore with exact paired API/worker/DB identity. D independently owns 40 frozen holdout cases of the balanced 80 and operates 20 recovery scenarios. Separate Founder + Owner C exact-release GO/NO-GO. [Day 1 issue #727](https://github.com/rumman52/Shuddho/issues/727) and [Linear MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout) remain open.

---

## 21 November 2026 — Day 1 exact main-only native ruleset scope ([draft PR #861](https://github.com/rumman52/Shuddho/pull/861))

**SOURCE_ONLY / pilot NO-GO.** Reopened the [authoritative Ruke AI ten-day completion plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 ¶141–152 and repository `AGENTS.md`/existing native policy operator. Base `main` `112e85fbe53e7ad983444414c2d6cb410b93ad96`. [PRs #846](https://github.com/rumman52/Shuddho/pull/846), [#850](https://github.com/rumman52/Shuddho/pull/850) and [#853](https://github.com/rumman52/Shuddho/pull/853) already merged status-row and ruleset-origin safeguards; this task does not duplicate them. Still-unresolved discrepancy: `scripts/day1_ruleset_drift.py::analyze` and `scripts/main_protection_audit.py::audit_governance` allowed native `conditions.ref_name.include` with main **plus extra refs**, duplicate/mixed aliases and unrecognized selector keys. Existing admin `scripts/reconcile_main_ruleset.py::_read_unique_existing` requires exact main-only scope. An ambiguous readback must not become `configuration_candidate`.

**Actual RED:** Test-only head `68c6ea6112d5fce3d42d2c1435e2326adbe828c7`; [GitHub Actions #44914417577](https://github.com/rumman52/Shuddho/actions/runs/44914417577) `test-and-build` **19 expected FAIL / 3,214 PASS / 105 SKIP / 6 WARN**. The 19 cases were 10 offline and 9 live candidate/redacted-bypass errors; no import or missing-env failures. **Smallest fix:** `d700b88691fef714cbf71ba4a9ee58b7207357a7` validates exact offline main-scope and rejects unreviewed policy selectors; `2953f1c407c870f1f2cbb3cefdeb77ca5be2b13f` adds privileged `_exact_main_scope` solely to `audit_governance` candidate and bypass-redaction routing. It **preserves** `_targets_main` and `_active_main_ruleset`, used by conservative ruleset discovery and creation-policy validator, so safety semantics do not drift. [Implementation plan](../superpowers/plans/2026-11-21-day1-exact-main-ruleset-scope.md), [task contract](DAY1_EXACT_MAIN_RULESET_SCOPE_2026-11-21.md), [draft #861](https://github.com/rumman52/Shuddho/pull/861). Final exact-head GREEN CI is **not assumed**; check all jobs separately. GitHub PR-event `governance-audit` skip is not native merge-control evidence.

**Read-only cross-platform checkpoint:** Supabase `shuddho-staging` ACTIVE_HEALTHY PostgreSQL 17.11, `cw_alembic_version=0070` versus source `0072_merge_0071_heads`; actual isolated restore and retained resource/budget not approved. Render workspace `Rumman` visible but requires explicit selection before service access. Vercel connected account returned zero Shuddho projects. ProductOS connected project is unrelated Dust2Glow, untouched; no PostHog capture approved. No native GitHub ruleset update, credential, schema migration, worker, paid provision, telemetry ingestion, D private holdout, model cost or pilot flag changed.

**Next owner actions:** GitHub administrator/Owner C to verify native ruleset `27324410` with approved App and independently operated denied and permitted merges under current checks and human review; Founder+C approve recoverable staging retention/budgets and paired API/worker/DB/Temporal identity; D alone retains 40 private holdout cases and operates 20 fault-recovery exercises; separate Owner C + Founder exact-release signoff. [Day 1 issue #727](https://github.com/rumman52/Shuddho/issues/727), [Linear MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout) remain active. SOURCE_ONLY is not Day 1 completion.

---

## 21 November 2026 — Day 1 privileged ruleset repository-origin verification ([draft PR #853](https://github.com/rumman52/Shuddho/pull/853))

**SOURCE_ONLY / pilot NO-GO.** Reopened [Ruke AI Ten-Day Completion Plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 ¶141–152, `AGENTS.md`, `SPEC.md` and the existing admin reconciler. Base `main` `d92e2ecd6f5c899e9acdc079b9f620870d613dfc`. Parallel [draft PR #850](https://github.com/rumman52/Shuddho/pull/850) protects the *offline* ruleset snapshot; its exact-head main source/Coworker/frontend/browser/PostgreSQL checks passed, but `ci-merge-gate` failed on required independent approval because it remained draft. This PR covers the separate **privileged GitHub live-readback** path.

**Reproduced root cause:** `scripts/main_protection_audit.py` fetched GitHub effective rulesets with `includes_parents=true` but ignored the returned `source_type`/`source` identity. Even a foreign/inherited rule or a rule without provenance could become a `configuration_candidate`; a foreign rule with bypass metadata redacted could trigger misleading escalation guidance. **Test-first RED:** `d5032953d2bcdeb5eb84a99ea8eb52876076aba6`, [GitHub Actions #44910176240](https://github.com/rumman52/Shuddho/actions/runs/44910176240) `test-and-build` **13 expected FAIL / 3,087 PASS / 105 SKIP / 6 WARN**. The 13 cases failed on the missing provenance guard or redacted-credential diagnostic, not an import/environment error.

**Minimum correction:** `63ff12ce1182d31910025c56ccf88156a5910889` applies exact `source_type=Repository`/`source==inspected repository` gating before V-01 candidate selection and before bypass-redaction diagnostic. `7f5a6a909482f24d26ad75cd8cd6745c2eb8c92b` restores positive full-readback fixtures to realistic server-returned provenance. No native ruleset mutation, admin-secret access, credential/endpoint broaden, check removal, review bypass or deploy. [Implementation plan](../superpowers/plans/2026-11-21-day1-live-governance-repository-origin.md), [evidence contract](DAY1_LIVE_RULESET_ORIGIN_2026-11-21.md), [draft PR #853](https://github.com/rumman52/Shuddho/pull/853). **Exact final-head GREEN must still be read from GitHub Actions**, and draft independent-review gate cannot count as success.

**Intermediate CI integration failure and corrective action:** [Actions #44910418521](https://github.com/rumman52/Shuddho/actions/runs/44910418521) failed **46 tests / 3,054 passed / 105 skipped / 6 warnings** because the first implementation changed `_active_main_ruleset(rule)` to require a `repository` argument, breaking the creation-template validator imported by `scripts/apply_main_ruleset.py`. That helper must continue to accept reviewed pre-creation JSON without native `source` fields. Commit `96f4e9a9da342464c98a5196dcc4fac0caaf892a` restores the original helper and applies ownership only in `audit_governance`; commit `6b09fc8ab0e8deade902dd49513b872fe693731b` adds a direct creation-template compatibility test. The intermediate FAILED run is documented rather than presented as green. Final-head CI remains to be checked.

**Read-only platform evidence:** Supabase `shuddho-staging` reported ACTIVE_HEALTHY PG17.11; Render one accessible Rumman workspace but service target not approved; Vercel returned zero Shuddho projects; ProductOS one unrelated Dust2Glow project left untouched. No PostHog telemetry enabled; no migration, workers, staging restore, private holdout, production or pilot activation.

**Remaining external gates:** Owner C/GitHub administrator must supply approved App with adequate access, read back reviewed ruleset `27324410` and operate real denied/unreviewed and permitted/independently reviewed native merge cases. Founder/C need authorized durable staging backup + isolated restore, approved retention/budgets and exact paired API/worker/schema identity. D must retain independent custody of private 40-case holdout and 20 operated recoveries. Distinct Founder+C exact-release approval required. Source and CI cannot substitute for these receipts. [Linear MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout).

**Rebased source/build correction:** [Actions #44911260802](https://github.com/rumman52/Shuddho/actions/runs/44911260802) on `9819cb88508da3f97dc2368e3ee61e892ba41dc7` failed **3 tests / 3,198 passed / 105 skipped / 6 warnings**. The three `apply_main_ruleset` positive HTTP GET-detail mocks used `detail()` without server-owned `source`/`source_type`; the new source guard correctly rejected them. Commit `c2115f408facf9891728e6c4dd4dfe16621c0e76` adds exact `source=REPO`, `source_type=Repository` to mock *readbacks* only; creation `candidate()` and its POST-body comparison remain unchanged. No native rule operation occurred. Latest source/build remains **unverified until fresh final-head CI**; do not report intermediate failures as success.

---

## 21 November 2026 — Day 1 offline ruleset repository-owned readback ([draft PR #850](https://github.com/rumman52/Shuddho/pull/850))

**SOURCE_ONLY / Day 1 and pilot NO-GO.** The [authoritative Day 1 plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) ¶141–152 requires actual protected-main controls and operated recovery, not a candidate audit. Reopened `main` at `b648d1ab2f83ea6b3abd79b660ccf96ce1322b14`; [PR #846](https://github.com/rumman52/Shuddho/pull/846) already merged the offline status-row gap and [PR #847](https://github.com/rumman52/Shuddho/pull/847) already merged the preseed backup gate; do not duplicate either. The next independent gap is `scripts/day1_ruleset_drift.py::analyze` accepting an offline ruleset readback even with missing, inherited or foreign `source`/`source_type`. The administrator `scripts/reconcile_main_ruleset.py::_read_unique_existing` already requires exact `source="rumman52/Shuddho"` and `source_type="Repository"` for existing rule `27324410`.

**TDD RED:** Test-only SHA `28d8fe4783f854bc722e1554f33c37a082a3ff6e`; [GitHub Actions #44889771927](https://github.com/rumman52/Shuddho/actions/runs/44889771927) `test-and-build` returned **10 targeted expected FAIL / 3,080 PASS / 105 SKIP / 6 WARN**. Every targeted case reported `configuration_candidate` instead of `blocked_configuration`. This is a proved regression, *not* green repository evidence. **Source fix** commit `f2c10625d688054b4e35271bfb66657125b01bc1` appends one fail-closed `ruleset.repository_origin` drift predicate; no native ruleset, App secrets, policy, CI pipeline or other app code changed. [Draft #850](https://github.com/rumman52/Shuddho/pull/850), [implementation plan](../superpowers/plans/2026-11-21-day1-offline-ruleset-origin.md) and [task contract](DAY1_OFFLINE_RULESET_REPOSITORY_ORIGIN_2026-11-21.md). Exact-final-head GREEN must be read back separately.

**Host boundary (read-only):** Supabase `shuddho-staging` still ACTIVE_HEALTHY on PG17.11, Alembic ledger `0070` versus repository head `0072_merge_0071_heads`; no authorized isolated restore or API-worker pairing. Connected Render refuses service listing without explicit workspace selection; do not pick one unilaterally. Vercel returns no Shuddho project; ProductOS's only visible project is unrelated Dust2Glow, untouched. PostHog is not authorized for telemetry. No mutation to GitHub ruleset, Supabase, Render, Vercel, PostHog, ProductOS, private D holdout, external provider or pilot cohort.

**Next:** Verify exact final PR HEAD checks including Coworker, source/build, browser, PostgreSQL-18, ancestry and merge gate; never label PR-skipped governance audit as pass. Distinct real GitHub review, administrator/Owner C protected App + genuine denied/permitted merge controls, Founder/C-approved recoverable staging, D-only custody of 40 independent holdout cases, 20 operated recoveries and separate Founder+C exact-release signoffs remain external blockers. [Linear MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout).

---

## 21 November 2026 — Day 1 offline native required-check row integrity ([draft PR #846](https://github.com/rumman52/Shuddho/pull/846))

**SOURCE_ONLY / pilot NO-GO.** Reopened [authoritative Ruke AI 10-day completion plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 ¶141–152 and `AGENTS.md` on exact `main` base `1dc6422a51e0309c48ca8c26298e3dd4443842a7`. PR [#838](https://github.com/rumman52/Shuddho/pull/838) was already merged; its native-readback governance auditor now rejects all malformed/untrusted required-status entries, whereas offline `scripts/day1_ruleset_drift.py::analyze` still checked only the three minimum contexts, ignoring any extra unknown/duplicated/untrusted rows. The offline validator also accepted unknown fields in the checked-in reviewed status row. This could label an untrustworthy JSON snapshot `configuration_candidate` despite the stricter CI auditor.

**Test-first RED:** [test-only SHA `017a958d7ad494b160cff0bb9ce8f4593e391ccb`](https://github.com/rumman52/Shuddho/commit/017a958d7ad494b160cff0bb9ce8f4593e391ccb), [Actions #44886807268](https://github.com/rumman52/Shuddho/actions/runs/44886807268) `test-and-build`: **13 expected FAIL / 2930 PASS / 105 SKIP / 6 WARN**. Eleven malformed/extra native rows returned `configuration_candidate`; an unknown key in a mandatory row left `drift=[]`; an altered reviewed policy failed to raise. This is confirmed RED, **not** a passing CI result.

**Bounded fix:** `scripts/day1_ruleset_drift.py` now checks every live status row for the exact context/integration ID keys, unique nonblank context and first-party integer App ID `15368`, appending `checks.unambiguous_first_party_rows` when invalid. It also rejects unknown reviewed-policy keys. Existing minimum check gap codes and public schema preserved; a unique additional trusted check remains permitted by the **read-only minimum-policy** candidate check. [Implementation plan](../superpowers/plans/2026-11-21-day1-offline-native-status-row-integrity.md), [task contract](DAY1_OFFLINE_CHECK_ROW_INTEGRITY_2026-11-21.md), [draft PR #846](https://github.com/rumman52/Shuddho/pull/846). Final-head GREEN requires separate GitHub CI readback.

**Read-only hosted check (this turn):** Supabase `shuddho-staging` ACTIVE_HEALTHY PG17.11 and migration ledger `0070` (source unified head `0072_merge_0071_heads`); connected Vercel search found no Shuddho project; connected ProductOS project is unrelated Dust2Glow and left untouched. Render service inventory returned `no workspace selected` and explicitly required the user to select a workspace; no team was chosen without confirmation. PostHog connection's default `Default project` (675660) has `ingested_event=false`, but it is not owner-confirmed as Shuddho, and no telemetry activated. No native GitHub ruleset PUT, schema migration, deployment, paid resource or release activation.

**Operational gap:** [GitHub #727](https://github.com/rumman52/Shuddho/issues/727) + [Linear MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout) still require C/admin protected scoped GitHub App, ruleset `27324410` and **real denied/unreviewed + accepted/independently reviewed merges**; C/Founder approved live backup/isolated restore + API-worker-schema pairing + budget; independent D custody of private 40 holdout cases; and separately attributable Founder/C release GO. The just-merged #838 had no submitted GitHub human reviews and its final run `ci-merge-gate=failure`, so native controls remain **unverified**, not GREEN.

---

## 21 November 2026 — Day 1 native required-check row ambiguity (draft PR #838)

**SOURCE_ONLY / pilot NO-GO.** After verifying [#833](https://github.com/rumman52/Shuddho/pull/833) had merged and there were no open pull requests, checked out `main` `4b6c747475aa881c979d0eabf52f415fe6100b3d` on branch `fix/day1-governance-audit-status-row-ambiguity-20261121`. The [authoritative Ruke AI 10-day plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 ¶141–152 requires read-only governance evidence *and* real native denied/permitted controls, independent review, staging recovery and evaluation custody. Source controls do not substitute for those operator receipts.

**Demonstrated discrepancy:** `scripts/main_protection_audit.py::_has_required_rules.valid_checks` individually matched the three minimum contexts but failed to reject duplicate first-party statuses and other malformed/untrusted native check rows. Its safer administrative counterpart `scripts/reconcile_main_ruleset.py` already rejected unknown/duplicate entries. [Test-only SHA `f44c59d2b7b812c33167b882d0c8096e6d56cc12`](https://github.com/rumman52/Shuddho/commit/f44c59d2b7b812c33167b882d0c8096e6d56cc12), [GitHub Actions #44790402009](https://github.com/rumman52/Shuddho/actions/runs/44790402009): **8 expected FAIL / 2,858 PASS / 103 SKIP / 6 WARN**; each targeted negative `DID NOT RAISE GovernanceAuditError`. A passing test was added for a separate unique first-party extra check because this auditor is a minimum-policy candidate, not an exact policy change tool.

**Smallest source correction:** reject all non-dict, duplicate, untrusted, whitespace-only or unknown-field native status rows; require three first-party `test-and-build`, `coworker`, `ci-merge-gate` with integer App ID `15368`. Preserve exact boolean `do_not_enforce_on_create=false`, strict current-head checks, reviewers and zero bypass actors. [Draft PR #838](https://github.com/rumman52/Shuddho/pull/838), [implementation plan](../superpowers/plans/2026-11-21-day1-governance-audit-status-row-ambiguity.md), [task contract](DAY1_STATUS_ROW_AUDIT_2026-11-21.md). RED evidence is **not GREEN**; exact final-head results must be independently read back.

**Hosted read-only refresh:** `shuddho-staging` in Supabase is ACTIVE_HEALTHY PostgreSQL 17.11 with Alembic ledger `0070`, behind source head `0072_merge_0071_heads`. Connected Render access shows `Rumman` workspace only, without an owner-approved service deployment choice. Connected Vercel search for Shuddho returned no projects. The ProductOS connection contains a single **unrelated** Dust2Glow project, left untouched. No PostHog privacy/collection approval was established, so collection remains outside this work. No migration, worker provision, native ruleset update, deployment, telemetry event or pilot flag was changed.

**Operational blockers:** Owner C/repo admin must use a protected App identity to check native ruleset 27324410 and prove genuinely denied and allowed merges with distinct human review; C/Founder must authorize specific staging recovery retention/budget and API-worker parity; D independently holds 40 private evaluation cases; Founder+C independently approve any candidate pilot. [Linear MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout) is the cross-tool handoff. Do not treat a skipped PR governance audit or green unit tests as native enforcement, Day 1 acceptance, or release qualification.

---

## 20 November 2026 — Day 1 native creation-exemption audit gap (draft PR #833)

**SOURCE_ONLY / Day 1 and pilot NO-GO.** [10-Day Completion Plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 §141–152 and [#727](https://github.com/rumman52/Shuddho/issues/727) require reviewable native main protection and actual denied/permitted merge-control evidence. At exact new branch base `main` `450105020f962a86197e7c5f2cc7bf865388b3d7`, [PR #828](https://github.com/rumman52/Shuddho/pull/828) was already merged; do not duplicate its existing-check publisher guard. The separately reviewed `infra/github/main-ruleset.json` specifies `do_not_enforce_on_create=false` and the offline Day 1 drift analyzer validates it, but the live-readback CI auditor's `valid_checks` predicate omitted this field entirely and could accept a native rule with weakened new-ref enforcement.

**TDD RED:** test-only `7b235a5cf005f0e1e4ccd55a11dca20bfe4e5b6e`; [GitHub Actions #44783850122](https://github.com/rumman52/Shuddho/actions/runs/44783850122) `test-and-build` returned **6 expected FAIL / 2,786 PASS / 103 SKIP / 6 WARN**. All six synthetic weakened/missing/type-confused cases unexpectedly passed `audit_governance` (`DID NOT RAISE GovernanceAuditError`). The positive fixture now accurately specifies an explicit boolean `false` matching the real checked-in policy. **Smallest fix:** `scripts/main_protection_audit.py` checks `p.get("do_not_enforce_on_create") is False`; no other acceptance, identity or policy rule relaxed. [Draft PR #833](https://github.com/rumman52/Shuddho/pull/833), [plan](../superpowers/plans/2026-11-20-day1-enforce-on-create-audit.md), [task contract](DAY1_AUDIT_ENFORCE_ON_CREATE_2026-11-20.md). Exact-final-head GREEN CI must be verified separately, not inferred from RED.

**Hosted read-only check:** Supabase `shuddho-staging` is ACTIVE_HEALTHY PostgreSQL 17.11, Alembic ledger **`0070`**, still behind source head `0072_merge_0071_heads`. Render only lists team `Rumman`; project authorization/workspace selection not confirmed, so no service-level inspection or modification. Connected Vercel search for `shuddho` found no project. ProductOS exposes an unrelated Dust2Glow project; do not touch it. No schema, deployment, telemetry, worker, provider cost, or production rule changed.

**Boundary and exact resume:** The repo's `governance-audit` job normally skips PR events; a green PR job does **not** prove protected main enforcement. C/repo admin must supply the protected scoped GitHub App identity, read back native ruleset `27324410` and prove both blocked and permitted merges under genuine independent review. C/Founder must authorize staging recovery and bounded resource choice, D must independently custody the 40 private holdout cases (#665), and release requires distinct Founder + Owner C signoff. Source progress cannot be promoted to Day 1 operational completion. [Linear MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout) tracks external handoff.

---

## 20 November 2026 — Day 1 unreviewed native status-check publisher safety (draft PR #828)

**SOURCE_ONLY / Day 1 and pilot NO-GO.** Reopened [Ruke AI 10-Day Completion Plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 paragraphs 141–152, and refreshed main from `4be5ea5c2fdccc2d718f0b37b958bdc2b5fa9577`. Merged PR #823 already rejects duplicate/unknown fields in existing native required-check entries, but a known `coworker` context with an **unexpected existing integration ID** could still be normalized to GitHub Actions App `15368` without explicit administrator review. This is an unreviewed native security configuration change, not a safe null/unscoped tightening.

**TDD RED:** [test-only commit `cf2e4eec040f606eb824ffd7d357d13737697291`](https://github.com/rumman52/Shuddho/commit/cf2e4eec040f606eb824ffd7d357d13737697291), [GitHub Actions #44778941841](https://github.com/rumman52/Shuddho/actions/runs/44778941841), `test-and-build` **5 expected FAIL, 2,726 PASS, 102 SKIP, 6 WARN**. All five new mismatch/type-confusion tests reached dry-run without an error; the two safe-positive cases passed. This deliberately RED run is not source acceptance. **Fix:** `scripts/reconcile_main_ruleset.py` now refuses any explicit non-null publisher with a non-integer/mismatched ID for the approved check context, while preserving null/missing IDs and the exact reviewed integration. [Draft PR #828](https://github.com/rumman52/Shuddho/pull/828) carries tests, source fix, [plan](../superpowers/plans/2026-11-20-day1-native-status-publisher-guard.md), and [task contract](DAY1_NATIVE_STATUS_PUBLISHER_GUARD_2026-11-20.md).

**Evidence status:** implemented source only; final-head CI and independent GitHub approval pending. A passing `test-and-build`, frontend or PostgreSQL compatibility suite would remain repository evidence, not native ruleset enforcement, isolated restore, real staging API/worker pairing, live 20/20 recovery, independent D custody, or an exact-release approval. The `governance-audit` skipped on the RED PR event and must not be treated as passing. No ruleset PUT, production flag, deployment, provider purchase, database migration, secrets, customer data, or telemetry mutation performed.

**Exact resume / external owner:** C + repo administrator configure the protected `V01_RULESET_APP_CLIENT_ID` / `V01_RULESET_APP_PRIVATE_KEY` and prove native ruleset `27324410`, no bypass, protected independent review and required first-party checks using negative/positive merge tests. C/Founder authorize staging backup/isolated restore, runtime/schema pairing and bounded budget; independent D holds the evaluation cases (#665); Founder+C approve any pilot release separately. Run `uv run --locked --extra coworker pytest -q tests/test_reconcile_main_ruleset.py tests/test_day1_ruleset_drift.py` on the exact final PR head, read the required CI jobs, and obtain independent human review. [Linear MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout) remains in progress.

---

## 20 November 2026 — Day 1 ruleset status-check preflight ambiguity (draft PR #823)

**SOURCE_ONLY / Day 1 and pilot NO-GO.** On exact base `main` `d88e606615195b88a876317ebb5a8ef79852da41`, the administrator-only `scripts/reconcile_main_ruleset.py` accepted duplicate first-party check contexts and unknown nested status-check fields in the **existing** native ruleset when building a replacement. This could silently discard unreviewed native settings on a subsequent explicitly authorized apply, contrary to the Part 01 D01.T04/G02 policy review boundary.

**TDD source evidence:** test-only commit `6f6ac66cd896ed62456f37084e6d664f61b8e63e`, [GitHub Actions #44774534026](https://github.com/rumman52/Shuddho/actions/runs/44774534026), reproduced two exact missing-error failures in `tests/test_reconcile_main_ruleset.py` (**2 failed, 2665 passed, 102 skipped, 6 warnings** on the general Python job). The positive regression retained a known `coworker` check with an unscoped integration ID that may be tightened to the reviewed first-party policy. Code commit `81790ce1dace118408336070522dab3a556dda2c` adds fail-closed duplicate/unknown-field checks in `_safe_target` before any PUT body is generated. [Bounded plan](../superpowers/plans/2026-11-20-day1-ruleset-status-check-ambiguity.md). **Corrected final-head CI and independent human GitHub review must be read back separately; neither is inferred from the RED result.**

**Post-diff safety review:** An early `already_configured` return also bypassed the first correction for a policy that otherwise met all required native rules. Additional test-only commit `29afffb9650c0bd497a96dc87ffc4ef3d03e4e06` covers duplicate/unrecognized fields on that compliant path, and source commit `91bc6653280c63eb281b5c3dadb47c814e5b1b84` centralizes the fail-closed check before either policy outcome. The final-head CI and independent review remain unverified until readback; the initial RED run's counts do not apply to this final source tree.

**Repository/hosted boundaries:** The checked-in policy still demands one independent approval, stale-review dismissal, last-push approval, thread resolution and strict first-party `test-and-build`, `coworker`, `ci-merge-gate` checks, without bypass actors. No native ruleset, protected audit App identity, secret, migration, deployment, provider, billing, telemetry, production flag or cohort was changed. Read-only Supabase confirmed `shuddho-staging` PostgreSQL 17.11 with 84 private tables, Alembic `0070`, zero Auth users and zero staging bucket objects; the source migration head remains `0072_merge_0071_heads`. Connected Vercel project search found no Shuddho project. Render's `Rumman` workspace was listed but not operator-confirmed, so live API/worker pairing has not been verified.

**External blockers / exact resume:** C and repository administrator must provision `V01_RULESET_APP_CLIENT_ID` and `V01_RULESET_APP_PRIVATE_KEY` in both protected `v01-governance` and `pa10-staging` environments, then run the checked-in reconciler with a **fresh exact main SHA** and an admin token through the protected operator environment, inspect the policy fingerprint and independently prove negative/positive native merge controls; no unconditional apply. C/Founder must approve isolated backup/restore target, staging runtime/schema pairing, worker/provider budget and privacy limits; D must independently custody the held-out cases (#665); the Founder and C must separately approve any exact-release pilot. From repository root for source verification: `uv run --locked --extra coworker pytest -q tests/test_reconcile_main_ruleset.py tests/test_day1_ruleset_drift.py`. Draft [PR #823](https://github.com/rumman52/Shuddho/pull/823) remains pending independent current-head review and complete required CI. The 100-task/54-gate structural inventory (#818) is not attested acceptance.

---

## 20 November 2026 — Day 10 first-run exact-release/scorecard binding (PR #822)

**SOURCE_ONLY / pilot NO-GO.** The Part 05 Day 10 D10.T04/D10.G04 contract requires the Day 9 first-run and independent holdout to be for the exact same frozen source revision, rollout digest and manifest. On merged `main` `6bdcd9667ab89d91d296146ab14731fdfde797cd`, `day10_release_decision.decide` only accepted any syntactically valid earlier first-run revision/digest and nonempty `scores`, even though the Day 9 report/holdout pair are generated from the same original attempt. A historical test incorrectly asserted a pre-fix manifest could still authorize a newly changed candidate. **TDD RED:** synthetic test-only commit `1607724cc9fe71699b9d116dec393a1d2c15dcd1`, [Actions #44755986612](https://github.com/rumman52/Shuddho/actions/runs/44755986612), **20 expected negative failures / 2,595 passes / 102 skips**; old release gate returned READY despite tampering with first-run revision, rollout digest, manifest, scores, rubrics and IDs. No real private data was used.

**Bounded source remedy:** [draft PR #822](https://github.com/rumman52/Shuddho/pull/822), `codex/day10-first-run-exact-release-binding-20261120`, introduces `first_run_matches_holdout` for exact release/source/rollout/manifest identity, 40 unique case IDs, identical review/security/deterministic/source outcomes between first-run report and protected holdout receipt, and recomputed case and cell acceptance aggregates. Legitimate rejected case rows remain in the 40-case denominator and can preserve low original reviewer scores. Historical reports remain intact as archival evidence but cannot be re-attached to another release to declare pilot readiness. Other source gates, thresholds and owner authority are unchanged. [Task contract](DAY10_FIRST_RUN_EXACT_RELEASE_BINDING_2026-11-20.md), [Superpowers plan](../superpowers/plans/2026-11-20-day10-first-run-exact-release-binding.md). **New exact-head CI/independent review pending; NOT repository-verified yet.**

**Read-only hosted readbacks:** Supabase `shuddho-staging` remains Alembic `0070` vs repository `0072`. Render has listed workspace `Rumman` but none selected by the operator (no permission to choose unilaterally). Vercel connection returns no Shuddho project; connected ProductOS project is unrelated Dust2Glow; PostHog 675660 has no event ingestion. These are nonqualifying infrastructure states. D still must authenticate the private 40-case/80-blinded-reviewer corpus, and C the exact-identity 20/20 operated DB/Temporal/storage matrix and native governance App/ruleset; Founder and Owner C must separately authorize. No deployment, migrations, production flags, provider, purchases, private holdout, telemetry writes, or pilot admission.

---

## 20 November 2026 — D01.T02 100-task/54-exit source-inventory reconciliation (draft PR #818)

**Scope/authority:** [Draft PR #818](https://github.com/rumman52/Shuddho/pull/818), branch `codex/day1-100-54-evidence-reconciliation-20261120`, branched from exact `main` `f5090638be33d7e648736daf533e4b25c307d13d`. **SOURCE_ONLY / NO-GO**; no independent review, staging execution, release freeze or activation is asserted. This bounded slice updates evidence **inventory**, not any of the task/exit acceptance states.

**Authoritative row-level source:** Reopened the connected [original ten-day plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit), then read the current GitHub execution issues [#727–#736](https://github.com/rumman52/Shuddho/issues/737). The issues have exactly **10 numbered implementation tasks each** (100 total) and **5 exit checkboxes for Days 1–8, six for Day 9, eight for Day 10** (54 total). All **54 issue exit checkboxes were unchecked** at this readback. The Day 3, Day 4 and Day 7 issues are marked closed, but their exit gates are unchecked; issue closure alone is not acceptance. The snapshot [TEN_DAY_100_TASK_54_GATE_SNAPSHOT_2026-11-20.json](TEN_DAY_100_TASK_54_GATE_SNAPSHOT_2026-11-20.json) preserves every row, its exact issue-reported text/status/owner and issue update timestamp with `NOT_ATTESTED` semantics. [Validator](../../scripts/validate_ten_day_acceptance_snapshot.py) and [tests](../../tests/test_ten_day_acceptance_snapshot.py) reject invented attestation, missing/duplicate/wrong-day rows, booleans-as-strings and a forged release-ready status. **A passing structural validator is not an operational or independent qualification receipt.**

**Historical count discrepancy:** The older **17/100 versus 18/100 implementation tasks** and **5/54 exits** are **not independently reconciled as accepted completions**. This source-snapshot can verify row inventory, not which tasks were independently reviewed and accepted on an exact source/staging release. The safe reported completion numerator remains **UNATTESTED / unresolved**, not an invented 17, 18 or zero accepted tasks. Owner C and independent D must reconcile each claimed completed row with the source SHA, review, CI, exact release identity and operated evidence wherever the task requires it; a copied markdown status or unchecked issue must never change the denominator.

**Fresh source/CI readback:** Merged PRs [#809](https://github.com/rumman52/Shuddho/pull/809), #810, #811, #812 and #813 are already present on `main` `f5090638be33d7e648736daf533e4b25c307d13d` and are not reimplemented here. PR #809's application/browser/frontend/PostgreSQL tests passed, but its independent-review `ci-merge-gate` failed and the review API exposed no submitted review before it merged. Main [CI #44736754897](https://github.com/rumman52/Shuddho/actions/runs/44736754897) on this baseline had passed application, browser, frontend and PostgreSQL 18 checks, while `governance-audit` failed and Coworker remained in progress at the source-inventory readback. This is **not full final-head CI green**. The new PR's exact-head checks/reviewer remain pending until read back separately.

**Read-only operations:** Supabase `shuddho-staging` still reports private `shuddho_coworker` schema (84 tables) at Alembic `0070`, versus checked-in `0072_merge_0071_heads`; zero Auth users and stored objects. Render's known staging API remains on old `0e0b662fad0a02817a79a4514abba8f94e0ad022`, and no dedicated Shuddho worker is present in the inspected workspace. Vercel has no connected Shuddho project. PostHog's exposed default project is not an approved telemetry destination. No operator-proven model/worker/DB/S3 release pair, independent holdout custody, 40 live evaluated cases, 20 operated recovery cases or authentic separate Founder/Owner-C release approvals were established.

**Required owner actions:** C/repository administrator — restore protected audit identity (`V01_RULESET_APP_CLIENT_ID` / `V01_RULESET_APP_PRIVATE_KEY` through approved environments), enforce ruleset `27324410` with independent required review, stale-review policy and strict status checks, and prove negative/positive controls before merge. C/Founder — separately approve exact staging restore target, data retention/credentials, worker/Temporal/storage, budget and provider. D — independently custody/review unseen holdout and operated traces (issue #665). Founder and C — only later, separately sign the same exact qualified release digest. Until then high-authority and production features remain disabled; the pilot remains **NO-GO**.

**Verification to run:** `python -m scripts.validate_ten_day_acceptance_snapshot`; `python -m pytest tests/test_ten_day_acceptance_snapshot.py -q`; then the existing full PR-head tests, browser, PostgreSQL 18 and governance gates. Do not infer acceptance from a draft PR or a test-only receipt.

---

## Day 9 immutable first-attempt failure/timeout evidence — 20 November 2026 (Asia/Dhaka)

**SOURCE_ONLY / Day 9 and Day 10 NO-GO.** [PR #817](https://github.com/rumman52/Shuddho/pull/817) repairs D09.T04 first-run result accounting: before this change, `candidate_ledger` unconditionally required a valid draft for each of 40 outputs and could not preserve an actual first-run failure/timeout in the cohort. Test-only commit `3042a737cdf1fafc9495bfd54b9e4c7142341dd8` reproduced **11 failed / 2545 passed / 101 skipped** in [exact-head CI #44739458984](https://github.com/rumman52/Shuddho/actions/runs/44739458984); specifically failed/timed-out attempts raised `candidate output must be a draft object`. This was RED evidence, not release qualification.

The bounded source correction adds explicit `failed` and `timed_out` first-run rows with no draft and no source citations; each must carry a private trace digest, failure code, ordered timestamps, unique run, complete frozen candidate identity and canonical hashed failure record. The evaluator retains **40/40 first-run** case rows and 80 distinct reviewer scores, rejects a forged deterministic PASS for a failed attempt, preserves unknown usage as unknown, and discloses `evidence_kind=failure_record` / `output_present=false` in the receipt. Existing successful draft schema and Day 9 quality/security gates remain unchanged. Operator schema: [DAY9_PILOT_QUALIFICATION_2026-11-12.md](DAY9_PILOT_QUALIFICATION_2026-11-12.md). Task contract: [DAY9_FIRST_ATTEMPT_FAILURE_CUSTODY_2026-11-20.md](DAY9_FIRST_ATTEMPT_FAILURE_CUSTODY_2026-11-20.md).

**Levels:** implemented on review branch; final-head required CI and independent review pending. Not staging-verified, not independently custodied, not production-qualified or activated. Human D still owns the protected 40-case corpus/80 genuine blind scores and human C the platform-authenticated 20/20 recovery matrix; Founder and Owner C still hold separate Day 10 signoffs. Native governance App identity and ruleset approvals remain admin-blocked. No paid infrastructure, provider calls, telemetry ingestion, migrations, production flags, pilot admission or external sends were performed.

---

## 20 November 2026 — Recovery of failing main CI after #804 / #805

**Status: proposed source/CI fix, not operated release approval.** Main revision `8abb5972e6b03e86bc891d736eb2854b63c53b61`; review branch `codex/fix-main-ci-day2-day7-day8-20261120`. [Main CI #44598107021](https://github.com/rumman52/Shuddho/actions/runs/44598107021) provided reproducible RED evidence: `test-and-build` 1 failure / 2,531 passes / 93 skips (owner-B error regex casing), Coworker Day 8 focused group 28 failures / 168 passes (an un-unpacked three-field evaluator return and a briefing fixture missing its required v3 feature dependencies), and governance plus merge gates failed. Frontend, browser qualification, and PostgreSQL 18 compatibility passed.

**Bounded correction on this branch:** unpack the validated Day 8 first-run/rerun/provenance result; preserve 40 first-run quality denominators and first-run latency, but include retry/rerun expenses and distinct provider usage/run evidence in the economic decision. Require explicit first-run and rerun provenance before any `FROZEN_FOR_DAY9` decision. Add positive and negative synthetic regression tests for the effect of expensive reruns, missing rerun expense/provenance, legacy v1 evidence and cross-profile receipt reuse. Correct the Day 2 expected error capitalization (the implementation already denies the foreign owner before private writes), enable the existing four briefing prerequisites only for the Day 7 successful completion-notification test (defaults remain off), and bind new briefing completion notices to the unique occurrence ID as required by the Day 7 one-notice contract. A legacy start-notice row is not mislabeled as a new completion.

**CI follow-up:** [PR #809 run #44603189941](https://github.com/rumman52/Shuddho/actions/runs/44603189941) confirmed 2,532 passing Python cases but exposed the missing completion-notice occurrence link (Day 8: 200 pass / 1 fail). After that source correction, [run #44604661596](https://github.com/rumman52/Shuddho/actions/runs/44604661596) passed focused Day 8 checks; it was cancelled when explicit legacy negative-test collection was added. [Run #44607002253](https://github.com/rumman52/Shuddho/actions/runs/44607002253) then failed the self-check that literally matches two adjacent Day 8 module paths in the CI command; the checked-in command was adjusted to retain that validated adjacency while still collecting the new legacy test. These RED and partial GREEN receipts are not a complete exact-final-head job, and no task, exit, or day is accepted from them.

**Evidence boundary:** no provider calls, migrations, new permissions, staging/production changes, external sends, billing, or feature flag activation. The branch changes the local evaluator, a narrowly bounded briefing notification linkage, and tests, not the actual frozen model/release. Required exact-final-head PR CI and independent review remain prerequisites for repository acceptance; operator-authenticated staging and Day 8 measurement remain independently blocked. **Do not credit ledger tasks/exits or accept the pilot from synthetic CI alone.**

**Persistent external blockers:** administrator and Owner C must configure the protected repository-scoped GitHub App audit identity and reconcile native ruleset `27324410` to require independent approval and verified strict CI. Owner C must approve an isolated backup/restore target, reconcile Supabase staging `0070` to reviewed source `0072` on disposable rehearsals, verify matching API/worker identity and budget; independent D must supply external holdout custody and human review. Founder/C approval remains necessary for paid resources and any production activation. The main governance audit continues to fail with missing client ID and the native ruleset remains under-protective. Historical source-only work #804/#805 was merged without submitted independent reviews; those merges are not proof of effective approval enforcement.

---

## Mandatory CI source-contract repair — 20 November 2026 (Asia/Dhaka)

**Source-only / pilot NO-GO.** Following merged Day 6 PR #804 and Day 2 PR #805, main `8abb5972e6b03e86bc891d736eb2854b63c53b61` failed [CI run #44598107021](https://github.com/rumman52/Shuddho/actions/runs/44598107021). The Python `test-and-build` gate reported **1 failed / 2531 passed / 93 skipped**: a Day 2 missing-control pre-write denial test required the lowercase phrase `owner B` but the actual fail-closed `Day2Failure` begins `Owner B`. The mandatory Coworker Day 8 step reported **28 failed / 168 passed**: `compare_day8_development` treated the tuple returned by `_day8_cases` as a mapping, and a positive-path briefing notification test omitted the already-defined `_enable_briefings` fixture prerequisite. The live main governance audit also failed because the GitHub App `client-id` input was empty; this is a separate, owner-admin external blocker.

**Bounded patch:** Unpack the Day 8 parser's mapping/rerun/provenance return value without changing scoring rules; correct only the Day 2 test regex capitalization; explicitly enable the four existing briefing prerequisites in the single positive-path test. No production authorization or feature defaults changed. Work branch `codex/restore-main-ci-day2-day7-day8-20261120`; plan [2026-11-20-restore-main-ci-source-contracts.md](../superpowers/plans/2026-11-20-restore-main-ci-source-contracts.md); contract [CI_REPAIR_DAY2_DAY7_DAY8_2026-11-20.md](CI_REPAIR_DAY2_DAY7_DAY8_2026-11-20.md).

**First PR-head RED and follow-on correction:** [run #44602686715](https://github.com/rumman52/Shuddho/actions/runs/44602686715) passed general Python, browser, frontend and ancestry; its focused Coworker Day 8 gate narrowed from 28 failures to **1 failed / 195 passed**. That remaining test exposed a genuine completion-notification linkage defect in `AutomationRepository.notify_run_completed`: briefing completion enqueue omitted `occurrence_id`, despite briefing intentionally not emitting a start notice to preserve the unique occurrence slot. A bounded runtime repair now attaches occurrence identity **only for briefing**, retaining separate start/completion notices for non-briefing profiles. The existing briefing test is the RED acceptance test; a non-briefing regression now asserts the separate-notice behavior. Fresh exact-head CI and independent review remain required.

**Verification level:** RED reproduced from exact main CI. Exact-head PR CI, full Coworker job, independent review and merge governance **pending**. Staging, PostHog telemetry and release flags unchanged. The independently held 40-case Day 9 cohort, 20 platform-authenticated recoveries, authentic Founder/Owner-C signoffs and pilot admission remain **not established**. Do not promote source tests to live acceptance.

---

## Day 6 export-manifest rejection regression — 19 November 2026 (Asia/Dhaka)

**D06 / [#732](https://github.com/rumman52/Shuddho/issues/732): source-only regression repair in draft [PR #804](https://github.com/rumman52/Shuddho/pull/804); hosted Day 6 acceptance remains NO-GO.** Base `main` `8afcfccf409c5a01fd70a7966fb4b538575f502f`; branch `codex/day6-export-manifest-rejections-20261119`; verified source/test commit `5acda35daa1ffdaf63d3ac1ca9b335199b78141e`; PR merge SHA for the verification run `12f8513402b887803f012a190dfc0b486bdc46d1`.

**RED reproduced on GitHub CI:** initial gate-only PR head `1664c8b38b80e99ea002866a131cef1952b000b7`, [run #44582729097](https://github.com/rumman52/Shuddho/actions/runs/44582729097), **3 failed in 7.35s**. The test supplied synthetic non-native DOCX/PDF bytes and expected a completion-phase error even though `validate_day6_exports` correctly rejected the malformed renderer output during `DocumentRunner.export`.

**Source fix:** no production code was changed. The test now separates (1) missing/duplicate/unexpected renderer file sets, (2) malformed DOCX/PDF bytes, and (3) missing/duplicate/unexpected persisted manifests after a real native render. It asserts export-time failures produce zero storage PUTs, and all rejected paths leave the task failed with zero published artifact records. The persisted-manifest cases use the existing native renderer and verify four successful private-storage PUTs before completion refuses publication. Coworker CI now explicitly runs this module with the coworker extra, a required-module/no-skips JUnit gate, and retained evidence.

**Exact code-head verification:** [PR run #44583092791](https://github.com/rumman52/Shuddho/actions/runs/44583092791): export-manifest gate **8 passed / 0 failed / 0 skipped** (JUnit artifact `14560960395`); broader Day 6 workflow suite **111 passed / 0 failed / 0 skipped** (artifact `14560006846`); offline quality evaluation **14/14 passed**. General test-and-build, frontend tests/build, browser qualification, and PostgreSQL 18 compatibility passed. Vercel GitHub integration posted a Ready preview. The full Coworker job was still running unrelated downstream qualification at the last readback (step 47/79); no full-job GREEN claim is made. Governance audit is skipped while the PR is draft.

**Read-only hosted blockers:** Supabase staging remains Alembic `0070`, with zero Auth users, Coworker accounts, AgentRuns, tasks, artifacts, outbox rows, and objects in the one private storage bucket. Render workspace `Rumman` is listed but not selected, so no service/worker readback or restart was performed. No PostHog ingestion or instrumentation was performed. No staging mutation, provider call, email send, deployment, migration, or paid resource was used.

**Disposition / next action:** keep PR #804 draft and #732 open. Full Coworker CI completion, independent human review, approved synthetic owners A/B, matching hosted API/worker/schema identity, and operated golden workflow evidence remain prerequisites. No Day 3–6 hosted acceptance or pilot activation is claimed.

---

## Day 1 restore-drill source identity — 19 November 2026 (Asia/Dhaka)

**D01.T06 / [#727](https://github.com/rumman52/Shuddho/issues/727): source guard implemented; operated staging recovery pending.** Base `b13ce501ba05073e3038e9c6cfab1b99b3876dc8`; branch `codex/day1-restore-fingerprint-validation`. The drill opened the restore target before validating both source fingerprints and prepared records before checking source identity. It now reads and records source fingerprints before the owner API or synthetic record creation. Verification requires both existing lowercase SHA-256 fingerprints before opening the target and rejects either matching source resource. The state format and valid prepared manifests are compatible.

**Local verification:** the regression suite reproduced 9 failures before the fix and passed all 19 tests afterward with zero skips. The Day 1 baseline passed 4 tests. The pinned 80-case source registry validated (40 development and 40 candidate holdout cases), manifest SHA-256 `72e0c27e3698b4835e7975889b31da5a48b675229caf4db500b8ca0fa71e2a9a`. Exact PR checks and independent review are tracked on GitHub.

**Open gates:** [main CI #44486151708](https://github.com/rumman52/Shuddho/actions/runs/44486151708) failed the GitHub App audit and merge gate. Live ruleset `27324410` has zero required approvals and no required status-check rule. Owner C and the repository administrator own credential setup, policy reconciliation and merge controls. Owner C also owns the approved isolated restore and migration rehearsal: Supabase staging is at `0070`, with zero Auth users and storage objects, and source expects `0072_merge_0071_heads`. Human D owns independent holdout access and review [#665](https://github.com/rumman52/Shuddho/issues/665). The existing completion totals are unreconciled. **SOURCE_ONLY / NO-GO.**

---

## Day 10 runtime-manifest derived-field reconciliation — 19 November 2026 (Asia/Dhaka)

**Source-only, NO-GO.** On `main` at `33aefddc5a5fd918d334c981769c6f9cf1b0b5bf`, authenticated API handler source emits **44** fields while PA-10 freeze, Day 10 release, and full-cohort verification require **exactly 43**. The one extra `grounded_conversation_replies` is a UI-specific derived indicator matching `conversation_replies`; removing it would disable a web UI capability signal. This branch centralizes strict matching: API requires the 43 original reviewed flags plus exactly one matching, boolean derived indicator; rollout/worker and generation identity remain exactly 43. Unknown/missing/numeric/independently toggled flags fail closed. Actual API-handler AST check and synthetic negative regressions added; review contract: [DAY10_RUNTIME_MANIFEST_CANONICAL_2026-11-19.md](DAY10_RUNTIME_MANIFEST_CANONICAL_2026-11-19.md). **Exact-head CI and independent review still pending.** No infrastructure, cohort, credentials or approvals touched; prior ledger **17/100 tasks, 5/54 exit checks, 0/10 accepted days** unchanged. Fresh D-owned 40-case review, C-operated 20 scenarios, live quality, distinct Founder/Owner-C approvals and admission remain absent. **No pilot admitted.**

---

## Day 10 post-admission member-account identity binding — 19 November 2026 (Asia/Dhaka)

**Status: SOURCE PATCH ON REVIEW BRANCH; LIVE PILOT NO-GO.** Base `33aefddc5a5fd918d334c981769c6f9cf1b0b5bf`. [PR #796](https://github.com/rumman52/Shuddho/pull/796) closes a false-positive operated-acceptance gap: the existing complete-cohort verifier counted any HTTP 200 from `/api/v1/me` without confirming the server returned the account identified by that member's signed token. The actual API returns a JSON `account_id`, and the existing admission prerequisite already validates each member's signed identity against the exact backend allowlist. Now the verifier carries that exact mapping into each HTTPS probe, rejects mismatched/absent/malformed/duplicate identities without outputting sensitive data, and preserves the existing fresh-nonmember denial and before/after nonprovisioning checks.

**RED, verified on genuine GitHub CI:** tests-only head `2c559fe47d15201f3b01b6eb6b9beba2f274b010`, [PR run #44390228483](https://github.com/rumman52/Shuddho/actions/runs/44390228483), mandatory Day 10 source step failed: **15 failed, 35 passed**, because `probe_access` did not accept expected member IDs. **Source fix:** initial code head `59a5d591b6e1d4d0d97197914458357f22aa5576`. Final head and complete CI must be freshly read after documentation commits; do not claim GREEN or successful merge before readback. No runtime admission, secrets, external provider, schema, worker, staging deployment, product feature flag, analytics event or policy mutation in this PR.

**Independent source/release boundary:** code-owner review remains required even if GitHub's active native ruleset `27324410` still improperly allows zero approvals. Founder/C must authorize isolated staging setup, distinct reviewer/custody, genuine live complete-cohort observations and rollback before the original D10 tasks can be marked PASS. The existing off-repo execution ledger remains **18/100 verified task PASS, 5/54 exit PASS, 0/10 accepted days** at this checkpoint; never interpret source tests as production qualification.

---

## Day 10 full-cohort post-admission verification — 19 November 2026 (Asia/Dhaka)

**Status: source implementation on review branch; live Day 9–10 NO-GO.** Review base `cebe322d88d2120e6c78c6755b70445eedf8c39f`. The existing staging cohort smoke test exercises one invite and one denial; new `scripts/pilot_admission_verify.py` performs exact-release, complete 5–10-member HTTPS and fresh nonmember DB/API boundary verification **only after** manual authorized admission. It validates the actual rollout digest and Day 10 READY receipt, exact backend allowlist, private member tokens and immutable output. It does not change allowlists or activate a pilot. Synthetic regressions are in `tests/test_pilot_admission_verify.py` and explicitly mandatory (zero skips) in Coworker CI, with a retained JUnit artifact; executable operator contract: [DAY10_PILOT_ACCESS_FULL_COHORT_2026-11-19.md](DAY10_PILOT_ACCESS_FULL_COHORT_2026-11-19.md).

**Read-only live blockers:** Supabase staging `0070`, zero Auth users, accounts and AgentRuns; no Render persistent Shuddho worker or matching API/worker release identity; no human D custody, blinded reviewers, forty operated first-run cases, twenty real recovery scenarios, live quality, distinct Founder/Owner-C approvals or admission. The previous ledger remains **17/100 task PASS, 5/54 exit PASS, 0/10 fully accepted days**. CI on this exact new branch and human review must be checked independently; none is claimed here. Owner C and Founder must authorize any billable/live environment actions before operation. **Pilot admission: NOT PERFORMED.** Day 9/10 remain open.

---

## Day 8 — mandatory privacy/redaction CI qualification (19 November 2026)

- **Source baseline:** `cebe322d88d2120e6c78c6755b70445eedf8c39f` includes merged telemetry schema/redaction PR #788. The mandatory Coworker Day 8 CI step ran only `tests/test_core_agent_observability.py`; the new `tests/test_day8_telemetry_privacy.py` was not explicitly protected by a required-module/no-skips gate. The general fast Python sweep is not sufficient evidence for the mandatory Coworker gate.
- **Reproduced before patch:** a new source contract test against the exact baseline Day 8 workflow step failed because the privacy test and explicit required-module check were absent.
- **Fix:** the mandatory Day 8 Coworker CI job runs economics and privacy tests into one JUnit report and checks both module names with `scripts.mandatory_test_gate` (rejects zero collection, skips, failures and errors). The new test guards the workflow against silently removing this coverage. No runtime code, event sink, credential, worker resource, release flag or DB schema was changed.
- **Local checks:** CI-contract test 1 passed; privacy suite 39 passed, 0 skipped, JUnit classname `tests.test_day8_telemetry_privacy` verified. Full exact-PR-head CI, independent review and staging emission still require separate evidence.
- **Status:** SOURCE PREPARED / STAGING NO-GO. D08.T04 still needs exact-head CI and D-reviewed independent privacy signoff. D08.T03 remains disabled without Founder/C approved destination, retention, consent and hosted delivery proof. Day 1 native ruleset `27324410` still requires an authorized administrator; no human-review/policy control outcome is claimed.

## Day 5 Runtime v3 memory correction race — 18 November 2026 (Asia/Dhaka)

Review base: `main` `c8aa7cf8444f1cf8c5408568e78b3cae6792f00a`.
Draft [PR #776](https://github.com/rumman52/Shuddho/pull/776) addresses a
fresh-decision race, without replacing merged #723, #740 or #742.

**RED reproduced before production-code changes.** The new delayed-planner
regression corrected a selected synthetic memory from version 1 to version 2
after context assembly, while the planner was in flight. The unpatched commit
path accepted that stale decision: exact-head [CI #44287313414](https://github.com/rumman52/Shuddho/actions/runs/44287313414),
mandatory Day 5 gate, **80 passed / 1 failed / zero skipped**, with
`Failed: DID NOT RAISE CoworkerError`. Its JUnit artifact was preserved.

The bounded correction rechecks explicit memory pins in
`AgentRepository.record_v3_decision` before a **new** planner decision is
persisted. It reuses `require_current_memory_pins`, preserving current
owner/workspace/version/expiry/deletion/feature-gate checks and maintaining
the existing early return for committed-decision replay. No migration,
provider, external action or production toggle was added. A second regression
retains committed replay but denies a new planner call after correction.

A **non-LLM deterministic** three-arm integration regression now holds the
task source/prompt, synthetic renderer and context budget fixed, exercising
no-memory, selected v1 and corrected v2 via the real preview, dispatch and
worker-context methods. It records SHA-256 references and per-arm rubric
scores in the Day 5 JUnit artifact, plus a second-owner normal-read denial.
These synthetic outputs demonstrate wiring only and **do not** qualify a
live DeepSeek model or the golden task. Corrected-head CI/independent
review and operated staging output comparison remain separate requirements.

Fresh read-only staging inventory on 18 November: Supabase Alembic `0070`
with zero Auth identities, application accounts, workspaces, memory facts,
Agent runs and registered workers. Render exposes the Shuddho staging API
but no persistent worker. The connected Vercel account has no Shuddho-linked
project; PostHog and Linear do not expose a matching Shuddho project. Staging
identity, Temporal/worker, S3 custody and authorized fixed-budget inference
must be supplied before a real three-arm run. The private database schema
has RLS disabled, but `anon` and `authenticated` currently lack schema
USAGE and memory-table SELECT; no policy or privilege change was made.

Owners: B selects/corrects and scores real outputs; A independently
revalidates; D verifies run receipts, security denial and evidence custody.
Keep pilot/production activation disabled, do not provision paid compute or
send external messages without explicit owner authorization. The next
executable step is to verify exact final PR-head Day 5 and broader CI, then
arrange approved nonproduction synthetic Auth users, persistent worker,
Temporal/S3 configuration and three fixed-model output receipts.

---

## Day 9 historical provenance CI repair — 18 November 2026 (Asia/Dhaka)

**Status: SOURCE ONLY / NO-GO; exact-head CI and independent review pending.**
Main `d1bed1e0f65703df67a740b94e2768fdf69abb49` already contains the Day 9 CI preflight from merged [PR #784](https://github.com/rumman52/Shuddho/pull/784); that PR was merged at its **failing** earlier head `91769b122d7aa3cc38b615c009efdeb7170ee33b` without a submitted independent review (confirmed via API), notwithstanding its recorded 109-pass/1-fail preflight. The red failure was caused by the Coworker job using a depth-one checkout for a valid, Git-authenticated historical source fixture. Main `test-and-build` already fetches full history. This work branch adds only the matching full-history checkout to Coworker, preserves the provenance assertion and records red evidence in [Day 9 task contract](DAY9_SOURCE_PREFLIGHT_CI_2026-11-18.md). The first CI run and any later repaired CI are distinct. **The unreviewed red-CI merge is a governance blocker requiring admin audit; never use it to qualify Day 9 or Day 10.**

No held-out data, model calls, stage migration, external send, credentials, live C fault operations, or paid resource was accessed/changed. Day 9 remains NO-GO pending C-authenticated runtime freeze and 20 operations, D custody/replacement and 40 first-run outputs, two blinded reviewers, and main governance/CI restoration.

---

## Day 9 source preflight CI enforcement — 18 November 2026 (Asia/Dhaka)

**Level: source-only PR; exact-head CI pending; Day 9 NO-GO.**
Main `aa705726f4c76cbb819a62211b7743aa44c59b17` has merged [#774](https://github.com/rumman52/Shuddho/pull/774), which fixed the native export fault-fixture failures reproduced in [CI #44278207003](https://github.com/rumman52/Shuddho/actions/runs/44278207003). Do not duplicate that patch. A separate, directly observed acceptance gap remains: the required Coworker CI workflow does not invoke the Day 9 `validate-registry` or `preflight` commands or separately gate the Runtime v3 helper tests. Branch `codex/day9-source-preflight-ci-20261118` adds precisely those source-only mandatory steps, preserving immutable D-held inputs and all opt-in live provider tests; the helper suite has an explicit zero-skip gate and CI artifact. See [task contract](DAY9_SOURCE_PREFLIGHT_CI_2026-11-18.md).

No new API, worker, model, storage, database, permission or feature flag is activated. This is **not** an independent freeze, D custody authentication, 40-case first run or 20 C-operated recovery receipts. Actual Supabase staging is PostgreSQL 17.11 / Alembic 0070 vs source 0072 head; required main governance still fails on missing App client ID and policy drift. Await exact final-head CI and independent GitHub review. C/owner administer governance and authorize staging operations; human D privately establishes #665 custody; reviewers and C carry out observed evaluations and operations. No owner-authorized billed resources or external sends were performed.

---

## Day 1 native export fault-fixture repair — 18 November 2026 (Asia/Dhaka)

Status: **TEST-SOURCE CANDIDATE / NO-GO**, in [draft PR #774](https://github.com/rumman52/Shuddho/pull/774), based on main `c8aa7cf8444f1cf8c5408568e78b3cae6792f00a`. This does not claim a merged fix, green final-head CI, hosted qualification, or production activation.

Exact-base [CI #44278207003](https://github.com/rumman52/Shuddho/actions/runs/44278207003) reproduced two failures after merged #766 enforced four validated native Day 6 exports before storage. The original ambiguous-PUT test generated three fake plaintext files; the hard-worker-loss child generated one fake plaintext file. Neither could reach the intended fault boundary, and the full Coworker job reported **2 failed, 1,628 passed, 4 skipped**. The frozen #769 capacity/sandbox/Fly gate still passed **4 tests, 0 skips**.

PR #774 changes only the two test fixtures: use the existing native renderer before injecting the second-PUT response loss or process SIGKILL; freeze the native bytes across ambiguous-PUT replay so content-addressed object names are stable despite DOCX/PDF metadata; assert four recoverable files and that a persisted orphan's bytes match its digest. Production `validate_day6_exports`, storage, cleanup and CI gate behavior remain unchanged.

The exact-head CI URL and independent GitHub review must be attached to #727 after final completion. Do not relabel skipped governance on PR checks as a passing main governance audit. Current native ruleset 27324410 lacks required independent review and checks; C/admin own its approved repair and positive/negative controls. Supabase staging remains at Alembic `0070` vs source `0072_merge_0071_heads`, with no authenticated synthetic owners or verified isolated restore. D independently owns new heldout cases and read-denial/custody receipts (#665). Provider identity/spend and Founder approvals remain missing. No production deploy, paid provision, credentialed probe, external send or private case transfer occurred. Remain **NO-GO**.

---

## Day 10 CTO handoff and live blockers — 17 November 2026 (Asia/Dhaka)

The current Day 10 disposition remains **SOURCE_ONLY / NO-GO**. The exact main
snapshot is `8f92814ab5f25d1214596d63213824c7ba577a93`. Main test/build, frontend,
Coworker, browser and PostgreSQL 18 checks passed, but `governance-audit` and
`ci-merge-gate` failed because the GitHub App client ID is not configured.
The active ruleset currently reports zero required approving reviews; the
workbook requires an independent reviewer for material changes.

Two source gaps were reproduced and have separate draft fixes:
- [PR #746](https://github.com/rumman52/Shuddho/pull/746) restores the missing
  16,000-byte UTF-8 cap on canonical reviewed-task snapshots, with the lower
  configured Agent context budget applied. It preserves already-admitted
  replay after a later budget reduction. Test-only exact-head CI reproduced
  four oversized Bangla preview/dispatch failures; corrected-head CI is running.
- [PR #748](https://github.com/rumman52/Shuddho/pull/748) tightens Day 10
  rollback, cancellation, paused-schedule and two-way owner-isolation receipt
  validation. Test-only exact-head CI reproduced 31 permissive false-positive
  cases; corrected-head CI is running. It does not create operated evidence.

Fresh read-only Supabase checks confirm healthy PostgreSQL 17.11, 84 private
application tables at Alembic `0070`, a private object bucket, and zero
application accounts/conversations/runs/artifacts, Auth users or storage
objects. `anon` and `authenticated` have no schema USAGE or table privileges
on `shuddho_coworker`; all 84 tables still report RLS disabled. Do not apply
blanket RLS without checking the runtime role and explicit policies. Performance
advisor findings remain informational and unoptimized.

Render workspace selection is pending; the only available workspace is
`Rumman`. The last Render/Temporal/S3 readback in issue #291 is historical
(16 Nov), not a fresh verification. No paid worker is authorized. The connected
Vercel account lists only project `ali`, not a Shuddho deployment.

The full source/CI/staging/approval matrix and ranked next actions are in
[the Day 10 CTO handoff](DAY10_CTO_HANDOFF_2026-11-17.md). No release manifest,
live planner/quality report, independent 40-case holdout, 20/20 operated
recovery receipts, rollback/cancellation/schedule/isolation operation, golden
run, or authentic Founder + Owner-C approvals is established. Keep production
and high-authority flags off; no pilot is authorized.

---

## Day 4 reviewed task brief UTF-8 snapshot budget — 17 November 2026 (Asia/Dhaka)

The previously closed, unmerged PR #726 fix has been ported onto current main
without replacing newer conversation, memory-pin or runtime-v3 changes. The
canonical UTF-8 snapshot is capped at the lower of 16,000 bytes and the
configured Agent context budget. Oversized previews and first admissions fail
with HTTP 422 before creating an AgentRun or outbox effect. Historical retries
retain the original digest semantics after a budget reduction.

Regression tests cover both preview and dispatch, the 16,000-byte and lower
configured ceilings, and replay of an already-admitted task after the budget is
reduced. Exact-head CI and independent review are pending; this source change
does not satisfy the Day 9 custody or operated-evidence gates.

---

## Day 4 admission requires Runtime v3 for reviewed briefs — 17 November 2026 (Asia/Dhaka)

The Day 4 workbook requires Runtime v3 for first admission of reviewed task
briefs. Both legacy runtime variants could previously admit these requests.
Admission now fails before creating a run or outbox entry when Runtime v3 is
off. Unreviewed legacy requests and identical retries of admitted reviewed
work retain their existing behavior.

Both legacy admission cases reproduced on `d3866064`. Hosted qualification
remains open. [Day 4 tracker](https://github.com/rumman52/Shuddho/issues/730)

---

## Day 10 operated recovery traces — 16 November 2026 (Asia/Dhaka)

The release decision now requires the Day 9 trace evidence for each of the
20 named recovery scenarios on the exact frozen release. Missing or simulated
execution and missing or unsafe access and mutation verdicts fail the gate.
Every required PostgreSQL, Temporal, or object storage boundary needs a real
instance reference and trace hash as defined by the scenario inventory.
Operators verify the submitted evidence against the source systems.

Twelve cases reproduced permissive decisions or malformed hash errors on
main at `0e421803`. The corrected release and evidence suites passed 256
tests, and the release-contract check passed. Hosted qualification remains open.

---

## Day 10 distinct pilot approvers — 16 November 2026 (Asia/Dhaka)

The handoff now requires two distinct, valid founder and operations-owner
identities. The gate uses the existing Day 9 identity normalization, so a case
or Unicode width variant of one signer cannot satisfy the second role. The
operator verifies both written approvals at the receipt reference.

Five duplicate or malformed identity cases reproduced an incorrect
`READY_FOR_OWNER_CONTROLLED_PILOT` decision on `main` at `3b6f5acb`.
The corrected result is `STAGING_ONLY` when all technical gates pass. The
focused release and evidence suites passed 244 tests, and the release-contract
check passed. Hosted qualification and owner approval remain open.

---

## Day 3 source citation validation — 17 November 2026 (Asia/Dhaka)

A valid citation could previously mask an incomplete source marker with
altered case or whitespace. The grounding validator now rejects those markers
and accepts repeated citations to the same authorized source. The adversarial
PDF and text fixtures confirm that source instructions stay in untrusted
context and create no AgentRun or outbox entry.

Three malformed citation cases reproduced on `d3866064`. The workbook still
requires hosted bilingual, two-owner qualification.
[Day 3 tracker](https://github.com/rumman52/Shuddho/issues/729)

---

## Day 5 memory pins bound to reviewed tasks — 16 November 2026 (Asia/Dhaka)

Based on merged `main` at `6316689c`. A reviewed brief preview now binds the
exact selected memory IDs and versions. The UI validates after a selection
change, admission rejects a mismatched digest before creating any run or outbox
entry, and worker context checks the stored binding. Previously admitted runs
retain their version-one replay format. Preview requests without selected memory
retain the existing digest and request shape.

Regressions cover changed selections, stale and foreign pins, the HTTP preview
and dispatch path, version-one replay, and mismatched persisted worker pins.
Hosted execution and current-head GitHub CI remain separate evidence.

---

## Day 5 reviewed constraints override saved preferences — 17 November 2026 (Asia/Dhaka)

The current task objective was checked for conflicts with saved preferences.
Review can store a newer explicit instruction separately as a constraint.
Memory assembly now applies the existing deterministic conflict checks to
the objective and each reviewed constraint. An overridden fact stays out
of planner context for that run. Its stored value and version are preserved.

The regression reproduced on main at `d3866064`, with a casual reviewed
constraint and a selected formal preference. Hosted two-owner and quality
qualification remain open. [Day 5 tracker](https://github.com/rumman52/Shuddho/issues/731)

---

## Day 4 reviewed task retries across follow-up turns — 16 November 2026 (Asia/Dhaka)

Base `2cbcae390865585f52cbe5299d52d8add1862db2`. An identical reviewed
dispatch retry previously returned HTTP 409 after a follow-up message even
though its original run and outbox entry had committed. The replay path now
validates the original turn, reviewed digest and current source pins before
returning the linked run. First admission and preview still require the latest
turn. Regressions cover HTTP 200 replay, one run and outbox entry, changed
brief or sequence, and source revocation after a follow-up.

Local verification: 206 focused tests passed. The canonical release-contract
check passed. GitHub CI, independent review, hosted staging qualification and
pilot activation remain pending.

---

## Reuse PR CI results on review events

Review events run `ci-merge-gate` without starting the test suites or
cancelling an in-progress test run. The gate requires all existing test
jobs and the ancestry check to pass for the same pull request, head SHA,
and GitHub test merge SHA before verifying the latest independent approval.
Main push CI and native branch rules retain their existing requirements.
For a review-only gate run, `scripts.v01_merge_evidence` accepts `--ci-run`
with the original test run ID printed in the successful reuse step.

---

## PA-10 ruleset audit integrated with scoped CI — 16 November 2026 (Asia/Dhaka)

PR [#714](https://github.com/rumman52/Shuddho/pull/714) now includes
`main` at `2cbcae390865585f52cbe5299d52d8add1862db2`. Routine PR CI retains its
scope selection and exact-revision review reuse. Native governance on `main`
uses the repository-scoped GitHub App audit. The PA-10 source entry job remains
secret-free. A separate audit guards staging access and runs again after approval.

Local verification: 283 governance, PA-10 and scoped-CI tests passed. The
canonical release-contract check and duplicate-key YAML validation passed.

The live rules endpoint currently lists deletion, non-fast-forward protection,
and PR reviews. Main CI [#43804910236](https://github.com/rumman52/Shuddho/actions/runs/43804910236)
failed the native governance audit. App and environment setup, a successful
live audit and worker qualification are pending. See the
[infrastructure runbook](../../infra/README.md#authorize-the-github-ruleset-audit).

---

## PA-10 live database check before worker provisioning — 16 November 2026 (Asia/Dhaka)

The paid worker workflow now requires the live Supabase database to be reachable
at the candidate's Alembic revision before any worker creation or repair. The
workflow revalidates protected `main` before using the staging DSN. The check's
runner receives the staging DSN only in the read-only migration check, without
the Render, Temporal or storage credentials used by the provisioning job.

Focused tests passed locally (40 passed, one archive process test skipped because
the runner lacks PostgreSQL binaries). The archive process test passed on merged
[PR #712](https://github.com/rumman52/Shuddho/pull/712) before this change.
Native main protection still requires GitHub owner verification. Live backup,
worker provisioning and the managed recovery drill remain pending.

---

## Day 2 recovery receipts bound to the frozen rollout — 16 November 2026 (Asia/Dhaka)

Base `2cbcae390865585f52cbe5299d52d8add1862db2`. The Day 2 acceptance
command previously accepted a set of recovery and restore receipts that agreed
with each other but referenced a different rollout from the release freeze.
Every recovery and restore receipt must now match the rollout SHA-256 carried
by the existing freeze. Missing, invalid and mismatched freeze digests fail
closed. An older receipt without that field requires a fresh release freeze.

Local verification: 175 focused tests passed. The PostgreSQL archive process
test needs PostgreSQL binaries. The canonical release-contract check passed.
Live Temporal recovery, PostgreSQL and private storage restore, and pilot
qualification remain pending.

---

## Supabase staging database backup verification — 15 November 2026 (Asia/Dhaka)

The staging backup command exports only `shuddho_coworker` over the verified
Supabase session pooler. It restores to a disposable local PostgreSQL cluster
and compares the Alembic revision, per-table row counts and row hashes from
the exported snapshot. The archive and receipt are private. GitHub CI
exercises real PostgreSQL utilities and a concurrent source write.

The live runtime role can read all 84 private tables and export a PostgreSQL
snapshot. A live archive and durable backup receipt still require a trusted
operator with the staging DSN and a private backup destination. This database
check is separate from the release-bound recovery drill for PostgreSQL and
private object storage. See [operator steps](../../infra/README.md#back-up-and-verify-the-staging-database).

---

## Replacement staging PostgreSQL — 15 November 2026 (Asia/Dhaka)

The expired Render database returned 404. A clean PostgreSQL 17 database in
Supabase `shuddho-staging` has 84 tables in the private `shuddho_coworker`
schema at Alembic revision `0070`. The restricted runtime role can read and
write application rows, but it cannot create schema objects or change the
migration ledger. A synthetic account and conversation round trip passed in
a rolled-back transaction. Direct verification used no historical data.

The staging Blueprint and PA-10 workflows now read a secret for the Supabase
session pooler. Runtime checks verify the Alembic head without running DDL.
See [staging operations](../../infra/README.md#coworker-staging-on-supabase)
for credentials, schema-owner migrations, and backup recovery. Full hosted
API/worker and external-provider qualification require separate live evidence.

---

## Day 10 reviewer and recovery evidence identity — 16 November 2026 (Asia/Dhaka)

The release decision now applies Day 9 reviewer identity normalization and
checks the exact 20 named Day 9 operated scenarios. A case or Unicode spelling
variant cannot count as a second reviewer. A duplicate, unknown or missing
scenario leaves the release source-only. Actual operator evidence and
independent human review remain required.

Local verification: 145 tests passed across the release and evidence suites.
Exact-head CI and the live release evidence remain pending.

---

## Day 10 holdout security absolute NO-GO — 13 November 2026 (Asia/Dhaka)

**Root cause:** `scripts/day10_release_decision.py::holdout_ok` previously allowed a 39/40 accepted independent holdout with `security_passed=false` or a missing security verdict to reach `READY_FOR_OWNER_CONTROLLED_PILOT` when other submitted gates passed. This contradicts Day 9's absolute security NO-GO rule. No existing release approval or operated evidence was changed.

**Review:** [draft PR #705](https://github.com/rumman52/Shuddho/pull/705), branch `fix/day10-holdout-security-absolute-nogo-20261113`, base main `6b604e4cc13e98f740729f3b11df3ed432e04dcb`. [RED exact-head CI #43461268411](https://github.com/rumman52/Shuddho/actions/runs/43461268411): **three expected security regression failures, 1,947 Python tests passed, 81 skipped**. The targeted fix requires explicit boolean `security_passed=true` for **every one** of the 40 cases, including human-rejected cases; operator handoff and [task contract](DAY10_HOLDOUT_SECURITY_GATE_2026-11-13.md) updated.

**Levels:** implemented in draft source; **corrected-head CI and independent review pending**, staging unverified, production NO-GO, pilot disabled. In particular Render staging PG18 remains billing-suspended, no persistent worker exists, `main` remains unprotected, D custody and 20 operated fault rows are missing. No paid provisioning, migrations, external sends, telemetry or cohort admission.

---

## Day 4 multilingual task-brief budget — 16 November 2026 (Asia/Dhaka)

Task-brief history now drops the oldest turns until the serialized request fits
the provider's UTF-8 byte limit. The proposal reserves the serialized prompt,
output allowance and framing before calling the provider. The workspace and
global capacity limits can reject the request before any model call. The latest
turn remains in the bounded history, and recent selected attachments take
precedence when the planner's source list reaches its limit.

Local verification: 132 focused tests passed, including Bangla requests,
workspace reservations and recent attachment selection. Exact-head CI and
remote staging are pending.

---

## V-01 source safeguard — 13 November 2026 (Asia/Dhaka)

**Scope:** fail-closed pull-request ancestry check. Existing draft PR #695 is 171 commits behind `main` (GitHub compare on `ce8a21046970a94a65d0b53a31da4c55d048e51a` vs `1b98702c602a8e57848175b3063bdad298abb6ae`) and omits previously merged conversation memory-pin admission and revocation checks. A blocking code review was posted to #695. The new guard checks the actual PR head rather than the synthetic PR merge checkout; `ci-merge-gate` rejects failed or skipped PR ancestry checks, while push events remain governed by the existing governance audit.

**Verification:** local synthetic Git DAG regression: 3 passed (stale branch rejected, merged-up-to-date head accepted, malformed/missing commit IDs rejected); Python syntax compilation passed. Branch `fix/ci-pr-base-ancestry-20261113`; base `ce8a210`. Exact remote PR-head CI and independent review pending. No production deployment, ruleset change, model call, paid resource, or release activation.

**Evidence levels:** source implemented on review branch; local unit verified; **repository-wide exact-head CI pending**, staging unverified, release **NO-GO**. This guard is defense in depth only and **cannot replace native protected-main rules**. Owner must still enable main protections, restore authorized staging PG18 and provision a persistent worker, and complete independent holdout/fault-test approvals.

---

## Day 7 briefing receipt chronology — 16 November 2026 (Asia/Dhaka)

The two-day briefing verifier rejects a verification or pause timestamp in the
future and requires actual positive integer automation revisions. The existing
pause command applies the same verifier before pausing the synthetic schedule
and after reading back the paused state.

Local verification: 89 tests passed across briefing, scheduling and the Day 10
release decision. The two natural staging occurrences and independent Temporal
timer evidence remain pending.

---

## Day 1 final source-alignment follow-up — 10 November 2026 (Asia/Dhaka)

After the source/UI ownership map identified an unsupported upload-picker claim, a React regression was committed first (`a8e7a37c6c86892976c7a67ffc4091297e8d308b`). GitHub frontend CI reproduced the precise RED: **240 passed, 1 failed**, actual picker `.txt,.docx,.pdf,.csv,.xlsx,.pptx` versus accepted `.txt,.docx,.pdf`. The subsequent code correction narrows the picker and hint without extending the upload client's formats, security boundaries, or the backend. **Exact corrected-head CI pending** at this source checkpoint.

Render's original Free staging PostgreSQL 18 remains expired and billing-suspended; the calculated 14-day retention risk is **14 Nov 2026 17:11:33 UTC** under Render's current policy, with recoverability and private backup unverified. Owner recovery decision, independently enforced protected-main review, and D custody remain external blockers. GitHub issues #291 and #484 contain fresh owner runbook updates. Production API auto-deploy remains disabled; no paid resource, model inference, migration, external send, merge or production activation was performed.

---

## Day 1 baseline continuation — 10 November 2026 (Asia/Dhaka)

Continue draft PR #664 from `5816cdbbce340b8bd286ec8ea7ab9a57e3e9e735`, main `1f6dae72e1de6f38ec4d9cf60180d856dbecb403`. Two CI failures reproduced independently; corrected the invalid provider test input and replaced sandbox string-membership with exact mount assertions. No production validator or sandbox boundary relaxed. Focused requested check: **4 passed, zero skips**, mandatory JUnit module gates pass. API and worker staging definitions now pin the existing bounded DeepSeek/model/provider/run policy; both environments load and validate with execution gates disabled. [Task, evidence, ceilings and blockers](DAY1_BASELINE_2026-11-10.md).

**Source verification:** 162 Coworker/sandbox/Fly tests, 39 evaluator/quality tests, 240 shared frontend tests plus 7 shell tests pass; web-editor build passes. Independent source-review findings fixed with eight RED→GREEN regression instances. 80 frozen scenarios prepared; 40/40 handcrafted development calibration is not model-quality evidence. CI now fetches source history for provenance; final-head CI pending. Production API Auto-Deploy changed to Off, independently confirmed by Render API at 2026-11-10T10:55:49.522248Z. Native main ruleset is populated; save awaits the owner’s GitHub account verification. [Operations](DAY1_OPERATIONS_2026-11-10.md), [evaluation](DAY1_EVALUATION_2026-11-10.md), [UI ownership](DAY1_UI_OWNERSHIP_2026-11-10.md).

**Immediate blockers/owners:** C/Render owner: expired billing-suspended PG18, no verified backup/restore or authorized retention choice, no persistent worker. C/GitHub administrator: main ruleset save requires account verification; native denied/permitted controls unperformed. Production API auto-deploy is now off. D: no independent holdout custody. Broader source checks and review pending; no merge, deployment, activation, inference spend or production qualification. Complete independent work while these remain blocked.

---

## Approved Figma frontend implementation — 5 November 2026 (Asia/Dhaka)

PR [#635](https://github.com/rumman52/Shuddho/pull/635), implementation commit `816700f8e9fb88eb2382915d88e9759255e09cd7`. Branch `fix/rukh-figma-visual-parity-20261105`, base `065dedfe73a95ddd36d331336e11297d75aa25db`. [Implementation, root causes, requirement mapping, verification and release blockers](../frontend/FIGMA_IMPLEMENTATION_2026-11-05.md).

Implements the approved Coworker home/sidebar/mobile composer, owner-scoped Projects with additive migration 0064 (default off), real Files/Settings/Plugins surfaces, and a sandboxed website editor alongside the existing writing editor. Project/chat/editor links preserve context; saved status requires persistence verification. Local API/identity/model browser fixtures are explicitly identified as synthetic.

Combined backend checks: 108 passed, zero skips. Frontend tests and browser measurements are recorded in the linked handoff. No live database migration, production promotion, paid provisioning or provider qualification is claimed. Public sign-in config and matching backend/hosting access remain release blockers. Main, backend data, and release gates are preserved.

---

## Real authenticated chat integration — 4 November 2026

Base `9ebd961c238339051188b2a758ba5df54d10fa1e`; branch `fix/real-chat-provider-integration-20261104`. Replaced draft-only routing with the actual auth/chat app, fixed auth return routes, added explicit Gemma chat streaming alongside default DeepSeek, unified capability/admission with model-family policy, and retained partial UI output on stream connection errors. [Contract, evidence and concrete release dependencies](../frontend/REAL_CHAT_INTEGRATION_2026-11-04.md).

204 frontend tests and all three app builds pass; 92 backend conversation/provider-policy checks pass with zero skips. Review findings on model families and tool parts fixed with regressions; independent re-review approved with 16 focused passes; exact-head CI pending. Existing public auth settings configured for this preview branch only. Production chat mount returns 404; its install omits Coworker extras; production browser auth is absent; old Render staging DB is suspended and Supabase has no application tables. Source integration is implemented/repository-tested; no real provider run, deployed authenticated chat, production qualification or external-action activation claimed. Next: supply/confirm durable server DSN and private storage through hosting secrets, install extras/migrate, qualify matching release and enable only authorized conversation/reply capability.

---

## Coworker entry recovery — 4 November 2026

Base main `dce675364ce98b16309731e743ce7b8357eef4e6`; branch `fix/rukh-coworker-entry-recovery-20261104`. Live `/coworker` returns the landing page because the deployed frontend manifest has `coworker_enabled: false`, despite current frontend/backend revisions. Repaired disabled navigation with an explicit draft-only workspace, keeping API/auth/execution gates closed. [Contract, requirement matrix, verification and next actions](../frontend/ENTRY_RECOVERY_2026-11-04.md).

Web Editor suite: 204 passed, zero skips; all three frontend builds pass, existing Coworker chunk warning retained. Independent reviewer found no Critical/Important issues; Minor draft-overwrite issue fixed. New-layout browser checks remain blocked by local Chromium download failure. Source implemented/unit-tested, exact-head CI pending; not deployed, live verified, production-qualified or activated. Real authenticated chat, provider/storage persistence, Editor handoff and full prompt completion remain unverified/incomplete.

---

## Browser-native Coworker voice controls — 4 November 2026 (Asia/Dhaka)

PR #625 was closed after its pull-request snapshot stopped following the updated branch ref; PR #626 is the current draft for the same branch and contains the full 18-commit change set.

PR #626 is the current open draft on `feat/rukh-coworker-voice-controls-20261104`. It adds optional browser-native dictation and read-aloud controls to the existing conversation workspace.

- Dictation requires an explicit microphone-button click, appends only final speech segments to the draft, supports device locale / Bangla / English selection, and never sends the message automatically.
- Read aloud uses the browser's installed `SpeechSynthesis`; Bangla-script responses request `bn-BD`. This is not generated AI audio or a real-time voice conversation.
- Audio is not uploaded, persisted, or logged. No provider, backend, schema, feature flag, approval, or production configuration changed.
- TDD evidence: the test-only commit `a980a09aea31700776f64d59cc603c98ada6b054` produced the expected RED result in [CI run #41809748139](https://github.com/rumman52/Shuddho/actions/runs/41809748139): the new speech-helper and reply-control tests failed before implementation.
- GREEN evidence: the frontend test/build job passed on predecessor implementation commit `3f5fef0ecf27b997d7035661844b131606671086` in [CI run #41810362794](https://github.com/rumman52/Shuddho/actions/runs/41810362794). The latest source commit adds Bangla TTS locale detection and mobile select sizing; exact-head CI is still pending.
- Vercel reported the earlier preview deployment ready, then refused subsequent deployments because the free daily deployment limit was exceeded (>100). The connected Vercel API still cannot inspect the project. The Render staging Postgres database is suspended after its 31 October expiry. No current live preview, staging, or production verification is claimed.

**Next:** verify exact-head CI for PR #626, obtain a fresh preview after the Vercel limit resets, and test microphone/TTS behavior on supported desktop and Android browsers. Remaining Muse gaps are token streaming, image capabilities, direct file-aware chat, provider-generated audio/real-time voice, and native integrations.

---

## Muse-inspired conversation enhancements — 4 November 2026 (Asia/Dhaka)

The approved practical chat enhancement slice is merged to main. Current source: `4db2843e0d43447af5065b04c13b82cf710a1084` (merge of PR #622). The merged implementation chain is #616 (native text replies), #617 (rename/export/Markdown/attachments), #618 (Unicode and attachment-test corrections), #620 (Coworker-first routing) and #622 (server-side five-source limit and final route/browser regressions). See [the feature handoff](../frontend/MUSE_CHAT_ENHANCEMENTS_2026-11-04.md) and [frontend ledger](../frontend/IMPLEMENTATION_LEDGER.md).

- User-visible scope: Coworker-first conversation UI, persisted owner-scoped text replies, rename with optimistic concurrency, Markdown/JSON export, safe Markdown rendering, and owner-scoped untrusted file/artifact attachments limited to five.
- Safety: saved messages and renames do not dispatch Agent work; direct chat does not read attached file contents; explicit Start task remains required for Agent processing. Native replies remain default-off.
- Latest main CI #41800917260: `test-and-build=success`, `Frontend tests and builds=success`, `coworker=failure` at the final browser step due to a stale `.workspace-coworker` selector after the Coworker standalone route change, and `governance-audit=failure` because main branch protection is not confirmed. PR #624 corrects the browser scroll target; exact-head rerun pending. Vercel commit status is success, not live UI qualification.
- Qualification levels: scoped source merged; repository verification partial until the Coworker job completes; staging not freshly verified; production not qualified; activation not performed.
- Handoff regression coverage now explicitly checks Bangla/long-Unicode Markdown preservation and narrow-panel code/table overflow; exact-head PR CI is pending.
- Remaining Muse gaps: streaming, voice/audio, image capabilities, direct file-aware chat, native mobile/WhatsApp integrations, and operated qualification of the wider Agent/automation/transaction surfaces.
- Next: inspect exact-head Coworker CI and this handoff PR's checks. Do not merge or deploy this documentation handoff as a substitute for governance or staging gates.

---

## Native chatbox continuation — 4 November 2026 (Asia/Dhaka)

The native assistant text-chat implementation is merged through PR #616 (merge commit `7b20c1c34217fdfe8ac7952fa6b8c40b5dc611c5`) and remains default-off. [Implementation, evidence and rollout handoff](../frontend/CHATBOX_COMPLETION_2026-11-04.md) records the backend contract; the follow-on Muse chat implementation and current qualification status are recorded in the new section above.

- Backend conversation/context/dispatch/retention/manifest suite: **92 passed, zero skips**, mandatory gate passed. The final reply-only rerun and independent reviewer run each passed **21 tests**.
- Full root JavaScript suite passes, including **169 web-editor tests**; web-editor, Coworker and Editor builds pass. Existing Coworker bundle-size warning remains.
- Real Chromium with a synthetic API passes five desktop/tablet/phone viewports, including first-entry and after-reply composer visibility, send/reply, scroll, history search, drawer keyboard focus, new chat and dark mode.
- Source review found and verified a fix for active/expired provider leases breaking account erasure. No remaining Critical/Important finding was reported.
- PR #616 is merged. No production migration, deployment, real provider call or feature activation is claimed. Native text chat is implemented in source but remains default-off; streaming and full Muse parity remain incomplete.

---

## Frontend conversation continuation — 4 November 2026 (Asia/Dhaka)

Base main `a8385b5a2849afd01486d86106cfa4ea491f46fd` includes merged #615. Branch `feat/rukh-conversation-usability-20261104` completes the first-entry composer, first-message conversation creation with retry identity, history search, prompt starters, IME-safe keyboard submission and inline real linked-run progress. [Task contract and capability matrix](../frontend/CONVERSATION_USABILITY_2026-11-04.md); [current frontend ledger](../frontend/IMPLEMENTATION_LEDGER.md).

- Local full root `npm test` passes, including **167 web-editor tests, zero skips**, standalone Coworker **4** and Editor **1**, gateway/shared/NLP and production-API checks. All three frontend TypeScript/Vite builds pass; the existing Coworker chunk-size warning remains.
- Browser qualification blocked locally: no Chromium executable and browser download returned invalid/truncated data. No mobile/desktop screenshots or real auth/provider scenario claimed.
- Fresh base-main frontend CI passed. Both Python jobs failed the existing multilingual quality fixture (0.8333 versus required 1.0); governance and merge gate failed. Base Vercel commit status reports success, which does not verify the live UI.
- Agent review found Unicode title splitting and historical-run request fan-out; both were reproduced and fixed with regressions. Continuation-head remote CI and human review pending at this source checkpoint. Source work is implemented and locally verified; staging/live deployment unverified; full production qualification incomplete; no activation, merge, paid provisioning or production deployment change.
- Next: inspect continuation PR exact-head frontend CI, review and browser evidence; implement native assistant conversation messages/streaming as a separate backend contract. Existing automations/connectors/VM/transaction surfaces do not establish full Muse parity or operated capability acceptance.

---

## Current continuation — 31 October 2026: live release-readiness and staging continuity

This is the latest Shuddho handoff and supersedes older operational claims below. Read [RELEASE_READINESS_REFRESH_2026-10-31.md](RELEASE_READINESS_REFRESH_2026-10-31.md) for exact evidence and owner actions.

- Current main: 38c5b8d0d3eafa5692f848a5e664897a500fcfe2. PR #596 and #597 are merged; no open PRs were returned.
- Exact-main CI #41098651428: test-and-build and coworker passed; governance-audit and ci-merge-gate failed. GitHub main reports protected=false and no active rulesets.
- Render Free staging PostgreSQL 18 expires 31 October at 23:11:33 Asia/Dhaka. It has no backups/PITR; external SQL is blocked by the empty IP allowlist, so its data inventory is unknown. No database or network changes were made.
- Staging API remains on 2 October source and no persistent worker exists. Production is live on current main but starts in degraded local analysis mode with detector/corrector disabled; health-check path is blank.
- Supabase is healthy but has no public tables/migrations; PostHog has ingested no events; Vercel deployment verification is denied; Linear and ProductOS expose no Shuddho project.
- Transaction regression steps passed in the coworker CI job, but real provider-side receipts, mutation counts, frozen staging identity and rollback drills remain unverified. All 17 A/C/P/V acceptance rows remain not fully qualified.
- Current evidence comments were added to #291, #339, #378, #484, #583 and #584. No source, database, network, service, billing, secret, branch-rule, production, provider or telemetry setting changed.

**Next priority:** owner-authorized staging database preservation before expiry, followed by native GitHub governance and the missing persistent worker. No production activation is authorized.

---

## Current continuation — 29 October 2026: PR #593 conflict resolution and review fixes

This checkpoint supersedes the pending-source claims below. Main at inspection is
`93ff94f0e60723652d2a1b523bf91198ebe3bd74` (merged #595). Existing draft
[#593](https://github.com/rumman52/Shuddho/pull/593) remains the bounded release-freeze
hardening workstream; no replacement PR or main merge is required for this continuation.

- **Task contract:** reconcile #593 with current main, preserve both progress histories
  and #595's prerequisite checks, then verify strict staging identity, manifest types,
  cohort enforcement and credential destination validation. No schema, capability,
  deployment, provider registration or authority change.
- **Review fixes:** alternative numeric IPv4 spellings (`127.1`, octal and hexadecimal
  components) are rejected by both HTTPS validators. Verification independently requires
  enforced synthetic cohorts and an exact integer limit in 1..25, including saved states
  produced by the earlier permissive prepare command.
- **Observed regressions:** #593's original regression file against main's original
  freeze module: 32 failed / 19 passed. Added numeric-address cases before the fix:
  12 failed / 6 passed. Added legacy-cohort cases before the fix: 4 failed / 1 passed.
  These are local, network-free reproductions, not operated staging evidence.
- **Final local validation:** release-freeze, prerequisite, endpoint, release-contract
  and `test_pa10_*.py` suites: **229 passed, zero skips**. Full lightweight `pytest -q`:
  **1713 passed, 72 collection skips, six Pydantic serialization warnings**. Optional
  coworker dependencies/services are absent from that lightweight environment; its skips
  do not qualify the mandatory PostgreSQL/Temporal/browser suites. Release contract,
  Python compilation and `git diff --check` passed. Dependency manifests match main.
- **Code review:** a separate read-only agent reproduced two Important findings above;
  both were fixed test-first. Re-review found no remaining scoped findings and independently
  checked numeric origins, valid DNS controls, legacy states and a valid frozen result.
  This is agent code review, **not independent human approval**.
- **Current main CI:** [#40765226807](https://github.com/rumman52/Shuddho/actions/runs/40765226807)
  had `test-and-build=success`, `governance-audit=failure`, `coworker=in_progress` at
  inspection. Native main protection remains false and rulesets empty. New PR-head CI
  must be inspected after publication; no final-head remote success is claimed here.
- **External disposition:** Supabase staging is healthy; PostHog project 675660 still
  reports no ingested events; Linear has no Shuddho issues and ProductOS no project.
  Vercel deployment listing returns 403, with no authenticated CLI available. Render
  workspace selection received no answer, so no fresh service/database check occurred.
  The last-reported database expiry remains **31 October 2026, 23:11:33 Asia/Dhaka**;
  a restorable backup and retention decision remain unverified.
- **Next:** inspect final #593 code CI, obtain independent human approval and resolve
  native governance [#484](https://github.com/rumman52/Shuddho/issues/484); the Render
  owner selects `Rumman`, secures database continuity and completes staging worker/
  Temporal/S3 prerequisites [#291](https://github.com/rumman52/Shuddho/issues/291).
  API readiness #583, privacy/telemetry #584 and operated provider/recovery acceptance
  remain open. All 17 architecture/core acceptance rows remain not fully qualified.

**Levels:** implemented and locally verified; final PR-head CI pending; staging blocked;
production qualification incomplete; activation not authorized. Keep this PR draft.

---

## Review-only source fix — 29 October 2026: staging prerequisite HTTPS preflight

- Starting `main`: `141d1f0f16655dcb4037cb32fafbae374aab42e1`. The final main CI [#40750231571](https://github.com/rumman52/Shuddho/actions/runs/40750231571) reports `test-and-build=success`, `coworker=success`, `governance-audit=failure` and `ci-merge-gate=failure`; `main.protected=false` and active rulesets are empty. **Not release qualified.**
- This draft branch `fix/pa10-preflight-https-raw-host-20261029` fixes a distinct `staging_prerequisite_preflight.py` HTTPS URL-shape gap (CR/LF/TAB stripping and local/IP destination admission), separate from draft [#593](https://github.com/rumman52/Shuddho/pull/593). See [task contract](PA10_PREFLIGHT_ENDPOINT_SECURITY_2026-10-29.md).
- Local isolated TDD reproduction: 28 rejected cases incorrectly passed before; after change 36 parameterized tests passed with zero skips, and `compileall` passed. The isolated mirror is not a full repo test run. **Repository CI, independent review, merge and staging verification pending.**
- Read-only live Render audit: `shuddho-staging-db` available, free tier, expiration `2026-10-31T17:11:33.79468Z`; no verified restore artifact; external SQL denied by current empty allowlist. Staging worker absent; staging API on 2 October SHA, config differs from reviewed Blueprint. Production `shuddho-api` auto-deploys unqualified main and reports degraded detector/corrector. Posted verified owner handoffs to [#291](https://github.com/rumman52/Shuddho/issues/291) and [#484](https://github.com/rumman52/Shuddho/issues/484).
- **Evidence levels:** source proposed; repo verification pending; staging blocked; production qualification incomplete; activation prohibited. No paid provisioning, database/network writes, secret access, provider calls, merges or production changes.
- **Next:** exact PR-head CI + independent review; owner to protect/restore-test staging DB before expiry and enforce native branch + promotion controls.

---

## Core Agent evidence ledger — 28 October 2026 (Asia/Dhaka)

- **New source of truth for P0/P1 disposition:** [CORE_AGENT_COMPLETION_LEDGER.md](CORE_AGENT_COMPLETION_LEDGER.md), drafted from main `ec4276d982d4efe89743f09afca0db762be3f05b`. Exact-main [CI #40736158784](https://github.com/rumman52/Shuddho/actions/runs/40736158784): code jobs `test-and-build` and `coworker` passed; `governance-audit` and `ci-merge-gate` failed. Main `protected=false`, GitHub rulesets list `[]`, PR #589 has zero submitted reviews. This is **not** release-qualified.
- **Owner blockers:** [#484](https://github.com/rumman52/Shuddho/issues/484) main governance; [#291](https://github.com/rumman52/Shuddho/issues/291) persistent worker/Temporal/S3, and the **last-reported** staging database expiry 31 Oct 2026 at 23:11:33 Dhaka; [#583](https://github.com/rumman52/Shuddho/issues/583) production API readiness; [#584](https://github.com/rumman52/Shuddho/issues/584) telemetry/privacy approval. Render workspace confirmation and Vercel deployment-access blockers prevent current operated validation. No production activation, paid provisioning or privileged mutation performed.
- **This change:** documentation-only review branch; check draft PR final-head checks and obtain independent review before considering merge. No tests were executed locally for this documentation update.

---

## PA-10 staging-freeze contract checkpoint — 29 October 2026 (Asia/Dhaka)

- **Source branch:** [draft PR #593](https://github.com/rumman52/Shuddho/pull/593) replaces unmerged closed #591; this is P0-04 release-freeze source hardening, **not** staging or production qualification. Code changes in `scripts/staging_release_freeze.py` and `tests/test_staging_release_freeze.py` harden exact typing and environment/cohort checks, reject local/private/malformed bearer-token destinations, refuse silently normalized control-character origins, and turn off inherited HTTPX proxy/CA configuration.
- **Reproduction and tests:** regression cases were committed before their implementation. Local Python confirmed the old `urlparse` behavior (CR/LF/TAB stripped) and HTTPX default `trust_env=True`; isolated predicate/Client controls behaved as expected after the edit. **A full test run on this exact final PR head has NOT been observed**; no GitHub Actions run, independent approval or staging proof is claimed.
- **CI caveat:** earlier source commit `284fa406` [CI #40744752467](https://github.com/rumman52/Shuddho/actions/runs/40744752467) passed `test-and-build` and `coworker`, but **failed** `ci-merge-gate` without independent review. That is not final-head clearance.
- **Governance:** source-main baseline in this checkpoint `9c4f3ebec90e00c53248c7125968c5b95a4e335c`, protected=false; PR #592 merged without independent review and with failed merge gate. [V-01 issue #484](https://github.com/rumman52/Shuddho/issues/484) requires admin-enforced native protection and promotion rules. Vercel confirms frontend production READY for this docs-only main merge, which is not an API/agent acceptance result.
- **External risks:** [#291](https://github.com/rumman52/Shuddho/issues/291) requires a genuinely restorable Render staging database backup and approved retention before the last-recorded **31 October 2026** free-database expiration, a persistent worker, approved cost and credentials, then exact API/worker revision matching. Render workspace is not user-confirmed and no live staging check or change was performed.
- **Evidence status:** source-only patch **PENDING exact-head CI**, staging **NOT VERIFIED**, human review **NONE**, Core Agent production release **NOT QUALIFIED**, activation **NOT AUTHORIZED**.

---

## Active review-only continuation — 28 October 2026 (Asia/Dhaka)

- **Refreshed source:** current `main` at audit is `bfcf85c1e1990093520ca4b03551424524b9b3d2`, merge of [PR #588](https://github.com/rumman52/Shuddho/pull/588). Exact-head [CI #40556423509](https://github.com/rumman52/Shuddho/actions/runs/40556423509) completed: `test-and-build=success`, `coworker=success`, `governance-audit=failure`, `ci-merge-gate=failure`. Native `main` reports `protected=false`; rulesets list returned `[]`. The two successful code jobs are not independent approval or release clearance.
- **New bounded implementation:** review branch `fix/api-smoke-analysis-profile-guard-20261028` makes the optional strict read-only API smoke gate require a reported `full_local` analysis profile and zero degraded reasons, rejecting missing/unknown profiles. No production endpoint or source configuration was changed. Regression tests and task contract: [API_SMOKE_ANALYSIS_PROFILE_GUARD_2026-10-28.md](API_SMOKE_ANALYSIS_PROFILE_GUARD_2026-10-28.md). The branch requires exact-final-head CI and independent review before merge; PR is draft until verified.
- **External blockers unchanged:** [V-01 #484](https://github.com/rumman52/Shuddho/issues/484) requires admin-enforced review/CI controls; [PA-10 #291](https://github.com/rumman52/Shuddho/issues/291) requires Render staging worker, protected secrets and database continuity before the last-reported 31 October 2026 expiry; [API #583](https://github.com/rumman52/Shuddho/issues/583) requires a production readiness policy and live smoke evidence; [PostHog #584](https://github.com/rumman52/Shuddho/issues/584) requires telemetry/privacy approval. Vercel deployment inspection returned 403 and no live API HTTP check was verified in this continuation.
- **Evidence levels:** proposed source change only; new final-head CI/review PENDING, staging proof NOT PERFORMED, production qualification INCOMPLETE, activation NOT AUTHORIZED. A passing smoke test does not close release gates.

---

## Current release-readiness handoff — 27 October 2026 (Asia/Dhaka)

This section supersedes earlier pending-source and deployment statements below. Current main is `f26425ca799e3a666082fcb40ff45d89c99de467`, merged from PR [#585](https://github.com/rumman52/Shuddho/pull/585) at 15:56:33 UTC. PR #585 has zero submitted reviews; do not treat its merge as independent review or release approval.

| Evidence level | Current verified result |
| --- | --- |
| Current main and exact-head CI | [Run #40535969404](https://github.com/rumman52/Shuddho/actions/runs/40535969404): `test-and-build=success`, `coworker=success`, `governance-audit=skipped`, `ci-merge-gate=failure`. The failing step is `Require independent current-head review`; its error is “Pull request is not an open non-draft revision.” The PR had already merged before the gate completed. |
| Release governance / production promotion | Render confirms production `shuddho-api` is live on `f26425ca799e3a666082fcb40ff45d89c99de467`, deploy `dep-dbgcjcqjnfac739vopbg`, completed 15:58:12 UTC. Service config remains `autoDeploy=yes` on `main`. Production deployed before mandatory review/merge-gate completion. V-01 [#484](https://github.com/rumman52/Shuddho/issues/484) is **BLOCKED**; the current connector cannot apply/read back native GitHub rulesets or update Render auto-deploy settings. |
| Application and agent test evidence | The completed coworker job reports success for PA-10 admission/recovery, transaction safety and PostgreSQL fault-boundary tests, Temporal recovery, connected-read authorization, trusted skill registry, bounded agent routing, multilingual route equivalence, long-horizon workflows, and browser/proxy checks. These are test results, not operated staging/provider qualification. |
| Production API health | Live service config still has an empty `healthCheckPath`. Recent Render request logs and metrics returned no rows/samples; direct public HTTP probing was unavailable through the connected fetch path. Therefore no successful live `/health`, `/version`, or analysis smoke test is claimed. Detector/corrector intent and production readiness semantics remain unresolved in [#583](https://github.com/rumman52/Shuddho/issues/583). |
| Staging API and worker | `shuddho-api-staging` remains on 2 October SHA `fce72760456bd8bb03524ce98127120c7ac3dfb9`; auto-deploy is off, build/start commands differ from the reviewed Blueprint, and live `healthCheckPath` is empty while `infra/render.staging.yaml` declares `/health`. No `shuddho-worker-staging` service is present. PA-10 [#291](https://github.com/rumman52/Shuddho/issues/291) remains **INCOMPLETE**. |
| Staging database retention | Render reports `shuddho-staging-db` (`dpg-dav98hfpn0mc739mndvg-a`) available on the free plan, with expiry `2026-10-31T17:11:33.79468Z` (**31 October 2026, 23:11:33 Asia/Dhaka**). External IP allowlist is empty. No backup/export, retention decision, upgrade, or migration is verified. Do not infer the database is empty from the unavailable read-only connection. |
| Supabase | `shuddho-staging` is `ACTIVE_HEALTHY`; security and performance advisors returned no lints. The connected project reports no migrations and no public-schema tables. This does not prove live auth, private S3, Temporal, or owner-isolation behavior. |
| PostHog | Project `675660` (`Default project`) reports `ingested_event=false` and onboarding incomplete. No events were sent. Telemetry implementation remains blocked on explicit approval of event scope, retention, region, privacy disclosure, and kill-switch semantics; see [#584](https://github.com/rumman52/Shuddho/issues/584). |
| Other project integrations | ProductOS has no projects in the connected organization; Linear search returns no Shuddho issues; the current Vercel deployment lookup did not resolve a deployment. Do not infer frontend release health from these connector results. |
| Staging / production qualification / activation | **Incomplete / incomplete / not authorized.** All 17 A/C/P/V acceptance rows remain not fully qualified. Passing source tests does not close operated evidence, independent review, or release authorization. |

### Remaining dependency queue

1. **Repository owner/admin — V-01:** apply/read back native main protection and require `ci-merge-gate` plus independent current-head review. Witness merge denial while CI is pending, failing, draft, or unreviewed, and a positive reviewed/green control. Do not soften the failing gate to hide a premature merge.
2. **Render owner — promotion and database continuity:** use the approved dashboard to disable unqualified production auto-promotion, verify a restorable database backup/export, and choose an approved retain/upgrade/migrate path before the expiry above. The connected Render tools do not expose these writes.
3. **Staging operator — PA-10:** after governance and retention are resolved, configure protected `pa10-staging` secrets and the approved persistent worker; reconcile the staging API/worker to the reviewed Blueprint; verify migrations, Temporal polling, private S3 round-trip, and synthetic-owner isolation on the exact frozen SHA.
4. **Production API owner:** decide whether detector/corrector being disabled is intentional, define liveness versus readiness, reconcile the health-check setting, and attach redacted live endpoint and safe-analysis smoke evidence.
5. **Privacy/product owner — PostHog:** approve or reject the proposed telemetry scope and privacy/retention controls before any instrumentation or event transmission.
6. **Provider/release owner:** complete the transaction provider sandbox, independent mutation counts, reconciliation, rollback/kill-switch, realistic multilingual quality, cost/latency, SLO, and reviewer-attested frozen evidence. Keep transaction and other high-authority capabilities disabled until their applicable gates and explicit authorization pass.

**Handoff:** the latest code CI is green, but the review/merge gate is not; production auto-deploy has already promoted the unqualified merge. No production settings, secrets, paid resources, database access controls, capability flags, or provider mutations were changed in this continuation.
---

## Latest continuation — 27 October 2026: database-expiry admission gate

- **Post-merge governance incident:** PR [#581](https://github.com/rumman52/Shuddho/pull/581) merged at 11:17:01 UTC as `e5cd2a9b9c7537f3066f6c3d5f3db534f235ab8a` with zero submitted reviews. Its observed exact-head `test-and-build` passed, `coworker` was cancelled, and `ci-merge-gate` failed; the merge nevertheless occurred because native main protection is disabled. Current main CI [#40494973875](https://github.com/rumman52/Shuddho/actions/runs/40494973875) has `governance-audit=failure`; application/coworker results were still pending at last inspection.
- **Confirmed production consequence:** Render `shuddho-api` is configured `autoDeploy=yes`, `autoDeployTrigger=commit`. Render events show production deployment `dep-dbg8gbs9v7es73e5r88g` of the same unqualified main SHA started 11:17:03 UTC and finished `succeeded/live` at 11:18:42 UTC. V-01 [#484](https://github.com/rumman52/Shuddho/issues/484) was updated with direct evidence and owner action to disable auto-deploy until native governance/promotion controls are enforced. The available Render connector cannot modify this service setting.
- **Time-sensitive database gate proposal:** Render reports `shuddho-staging-db` free-plan expiry at `2026-10-31T17:11:33.79468Z` (23:11:33 Asia/Dhaka). Direct read-only SQL via the connected Render tool is blocked by the empty database IP allowlist; this does not imply the database is empty. Branch `fix/pa10-staging-db-expiry-admission-gate-20261027` adds `scripts/pa10_database_expiry_gate.py`, unit tests, and workflow/static-contract checks to fail closed when expiry is unknown or within seven days. Workflows first query non-sensitive lifecycle metadata, then fetch the private connection string only after the gate passes; unknown plan identifiers and custom plans without expiry metadata also fail closed. It neither backs up nor upgrades the DB. PA-10 [#291](https://github.com/rumman52/Shuddho/issues/291) was updated with the deadline and required owner decision.
- **Do not merge as a substitute for governance:** This is a bounded fail-closed guard, not the needed backup/retention decision, and current `main` is still not release-qualified. Require independent review and green exact-head CI, then native no-bypass branch policy and witnessed negative/positive merge controls before merging. No paid plan, allowlist, worker, provider credential, or production setting was changed.

---

## Latest continuation — 27 October 2026: post-approval main-head revalidation

- **Verified baseline:** [PR #580](https://github.com/rumman52/Shuddho/pull/580) merged 10:53:44 UTC without independent submitted review. Main at `e8c465ad1a84419cfbd360be7c4d7d2078339b44`; `protected=false`, required checks off, rulesets `[]`. PR-head `test-and-build=success` while coworker still in progress at last inspection. New-main CI #40492004572 pending/in progress, not production qualified.
- **New bounded proposal:** branch `fix/pa10-main-head-revalidation-before-provider-20261027` adds `scripts/pa10_main_head_guard.py`, unit negative tests, workflow-order regression tests and a read-only current-main recheck **after** protected staging environment approval, before Render access, before worker mutation, and before worker deployment. Keeps no-secret pre-admission gate from #580. [Implementation contract](PA10_MAIN_ADVANCE_REVALIDATION_2026-10-27.md).
- **External status:** Supabase `shuddho-staging` reported `ACTIVE_HEALTHY`, security advisor 0 lints, zero public tables; this is not functional provider qualification. Vercel project `shuddho-web-editor` returned `READY` production-target deployment, which is not release authorization or runtime smoke-test evidence. Linear/ProductOS had no Shuddho project tracked in connected accounts. The PA-10 Render database expiry risk (31 October 2026) still needs owner action. No production settings, paid compute, secrets, or provider resources changed.
- **Controls:** source-level checks cannot enforce GitHub's merge UI. Owner/admin must apply and negative-test V-01 [issue #484](https://github.com/rumman52/Shuddho/issues/484), protect staging environment, authorize paid compute and database continuity [PA-10 #291](https://github.com/rumman52/Shuddho/issues/291), verify exact-release provider isolation, and gate production deployment. Do not merge unreviewed or incomplete-CI changes. **Overall production qualification INCOMPLETE**.

---

## Source/secret boundary follow-up — 27 October 2026 (Asia/Dhaka)

- **Main baseline:** `c54e745a25029f61d468a14369747fda502e3e58`, merge of [PR #579](https://github.com/rumman52/Shuddho/pull/579) at 10:39:03 UTC. Independent submitted reviews for #579: `[]`. Native `main` reported `protected=false`; rulesets `[]`. Its new-main CI [#40490125092](https://github.com/rumman52/Shuddho/actions/runs/40490125092) observed `governance-audit=failure` while code/coworker jobs were in progress. No production qualification inferred.
- **New bounded follow-up:** the PA-10 read-only preflight and manual paid-worker provisioning previously declared `PA10_*` secrets in the same job that checked source qualification. On branch `fix/pa10-unprivileged-source-gate-before-secrets-20261027`, both now require a separate no-secrets `source_gate` to succeed before the protected-environment job is eligible to start. `source_gate` only has GitHub `contents: read` and `actions: read`; checkout credential persistence disabled. Mock-free static checks on fetched branch contents verified both jobs, explicit `needs` and exact-SHA guard; new unit regression contract is under `tests/test_pa10_secret_boundary.py`.
- **Qualification and blockers:** source-code change is proposed but not merged at this checkpoint. Full final-head application/coworker CI, independent approval, native V-01 branch-protection enforcement with negative merge controls, protected `pa10-staging` environment review, live S3/Temporal/Auth/provisioning and production deploy gating remain pending. [V-01 #484](https://github.com/rumman52/Shuddho/issues/484); [PA-10 #291](https://github.com/rumman52/Shuddho/issues/291). No paid resources, credentials, production environment, secrets, provider traffic, live staging worker or feature flags changed.
- **Entry points:** [PA10_PRE_SECRET_ADMISSION_BOUNDARY_2026-10-27.md](PA10_PRE_SECRET_ADMISSION_BOUNDARY_2026-10-27.md), `.github/workflows/provision-pa10-staging-worker.yml`, `.github/workflows/pa10-staging-prerequisite-preflight.yml`, `scripts/pa10_source_gate.py`. Stage qualification and activation **INCOMPLETE**.

---

## Latest source-safety checkpoint — 27 October 2026 (Asia/Dhaka)

- **Refreshed main:** `46f4f691db8aaa72431729dd53e0a74a72ff43c5`, merger of [PR #578](https://github.com/rumman52/Shuddho/pull/578). Submitted PR reviews: **zero**. New-main [CI #40468460697](https://github.com/rumman52/Shuddho/actions/runs/40468460697) completed: `test-and-build=success`, `coworker=success`, `governance-audit=failure`, `ci-merge-gate=failure`. Direct branch read reports `protected=false` and required-check enforcement off; active rulesets returned `[]`. V-01 remains a release blocker.
- **Bounded pending source defense:** branch `fix/pa10-exact-main-ci-provision-gate-20261027` introduces `scripts/pa10_source_gate.py` plus mocked tests and a pre-Render source gate in the manually dispatched staging-worker workflow. The gate requires candidate native protection, the exact current main SHA, a completed successful main-push CI run, and uniquely passing four required jobs before provisioning can proceed. [Task contract](PA10_EXACT_MAIN_CI_SOURCE_GATE_2026-10-27.md). Local isolated tests: eight passed with mocked external calls and a local import shim; full remote CI, independent review, native negative controls, and live staging evidence remain pending. **Do not merge without these conditions.**
- **Other checked systems:** `shuddho-staging` Supabase project currently reports `ACTIVE_HEALTHY`; Vercel `shuddho-web-editor` has a READY production-target deployment at the latest main SHA. Neither proves provider paths, end-user health, or approved release. No paid resources, deployment configuration, credentials, provider permissions, feature flags, or production settings were changed in this slice.
- **Required owner/operator work:** effective GitHub non-bypassable ruleset + negative/positive merge proof ([#484](https://github.com/rumman52/Shuddho/issues/484)); verify the protected staging environment, paid worker approval and credentials, and staging DB continuity before the 31 October expiry ([#291](https://github.com/rumman52/Shuddho/issues/291)); enforce fail-closed production promotion, then gather exact-release Temporal, private S3, auth isolation, transaction, quality and recovery evidence. Overall production qualification and activation remain **INCOMPLETE**.

---

## Current verified release handoff — 26 October 2026 (Asia/Dhaka, latest)

- **Source baseline:** `main` `87d54dcbd1dcc899b247aef1908ff6cc85047847` (merger of [PR #577](https://github.com/rumman52/Shuddho/pull/577)); [PR #576](https://github.com/rumman52/Shuddho/pull/576) also merged. Both PRs passed their application and coworker test suites but had **failing merge gates**. Native `main` reports `protected=false`; no active rulesets were observed. [Current-main CI run #40373045502](https://github.com/rumman52/Shuddho/actions/runs/40373045502) had governance-audit=**failure**, test-and-build=success, coworker=running at this checkpoint. Do not treat merges, tests or successful deployments as release qualification.
- **Current bounded safety patch:** [draft PR #578](https://github.com/rumman52/Shuddho/pull/578) / `fix/pa10-worker-predeploy-readback-20261026`. Test-first `70a5518`, implementation `860c6f5`: compare the independently read-back worker `serviceDetails.envSpecificDetails.preDeployCommand` against the approved migration command `uv run --extra coworker python -m services.coworker.migrate` **before** credentials or deployment. Modified or missing pre-deploy command fails. Contract: [PA10_PREDEPLOY_COMMAND_READBACK_2026-10-26.md](PA10_PREDEPLOY_COMMAND_READBACK_2026-10-26.md). Exact final-head CI and independent review **PENDING**. No paid resources, credentials or production flags were changed.
- **External release blockers:** Render production API `shuddho-api` still has auto-deploy on each main commit; staging API differs from the Blueprint and has no configured readiness path; **no persistent PA-10 staging worker** is connected. The free staging Render PostgreSQL instance expires **31 October 2026**. Supabase staging is `ACTIVE_HEALTHY`, not proof of Temporal/S3/auth provider operation. Vercel production target is `READY`, not runtime-health evidence. GitHub native admin merge protection, negative-control tests, secure staging secrets, paid worker approval, same-SHA provider qualification, PostHog ingestion and release authorization remain outstanding.
- **Required order:** GitHub owner applies effective native CI/review protection ([V-01 #484](https://github.com/rumman52/Shuddho/issues/484)) and verifies negative merge controls; Render owner disables unauthorized auto-promotion; operator addresses database expiry and reviewed staging credentials/compute ([PA-10 #291](https://github.com/rumman52/Shuddho/issues/291)); engineer freezes exact candidate and gathers real provider/transaction/reliability evidence. Capabilities stay default-OFF. **Overall production readiness: NOT VERIFIED**. No fake completion percentage assigned.

---

## Latest verified checkpoint — 26 October 2026 (Asia/Dhaka, evening)

- **Main is unchanged:** `5f6365fe9290383b184a1b464bb9c360a1fa7669`, merger of [PR #575](https://github.com/rumman52/Shuddho/pull/575). Native `main` protection is **false**; required status checks are **off**; active rulesets list `[]`. [Merged-main CI #40329612005](https://github.com/rumman52/Shuddho/actions/runs/40329612005) ended with `test-and-build=success`, `coworker=success`, `governance-audit=failure`, and `ci-merge-gate=failure`. No independent PR #575 review was submitted. **V-01 #484 is BLOCKED**, not merely untested.
- **Existing [draft PR #576](https://github.com/rumman52/Shuddho/pull/576):** 120-second staging-worker shutdown readback; [CI #40338064970](https://github.com/rumman52/Shuddho/actions/runs/40338064970): `test-and-build=success`, `coworker=success`, `governance-audit=skipped` (PR event), `ci-merge-gate=failure`. No submitted independent review; leave draft/unmerged.
- **New [draft PR #577](https://github.com/rumman52/Shuddho/pull/577):** closes a distinct PA-10 *credential-sequencing defect* in the new-service creation path. The original command passed private DB URL, S3 access-key pair and Temporal API key to `render services create` **before** the independent config readback. Test-first `06ffe0e` records fake CLI arguments and rejects premature credentials; implementation `c069f75` removes all four from creation but keeps inert flags and all subsequent, post-readback reconciliation calls. [Bounded task contract](PA10_WORKER_CREATION_CREDENTIAL_BOUNDARY_2026-10-26.md) documents risk, exact test and rollback. Static main-vs-branch assertions show **4 unsafe create flags before / 0 after**, reviewed flags preserved, and reconciliation ordering unchanged. **Full final-head CI and human review pending; no staging/production qualification inferred.**
- **Render:** production API `shuddho-api` still uses `autoDeployTrigger=commit`, and commit `5f6365f` was deployed live as `dep-dbfl6qs9v7es73dk9pcg` despite merged-main governance failure. `shuddho-api-staging` is unaligned with the reviewed Blueprint; no `shuddho-worker-staging` persistent service exists in the connected workspace. The free `shuddho-staging-db` is scheduled to expire **31 October 2026**. No infrastructure, secrets, paid compute, production settings or capability flags were modified by this new branch.
- **Other environments:** Supabase staging `bsmbvjenpvcyfjzwtuax` reports `ACTIVE_HEALTHY`; no public application tables were returned at last inspection, and security advisor had no lints. Vercel project `shuddho-web-editor` reports READY deployments for the current main and review branches, **not** operated/user-facing health. PostHog `Default project` has `ingested_event=false`; Linear and ProductOS have no Shuddho project in the connected workspace. No provider-verified Temporal, S3, transaction or quality/SLO release evidence was established.
- **Closure order:** admin-enforced native required checks + review and negative merge controls; fail-closed production deployment gating; paid worker/credential/DB retention decision and API staging alignment; same-SHA Temporal/S3/auth tests, transaction provider qualification and telemetry; independent review and explicit bounded-pilot authorization. Until then, architecture/coworker/transactions are **implemented in part, not fully staging-verified or production-qualified**. Avoid fabricated completion percentages.

---

## Current release-readiness delta — 26 October 2026 (Asia/Dhaka, 16:37)

- **Refreshed main:** `b36caab25d3e84ddb0426f6eff6603ad0785cbfa` (PR #574 merged). Its [merged-main CI #40269775174](https://github.com/rumman52/Shuddho/actions/runs/40269775174) completed with `test-and-build=success`, `coworker=success`, `governance-audit=failure`, and `ci-merge-gate=failure`. [PR #574](https://github.com/rumman52/Shuddho/pull/574) has zero submitted reviews. Do **not** treat its source tests or the Vercel READY deployment as production qualification.
- **Governance remains blocked:** the connected rulesets query returned `[]`, and main's native protection is not confirmed. The production Render API still has `autoDeployTrigger=commit` and live deployment `dep-dbfdgls9v7es73dbne3g` on `b36caab`, notwithstanding merged-main CI failure. Issue #484 requires administrator policy, an independent review gate and a negative-control merge test; nothing here can replace those controls.
- **PA-10 staging still blocked:** in the connected Render workspace, `shuddho-worker-staging` is absent; `shuddho-api-staging` remains deployed on October 2 source `fce72760456bd8bb03524ce98127120c7ac3dfb9` with non-Blueprint commands/health path. The free staging Postgres currently reports available but expires on **31 October 2026**. Supabase project `bsmbvjenpvcyfjzwtuax` reports ACTIVE_HEALTHY; security/performance advisors returned zero lints. Neither implies a working worker, Temporal polling, owner isolation or full PA-10 evidence.
- **Current review task:** [draft PR #575](https://github.com/rumman52/Shuddho/pull/575) adds a post-create/update, pre-secret-reconciliation read-back gate for exact worker identity, main branch, disabled auto-deploy, region, compute plan and build/start commands. Test-first commit `f0d5a4622043a9b1d75978a42a6c80c3128a3cf8`; implementation commit `28d34df25ddd2c36611fd441e3c18be22dd5a31b`. Five predicate cases were exercised locally with jq (one accepted configuration, four rejected drifts); **full repository CI, independent human review and merge are pending**. No paid provisioning, secrets, production flags or external provider effects were performed.
- **Vercel caution:** `shuddho-web-editor` reports a READY production-target deployment on `b36caab`, but the connected app returned 403 for protected-deployment access and runtime-errors inspection. User-facing frontend health is not verified.
- **Acceptance:** architecture/core, PA-10, transactions, V-01 governance and V-04 activation remain **NOT FULLY QUALIFIED**. Next: independently review #575 and require exact final-head checks; administer branch protection and production deployment safety; then securely establish and freeze the staging worker + API pair before provider/recovery/economics scenarios. The older handoff below is historical and must not be used as the current main/CI status.

---

## Current release-readiness handoff — 26 October 2026 (Asia/Dhaka; refreshed at 01:46)

- **Current main:** `79ab86a4e0ed8bfc549d26eb6db18cde8d3d1e88`, merge of [PR #572](https://github.com/rumman52/Shuddho/pull/572), which moves PA-10 credential references to the `pa10-staging` GitHub environment. [PR #571](https://github.com/rumman52/Shuddho/pull/571) also merged the aggregate Temporal replay-history size bound. No open pull requests were returned at refresh.
- **Current-main CI:** [run #40226555506](https://github.com/rumman52/Shuddho/actions/runs/40226555506) is still **in progress**. `test-and-build=success`; `governance-audit=failure` with `main branch protection is not confirmed`; `coworker` is still running at **Install document rendering libraries and fonts**. Do not label the run fully green or infer a final coworker result until it completes.
- **V-01 native governance:** the GitHub branches API currently returns `protected=false` for `main`, required-check enforcement off, and the connected rulesets query returns an empty list. The governance job fails for this actual configuration observation. The existing [ruleset operator](https://github.com/rumman52/Shuddho/blob/main/docs/coworker-roadmap/V01_SAFE_RULESET_APPLY_OPERATOR_2026-10-25.md) is already merged; do not duplicate it. The connected GitHub tools are read-only for ruleset writes, so an authorized repository administrator must inspect the effective policy, run the operator's dry-run, apply the reviewed template only after resolving conflicts and receiving authorization, read it back, then demonstrate red/pending/stale-review/missing-approval merges are blocked and a reviewed green PR is eligible. Configuration read-back alone is not behavioral proof. See [issue #484](https://github.com/rumman52/Shuddho/issues/484).
- **Production API / Render:** `shuddho-api` (`srv-d6oki2v5r7bs73e7isfg`) auto-deploys commits from `main`. The current live deployment is `dep-dbf5iqta647c73eobrjg`, built from this exact main SHA and reported live at 19:35:38 UTC on 25 October. HTTP request-count and latency metrics returned empty data for the inspected 24-hour window; no app error/fatal entries were returned for 18:45–19:45 UTC. Neither result proves endpoint health or useful traffic. The service has no configured HTTP health-check path, and the production deployment path is not gated on the repository's complete release qualification. No production settings were changed.
- **Controlled staging / Render:** only `shuddho-api-staging` is listed; no `shuddho-worker-staging` exists in the connected workspace. The API's current live deployment `dep-davmrnu7bikc73emahdg` uses source `fce72760456bd8bb03524ce98127120c7ac3dfb9` from 2 October. Its configured build/start commands differ from `infra/render.staging.yaml`, and its health-check path is empty. The Render Postgres instance `shuddho-staging-db` is available on the free plan with expiry **31 October 2026**. Do not create a cron or web-service substitute for the persistent worker. See [issue #291](https://github.com/rumman52/Shuddho/issues/291).
- **Supabase staging:** project `shuddho-staging` (`bsmbvjenpvcyfjzwtuax`) currently reports **ACTIVE_HEALTHY**, correcting the earlier inactive observation. Read-only checks found the `shuddho-coworker-staging` storage bucket exists and is private, security/performance advisors returned no lints, and no public-schema application tables or migrations were listed. This can be consistent with the project being used for Auth/Storage; no schema changes were made. The S3 access-key pair and Temporal credentials still require secure operator configuration and a real upload/read/delete and queue-polling test.
- **PA-10 credential workflow:** `.github/workflows/pa10-staging-prerequisite-preflight.yml` and `.github/workflows/provision-pa10-staging-worker.yml` reference `PA10_*` secrets through the `pa10-staging` environment. The actual environment reviewers/protection rules and secret presence cannot be read through the connected GitHub tools. The workflows must be run from `main` only after an authorized operator verifies the environment and required secrets. Provisioning requires the explicit `PROVISION` input; do not claim the worker exists until Render confirms it.
- **Vercel frontend:** the connected `shuddho-web-editor` project reports its latest production-target deployment `dpl_ASH9mH1XZ3rztm3mZ3VmMvv1mfWH` as **READY** on `79ab86a4e0ed8bfc549d26eb6db18cde8d3d1e88`, but the project summary reports `live=false`. Runtime-error/domain/deployment-detail inspection was denied or returned not-found in the connected account context, so production-domain assignment, runtime health and exact user-facing availability remain **UNVERIFIED**.
- **PostHog telemetry:** the connected PostHog account exposes a project named `Default project` with `ingested_event=false` and onboarding incomplete. It does not provide evidence that Shuddho's production/staging events, LLM usage, cost, latency or error telemetry are wired. Confirm the intended project and instrumentation before treating analytics as qualification evidence. The connected Linear workspace search returned only generic setup issues; the ProductOS project context is unnamed and has no wiki content, so neither currently provides a Shuddho acceptance ledger.
- **Scope status:** the repository has substantial implementation and passing code checks, but the overall required workflow is not green and the expanded coworker is not production-qualified. Architecture/core, PA-10, transactions, production controls and activation must remain **NOT FULLY QUALIFIED** until their individual code, provider, staging and operational evidence gates pass. No completion percentage is assigned because there is no validated weighted acceptance denominator.

### Current evidence table

| Gate | State at refresh | Exact closure condition |
| --- | --- | --- |
| PR #571 aggregate Temporal history bound | **MERGED; main CI in progress** | Confirm final merged-main coworker result; retain the resource-bound tests |
| PR #572 protected-environment secret references | **MERGED; configuration not yet verified** | Confirm environment protection, secret availability and successful authorized preflight |
| V-01 main protection | **BLOCKED_EXTERNAL / UNVERIFIED** | Admin-applied effective rules plus negative and positive merge-control proof |
| Current-main CI | **PARTIAL: test-and-build PASS; governance FAIL; coworker RUNNING** | Complete the current run; resolve governance through native policy, then rerun required CI |
| Production deploy gating | **BLOCKED_EXTERNAL / UNVERIFIED** | Render owner-authorized fail-closed promotion path and proof that an unqualified candidate cannot promote |
| Production API health | **LIVE DEPLOY; USER-FACING HEALTH UNVERIFIED** | Configure a readiness check and collect successful endpoint/latency evidence over an appropriate window |
| Controlled staging | **BLOCKED_EXTERNAL** | Verify current credentials, align API config, provision persistent worker, validate DB/Temporal/private storage/auth, freeze one exact candidate |
| Vercel frontend | **DEPLOYMENT READY; PROJECT NOT REPORTED LIVE** | Confirm domain assignment and authorized runtime/HTTP health |
| PostHog quality/economics telemetry | **NO SHUDDHO EVIDENCE IN CONNECTED PROJECT** | Confirm the intended project, verify event ingestion, then collect real usage/cost/latency/error data |
| A/C/P/V acceptance, PA-10, transactions | **NOT FULLY QUALIFIED** | Close each existing acceptance row/scenario/provider gate with exact SHA-bound evidence |
| Production activation | **NOT AUTHORIZED / NOT ESTABLISHED** | Capability-specific release evidence, human review and explicit bounded-pilot authorization |

### Dependency-ordered next actions

1. **Repository administrator — V-01:** use the already-merged operator from a trusted local environment with a suitably scoped admin token. Start with the dry-run command in the operator document; resolve existing/inherited policies before any apply. Never place admin credentials in PR-controlled CI or chat.
2. **Render owner — production deployment safety:** configure a fail-closed production promotion policy that requires the complete required checks to execute and succeed. The connected Render integration can inspect services/deployments but cannot change service auto-deploy settings, so this requires authorized dashboard/API access. Do not treat generic Render CI-check integration as sufficient when neutral/skipped checks are possible.
3. **Staging operator — PA-10:** verify `pa10-staging` environment protection/reviewers and securely populate only the required `PA10_*` secret references. Recheck the reviewed Render plan and database-expiry decision. Run the prerequisite preflight, then the worker-provisioning workflow from `main` with the explicit `PROVISION` input after approval. Confirm the actual worker service, migrations, Temporal polling, private S3 upload/read/delete, synthetic identity isolation and API/worker source match.
4. **Release engineer — freeze and qualify:** reconcile the live service configuration with `infra/render.staging.yaml`, configure `/health`, freeze one exact candidate, and run the existing PA-10 matrix. Do not reuse synthetic CI traces as live provider/model evidence.
5. **Core/transactions/quality:** continue dependency-ready A/C/P and transaction work without duplicating merged fixes. Obtain the missing provider contracts/accounts for shopping/travel, run all applicable transaction fault cases with independent effect observations, and finish restore/deletion/rollback/load/SLO plus human-reviewed English/Bangla quality and economics evidence.
6. **Release owner:** establish the correct PostHog project and event ingestion, then compile a version-bound release bundle and authorize only a capability-specific bounded pilot after all relevant gates pass. Keep expanded coworker/action flags off until then.

No administrator-only settings, secrets, paid resources, provider actions or production activation were changed during this refresh.

---

## Historical checkpoint — P-01 connected read-context grant recovery — 24 October 2026 (superseded 25 October)

- **Current base:** main `c3472f76ca2725fd8928abd59cdce57dc524422e`, merge of #560; repository main has no enforced native required checks/review ruleset at source selection (V-01 issue #484).
- **Historical state at publication:** `fix/p01-connected-grant-admission-recovery-20261024` / [PR #561](https://github.com/rumman52/Shuddho/pull/561) was unmerged at that time. PR #561 subsequently merged into main on 24 October; do not resume or recreate that branch. See the current release-blocker checkpoint above.
- **P-01/C-01 scoped defect:** Agent UI loses a confirmed connector read-grant if first sync fails, and an accepted-but-lost grant creation response is retried with a fresh key *and* expiry. The patch retains the exact pending identity per connection, blocks same-tick duplicate grant admissions, displays/selects confirmed grants before first sync, and preserves manual Sync/revocation.
- **Test-first regression coverage:** four new React tests in `connectorGrantAdmission.test.tsx`, included in the shared web test registry. Tests-before-fix commits `f58c078b` and `4b49bbd`; source fix `29fc7ff9`; [contract](P01_CONNECTOR_READ_GRANT_ADMISSION_RECOVERY_2026-10-24.md). Test-only CI was cancelled by subsequent branch pushes before Node tests completed; no observed red run is claimed.
- **Verification level:** implementation exists in a draft branch; exact final-head `test-and-build`, `coworker` and `ci-merge-gate` must be observed and independent review obtained. Staging, production qualification and activation remain **not established**. Owner-only native merge controls and external staging/provider prerequisites remain separately open.
- **Historical next action at publication:** inspect PR #561 final-head CI and review before merge. This is superseded by the confirmed merge; current work is the V-01 native-policy and staging blockers recorded at the top of this file.

---

## A-02 / P-01 goal-run admission replay — 24 October 2026

- Baseline `main` `d1621e5e320bce44ce4e5f5c3c773df39412fdc1`, merged #558. PR #559 is now merged into main; it covers Agent-form identity, not this goal-run path.
- Defect: `GoalWorkspace.runNow()` minted a fresh random key on every click, so an admitted-but-lost HTTP response could create a second durable Agent run on retry. The UI now binds retry to owner-visible goal ID/revision/language, changes identity when target changes, rotates only upon confirmed admission (before refresh), and blocks reentrant in-flight calls.
- Four integrated React tests exercise exact same-key uncertain replay, two legitimate starts, different goal after uncertain response, and confirmed run with failed follow-up refresh. Test module and runner registration preceded source fix; no observed RED execution claimed.
- [Bounded task contract](A02_P01_GOAL_RUN_ADMISSION_REPLAY_2026-10-24.md). Implementation on independent review branch; final-head web tests/build, full required CI and human review **pending at publication**. No staging duplicate-effect witness, PostgreSQL/Temporal operated recovery, native main protection, production qualification or activation established. Retain all 17 A/C/P/V requirements as not fully qualified.

---

## P-01 / C-01 Agent submission identity — 24 October 2026

- Base main `a14dee4870af05954936b88882e40f6db2374aab`. New dedicated review branch `fix/p01-agent-run-submission-identity-20261024`; earlier draft #558 is independent and remains unmerged.
- Concrete defect: after successful bounded-Agent admission the form retained its idempotency key, so an explicit identical run request returned the existing run. The fix rotates the key **only after confirmed success**, preserving same-key recovery following a lost response and changed-payload rebinding. The submit guard also rejects in-flight/disabled/invalid synthetic submissions before changing identity.
- Regression coverage: [`agentSubmissionIdentity.test.tsx`](../../apps/web-editor/src/coworker/agentSubmissionIdentity.test.tsx) exercises repeated accepted goals, accepted-but-lost response replay/fresh next click, and edited uncertain input; registered with the existing web test runner. Tests committed first, but no observed failing-first run is claimed.
- [Task contract](P01_AGENT_SUBMISSION_IDENTITY_2026-10-24.md). Implementation on review branch; exact-head web tests/build and required repository CI pending, independent review pending. No claim of staging qualification, production readiness, or activation. Native V-01 main protection remains blocked on administrator action. All 17 A/C/P/V formal acceptance requirements remain not fully qualified.

---

## V-01 required governance aggregate — 24 October 2026 (Asia/Dhaka)

- Base main: `ddb58a308b9cd28de791c911bc1338f12d7bed5c`; no open PRs at selection. Main [CI #39954055394](https://github.com/rumman52/Shuddho/actions/runs/39954055394) passed code/coworker and aggregate jobs while governance failed; native main protection was false and rulesets empty.
- Branch: `fix/v01-required-governance-gate-20261024`. The aggregate job now waits for governance and rejects failed/cancelled/skipped/missing audit results on main push. PR/review events retain the intentional read-only audit skip and independent-current-head review. Unsupported events and unexpected audit failures are denied. No elevated PR permissions.
- Added an unapplied native ruleset payload and administrator verification runbook, plus a complete Code Editor implementation/verification prompt. [Task and operator runbook](V01_REQUIRED_GOVERNANCE_GATE_2026-10-24.md); [Codex prompt](CODEX_COMPLETION_PROMPT.md).
- Test-first: **15 failures, 38 passes** before the workflow/configuration change. Focused governance/review/redirect suite: **149 passed, zero skips**. Full lightweight Python suite: **1,529 passed, 71 skipped, 6 warnings**; the skipped optional integration coverage is not claimed as verified. Release-contract checker passed. `git diff --check` passed.
- Independent AI review of the code/configuration/handoff found no Critical, Important or Minor findings and independently reran the focused suite: **149 passed, zero skips**. This is not human approval or live governance evidence.
- Native protection is **not applied** by these files. The read-only token may lack visibility of ruleset bypass actors even after configuration; missing visibility remains a failure, not proof of no bypass. A trusted administrator evidence path and real negative/positive merge controls remain required.
- Levels: implemented on review branch; exact-final-head remote CI and independent human approval pending; staging/production/activation not established. All 17 acceptance rows retain their outstanding qualification gates. No provider transaction, deployment, paid provisioning, flag change or merge performed.
- Next: inspect the final PR-head code/integration jobs and review; apply and verify the concrete native policy through authorized admin tooling; refresh staging prerequisites (#291), then close evidence gaps rather than reimplementing existing Runtime v3/browser/code/skill foundations.

---

## CW-09 CONNECT handshake deadline — 21 October 2026 (Asia/Dhaka)

- Refreshed baseline: main `94fd180e895c3fd90e760874ac8ff83cf11c1e78` after PR #526. PR #527 private-IP defense is a separate open change; its exact-head `test-and-build` succeeded and `coworker` was still running at task selection. Do not infer complete CI or human review from this partial state.
- Bounded source defect: the real HTTPS CONNECT boundary awaited broker authorization without a timeout, then started a fresh upstream inactivity timeout. Slow authorization plus slow TCP setup could exceed the intended navigation budget.
- Branch `fix/cw09-connect-handshake-deadline-20261021`; draft [PR #528](https://github.com/rumman52/Shuddho/pull/528); [task contract](CW09_CONNECT_HANDSHAKE_DEADLINE_2026-10-21.md). Local test-only commit `43831763912852a22a55bb6b07d661bb8f423891` produced 2 intended deadline assertion failures, 22 passes and zero skips against unchanged production source. Local source commit `7edb613a1835a3ee11b644cb9033355816d13a33` adds one shared handshake deadline, paired socket teardown and safe late-result rejection; established active tunnels retain the existing idle timeout.
- Review found an elapsed-deadline race before timer callbacks execute. Test-only `7189e57` reproduced both late-authorization and late-TCP readiness failures; correction `24d59057637984a97e522a4cecb652cc550d58b3` adds monotonic expiry checks before both side-effect boundaries. Final local Node policy/proxy suite: **26 passed, zero failures/skips**; source syntax check passed. Fresh agent re-review confirmed the original real TCP and authorization reproductions now reject, with no remaining Critical/Important finding. This is not human approval.
- `npm test` passed all configured workspaces (including 120 editor tests); full workspace build passed. Backend browser/broker tests: **117 passed, zero skips**. All **26** proxy/policy tests also passed on Node 20, matching CI's major version. The full Python suite remains in progress and is not claimed as passed.
- GitHub account/owner verification resolved the initial publication rejection; PR #528 was published through the connected integration after the shell lacked credentials. Initial remote head `e217a281dee5fb5865ba56496c70b4da19790097` exactly matched reviewed local tree `c3c630b9cffe563fd03039d3d11ac4c92cdd7d8e`. Its [CI #39543526174](https://github.com/rumman52/Shuddho/actions/runs/39543526174) passed `test-and-build`; `coworker` was still running at refresh. This final documentation checkpoint requires fresh exact-head CI; inspect PR #528's latest revision rather than qualifying it with an earlier run. Local TCP tests do not establish operated Chromium/DNS-rebinding or isolated staging evidence.
- Existing #527 exact-head [CI #39540792404](https://github.com/rumman52/Shuddho/actions/runs/39540792404) completed: code jobs `test-and-build` and `coworker` passed; `ci-merge-gate` failed for missing independent current-head approval. Do not merge based on code-job success.
- Levels: implemented **yes, review branch**; full repository-verified **pending**; staging-verified **not established**; production-qualified **no**; activated **no**. V-01 native protection #484 and staging #291 remain open. No schema, credentials, permissions, deployment, provider calls or paid resources change.
- Next: resolve any review findings, inspect all required checks on the final documentation-inclusive PR head, and obtain independent human review. Keep draft/unmerged until those external gates are satisfied.

---

## CW-09 — worker-side browser private DNS fence (21 October 2026, Asia/Dhaka)

- Baseline main `0c4b8a7d049aad4ff4657a5f101af55d05c792b5`. Separate [draft PR #526](https://github.com/rumman52/Shuddho/pull/526) is still open/unmerged: its test-and-build and coworker succeeded but ci-merge-gate failed. V-01 governance [#484](https://github.com/rumman52/Shuddho/issues/484) remains BLOCKED; no native protection was configured.
- Chosen **independent CW-09 source-level defect:** after broker DNS network-check, the real HTTPS CONNECT worker in `scripts/browser_pinned_proxy.mjs` enforced valid IP *syntax* but not public routability. A syntactically valid `127.0.0.1` returned from an erroneous broker response could reach TCP dialing.
- Draft [PR #527](https://github.com/rumman52/Shuddho/pull/527). Test-only SHA `4431e5fa0d7136114353c075d2f7d12d6ed867b9` extends the actual real TCP proxy harness with 14 private/mapped/mixed-address DNS regressions. [Test-only workflow #39539992177](https://github.com/rumman52/Shuddho/actions/runs/39539992177) cancelled before coworker reached proxy tests; do **not** count that as a full observed red integration run. Local copied original predicate independently returned `true` for loopback and failed the intended rejection assertion.
- Source fix SHA `1d4334f709bc8b5875889dcb63e6ae3d4b121ad9`: Node CIDR blocklists refuse IPv4 reserved/private and IPv6 not globally routable (plus transition/documentation ranges) before pinned dial. Reject an entire DNS answer if any item is disallowed. Local Node probe: 16 blocked and 4 allowed classifications. [Task contract](CW09_WORKER_SIDE_DNS_EGRESS_FENCE_2026-10-21.md).
- **Levels:** Implemented on feature branch; exact-final-head mandatory coworker and full CI **pending**; operated staging, production qualification and activation **not proven**. No provider credentials, network permission, schema, flags, external mutations or deployments changed.
- **Next:** inspect exact doc-inclusive PR-head `test-and-build` / `coworker` real proxy step / `ci-merge-gate`, obtain independent human review, keep draft/unmerged until native main governance and staging dependencies proven.

---

## V-01 required-check source pinning — 21 October 2026 (Asia/Dhaka)

- **Current baseline for this branch:** main `0c4b8a7d049aad4ff4657a5f101af55d05c792b5` (merged PR #525). PR #525 exact-head [CI #39493914888](https://github.com/rumman52/Shuddho/actions/runs/39493914888) concluded failure: test-and-build and coworker succeeded, ci-merge-gate failed. Main protection endpoint reports `protected=false`. V-01 issue [#484](https://github.com/rumman52/Shuddho/issues/484) remains open.
- **Implementation branch:** `audit/v01-ci-check-source-pinning-20261021`; [task contract](V01_REQUIRED_CHECK_SOURCE_PIN_2026-10-21.md). The read-only native policy evaluator now requires explicit GitHub Actions App source (ID 15368) per required job, rejects arbitrary/unpinned/duplicated sources, and keeps 2=blocked or 3=configuration-candidate (never success 0).
- **Tests/review:** Expanded native audit from 11 to **15 authored tests**. No local Python test execution, successful final-head CI, human approval or review sign-off is claimed at this checkpoint; retrieve exact-head CI after PR creation.
- **Levels:** implemented as review-branch changes; repository-verified **pending**; staging-verified **not established**; production-qualified **NO**; activated **NO**. No settings, providers, deployments, release flags or privileges were changed.
- **Next exact action:** obtain exact-head CI and independent final-head review, then authorized owner configures effective native protection and demonstrates live red/unreviewed/stale-head negative controls and green/reviewed positive control. Do not merge or close #484 based on a source-only diagnostic.

---

## V-01 continuation — live review snapshot confirmation (21 October 2026, Asia/Dhaka)

- Baseline main `e937dd974c04c725faca74fb5d6c3569f83c1b2c` (merged PR #523). [PR #523](https://github.com/rumman52/Shuddho/pull/523) **merged 2026-10-20 20:06:45 UTC** with **zero submitted reviews**. Exact-head [CI #39487739882](https://github.com/rumman52/Shuddho/actions/runs/39487739882): `test-and-build` success, `coworker` cancelled, `ci-merge-gate` failure. Native controls still BLOCKED [#484](https://github.com/rumman52/Shuddho/issues/484).
- Next bounded defect: live `scripts/independent_review_gate.py` re-fetched PR metadata after review pagination, but failed to re-fetch independent review *state*; a dismissal or newly submitted change request could be absent from the stale approval snapshot. This is a source gate weakness, **not a native branch protection fix**.
- Draft [PR #524](https://github.com/rumman52/Shuddho/pull/524), test-first `1f19e502f60accae966de5b3620bb069dba736e3`; actual [RED CI #39490196014](https://github.com/rumman52/Shuddho/actions/runs/39490196014) showed **5 intended regression failures, 1,266 tests passed, 71 skipped**. Fix `dfcf9e1f7178a7a23cbafd5ab47be33c54e88f60` re-fetches bounded review pagination, rejects changed evidence, and rechecks PR metadata after second fetch. `200e8595b401d91479d0f660a07cfe6342fd151a` updates original test's exact API call assertions.
- [Task contract](V01_REVIEW_SNAPSHOT_CONFIRMATION_2026-10-21.md). **Verification pending on final doc-inclusive PR head:** all three required jobs must complete successfully; no early merge, no bypass, and no independent-approval claim from automation.
- V-01 [#484](https://github.com/rumman52/Shuddho/issues/484) still needs owner/admin enforced native branch protections and negative-control verification. Staging [#291](https://github.com/rumman52/Shuddho/issues/291) is separately blocked. No production enablement, schema, credentials, provider calls, payments or deployment changed.

---

## V-01 continuation — historical approval vs CI gate chronology (21 October 2026, Asia/Dhaka)

- Baseline `main` `13360a9cd4e2d64fa9f2f2bf8c35befd4ca531ad` after #522; PR #522 **merged 2026-10-20 19:45:33 UTC**, no submitted independent human reviews, after code job success but before `coworker` cancellation and `ci-merge-gate` failure on exact-head [CI #39484713573](https://github.com/rumman52/Shuddho/actions/runs/39484713573). Both latter conclusions occurred **after merge**. Recorded in [#484](https://github.com/rumman52/Shuddho/issues/484#issuecomment-6300108322).
- Next bounded bug: `scripts/v01_merge_evidence.py` could report no incident when the first effective independent current-head approval was submitted **after** the historical `ci-merge-gate` completed (yet before PR merge). This specific gate run could not have observed any of those later approvals.
- Draft [PR #523](https://github.com/rumman52/Shuddho/pull/523). Tests-only commit `f3f6be69616a693ddd9947398d90e0d911598bb0`; real [RED #39487371765](https://github.com/rumman52/Shuddho/actions/runs/39487371765) `test-and-build` showed **3 intended failures, 1,263 passed, 71 skipped**, with unaffected positive control passing. Source fix `8631ebec491180aba9fa7d3a4ea3a72900cc43ab` binds effective approval times to the exact CI gate completion and flags `ci-merge-gate:completed_before_independent_approval` when no such approval existed by that time.
- [Task contract](V01_APPROVAL_GATE_CHRONOLOGY_2026-10-21.md). **Final-head CI required**: inspect all three required jobs after documentation commit, do not infer the outcome from earlier RED, and do not merge without independent human review.
- V-01 [#484](https://github.com/rumman52/Shuddho/issues/484) remains **OPEN/BLOCKED on native owner/admin protections and negative-control verification**; staging [#291](https://github.com/rumman52/Shuddho/issues/291) is separate. No deployments, payments, provider grants, secrets, policy changes or production activation.

---

## V-01 continuation — independent review submission evidence (21 October 2026, Asia/Dhaka)

- Refreshed main `d335fe98dcd277daa02011c0900ad957f62e7495` was the merge commit of PR #521. [Exact-head CI #39481714982](https://github.com/rumman52/Shuddho/actions/runs/39481714982): `test-and-build` passed at 19:16:21 UTC; PR #521 **merged at 19:26:14 UTC without submitted reviews**; `coworker` was cancelled at 19:27:28 UTC and `ci-merge-gate` failed at 19:27:36 UTC. Both were **post-merge** outcomes. V-01 native governance is still blocked [#484](https://github.com/rumman52/Shuddho/issues/484#issuecomment-6299558811).
- Chosen bounded source defect: `scripts/independent_review_gate.py` did not verify submission timestamps for APPROVED/CHANGES_REQUESTED/DISMISSED reviews or reject duplicate review IDs. These are malformed-evidence acceptance gaps, **not** the cause or cure of the native settings misconfiguration.
- Draft [PR #522](https://github.com/rumman52/Shuddho/pull/522). Test-only SHA `4b5848c4088f672c7e86521413aee7d3afe4888d` produced authoritative [RED #39484280083](https://github.com/rumman52/Shuddho/actions/runs/39484280083): **6 expected failures, 1,256 passed, 71 skipped**. Fix SHA `e907878b3b5cca3252405131637f20f5792d0cf4` adds timezone-aware submitted-at and globally unique review-ID validation, preserving nonactionable PENDING/COMMENTED semantics.
- [Bounded task contract](V01_REVIEW_SUBMISSION_EVIDENCE_2026-10-21.md). At checkpoint, exact-final-head **GREEN and mandatory coworker** must be independently read from GitHub Actions. A test-only red result is not verification of implementation; a green `test-and-build` alone is not a green full workflow.
- **Do not merge**: owner/admin main branch controls and independent final-head human review are not proven; V-01 [#484](https://github.com/rumman52/Shuddho/issues/484) remains OPEN. No new permissions, releases, credentials, providers, production/staging deployments, or cost.

---

## V-01 continuation — workflow provenance binding for merge evidence (21 October 2026, Asia/Dhaka)

- Refreshed `main` at start: `25c79968d763ce8d5bdba53ed0d0d66ba7bb2562` after #520. The #520 draft was merged at **19:03:54 UTC** on 20 October 2026 **without reviews**, after `test-and-build` succeeded (18:59:43) but **before** `coworker` finished cancelled (19:04:38) and `ci-merge-gate` finished failure (19:04:46) on exact-head [CI #39479360250](https://github.com/rumman52/Shuddho/actions/runs/39479360250). This is a **new governance incident**, not V-01 acceptance.
- Bounded source defect: `scripts/v01_merge_evidence.py` checked exact commit SHA but not whether the workflow run belonged to the PR's source branch/head repository and target repository. Introduced nine provenance controls first on SHA `b3c8b594caf39078fb22fe8c274e0ce1a264c70e`; [RED CI #39481027487](https://github.com/rumman52/Shuddho/actions/runs/39481027487) confirmed **9 intended failures, 1,246 passed, 71 optional skips**, in test-and-build before implementation.
- Draft [PR #521](https://github.com/rumman52/Shuddho/pull/521), branch `fix/v01-evidence-run-provenance-20261021`. Production code now rejects missing/mismatched `head_branch`, `head_repository.id`, and base `repository.id` against PR metadata; invalid evidence remains fail-closed. [Task contract](V01_WORKFLOW_PROVENANCE_BINDING_2026-10-21.md).
- **Verification boundary:** only the test-first RED result is fully confirmed at this checkpoint. Need to inspect final SHA full CI and independent human review before even considering merge. The evidence script is read-only and not enforceable native branch protection.
- **Governance V-01 #484 BLOCKED** until an authorized admin configures and proves non-bypassable exact-head CI and independent-review rules with negative controls. External staging [#291](https://github.com/rumman52/Shuddho/issues/291) incomplete. No permissions, secrets, deployment, production flag, paid resources or activation were changed.
- **Next:** verify final-head tests and coworker, request independent maintainer review, keep the PR draft/unmerged. Native owner/admin policy work is an independently required release prerequisite.

---

## V-01 next bounded task — historical pre-merge evidence audit (21 October 2026, Asia/Dhaka)

- Fresh `main` before this work: `1f50654d514a5c3c0079886c7154cecc4e793e8e` (PR #519 merge). [#519](https://github.com/rumman52/Shuddho/pull/519) merged **20 October 2026 18:42:34 UTC** with **zero submitted reviews**, despite exact-head [CI #39471452728](https://github.com/rumman52/Shuddho/actions/runs/39471452728) ending **FAILURE** at 18:30:39 UTC. `test-and-build` and `coworker` had passed; `ci-merge-gate` failed at 18:30:38 UTC. This is a confirmed merge-after-failed-gate incident, not a merely pending job. Recorded in [issue #484](https://github.com/rumman52/Shuddho/issues/484#issuecomment-6298600506).
- Branch `audit/v01-premerge-evidence-20261021` adds a **read-only**, fail-closed historical evidence classifier and focused regression tests. The classifier binds the exact PR SHA, reviews, three job outcomes and pre-merge completion timestamps; it refuses to equate no observed incident with effective branch protection. [Contract](V01_PREMERGE_EVIDENCE_AUDIT_2026-10-21.md).
- Focused isolated local test suite: **15 passed**, no skips. Local `py_compile` passed. These are NOT full repository or exact-head GitHub CI results, and the script is not configured as a required merge check.
- Current main branch summary reported `protected: false`, enforcement off; the rulesets list was `[]`, while the detailed protection endpoint returned **403** to the installed GitHub integration. Effective organizational/admin policies and tested bypass actors still require authorized inspection. Source audit/CI cannot enforce repository merges.
- **V-01 #484 OPEN / native protection NOT VERIFIED.** No repository-settings write, deployment, secret, cost, staging/prod activation or new execution authority. External staging prerequisites #291 and all seventeen A/C/P/V acceptance rows remain incomplete. Do not merge this branch without independent human review and final-head checks.
- Next: exact-head CI and independent review of this draft PR; independently, repository owner/admin enforces main rules and proves a failed/unreviewed PR cannot merge and a final-head reviewed PR can. Only that admin proof can change V-01 status.

---

## V-01 continuation — PR metadata revalidation during review retrieval (21 October 2026, Asia/Dhaka)

- Refreshed base main: `3eba42fb767ca29e24eca4ead22273eae09dd535`, merged #518. GitHub reports #518 merged at 17:50:47 UTC on 20 October and zero submitted reviews. Its earlier exact-head run #39462233199 passed both code jobs but **failed** independent-review gating; later run #39469590777 was still running during task selection. No effective governance acceptance is inferred.
- Next bounded defect: `validate_live_review` fetched PR metadata only before paginating reviews. A concurrent push, draft conversion, close or merge during retrieval could leave old metadata accepted with an old-head review.
- Test-first evidence: test-only head `36ea88e83dcf5a6a01c3b720cc77b28152aa0e3f`, [CI #39471147429](https://github.com/rumman52/Shuddho/actions/runs/39471147429), job 118795217428: **9 failed, 1,219 passed, 71 skipped**. All failures were the intended new live-validator cases. Lightweight optional-dependency skips are not mandatory coworker evidence.
- Implementation on `fix/v01-review-fetch-revalidation-20261020`, draft [#519](https://github.com/rumman52/Shuddho/pull/519): preserve initial validation, refetch PR metadata after the terminating review page, then reapply the current-head/eligibility/independence policy. No workflow, permission, schema or release flag changes.
- Independent agent review of the design/tests found no Critical/Important issue and requested initial-invalid/final-valid coverage. Three such cases were added before implementation. Final whole-diff agent review and exact-head code CI remain pending at this checkpoint; consult the final PR description for fresh evidence. Agent review does not satisfy independent human approval.
- [Contract](V01_REVIEW_FETCH_REVALIDATION_2026-10-21.md). This check is defense in depth, not an atomic merge transaction. Review changes after collection or PR changes after the final read require native GitHub review/check protections and event-driven reevaluation.
- **V-01 #484 remains OPEN**. Do not merge this unreviewed draft or count code CI as branch-protection evidence. Owner/admin must enforce and negatively test required checks/reviews without routine bypass. Staging prerequisites #291 and the full A/C/P/V qualification requirements remain incomplete. No deployment or production activation was performed.

---

## Current continuation — TX-03 integrity regression and corrective PR #503 (20 October 2026, Asia/Dhaka)

- **Current main at the regression:** `e8dfccdde32604824f67975be0a170c2563caec4`, after PR #502.
- **Regression evidence:** main CI [#39397296464](https://github.com/rumman52/Shuddho/actions/runs/39397296464) completed with `test-and-build` success, `coworker` failure (**4 failed, 1,452 passed**), and `ci-merge-gate` failure. The failing tests reject tampered stored terms/price before review binding, action approval, and provider claim.
- **Root cause:** PR #502 changed only two test files; it did not change production code. `TransactionRepository._require_current_fresh_terms` and `ActionRepository._validate_transaction_source_binding` trusted the stored `terms_sha256` value without recomputing it from persisted terms/price/quote data.
- **Corrective work:** draft [PR #503](https://github.com/rumman52/Shuddho/pull/503) adds shared canonical snapshot verification, validates redundant currency/total fields, and checks integrity at review binding and transaction-bound action approval/execution. The PR remains unmerged.
- **Verification boundary:** inspect the final PR #503 head and require exact-head `test-and-build`, mandatory `coworker`, and `ci-merge-gate` to pass; perform independent review and do not weaken assertions. A test-only or stale-head green run is insufficient.
- **V-01 remains OPEN:** repository rulesets currently return an empty list; this connection receives 403 for branch-protection reads and cannot change effective protection. Owner/admin action is still required to configure and test merge rules.
- **Overall status: INCOMPLETE.** No staging/production qualification or activation is claimed.

---

## Current architecture/core continuation — post-merge verification and governance (20 October 2026, Asia/Dhaka)

- **Current main:** `41a22aab83d48d78b65ebc530cb2889aeb54947b`, merge commit for PR #500.
- **PR #500 exact-head CI:** [run #39378060158](https://github.com/rumman52/Shuddho/actions/runs/39378060158) ultimately passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate`. The PostgreSQL connected-read/revocation concurrency regression ran in the required coworker gate after the fixture's parent rows were explicitly flushed before dependent rows.
- **Critical timing detail:** PR #500 merged at 06:10:43 UTC. Its `coworker` job completed at 06:26:55 UTC and `ci-merge-gate` at 06:27:01 UTC; the submitted-review API returned zero reviews. The exact-head workflow passed eventually, but its later success does not prove pre-merge enforcement.
- **Merged-main CI:** [run #39378904314](https://github.com/rumman52/Shuddho/actions/runs/39378904314) passed all three required jobs on this exact main SHA.
- **V-01 remains OPEN:** the repository branch endpoint reports `protected: false` and repository-level required-check enforcement disabled. Applicable organization-level policy still needs owner/admin inspection. Require PR-only merges, final-head checks, independent approval and substantive review-thread resolution; avoid ordinary bypass and validate both blocked and allowed merge cases. No repository settings were changed here.
- **Staging remains separate:** external worker, Temporal, S3, synthetic identity and provider/release-freeze prerequisites remain tracked in [issue #291](https://github.com/rumman52/Shuddho/issues/291). Do not put secrets in GitHub/chat; no staging or production qualification/activation is claimed.
- **Next actionable work:** repository/organization owner/admin must resolve V-01 in GitHub settings. Continue source implementation only after refreshing the specific acceptance row and proving the proposed gap is still present on current main; do not repeat already-merged PRs #497–#500 or infer full completion from green CI.
- **Overall verdict: INCOMPLETE.** All 17 A/C/P/V requirements remain not fully qualified; independent review, operated staging, quality/SLO evidence and explicit release authorization remain separate gates.
---

## Part 01 — connected-read grant admission TOCTOU (20 October 2026, Asia/Dhaka)

- **Base main SHA:** `bb366506d07ab2748fbbc8ea8d36b7b799f9cfb7` (PR #496 merge).
- **Root cause:** `ConnectorReadRepository.create` validated a read connection in a separate session, then persisted the grant without rechecking active state or current scopes. A disconnect/scope change in that gap could leave an active grant row attached to revoked authority.
- **Implementation:** PR [#497](https://github.com/rumman52/Shuddho/pull/497) merged a connection-first lock and current identity/scope check in the grant-creation transaction, plus deterministic disconnect/scope-revocation regressions.
- **Verification boundary:** PR #497 was merged while mandatory `coworker` was still running and without a submitted independent review. Its merge is not proof of complete required CI or governance. Recheck the exact merge-head results.
- **Contract:** [PART01_CONNECTED_READ_GRANT_ADMISSION_2026-10-20.md](PART01_CONNECTED_READ_GRANT_ADMISSION_2026-10-20.md). No migration, capability default, API surface or production configuration changed.

---

## Part 00 governance audit — 20 October 2026 (Asia/Dhaka)

- **Current main:** `bdd12f24390077cc838d4f528b5d8c58eb8c8a78` (PR #495 merged). This supersedes older checkpoint references to `c2d029c4782768b8aba04c96105eae978d7e2c07`.
- **PR #495 / C-01:** the Runtime v3 finalization fix for cancelled/cancel-requested and missing runs is merged. Its exact-head `test-and-build`, `coworker`, and `ci-merge-gate` eventually passed ([run #39319946005](https://github.com/rumman52/Shuddho/actions/runs/39319946005)), but the PR merged before `coworker` and `ci-merge-gate` completed. No submitted PR review was recorded. Do not count later green checks as proof that pre-merge governance worked. [Contract](C01_CANCELLED_FINALIZATION_FENCE_2026-10-20.md).
- **Current main CI:** all three required checks passed on exact `main` SHA `bdd12f24390077cc838d4f528b5d8c58eb8c8a78` in [run #39320415139](https://github.com/rumman52/Shuddho/actions/runs/39320415139).
- **V-01 remains OPEN; repository-level enforcement is not demonstrated:** GitHub's branch endpoint reports `protected: false` for `main`, and the repository rulesets API returned an empty list. The detailed legacy branch-protection endpoint returned 403 to the connected integration; inspect any applicable organization-level policy in Settings → Rules/Branches. Prove pending/failing checks block merge and that a passing independently reviewed PR can merge. [Issue #484](https://github.com/rumman52/Shuddho/issues/484).
- **Staging remains blocked by external prerequisites:** [issue #291](https://github.com/rumman52/Shuddho/issues/291) still lists the persistent worker, Temporal/S3 credentials, synthetic identity, provider setup and release-freeze checks. No secrets in GitHub/chat; no production activation.
- All 17 A/C/P/V acceptance requirements remain **not fully qualified**. The next safe step is owner/admin completion of V-01 governance, while staging prerequisites are completed separately; do not enable unqualified capabilities.
---

## Architecture/core closure — C-01 final completion evidence (20 October 2026)

- Base `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`, dedicated branch `codex/c01-v3-completion-evidence-20261020`. Existing merged #490 replay behavior preserved.
- Reproduced three finalization bypasses: empty run, missing-information receipt, unconfirmed action receipt. Pre-fix run: **3 failed, 3 positive controls passed**. Finalization now reuses `v3_can_complete` inside the existing run-row transaction. No schema, new authority, capability default or activation change.
- Focused final recovery/finality checks: **56 passed, zero skips**; baseline **50 passed**. Independent read-only agent review found no Critical/Important findings. Full local suite is running; mandatory exact-head GitHub CI remains required. [Contract](C01_V3_COMPLETION_EVIDENCE_2026-10-20.md).
- Current staging preflight is **blocked_external: RENDER_API_KEY REQUIRED** in this session. This does not establish remote billing/deployment status. Operated browser/sandbox isolation, CW-11 mixed-version drain, sixteen CW-02 staging artifacts, realistic coworker/model quality and independent human release reviews remain unverified. The full 17-row A/C/P/V inventory remains in scope and INCOMPLETE.
- Next source tasks found by independent review: sandbox cleanup-before-completion and deadline enforcement during control I/O; conversation linked-run navigation and payload-bound UI retries. Each requires a separate reviewable task. No production activation or merge performed.

---

## Architecture/core closure — C-01 completed-step deadline retry (20 October 2026)

- **Starting main:** `7aa69522d8be40360123c4ec6d21896c3c9792cd` includes merged #489. PR #489's exact-head CI passed; post-merge CI was still in progress at snapshot.
- **Defect:** `execute_step` rejected a completed Runtime v3 invocation on delayed activity retry if the task deadline had passed, before consulting its existing durable state.
- **Patch:** [PR #490](https://github.com/rumman52/Shuddho/pull/490) replays previously completed v3 invocation without dispatch, but rejects cancellations/competing terminal outcomes and enforces deadline before fresh work. Legacy v1/v2 behavior preserved. [Contract](C01_V3_STEP_COMPLETION_DEADLINE_REPLAY_2026-10-20.md).
- **Evidence:** five regression instances committed before source change; must complete mandatory exact-head CI with zero skips and independent review. Synthetic receipt fixture does not establish operated Temporal/PostgreSQL or provider verification. C-01/A-02 and broader A/C/P/V acceptance remain open.

---

## Architecture/core closure — C-01 terminal tool state integrity (20 October 2026)

- **Base:** main `79c111d7bc3ec8ae1ad65b55e4f78595aec54e46`, merged #485. Independent [PR #486](https://github.com/rumman52/Shuddho/pull/486) prevents late Runtime v3 tool plan/start/receipt and approved-action readiness transitions from reviving an already-terminal run.
- **Root cause and scope:** `append_v3_step`, `begin_invocation` and `finish_invocation` did not check non-cancel terminal Runtime v3 outcomes under their existing row locks. The fix adds fail-closed guards while preserving legacy v1/v2 operations and exact committed result replay. [Contract](C01_TERMINAL_TOOL_STATE_FENCE_2026-10-20.md).
- **Evidence:** six regression instances were committed before implementation; four additional plan/action-readiness cases were added with the follow-up guards. Exact-head CI and independent review are required; unexecuted/cancelled test-only CI is not failing-first evidence. No live provider/worker or staged process-recovery proof is claimed.
- **Remaining:** C-01/A-02/P-03, CW-09 live isolation, CW-10 sandbox, CW-11 mixed worker and all operated quality, security, rollback, activation gates remain open. No schema, new authority, default flag or production action.

---

## Architecture/core checkpoint — A-03 compatibility inventory and combined verification (20 October 2026)

- Inspected main `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`; dedicated documentation branch `codex/a03-compatibility-inventory-20261020`. [62-revision review and rollback inventory](A03_MIGRATION_COMPATIBILITY_2026-10-20.md). Alembic ScriptDirectory and source metadata confirm one linear chain of 62 revisions with head0062; all local links resolve. Independent review corrected five explicitly refused expand-only downgrades and clarified reviewed research's database version versus Temporal type.
- Three separate, unmerged source PRs: [#491](https://github.com/rumman52/Shuddho/pull/491), head `e7644e64ac47fd81672894108dc2698bd4f02765`, final completion result validation; [#492](https://github.com/rumman52/Shuddho/pull/492), head `7e9d5f96658a80d6dc96e9dc4961e0250d1e1710`, sandbox supervision/cleanup; [#493](https://github.com/rumman52/Shuddho/pull/493), head `ab428153cb4828f945252f020062e7b48b205651`, conversation retry/navigation identity. Their source trees match the corresponding locally tested commits. No PR is treated as merged or activated.
- Combined local source head `6cc65704ea7fb9ad5005405dc5b253b39e848a30`, tree `d13cef85655742286560609215a2081cd11afba2`, applies all three without conflicts: **245 related Python tests passed, zero skips/failures**, mandatory collection gates passed. Full JavaScript workspaces passed, including web-editor **120 tests**; final TypeScript/Vite build passed. Independent source reviews resolved all substantiated Critical/Important findings.
- Full local Python run on the C-01 source tree matching #491: **2338 passed, 86 skipped, 17 warnings**, zero failed/error tests. Skips: 43 need PostgreSQL (41 dedicated DB, one concurrent admission, one post-mutation disconnect); 41 need a Temporal server; two ML collection skips need PyTorch. This is not a zero-skip mandatory-integration verdict. Local JUnit2 emitted record_property warnings; six proposal-fixture serialization warnings also occurred. Required GitHub coworker CI supplies separate PostgreSQL/Temporal/browser evidence.
- At this checkpoint, all three PRs have successful test-and-build checks; their full coworker/merge gates remain to be refreshed. CI runs: [#491](https://github.com/rumman52/Shuddho/actions/runs/39314867789), [#492](https://github.com/rumman52/Shuddho/actions/runs/39316114712), [#493](https://github.com/rumman52/Shuddho/actions/runs/39316327464).
- Offline evaluation gates passed: agent12/12, routing27/27, multilingual23/23, permanent suite410 scenarios, long-horizon6/6 scenarios with62/62 milestones, curated quality5/5. These are deterministic/offline contracts, not live model usefulness, cost/latency, human acceptance or availability measurements.
- **Remaining scope unchanged:** all17 A/C/P/V rows; archived-history replay corpus, exact old/new binary compatibility, sixteen operated CW-02 artifacts, live browser/sandbox isolation, CW-11 mixed-worker drain/rollback, four realistic coworker outcomes, human security/operations review and production qualification. A-01/A-02/A-04 contracts were reviewed at bounded source interfaces; A-03 inventory now exists but compatibility/replay/operated evidence remains unverified.
- Current staging preflight is blocked by missing RENDER_API_KEY in this session. Complete the remaining final-head CI/review gates, then use existing prerequisite/freeze/qualification collectors in the approved staging context. No paid infrastructure, external messages/transactions, schema change, deployment or activation was performed.

---

## Architecture/core closure — C-01 terminal Runtime v3 planner reservation fence (20 October 2026)

- **Starting main:** `7c2eced6396f2cdf93106bf05e006b7c423eecfb` includes merged #480–#483. Existing Core v3 committed retry and no-tool block fixes are preserved.
- **Root cause:** a new post-terminal Runtime v3 activity could enter `reserve_planner` after needs_input/blocked, reserving provider/daily tokens before eventual late-decision rejection. [Contract](C01_TERMINAL_RESERVATION_FENCE_2026-10-20.md).
- **Bounded fix / PR:** [#485](https://github.com/rumman52/Shuddho/pull/485) rejects new logical decisions early and under the AgentRun reservation lock; exact committed result replay, cancellation errors and v1/v2 behavior stay unchanged. No schema, grants, capability defaults, paid providers or activation.
- **Evidence boundary:** five test instances committed before implementation; require exact final-head CI and independent review before declaring repository verification. No deployed Postgres/Temporal, live provider/cost, mixed-version or operated staging evidence supplied. A-02/C-01 remain open at complete acceptance level.

---

## Architecture/core closure — P-01 conversation request and navigation identity (20 October 2026)

- Branch `codex/p01-conversation-request-navigation-20261020`, base `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`. [Contract](P01_CONVERSATION_REQUEST_NAVIGATION_2026-10-20.md).
- Reproduced three defects with mounted React components: an old linked run opens unrelated recent work; edited message/title retries reuse the original accepted payload key. Final source preserves exact linked-run GET even outside recent30 and binds retry keys to normalized request payloads, including conversation and ordered source identity.
- Six mounted component scenarios pass: old linked run, rejected target without fallback, identical message/title replay, changed message/title. Full JavaScript workspace suite passed; web-editor runner **120 passed, zero failures/skips/cancellations**. Final web-editor TypeScript/Vite build passed. Independent read-only agent review found no Critical/Important findings. React renderer is a development-only dependency; the test bundle uses the same native React instance to avoid hanging act MessagePorts.
- Required final-head CI remains pending at publication. Chromium download in this session failed; mounted component/client fixtures are not a full browser/API/worker reconnect qualification. No schema, approval, model provider, backend history limit, production dependency, deployment or activation change. P-01/P-03 and the full A/C/P/V inventory remain unqualified.

---

## Architecture/core closure — P-01 conversation activity refresh ordering (19 October 2026)

- **Starting main:** `bc88f124e61f003bcbf70dbba2303590992edd0a`, merged PR #482. [Task contract](P01_CONVERSATION_ACTIVITY_REFRESH_ORDER_2026-10-19.md).
- **Source-level defect:** `ConversationWorkspace` runs a 5-second activity polling loop without preventing simultaneous requests or rejecting older responses. A slow response can overwrite a more recent run state; a post-dispatch explicit refresh can also lose to a stale poll. The activity API is read-only, but misleading progress affects P-01 continuity.
- **Bounded change:** serialize only background polls and reject stale results using a monotonic request revision shared with explicit refreshes; invalidate on conversation switching/unmount, and avoid applying an old conversation's response. No new ledger, API, provider, navigation, or authorization behavior.
- **Regression coverage:** new Node unit tests for out-of-order completion, conversation switch, and explicit action refresh. Full frontend test/build, final-head mandatory CI, independent review and staging UI reconnect remain to be verified at the PR. No activation.

---

## Architecture/core closure — P-01/P-02 source identity (19 October 2026)

- Starting main `8a83844b148a811357b8906c58deb3ba8b76f1d3` contains merged #479; no open PR existed at fresh task selection. #479 exact-head required CI passed. Merged-main CI is checked separately.
- Branch `codex/core-context-source-closure-20261019` fixes three reproduced core/context failures: changed dispatch output-language replay, expired-source memory acceptance, and goal-memory acceptance after originating conversation erasure. [Contract](CORE_CONTEXT_SOURCE_CLOSURE_2026-10-19.md).
- Failing-first result: 3 failed, 1 positive control passed. Focused final result: 63 passed, zero skips/failures/errors across conversation admission/dispatch/context and memory; mandatory collection gate passed. Final-head full CI and independent review are pending at publication; inspect this branch's PR checks for final results.
- This is one coherent source slice in the user's full Architecture/Core scope. Remaining implementation review found durable Runtime v3 retry, sandbox cleanup/process-boundary and conversation steering/navigation gaps; these are being handled separately. The existing 17 A/C/P/V acceptance rows remain in scope.
- No staging, human security review, production qualification or activation is claimed. Current local staging access is not supplied; do not manufacture provider/deployment evidence.

---

## CW-02 retention reference snapshot ordering — 19 October 2026 (Asia/Dhaka)

- **Verified starting main:** `a95d87f6aea1f54139737a628675850f95524576`, merged [PR #478](https://github.com/rumman52/Shuddho/pull/478). Exact-main [CI #39260672598](https://github.com/rumman52/Shuddho/actions/runs/39260672598) passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate`. No open PR existed at selection. Historical pending PR/CI statements below are superseded for this starting revision.
- **Demonstrated defect:** orphan cleanup sampled database references before potentially slow object inventory. An age-eligible object checkpointed during the listing could be falsely identified and deleted. Both new preview/apply cases failed against unchanged production code.
- **Bounded implementation:** branch `codex/cw02-retention-reference-snapshot-20261019` reads references after inventory completes. Its real SQLite export checkpoint/local-store regressions preserve newly referenced bytes while retaining a genuine orphan cleanup control. Existing minimum-age, prefix, inventory-validation and failure/retry behavior remain unchanged. [Task contract and residual boundary](CW02_RETENTION_REFERENCE_SNAPSHOT_2026-10-19.md).
- **Verification:** baseline retention suite 20 passed; pre-fix regression 2 failed, 20 deselected; post-fix retention suite 22 passed, zero skips/failures/errors; mandatory JUnit collection gate passed. Full local suite is running; required final-head CI remains pending at publication. Independent final read-only branch review found no Critical/Important findings and independently reran both new cases (2 passed, 20 deselected). This is agent review, not human security/operations certification.
- **Residual boundary:** references committed after the post-inventory database read can still race deletion. This slice does not establish atomic garbage collection; operated cleanup requires quiescent writers until coordinated exclusion is qualified. Synthetic aged local objects are not real S3 outage/erasure evidence.
- **Review PR:** [#479](https://github.com/rumman52/Shuddho/pull/479), targeting `main`; code/test content commit `6ed3b6c66daf332b69bef219ff376c7a1a62ea69` has Git tree `7671246b5a588b353e81efaca357ab90a9d3e46a`, matching the locally tested/reviewed tree. This documentation follow-up records review and current preflight; inspect the PR head and its new CI before integration.
- **Fresh local staging preflight:** `uv run python -m scripts.staging_prerequisite_preflight --output /tmp/shuddho-staging-preflight.json` returned `blocked_external: RENDER_API_KEY REQUIRED`. This establishes missing access in this session only, not current Render billing/worker state or absence of repository secrets. The next environment owner step is to run the same preflight within the approved staging secret context, then freeze/verify matching API and worker identity and collect operated scenarios.
- **Completion:** implemented on review branch; full repository verification pending; staging/production qualification and activation not established. All sixteen operated CW-02 cases, matching staging identity, CW-11 mixed-version drain, live browser/sandbox isolation, measured coworker/model quality and independent release reviews remain open. No deployment or activation.
- **Next:** inspect final-head required CI and independent branch review, integrate through the review process, then execute controlled staging collectors when matching environment/provider access is available. Do not replace missing operated proof with more synthetic PASS records.

---

## Architecture/core closure — C-01 no-tool terminal retry integrity (19 October 2026)

- **Baseline:** `main` `129fa78a578df10ad861a9ded7a3a3a4fec90cf8`, after merged [#481](https://github.com/rumman52/Shuddho/pull/481). Dedicated [PR #482](https://github.com/rumman52/Shuddho/pull/482) addresses a bypass of that durable decision-result path when no tools are enabled.
- **Defect and scoped fix:** previously the no-tool branch persisted `blocked` without a logical activity result checkpoint, and could return `blocked` after a concurrent cancellation or `needs_input` transition. The existing AgentRun transaction now atomically checks active authority, records one blocked event and one retry-identity result. No additional ledger/schema, broader grant, new tool, workflow-history change or activation.
- **Evidence status:** three replay/cancellation/competing-terminal regression tests were committed before implementation; two additional lost-response/atomic-rollback tests were added after the fix. The test-only CI attempt was superseded/cancelled before coworker tests completed, so failing-first execution is **unverified**, not claimed. Exact final-head CI and independent review are required for repository verification. [Contract](C01_V3_NO_TOOLS_TERMINAL_RECOVERY_2026-10-19.md).
- **Closure boundary:** C-01 and A-02 remain partially implemented and not staging-qualified. Operated Temporal/PostgreSQL recovery, browser/sandbox and CW-11 mixed-version isolation, realistic coworker quality, independent operational/security review and production activation remain open.

---

## Architecture/core closure — durable v3 decision recovery (19 October 2026)

- Branch `codex/core-v3-durable-decision-retry-20261019`, base main `8a83844b148a811357b8906c58deb3ba8b76f1d3`. [Contract](CORE_V3_DURABLE_DECISION_RECOVERY_2026-10-19.md).
- Actual Temporal activity attempt 2 previously inferred again and failed `agent_loop_detected` after attempt 1 committed. The activity now derives a stable logical identity and atomically commits the decision, memory/step/terminal effect, exact result and idempotent token settlement through the existing Agent ledger/checkpoints. Uncommitted actual inference attempts remain bounded and charged.
- New recovery module: 8 passed, zero skips; includes lost commit response and pre-step interruption. Surrounding regressions, independent review and exact-head CI are finalized in the PR; full CI is pending at publication. No migration, workflow argument/history change, grant, default flag, deployment or activation change.
- Context slice is draft PR #480, independently reviewed with 63 passing local tests; exact-head CI pending. The finite 17 architecture/core acceptance IDs remain in scope; sandbox lifetime, conversation steering/navigation/explicit memory selection and final design/inventory closure continue separately. Operated staging and human qualification remain absent.

---

## CW-02 S3 inventory owner-scope and terminal-page integrity — 19 October 2026 (Asia/Dhaka)

- **Starting main:** `b91d7952da640cc59c9c826ca0c0a18f9f23599b`, merged [PR #477](https://github.com/rumman52/Shuddho/pull/477). At task selection exact-head [CI #39238717292](https://github.com/rumman52/Shuddho/actions/runs/39238717292) had `test-and-build` success and mandatory `coworker` in progress. No independent PR review recorded. Merged-main CI remains a separate check.
- **Demonstrated gap:** Although #477 rejects missing continuation tokens, cycles, duplicate keys and malformed dates, the S3 listing adapter still trusted `IsTruncated` values of arbitrary types and accepted S3 keys outside the requested owner/prefix. `RetentionRepository.cleanup_orphans` uses the returned list for deletion.
- **Bounded implementation:** require actual boolean `IsTruncated` and enforce the requested prefix on each listed object before returning any inventory. Added deterministic fake-S3 fixtures for invalid final-page values and foreign-prefix keys on first/second pages. Preserve all existing guards, permissions and object-store interface. Require exact-head mandatory CI and independent review before merging the review PR.
- **Limit:** synthetic response-integrity tests, not actual S3 outage/erasure evidence. Full 16 operated CW-02 fault cases, CW-11 staging, browser/code sandbox isolation, live coworker outcome quality and independent release review remain open.

---

## CW-02 S3 inventory pagination and orphan-recovery safety — 19 October 2026 (Asia/Dhaka)

- **Verified starting main:** `dfe7c3c5592c8bd8edc8d5487454c2e86c7eeddf`, [PR #476](https://github.com/rumman52/Shuddho/pull/476) merged to main. Its exact-head [CI #39228196768](https://github.com/rumman52/Shuddho/actions/runs/39228196768) passed `test-and-build`, mandatory `coworker` and `ci-merge-gate`. No submitted independent review was found. The merged-main CI must be checked separately.
- **Demonstrated code gap:** `S3ObjectStore.inventory` previously returned a partial inventory when `IsTruncated` was true but `NextContinuationToken` was absent. It also lacked repeated-token and duplicate-key guards. This threatens the integrity/boundedness of existing `RetentionRepository.orphan_candidates` and `cleanup_orphans`, which consume the listing.
- **Bounded fix:** retain the existing ObjectStore protocol; reject incomplete, cycling and duplicate-key S3 listings instead of reporting partial completion or looping. Deterministic fake-S3 tests cover a valid multi-page scan, absent/blank/invalid tokens, repeated token and duplicate keys. These tests are in existing mandatory `tests/test_coworker_retention.py`. Require exact-head CI and independent review before mainline merge.
- **Evidence boundary:** repository S3-response simulation only. Real S3 read/write failures, sixteen operated CW-02 provider/process faults, staging identities, CW-11 mixed-version drain, browser/sandbox isolation and human security/production qualification remain open. No activation.

---

## CW-02 exact fault artifact-set integrity — 19 October 2026 (Asia/Dhaka)

- **Inspected main:** `2cc3778c9219d943a0e56938f2d4e4c6f75727b5` (PR #475 merged), PR #475 exact-head CI [#39220814698](https://github.com/rumman52/Shuddho/actions/runs/39220814698) passed required `test-and-build`, `coworker` and `ci-merge-gate`; no independent PR review submitted. Its merged-main CI must be checked independently.
- **New bounded acceptance:** The 16 CW-02 artifact names constitute a closed set. Both standalone `verify_evidence_files` and signed `fault_tree_sha256` reject symlinked evidence directories and unmanifested extra entries; preserve checksums, source/run identity, per-file symlink rejection and the same signed witness trust model. The branch includes unit and signed-bundle synthetic tests for exact set, extras and alias directory. Require exact-head CI + independent review before merge.
- **Qualification boundary:** Structural evidence integrity is not operated staging proof. Full 16 real fault injections, provider-applied mutation counters, CW-11 mixed-version drain, live browser/sandbox isolation, quality, independent security/operations review and production activation remain OPEN.

---

## CW-02–04 signed release schema strictness — 19 October 2026 (Asia/Dhaka)

- **Starting revision:** `main` `e43762a1aeb43602edc9c88be082f2c9d1668b17`, merged [PR #474](https://github.com/rumman52/Shuddho/pull/474). PR exact-head [CI #39218975244](https://github.com/rumman52/Shuddho/actions/runs/39218975244) had test-and-build passed, mandatory coworker in progress; merged-main CI also running at task selection. No independent review found. Do not claim all gates complete.
- **Bounded task:** `codex/cw0204-signed-schema-type-fail-closed-20261019` rejects JSON `true` or `1.0` for `checkpoint.schema_version` and signed independent-review `schema_version`, complementing strict CW-02 manifest handling. Freshly signed synthetic fixtures test both, plus ensure only frozen API/worker observations define the review timestamp floor. Require final-head mandatory CI and independent review before merge.
- **Release boundary:** code and synthetic evidence integrity only. Sixteen operated fault cases, CW-11 mixed worker drain, browser/code isolation, independent security/operations review, staging model quality and production activation all remain OPEN.

---

## CW-02 chronology mainline integration checkpoint — 19 October 2026 (Asia/Dhaka)

- **Correct source-of-truth:** `main` at `f1ae5b643da3a4a6ef9be0b16638b653bf8ba3b5` contains [merged PR #472](https://github.com/rumman52/Shuddho/pull/472), whose head [CI #39215117594](https://github.com/rumman52/Shuddho/actions/runs/39215117594) passed all three required jobs. [PR #473](https://github.com/rumman52/Shuddho/pull/473) is reported merged, but **its base was the #472 feature branch, not main**, so the CW-02 signed-fault chronology check was absent from main at inspection. No independent GitHub PR reviews were recorded for #472/#473.
- **This integration task:** `codex/cw02-chronology-mainline-integration-20261019` reuses the exact functional implementation and signed synthetic regression tests already authored in #473, cherry-picking only `scripts/cw0204_qualification_gate.py`, `tests/test_cw0204_qualification_gate.py`, and the existing CW-02 contract onto current main. It verifies that fault observations cannot predate the later of frozen API and worker readiness, including timezone offsets and signed contradictory bundles. Publish one main-targeted PR and require exact-head mandatory CI and independent review before merge.
- **Evidence level:** implementation carried into a new branch; verification/merge pending until observed. The signed gate proves structural consistency, not an actual operated staging fault, provider mutation, reviewer identity, or production release. CW-02 sixteen operated cases, CW-11 staged worker drain, real browser/sandbox isolation, independent security review, live coworker task quality and activation remain OPEN.

---

## Current continuation — CW-02 fault evidence integrity hardening (19 October 2026, Asia/Dhaka)

- **Main:** `c04eccf3ce9ca8778da0931c2f1d96d4ac3270dc` (PR #471 merged). [PR #471 head CI #39213261699](https://github.com/rumman52/Shuddho/actions/runs/39213261699) had test-and-build passed, mandatory coworker still in progress at last inspection; [merged-main CI #39214301418](https://github.com/rumman52/Shuddho/actions/runs/39214301418) was also in progress. No independent PR #471 review was recorded.
- **CW-02 next bounded slice:** `codex/cw02-fault-evidence-identity-hardening-20261019` enforces operator/environment/result identity agreement between the manifest and each checksummed fault record; rejects duplicate JSON object keys, nonfinite JSON constants, and boolean schema-version substitutions. Update both CW-02-only and signed CW-02–04 synthetic fixtures so stronger checks run through mandatory CI. The branch must pass exact-head CI and independent review before merge.
- **Evidence boundary:** This is offline internal-consistency checking only, not confirmation of operator identity or independent provider observations. All sixteen real fault cases, controlled staging identity, real browser/sandbox isolation, CW-11 drain, human security review, model quality and production qualification remain open. No activation is authorized.

---

## Current continuation — CW-02 PR #471 conflict resolution and cleanup recovery (19 October 2026, Asia/Dhaka)

- **Base:** main `7e20e1bb9dd5f80af30e104d8cc71ab1635224a6` (merged #470); required mainline CI [#39164154651](https://github.com/rumman52/Shuddho/actions/runs/39164154651) completed successfully.
- **Work:** [PR #471](https://github.com/rumman52/Shuddho/pull/471), `codex/cw02-orphan-delete-failure-reporting-20261019`, retains the existing deletion-failure regression and adds a recovery retry: the first cleanup must report the failed key without deleting it; after restoring the store, a second age-bounded cleanup must delete the same orphan.
- **Previous branch verification:** exact-head [CI #39160757345](https://github.com/rumman52/Shuddho/actions/runs/39160757345) passed test-and-build, mandatory coworker and ci-merge-gate on `1a248f6317509ab8676ef71d23cc23acd674001c`; it does **not** validate the new merge/recovery commit, whose exact-head checks remain pending.
- **Integration:** merge the newer main tree without discarding #470 browser DNS protections or already-merged CW-02 recovery tests, and retain one canonical continuation record.
- **Evidence boundary:** local SQLite/object-store failure injection is not live S3 or operated staging. Sixteen distinct CW-02 staging artifacts, independent provider-side observations, CW-11 mixed-version drain, real browser/sandbox isolation, independent security review, quality qualification and authorized activation are still open.

---

## Current continuation — CW-02 and CW-09 gates (19 October 2026, Asia/Dhaka)

- **Main:** `1a852034576a9a5124187d9901203864b3664ed6`. PR #468 hard-worker-loss orphan-recovery test is merged and its exact-head `test-and-build`, mandatory `coworker`, and `ci-merge-gate` passed.
- **Merged-main CI:** run [#39159745525](https://github.com/actions/runs/39159745525) on this SHA was still running at the last refresh. Do not call mainline fully verified until all required jobs pass.
- **CW-09 follow-up branch:** `codex/cw09-proxy-dns-response-shape-20261019-v2` validates broker response hostname and resolved-IP structure before dialing from the real CONNECT handler. Local socket regressions cover missing/mismatched hostname, empty/non-array lists, invalid IP literals and excessive entries. Exact-head CI has not run yet.
- **Evidence boundaries:** no local checkout was available to execute these tests directly during authoring; GitHub CI remains the executable verification gate. Local proxy sockets do not prove live Chromium, DNS rebinding, private-network isolation or staging.
- **Still open:** the complete sixteen-row CW-02 operated evidence matrix; protected CW11-STAGING mixed-version drain; browser/sandbox isolation; independent review; personal-coworker quality and production qualification. No deployment, provider activation or production action is claimed.


---

## Current source-revalidation checkpoint — 18 October 2026 (Asia/Dhaka)

- Refreshed main: `9e52756e4de52d95cc69879ce7cdbb3a390c0ac7`; #461 is merged, not open. No open PRs existed at task selection. Main CI [#39147097140](https://github.com/rumman52/Shuddho/actions/runs/39147097140) was still running when this checkpoint was written; its `test-and-build` job passed. The earlier #461 code/test head passed all three required jobs in #39141823326. No formal independent review submission was recorded for #461.
- Work branch: `codex/c01-late-planner-source-revalidation-20261018`. [Task contract](C01_LATE_PLANNER_SOURCE_REVALIDATION_2026-10-18.md). Fresh Runtime v3 decisions now revalidate the original conversation's selected source pins after inference, before saving model output/checkpoints. Already-committed decisions retain idempotent replay; direct/legacy run semantics remain unchanged.
- Reproduction: six source-invalidated cases failed before the guard; unchanged-source control passed. Focused conversation/context/cancellation regressions: **41 passed, 92 deselected**, zero skips. The mandatory JUnit gate passed. Full local pytest and exact-head required CI remain pending at publication; consult this branch's PR checks for the final revision. These numbers are a focused selection, not a repository-wide total.

| Part | Evidence-supported status | Remaining gates |
| --- | --- | --- |
| Architecture A-01..04 | Existing state/trust foundations and repository recovery contracts; this slice adds no store, orchestrator or schema | Mixed-version operated recovery/rollback, staging boundary review |
| Core C-01..06 | #461 grounded adapter handoff is merged; late selected-source response guard locally verified in this branch | Final-head CI/review; real browser/sandbox isolation; CW-11 staged drain; live provider/model qualification |
| Context/experience P-01..03 | Existing owned conversations and explicit selected context; delayed invalidation regression added | Four operated study/work/separation/recovery scenarios and UI reconnect evidence |
| Verification V-01..04 | Focused regression evidence only for this branch | Full mandatory final-head CI, protected staging, human security/quality review and separately authorized production rollout |

Separate read-only agent review found no Critical/Important issues; this is not human security certification. Minor observation: the no-memory-proposal assertion is only incidental because the synthetic response proposes no memory. End-to-end Temporal failure-state persistence and PostgreSQL invalidation races remain outside this regression.

The full Architecture/Core Agent workstream remains **INCOMPLETE**. No staging, production qualification or activation is established. The guard observes invalidation committed before its source check; it does not claim serializable source-deletion locking or recall of data already submitted to inference. Historical checkpoints below are retained and superseded by this entry.

---

## Current continuation checkpoint — 18 October 2026 (Asia/Dhaka)

- Current `main`: `ea7ad398f69e898b152f4227cb6e0c1a193999c1`. PR #460 is merged; its exact-head CI [#39111138510](https://github.com/rumman52/Shuddho/actions/runs/39111138510) passed all three required jobs. Merged-main CI [#39138804133](https://github.com/rumman52/Shuddho/actions/runs/39138804133) also passed all three required jobs.
- C-01 code/test commit `b3d3cad4c93abaff3523b7f998529f4a6375c46e` passed exact-head CI [#39141823326](https://github.com/rumman52/Shuddho/actions/runs/39141823326): `test-and-build`, mandatory zero-skip `coworker`, and `ci-merge-gate`. The dedicated `c01-v3-handoff-evidence` JUnit artifact records 1 test, 0 failures, and 0 skips.
- PR #461 remains open; formal independent review, live provider quality, operated staging, production qualification, and activation remain unestablished. The repository CI result does not complete the overall Architecture/Core Agent scope.

---

## C-01 Runtime v3 grounded multi-step handoff — in progress (18 October 2026)

**Base:** `main` `ea7ad398f69e898b152f4227cb6e0c1a193999c1`. **Branch / PR:** `codex/c01-runtime-v3-adapter-e2e-20261018`, [#461](https://github.com/rumman52/Shuddho/pull/461).

**Implementation:** `test_agent_v3_deepseek_adapter_executes_grounded_multistep_workflow` uses the actual `DeepSeekAgentPlanner` adapter with deterministic `httpx.MockTransport`, the real Temporal test worker, and the existing server-owned `document.create` and `email.draft` tools. It verifies the completed document observation, exact upstream task artifact handoff, source digest/provenance, two completed receipts, completion ordering, planner/token accounting, and absence of task text or synthetic credentials from Temporal history. Handoff flags are enabled only in synthetic test settings. No production runtime, API, schema, migration, authority, or default-flag behavior changes.

**Failure correction:** run [#39126595594](https://github.com/rumman52/Shuddho/actions/runs/39126595594) exposed an assertion that incorrectly expected the original brief to be absent. A second source/schema audit found that the persisted draft stores the source digest in the manifest keyed by source ID and stores source references at `draft.source_ids`, not `draft.email.source_ids`. The assertions are corrected without weakening the acceptance criteria.

**Evidence status:** exact-head CI [#39141823326](https://github.com/rumman52/Shuddho/actions/runs/39141823326) passed all three required jobs on code/test commit `b3d3cad4c93abaff3523b7f998529f4a6375c46e`. The dedicated JUnit artifact records 1 test, 0 failures, and 0 skips. The model transport and draft model are synthetic, so this is adapter/workflow integration evidence only—not live provider quality, staging, production qualification, or activation. Independent review is not recorded.

---

## CW-02 planner retry regression follow-up — repository CI verified (18 October 2026)

PR [#456](https://github.com/rumman52/Shuddho/pull/456) merged the typed retryability propagation. The first regression assertion then failed because the run DTO retains an ordinal-zero run-created sentinel in `steps` while the executable `plan` excludes it. Follow-up PR [#457](https://github.com/rumman52/Shuddho/pull/457) corrected the assertion to require an empty executable plan, the non-executable sentinel, and zero tool invocations; its exact-head CI [#39099648984](https://github.com/rumman52/Shuddho/actions/runs/39099648984) passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate`.

This closes that repository-level regression slice only. It does not complete the CW-02 16-fault matrix, independent provider-side reconciliation, authorized staging qualification, production qualification, or activation.

---

## Runtime v3 late planner cancellation fence — 18 October 2026 (Asia/Dhaka)

**Roadmap mapping:** this is a cross-cutting correctness slice supporting the CW-06 acceptance criterion “cancellation beats delayed result.” It does **not** complete all of CW-06 and is not the roadmap's CW-02 transaction-chaos task. The branch name retains its historical `cw02` segment from the original failing-first test commit.

**Reproduction-first evidence:** the initial failing-first test commit `87a37898979455b62b248098d3c5027f3490f5cd` was based on `e52006c112c8b07623dbe1c07dc982406ce31084`, before 13 newer mainline commits. [CI run #39059380961](https://github.com/rumman52/Shuddho/actions/runs/39059380961) passed `test-and-build` but failed the mandatory `coworker` job with **2 failed, 1407 passed** in 647.14 seconds. The race test observed an `AgentDecision` persisted after cancellation; the direct memory test showed `propose_from_agent` accepted a proposal after cancellation. The `ci-merge-gate` failed because the required coworker job failed. This is the confirmed pre-fix reproduction.

**Implementation:** the candidate code/test commit `dcec2490057be63ad366a9aa4eda4c15a679a898` was rebased onto current `main` `515dbc8d842645e3b93403cbe003e707642a4955`. `AgentRepository.record_v3_decision` now checks cancellation/terminal state under the existing run-row lock after the planner-call idempotency lookup; an already-recorded decision still replays without duplication. `MemoryRepository.propose_from_agent` rejects cancelled/terminal runs under its existing run-row lock before proposal persistence. Regressions cover cancellation races, direct late proposals, non-cancelled terminal runs, and idempotent replay. Task contract: [Runtime v3 late planner cancellation](RUNTIME_V3_LATE_PLANNER_CANCELLATION_2026-10-18.md).

| Evidence level | Status |
| --- | --- |
| Implemented | Yes — source and regressions are on PR #455 |
| Repository-verified | Yes — PR #455 exact-head CI #39062674571 and merged-main CI #39063079528 passed all three required jobs |
| Staging-verified | Not established; operated CW-02 transaction-chaos and full CW-06 acceptance remain separate |
| Production-qualified | Not established |
| Activated | No |

No provider was called, no secret or protected staging environment was accessed, and no deployment or capability activation occurred. Independent review is not claimed. **Next exact action:** fix the separate CW-02 planner-retry regression assertion and obtain exact-head CI evidence, then complete the remaining CW-02 fault matrix and authorized operated cancellation/recovery qualification.

---

## CW-11 staging workflow shell-input hardening — 17 October 2026 (Asia/Dhaka)

PR [#453](https://github.com/rumman52/Shuddho/pull/453) merged as `e52006c112c8b07623dbe1c07dc982406ce31084`; its exact-head CI [#39053340279](https://github.com/rumman52/Shuddho/actions/runs/39053340279) passed all three required jobs. Final review then identified a separate security defect in the merged workflow: user-supplied old-source-revision and expected-publication-version inputs were interpolated into shell command source.

The follow-up branch `codex/cw11-staging-workflow-fail-closed-20261017` passes those values through step-scoped environment variables, quotes shell expansions, rejects non-main dispatches before staging access, validates the old revision and binds service responses to requested IDs, and adds regression tests for those boundaries. Exact-head CI for this follow-up is pending. Do not call this follow-up repository-verified until its own `test-and-build`, mandatory `coworker`, and `ci-merge-gate` pass. Staging remains unverified, no protected workflow has been dispatched, and CW-11 remains default-off.

---

## CW-11 staging workflow fail-closed hardening — 17 October 2026 (Asia/Dhaka)

**Fresh base:** `main` `e7a9f22834c8c84b5d4d2e81c33af7dc96d65f32`. PR [#452](https://github.com/rumman52/Shuddho/pull/452) is merged; merged-main [CI #39050236569](https://github.com/rumman52/Shuddho/actions/runs/39050236569) passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate`.

**Next implementation slice:** draft [PR #453](https://github.com/rumman52/Shuddho/pull/453), branch `codex/cw11-staging-workflow-fail-closed-20261017`. The staging workflow previously skipped its only evidence job when the confirmation token was wrong, potentially leaving a green run with no artifact. It also applied pending staging migrations before verifying the legacy Render service had zero instances and the candidate was running the exact qualification revision.

**Implemented:** separate no-secret confirmation job that fails on an incorrect token; evidence job depends on that success; live Render service/instance/revision validation precedes pending staging migrations; Render/database/auth credentials are injected only into the specific steps that need them; standard-library workflow-contract tests; rollout runbook and bounded task contract updated. The code change does not alter runtime authorization, provider behavior, schema, or capability flags.

| Evidence level | Status |
| --- | --- |
| Implemented | Yes — draft PR #453 |
| Repository-verified | Use the latest exact-head checks on PR #453; do not infer from the prior main run |
| Staging-verified | Not established; the protected workflow has not been run in this session |
| Production-qualified | Not established |
| Activated | No; CW-11 remains default-off |

No staging secrets were accessed, no protected workflow was dispatched, and no staging migration, deployment, publication selection or activation was performed. **Next exact action:** verify all three required CI jobs on PR #453's latest head; then an authorized operator must run the protected `CW11-STAGING` workflow with real service IDs and inspect the artifact, followed by independent operational review.

---

## CW-11 historical migration dispatch fence — 17 October 2026 (Asia/Dhaka)

**Fresh main baseline:** `main` `75521bdc77fea7366127c18ee854731880cff58b`. [PR #451](https://github.com/rumman52/Shuddho/pull/451) is merged. Its exact-head and merged-main CI runs passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate` ([PR CI #39028085374](https://github.com/rumman52/Shuddho/actions/runs/39028085374), [main CI #39030046227](https://github.com/rumman52/Shuddho/actions/runs/39030046227)). CW-11 still lacks protected staging, independent operational review, and production qualification.

**New bounded task:** [PR #452](https://github.com/rumman52/Shuddho/pull/452), branch `codex/cw11-legacy-migration-dispatch-fence-20261017`. The source change is in commit `e1768729fcb1420a3d6e95021391968b51a8c8fd`; regression cases are in `a12b65d3d627d0fde1e37053851344a48012f700` and the final test-fixture correction in `734077a899e1d84bdc79671401826140397b5a26`. Contract: [CW11_LEGACY_TASK_MIGRATION_DISPATCH_FENCE_2026-10-17.md](CW11_LEGACY_TASK_MIGRATION_DISPATCH_FENCE_2026-10-17.md).

**Gap reproduced from current source:** `migrate_legacy_reviewed_tasks()` checked only the Task phase and search-attempt record. A Task may still appear queued after its parent Temporal workflow has been dispatched, including a lost dispatch response. Rebinding that Task's workflow/publication identity in place would cross an uncertain execution boundary.

**Implemented on the review branch:** migration now requires Task state and phase to remain queued; a pristine, undispatched parent AgentOutbox; an undispatched planning-state AgentRun; a planned, never-started `research.search` step; a prepared, never-started matching invocation; no linked task resource and no ToolReceipt. Existing exact review-hash, selected-publication, grant, deadline, search-attempt and worker-drain checks remain. A single unsafe candidate aborts the whole migration transaction.

| Evidence level | Status |
| --- | --- |
| Implemented | Source and regression tests committed on PR #452 |
| Repository-verified | Pending exact-head `test-and-build`, zero-skip `coworker`, and `ci-merge-gate`; do not substitute PR #451 CI |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No; capability remains default-off |

No local test execution, independent review, protected staging run, deployment, or activation is claimed. **Next exact action:** inspect all required checks on PR #452's latest head; repair failures without weakening safety assertions, then obtain independent review. The outbox fence proves a repository pre-dispatch condition only; it does not certify live fleet drain, mixed-version Temporal recovery, or production rollout.

---

## CW-11 follow-up — selection and staging claim accounting — 17 October 2026

Parent [PR #450](https://github.com/rumman52/Shuddho/pull/450) merged as `bd4fc89b0d3d43f529a4014fa6c442f4442c726c`. Exact merged-main `test-and-build` passed; mandatory `coworker` and `ci-merge-gate` were still running at checkpoint. The automated independent review could not run because the configured review service reported its usage limit.

**Gap found after merge:** the fleet compatibility check used by reviewed-skill selection/rollback and the staging evidence collector did not independently account for active claim rows on a worker whose inventory state appeared drained.

**Follow-up branch:** `codex/cw11-claim-aware-selection-evidence-20261017`.
- Lock the worker fleet first, then reject reviewed-skill selection/rollback/legacy migration if any active dispatch claim remains, even when a worker row claims to be drained.
- Make CW-11 staging evidence reject a legacy worker row with active claims, reject a missing legacy worker row, and include old-fleet claim counts in the artifact.
- Second-pass review found that a drained row from an unexpected/third source revision could still carry an active claim. Reject active claims on every row marked drained, independent of source revision, and expose the aggregate plus an explicit evidence assertion.
- Add regression tests for a legacy false-drain row, a false-drained unexpected revision, and missing legacy inventory, proving registry controls and staging evidence fail closed.

This is repository code/test work only. Protected Render staging, independent operational review, four operated coworker scenarios, production qualification, deployment, and activation remain unverified.

---

## CW-11 per-claim dispatch drain fencing — 17 October 2026 (Asia/Dhaka)

**Active branch:** `codex/cw11-per-claim-drain-fencing-20261017`, [PR #450](https://github.com/rumman52/Shuddho/pull/450), initially at `950d3be74e6bc8a31ee07ae310f675821963f7e5`. Initial exact-head CI run [#39017961482](https://github.com/rumman52/Shuddho/actions/runs/39017961482): `test-and-build` passed; mandatory `coworker` failed with 1 failed / 67 passed in the CW-11 registry suite because the new task-claim test used `reviewed_task()` without selecting a reviewed publication first. The repository correctly failed closed. A test-only correction now explicitly publishes and selects the fixture publication before creating that task; all required checks must be rerun on the resulting head. The independent Codex review could not run because the configured review service reported its usage limit. No local test execution, staging qualification, deployment, or activation is claimed.

**Failure mode closed by this slice:** an outbox could be claimed by an Agent/action dispatcher without a registered worker identity, and the worker registry could mark a worker drained while a dispatch attempt was still in flight. A worker could also claim a batch, fail on the first dispatch, and leave the rest of that batch indistinguishable from active in-flight work.

**Implementation:**
- Add migration `0062` and durable `cw_worker_claims` records for task, Agent and approved-action dispatch claims. A second-pass schema review removed a redundant ORM-only worker index; the migration/model parity regression now checks index names as well as columns.
- Make task, Agent and action outbox claims lock the registered worker first, require a fresh `running` worker on the configured queue, and create claim records atomically with outbox leases.
- Require an active durable claim at the Agent dispatch boundary, including staging/operator helper paths.
- Complete claims after each dispatch attempt returns. On a batch failure, close claims for unattempted items without acknowledging their outbox rows, preserving normal lease-based retry.
- Keep the browser-test worker lifecycle aligned with production by recording drain only after the Temporal worker context exits; make cancellation outbox coverage use a real registered worker rather than a no-identity call that always returns an empty batch.
- Make `mark_worker_drained()` refuse completion while active claims remain; expose `active_claim_count` in worker inventory and require zero claims in drain evidence.
- Add tests for Agent/action/task claim blocking, rejection of Agent dispatch without an active claim, failed-batch cleanup for unattempted items, migration/model column-and-index parity, and a PostgreSQL interleaving where a drain waits behind an uncommitted claim.

**Safety boundary:** claims have no expiry-based auto-clear. A process crash that leaves an active claim blocks drain certification until evidence-driven reconciliation. The claim ledger tracks dispatcher work; it does not replace the existing requirement to await Temporal worker shutdown before marking the process drained. No production activation, external provider mutation, deployment or protected staging run is performed by this change.

**Remaining gates:** exact-head `test-and-build`, `coworker`, and `ci-merge-gate`; independent code/security review; protected `CW11-STAGING` with real worker identities and exact-revision evidence; the four operated coworker scenarios; and separate production qualification/activation authorization.

---

## CW-11 worker-registration phantom fence — 17 October 2026 (Asia/Dhaka)

**Mainline baseline:** PR #447 is merged as `e8de414e8b98eb503700a85474190304e28e58ed`. PR #448 then merged the initial queue advisory-lock and PostgreSQL registration-trigger implementation as `6b5aa1e2743bdbbdaa7c38a55670f6d39e8043da`. Its merged-main CI run [#39008038850](https://github.com/rumman52/Shuddho/actions/runs/39008038850) has `test-and-build` green; the mandatory `coworker` job was still running at this checkpoint.

**Remaining race:** PostgreSQL row locks protect existing worker rows, not a worker inserted after the inventory query. Without queue-membership serialization, a new incompatible worker could appear between the reviewed-skill fleet snapshot and selection commit.

**Follow-up implementation on branch `codex/cw11-worker-registration-guard-followup-20261017` (PR #448 is already merged at its earlier head):**
- Add a deterministic transaction-scoped PostgreSQL advisory lock per task queue.
- Acquire it in both the fleet-compatibility snapshot and `register_worker()`, before worker-row or selection/publication work.
- Require registrations on the configured queue to match the deployment-attested runtime revision while still allowing a candidate runtime to start before the old publication is switched.
- The merged Alembic migration 0061 installs a PostgreSQL `BEFORE INSERT` trigger requiring transaction-local `shuddho.worker_source_revision` attestation. The follow-up binds that attestation to the configured runtime setting. This blocks new registrations from legacy binaries that predate the lock protocol; existing legacy rows remain available for drain checks.
- Add a SQLite contract test, a barrier-controlled PostgreSQL race test, and a PostgreSQL regression proving un-attested inserts are rejected. The mandatory CW-11 JUnit gate must collect all PostgreSQL tests with zero skips.
- No public API change, expanded grant, external action, deployment or activation. A PostgreSQL schema migration is required.

**Validation status:** the follow-up branch carries additional runtime-revision and regression-fixture hardening beyond the merged PR #448 head. Exact-head CI and independent review for this follow-up are pending. No local test execution is claimed.

**Remaining gates:** per-claim drain fencing for Agent/action outboxes; protected `CW11-STAGING` using real authorized worker identities, confirmed drain and exact-revision evidence; four operated coworker scenarios; independent operational review; and separate production qualification/activation authorization. Existing legacy processes may continue running after migration but cannot re-register if they restart; rollout/rollback must account for that availability trade-off. The intermittent parallel SQLite malformed-schema/duplicate-index symptoms also remain unexplained; a serial rerun is not root-cause evidence.


---

## CW-11 staging collector task-ledger and evidence-boundary hardening — 17 October 2026 (Asia/Dhaka)

**Base and dependency:** stacked on the exact CI-green head of [PR #444](https://github.com/rumman52/Shuddho/pull/444), `fdad69dafbd887285e93d559b2a71927ea2bbfcb`, because main still contains the pre-fix CW-11 regression until #444 is merged. Working branch: `codex/cw11-staging-collector-ledger-guard-20261017`. This follow-up does not merge or activate #444.

**Gap:** `collect_evidence()` counted only nonterminal pre-fence Tasks that already had a reviewed identity Step. It did not block an active reviewed-workflow Task missing that identity or ambiguous active legacy Agent-owned research without one. External Render JSON was validated only by `main()`, so direct callers could bypass the boundary validator. Second-pass review also found that a lost worker on an undeclared revision, a stale active worker beside a fresh candidate, or an old worker row marked `drained` without a `drained_at` timestamp could be accepted despite the rollout contract requiring explicit drain evidence.

**Implementation:** reuse `inspect_reviewed_rollback()` and fail closed on any returned blocker; include its aggregate, non-authorizing ledger result in the evidence artifact. Validate external Render payloads inside `collect_evidence()` before database reads, reject non-object/extra-field payloads and boolean-as-integer schema versions, require strict integer counts, distinct nonblank service IDs and full 40-character lowercase Git SHAs, and compare both revisions to the requested/deployment-attested values. Block lost, unknown-state and stale-heartbeat active worker records regardless of whether their revision matches the declared old revision; also require a durable `drained_at` timestamp for any old-revision worker row marked drained. Add regressions for task-ledger gaps, uncertain workers, inconsistent drain state, malformed/unverified/revision-mismatched payloads and a clean ledger. Update the rollout contract and this checkpoint.

**Validation:** source/test implementation commit `001d1b515eb3846d4002d07ee57d4b6425a3678a`, included in main-targeted [PR #446](https://github.com/rumman52/Shuddho/pull/446) head `a0bd20832a84ef86915d3d2804d8d42e214ac25c`, passed exact-head [CI run #38964001167](https://github.com/rumman52/Shuddho/actions/runs/38964001167): `test-and-build`, mandatory `coworker`, and `ci-merge-gate` all succeeded. This run includes the task-ledger, strict Render evidence, uncertain-worker and durable drain-timestamp regressions. The present checkpoint-only documentation update changes no source/test files; its PR checks may rerun automatically, but the source/test tree has passed the required suite. The prior dependency PR #444 head `fdad69dafbd887285e93d559b2a71927ea2bbfcb` also passed [run #38948849904](https://github.com/rumman52/Shuddho/actions/runs/38948849904). No local test execution is claimed. The Codex review bot reported its review usage limit and did not produce an independent review; source-level second-pass review found and fixed the uncertain-worker and inconsistent-drain-state gaps, but independent review remains open.



**Still blocked:** protected `CW11-STAGING` has not been run. It requires the protected staging environment, operator confirmation, real old/candidate Render worker service IDs, actual drain state, and an inspectable artifact bound to the exact candidate revision. No staging/production qualification, deployment or activation is claimed.

**Next:** complete independent review and the dependent PR integration sequence (#444 before #445); then run the protected staging gate only with real authorized staging inputs and inspect the uploaded evidence artifact. The task-ledger query remains a point-in-time snapshot, not a substitute for admission quiescence or whole-fleet drain.

---

## CW-11 parallel scheduler fixture correction — 17 October 2026 (Asia/Dhaka)

**Resume base:** main `272186af38965ab60e6c551e8ebce9337c6e6ae0`; open [PR #444](https://github.com/rumman52/Shuddho/pull/444) head `c99cd56c0f774beed5995a794e444b54afc42971`. This session reproduced a remaining fixture defect before repairing it: the research/document/document plan derives `[[], [1], [2]]`, while the fan-in test asserts `[[], [], [1, 2]]`. The same sequential graph prevents the restart fixture's two-branch barrier from being reached.

**Correction:** a test-only helper seeds the explicit persisted three-node DAG for the three scheduler/recovery tests. The real SQL repository, dispatcher, Temporal workflow and runtime still execute the graph. Existing plan-derivation tests remain unchanged. Reviewed research remains one call per run; no production dependency rules, authority, budgets or default-off controls are changed.

**Local evidence:** affected Temporal tests **3 passed, 25 deselected**; reviewed/research tests in `test_coworker.py` **6 passed, 81 deselected**. Full Temporal suite is running; exact amended-head CI remains required. Independent bounded review is in progress. The GitHub automated review attempt on #444 failed due to account review quota, not a demonstrated code finding. No merge/deployment/activation performed.

**Next:** verify amended #444 with all three mandatory CI jobs and review. A separate staging-collector safety patch is preserved for independent review: reuse rollback task-ledger classification and validate external evidence at the collection boundary. Real staging worker/drain/replay evidence and overall A/C/P/V qualification remain incomplete.

---

## CW-11 reviewed research parallel-test contract repair — 16 October 2026

**Live mainline truth:** `main` `272186af38965ab60e6c551e8ebce9337c6e6ae0` includes merged [PR #443](https://github.com/rumman52/Shuddho/pull/443), but both its exact-head CI [#38944172227](https://github.com/rumman52/Shuddho/actions/runs/38944172227) and merged-main CI [#38944959166](https://github.com/rumman52/Shuddho/actions/runs/38944959166) failed the mandatory `coworker` job while `test-and-build` passed. The mainline is therefore **not repository-verified**.

**Failure analysis:** The earlier Temporal failures were caused by fan-out/fan-in/restart fixtures issuing two `research.search` calls after explicitly selecting the reviewed pilot, whose accepted manifest imposes a one-call-per-Agent-run limit. A temporary attempt to route around this by honoring the mutable feature flag contradicted the registry contract: explicit publication selection remains the Agent research gate even if that flag changes, as tested by `test_selected_publication_remains_the_agent_gate_after_feature_flag_off`. That attempt also caused the current mainline registry regression. Do not weaken the one-call limit or treat flag-off as permission to downgrade selected/pinned reviewed work.

**Correction branch:** `codex/cw11-regression-ci-fixes-20261016`, corrective source/test commit `f425760326b96739067d845a7b9ac88c4476e175` before this checkpoint update. It restores the registry-authoritative admission/replay behavior, removes the contradictory test, and keeps the Temporal concurrency/recovery tests meaningful with one reviewed research task plus one independent document task. The rollback preflight still fences both legacy reviewed v1 and current reviewed v2 workflow identities. No authority, provider budget, workflow version or release flag is widened.

**Evidence:** Correction is not yet verified until exact-head `test-and-build`, mandatory no-skip `coworker`, and `ci-merge-gate` all pass on the final corrective revision. The staging workflow has not been run; its actual staging environment, Render worker IDs and operated drain evidence remain separate required inputs. No staging, production qualification or activation is claimed.

**Next:** open a corrective PR from this branch, inspect the exact final-head CI and fix any remaining failures without changing the reviewed one-call contract. Only after CI is green, continue with the protected `CW11-STAGING` operated evidence gate and verify the artifact against the exact candidate revision. Overall CW-11 remains **INCOMPLETE**.

---

## CW-11 / A-03 rollback preflight mandatory-CI repair — 16 October 2026

**Fresh failure evidence:** merged `main` `b0d6c56f81e81fef8da1cc75a0a0a215c89c992f`; exact PR-head CI [#38915877509](https://github.com/rumman52/Shuddho/actions/runs/38915877509) for #437 failed only in mandatory `coworker`: `test-and-build` passed, `coworker` failed, and `ci-merge-gate` failed. The coworker suite reported **1402 passed, 2 failed**.

**Root cause:** two deterministic fixture defects, not a production authorization defect. The research cohort test enables research but omitted the current required backend-only search-key fixture, so `Settings` validation rejected the test setup. The rollback-inventory test created the default `report_email` TaskCreate with neither notes nor a document, which the current schema correctly rejects.

**Repair branch:** `codex/cw11-rollback-preflight-ci-repair-20261016`, first repair commit `7a966660be102da4ab518154781f89b3ac66ddcf`. It supplies the repository's existing `fixture-only-search-key` convention to the research test and gives synthetic rollback tasks a fixture note. No production code, authority, provider registration, release flag or schema contract is changed. [Task contract](CW11_ROLLBACK_PREFLIGHT_CI_REPAIR_2026-10-16.md).

**Evidence state:** implemented on repair branch; focused test and exact final-head CI are pending. No staging/production qualification or activation is claimed. Next exact action: run the focused cohort-health tests, then require all three final-head CI jobs to pass before repository verification of #437 can be considered restored. Historical worker-drain/Temporal/provider staging evidence remains a separate CW-11 gate.

---

## CW-11 / A-03 historical reviewed-skill rollback task-ledger preflight — 16 October 2026

**Baseline verified at task selection:** `main` `d757d167bbb36eaea829b683714f03b37d7206d9`, merged [#435](https://github.com/rumman52/Shuddho/pull/435). [#436](https://github.com/rumman52/Shuddho/pull/436) has since been merged into `main` at `8dba11cb3d288f374be12c96410f8ee276aff67a`; this reconciliation preserves its cohort-health regression and documentation. The initial checkpoint was written before that merge. Exact review/qualification evidence remains separately gated. The merged #435 required long-running coworker jobs and P1/P2 re-review were not fully qualified at last observation. Older checkpoint sections below predate those merges.

**Isolated new work:** `codex/cw11-legacy-reviewed-rollback-preflight-20261016` introduces read-only `scripts/reviewed_skill_rollback_preflight.py` and SQL regression cases in `tests/test_cohort_health_gate.py` to count nonterminal legacy-reviewed Tasks (pinned reviewed Step without the new workflow version), active new-version Tasks missing an identity, ambiguous active legacy Agent research without a review Step, safely fenced Tasks and terminal old-reviewed Tasks. The counts run in one SQL statement snapshot; missing review Step never creates an optimistic clean result. Nonzero blocker counts return `BLOCKED_TASK_LEDGER` / failed CLI exit. A clean task-ledger snapshot is only `TASK_LEDGER_CHECK_ONLY`, with explicit false `fleet_drained_verified`, `staging_verified` and `rollout_authorized`; no mutation/provider operation or owner data disclosure. [Bounded task and operated acceptance contract](CW11_LEGACY_REVIEWED_ROLLBACK_PREFLIGHT_2026-10-16.md). Exact final-head CI and independent review are pending, so this is **implemented on branch, not repository/staging verified**.

**Open P1 and next action:** A historic nonterminal Task admitted under #434 as `work_research_v1` plus reviewed Step can still execute on pre-#435 older workers. An isolated DB inventory cannot prove that all older API/Temporal/worker processes have drained or all in-flight provider operations are reconciled. Preserve default-off policy; perform a controlled real deployment drain, worker-version inventory, historical-work reconciliation and matching staging/replay proof before closing A-03/C-05 or activating the pilot. Trusted skill publication/version selection, cross-purpose coworker scenarios and CW-09/CW-10 operated tests remain separate obligations.

**Evidence and authority:** Source/docs/test commits only; no merge, deploy, provider charge, purchase or activation. No completion percentage claimed. Next exact checks: `uv run --extra coworker pytest tests/test_cohort_health_gate.py -k reviewed_skill_rollback -q` and all three required exact-head CI jobs with review findings resolved.

---

## CW-11 old-worker fence merged; cohort metric and rollout contract follow-up — 16 October 2026

**Current merged implementation baseline:** `main` `d757d167bbb36eaea829b683714f03b37d7206d9`, externally merged [PR #435](https://github.com/rumman52/Shuddho/pull/435) at last observed PR head `62665ecedeae26b4d1e7a541b41601dac1070fc9`. The merged patch gives *newly admitted* reviewed research Tasks distinct `work_research_reviewed_v1` workflow identity, which older `work_research_v1` workers fail to resolve and whose old paid-search reservation rejects. Current worker/runner maps this reviewed workflow to the existing source-reviewed WorkSkill; SQL pinned Step, grants and exact sources are still rechecked. Terminal reviewed Task idempotent replay is retained. No capability activation, external sends, or deployment is established.

**Evidence:** Last observed exact-head [PR #435 CI #38911379269](https://github.com/rumman52/Shuddho/actions/runs/38911379269): `test-and-build` passed, mandatory `coworker` in progress, dependent merge gate pending. Merged-main [CI #38911480448](https://github.com/rumman52/Shuddho/actions/runs/38911480448) also pending. The first independent review recorded P1 older-worker downgrade and P2 terminal replay; amended source addresses new Tasks and terminal replay, but the final re-review attempt failed to produce clean clearance and threads remained unresolved at observation. Do not treat merge as security qualification.

**Follow-up review branch:** `codex/cw11-reviewed-rollout-evidence-followup-20261016` updates the canonical rollback contract for the distinct task workflow and modifies `scripts/cohort_health_gate.py` to include `work_research_reviewed_v1` failures and samples in release stop-gate metrics. Adds a synthetic-cohort regression proving a failed reviewed Task raises the research failure rate and STOP_ROLLOUT. This evidence slice awaits final-HEAD mandatory CI and independent review and is **not merged**.

**Outstanding P1 rollout boundary:** Already admitted research Tasks from merged #434 may retain **legacy** `work_research_v1` with `reviewed_skill_identity`. An actually older worker ignoring that Step could still execute it after flag rollback. The new version fence protects **new** admissions, not historical in-flight ones. Block mixed-version activation until old workers are drained and a controlled, owned existing-task inventory/backfill/recovery plan is operated and verified with PostgreSQL, Temporal, and real provider-dispatch boundaries. Never silently retype a running task or declare old-worker coexistence safe. Trusted skill publication, version/revision rollback, CW-09/CW-10 operated isolation, P-01/P-03 scenarios and V staging/production qualification remain separate unmet gates.

**Next:** Inspect exact merged-main and follow-up PR CI; finish independent security review with old-worker/historical Task risk explicitly scoped. Prove a safe staged upgrade/drain/backfill and mixed-version compatibility contract before activating reviewed research. No automatic merge, deploy or activation.

---

## CW-11 persisted reviewed-skill rollback guard — 16 October 2026

**Refreshed baseline:** `main` `c4d047dc9ede00b3caac81239621f3dcca28d6ab` includes externally merged [PR #434](https://github.com/rumman52/Shuddho/pull/434), exact final PR head `c03406e5d84a5f3af500fa3a59556ecbf5d9ed0d`. Matching [PR-head mandatory CI #38904915894](https://github.com/rumman52/Shuddho/actions/runs/38904915894) passed `test-and-build`, `coworker` and `ci-merge-gate`. Merged-main [CI #38908427544](https://github.com/rumman52/Shuddho/actions/runs/38908427544) was **running** at first refresh. The original three P1 review threads on #434 remain **unresolved**, and repeat Codex reviews failed operationally; source/CI success is not independent security review clearance. Older #434 unmerged/pending status immediately below is historical.

**Next safety slice on isolated review branch:** `codex/cw11-reviewed-skill-rollback-boundary-20261016`. The merged reviewed research pilot persisted a Task-scoped reviewed manifest digest, but its worker read, Task replay and search credit reservation were gated solely by the live `SHUDDHO_AGENT_REVIEWED_RESEARCH_SKILL_ENABLED` flag. Disabling this flag post-admission could silently demote pinned Tasks to the unreviewed legacy path. New code independently checks the existing `reviewed_skill_identity` Step even when the flag is off, denying previously pinned Tasks at all three boundaries without new provider work. A synthetic SQL regression checks same Task across disable and re-enable, no search reservation after disable, and standalone legacy compatibility. [Task contract](CW11_REVIEWED_SKILL_FLAG_ROLLBACK_GUARD_2026-10-16.md).

**Evidence state:** Committed source/regression and task contract; exact final-head CI/reviewer evidence **not yet confirmed** at this checkpoint. This closes neither true mixed-version rollout safety (older workers remain unsafe) nor trusted publication/version selection/rollback, operated worker/PG/Temporal staging, or A/P/V full acceptance. Code is default-off; no merge/deploy/provider send/activation performed here.

**Next:** Inspect final-head mandatory CI and independent review; fix any failed denial/cleanup assertions; maintain old-worker downgrade as a rollout blocker. Then move to trusted reviewed skill publication/selection and operated version-replay acceptance.

---

## CW-11 / C-05 reviewed research worker binding — 16 October 2026

**Live baseline:** `main` `d4fccefdced8a68e8fb839525141d9796a6f4dac`. [PR #433](https://github.com/rumman52/Shuddho/pull/433) was merged externally; exact [PR-head CI #38877447028](https://github.com/rumman52/Shuddho/actions/runs/38877447028) passed `test-and-build`, `coworker` and `ci-merge-gate`; Codex review completed with no findings. Earlier checkpoint calling #433 open and pending is now historical.

**Separate unmerged implementation:** `codex/cw11-reviewed-research-worker-binding-20261016`, a bounded *default-off* Agent-owned `research.search` pilot. Existing inert reviewed `CoworkerSkillManifest` is now consumed at SQL-backed task creation, worker phase read and paid research reservation, checking exact owner/run/step/tool, pinned Task workflow/ToolSpec and newly persisted Task review SHA identity, explicit durable run grant, exact query/inputs, immutable selected DocumentVersion subset of the owning AgentRun, one-call ceiling, cancellation and live manifest/source policy. The parent AgentRun lock serializes a revocation against the search credit reservation. Standalone research remains unchanged; no new provider authority, runtime skill publishing, migration, action ledger or production rollout. Adds SQL regression tests including denial of grants/versions/owner/inputs and review drift. Independent Codex review of initial SHA `a263313` raised three P1 findings: public key replay collision, unexpired-state vs actual run deadline, and stale grant before research dispatch. Follow-up commits now check owner/run/step on replay with fresh reviewed validation, reject past-deadline runs, gate the credit reservation under AgentRun/Task locks, and recheck before provider invocation with a zero-credit settlement on denial. **The fixes still require exact-head CI and fresh independent re-review; original threads remain open.** [Task contract](CW11_REVIEWED_RESEARCH_WORKER_BINDING_2026-10-16.md).

**Evidence:** Source/tests committed to review branch; focused local checks and exact final-HEAD CI are **not yet confirmed** at this checkpoint. Independent review and operated PG/Temporal/staging remain pending. This is a real but incomplete step toward C-05, **not reviewed skill publication/rollback or production qualification**.

**Next:** Open/review independent draft PR; inspect final-head `test-and-build`, mandatory no-skip `coworker`, `ci-merge-gate`; fix actual failures and review findings. Then implement trusted publication/version rollback and later operated worker proof. No merge, deploy, model/provider spend or activation.

---

## CW-11 restricted planner attached-action review repair — 16 October 2026

**Live baseline:** `main` `41f457b04f2b1e466cbaafd7bbfff04cc5993186` includes merged [PR #432](https://github.com/rumman52/Shuddho/pull/432). Its exact-head [CI #38861042441](https://github.com/rumman52/Shuddho/actions/runs/38861042441) passed `test-and-build`, `coworker` and `ci-merge-gate`. Merged-main [CI #38876797929](https://github.com/rumman52/Shuddho/actions/runs/38876797929) was still in progress at this checkpoint. [Codex review thread on #432](https://github.com/rumman52/Shuddho/pull/432#discussion_r4291573554) identified an unresolved authorized-attached-action regression despite green CI.

**Review branch:** `codex/cw11-attached-action-scope-repair-20261016`. Ordinary tool suggestions remain filtered by the persisted run grant, but independently run-bound pending `attached.*` handles are no longer removed whenever that grant is nonempty. Added synthetic/SQL-backed action selection, opaque-handle, selected-vs-unselected release, and replan-after-renumbering regression assertions in `tests/test_coworker.py`. No additional provider authority, release flag, production operation or schema change. [Task contract](CW11_ATTACHED_ACTION_SCOPE_REPAIR_2026-10-16.md).

**Evidence:** Source and tests committed on dedicated branch; focused command and exact *final branch-head* required CI **not yet observed passing** when this checkpoint was written. Review feedback needs re-verification against the new diff. **Implemented on review branch; repository verification pending; staging, production qualification and activation not established.**

**Next:** Review the focused test and final-head `test-and-build`, `coworker`, `ci-merge-gate` results; repair failures rather than muting the check. Then proceed to CW-11 reviewed, grant/version-bound skill publication and rollback, with separate real worker/browser, cross-purpose and staging acceptance gates. No merge, deploy, activation, or external action authorized.

---

## CW-11 post-merge planner and fallback tool scope — 16 October 2026

**Live source:** [PR #431](https://github.com/rumman52/Shuddho/pull/431) merged at `main` `18068a48aae1dcd3f354638e525cdd2cf88fc185` (16 October 2026). Its earlier exact PR head was `b062f487ba2aa0de11fb367424c70d9eb9ce01cc`. Merged-main `CI #38860546551` was in progress at this review. Historical branch/open notes below predate the merge.

**Independent continuation branch:** `codex/cw11-planner-scope-continuation-20261016`. The merged worker-admission guard is insufficient alone: the initial intelligent planner and replan offered tool names without filtering the run's durable `tool_allowlist`; deterministic fallback and model proposal conversion also omitted it. This branch passes the persisted scope through all these routes and adds real repository regressions for restricted initial plan, replan, fallback and no-eligible-tool denial. The follow-up diff is **not merged** and neither exact final CI nor staging evidence is claimed. No model can grant extra tools via this change.

**Next:** create/review separate draft PR, inspect exact-head CI, resolve test/review findings and keep capability gates disabled. Full CW-11 reviewed skill publication and runtime version selection, CW-10 real worker isolation, CW-09 browser network proof, and broader A/P/V scenarios remain independently incomplete. [Acceptance details](CW11_RUNTIME_TASK_SCOPE_HARDENING_2026-10-16.md).

---

## CW-11 / A-04 restricted-run task scope at worker claim — 16 October 2026

**Refreshed default branch:** `main` `9b9e23a182ec212ce7f30e87d7a235ba886c2f5f`, with #430 merged and exact merged-main CI #38858449740 still in progress at first inspection; no open PRs were observed. Older 15 October recovery-claim CI checkpoint is superseded.

**New bounded security slice:** `codex/cw11-task-run-scope-claim-20261016` prevents any tool outside a stored nonempty Agent run `tool_allowlist` from being admitted by `save_plan`, `replace_remaining_plan` or `AgentRuntime.execute_step`. Additionally, initial intelligent planning, replanning and deterministic fallback now consume the exact stored scope so an unauthorized tool is not offered to the model and a valid restricted fallback can complete. All non-approved-action tools (including browser/sandbox) are restricted by this field; attached consequential actions retain their existing ExternalAction approval checks. Targeted SQL repository tests reject task/browser admission, simulate an altered persisted browser invocation and check no new Task/session is created; a separate regression covers initial model tool enumeration, replan and constrained fallback.

**Evidence state:** changes committed on a review branch; targeted test, exact-final-HEAD mandatory CI, independent review, PostgreSQL/Temporal racing worker replay and staging were **not yet verified** at checkpoint drafting. This narrows the authority gap but **does not** complete CW-11 publication or activation, CW-10 operated sandbox, CW-09 browser, A/P/V qualification. [Task acceptance](CW11_RUNTIME_TASK_SCOPE_HARDENING_2026-10-16.md).

**Next:** open review PR, inspect required final-head CI and review, fix failures without weakening scope. After review, implement independently version-pinned approved skill publication and runtime grants; no automatic merge, deployment or activation.

---

## CW-10 generated model source → worker revocation integration regression — 16 October 2026

**Verified baseline:** `main` `4b456bf41ad324d79e142c3dd39e4a49e9e2a612` contains merged #429 bounded owner DeepSeek model drafts. Its exact-head [PR CI #38852014466](https://github.com/rumman52/Shuddho/actions/runs/38852014466) and merged-main [CI #38852778094](https://github.com/rumman52/Shuddho/actions/runs/38852778094) passed all three required jobs; no open PRs at task selection.

**New test-only work:** isolated branch `codex/cw10-model-review-worker-revocation-e2e-20261016` adds full bounded synthetic acceptance from mocked DeepSeek output to authenticated model draft, immutable owner review SHA, atomic single sandbox dispatch, one authorized worker claim, and success/retry identity, plus an adversarial revocation *after claim*. The latter drives real owner revoke and SQL `worker_control` through the actual `scripts/sandbox_worker.py::execute_claim` loop, using simulated `Popen`. It asserts process kill request, refusal to send completion, destruction of temporary Python source paths, cleared SQL proposal and execution source, revoked lease and blocked late result/retry. [Acceptance and environment limits](CW10_GENERATED_WORKER_REVOCATION_E2E_2026-10-16.md).

**Verification:** tests and contract committed but final-head no-skip `test-and-build`, `coworker`, `ci-merge-gate` are pending. The process is synthetic, not operated `bwrap`; real kernel no-egress, PostgreSQL concurrent retries, Temporal restart, actual OS kill, in-memory wipe, real model/provider quality and independent security reviewer remain unverified. No product authority or deployment settings change; CW-10 remains **default-off, INCOMPLETE**.

**Next:** address CI errors on exact final branch SHA; then operated reviewed-source real bubblewrap/PG kill + cleanup, and CW-11 reviewed skills / CW-09 browser / P/V coworker scenario obligations.

---

## CW-10 owner-invoked model Python producer — 16 October 2026

**Source truth at task start:** `main` `08512aba78d5446c8115adbeafeded8a9e4f33cd` includes merged [PR #428](https://github.com/rumman52/Shuddho/pull/428). Its exact final-head [CI #38848800194](https://github.com/rumman52/Shuddho/actions/runs/38848800194) passed `test-and-build`, `coworker`, `ci-merge-gate`. New merged-main CI #38850518005 was in progress at start. No open PRs.

**First dependency-ready gap C-04:** An authenticated owner could inspect/approve manually submitted Python but could not request an actually model-generated source draft. The new branch `codex/cw10-owner-model-code-producer-20261016` adds an independent default-off `SHUDDHO_MODEL_CODE_PROPOSALS_ENABLED` flag; an explicit owner-only model-draft API and Agent review UI button; strict DeepSeek JSON→validated Python with no tool or execution grant; pre-provider owner/private-context checks, ordinary planner reservation/settlement, and immutable SHA-bound post-inference code proposal persistence. Exact-key replays return stored source without another model call; cancellation between inference and persistence fails closed. No private-input mounts, network or destinations. User-supplied HTTP proposals cannot forge the reserved model-origin idempotency namespace. [Detailed contract](CW10_MODEL_CODE_DRAFT_PRODUCER_2026-10-16.md).

**New tests:** disabled-before-provider, no cross-account or selected private-source generation, one-key replay, no sandbox execution, cancellation during inference, invalid provider output, provenance spoof rejection, typed frontend direct request without execution paths. **Not verified until exact final-head CI passes.** The provider is mocked in CI, no real paid DeepSeek performance or operated deployment proof. No merge, deploy or activation.

**Next:** confirm mandatory `test-and-build`, `coworker`, `ci-merge-gate` on final SHA and repair red checks. Then qualify human-approved model source → sandbox worker in synthetic PostgreSQL concurrency/real bwrap/revocation/crash experiments, in-flight filesystem erasure, and durable recovery. CW-11 reviewed skills, CW-09 operated browser and P/V scenarios remain separate. **INCOMPLETE**.

---

## CW-10 atomic reviewed-owner dispatch — 16 October 2026

**Verified starting state:** `main` `8d9420e5ebc38e7c188dc8bf1e4cb19873190a90`; merged #427 added exact owner Python review UI. Its [PR CI #38845738704](https://github.com/rumman52/Shuddho/actions/runs/38845738704) and merged-main [CI #38845856137](https://github.com/rumman52/Shuddho/actions/runs/38845856137) both passed all three required jobs. No open PRs before this branch.

**New source changes** on `codex/cw10-reviewed-dispatch-atomic-20261016`: independent default-off `SHUDDHO_CODE_PROPOSAL_DISPATCH_ENABLED`; authenticated exact-hash dispatch endpoint; `SandboxRepository.dispatch_reviewed_proposal` locks owner run → stored proposal → owner human approval, verifies admitted source, live expiry/permission/cancellation/limits, rejects unsupported private inputs, and creates one new session and its proposal-FK-linked prepared execution in one SQL transaction. Unique FK and run lock give duplicate POST one durable identity. Worker claim uses the same source/review guard and denies linked claims if the new gate is disabled. Added HTTP and worker negative/replay regressions. Existing direct-user sandbox path is unchanged, generated-code UI still has no execution control. [Detailed contract and rollout blockers](CW10_ATOMIC_REVIEWED_DISPATCH_2026-10-16.md).

**Evidence required:** final-head mandatory `test-and-build`/`coworker`/`ci-merge-gate`, independent security review, operated PostgreSQL concurrency/worker revocation/staging bwrap isolation. **Source erasure improvement:** queued reviewed execution stores a source reference, not a duplicate Python snapshot; revocation clears the original proposal snapshot before claim, and claim fails closed. Still unverified: source already released to worker memory, process cancellation latency, temporary file erasure, old legacy manually linked rows and operated isolation. Old workers do not know this gate: mixed-version dispatch forbidden. No deployment/activation or production qualification.

**Next:** prove actual worker process cancellation and in-memory/filesystem erasure after revocation; implement trusted model code proposal producer and qualify live full end-to-end CW-10 lifecycle. CW-11 skills, CW-09 operated browser and P/V coworker scenarios remain incomplete. Overall **INCOMPLETE**.

---

## CW-10 exact owner code inspection UI — 16 October 2026

**Current baseline:** `main` `d9d664c8b5a735260a17c1af58687e14e2b8c058` contains merged [PR #426](https://github.com/rumman52/Shuddho/pull/426), whose exact-head [CI #38843127126](https://github.com/rumman52/Shuddho/actions/runs/38843127126) passed all three mandatory jobs. The subsequent `main` push [CI #38844772799](https://github.com/rumman52/Shuddho/actions/runs/38844772799) was still in progress at task selection. No open PRs at bootstrap.

**First unresolved C-04 user-facing path:** Inert code proposals and owner human decisions exist in SQL, with secure claim checks behind default-off flags, but the actual coworker UI could neither discover nor inspect the full source/limits/destinations before review. Branch `codex/cw10-owner-code-inspection-20261016` adds a bounded, authenticated and no-store metadata-only code proposal list revalidated against live run/context scope, a typed exact owner review client, and a run-keyed React inspection panel displaying untrusted full source, digest, input SHA, compute limits, no egress and expiry. A checkbox confirms actual inspection before the existing exact-hash human decision. Reject/revoke erase the private bytes; owner review never creates a sandbox execution or grants credentials. Tests cover no-source metadata, cross-owner denial, stale/tampered/revoked source, typed exact API transport and absent execution path. [Acceptance contract](CW10_OWNER_CODE_REVIEW_UI_2026-10-16.md).

**Evidence:** Code and tests committed on review branch. This slice is not qualified until final HEAD `test-and-build` (including UI tests), zero-skip `coworker`, and `ci-merge-gate` pass. Browser rendering, staging and independent security review unverified. **No merge, deploy or activation.**

**Next:** trusted model-generated code proposal producer and explicit secure owner notification; then atomic server-side binding/dispatch of exactly one reviewed proposal into SQL-owned sandbox execution, with mixed-version worker safety and operated bubblewrap/PG/Temporal recovery. CW-11 skills and operated CW-09/P/V remain separate.

---

## Mandatory CI recovery — Alembic 0058 SQLite FK compatibility — 16 October 2026

**Current mainline truth:** `main` `e495a202720de658ef98cf55a21f3032ef4f1f12` has merged [PR #425](https://github.com/rumman52/Shuddho/pull/425), but **its final-head [PR CI #38838451837](https://github.com/rumman52/Shuddho/actions/runs/38838451837) and merged-main [CI #38842070652](https://github.com/rumman52/Shuddho/actions/runs/38842070652) both failed** mandatory `coworker` while `test-and-build` passed. Inspect log `coworker` step "Run mandatory transaction safety regressions without skips": seven transaction regression fixtures could not migrate new SQLite databases. The blocking traceback is `services/coworker/migrations/versions/0058_sandbox_code_proposal_binding.py:16`, `NotImplementedError: No support for ALTER of constraints in SQLite dialect` when adding the new `agent_code_proposal_id` foreign key. This is a failed **migration setup**, not a demonstrated transaction invariant failure. The merge did not satisfy the required final-head acceptance gate.

**Isolated CI safety repair:** branch `codex/cw10-0058-sqlite-fk-migration-ci-20261016` forked from exact main `e495a202720de658ef98cf55a21f3032ef4f1f12`. Migration 0058 now uses `op.batch_alter_table` for FK column addition and downgrade, following existing portable migration patterns 0032/0039; the original PostgreSQL non-null-safe nullable FK and **unique non-null index are retained**. Dedicated regression inspects SQLite migration metadata to require actual FK to `cw_agent_code_proposals.id` and unique claim origin index; transaction mandatory regressions are not skipped or weakened.

**Evidence pending:** Exact final repair-branch SHA `test-and-build`, no-skip `coworker` including transaction safety suite and PostgreSQL/Temporal, and `ci-merge-gate` must pass. Independent review and operated staging remain unproven. Keep draft. **No merge/deploy/activation authorized.**

**Next once green:** Continue CW-10 trusted generated-code producer + owner review UI and safe server dispatch, without allowing a model to self-grant authority; require real worker isolation/restart evidence. CW-11 reviewed skill activation and browser/P/V scenarios remain independently incomplete.

---

## CW-10 reviewed generated-code worker-claim guard — 16 October 2026

**Refreshed truth:** `main` `35287ac3ab0e2c691d76b2a1973166342c5ccf06`; [PR #424](https://github.com/rumman52/Shuddho/pull/424) merged at this SHA and its exact-head [PR CI #38792431386](https://github.com/rumman52/Shuddho/actions/runs/38792431386) passed. Merged-main [CI #38837201149](https://github.com/rumman52/Shuddho/actions/runs/38837201149) was still in progress when the branch was opened. No open PRs at that initial refresh. The original document's old red CI and earlier draft reviews have since been superseded by merged fixes.

**Missing real authority boundary:** The sandbox worker's claim/heartbeat/result path currently guards source integrity, lease and environment but never binds a model-generated proposal to its recorded owner decision. An `approve` record is inert; treating it as sufficient would bypass current source scope, budgets and revocation. This independent branch `codex/cw10-reviewed-sandbox-claim-guard-20261016` starts from the exact `main` above and adds nullable SQL-owned `agent_code_proposal_id` FK via migration `0058`. The current direct-user Python execution API never sets it.

**Implemented on review branch:** Source-origin-bound reviewer validation at claim, heartbeat and receipt acceptance. Under SQL locks, only an exact owned unexpired/unrevoked approved proposal with current live run+conversation/source permissions, hash and reviewed limits may release bytes or settle; all unsafe claims fail closed and scrub source. Private input versions are explicitly denied pending an operated reviewed input-mount path. Changed reviewer/submitted hash, source tampering, revoked/expired consent, cancelled run and excess resource ceilings are tested; direct-user executions are unaffected. [Acceptance/rollout contract](CW10_SANDBOX_REVIEW_CLAIM_GUARD_2026-10-16.md).

**Evidence:** Source and synthetic tests committed, required final-head no-skip `test-and-build`/`coworker`/`ci-merge-gate` still pending; real PostgreSQL migration test added. No independent security review or operated staging worker process evidence. Do not merge, deploy, or activate.

**Remaining:** CW-10 trusted model proposal producer and trusted owner-review UI; atomic privileged server-side producer/dispatch path that sets proposal binding; reviewed private-input mounts and isolation/rollback; CW-11 skill publication; operated CW-09 browser network security; P/V goal/work/recovery/security scenarios. Core/architecture qualification remains **INCOMPLETE**.

---

## CW-10 exact owner human review decision, no worker authority — 16 October 2026

**Fresh repo:** `main` `a8b60903268f4be4655fd8191305bc35c739a9bd`; [PR #423](https://github.com/rumman52/Shuddho/pull/423) has merged private code revocation/expiry/account erasure, but its exact-head [PR CI #38789767003](https://github.com/rumman52/Shuddho/actions/runs/38789767003) and merged-main [CI #38790723827](https://github.com/rumman52/Shuddho/actions/runs/38790723827) were **still running**, and therefore not qualified at this initial inspection. Older green jobs do not close the new revision. No other open PR was present.

**New C-04 review-only slice:** `codex/cw10-exact-human-review-decision-20261016` based on this exact main. New additive migration `0057` stores one `AgentCodeReview` per private proposal (owner/run/whole-envelope hash, approve/reject, server decision time, bounded owner expiry, revocation). Owner-authenticated `POST .../code-proposals/{proposal_id}/review` checks exact hash, original selected owned scope, active runtime-v3 run and current limits for an approve; rejection scrubs source. Concurrent approval/revocation use shared run+row lock and one-decision PK. Replay of identical decisions is stable, changed decisions conflict. Existing revocation, expired maintenance and account deletion now handle review records. No schema/runtime activation or worker code-execution permission, with `execution_authorized=false` and `code_executed=false` in all review responses. New API/DB and PostgreSQL FK tests provided. [Acceptance contract](CW10_HUMAN_REVIEW_DECISION_2026-10-16.md).

**Verification status:** Source committed on review branch, exact final-head mandatory `test-and-build`/`coworker`/`ci-merge-gate` still required; independent review and operated worker/staging unverified. Do not merge, deploy or activate.

**Next:** Finish trusted model-generated proposal producer and inspected owner UI, then a **separate** security slice atomically validates this reviewed identity against source/input/limits/run/worker lease at sandbox claim. Unconsumed human decision is not execution authority. CW-11 reviewed skills, operated browser isolation and P/V realistic scenarios remain incomplete.

---

## CW-10 inert proposal owner revocation and private source retention — 16 October 2026

**Repo truth:** `main` `0c292f635cc27515c12a5ae0158dc8db3c222c1f`, merged [PR #420](https://github.com/rumman52/Shuddho/pull/420) (inert proposal persistence), [PR #421](https://github.com/rumman52/Shuddho/pull/421) (admitted conversation source scope), and [PR #422](https://github.com/rumman52/Shuddho/pull/422) (real direct-chat test). These are already merged, not unfinished tasks. Main push [CI #38788446857](https://github.com/rumman52/Shuddho/actions/runs/38788446857) was in progress when this new branch was created.

**Safety/data-integrity gap:** `AgentCodeProposal.snapshot` retains untrusted private Python indefinitely after proposal expiry, has no owner revocation path, and `RetentionService.erase_account` did not remove proposal rows before the parent AgentRun. The latter violates the schema's foreign key and blocks full account erasure with code proposals present. No generated-code execution authority exists yet.

**Isolated implementation:** branch `codex/cw10-proposal-revocation-erasure-20261016` forked from that exact main. New owner-authenticated exact-review-hash `POST .../code-proposals/{proposal_id}/revoke` atomically scrubs source and leaves a non-executing tombstone; repeat revocations are idempotent, cross-owner/wrong hash fail closed, and GET/POST replay cannot disclose/resurrect erased code. Bounded expiry retention is wired into the existing five-minute worker maintenance pass. Account erasure now removes proposals before runs. Regression tests cover wrong owner/hash/run, cancelled run, expiry, idempotency and account FK deletion. No new permissions, model decisions, approval fields, schema migration or sandbox execution. [Task contract](CW10_PROPOSAL_REVOCATION_ERASURE_2026-10-16.md).

**Evidence:** Code and tests committed, final-head `test-and-build`, mandatory no-skip `coworker`, `ci-merge-gate` and independent review pending at this checkpoint. No direct local PostgreSQL/Temporal or operated worker/staging evidence. Keep default-off, draft and do not auto-merge/activate.

**Next:** Obtain exact-HEAD CI and independent security/retention review. Then complete trusted model proposal admission, explicit human decision with expiry/revocation and atomic worker-claim validation. CW-11 reviewed skill publication and remaining operated CW-09/P/V scenarios remain independently incomplete.

---

## CW-10 conversation-bound code proposal scope — 16 October 2026 (Asia/Dhaka)

**Refreshed main:** `badc8bbb66c8ead4a43c3463e32112b1bfd7e996`, merged [PR #420](https://github.com/rumman52/Shuddho/pull/420). Exact #420 PR head `f1ddb5d45c0b62f70f95c84db00374541621f420` passed required `test-and-build`, `coworker`, and `ci-merge-gate` in [CI #38780057144](https://github.com/rumman52/Shuddho/actions/runs/38780057144). Main push [CI #38783568443](https://github.com/rumman52/Shuddho/actions/runs/38783568443) was still running at this bootstrap. No open PRs were returned. The older document's `baa484e` red recovery-claim checkpoint is historical; do not repeat its repair.

**Bounded safety defect and fix:** Code-proposal creation/replay/GET checked current document rows but omitted CW-08's original conversation message/source/run validation. A same-ID document version change, removed source selection/run link, unavailable conversation or moved message still returned private source/accepted new snapshots. A new proposal could adopt substituted live source hashes. Reuse `require_admitted_conversation_run_sources` in the existing shared `_verify_code_proposal` path, preserving non-conversation semantics. This is an inert proposal scope correction, with no new authority or schema.

**Branch/contract:** `codex/cw10-conversation-proposal-scope-20261016`; [task contract](CW10_CONVERSATION_PROPOSAL_SCOPE_2026-10-16.md). Baseline focused suite **29 passed**. Final failing-first matrix **16 failed for successful HTTP 201/200 instead of 409** before the repair. An initial broader run had three invalid composite-owner fixture mutations; the fixture now moves the message and owner together into a real foreign conversation, preserving database constraints, and all sixteen were rerun against the pre-fix code. JavaScript tests and workspace build passed. Affected proposal/conversation/sandbox suite **164 passed, zero skips**, with six pre-existing adversarial-model Pydantic serializer warnings (63.00s). Full Python and exact new PR-head CI pending at this checkpoint.

**Evidence/authority:** Source repair local, remote review pending; required exact-head mandatory CI, independent security review, staged PostgreSQL/Temporal/sandbox and production qualification are not inferred. Flags remain unchanged/default-off. No deployment, merge, human approval, code execution or external transaction was performed. Review is a local second pass, not independent.

**Remaining work:** C-04's model-authored proposal admission/trusted review UI, persisted exact owner decision with expiry/revocation, and atomic approved sandbox claim remain incomplete; retain that dependent lifecycle as the next engineering task after this scope repair is reviewed/integrated. CW-11 trusted skill publication and operated C-02/P/V scenarios remain independent. Missing staging identity/credentials, real sandbox/container services and human quality/security evidence are external blockers, not completed checks. Current local environment has neither PostgreSQL nor Docker executable; mandatory remote CI must supply their required evidence.

---

## CW-10 proposal persistence CI repair and mainline integration — 15 October 2026

**Fresh main:** `be78fe057bce6d6d09271d1e0fb135b4b422bd74`; [PR #418](https://github.com/rumman52/Shuddho/pull/418) merged after final PR-head [CI #38775100942](https://github.com/rumman52/Shuddho/actions/runs/38775100942) passed `test-and-build`, mandatory `coworker` and `ci-merge-gate`. The original [PR #419](https://github.com/rumman52/Shuddho/pull/419) was not mergeable after #418 and [CI #38777496427](https://github.com/rumman52/Shuddho/actions/runs/38777496427) failed seven stored-code-proposal assertions, leaving mandatory `coworker` and merge gate red; `test-and-build` passed.

**Cause, repair, new branch:** The strict immutable reviewer accepts standard `datetime.timezone`/`ZoneInfo` values but API/JSON Pydantic parsing generates `pydantic_core.TzInfo`. Valid code proposals were rejected as `code_proposal_invalid`. A narrow `canonicalize_transport_code_proposal` converts this exact trusted parser timezone to a standard immutable timezone before **unchanged** review validation for POST, replay and stored GET. The normalization preserves JSON review identity, malicious extra fields and validator rejection; focused Pydantic-only local reproduction confirmed parser types and copied-field preservation. The replacement branch `codex/cw10-proposal-persistence-ci-repair-main-20261015` ports the entire owner-scoped inert proposal model, additive migration `0056`, API, PostgreSQL race tests, no-skip CI and all regressions onto the merged mainline. No human approval or worker-execution grant exists.

**Evidence:** Source patches and tests committed, but required exact-head `test-and-build`, `coworker`, `ci-merge-gate`, independent security/migration review and operated sandbox proof remain **unverified**. Full local repo tests unavailable because local GitHub clone/network access failed. Do not merge/deploy/activate. Next C-04: persist owner approval with expiry/revocation and enforce exact source/input/limits binding atomically at sandbox claim; CW-11 and P/V scenarios remain independent.

---

## CW-10 fail-closed sandbox heartbeat — actual mainline integration — 15 October 2026

**Fresh repo truth:** `main` `ce76803eb20e8383bb507f02e2cad17d9ff77d3f` contains [PR #416](https://github.com/rumman52/Shuddho/pull/416), whose exact [PR CI #38770425863](https://github.com/rumman52/Shuddho/actions/runs/38770425863) passed all three mandatory jobs. [PR #417](https://github.com/rumman52/Shuddho/pull/417) was marked merged into the earlier review branch, not `main`, and `main:scripts/sandbox_worker.py` still had the unguarded worker heartbeat behavior. #417's own earlier CI cannot qualify a new mainline integration.

**Source repair branch:** `codex/cw10-sandbox-heartbeat-mainline-20261015` created from that exact `main`. Ports the previously reviewed bounded `scripts/sandbox_worker.py` heartbeat fail-closed change and the associated negative/positive `tests/test_sandbox_control_plane.py` cases. Any control heartbeat error, unexpected/missing action or explicit `stop` terminates the subprocess; only explicit `continue` allows it to proceed. Keep default-off sandbox and deny model-created authorization. [Integration contract](CW10_SANDBOX_HEARTBEAT_MAINLINE_INTEGRATION_2026-10-15.md).

**Verification:** GitHub source commits recorded; exact final-head `test-and-build`, `coworker`, `ci-merge-gate` pending until this review branch CI runs. No independently operated bubblewrap process-kill proof, staging or release evidence. Do not conflate existing tests with real network/worker operation or mark C-04 complete.

**Next:** Review and qualify this **main-targeting** PR on final SHA, without auto-merging; then implement immutable model-generated proposal+owner decision+atomic claim approval under C-04. CW-09 operated browser/DNS/SSRF, CW-11 skill publisher, P-series coworker scenarios and V-series release checks remain independent blockers.

---

## CW-10 source-integrity recovery worker-control CI contract repair — 15 October 2026

**Refreshed main:** `baa484ef861e41daf7653a29f6aaa07720932055`, merged [PR #415](https://github.com/rumman52/Shuddho/pull/415); [main CI #38760717140](https://github.com/rumman52/Shuddho/actions/runs/38760717140) `test-and-build` successful, `coworker` failed eight stale-claim assertions (1,375 other tests passed in that invocation), `ci-merge-gate` failed. No open PRs at bootstrap. The integrity denial, terminal failure, source scrub and lease revocation assertions all passed; the outdated expectation that `worker_control` **raises** disagreed with the newer explicit `stop/session_closed` terminal protocol.

**Isolated review branch:** `codex/cw10-recovery-claim-stop-ci-repair-20261015`. Test-only repair keeps all 16 initial/recovery tamper cases, asserts worker receives `stop/session_closed`, then submits a stale success receipt to the real completion boundary and verifies typed rejection with no change to durable integrity failure, session terminal state or source/lease cleanup. Production code unchanged. [Task contract](CW10_RECOVERY_CLAIM_STOP_CONTRACT_2026-10-15.md). **Exact branch-head mandatory CI pending; no independent security review, operated sandbox/network proof, staging or activation.**

**Next:** Obtain exact-head `test-and-build`, `coworker` and `ci-merge-gate` on the draft PR; inspect no-skip sandbox/PG/Temporal/browser/transaction checks and review. Do not merge or activate automatically. Continue missing immutable model-generated proposal, human owner approval with expiry/revocation and atomic sandbox claim gate (C-04), followed by reviewed skill publication (CW-11) and operated coworker scenarios.

---

## CW-10 terminal-session worker authority guard — 15 October 2026

**Latest repository baseline:** `main` `4015dc9fc30525b2344f522d5e0b195ed5d35fd3`, merged [PR #414](https://github.com/rumman52/Shuddho/pull/414) at 2026-10-15 14:36 UTC. PR-head `test-and-build` passed, but mandatory `coworker` and new main CI were still in progress at initial refresh. No submitted independent PR #414 review was found. The merge does not establish full operated safety.

**Additional same-batch finding:** Claim rows are selected as a batch before the loop. After one corrupted job fails the owning session, an already-selected sibling could previously reset that session to `running` and still receive source. The same PR now rechecks terminal state for every selected claim row, fails/scrubs ineligible siblings and includes a batch regression. Unselected abandoned jobs still need general retention/reconciliation review.\n\n**New source-level CW-10 safety finding:** A first execution can remain leased after a *sibling* source-integrity failure makes the owning sandbox session `failed`. The real worker heartbeat and completion paths previously checked cancellation or wall-clock expiry only. With no cancel flag and future expiry, stale worker execution and result acceptance could continue under a failed session.

**Isolated implementation:** `codex/cw10-terminal-session-worker-guards-20261015` hardens `SandboxRepository.worker_control` and `complete_execution` to reject **all terminal session states**, with durable scrub/lease cleanup and no altered happy path. Parameterized SQLite real-worker regression and PostgreSQL persistence regression added. [Task contract](CW10_TERMINAL_SESSION_WORKER_GUARD_2026-10-15.md). **Code/tests committed; exact-head PR CI, independent security review and staging qualification pending at this checkpoint.** The model-generated code proposal/owner approval/worker claim lifecycle remains **absent**; C-04 not complete.

**Next:** Finish exact-head CI and review on the new isolated PR, preserve default-off sandbox and avoid auto-merge. Then implement reviewed generated-code proposal/approval and worker claim enforcement; qualify CW-09 live Chromium/DNS/SSRF, CW-11 reviewed skill publisher/grants and P/V operated coworker evidence separately.

---

## CW-10 late sandbox completion rollback repair — 15 October 2026

**Refreshed evidence:** `main` `9bdb73a9142bce6e9e9848373dddde44514ca144`, merged [PR #413](https://github.com/rumman52/Shuddho/pull/413), matching [CI #38746278784](https://github.com/rumman52/Shuddho/actions/runs/38746278784) passed `test-and-build`, `coworker`, `ci-merge-gate`. No open PRs at task start. Earlier CW-10 source/policy worker-claim integrity is merged and verified at repository CI level; actual model-generated proposal/approval and operated isolation remain absent.

**Defect:** A sandbox worker completion arriving after session expiry/cancellation updated terminal state, scrubbed source and revoked the lease, but raised typed `sandbox_session_closed` inside `sessions.begin()`, rolling all of that transaction back. SQLAlchemy rollback reproduced independently. This is a source-level data-integrity/race defect, not confirmed production exploitation.

**Bounded fix:** `codex/cw10-late-completion-commit-20261015` commits the persisted closed-session transition inside the existing transaction and raises 409 only afterward. Adds owner-bound audit event, SQLite regression for post-claim expiry/cancellation, no repeat claim and no accepted receipt. [Contract](CW10_LATE_SANDBOX_COMPLETION_COMMIT_2026-10-15.md). **Committed branch; final-head CI, review and staging pending** at this entry. No schema/permissions/feature activation changes.

**Next:** Open review PR; check exact-head required `test-and-build`, no-skip `coworker` and `ci-merge-gate`. Obtain review, avoid auto-merge. Then address CW-10 immutable *model-generated* proposal, human decision with expiry/revocation, atomic worker-claim recheck, and staging sandbox cleanup/isolation. Other architecture, personal context, CW-09 and CW-11 gates remain incomplete.

---

## CW-10 worker-claim source integrity at authorization boundary — 15 October 2026

**Bootstrap and dependency evidence:** `main` `e4381617fd51107b74b4aac25e76109caf1a0123`; [PR #412](https://github.com/rumman52/Shuddho/pull/412) merged the HTTPS CONNECT pending-socket cleanup after its rewritten exact-head [CI #38725411478](https://github.com/rumman52/Shuddho/actions/runs/38725411478) passed required `test-and-build`, `coworker`, and `ci-merge-gate`. [PR #411](https://github.com/rumman52/Shuddho/pull/411) exact user-code Agent replay/receipt protections were already merged. Latest post-merge main [CI #38727695049](https://github.com/rumman52/Shuddho/actions/runs/38727695049) had `test-and-build` success and `coworker` still running at refreshed checkpoint. No open PR at task bootstrap; no independent submitted security review or operated staging/production identity. Core, context and release acceptance remain incomplete.

**Selected first unblocked safety defect:** Existing `SandboxRepository.prepare_execution` records exact source UTF-8 SHA-256 and byte length. Real `SandboxRepository.claim_executions` releases `request_spec.source` to authenticated workers without verifying it still matches those fields or the originally recorded `untrusted` source/policy versions. A post-preparation mutated request spec can execute different source on initial worker claim or expired-lease re-claim, even though later Agent receipt verification would detect a mismatch. This is a source-level data-integrity defect, not evidence of live exploitation. [CW-10 worker claim contract](CW10_SANDBOX_WORKER_CLAIM_INTEGRITY_2026-10-15.md).

**Committed implementation:** Isolated branch `codex/cw10-sandbox-claim-source-integrity-20261015` from above exact `main`. Within the authoritative worker claim transaction, reject absent/nonobject/invalid-UTF8, missing, oversized, reencoded, same-length substituted or hash/byte-length different source, mismatched `source_trust` or `policy_version`, or a changed server-owned sandbox execution policy or purpose/runtime fingerprint. Instead of delivering any code, mark execution failed `sandbox_source_integrity_failed`, scrub source, clear active worker/lease, mark session failed, audit the integrity failure, and retain `cleanup_state=required` if an older worker lease was already claimed; no re-claim. No changes to model authority, sandbox network/credential policy, approval grants, schema, action ledger, environment or rollout flag. Existing correctly prepared user-authored source claim stays operational.

**Tests:** `tests/test_sandbox_control_plane.py` tests eight tamper forms on first worker claim and expired-lease recovery (16 controlled cases), verifies no code dispatched, failure/scrubbing/terminal session, no second claim and stale worker invalidation. `tests/test_coworker_postgres.py` drives actual owned PostgreSQL sandbox rows and confirms same-length altered source cannot be claimed, job is failed/scrubbed and never reclaimed. Existing mandatory `coworker` CI already includes both test modules. Code committed, **final PR-head CI not yet verified**; no local full repository execution, independent review or staged sandbox network isolation. Current branch is not merged; browser remains default off and sandbox remains gated.

**Next:** Open draft review PR, inspect final-head `test-and-build`, no-skip `coworker` (PostgreSQL/Temporal/browser/transactions/sandbox) and `ci-merge-gate`; repair failures without weaker assertions. Independently review first-claim and re-claim, cancellation/cleanup, source-hash and owner scope; stage sandbox isolation. Then deliver CW-10's separately required immutable exact **model-generated** proposal, owner human review decision/expiry/revocation, atomic approval recheck on worker claim and cleanup. CW-11 review/version/grant skill selection, personal context and full CW-09 staging remain. No auto-merge/deploy/activate.

---

## CW-09 PR #412 hotfix rebase and commit rewrite — 15 October 2026

**Observed:** `main` `fdba3a4f607184b10dacb359e980a37db5000d68` contains merged CW-10 source/receipt guards from [PR #411](https://github.com/rumman52/Shuddho/pull/411). [PR #412](https://github.com/rumman52/Shuddho/pull/412) based on older `main` passed all mandatory jobs in [run #38715542785](https://github.com/rumman52/Shuddho/actions/runs/38715542785), but could not merge after #411 changed the same canonical inventory and progress files. GitHub `mergeable_state=dirty` was a documentation conflict, not a new test failure.

**Action:** rewrite only PR #412's review-branch commit on current main using force-with-lease (no shared-main history rewrite). Preserve the exact verified prior-PR code/test contents for early inbound socket registration, deterministic disconnect/cancel tests and valid pinned hostname evidence; preserve CW-10's mainline source-binding code, its tests and complete progress history. Semantic documentation merge uses the current main file plus the original CW-09 incident checkpoint and this reconciliation record. No conflict markers, no disabled checks.

**Verification:** Previous #412 exact-head `test-and-build`, `coworker`, and `ci-merge-gate` passed but cannot qualify the rewritten SHA. All three jobs must pass on new PR head; request independent review, stage real Chromium/DNS rebinding/SSRF. Status: repository qualification pending, production not qualified, features not activated. Do not auto-merge/deploy/activate.

---

## CW-09 mandatory Node CONNECT CI hang and pending-socket cleanup — 15 October 2026

**Live repository baseline:** `main` `1a75eb2f66595ef6ec2f8ccd01156f03276c9566` ([merged PR #410](https://github.com/rumman52/Shuddho/pull/410)); no open PR at initial next-session bootstrap, then [draft PR #411](https://github.com/rumman52/Shuddho/pull/411) opened on exact sandbox source/receipt identity. Required PR #410 head [run #38711309533](https://github.com/rumman52/Shuddho/actions/runs/38711309533) and merged-main [run #38711977867](https://github.com/rumman52/Shuddho/actions/runs/38711977867) both passed `test-and-build` but spent extended time in mandatory browser Node CONNECT step without finishing `coworker` / `ci-merge-gate` at this checkpoint. In-progress job logs unavailable (`BlobNotFound`), so cannot claim green. Production not activated.

**Reproduced high-priority bug:** A reconstructed, locally executed Node test using the repo's actual proxy/test logic timed out in the first two CONNECT tests and did not exit until forcibly killed; test three could observe an outbound dial after a client closed but before the server knew, and the valid-tunnel assertion dereferenced an invalid hostname property. More importantly, the actual `createPinnedProxy` registered client sockets for `pause()/destroy()` only *after* asynchronous `network-check`, so a pending browser CONNECT was not in the cancellation cleanup set. This is a source-level pending-transport cleanup defect, not a confirmed outside-network breach. [CW-09 defect contract](CW09_PROXY_SOCKET_CI_HANG_2026-10-15.md).

**Isolated fix branch:** `codex/cw09-proxy-socket-test-hang-repair-20261015` from exact `main` baseline. Register inbound `clientSocket` and close cleanup at CONNECT admission, before DNS await; avoid double registration. Browser Node tests drain rejected responses and store bounded buffered response, assert inbound close before releasing stalled authorization, explicitly tear down the server end for disconnected-client simulation, and address `state.evidence["example.com"]` with valid literal key. An isolated Node rehearsal with equivalent actual callback + tests passed **5/5, no skipped tests, process exits**. This local rehearsal is **not** exact-head CI. Worker command/epoch and TLS/pinned DNS checks remain unchanged; no new grant/ledger/migration.

**Required next verification:** Open draft PR, run final-head mandatory `test-and-build`, `coworker` (including this Node suite, PG/Temporal/transaction and browser) and `ci-merge-gate` with no bypass. Inspect actual CI failures and review. Obtain independent security review and operated Chromium/DNS/SSRF staging separately. PR #411 CW-10 must reconcile a later merge with `main`, and remains blocked by actual CI plus human-reviewed generated-code lifecycle. **No auto-merge/deploy/activation.**


---
## CW-10 exact Agent sandbox source identity on resume — 15 October 2026

**Current truth:** `main` `1a75eb2f66595ef6ec2f8ccd01156f03276c9566`; [PR #410](https://github.com/rumman52/Shuddho/pull/410) merged the real CONNECT proxy tests, with exact PR-head [CI #38711309533](https://github.com/rumman52/Shuddho/actions/runs/38711309533) and new merged-main [CI #38711977867](https://github.com/rumman52/Shuddho/actions/runs/38711977867) showing `test-and-build` success, mandatory `coworker` still running at initial refresh. Previous PR #409 exact-head [CI #38709409366](https://github.com/rumman52/Shuddho/actions/runs/38709409366) and matching-main [CI #38709819435](https://github.com/rumman52/Shuddho/actions/runs/38709819435) had passed all three. No relevant open PRs at bootstrap; PR #410 merged externally, without this session authorizing merge. No independent submitted reviews, operated browser/staging/production evidence missing.

**Selected immediate CW-10 safety defect:** The real `sandbox.execute_python` Agent tool intentionally executes **only exact user-authored fenced code**, never generated model code. It persistently binds one sandbox session to the Agent step. On resume, the runtime simply uses `list_executions(...)[0]` and proceeds with polling/receipt settlement without checking that the existing execution's source digest and byte size match the step's current exact source. Changed/restored ToolInvocation arguments could cause mismatched output attribution. [Bounded contract](CW10_SANDBOX_AGENT_SOURCE_BINDING_2026-10-15.md).

**Committed isolated fix:** `codex/cw10-agent-sandbox-source-binding-20261015` branched from current `main`. In `services/coworker/agent_runtime.py`, before accepting any existing execution as prepared/running/succeeded, require exactly one owned execution and equality of UTF-8 bytes count and SHA-256 against current `args.source`. **At the independent ToolReceipt commit transaction**, lock and verify the Agent-bound owned sandbox session, succeeded execution, exactly one execution, current invocation code SHA/byte size, and matching worker isolation, exact bounded stdout/stderr text and hashes, exit code and artifact identity. Deny mismatches with typed 409 `sandbox_source_binding_mismatch` without a false receipt. `tests/test_sandbox_control_plane.py` has two real Agent repository and sandbox integration fixtures: same-byte-length code substitution after an execution is prepared and after the independent sandbox worker completed. Require no second execution and no ToolReceipt, including a direct forged final-receipt attempt after the original worker has succeeded. A separate integration case submits a forged stdout excerpt with matching hash, proves denial, then completes the genuine result. **Real PostgreSQL integration coverage** in `tests/test_coworker_postgres.py` repeats source-substitution and forged-output denial directly at ToolReceipt settlement, and holds a PostgreSQL sandbox execution lock during a concurrent receipt attempt to prove fail-closed `SKIP LOCKED` behavior without a deadlock. It then verifies legitimate completion; no mandatory suite skip. User-supplied unaltered code path still covered by existing full sandbox tests. No schema migration, extra permissions/provider/action ledger, or feature activation. The generated-code path still requires durable human approval and sandbox claim enforcement; do not label C-04 complete.

**Evidence:** Product/test changes committed on GitHub review branch. Exact new PR SHA `test-and-build`, mandatory zero-skip `coworker` (PG/Temporal/transactions/browser/sandbox), `ci-merge-gate` **pending**; no local full checkout, independent review or operated staging. Browser proxy #410 new-head and main CI need final check. Staging S3/DNS/SSRF/prompt injection, CW-10 full approval lifecycle, CW-11 publisher, P-01/P-02/P-03 scenarios and release V-02–04 remain incomplete.

**Next:** Open draft PR, inspect exact final-head CI, repair any failures without skipping or weakening assertions. Obtain independent security review; qualify live browser sandbox/network staging separately. Then implement immutable generated-code proposal, owner human decision, atomic worker claim and bounded sandbox cleanup under CW-10, followed by CW-11 trusted skill publication and user grant selection. No merge/deploy/activation.

---

## CW-09 production HTTPS CONNECT socket-race qualification — 15 October 2026

**Fresh bootstrap:** `main` `74902c9223d648d3422a7d70b18991e8266f0281`; PR [#409](https://github.com/rumman52/Shuddho/pull/409) merged its reconciled old head `6993024eee41961e7c22cda76817939dc1eb193d`. Exact merged-PR [CI #38709409366](https://github.com/rumman52/Shuddho/actions/runs/38709409366) and new merged-main [CI #38709819435](https://github.com/rumman52/Shuddho/actions/runs/38709819435) had `test-and-build` success while `coworker` was **still in progress** at this initial checkpoint; do not count fully green until verified. PR #408 individual source erasure already merged. No open PRs at bootstrap, no independent submitted #409 review, operated Chromium/S3/staging/SSRF not available. Current architecture/core inventory remains incomplete.

**Selected safety qualification gap (C-02/C-03):** #409's Node suite checks `browserProxyClaimValid` as a predicate, not the actual asynchronous `http.Server` HTTPS CONNECT proxy, TCP socket registration or cancellation. That permits a broken control flow to remain untested despite pure-predicate success. `scripts/browser_worker.mjs` additionally dialed a pinned upstream after the client disconnected during a pending authorization, even if the claim remained live. New isolated branch `codex/cw09-proxy-socket-race-qualification-20261015` from fresh `main`. [Task contract](CW09_REAL_PROXY_SOCKET_RACE_2026-10-15.md).

**Code committed:** Extract the worker's same proxy handler into `scripts/browser_pinned_proxy.mjs`, preserving HTTPS-only authority, 443, broker `network-check`, pinned response IP, owner command/epoch/evidence triple gates before/after async authorization and TCP connect before 200. Worker now calls this module with its code-owned host validator and configured timeout; no user/model-supplied injection. Strengthen the post-await gate to refuse TCP dial if `clientSocket.destroyed`. Add `scripts/browser_pinned_proxy.test.mjs`: local socket-level CONNECT with asynchronous network authorization and controlled dial tests for command cancellation, ABA same-ID resumption, browser-client disconnect, revoked TCP handshake before acknowledgement, and an allowed pinned tunnel. Extend the **existing mandatory** `coworker` CI policy test step to run this new file as well as the unchanged policy tests. No new ledger, DB migration, provider, external action, broad grant or activation. Browser remains default-off.

**Evidence level:** Code and tests committed in GitHub branch; final SHA exact-head `test-and-build`, no-skip `coworker` including owned browser/PG/Temporal/transactions/Node proxy, and `ci-merge-gate` **pending** until new PR checks. No local checkout/test in this GitHub-only coding session; staging real Chromium + egress firewall/DNS/SSRF and independent review missing; production not qualified, activated no. CI green on #409 old head or main before this code does not qualify new branch.

**Next:** Open draft PR; review actual diff and code path; inspect final-head CI logs; repair any concrete failure without disabling checks or relaxing ownership. Obtain independent security review and operated staging worker egress/SSRF/DNS rebinding; continue CW-10 exact approved generated-code lifecycle, CW-11 review-bound skills, personal context scopes and four realistic coworker scenarios. Do not auto-merge/deploy/activate.

---

## CW-09 PR #409 conflict reconciliation — 15 October 2026

**Actual cause:** [PR #409](https://github.com/rumman52/Shuddho/pull/409) was based on `main` `896b5014bc371f5549fb9daa815338d932506a73`. [PR #408](https://github.com/rumman52/Shuddho/pull/408) subsequently merged into `main` `546e9a97c6ecda1abc34186bdb26971852539a75` and changed the same acceptance inventory and progress checkpoint lines. GitHub correctly reported a dirty merge in exactly those **two documentation files**, despite original #409's [CI #38704339583](https://github.com/rumman52/Shuddho/actions/runs/38704339583) being green. PR #408 [CI #38703355409](https://github.com/rumman52/Shuddho/actions/runs/38703355409) and merged-main [CI #38706921819](https://github.com/rumman52/Shuddho/actions/runs/38706921819) completed with all three mandatory jobs successful.

**Resolution design:** incorporate the exact new main tree, preserve all #408 source-erasure changes, retain #409's browser worker/policy/Node test and security contract unchanged, and reconcile the two conflicting docs semantically. Preserve full historical checkpoints for both workstreams; never choose either version wholesale or leave conflict markers. Update PR #409 branch through one actual two-parent merge commit, with old PR head as first parent and latest `main` as second parent; do not alter `main`, squash unrelated code or merge PR.

**Validation gate:** previous source head checks are historical, **not** final merge-head checks. After the merge commit, require exact final-head `test-and-build`, mandatory `coworker`, `ci-merge-gate`, mergeability and independent review. Staging browser DNS/revocation, SSRF and S3 evidence remain unverified, full CW-09 and CW-10/CW-11 incomplete, default-off and no deployment/activation authority.

---

## CW-09 async proxy CONNECT stale-claim race — 15 October 2026

**Baseline:** `main` `896b5014bc371f5549fb9daa815338d932506a73`, #406 merged with successful exact-head + main CI. Concurrent direct-main [merged PR #408](https://github.com/rumman52/Shuddho/pull/408) is separately repairing PR #407's deletion functionality which merged into a historical feature branch, not main; its required CI is pending. **Isolated worker safety branch:** `codex/cw09-browser-proxy-revocation-race-20261015`, created directly from this main; no PR branch dependencies or production changes.

**Observed source-level race:** HTTPS CONNECT pinned proxy asynchronously awaits DNS + server `network-check` and then opens an upstream socket; `pause`/cancel can happen during that await before client/upstream sockets are registered. An out-of-date authorized answer could open or acknowledge a tunnel after claim revocation. The original code did not revalidate worker claim generation after network check or on TCP connect.

**Committed bounded fix:** monotonic `proxyClaimEpoch` increment on set/pause/destroy; snapshot `{commandId, epoch, evidence}` per CONNECT; revalidate before DNS call, after network-check before `net.connect`, and on socket connect before sending HTTP 200/forwarding bytes. Stale/reused same-command snapshots fail closed. Pure Node policy regression tests cover cancelled in-flight check, ABA resume, evidence swap, wrong command, malformed generation. [Task contract](CW09_PROXY_DNS_REVOCATION_RACE_2026-10-15.md). Browser stays default-off, supervised controls intact. No new tool grant, action/outbox ledger, API or migration.

**Evidence:** GitHub source committed, exact-head required CI pending until PR checks; independent review not available; local full checkout/browser integration not available; **staging network race/SSRF/DNS rebinding not operated**, production qualification unavailable, activated no. Old proxy policy CI is not final revision evidence. No claim of observed live exploit.

**Next:** draft independent PR; final-head `test-and-build`, zero-skip `coworker`, `ci-merge-gate` and adversarial review; inspect actual failures, fix without disabling tests; independently stage live proxy cancellation + rebinding and comprehensive CW-09 browser security, then CW-10 immutable human-approved generated-code and CW-11 reviewed skills. Do not auto-merge/deploy/activate.


---
## CW-09 direct-main source-erasure integration — 15 October 2026

**Current baseline verified:** `main` `896b5014bc371f5549fb9daa815338d932506a73` (merged [#406](https://github.com/rumman52/Shuddho/pull/406) retained private browser-source artifacts). #406 final-head required [CI #38696966902](https://github.com/rumman52/Shuddho/actions/runs/38696966902) and latest matching main-push [CI #38699094958](https://github.com/rumman52/Shuddho/actions/runs/38699094958): all required `test-and-build`, `coworker`, `ci-merge-gate` completed **success**. PR [#407](https://github.com/rumman52/Shuddho/pull/407) was **merged into the historical #406 feature branch**, not `main`; its exact-head [CI #38697102026](https://github.com/rumman52/Shuddho/actions/runs/38697102026) passed, but its `DELETE /api/v1/browser-source-artifacts/{artifact_id}` route was absent on `main`. No relevant open PR at bootstrap. No independent submitted review for #407, no operated staging evidence.

**Selected first unresolved dependency (C-02/CW-09):** Restore the already-tested owner-scoped browser-source erasure behavior to the **actual default branch integration path**, without repeating or merging an old feature branch. Created isolated `codex/cw09-source-erasure-main-20261015` **from current main SHA above**. Ported only relevant `retention.py`, `api.py`, `agent_repository.py`, SQLite API/end-to-end `tests/test_agent_browser_tool.py`, and real PostgreSQL `tests/test_coworker_postgres.py` source diff. [Updated task contract](CW09_BROWSER_SOURCE_ERASURE_2026-10-15.md); updated [versioned acceptance inventory](ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md).

**Behavior:** authenticated owner-only deletion for one completed/cancelled/failed browser-source Agent run. Validate exactly one owned `browser.read` receipt, lock AgentRun and Artifact/ToolReceipt; refuse active runs with 409; atomically delete Artifact row and redact source URL/text/digest/size/artifact ID from persisted receipt, set `source_deleted=true`, and write audit. Then delete private object using existing ObjectStore. If object deletion fails, return truthful `metadata_erased=true, object_deleted=false, object_cleanup_pending=true` for existing aged orphan cleanup; no stale metadata-driven user downloads. Cross-user, active-run, confirmed object deletion, repeat attempts, storage outage and PostgreSQL JSON source-reference coverage ported. Existing presigned-browser-source URL prohibition maintained. No schema migration, new ledger, permissions, activation, deployment or external effects.

**Evidence distinctions:** source/test changes **committed** on direct-main branch, new exact-head repository CI **pending** until opened PR checks complete; no local full-checkout tests run in GitHub-only authoring environment. Previous #407 green CI on its **different target branch** is only supporting prior evidence, not qualification of this direct-main integration. Independent review **pending**, staging **not tested**, production **not qualified**, feature remains **default off**.

**Remaining highest priority:** open reviewable draft PR from direct-main branch, collect latest exact-head mandatory `test-and-build`, `coworker` (PostgreSQL/Temporal/browser/transaction no skip) and `ci-merge-gate`, review any failures and repair them without weakened assertions, request independent review and collect operated S3/source-revocation evidence. Next complete CW-09 worker network/redirect/DNS/SSRF and adversarial prompt-injection qualification, CW-10 exact user-approved generated-code lifecycle, CW-11 reviewed skills and the four operated personal coworker scenarios. Do not auto-merge/deploy/activate.

---

## CW-09 owner-bound durable visible source artifact — 15 October 2026

**Repository bootstrap:** `main` `599002b8e80089ac658548fdd6ed9e3dafc5ec22`; [PR #405](https://github.com/rumman52/Shuddho/pull/405) merged, exact final-head [CI #38692852396](https://github.com/rumman52/Shuddho/actions/runs/38692852396) has mandatory `test-and-build`, `coworker`, and `ci-merge-gate` all **success**. [#404](https://github.com/rumman52/Shuddho/pull/404) exact-head full CI also passed. Merged #405 main push [CI #38694104016](https://github.com/rumman52/Shuddho/actions/runs/38694104016) still running at initial refresh. No open PRs at branch creation, and neither #405 nor #404 had an independent submitted review observed. No operated staging or release eligibility evidence.

**Selected next gap:** CW-09 browser capture became a bounded text receipt but the full bounded source vanished at ToolReceipt settlement. Existing `Artifact` record, private `ObjectStore`, owner-authenticated artifact content API and `RetentionService` already provide the correct durable store, with no schema or orchestrator replacement. **Branch:** `codex/cw09-owned-browser-source-artifact-20261015` from above `main`. [Contract](CW09_OWNED_BROWSER_SOURCE_ARTIFACT_2026-10-15.md).

**Implemented on review branch:** `browser_sources.py` derives stable owner/command-bound UUID artifact identity and code-owned private object key. Runtime writes exactly the verified bounded UTF-8 visible text to existing private object storage and reads back to verify; storage errors fail closed without a verified receipt. The final `AgentRepository.finish_invocation` transaction rechecks live owned session, succeeded command and full bytes/digest/size/truncation/excerpt/URL/trust, inserts one existing `Artifact(artifact_class="browser_source")` alongside ToolReceipt atomically and scrubs transient browser ledger ciphertext on successful settlement. ToolReceipt references the artifact ID and exact content SHA. The authenticated artifact download gateway refuses S3 presigned URLs for `browser_source` while preserving ordinary export downloads; a regression test traps attempted presigning. Retention/account deletion and orphan cleanup are reused; an aborted post-blob DB commit is explicitly an orphan, not a verified source. No new UI, artifact list, migration, authority, activation or consequential action. Normal task artifact listing remains unchanged. Content is *bounded worker-visible text*, not raw HTML. Tests extended for owner/cross-owner object access, hashed capture bytes, fake content, S3-like storage failure, same-command retry/idempotence and real PostgreSQL + local ObjectStore.

**Evidence at branch implementation:** GitHub source committed on [draft PR #406](https://github.com/rumman52/Shuddho/pull/406); required exact-final-head CI **pending** until PR head checked; no local checkout or locally executed tests in this authoring environment, no independent review and no staged S3/Chromium. **Staging:** unverified. **Production:** not qualified. **Activation:** no (existing Agent browser flag remains default off). User-controlled per-source deletion, purpose-bound sharing and operated egress/SSRF/prompt-injection remain incomplete.

**Next:** open draft PR; inspect exact-head Python, Node, full no-skip `coworker` with real PostgreSQL/Temporal and `ci-merge-gate`; repair failures rather than disabling checks, independent adversarial review and staged source erasure/network/object-store proof. Follow with CW-10 human-approved generated code and CW-11 trusted skill publication/selection, plus four operated coworker scenarios. Do **not** auto-merge, deploy or activate.

---

## CW-09 final receipt authorization expiry guard — 15 October 2026

**Repository baseline:** main `96462220bb4d418227b322e55c6b4e4b60e67cd5` (PR [#404](https://github.com/rumman52/Shuddho/pull/404) merged). [PR #404 exact-head CI](https://github.com/rumman52/Shuddho/actions/runs/38691117096) and [merged-main push CI](https://github.com/rumman52/Shuddho/actions/runs/38691443218) had `test-and-build` success but mandatory `coworker` still **running** when reviewed; no independent submitted PR #404 review observed. No open PR at bootstrap. Previous PR #403 exact-head full CI green, but neither an old check nor an external merge establishes operational readiness.

**Reproduced first unresolved integrity boundary:** Browser content getter rechecked expiry, but final Agent ToolReceipt transaction and `_settle_agent_browser_session(completed=True)` did not. A session that expires between read and receipt could be falsely marked verified. New bounded branch `codex/cw09-expired-agent-receipt-guard-20261015` started exactly from the main SHA above. Code adds expiry guards **at final settlement and in canonical helper**, without broadening authority. PostgreSQL-backed test covers metadata-only and bounded content, including successful pre-expiry getter, post-expiry denied receipt, no ToolReceipt, no recovery by replay, and broker cleanup of transient sealed content. [Task contract](CW09_AGENT_BROWSER_LATE_RECEIPT_EXPIRY_2026-10-15.md).

**Additional PostgreSQL qualifier:** `tests/test_coworker_postgres.py` now runs the same expired capture-to-receipt boundary on the CI-provided real PostgreSQL service, verifying locked stale receipt denial and sealed source scrubbing. Source commit `798239e475b222a2ad9a703aa8ab4b910ca2fe5a`. The existing `tests/test_agent_browser_tool.py` container fixture uses SQLite; do not describe that fixture as PostgreSQL. **Draft PR:** [#405](https://github.com/rumman52/Shuddho/pull/405). All commits must be requalified at new final head.
**Change and evidence:** committed source, tests and refreshed [inventory](ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md) on branch; mandatory exact-final-head CI not yet established, independent review pending, staging not tested, production not qualified, capability not activated. Local full checkout/test unavailable via current GitHub-only authoring route; repository CI is primary evidence. No merge, deployment or activation performed. All edits committed through GitHub isolated branch; no local dirty checkout.

**Next:** open draft review PR, inspect exact SHA `test-and-build`, mandatory `coworker` (PG/Temporal/transaction/browser no skips), `ci-merge-gate`; repair any failures without weakening safety, obtain independent review, then continue CW-09 durable source artifact and operated egress/SSRF. CW-10 generated code, CW-11 reviewed skills and full operated coworker scenarios remain incomplete.

---

## CW-09 bounded page text: code review and exact-head qualification checkpoint — 15 October 2026

**Base:** main `e4a2e671ccaef9ab212f77cbd02521eec9866bd6`; previous [#403 exact PR-head CI](https://github.com/rumman52/Shuddho/actions/runs/38686360933) passed all three jobs. Main [push CI #38689490563](https://github.com/rumman52/Shuddho/actions/runs/38689490563) also completed with `test-and-build`, `coworker`, `ci-merge-gate` success. **Branch:** `codex/cw09-owned-page-text-capture-20261015`. **Draft PR:** [#404](https://github.com/rumman52/Shuddho/pull/404). **Latest substantive implementation/test head before this checkpoint:** `50be66cf67f09c18c64eb42343a23278608d9dcd`.

**Implemented on review branch:** isolated worker bounded UTF-8 visible-page-text extraction; strict typed worker evidence with exact whitespace preservation; broker AES-GCM owner/session/command-bound transient sealed text and SHA-256 of captured bytes; public DTO redaction; owner-scoped getter; Runtime v3 untrusted <=1200-byte excerpt and distinct `captured_text_excerpt` provenance. Blank text stays metadata-only. Settlement, cancellation and expiry remove sealed text. Expiry cleanup commits in an independent transaction before returning read denial, preventing accidental rollback of deletion. Regression tests cover Bangla bounds, owner isolation, exact digest, blank text, invalid receipts, source cancellation, stale expiry and typed schema compatibility. No new approval authority, schema migrations, production flags or outgoing consequential actions.

**Observed verification at handoff:** [PR #404 exact code-head CI #38691005056](https://github.com/rumman52/Shuddho/actions/runs/38691005056) running at the latest refresh for source SHA above; superseded runs were canceled due to ongoing changes. This docs checkpoint itself advances the branch and **requires a fresh exact final PR-head CI**. Full mandatory `test-and-build`, no-skip `coworker` and `ci-merge-gate` results **not yet established** for final head. Author self-review found and fixed (1) premature grounded claim on empty content, (2) expiring capture cleanup rolled back by read denial. **Not independently reviewed**.

**Evidence:** implemented in branch source; repository-verified **pending**, staging **not tested**, production qualification **not established**, activated **no** (Agent browser remains default off). Local full-repo tests unavailable because the authoring container cannot resolve GitHub; GitHub CI is authoritative. Owner-scoped PostgreSQL encrypted transient text **is not** a durable versioned source/artifact or full upstream HTML digest. Staging Chromium/egress and redirect/DNS/SSRF + model prompt-injection evaluations and release eligibility are outstanding, along with CW-10 exact approved code+worker sandbox and CW-11 trusted reviewed skills.

**Next exact action:** inspect #404 latest final-head CI `test-and-build`, `coworker` (PostgreSQL/Temporal/transaction/Agent browser no skips), `ci-merge-gate`, review and repair any failures without weakening enforcement. Obtain independent review and operated staging evidence. Do not auto-merge, deploy or activate.

---

## CW-09 bounded visible page text content slice — 15 October 2026

**Bootstrap truth:** `main` `e4a2e671ccaef9ab212f77cbd02521eec9866bd6`; [PR #403](https://github.com/rumman52/Shuddho/pull/403) was **merged**, its final-head [CI #38686360933](https://github.com/rumman52/Shuddho/actions/runs/38686360933) **passed all three** `test-and-build`, mandatory `coworker` and `ci-merge-gate` jobs. Matching main push [CI #38689490563](https://github.com/rumman52/Shuddho/actions/runs/38689490563) was running at bootstrap; no open PR at that point. No staging, production qualification or activation demonstrated.

**Next selected gap:** Agent browser source output remained metadata-only title/URL, insufficient for grounded public-page research. **Implementation branch:** `codex/cw09-owned-page-text-capture-20261015` based on the above main revision. [Contract](CW09_VISIBLE_PAGE_TEXT_CAPTURE_2026-10-15.md). In real Runtime v3 broker read path, isolated worker now returns optional bounded visible text; PostgreSQL command stores text encrypted with owner/session/command TokenVault binding and true digest of captured UTF-8 bytes; only owned server runtime obtains a <=1,200-byte untrusted excerpt. Browser user DTO excludes ciphertext/plaintext; Agent settlement, cancellation and expiry scrub temporary sealed text; malformed claims remain terminal. Legacy metadata-only worker receipts retain truthful metadata scope. New Python/JS tests and strict worker HTTP schema fixture update provided.

**Evidence levels:** Source implementation on review branch; **repository required exact-head CI and independent review still pending**, local checkout unavailable due GitHub DNS failure; **staging not tested**, **production not qualified**, **not activated**. The digest is of *bounded extracted visible text*, not complete HTML, and persistent private source artifacts remain a separate missing deliverable.

**Remaining:** CW-09 real isolated worker egress, SSRF/redirect/rebinding, source artifact retention/provenance, prompt injection, cancellation/staging; CW-10 exact generated-code human-approval+sandbox claim; CW-11 versioned trusted publish/grants/rollback; context continuity/recovery operated scenarios and production release contracts. See [versioned acceptance inventory](ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md). No auto-merge, deployment, paid provisioning or runtime activation.

---

## CW-09 Agent browser credential and HTTP mutation isolation — 15 October 2026

**Current main at bootstrap:** `45906f87cf2eba9f6abb5afc654f834166fa5820`; [PR #402](https://github.com/rumman52/Shuddho/pull/402) **merged**. Its exact-PR-head [CI #38685207628](https://github.com/rumman52/Shuddho/actions/runs/38685207628) `test-and-build` passed and mandatory `coworker` was **in progress** at initial review; merged-main [push CI #38685347836](https://github.com/rumman52/Shuddho/actions/runs/38685347836) also in progress. Do not report these green until refreshed. No other open PRs at bootstrap.

**Next security slice:** The browser worker previously replayed and persisted storage state for Agent reads and did not block page-originated POST/PUT/PATCH/DELETE for the Agent `navigate` command. Isolated implementation branch `codex/cw09-agent-read-cookie-isolation-20261015`, based on main SHA above. Added broker and worker defense-in-depth plus JS policy and real PostgreSQL-backed broker regression coverage. Human-supervised state continuity and takeover policy unchanged. [Contract](CW09_AGENT_BROWSER_CREDENTIAL_AND_MUTATION_ISOLATION_2026-10-15.md).

**Latest focused regression commit:** `90b38cdeef39f7faba5a1196daf4cbd75c3b102e` tests that even deliberately injected legacy encrypted session state never reaches an Agent worker claim. **PR:** [#403](https://github.com/rumman52/Shuddho/pull/403) (draft; not merged).
\n**Evidence (this new slice):** Source/test implemented and committed on branch; **required exact-final-head CI pending**, independent reviewer pending; **staging no, production qualification no, activation no**. Confirm JS worker policy runs via `test-and-build` and Python cookie-receipt terminality via `coworker`. Next: investigate failures and review PR without weakening checks. Then implement private bounded page text and real provenance/egress, not metadata as content. See the [versioned architecture/core acceptance inventory](ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md).

**Security:** Agent browser remains disabled unless separately qualified/authorized; no merge, deployment, paid provision, external action or activation performed.

---

## CW-09 post-#401 exact server-bound destination fixture — 15 October 2026

**Source truth:** PR #401 merged at `main` `052194a2b27eafc13d37b701cd90d25e887993eb` but its [CI #38681248077](https://github.com/rumman52/Shuddho/actions/runs/38681248077) had **1 failed, 35 passed** on mandatory Agent browser; `test-and-build` passed, `coworker` and `ci-merge-gate` failed. Original test remediation did not complete CI. Root cause: new DNS terminal-receipt test session start URL `/` differed from locked `/article` prepare command, provoking the intended `browser_agent_scope` guard before DNS was tested.

**Correction:** One-line fixture binding on `codex/cw09-bound-destination-ci-fixture-20261015` based on main SHA above. Set session start URL to exact `https://example.com/article` (matching prepare and final URL). No runtime or authorization changes. [Task contract](CW09_EXACT_AGENT_BROWSER_DESTINATION_FIXTURE_2026-10-15.md). Initial source commit `1e629fb47842d6fdbd32cdc314c4d8a0e8aadd10`.

**Evidence:** source implementation on branch; **exact final-head CI, no-skip PostgreSQL/Temporal/browser/transactions and independent safety review pending**; staging no; production qualified no; activated no. **Next:** get all three required CI jobs green, review, then address actual CW-09 content capture/SSRF worker staging and CW-10/11 missing real integration. No auto-merge, deployment or runtime activation.

---

## CW-09 mandatory browser CI repair — 15 October 2026

**Fresh default branch:** `main` `a305652a0be05b6d6a3768afbe6a14a029bd91c8`; PR #400 merged, no open PRs at task bootstrap. [Exact-main CI #38612375324](https://github.com/rumman52/Shuddho/actions/runs/38612375324): `test-and-build` success; `coworker` failed mandatory Agent browser gate (**2 failed, 33 passed**); `ci-merge-gate` failed. Earlier notes about #400 remaining draft or repository-green are superseded.

**Contract:** [CW09_MAIN_BROWSER_CI_TEST_CONTRACT_REPAIR_2026-10-15.md](CW09_MAIN_BROWSER_CI_TEST_CONTRACT_REPAIR_2026-10-15.md). **Branch:** `codex/cw09-browser-ci-regression-repair-20261015` based on `a305652a`. Focused correction commit `fe989fffb46116d4c24d46d9b521b19c4f749a07` before documentation. Invalid DNS terminality now tested in a dedicated negative scenario, not followed by success on the same failed command; authorized clean browser route still tested. The malformed-Unicode fixture now uses a real lone surrogate `chr(0xD800)` rather than literal escape text. Test-only fix, no relaxed assertions or broker change.

| Architecture/core part | Source status | Required remaining evidence |
| --- | --- | --- |
| Part 1: Architecture/contracts | Durable owner-bound, Temporal/outbox, permission boundaries exist in merged foundations; design not exhaustively qualified | Resolve and evidence residual state/trust/migration and operated boundaries |
| Part 2: Core agent/tool execution | CW-05–CW-08 foundations integrated, CW-09 metadata-only browser and inert CW-10/11 contracts; this browser test correction on isolated branch | Required exact-head CI; private page content/digest, generated-code stored approval+sandbox, reviewed skill runtime selection |
| Part 3: Context/coworker continuity | Owned context, message/activity and memory foundations present | Operated reconnect, erasure, purpose isolation, steering and resume |
| Part 4: Verification/release | Main mandatory Agent browser red at bootstrap | Corrected PR exact-final-head required CI and review; staging/operated release evidence absent |

**Evidence for this change:** implemented on branch; repository verified **pending exact-final-head tests**; staging verified **no**; production qualified **no**; activated **no**. **Next exact action:** inspect branch CI jobs and review comments, fix findings while retaining fail-closed tests. Then tackle next remaining CW-09 private-content worker receipt slice. No automatic merge, deployment, flag activation, provider action, or production claim.

---

# Coworker evolution progress

## CW-09 malformed Agent read receipt terminality — 14 October 2026

**Bootstrap/main:** `607b828274f9f4c580cd3dbd2ea5889d947904fc`. CW-09 [PR #399](https://github.com/rumman52/Shuddho/pull/399) **merged**; the historical section below calling it a draft is superseded. Its preceding main `ddc81711` [CI #38548692557](https://github.com/rumman52/Shuddho/actions/runs/38548692557) passed all three required jobs; the latest main `607b828` [run #38600101218](https://github.com/rumman52/Shuddho/actions/runs/38600101218) was still in progress at bootstrap. No staging or production qualification established. No open PRs at bootstrap.

**Selected first dependency-ready gap:** `_bounded_observation` rejects a malformed Agent worker result before committing a failed command; the same worker could resubmit a clean result. This differs from already fixed interaction signals, which terminally fail. **Branch:** `codex/cw09-terminal-malformed-agent-browser-evidence-20261014`, base `607b828274f9f4c580cd3dbd2ea5889d947904fc`; source and regression SHA `846f7f5a72edef2025fbcfed496594605a84c8c1` (initial); post-P1 source/test head `5832dce5eff5bdb04a8efab07f3861e8fb7d27b0` before latest docs. [Task contract](CW09_MALFORMED_AGENT_READ_TERMINAL_RECEIPT_2026-10-14.md).

**Change:** in code-owned broker completion, after malformed receipt detection lock BrowserSession then BrowserCommand; for the claimed Agent read only, commit failure, revoke session, clean claims/state/frame and audit, then propagate original error. Non-Agent sessions keep original validation/retry semantics. New regressions cover malformed object shape, missing URL, malformed DNS/title, terminality and no resubmission, plus ordinary browser retry acceptance. No feature or authority granted.

| CW task | Integrated source status | Remaining acceptance |
| --- | --- | --- |
| CW-05–CW-07 | Owner-scoped messages, dispatch/activity foundations | Operated replay/reconnect/deletion and UI acceptance |
| CW-08 | Selected source/context foundations | Revocation, expiry, erasure and versioned memory staging |
| **CW-09** | Metadata broker, Agent kill switch, verified prior changes including #399; this terminality fix isolated on review branch | Final-head tests/review; private page text and hash, egress/SSRF redirect worker staging, runtime release eligibility |
| CW-10 | Inert immutable proposal schema merged | DB persistence, exact human approval, sandbox claim enforcement, isolation tests |
| CW-11 | Inert reviewed manifest validator merged | Trusted publish/version rollback/runtime grant selection and evaluation |

| Evidence | Selected repair |
| --- | --- |
| Implemented | Isolated branch code/tests and contract |
| Repository verified | **Pending exact final PR SHA CI and independent review** |
| Staging verified | Not run |
| Production qualified | Not established |
| Activated | No; Agent browser flag remains default-off |

**Additional P1 review resolution:** The reviewer found FastAPI `BrowserWorkerObservation` returning HTTP 422 before the broker could terminally fail a claimed Agent read, and `UnicodeEncodeError` bypassing the typed failure from `storage_state`. Corrected in source/test commit `3c05b2161b836010dc14d411eb3463101706c8b5` before final docs: authenticated endpoint retains strict Pydantic model validation, uses broker session-before-command failure for a correctly claimed Agent command, preserves non-Agent and wrong-worker behavior, handles invalid Unicode as a typed error, and calls blocking repository operations via threadpool. HTTP tests cover bad final URL/title/DNS/storage/extra fields and denial of a successful rewrite. **Newest exact-head CI and independent re-review required.** No release evidence granted.

**Review and resolution:** On [draft PR #400](https://github.com/rumman52/Shuddho/pull/400), the independent reviewer found a **P1**: post-envelope validation exceptions rolled back and allowed rewritten Agent reads. Added a shared committed terminal transition after the failed completion transaction, excluding legitimate cancellation/worker-claim/revocation control errors. Added DB-backed invalid storage, DNS, URL and redirect cases, and wrong-worker regression. **Next exact action:** Verify newest PR #400 exact-head `test-and-build`, no-skip `coworker` browser/PG/Temporal, `ci-merge-gate` and independent re-review; correct findings. Continue private page content capture and operated worker tests. Do not auto-merge, deploy or activate.

## Architecture/core status refresh — 14 October 2026, PR #399

**Default branch:** `main` `ddc81711c8ccb4475d3a0053b26b5955a5be35b1`; [CI #38548692557](https://github.com/rumman52/Shuddho/actions/runs/38548692557) passed `test-and-build`, `coworker` and `ci-merge-gate`. [#398](https://github.com/rumman52/Shuddho/pull/398) merged (CW-09 autonomous browser kill-switch broker repair), [PR CI #38547893525](https://github.com/rumman52/Shuddho/actions/runs/38547893525) all three required jobs passed. No open PR at bootstrap. No fresh staging/production evidence established.

**Selected unfinished task:** CW-09 typed worker receipt shape validation; malformed JSON arrays/scalars/null triggered unhandled `AttributeError` at `_bounded_observation`. [Contract](CW09_BROWSER_RECEIPT_TYPE_VALIDATION_2026-10-14.md). On branch `codex/cw09-observation-type-validation-20261014` based on main SHA above. Test commit `a0601c01e1ddd770ef5a4632a8570223ff588fdf`; source commit `edd7fa8bb9dfaccccd19de6edd6c3bdd9646ee01`; this documentation checkpoint follows. [Draft PR #399](https://github.com/rumman52/Shuddho/pull/399) is **unmerged**, its exact-final-head CI and independent review remain **pending**. Five regression values exercise real worker claim and valid subsequent completion. No authority or feature flags changed.

| Canonical acceptance | Integrated on main | Remaining acceptance |
| --- | --- | --- |
| CW-05–CW-07 | Owner-bound chat, routing/activity foundations | Operated replay/reconnect, keyboard/mobile and ownership verification |
| CW-08 | Selected source/context foundations | Fresh staging deletion/revocation/retention |
| CW-09 | Metadata read broker and Agent kill-switch repair #398 | New malformed-receipt fix #399 review/CI; private page-text/hash/provenance, egress staging, canonical release eligibility |
| CW-10 | Inert source/proposal schema | Persisted immutable proposal, reviewed identity/approval and isolated compute claim |
| CW-11 | Inert reviewed manifest validator | Trusted publish/rollback, runtime grant selection, evaluations and staging |

**Evidence separation:** New #399 slice implemented on draft branch, **not integrated main or repository-verified** pending CI/review. Staging-verified no; production-qualified no; activated no. Historical checkpoints below describe their respective earlier branch states.

**Next exact action:** Retrieve PR #399 exact head and all three required GitHub CI job conclusions; self/independent review and correct any failed check. Maintain draft status. Then implement independently gated CW-09 private browser content capture and provenance, not infer a working page reader from metadata.

---


## CW-09 Agent browser worker-time kill-switch — 14 October 2026

**Refreshed default branch:** `main` `7da39a13e0207b96a2b05dde72e1fb876a970a5c`; no open PRs at bootstrap. Main `test-and-build` passed while `coworker` and `ci-merge-gate` were not yet complete on [CI #38546539014](https://github.com/rumman52/Shuddho/actions/runs/38546539014). The previous CW-11 #396/#397 work has been merged; earlier PROGRESS notes treating it as draft are historical. No deployed release or staging evidence was established.

**Current task:** CW-09 autonomous browser read revocation at the actual worker/broker boundary. [Contract](CW09_AGENT_READ_REVOCATION_BOUNDARY_2026-10-14.md). Review branch `codex/cw09-agent-read-revocation-boundary-20261014`; base as above; initial source commit `28ebf7a7f2edc3e84d3a15ab977aa9ac8de71981`, regression tests commit `605b65cf180784645b31043e9d54474e9520560a`, task-contract commit `fa21d61a54720fe66464ee1f5b5ded3d0ac680d1`, before this progress update. Exact final implementation SHA and PR number must be obtained from GitHub after this checkpoint.

**Gap:** Existing runtime/tool gating was not enough: a prepared `agent_read_only` browser command could be claimed by a worker after the Agent-specific switch was disabled; an already-claimed command could still pass independent broker network preflight and submit a late verified receipt. The broker now denies new server-agent sessions and preparation when disabled, terminally fails queued/claimed Agent reads at claim/control and completion, and explicitly rejects network egress preflight after revocation. Human-supervised browser reads retain their separate capability. Tests cover queued revocation, claimed network/control/receipt and supervised non-regression. No migration, second ledger, external provider, human approval bypass or production activation.

| Architecture/core acceptance | Integrated evidence | Remaining |
| --- | --- | --- |
| CW-05–CW-07 | Conversation and activity foundations merged | Owned operated replay/reconnect/UX qualification |
| CW-08 | Selected-source validation and memory controls merged | Staging revocation/deletion and retention |
| **CW-09** | Broker and tool foundations on main; new revocation repair on isolated branch | **Final-head CI/review**, private bounded page text provenance, worker egress staging, canonical runtime release eligibility |
| CW-10 | Inert reviewed code-proposal envelope merged | Persisted immutable proposal, explicit reviewed approval and sandbox worker claim |
| CW-11 | Inert reviewed manifest integrated via #396/#397 | Trusted publication/rollback enforcement, runtime grant-selection and staging evaluations |

**Evidence:** implemented on isolated review branch, repository-verified **pending exact-head CI and independent review**, staging-verified **no**, production-qualified **no**, activated **no**. An in-flight request already allowed just before a revocation cannot be undone; the worker stop/egress and shutdown staging boundary still needs testing. Flags unchanged and default-off.

**Next exact action:** Open draft PR for the review branch, inspect `tests/test_agent_browser_tool.py`, `tests/test_browser_broker.py`, exact-head `test-and-build`, `coworker` and `ci-merge-gate` (zero mandatory skips), repair any failures, obtain independent review. Then take a separate CW-09 page-content/private receipt and runtime release-gate slice without treating this guard as CW-09 closure.


## CW-11 schema-generator dependency-pinning repair — 14 October 2026

**Live verified bootstrap:** `main` `4acea1d245030101aff657d80f89b1c66c7ca097`, CI [#38527867446](https://github.com/rumman52/Shuddho/actions/runs/38527867446) **success** (`test-and-build`, mandatory `coworker` incl. browser, `ci-merge-gate`). Historical merged-red CW-09 notes below are superseded by this newer integrated CI. **Open #396:** CW-11 inert manifest pilot was green on `9b80e39ddb3c129726ec85f2779f52b5bd4bbf1b` ([CI #38527404758](https://github.com/rumman52/Shuddho/actions/runs/38527404758)) but unmerged; [P2 review](https://github.com/rumman52/Shuddho/pull/396#discussion_r4267904354) found a dependency-upgrade bypass. The other three P2 findings were addressed in that earlier branch revision.

**Correction:** continue the existing branch `codex/cw11-inert-reviewed-skill-manifest-20261014`, no duplicate PR. Code/tests SHA `045830b2afc2e5645438c00a769929b36ae03953` before docs. Initially pinned whole `uv.lock` bytes, but [CI #38539292291](https://github.com/rumman52/Shuddho/actions/runs/38539292291) exposed an incorrectly escaped Git blob NUL separator (33 failed, 1110 passed, 66 skipped), not an actual generator upgrade. Replaced byte hash with exact pinned **Pydantic/core/typing generator versions in both parsed lockfile and installed environment**; lock version mutation and installed version mismatch still fail closed. Latest source/test commit `931507c348f686282d9c9e35023875fb06639e31` before docs. Independent [P2 shared nested limits](https://github.com/rumman52/Shuddho/pull/396#discussion_r4268811787) review fixed: returned manifest copies do not share limits/reference object, and exact scalar ceilings are checked before equality. Added malicious `object.__setattr__` regression. The earlier Git blob separator P1 was resolved by removing the brittle whole-file hash in favor of exact locked+installed generator versions; final-head full CI is pending. **Evidence level: implemented on open PR #396, exact-new-head CI and independent re-review pending.** This is an *inert* data validator, not skill publication, agent tool selection, or provider/grant activation. A deployment without its reviewed dependency identity fails closed.

| Canonical item | Integrated state | Still required |
| --- | --- | --- |
| CW-05–CW-07 | Conversation/activity integrated; main CI green | Operated replay/reconnect and UI |
| CW-08 | Selected source/context integrated; main CI green | Operated deletion/revocation |
| CW-09 | Read broker and ledger corrections merged; main CI green | Real private page text/content digest, isolated browser egress staging, runtime release guard |
| CW-10 | Inert reviewed code-envelope source merged; main CI green | Persisted proposal+exact approval+isolated claim |
| **CW-11** | Inert reviewed manifest **on PR #396, not integrated** | Re-review and exact-head CI on pinned generator deps; persisted reviewed publish/rollback and runtime grant filter |

**CI correction:** [#38540161508](https://github.com/rumman52/Shuddho/actions/runs/38540161508) had 1 failed/1143 passed/66 skipped in broad Python checks solely because the generator drift test used literal backslash-n rather than a newline in its TOML fixture string. Corrected to `chr(10)` without weakening the negative assertion; exact-final-head CI still required. **Next exact action:** inspect PR #396 latest-head CI, mandatory no-skip tests and independent review. Repair actual failures on that branch without automatic merge or activation. Read-only synthetic tests do not qualify production.

## CW-11 first code-owned reviewed manifest pilot — 14 October 2026

**Live reference:** `main` `3505c5029891d488678b1f2e8b302694ce0a96e4`; merged #393 exact-head [CI #38513869839](https://github.com/rumman52/Shuddho/actions/runs/38513869839) green. #394 merged initial CW-10 envelope, with new independent datetime-subclass P2 addressed on separate [draft PR #395](https://github.com/rumman52/Shuddho/pull/395), **not a dependency automatically merged here**. Main CI #38524741451 and #395 CI #38525432542 were in progress at this checkpoint.

**Independent first CW-11 dependency-ready slice:** branch `codex/cw11-inert-reviewed-skill-manifest-20261014`, base `3505c5029891d488678b1f2e8b302694ce0a96e4`, initial source/tests SHA `6f11f841c8427620d62b9e897eda96fe80fda57c`; latest source/test SHA `d0264e22cf4c6ae6a606f8f6bafb8e36b7270bc6` before docs. Independent [#396 review](https://github.com/rumman52/Shuddho/pull/396) identified three P2 issues: regenerated unpinned policy, subclassed comparison identities, retry-unaware wall cap. Corrected via static Git blob source attestations, one frozen code-reviewed pilot snapshot plus live drift checks, exact field identity guards and 481-second retry-aware budget. New regression cases added. **Draft PR #396**, unmerged; exact final-head CI and independent re-review still required. [Task contract](CW11_INERT_REVIEWED_SKILL_MANIFEST_2026-10-14.md). New **pure, inert** `CoworkerSkillManifest` pilot for existing `research` / `research.search`; pins current WorkSkill version and instruction/guidance hash, exact ToolSpec input and output schema hashes, full registered tool-policy hash (including permissions), immutable resource ceilings, rollback version and code-owned `allowed_tools` subset. Negative tests reject new tools, connected email/browser escalation, changed source/schema/policy, permission drift, subclass/mutable values and wider limits. No dynamic skill install/loader, feature flag or production capability change.

| Task | Integrated code | Missing acceptance |
| --- | --- | --- |
| CW-05–07 | Owned conversation/run/activity integrated | Staging replay and UX/accessibility |
| CW-08 | Owned source/context foundation integrated | Revocation/deletion retention staging |
| CW-09 | #393 merged with exact CI pass | Page text private checksum, worker/network SSRF staging, runtime release eligibility |
| CW-10 | #392/#394 merged inert envelope; #395 draft correction | #395 final-head CI/review; persisted proposal/approval and isolated worker claim |
| **CW-11** | Static WorkSkill/ToolSpec registry; inert pilot manifest **on isolated review branch** | Final-head CI and review, publication/rollback authority, skill-selection gate, quality/cost evaluation and operated staging |

| Evidence level | CW-11 pilot |
| --- | --- |
| Implemented | Isolated source/test/doc changes |
| Repository-verified | **Pending exact-final-head CI** |
| Staging-verified | No |
| Production-qualified | No |
| Activated | No (no registry/dispatch/permission mutation) |

**Next exact action:** open CW-11 draft PR, inspect `tests/test_coworker_skill_manifests.py`, full `test-and-build`, `coworker`, `ci-merge-gate`, and independent review on exact final head. Fix failures without weakening checks; no merge/activation. Continue CW-09/10 operational contracts in separate dependency-reviewed slices.

## CW-10 exact timestamp / UUID class review repair — 14 October 2026

**Live bootstrap:** `main` `3505c5029891d488678b1f2e8b302694ce0a96e4`, after merges [#393](https://github.com/rumman52/Shuddho/pull/393) and [#394](https://github.com/rumman52/Shuddho/pull/394); **no open PRs** at bootstrap. #393 exact-head [CI 38513869839](https://github.com/rumman52/Shuddho/actions/runs/38513869839) passed `test-and-build`, all `coworker` (including mandatory browser tests) and `ci-merge-gate`; merged source corrects exact integer schema versions. #394 exact-head [CI 38521982865](https://github.com/rumman52/Shuddho/actions/runs/38521982865) passed, but the latest independent [P2 review](https://github.com/rumman52/Shuddho/pull/394#discussion_r4267484974) documented an unguarded subclassed `datetime.astimezone` bypass during immutable proposal review. Main [CI 38524741451](https://github.com/rumman52/Shuddho/actions/runs/38524741451) was still in progress at bootstrap.

**Coherent correction:** branch `codex/cw10-exact-timestamp-uuid-review-20261014`, baseline `3505c5029891d488678b1f2e8b302694ce0a96e4`, initial code/test head `6624209e7f7b2b778a9897e005fcc1aef39733e2`; earlier reviewed source/test head `b5b49bc9e9e1f7855cd6475cfee1bbdd07751682`; latest test-only correction head `cdc1fb1338ca57b2ce744365760780ffabfd69d2` before final docs. Prior CI `a018236` had 3 **test fixture setup** failures from stdlib UUID construction receiving an equality-overriding `int` subclass. The fixture now constructs a standard UUID and injects the hostile payload directly; exact latest-head CI and independent review remain mandatory, after final-head review found [P2 hostile tzinfo](https://github.com/rumman52/Shuddho/pull/395#discussion_r4267754497) and [P2 UUID integer subclass](https://github.com/rumman52/Shuddho/pull/395#discussion_r4267754504) bypasses. Code now checks exact canonical timezone/clock and UUID integer payload; matching-digest negative tests added. **Draft [#395](https://github.com/rumman52/Shuddho/pull/395)**, unmerged; refreshed exact-head CI/review required; [task contract](CW10_SUBCLASSED_REVIEW_IDENTITY_REPAIR_2026-10-14.md). Verifier now requires exact `datetime` and `UUID` types on original proposal and nested input identities **before invoking subclass-overridable normalization or serialization**; tests use self-consistent hashes with adversarial subclassed three-hour expiry and UUID references. Unchanged finite limits, source hash, owner, version, immutable nested type, and `egress_profile=none` gates. No new authority.

| Acceptance item | Integration | Unmet acceptance / next action |
| --- | --- | --- |
| CW-05/CW-06/CW-07 | Existing merged implementation | Operated owned chat, steering, resume and deletion |
| CW-08 context/memory | Existing merged core | Revocation, expiry, retention staging |
| CW-09 brokered browser | #387–#393 integrated; #393 final CI green | Actual bounded webpage text/private digest, isolated-worker egress/DNS/SSRF proof, execution-time eligibility, staging |
| **CW-10 reviewed code** | #392/#394 integrated inert envelope, current subclass correction on new review branch | Exact-head CI/review, persisted immutable proposal/approval, sandbox worker claim and execution safety |
| CW-11 reviewed skills | Static registered code-owned tools | Strict versioned manifests, no authority expansion, rollback + qualification |

| Evidence | Current CW-10 correction |
| --- | --- |
| Implemented | Source/test/docs in isolated review branch |
| Repository-verified | **Pending exact-final-head mandatory CI and independent review** |
| Staging-verified | Not run |
| Production-qualified | Not established |
| Activated | No: code proposals remain inert and browser.read default-off |

**Next exact action:** Open draft PR, verify `test-and-build`, `coworker`, `ci-merge-gate`, and `tests/test_agent_code_proposals.py` on that final SHA, obtain independent review; correct failures without reducing guard/test strength. Then select next dependency-ready CW-09/10/11 coherent slice. No automatic merge, credential change or activation.

## CW-10 #394 copied-state and subclass integrity repair — 14 October 2026

**Source/PR:** [#394](https://github.com/rumman52/Shuddho/pull/394), branch `codex/cw10-review-envelope-revalidate-20261014`; source/regression commit `4f060279cc38895e1f04f7ab5255724b1451ba8b`. Original branch baseline `9f8cf53a422ba5eee7d5a0772b2943328d3faaaa`; reconciled with main `81cc0cd9d679b568a98722ca6cb53b91c9170eb2` (merged [#393](https://github.com/rumman52/Shuddho/pull/393)). Current PR head is resolved from GitHub at review and CI time; do not substitute older SHA checks.

**Reproduced risk and fix:** Review on #394 found inherited/subclass serializers can disguise original proposal state, and `model_copy(update={"approved": True})` can add an undeclared field that `model_dump` omits, while a matching review hash still verifies. `verify_reviewed_code_identity` now rejects subclasses and requires exact declared stored fields (including nested limits and input versions), with no hidden Pydantic extra/private state before strict reconstruction. Added six negative parameter cases covering copied undeclared top-level fields, nested extras and subclass overrides. These remain inert checks; no code execution, approval, grants or rollout.

**Previous CI diagnosis:** [old #394 CI](https://github.com/rumman52/Shuddho/actions/runs/38514097821) had successful `test-and-build`, 1340 general coworker tests passed, but mandatory CW-09 browser gate failed `21 passed, 1 error` on missing `signed_client` fixture, therefore `ci-merge-gate` failed. This was a pre-#393 base; #393 deleted/relocated the fixture-dependent test. The new combined head needs its own complete required CI. Do **not** claim it green yet.

**Evidence levels:** implemented on a GitHub review branch; repository-verified **pending exact-head no-skip CI** and review; staging-verified **no**; production-qualified **no**; activated **no**. Existing CW-09 and CW-10 incomplete operational requirements remain separate.

**Next exact action:** Inspect the reconciled PR head, run `uv run --extra coworker pytest tests/test_agent_code_proposals.py -q`, require `test-and-build`, `coworker` and `ci-merge-gate` on the final head with zero mandatory skips. Resolve outstanding review threads only on evidence; do not merge, deploy or activate. Then implement CW-10 persisted code proposal, exact human approval and sandbox claim as a separate reviewed slice.

## CW-10 #394 immutable nested copy integrity — 14 October 2026

Second independent [P2](https://github.com/rumman52/Shuddho/pull/394#discussion_r4266920978) found that strict Pydantic reconstruction can accept a valid `limits`/input plain mapping and normalize it, leaving the original copied proposal mutable for downstream use. Added checks for exact `CodeComputeLimits`, `CodeInputVersion` and immutable tuple types **on the original object** before the strict round trip. Three new self-hashed negative cases test same-value limits/input mappings and mutable empty destinations. Latest source/test SHA `9285ff38408f9099bcf3d80c3794169589700507` before docs. Draft [PR #394](https://github.com/rumman52/Shuddho/pull/394), unmerged; exact final-head full required CI, review and authority/compatibility checks pending. No execution grant.

## CW-10 #394 strict typed validation review correction — 14 October 2026

CW-10 [draft PR #394](https://github.com/rumman52/Shuddho/pull/394) independent review [P2](https://github.com/rumman52/Shuddho/pull/394#discussion_r4266890920) found `model_validate()` can coerce untrusted copied timestamps and other field types instead of proving immutable typed identity. Revalidation now uses `strict=True`, rejects boolean schema version explicitly, and includes rehashed copied string-expiry/boolean-schema/float-CPU negative cases; latest source/test commit `db2aafa7feca94a399c816f1fc0437da51dded65` before documentation. Earlier `test-and-build` success was on an older SHA. Exact-final-head `test-and-build`, `coworker`, `ci-merge-gate` and independent review remain required. No code execution or production flag enabled.

## CW-10 copied inert review-envelope validation — 14 October 2026

**Live main baseline:** `9f8cf53a422ba5eee7d5a0772b2943328d3faaaa`, #392 immutable schema merged. New **independent** branch `codex/cw10-review-envelope-revalidate-20261014`; code/tests SHA `d3740983443bdf450422ebcab9b60e8ca9cdb9f7` before docs. [Task contract](CW10_COPIED_REVIEW_ENVELOPE_VALIDATION_2026-10-14.md).

**Bug and change:** although Pydantic `CodeProposalEnvelope` is frozen, unvalidated `model_copy(update=...)` can change forbidden egress/destinations/source checksum/nested CPU policy/expiry without model validators. `verify_reviewed_code_identity` now reconstructs and validates the entire existing proposal object before digest/owner/run/time/input ceiling checks, rejecting invalid copies even when a newly recomputed hash matches them; five corresponding no-authority regressions added. No DB approval, grant, credential, generated-code execution or production flag is created.

**Verification:** exact-final-head task tests and full required CI **pending**; independent review **pending**. CW-09 remains separately red on merged main, addressed by [draft PR #393](https://github.com/rumman52/Shuddho/pull/393) with its own mandatory CI and review. These are two independent draft changes; both must pass before claiming an integrated green repository.

| Evidence | CW-10 copied-envelope validator |
| --- | --- |
| Implemented | Separate source/test/docs branch |
| Repository verified | **Not yet: exact-head CI pending** |
| Staging verified | Not attempted |
| Production qualified | Not established |
| Activated | No; inert contract only |

**Next exact action:** Open CW-10 independent draft PR, run `tests/test_agent_code_proposals.py` and exact full CI, obtain independent review and fix any findings. Then move to persisted owner/run immutable proposal, human approval and sandbox worker claim (still unimplemented), only after preserving existing no-grant and user-supplied-Python behavior. No automatic merge/deploy/activation.## CW-09 #393 embedded runtime typed-schema P2 repair — 14 October 2026

Second independent [P2](https://github.com/rumman52/Shuddho/pull/393#discussion_r4266898374) on #393 found `runtime.schema_version = true` or `1.0` accepted by Python equality even after outer activation type hardening. Added `type(runtime.schema_version) is int and runtime.schema_version == 1` and two synthetic self-rehashed runtime-manifest negative tests, source/test SHA `06a172051e951b3a832374087d617d8a3353f8b2` before docs. Earlier tests on old head are **superseded**; request a fresh independent review and exact-final-head CI of browser no-skip, PostgreSQL, full coworker, test-and-build and merge gate. Branch remains draft/unmerged and default-off. CW-10 separate #394 is likewise draft and requires its own checks.

## CW-09 PR #393 independent P2 review fix — 14 October 2026

[#393](https://github.com/rumman52/Shuddho/pull/393) review [P2](https://github.com/rumman52/Shuddho/pull/393#discussion_r4266861068) found a malformed activation with JSON `true` or `1.0` could pass `schema_version == 1` through Python bool/float equality; corrected with exact integer type check and two synthetic negative regressions, source/test SHA `121280e82b9856366dec8ccf1f0a20ff810b2356`. Earlier CI on `6ec683d5` passed `test-and-build` and PG safety, but was superseded. **Require final-head `coworker` browser no-skip, `test-and-build`, `ci-merge-gate` and final review.** CW-10 independent [draft PR #394](https://github.com/rumman52/Shuddho/pull/394) closes a copied Pydantic immutable-schema trust-boundary bypass separately; do not conflate branches. No merge/deployment/activation in this continuation.

## 14 October 2026 — CW-09 merged-red mandatory CI and ledger review correction

**Verified at bootstrap:** `main` `9f8cf53a422ba5eee7d5a0772b2943328d3faaaa`; [PR #391](https://github.com/rumman52/Shuddho/pull/391) **merged** (`0e6ea7182ffae6e5bf8dbdfc4e229cb6472dcd46`), [PR #392](https://github.com/rumman52/Shuddho/pull/392) **merged** (`4248966e445f535a19027f6c3aa2d11a213ddd8e`), **no open PRs** before this correction. Historical entries below calling #391/#392 unmerged are superseded. PR #391 [exact-head workflow #38463696028](https://github.com/rumman52/Shuddho/actions/runs/38463696028) failed mandatory Agent browser test gate (21 passed, one `signed_client` **fixture not found** setup error); latest main [workflow #38465787058](https://github.com/rumman52/Shuddho/actions/runs/38465787058) also failed that gate. `test-and-build` passed in both, but `coworker` and `ci-merge-gate` failed. Production is **not qualified**.

**Review findings:** latest #391 [P1/P1/P2 security review](https://github.com/rumman52/Shuddho/pull/391#pullrequestreview-5509664548) identified missing canonical rollout `incident.change_reference` semantic match, acceptance of arbitrary non-Git deployment revision and acceptance of activation without version 1 schema. Prior rollout digest, post-deploy status chronology and kill-switch checks remain in place.

**Corrective source branch:** `codex/cw09-main-red-ci-ledger-review-repair-20261014` based on `9f8cf53a422ba5eee7d5a0772b2943328d3faaaa`, source/tests head `b4f5e0c32fcaa96c05c73aaf7b971a7481f7bb42` before documentation. [Task contract](CW09_MAIN_CI_RELEASE_LEDGER_CORRECTION_2026-10-14.md). Move the out-of-module authenticated manifest assertion into the actual API test fixture; browser mandatory suite remains no-skip. Add schema 34 review-bound incident, canonical Git SHA-1 and activation v1 enforcement, synthetic adversarial tests with rehashed documents. **No generated proof, provider operation, activation or changed model grants.**

| CW item | Integrated status | Unfinished verification/acceptance |
| --- | --- | --- |
| CW-05 owner-bound conversation | Existing integrated implementation | Actual staging replay, deletion and recovery |
| CW-06 steering/durable dispatch | Existing integrated implementation | Operated Temporal/late observation |
| CW-07 activity and reconnect | Merged previous PRs | Browser/mobile keyboard and reconnection staging |
| CW-08 context and memory | Merged previous PRs | Retention, source revocation and ownership staging |
| **CW-09 read-only browser** | Broker/read and controlled-release contracts merged, but **main CI red and schema34 review P1**; corrective isolated branch implemented | Final-head no-skip CI, reviewed release changes, bounded actual page content with private checksum/provenance, isolated worker DNS/SSRF/redirect tests and execution-time canonical eligibility |
| CW-10 immutable generated-code proposal | Initial inert envelope merged #392 | Actual immutable persistence, grant/approval binding and sandbox claim tests |
| CW-11 versioned skills | Existing static tool contracts only | Versioned reviewed manifest, constraints and budget authority controls |

| Evidence level | CW-09 merged-red correction |
| --- | --- |
| Implemented | Source/test changes on isolated branch |
| Repository verified | **Pending final-head CI + independent review** |
| Staging verified | **No** |
| Production qualified | **No** |
| Activated | **No**; defaults remain off |

**Next exact action:** Open draft PR; inspect full final-head `test-and-build`, `coworker` (PostgreSQL/Temporal/transactions/browser no-skip) and `ci-merge-gate`; request independent security review, correct any failures without loosening mandatory tests. Continue only other independent CW-09/CW-10/CW-11 work while release is gated. **No automatic merge, deploy or activation.**

## CW-10 first inert review-envelope contract — 14 October 2026

**Source bootstrap:** `main` `76a07600328d0c6ff0ed73b69d2c7933d38bf927`. CW-09 corrective [PR #391](https://github.com/rumman52/Shuddho/pull/391) was merged into main at `905a09c3a5e2931be46d9053ba4af09ecd331125`, while exact-final-head mandatory CI and security review still require confirmation; do not infer production qualification. Do not conflate this dependent CW-09 safety review with CW-10 work.

**Independent dependency-ready CW-10 preparatory slice:** `codex/cw10-immutable-proposal-envelope-20261014`, base `76a07600328d0c6ff0ed73b69d2c7933d38bf927`, initial source/test head `cd5463231a9a18043f26363b33777c2a251d7b4d`, latest source/test head `804a875ddfa4f3a104b21c301a6d039eb7131084` before final docs; second independent [P2 DST lifetime issue](https://github.com/rumman52/Shuddho/pull/392#discussion_r4263771173) fixed with UTC-normalized lifetime and regression. CW-10 branch reconciled onto main `905a09c3a5e2931be46d9053ba4af09ecd331125` using a two-parent merge preserving CW-09 progress after [independent P2 future-validity review](https://github.com/rumman52/Shuddho/pull/392#discussion_r4263712225) and not-before test; [draft PR #392](https://github.com/rumman52/Shuddho/pull/392), not merged; new frozen, strict `CodeProposalEnvelope`, exact source/content and owner-version SHA, full canonical review digest, offline `verify_reviewed_code_identity` comparing live owner/run/input versions, expiry and sandbox policy ceiling; zero grant or execution. Regressions: cross owner/run, modified code/input/limits/expiry, network expansion, bad hash. [Task contract](CW10_IMMUTABLE_INERT_PROPOSAL_ENVELOPE_2026-10-14.md). Draft PR and final-head checks pending. **This satisfies only the immutable-envelope contract precursor, not CW-10 operational completion.**

| Acceptance | Integrated/source evidence | Remaining proof |
| --- | --- | --- |
| CW-05–CW-07 conversation/activity | Existing integrated source and prior CI | Staging reconnection/erasure/steering |
| CW-08 selected context/memory | Integrated source | Operated revocation and retention |
| CW-09 brokered read-only browser | #387–#390 merged; #391 unmerged P1 repair | #391 final-head CI/review, private webpage content provenance, isolated egress staging and runtime release gate |
| **CW-10 reviewed generated code** | Inert schema/test review branch only | Database proposal authority, exact human approval, claim validation in existing sandbox, UI, isolation tests and release gate |
| CW-11 versioned skills | Existing fixed static registry | Versioned reviewed manifests after CW-10 core dependencies |

| Evidence level | CW-10 prep |
| --- | --- |
| Implemented | Bounded isolated source/tests/docs |
| Repository-verified | Not yet: draft PR exact-head CI pending |
| Staging-verified | No |
| Production-qualified | No |
| Activated | No: no generated-code route or approval exists |

**Next exact action:** Open CW-10 draft PR, request independent review, inspect exact-head Python tests, coworker mandatory gates and ci-merge-gate. Correct findings before code acceptance. Continue first actual persisted proposal+approval slice separately; never equate a pure validator with an execution permission.


## CW-09 merged release contract P1 corrective slice — 14 October 2026

**Current baseline at bootstrap:** `main` `76a07600328d0c6ff0ed73b69d2c7933d38bf927`. [PR #390](https://github.com/rumman52/Shuddho/pull/390) is **merged** despite three unresolved P1 automated-review findings and exact-final-head [CI #38458791465](https://github.com/rumman52/Shuddho/actions/runs/38458791465) still in progress on inspection. Historical section below refers to the PR as draft; that is superseded by live GitHub evidence. Previously merged #389 [CI #38456526299](https://github.com/rumman52/Shuddho/actions/runs/38456526299) passed required gates, but did not prove the new release contract.

**Repair:** `codex/cw09-release-attestation-repair-20261014`, base `76a07600328d0c6ff0ed73b69d2c7933d38bf927`, initial code/tests head `2e03cb331a8833826d9ffd5a92a015713fe57bb3`; latest source/test head `f07b6da0d416e0794f36155a1473bed0367bfee8` before final docs; exact enabled manifest and newly added deployment rollout digest, strict timestamp ordering, mandatory dedicated kill-switch regressions. PR #391 independent first review flagged [rollout binding P1](https://github.com/rumman52/Shuddho/pull/391#discussion_r4263640759), [stale status P1](https://github.com/rumman52/Shuddho/pull/391#discussion_r4263640771) and [rollback P2](https://github.com/rumman52/Shuddho/pull/391#discussion_r4263640779); all addressed in new source/tests, pending exact-head CI and renewed review. **Draft PR [#391](https://github.com/rumman52/Shuddho/pull/391)**, unmerged. Earlier PR-head `test-and-build` succeeded but was superseded by this test addition; requalify exact final head. Independent review of #390: (1) [P1 recovery/rollback](https://github.com/rumman52/Shuddho/pull/390#discussion_r4263411541), (2) [P1 schema34 missing](https://github.com/rumman52/Shuddho/pull/390#discussion_r4263411549), (3) [P1 manifest missing](https://github.com/rumman52/Shuddho/pull/390#discussion_r4263411559). The repair updates the existing recovery mapping, rollback mode, runtime manifest, HMAC schema 34 validation/append CLI and negative regressions. [Task contract](CW09_RELEASE_ATTESTATION_P1_REPAIR_2026-10-14.md). **No deployment, release proof or production activation.**

| Acceptance | Current source/PR integration | Remaining proof |
| --- | --- | --- |
| CW-05 owned conversations | Integrated source, prior repository checks | Operated owner erasure/duplicate replay |
| CW-06 dispatch, steering, cancellation | Integrated runtime | Real Temporal/recovery/late observation |
| CW-07 active chat/reconnect | #385 merged | Mobile/keyboard/events/reconnect |
| CW-08 context and memory | #384/#386 merged | Owned deletion and source revocation staging |
| **CW-09** read-only brokered Agent browser | #387-#390 merged; new P1 corrective review branch | **Exact-head full CI and independent review of schema34 repair**; bounded webpage text/private digest; isolated egress/SSRF/redirect staging; runtime release eligibility; human acceptance |
| CW-10 inert reviewed generated code | Existing sandbox accepts exact *user-provided* fenced Python | Immutable model-code proposal and exact owner/run/input/limits/egress approval |
| CW-11 reviewed versioned skills | Static code-owned tools | Manifest hashes/grant subset/version rollback |

| Evidence type | Release repair |
| --- | --- |
| Implemented | Branch source/tests/docs checkpoint |
| Repository-verified | **Pending final implementation SHA CI** |
| Staging-verified | Not performed |
| Production-qualified | Not established |
| Activated | No; `agent_browser_read` remains default off |

**Next exact action:** Open draft P1 repair PR and inspect full mandatory CI, especially `tests/test_agent_browser_release_attestation.py`, `tests/test_cohort_recovery_verification.py`, `tests/test_cohort_rollback_completion.py`, `tests/test_coworker.py`, and existing full browser/Temporal/PG suites. Request independent review, resolve findings on actual final SHA, keep no-merge/activation boundary. Continue independent CW-09/CW-10 work only after maintaining this checkpoint.

## CW-09 independent browser.read release gate — 14 October 2026

**Authoritative repository bootstrap:** `main` `d6ba9c183860284207cafd5f8cc2052205080837`; no open PRs at bootstrap. [PR #389](https://github.com/rumman52/Shuddho/pull/389) was already **merged** (the earlier 14 October checkpoint below calling it an unmerged draft is historical and superseded). The exact-head [CI #38456526299](https://github.com/rumman52/Shuddho/actions/runs/38456526299) had successful `test-and-build`, mandatory PostgreSQL/conversation race checks **and** dedicated CW-09 brokered Agent browser suite; its broader `coworker` and merge gate were still in progress when last inspected. Main [CI #38457535194](https://github.com/rumman52/Shuddho/actions/runs/38457535194) also remained in progress. CI success is not staging qualification or permission to activate.

**First dependency-ready gap:** the code-owned `browser.read` flag exists, but controlled release had no independent staging/capability/rollback/activation evidence entry. **Branch:** `codex/cw09-agent-browser-release-contract-20261014`, based on `d6ba9c183860284207cafd5f8cc2052205080837`. **Initial implementation/test SHA:** `a069daf5d2567e84d5bff3c1e525553e1d98d9b4`. **Current code+test SHA:** `f2c8c4099674000a0930c60d09560efe4a2b7e4f` before final docs, including exact gate-map test correction for new default-off key. **Draft PR [#390](https://github.com/rumman52/Shuddho/pull/390)**, unmerged. Initial PR-head `test-and-build` failed only the canonical feature-gate equality assertion (new independent `agent_browser_read: false` absent in old expected map); the test remains strict and has been corrected. Latest final-head CI must be rechecked after this documentation checkpoint. **Task contract: [CW09_AGENT_BROWSER_RELEASE_CONTRACT_2026-10-14.md](CW09_AGENT_BROWSER_RELEASE_CONTRACT_2026-10-14.md). Draft PR not yet opened at this checkpoint; inspect actual GitHub head and CI when reviewing.

**Change:** the canonical rollout gate now recognizes **default-off** `agent_browser_read`, requiring the existing `browser`, `runtime_v3` and `connector_trust_boundary` capabilities, a distinct staged browser Agent read evidence gate, a separate `SHUDDHO_AGENT_BROWSER_READ_ENABLED=false` rollback, and `agent_browser_read_verified` activation ledger proof. Templates remain pending/false. Tests cover absence/default-off, dependency, rollback, and independent activation proof. This patch **does not** add page content capture, mint approval, or enforce live release proof at tool execution; no authority is granted by documentation or rollout registration alone.

| Architecture/core acceptance | Integration evidence | Remaining acceptance |
| --- | --- | --- |
| CW-05 owned conversation | Merged existing source and prior repository checks | Staging replay/privacy/erasure |
| CW-06 dispatch and steering | Merged source and durable dispatch | Operated cancellations/races and UX |
| CW-07 active chat/reconnect | Merged #385, prior exact-head PR CI | UI mobile/keyboard/event cursor |
| CW-08 context/memory | Merged #384/#386, previous exact-head CI | Staging source revocation and memory lifecycle |
| **CW-09 read-only browser** | Merged #387/#388/#389; #389 core safety tests green, full checks pending | New release contract in isolated branch, full content capture and private hash, execution-time canonical eligibility, isolated worker egress/cancel security evidence |
| CW-10 reviewed generated Python | No signed inert code proposal envelope | Proposal hash/approval/sandbox claim and tests |
| CW-11 versioned skills | Static tool contracts only | Reviewed manifest + version/grant subset |

| Evidence level | CW-09 release contract |
| --- | --- |
| Implemented | Review branch with source/templates/tests/docs |
| Repository-verified | **Pending exact final-head CI** |
| Staging-verified | **No** |
| Production-qualified | **No** |
| Activated | **No**; both broker and Agent read flags remain default off |

**Review/next action:** Open independent draft PR; verify exact-head `test-and-build`, `coworker` and `ci-merge-gate`, plus explicit `tests/test_release_contract.py`. Obtain independent review and resolve findings without weakening tests. No auto-merge or flag activation. Continue CW-09 content-capture/private provenance and runtime release enforcement after this contract, and subsequently CW-10/CW-11 in dependency order.

## CW-09 receipt/cancellation correction — 14 October 2026

**Refreshed main:** `fd4cb99a2d7925bcdd0faafad5a3eae041496a80`, after merged [PR #388](https://github.com/rumman52/Shuddho/pull/388). Unlike the historical entry below that calls #388 draft/unmerged, **it is merged**, but [exact-head CI #38432751315](https://github.com/rumman52/Shuddho/actions/runs/38432751315) and [main CI #38436567016](https://github.com/rumman52/Shuddho/actions/runs/38436567016) failed. In PR CI `test-and-build` passed; mandatory PostgreSQL conversation step failed (59 pass, 1 failure, OAuth test setup missing); `coworker` stopped before mandatory CW-09 browser tests; `ci-merge-gate` failed. The merged PR's final automated review identified a remaining **P1 BrowserCommand-before-BrowserSession row-lock inversion** in `finish_invocation`.

**Chosen first dependency-ready task:** Repair exact-session-before-command locking at browser receipt settlement, and correctly configure the real PostgreSQL race tests. **Base:** main `fd4cb99a2d7925bcdd0faafad5a3eae041496a80`. **Branch:** `codex/cw09-receipt-lock-postgres-fixture-20261014`. **Initial implementation+test SHA:** `7afabac1dc6c1fdada5ffdfe20994c60a0cc3aa9`. **Current source/test SHA:** `67df97ab0e125e48e18d3b36a143cf59af98d6b5` before final docs; independent PR #389 review flagged that a cancellation-only race does not lock an already succeeded command, so added an actual PostgreSQL `SELECT ... FOR UPDATE` session-before-command ordering assertion in addition to concurrent receipt/cancel coverage. **Draft PR [#389](https://github.com/rumman52/Shuddho/pull/389)**, unmerged. **Task contract:** [CW09_RECEIPT_CANCELLATION_LOCK_REPAIR_2026-10-14.md](CW09_RECEIPT_CANCELLATION_LOCK_REPAIR_2026-10-14.md). A draft PR will link this branch; never assume it is merged. Configuration uses the existing simulated test OAuth values without bypassing validation; added actual concurrent PostgreSQL receipt/revoke regression, preserving no late receipt and one command invariants.

| Acceptance item | Source / integration status | Unmet evidence / next action |
| --- | --- | --- |
| CW-05 owner messages | Existing integrated ledger | Staging identity/replay and deletion |
| CW-06 dispatch/cancel | Existing integrated source | Operated revocation/steering recovery |
| CW-07 activity continuity | PR #385 merged; prior final-head CI successful | Accessibility/reconnect/event-level cursor |
| CW-08 owner-scoped context | PRs #384/#386 merged with prior successful PR-head CI | Full memory and source-retention qualification |
| **CW-09 brokered read** | PR #387/#388 **merged despite failing mandatory CI**; current receipt/fixture safety repair isolated on review branch | Exact-head CI including real PostgreSQL/browser with no skips; human security review; bounded actual page content + private hash; isolated-worker staging and release eligibility |
| CW-10 generated-code proposals | Only existing sandbox foundation | Immutable inert code review/approval envelope |
| CW-11 reviewed skill manifests | Static tool registry | Version/hash/rollback with fixed authority |

| Evidence level | CW-09 current correction |
| --- | --- |
| Implemented | Review branch, code/test/doc changes |
| Repository-verified | **No**; final-head CI pending |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | No change; independent browser tool flag remains default off |

**Next exact action:** Open the draft PR, inspect exact-head GitHub `test-and-build`, `coworker` PostgreSQL & Agent browser no-skip gates, `ci-merge-gate`, obtain independent review, fix failures, retain blocked production state. Then continue independently dependency-ready CW-08/CW-10 preparation if infrastructure prevents operating CW-09.

## CW-09 post-merge safety recovery — 13 October 2026

**Authoritative bootstrap:** current `main` `8de8aa9bb672f0b77ddb250e3718bc3ae060dfbd`. [PR #387](https://github.com/rumman52/Shuddho/pull/387) was merged at this revision **with failed required exact-head CI** ([run 38412412901](https://github.com/rumman52/Shuddho/actions/runs/38412412901): `test-and-build` pass; `coworker` fail, 1/9 CW-09 mandatory test failed; merge gate fail). Postmerge main [CI 38414646497](https://github.com/rumman52/Shuddho/actions/runs/38414646497) also failed the same gate. Historical lower entries that say PR #387 was unmerged are superseded by this dated correction. No open PR existed when this repair was selected.

**First dependency-ready task:** CW-09 correctness and safety repair before CW-10/11. Five unresolved automated review findings from PR #387 were triaged: (1) cancel broker command with owning Agent, (2) release Agent sessions after receipt, (3) terminally persist attempted worker interaction, (4) Bangla read intents, (5) browser-read questions. The failing test observed an eligible read classified as `unsupported` because previous route ordering allowed other rules to block it.

**Work branch:** `codex/cw09-postmerge-safety-repair-20261013`, based on `8de8aa9bb672f0b77ddb250e3718bc3ae060dfbd`. **Initial implementation/test SHA:** `4a3698db81c00a65c3865f5b93567e23aceb7f34`. **Latest implementation/test SHA:** `d742870d2ce3deef9c1af27518722f9c975f606b` before this checkpoint, also aligning the browser worker-control poll to canonical BrowserSession→BrowserCommand locks and adding a concurrent PostgreSQL Agent cancellation/work-control regression. Earlier source `581f5b63c0db02a1ee59c682c2a3a4acb0062dff` addressed malformed interaction evidence and multilingual intent. The prior revision `e1068cbfea9389a45de5e2d793c8630d43e3496a` added a revoked-session receipt race regression. **Draft PR [#388](https://github.com/rumman52/Shuddho/pull/388)**, still unmerged. **Contract:** [CW09_POSTMERGE_SAFETY_REPAIR_2026-10-13.md](CW09_POSTMERGE_SAFETY_REPAIR_2026-10-13.md). Verify mandatory CI against the latest exact PR head **after this documentation checkpoint**; earlier workflow attempts may be cancelled. The patch strengthens the **existing** Agent and browser ledgers; no replacement engine, migration, live egress or provider actions.

| Workstream item | Current source/integration | Missing evidence and next work |
| --- | --- | --- |
| CW-05 owner message ledger | Merged established source | Operated race/retention and source lifecycle |
| CW-06 conversation dispatch | Merged established source | Operated cancellation/steering and late worker checks |
| CW-07 owned activity cursor | Merged PR #385, prior successful PR CI | Real UI reconnect/mobile/keyboard/event cursor |
| CW-08 selected context/memory | Merged PRs #384/#386, prior successful PR CI | Staging revocation/use races, broader consent lifecycle |
| **CW-09 typed browser** | PR #387 merged **without passing CI**; corrective code on isolated branch only | Final-head CI with no skips, independent review of five findings, real isolated-worker/egress tests, captured webpage content/source digest, canonical release eligibility |
| CW-10 reviewed generated code | Sandbox exists, no immutable approved proposal | Store review/immutable hash envelope and sandbox claim in independent branch |
| CW-11 reviewed skills | Static registry, no reviewed manifest | Validated versioned manifests and authority subset |

| Evidence level | CW-09 correction |
| --- | --- |
| Implemented | Branch only, review pending |
| Repository-verified | **No**; exact-final-head GitHub checks required |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | No new activation; browser tool still defaults off |

**Verification and next exact action:** Open corrective draft PR, verify `test-and-build`, `coworker` including required `tests/test_agent_browser_tool.py` without skips, and `ci-merge-gate` on the final PR implementation revision. Inspect logs for any failed assertions and adjust code/tests only to preserve documented intent. Obtain an independent security review, then run frozen real isolated-worker staging SSRF/cancel/takeover/egress tests. Do not auto-merge or activate. Follow CW-09 with independent dependency-ready CW-10/CW-11 review work when this is repository-verified.

## CW-09 default-off Agent browser metadata read — 13 October 2026

**Refreshed baseline:** `main` at `f5c11ec7db35721190b67212695e7612af63f09f`, with [CW-08 source-consent PR #386](https://github.com/rumman52/Shuddho/pull/386) merged and exact-head [CI #38404758754](https://github.com/rumman52/Shuddho/actions/runs/38404758754) successful; latest main [CI #38408371736](https://github.com/rumman52/Shuddho/actions/runs/38408371736) still in progress when inspected. No open PRs at bootstrap.

**Current bounded CW-09 task:** Register default-off typed `browser.read` as a Runtime v3 tool, qualify explicit user-authored read requests at the public Agent router, and connect it to the existing owner-scoped supervised broker and worker. Deterministic `explicit_browser_url` derives one HTTPS URL from the user's *original run goal*, not a model-chosen destination. Runtime creates/reuses a reserved `agent:<run_id>:<ordinal>` browser session, atomically prepares one read-only navigate command, and persists the broker-verified page URL/title/time/hash as **untrusted metadata-only**, not full page text or HTML capture. No new run or transaction ledger. A separate `SHUDDHO_AGENT_BROWSER_READ_ENABLED` flag defaults off and requires existing browser/v3/intelligent planner dependencies.

**Base:** `f5c11ec7db35721190b67212695e7612af63f09f`. **Branch:** `codex/cw09-brokered-read-metadata-20261013`. **Initial source + regression SHA:** `4d7c2521bdf083177c9f34cd8693007cf75ef535`. **Latest implementation SHA:** `bf155122aa50060fcb682eb978f7a9a8cd5bade3` before this checkpoint commit, including public read-only admission routing and broker no-interaction enforcement. **Final review PR:** [draft #387](https://github.com/rumman52/Shuddho/pull/387), unmerged. Prior CI was superseded by code edits; inspect the GitHub workflow run matching the **current PR head** for `test-and-build`, `coworker`, dedicated mandatory CW-09 browser suite and `ci-merge-gate`; no such final-head pass is yet claimed. **Contract:** [CW09_BROKERED_AGENT_READ_METADATA_2026-10-13.md](CW09_BROKERED_AGENT_READ_METADATA_2026-10-13.md). **Draft PR:** [#387](https://github.com/rumman52/Shuddho/pull/387), still unmerged; dedicated no-skip test step added in `.github/workflows/ci.yml`. Final implementation/test SHA preceding this documentation checkpoint: `c596a3e9ed4af211fbfaf4e65e3413079d53ae45`. Latest exact-head CI must be refreshed after this commit; older runs were superseded.

| Item | Verified/current state | Pending acceptance |
| --- | --- | --- |
| CW-05 owned messages | Merged ledger/owner source + prior repository tests | Staging races/replay and deletion |
| CW-06 dispatch/cancel | Merged routing/dispatch, revision cancellation | Operating steering and terminal precedence |
| CW-07 activity continuity | PR #385 merged, full final-head CI passed | Mobile/keyboard/reconnect operated evidence, event-level cursor |
| CW-08 pinned context/memory | PR #384 and #386 merged, exact-head PR CI passed; prior-task implicit read sealed for conversations | Full lifecycle/revocation races, broader purpose consent, multilingual human acceptance |
| CW-09 browser read | Current branch: metadata-only typed v3 tool with default-off flag/broker command+receipt | Exact-head CI, actual page-body/private digest, real worker/SSRF/redirect/egress and release gates |
| CW-10 generated code | Sandbox foundation exists; approval-bound immutable code proposal not completed | Independent code-proposal and sandbox approval route |
| CW-11 skill manifests | Static skill registry; reviewed manifests not completed | Version/hash, authority subsets, compatible rollback |

| Evidence | CW-09 metadata slice |
| --- | --- |
| Implemented | Branch-only code + synthetic worker/broker tests |
| Repository-verified | Pending exact-final-head no-skip GitHub Actions |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | **No** — flag remains default-off |

**Review:** Self-review only. Explicit user URL and reserved server resource identity reduce planner authority; test covers denied destinations and replay. A separate full content capture and canonical release eligibility policy still need integration; metadata hash is explicitly not claimed as web content hash. An independent security reviewer and frozen live isolated-worker evidence are mandatory before activation. Existing PHP/Node/web dependencies, transaction provider and writing/DeepSeek configuration remain unchanged.

**Next exact action:** Open draft PR and verify current-head `test-and-build`, `coworker`, `ci-merge-gate`, and targeted `tests/test_agent_browser_tool.py`. Resolve any failure, obtain independent review, then implement CW-09 bounded page-body capture/private checksum on its own review slice or advance independent CW-10 proposal contract. Do not merge or activate automatically.

## CW-08 explicit conversation source-selection boundary — 13 October 2026 (Asia/Dhaka)

**Repository bootstrap:** `main` `b2a6920d2fea10dfc5a813746e19c7241597846b`. [CW-07 PR #385](https://github.com/rumman52/Shuddho/pull/385) was **merged**; its final-head [CI #38402405574](https://github.com/rumman52/Shuddho/actions/runs/38402405574) was still in progress as inspected, so completion of its broad checks is not inferred. New main [CI #38403290676](https://github.com/rumman52/Shuddho/actions/runs/38403290676) also in progress. No other open PRs at bootstrap.

**Selected dependency-ready task:** CW-08's selected-only conversation planning context. Source finding: `ContextService._resolved` included lexical-matching prior completed/needs-input `Task` content from the owner workspace even when a conversation message carried `selected_sources=[]`. The conversation admission ledger bound only selected document versions; this prior-task inclusion lacked message source consent. **Repair** bypasses implicit prior-task retrieval for server-created conversation Agent runs, retaining standalone Agent compatibility and already-enforced conversation document pin, owner, revocation and checksum checks.

**Base and branch:** `main` `b2a6920d2fea10dfc5a813746e19c7241597846b`; `codex/cw08-explicit-conversation-context-20261013`. **Implementation/regression SHA:** `00cbe0d8dbe32a242dc458c83fc37ed383941d52` before documentation. **Task contract:** [CW08_EXPLICIT_CONVERSATION_CONTEXT_2026-10-13.md](CW08_EXPLICIT_CONVERSATION_CONTEXT_2026-10-13.md). **Review:** [draft PR #386](https://github.com/rumman52/Shuddho/pull/386), original review head `bd5e5bfaa7fdbc545e22e13d9b2a6e61e55ea308` before this final checkpoint; required exact-current-head CI [run 38404234208](https://github.com/rumman52/Shuddho/actions/runs/38404234208) was in progress and will be superseded by new commits. Always refresh the actual PR head and checks before closure. A same-owner real completed task with private notes/draft is excluded from an unselected conversation's planner and context while remaining available to existing direct Agent continuity.

| Scope requirement | Integration/evidence | Unmet acceptance |
| --- | --- | --- |
| CW-05 messages | Existing merged implementation, prior tests | Operated consent/replay/race/deletion qualification |
| CW-06 routing and revisioned cancellation | Existing merged implementation | Steering and late/cancel operational checks |
| CW-07 resumable activity and UI | PR #385 merged; final-head broad CI pending when inspected | Verify exact-main CI, independent/mobile/reconnect and combined event cursor |
| CW-08 context and reviewable memory | Pinned source integrity #384 merged; new prior-task consent repair only on review branch; memory edit/delete UI exists | Exact-head CI, source revocation race, explicit whole-context consent, Bangla/English task evidence |
| CW-09 typed browser read | Isolated browser broker/worker but no Agent `browser.read` registered at inspection | Typed default-off dispatch and isolated SSRF/takeover validation |
| CW-10 reviewed generated code | Sandbox foundation only | Stored immutable approved code-to-execution envelope |
| CW-11 versioned skill manifests | Static skill registry only | Validated reviewed manifest and rollback after CW-09/10 |

| Evidence level | This CW-08 slice |
| --- | --- |
| Implemented | On isolated branch only |
| Repository-verified | Pending exact-final-head PR `test-and-build`, `coworker`, `ci-merge-gate`; local full-repo execution unavailable |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | No flags or external authority changed |

**Review:** Self review before PR; no independent review claimed. Owner-bound conversation prefix only comes from server dispatcher and is already protected at worker-use context source validation. Existing standalone Agent retrieval intentionally unchanged. The cursor in merged CW-07 remains message-based, not per-Agent-event. No new schema, orchestration engine, ledger, provider credential, grant or rollout.

**Next exact action:** Open draft PR for `codex/cw08-explicit-conversation-context-20261013`, compare exact PR SHA and required CI, resolve failures without weakening tests, seek independent review and only then classify repository verification. Continue an independent CW-08 lifecycle or CW-09 browser capability slice without merging or production activation.

## CW-07 Architecture/Core Agent — owned activity cursor continuation (13 October 2026)

**Fresh repository evidence:** `main` at `4b369fa99b9a7c4784f5060aa3399a58e340815f`. [CW-08 source-pin PR #384](https://github.com/rumman52/Shuddho/pull/384) is **merged**, and its exact-final-head [CI #38395801164](https://github.com/rumman52/Shuddho/actions/runs/38395801164) passed. Main CI [38400940687](https://github.com/rumman52/Shuddho/actions/runs/38400940687) was in progress at bootstrap; a skipped separate run does not count as green. There were no open PRs when selecting this new bounded slice.

**Active task:** CW-07 — durable owner-bound cursor pagination for the read-only continuous-chat activity projection. Main only exposed latest-N activity, so older launched work cards were missing on reconnect for longer conversations. The current slice adds `after=start` + forward owner/conversation-bound cursor, `next_cursor`, `has_more`, HTTP support, frontend paginated replay and regression tests, without another run ledger or side effect. Omitted `after` retains latest-N polling for run-state changes with no new message. The cursor is an owned read checkpoint, not a permission grant or durable all-events stream.

**Review branch:** `codex/cw07-owner-bound-activity-cursors-20261013`. **Base:** `4b369fa99b9a7c4784f5060aa3399a58e340815f`. **Initial implementation/test:** `99d3934803227721f4d2e0dac71b65686be52329` (prior to documentation). **Contract:** [CW07_OWNER_SCOPED_ACTIVITY_CURSOR_2026-10-13.md](CW07_OWNER_SCOPED_ACTIVITY_CURSOR_2026-10-13.md). PR and final exact-head CI must be read from GitHub once created.

| Acceptance item | Current code/integration | Remaining qualification |
| --- | --- | --- |
| CW-05 message ownership | Existing main source and prior CI | Operated replay, deletion and PostgreSQL races |
| CW-06 routing/admission/cancel | Merged CW-06 #383 and durable dispatch | Steering, terminal-order and operated cancellation |
| CW-07 unified activity | Owner cursor + frontend history replay on current review branch only | Exact-head CI, independent review, mobile/keyboard/reconnect and live run-state proof |
| CW-08 workspace/memory | Merged pinned-source #384; existing memory edit/delete and manifest | Source-use races, bounded context + human multilingual acceptance |
| CW-09 browser | Broker/workers exist but no registered v3 `browser.read` | Gated typed tool, SSRF, takeover, worker tests |
| CW-10 reviewed generated code | Sandbox exists | Immutable approved proposal-to-execution envelope |
| CW-11 skill manifests | Static skills exist | Reviewed manifest validation and authority subset |

| Evidence level | CW-07 cursor slice |
| --- | --- |
| Implemented | Yes, only on isolated review branch |
| Repository-verified | Pending exact-final-head mandatory GitHub Actions; no local full-repo pytest/build |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No authority, provider, flag, paid resources or production changes |

**Next exact action:** Open draft PR for CW-07 branch, inspect final-head `coworker`, `test-and-build` and `ci-merge-gate`, correct test/source issues and seek independent code review. Do not merge automatically. Continue remaining dependency-ready CW-08/CW-09 implementation separately after evidence checkpoint. No success percentage inferred from task labels.

## CW-08 Architecture/Core Agent continuation — 13 October 2026 (Asia/Dhaka)

**Source baseline:** `main` at `fb3c8994edc2d6a7db2781b9a798a21a7a9beec6`. Main CI [38393963804](https://github.com/rumman52/Shuddho/actions/runs/38393963804) was in progress when inspected; no claim of successful final-head CI is made for it. Earlier CW-06 [PR #383](https://github.com/rumman52/Shuddho/pull/383) is **merged**; final PR SHA `1312877604520fec49e00970d12ff14a4b9c7294` passed [CI 38391641647](https://github.com/rumman52/Shuddho/actions/runs/38391641647). No open PRs appeared before this CW-08 work.

**Selected task:** CW-08 worker-time conversation source-pin enforcement, scoped to a single reviewable code slice. `ConversationMessage.selected_sources` already preserves exact version/hash/owner selection, but `AgentRun.input_versions` records only IDs and `ContextService._run_and_sources` previously trusted the *current* DocumentVersion row at worker time. A same-ID in-place changed digest/version could bypass the admitted selection. The new shared validator revalidates the original owner-scoped message, document pin, run link and live resource status both at `AgentRepository.worker_run` entry (v1/v2/v3) and at planner context load; pre-existing non-conversation runs retain their former logic.

**Branch:** `codex/cw08-conversation-pinned-context-20261013` from `fb3c8994edc2d6a7db2781b9a798a21a7a9beec6`. **Implementation/test head:** `cea2c57eeb1ddd2c38526c9a2e8475333526a11f` before checkpoint update. **Task contract:** [CW08_CONVERSATION_SOURCE_BINDING_2026-10-13.md](CW08_CONVERSATION_SOURCE_BINDING_2026-10-13.md). **Review PR:** [draft #384](https://github.com/rumman52/Shuddho/pull/384); exact final head and CI are verified on the PR.

| Acceptance task | Source evidence level | Remaining gate |
| --- | --- | --- |
| CW-05 owner-scoped messages | Existing implementation and prior main CI | Staging race/replay/deletion qualification |
| CW-06 bounded message dispatch/cancel | Merged CW-06 routing repair, previously green exact-head CI | Full steering and operational cancellation proof |
| CW-07 continuous activity | Existing UI and owner-scoped activity projection | Cursor/reconnect/mobile and staging qualification |
| CW-08 context/memory | Existing source and memory controls; new exact conversation pin worker check on review branch | Final-head CI, live revoke/replacement race, remaining bounded context/memory lifecycle and quality review |
| CW-09 browser read | Existing broker/isolated worker, no registered Agent `browser.read` | Gated typed integration and isolated-worker testing |
| CW-10 reviewed generated code | Existing sandbox control plane | Immutable reviewed code proposal/approval/execution binding |
| CW-11 skill manifests | Existing static versioned work skills | Reviewed manifest hashes, authority subsets and compatible rollback |

| Evidence level | CW-08 source-pin task |
| --- | --- |
| Implemented | Branch-only implementation + focused regression cases |
| Repository-verified | Pending required exact-final-head PR CI; local full-repository pytest not run |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | None; no grant, provider or rollout changed |

**Next exact action:** Inspect draft PR #384 exact-PR-head `coworker`, `test-and-build` and `ci-merge-gate`; fix source defects without silencing tests; obtain independent review. Then continue remaining dependency-ready CW-08 and CW-09 code slices in separate PRs. No merge or production activation is authorized by this execution prompt.


## Current Architecture/Core Agent checkpoint — 13 October 2026

Refreshed default branch: `main` at `339d6924b244c0bb1641764dabd68c4f55488bb3`. Exact-main CI [run 38338728994](https://github.com/rumman52/Shuddho/actions/runs/38338728994) passed its coworker, test-and-build and merge-gate jobs. No open PR was returned before beginning this slice.

CW-06 contract gap: the `report.create` registered tool declares public capability `report` but internal durable task skill `report_email`. The old single-tool router emitted the internal skill into public route decisions while `tests/fixtures/core_agent_route_cases.jsonl` expects `report`. This finding is based on current canonical tool/route source, not historical completion percentages.

Review branch `codex/cw-core-router-report-contract-20261013`, [draft PR #383](https://github.com/rumman52/Shuddho/pull/383), initial implementation/test head `aeb00b2cdd5994e3e8236bc049d2f916f9ad7862`. Changed only the single-tool router capability mapping to server-owned route intent and added a regression asserting that the public `report` route still uses `report.create` and the legacy `report_email` skill. The reviewed task contract is [CW06_REPORT_ROUTE_CONTRACT_2026-10-13.md](CW06_REPORT_ROUTE_CONTRACT_2026-10-13.md).

| Evidence level | Status |
| --- | --- |
| Implemented | On isolated review branch; not integrated into `main` |
| Repository-verified | Pending exact-final-head PR CI; local package tests not run in this GitHub connector environment |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | No provider, capability, or production activation |

Scope: CW-05–CW-11 Architecture/Core Agent. CW-01–04 supply prerequisite evidence, not renewed assignments. The merged CW-09–14 qualification registry is a default-off metadata foundation, not a working browser/generated-code/skill runtime or live release qualification. Preserve prior transaction checkpoints below as historical. Pending CW-08 context/memory integration and CW-09–11 actual implementations must be rechecked against live source; staging/billing/provider/human evidence cannot be inferred from CI.

Acceptance inventory based on inspected `main` source and available CI (per-task staging and full acceptance remain separate):

| Task | Main source / current state | Next unmet acceptance / evidence |
| --- | --- | --- |
| CW-05 | Conversation schemas, repository and durable message tests exist; main CI includes PostgreSQL conversation races | Complete operated owner/deletion/replay qualification on a frozen staging release |
| CW-06 | Atomic conversation dispatch and revision-checked cancellation exist; one report public-route mismatch repaired only on PR #383 | Verify PR exact-head CI; inspect missing/non-mutating steering contract and late-result precedence |
| CW-07 | Conversation UI and read-only activity projection exist | Verify reconnect/mobile flows and add durable owner-scoped activity cursor if canonical contract remains unmet |
| CW-08 | Source admission validation and read-only workspace manifest exist | Prove worker-use revocation/version checks, reviewable memory edits/deletion and bounded multilingual context |
| CW-09 | Isolated browser broker/worker foundation exists; no `browser.read` in core `agent_tools.py` | Register and safely wire typed default-off read-only tool; prove SSRF/ownership/takeover boundaries |
| CW-10 | Isolated sandbox control plane exists | Store immutable generated-code proposals and exact reviewed approval binding before execution |
| CW-11 | Static versioned `WorkSkill` definitions exist | Validate reviewed manifest hashes, tool authority subset and compatible rollback after CW-09/10 |

These are discovery statuses, not assertions that each full CW acceptance suite has passed. A successful green CI run on a revision does not substitute for missing staging, adversarial or human quality evidence.

Next exact action: inspect exact-head GitHub Actions on PR #383 and obtain independent review; if a check fails, repair code without weakening expected behavior. Then choose the next smallest dependency-ready CW-08/09/10/11 capability slice while keeping external activation gated.


## Current Transactions qualification recovery — 13 October 2026 (Asia/Dhaka)

Refreshed main: `fb1a08059cd242f5da4d72dbf72da0c6971bfe30`, latest merge PR #379.
PR #375 process recovery, #376 attestation chronology/file binding and #377's
checkpoint are now merged. There were no open PRs at the start of this continuation.
[Exact-main CI 38292932568](https://github.com/rumman52/Shuddho/actions/runs/38292932568)
failed both required upstream jobs: lightweight collection imported optional
SQLAlchemy without a guard, and Temporal `before_claim` recovery hit the workflow
deadline. The merged boundary/reconciliation tests were absent from the explicit
heavyweight transaction safety command.

Branch `codex/transactions-ci-recovery-20261013` repairs that qualification boundary:

Review: [PR #380](https://github.com/rumman52/Shuddho/pull/380). Initial implementation
head: `7ae84f757a696116f3aade9aaeeced296b7078a3`. This checkpoint precedes the final
required CI result; the PR records its final head/run and review readiness.

- Optional-dependency collection follows the existing lightweight/heavyweight split.
- All newly merged execution, reconciliation and mutation-guard test modules are
  mandatory in the safety JUnit report, with collection and zero-skip checks.
- A parent-owned barrier keeps the restarted real Temporal worker connected but
  not polling while only the interrupted activity timeout/first retry is advanced.
  Automatic result time skipping is then disabled. Production workflow timeouts,
  authorization, durable claims, receipt validation and uncertainty remain unchanged.
- Enabling the omitted reconciliation test reproduced a nonexistent fixture field
  (`SimulatedGoogle.provider`). Its corrected receipt assertions check the actual
  configured Google provider, confirmed state, one send and another owner's 404.
- Added execution diagnostics identify the exception class before the Temporal
  activity redacts its error; that diagnostic prints no raw SQL parameters,
  credentials or message contents.

Local verification: the lightweight project suite passed **1,052 tests, 65 optional
skips** (8.56 seconds); the final combined process/Temporal/HTTP/safety/boundary run
passed **41 tests with one PostgreSQL-only admission-race skip** (60.14 seconds).
The mandatory safety subset passed **25 tests, zero skips** (4.88 seconds), and
its gate confirmed collection from all five required modules. Neighboring transaction/
action/permission/gate checks passed **103 tests** (46.58 seconds).
The initial combined run also failed before its first crash barrier;
four isolated Temporal cases and the final combined run passed after adding safe
setup diagnostics. These local SQLite runs do not establish PostgreSQL qualification.
The required exact-head CI must run all 17 process cases on real PostgreSQL and
all 25 transaction safety cases with zero mandatory skips before review readiness.

| Evidence level | Current status |
| --- | --- |
| Implemented | Bounded test/CI repair exists on the review branch |
| Repository-verified | Pending exact final-head required CI; record its SHA/run in the PR |
| Staging-verified | Not established by this continuation |
| Production-qualified | Pending operated matrix, selected-provider evidence and release reviews |
| Activated | No capability/provider/production activation |

PR #379's `TransactionMutationGuard` is an unused, process-local qualification helper:
its unit tests do not establish distributed provider deduplication. Production
authority remains the existing durable ExternalAction boundary. Complete Transactions
qualification still requires the full sixteen-fault operated staging matrix and
selected real-provider receipts/counters; shopping/travel registration remains disabled.

Next exact action: independently review this repair, inspect exact final-head CI,
then collect the controlled staging/provider evidence on a frozen matching release.
See [the bounded task plan](../superpowers/plans/2026-10-13-transactions-qualification-recovery.md).

## Historical process-recovery checkpoint — 12 October 2026

Reviewed main `1c41907594dd8dd93a6eac747494d5491587b709` (PR #373); merged-main CI #1368
passed `test-and-build`, `coworker` and `ci-merge-gate`. Draft PR #374 remains a separate
offline CW-02–04 witness-gate proposal. Historical entries below predate newer merges.

Branch `codex/cw02-transaction-process-recovery-20261012` implements the next CW-02 slice:
counted real HTTP to a loopback provider, abrupt disposable worker loss at four commit/
dispatch boundaries, the same four boundaries in real Temporal activities, six provider
failure/uncertainty cases, PostgreSQL public-API duplicate admission, hard API loss after
commit and actual Temporal-server unavailability/outbox recovery. Seventeen executable
tests are mandatory in the heavy CI job, with PostgreSQL required and zero skips allowed.

Review PR: [#375](https://github.com/rumman52/Shuddho/pull/375). Initial implementation
commit: `b8a5a2b2130991b383cc8a9bfd16472b903a8ed4`; the follow-up also binds restarted
Temporal worker readiness before unlocking its virtual retry clock. The PR check suite
records the exact final head and required CI evidence; this checkpoint precedes that result.
CI run `38240791675` remained in rendering dependency installation for more than fifteen
minutes. The final follow-up makes apt/debconf/needrestart noninteractive and bounds the
installer to ten minutes, triggering a fresh runner without removing any required check.
The cause of the stalled installer was not observable from unfinished GitHub job logs.

The final focused local process/Temporal/HTTP plus existing safety/matrix run passed
35 tests with one explicitly PostgreSQL-only skip (46.14 seconds). The new module itself
passed sixteen tests and skipped its PostgreSQL admission race. Surrounding transaction/
permission/action checks passed 97 tests (38.63 seconds). Exact-head full CI with real
PostgreSQL and zero mandatory skips remains required before repository qualification.

No production source interface, migration, provider authority or activation changed.
JUnit records are integration evidence with a simulated provider, not live certification.
CW-01 and CW-05–07 foundations are on main; CW-08 continuity remains partially qualified.
CW-02–04 full operated staging, exact provider reviews and CW-14–20 release requirements
remain unfinished. Do not activate transactions from this slice alone.

Next: review the new source/test/CI changes, verify exact-head CI, then execute the full
sixteen-fault matrix on a frozen controlled staging release with independent provider
counters. See [the task contract](CW02_PROCESS_RECOVERY_TASK_2026-10-12.md).

## Historical checkpoints

Updated: 11 October 2026 UTC. Base: `c6389b3702aae93019c2ec5643f4e4d5dd76ea2a`.
The coding kit from PR #362 is merged.

## Three-stage execution

| Stage | Tasks | Status |
| --- | --- | --- |
| 1. Safety and operated foundation | CW-01..04 | CW-01 implemented and locally verified; full recovery/deployed qualification pending |
| 2. Continuous coworker | CW-05..13 | CW-05 in progress; later tasks planned |
| 3. Transactions and production pilot | CW-14..20 | Provider/live review and operated evidence required; not qualified or activated |

## CW-01 result

Branch: `codex/cw01-safety-foundation-20261011`.
Repairs invalid fixtures/assertions without changing production behavior; same binding
replays and another action conflicts. Simulated real-transport tests count dispatches and
applied mutations after a lost reply, check actual approval/claim expiry and exact receipts.
The existing coworker CI job runs a separate mandatory suite with locked extras,
JUnit upload and empty/skip/failure/error/required-module rejection.

Verification:
- Original three tests reproduced three failures before reaching the safety boundary.
- Final focused transaction/gate suite: **44 passed, zero skips**, 17.18 seconds.
- Surrounding action/permission/personal-transaction suite: **57 passed, zero skips**, 25.92 seconds.
- Chaos-only CLI gate: **5 collected, zero skips/failures/errors**.
- Fresh review: no Critical findings; one Important mandatory-collection gap fixed
  with a failing regression, required-module check and separate reports.
- Deferred minor: successful replay checks applied mutations but could also assert
  HTTP dispatch count; lost-reply coverage already checks both.
- Exact-head remote CI pending. Local checks do not establish complete repository CI.

Existing PR #363 is open/conflicted at inspected head
`3ba85a5c66582dc9cd27a5e7653291ec97c099f4`; it still calls unsupported
interfaces and installs missing requirements.txt. This main-based branch replaces that
repair; maintainers should retain one implementation, not merge both conflicting patches.

## External qualification blockers

Fresh local CW-03 preflight: `blocked_external: RENDER_API_KEY REQUIRED`.
This execution has no Render connector, staging synthetic identity, Temporal credentials
or private S3 access. Historical PA-10 billing/worker observations were not re-certified.
CW-02 needs the full public API/PostgreSQL/Temporal process-interruption matrix.
CW-04 requires matching frozen API/worker/model/rollout identity.
CW-12..20 additionally require live connector/push/provider access, concrete registered
shopping/travel providers, human Bangla/English and security review, real cost/load,
restore/rollback and an operated availability window.

## Scope and next action

CW-05 may proceed independently while staging access is blocked. Use existing task/run
outboxes and ledgers for CW-06/07. Preserve all capabilities default-off; this work has
not activated production, broadened provider authority, provisioned paid infrastructure,
or executed external sends/purchases. All CW-02..20 acceptance gates remain unfinished
until their exact evidence passes. Refresh main/open PRs/CI before resuming.

## Latest five-commit security and integration review — 12 October 2026

Reviewed main head `ec41ac8b55de99a50e8214a58b22bfc797ae5256` and the four preceding main commits
(`79070ea`, `039093b`, `bb77b28`, `b90b6a4`).

- CW-05 PR #368 is now merged into main. PR #369 marked merged **into the CW-05 feature branch**, not main, so CW-08 source revalidation did not reach main from that merge.
- Repaired CW-05 source selection to reject an expired uploaded document version before message admission; previous behavior pinned expired documents.
- Ported CW-08 read-only, owner-bound document/artifact source revalidation and its seven tests to a new main-based review branch. This is a foundation, **not yet connected to CW-06 admission**.
- Added both the CW-08 unit tests and the PostgreSQL conversation-race module to mandatory coworker CI gating.
- Source changes remain default-off; exact-head CI and PostgreSQL migration/race evidence must be independently reviewed.
- CW-01 source safety foundation remains implemented. CW-02–04 operated staging checks and CW-06/07/08 full task-level acceptance criteria remain incomplete.
- Do not turn on conversations, transactions, or external-action providers from this patch alone.

Next: review/qualify this branch, merge through normal protections, implement CW-06 atomic admission/steering with source validation at the same transaction boundary, then CW-07 UI and complete CW-08 workspace/context lifecycle.


---

## Core routing authenticated API regression repair — 16 October 2026 (Asia/Dhaka)

**Base:** main `badc8bbb66c8ead4a43c3463e32112b1bfd7e996`. Independent [PR #422](https://github.com/rumman52/Shuddho/pull/422), branch `codex/core-router-api-regression-20261016`; CW-10 conversation scope remains on separate [draft PR #421](https://github.com/rumman52/Shuddho/pull/421), source head `27c32e37a89da3af25b14d9757273329dd46e4e0` (164 focused passes; exact-head CI pending at this checkpoint).

**Observed full-suite failure:** `tests/test_core_agent_router.py::test_simple_question_does_not_create_agent_run` raises AttributeError because the stale Agent test double lacks the actual API's `public_idempotent_replay` method. Independently reproduced on unchanged main. The lightweight CI skips the boundary without JWT and the heavy pytest list omits that module. This finding does not establish incorrect production routing.

**Bounded repair:** move the single API boundary test to existing authenticated/DB `test_coworker.py` fixtures, assert two direct-answer refusals and no AgentRun/AgentOutbox/Task. Retain lightweight pure routing tests. Include the precise API test node and required-module gate in the already mandatory no-skip conversation/PG report. No product code or authority changed. [Contract](CORE_ROUTER_API_REGRESSION_2026-10-16.md).

**Local evidence:** pure routing plus real API boundary **18 passed, zero skips**, mandatory JUnit gate passed. Initial real fixture enabled research without credentials; removed that unrelated flag and revalidated settings. Independent read-only agent review found no Critical/Important/Minor findings; this is not human security certification. Full branch pytest and exact new PR-head mandatory CI pending. The separate #421 full run finished 2068 passed, 70 service skips and the one stale test failure (480.60s). Do not infer repository-wide qualification or merge/activation from this focused result. All C-04/CW-11 and operated A/P/V gates remain unfinished.


**Integration:** this entry is appended rather than prepended to avoid conflicting with #421's simultaneous canonical-progress prepend. Both PRs remain separately reviewable against the same base; refresh main/CI after either is integrated. Direct git push was unavailable (no transport credentials); authorized connector writes were used and remote/local Git tree identities verified.


---

## CW-02 artifact storage failure continuation — 19 October 2026 (Asia/Dhaka)

**Refreshed main:** `1344348707066556a0a21e4ec0620e16499294cf`, merge commit for [PR #465](https://github.com/rumman52/Shuddho/pull/465). The export-write failure regression and cleanup are now on main. At the checkpoint refreshed for this follow-up, the `test-and-build` job passed but the required `coworker` job remained in progress; do not describe the exact main revision as fully CI-verified until that job finishes.

**Next bounded slice:** branch `codex/cw02-storage-read-recovery-20261019` now tests (1) transient required-artifact GET failure at the actual `DocumentRunner.phase(..., "complete")` boundary, with no terminal success or published Artifact records and a retry that verifies existing bytes without additional object PUTs; and (2) a lost database response after the export checkpoint commits. The second case exposed a data-loss hazard in PR #465's cleanup logic: a committed checkpoint could reference blobs that unconditional exception cleanup then deleted.

**Correction in this branch:** partial-export cleanup runs only before checkpoint submission. Once checkpoint submission starts, the commit outcome is uncertain, so object deletion is suppressed; retry observes a committed checkpoint and reuses its referenced objects. This deliberately favors preserving potentially referenced data over eager orphan cleanup. Exact-head CI is required before merging.

**Evidence boundary:** test-store fault injection is not live S3 staging evidence. Persistent storage outage, cleanup after hard process death, the remaining CW-02 fault matrix, CW11-STAGING mixed-version drain, browser/sandbox isolation and complete personal-coworker scenarios remain unqualified. No deployment, provider activation or production action was performed.

---

## Architecture/core closure — C-01 terminal completion/replan finality (20 October 2026)

- **Starting main:** `79c111d7bc3ec8ae1ad65b55e4f78595aec54e46` already includes merged #485. The concurrent draft #486 addresses late tool start/receipt; this slice intentionally does not modify it.
- **Root cause:** `complete_run` could turn a v3 run already `needs_input` or `blocked` into `completed` if existing receipt counts match. `replace_remaining_plan` could also change prepared tool steps after a terminal outcome.
- **Correction:** [PR #487](https://github.com/rumman52/Shuddho/pull/487) inserts v3-only `agent_run_closed` checks under the owning AgentRun row lock. Already-completed and cancelled idempotence and legacy v1/v2 behavior are preserved. [Contract](C01_TERMINAL_COMPLETION_REPLAN_FINALITY_2026-10-20.md).
- **Evidence:** five regression test instances committed before implementation; the CI suite now explicitly includes this module with a required-module/no-skips gate. Mandatory exact-head CI and independent review pending. No live staging, worker-restart, PostgreSQL race, provider cost, human security signoff or production activation claimed. C-01/A-02 and full Architecture/Core acceptance remain incomplete.

---

## Architecture/core closure — C-01 committed decision replay after deadline (20 October 2026)

- **Starting main:** `9d830f3d7f9fe405020a45c42ab99bf05dea5b65`, merged PRs #486/#487 preserved. [PR #488](https://github.com/rumman52/Shuddho/pull/488) covers a distinct committed-activity replay/deadline ordering gap.
- **Defect:** `decide_v3` checked the task deadline before looking up an exact committed retry result. A lost response retried after expiry could reject an already-durable result; the no-tools repository helper had a similar internal race.
- **Scope:** move only the committed-result lookup ahead of deadline validation, keeping cancellation first and maintaining deadline checks on all *new* work. [Task contract](C01_V3_DEADLINE_REPLAY_2026-10-20.md). No new provider calls, ledger, flags or authority.
- **Evidence:** five cases committed before implementation, plus one internal no-tools helper test; mandatory test module collection already configured in CI. Exact final-head CI, independent review and operated PostgreSQL/Temporal qualification remain open until verified. Full A/C/P/V not closed.

---

## Architecture/core closure — C-01 late-inference deadline write fence (20 October 2026)

- **Base:** `main` `b1cb627b620a6ab7706efb5e41a67018a46100af` includes merged #488. This task is a separate commit-time validity defect, not a duplicate of committed retry replay after deadline.
- **Defect:** the provider can finish after expiry; `record_v3_decision` checked terminal state and context but not the deadline, allowing fresh `needs_input`/`blocked`/`wait` outcomes to persist late.
- **Review branch:** [PR #489](https://github.com/rumman52/Shuddho/pull/489) adds the deadline fence under the existing run lock before fresh decision persistence, preserving exact previously committed replay and provider usage settlement. [Task contract](C01_LATE_INFERENCE_DEADLINE_FENCE_2026-10-20.md).
- **Evidence:** five tests committed before implementation, one direct-record test added during patch. Full exact-head CI and independent review pending; no live PostgreSQL/Temporal operated staging evidence or production activation. C-01/A-02 and full A/C/P/V inventory remain incomplete.


## C-04 / CW-10 worker lifetime and cleanup — 20 October 2026

- Dedicated branch `codex/cw10-sandbox-cleanup-order-20261020`, base `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`. [Task contract](CW10_WORKER_LIFETIME_CLEANUP_2026-10-20.md).
- Five real local subprocess regressions failed before implementation: source/scratch still present during normal/lost-response completion, cleanup failure after a false destruction claim, blocked-control wall overrun, and unexpected supervisor exception leaving code alive. A watchdog now enforces wall/disk limits during control I/O; final cleanup always reaps a live child; completion is published only after output handles and private directories close.
- Independent review found an Important watchdog exception hole. A sixth real-child regression reproduced thread termination on RecursionError; unexpected inspection exceptions now fail closed and stop the child. Reviewer also independently verified interactive output preservation and Thread.start failure cleanup. No remaining substantiated Critical/Important finding is open in this slice.
- Final sandbox/lifecycle/code-proposal suites: **189 passed, zero skips**, six existing Pydantic invalid-input serialization warnings. Mandatory lifecycle collection and syntax checks passed. Required exact-head CI remains pending at publication.
- Tests substitute namespace launch with a real local child; they establish supervision/cleanup ordering, not real bubblewrap, mount/network isolation or memory zeroization. This host cannot create the required bubblewrap UID mapping. Staging preflight lacks RENDER_API_KEY. C-04, other A/C/P/V gates, human security review and production qualification remain open. No merge, deployment, activation, policy version, approval or capability-default change.


## Projects dashboard entry correction — 9 November 2026

The user-provided Projects screenshot and the exported Figma screen `projects-desktop` define the initial state: the shared sidebar has Projects selected; the top bar reads Projects and includes Activity & context; the main dashboard shows the Projects heading, `+ New project`, project search, and API-backed project cards. The New project form is a secondary state opened only after the user selects `+ New project`.

PR #649 inverted this behavior by initializing `projectCreateMode` from `?view=projects`, setting it to true during Projects navigation, and passing `initialCreate` into `ProjectWorkspace`. PR #653 restores dashboard-first navigation and removes the route-level `initialCreate` path. Project cards remain generated from the authenticated Projects API; the sample names in the reference are not hard-coded. Selecting a card still opens its project workspace with Overview, Chats, and Files tabs. Creating, cancelling, editing, linking, uploading, and deleting continue to use the existing owner-scoped APIs.

The Figma MCP context request was rate-limited, so visual comparison used the supplied screenshot and the repository's exported `design.json` / `design-tokens.json`. The project layout CSS already matches the exported 1440×900 geometry and Rukh palette; this correction changes route state, not the design system.

Frontend test/build CI passed on the implementation head (web-editor: 238 passed, 0 failed; standalone Coworker and Writing Assistant checks passed). The Vercel GitHub integration reported the branch preview Ready. Broader Coworker qualification CI is tracked separately. No production migration, backend flag, database record, or production deployment was changed. See [task contract](PROJECTS_ENTRY_SCREEN_2026-11-08.md).

## Day 10 source identity and CI gate correction — 18 November 2026 (Asia/Dhaka)

- **Base:** main `aa705726f4c76cbb819a62211b7743aa44c59b17` (includes #774); branch `codex/day10-exact-readback-ci-20261118` for [#736](https://github.com/rumman52/Shuddho/issues/736). The main's positive Day 10 fixture passed even with no API/worker image digest and no worker 43-flag readback, and the release gate expected aliases `frontend`/`postgres-18-qualification` rather than the real GitHub job names.
- **Bounded proposed source fix:** enforce lowercase SHA-256 build digests in API and worker evidence; exact schema-v2 worker environment/43 boolean flags (including false values) and provider list; use Day 9's canonical seven exact-head GitHub contexts. Preserve canonical release/quality gates and all current production defaults. Add 13 parameterized rejection cases. See [contract](DAY10_IDENTITY_CI_EVIDENCE_GUARD_2026-11-18.md) and [operator snapshot](DAY10_NO_GO_OPERATOR_HANDOFF_2026-11-18.md).
- **Source vs operations:** previous main Coworker CI was red on two unrelated export test fixtures fixed in now-merged [#774](https://github.com/rumman52/Shuddho/pull/774); governance/merge controls also red. Read-only Render staging API remains on `0e0b662fad0a02817a79a4514abba8f94e0ad022` and lacks worker; Supabase schema ledger remains `0070` vs source head `0072_merge_0071_heads`; Vercel connected Shuddho project absent. No live evidence, migration, provider spend, flag change, rollout freeze, signoff or pilot admission was made. **SOURCE_ONLY / NO-GO**.
- **Repository verification:** pending focused tests, final-head mandatory CI and independent reviewer signoff. Do not claim live or production qualification from mock-positive unit tests. **Next:** run focused Day 10 suite and inspect immutable PR-head GitHub checks; C fixes controls; after explicit owner authorization operate staging and genuine receipts.

---

## Day 6 evidence and acceptance gates — 18 November 2026

- **Current main checkpoint:** `aa705726f4c76cbb819a62211b7743aa44c59b17` merged Day 1 recovery fixture repair [#774](https://github.com/rumman52/Shuddho/pull/774), superseding an overlapping isolated Day 6 test-fix [#775](https://github.com/rumman52/Shuddho/pull/775). Production validators are unchanged.
- **Source and CI:** original `c8aa7cf...` had 1,628 Coworker pass / 2 fail / 4 skip; the parallel #775 focused Day 6 JUnit is 107/107 with 14/14 **offline** quality calibration, not the two original regression cases nor a live 40-case model run. Full new-main verification and independent review must not be inferred from concurrent PR status.
- **Live preflight (read only):** Supabase staging 1 private bucket but 0 Auth users, 0 Coworker accounts/runs/tasks/artifacts/objects, and outbox 0; migration at `0070`, source ahead. Render staging API deploy is from 14 November, with no workflow registered; connected Vercel has no Shuddho project.
- **Day 6 verdict:** **NO-GO**: approved owner A/B, source-complete bilingual golden run, native owner retrieval/SHA-256, cross-owner denial, “Draft ready” UI/no-send provider receipt, reconnect/restart, and D-reviewed 40 development first-run versus regression are not demonstrated. No production deploy, schema mutation, paid resource or send performed.
- **Traceable handoff and owner next steps:** [DAY6_EVIDENCE_2026-11-18.md](DAY6_EVIDENCE_2026-11-18.md), tracker [#732](https://github.com/rumman52/Shuddho/issues/732). C approves/prepares staging, A/B run the golden research/report-email workflow, D independently verifies actual files/citations/language/retrieval and scores, Founder+C own release/spend gates.


## 2026-11-18 — Day 7 (#733): credential-safe scheduled-profile probe (source-only)

- **Candidate pinned:** merged main `c8aa7cf8444f1cf8c5408568e78b3cae6792f00a`. PRs #709/#721/#747/#759 are already merged; no duplicate goal, automation, Temporal, occurrence or notification subsystem was introduced. Draft review branch: `fix/day7-staging-probe-https-origin-20261118`.
- **Reproduction before editing:** the existing `clean_origin` code accepted `https://localhost`, `https://127.0.0.1`, a tab-suffixed origin, an out-of-range port and multiple trailing slashes. The scheduled-profile probe passes the synthetic owner's bearer token to that configured origin. New parameterized regression cases cover these and other invalid shapes.
- **Bounded patch:** reuse the existing `staging_prerequisite_preflight._validate_https_endpoint` public HTTPS validation; require a path-free origin with no query or fragment marker; retain a single optional trailing slash and valid HTTPS port. Updated the controlled-staging runbook. No production logic, credential, deployment, governance or billed-resource change.
- **Verification:** reproduced the baseline behavior using the exact pre-patch function in an isolated Python invocation (five invalid origins accepted). Focused source tests and exact-head CI are **not yet certified**; required: `uv run --extra coworker pytest tests/test_staging_pa10_scheduled_profile.py tests/test_automations.py tests/test_coworker_temporal.py -q -rs` and the repository's full PR checks. Record the final PR SHA and CI jobs before merging.
- **Live staging readback (read-only):** Supabase migration `0070`, with zero Auth users, automations, occurrences and Agent runs; Render has the staging web API but **no persistent coworker worker**; Vercel has no linked Shuddho project. Day 2 #728 is not approved/complete, and the prior worker-billing approval is expired. **SOURCE_ONLY / NO-GO:** no real owner-approved goal/schedule, Temporal firing, immutable source or notification receipt, natural-fire proof, Day 8 second fire or next local-fire time can be claimed.
- **Owners / next executable step:** C + Founder approve the exact no-/paid-resource staging boundary, secure worker/Temporal/S3/model credentials, migrate only after backup/release authorization and restore proof, and pair API/worker/schema. B + A then create and read back the approved daily goal/schedule. C + D witness natural Temporal history without manual trigger; B + D update an authorized document before Day 8. Keep primary schedule eligible through Day 8; use a separate synthetic schedule for destructive/quiet-hour tests.
