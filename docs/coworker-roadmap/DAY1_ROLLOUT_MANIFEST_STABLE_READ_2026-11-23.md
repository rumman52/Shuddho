# D01.T06 / D01.G03 — stable rollout manifest for private recovery evidence

**Date:** 2026-11-23, Asia/Dhaka. **Owner:** A source/runtime; C hosted recovery/operator; Founder+C authorization; D independent reviewer and custody. **Disposition:** SOURCE_ONLY / NO-GO.

## Identity and observed defect

Base `main`: `e8d3e3c8180eaba2065468bf31f2dba96d682664`. Branch `fix/day1-rollout-manifest-inode-drift-20261123`. Draft [PR #902](https://github.com/rumman52/Shuddho/pull/902), parent [#737](https://github.com/rumman52/Shuddho/issues/737), Day 1 [#727](https://github.com/rumman52/Shuddho/issues/727), Day 2 [#728](https://github.com/rumman52/Shuddho/issues/728), [Linear MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout).

The existing `scripts/staging_release_evidence.py::_read_rollout_manifest` already uses `O_NOFOLLOW`, bounded `os.read`, duplicate-key and nonfinite-number rejection, and an exact-byte SHA-256. It checked `os.fstat` only **before** consuming input. A same-inode JSON replacement, append after initial stat, or rewrite at EOF could be accepted and labeled with a digest despite a changing release manifest. This is a distinct release-evidence continuity problem, not the already merged private-object #896 or Day 10 receipt #900.

**Expected:** reject a manifest that changes while its opened descriptor is being consumed; never return a source revision/release ID/digest computed from an unqualified file. **Actual RED:** test-only `4b1e71485593abf2eb04864545503878bd1fe672`, [Actions #45225593317](https://github.com/rumman52/Shuddho/actions/runs/45225593317) `test-and-build`: **3 expected failures, 3726 passes, 107 skips, 6 warnings**. Every new failure reports `DID NOT RAISE StagingReleaseEvidenceError`, proving the original behavior. Three cases: same-length replacement, growth with valid JSON whitespace, same-size replacement at EOF.

## Source correction and reproduction

The candidate code captures final `os.fstat` on the **same still-open descriptor**. Before returning a parsed payload or hash, it requires regular-file status, stable `st_dev`/`st_ino`, stable initial/final size, exactly the initially declared number of bytes consumed, and identical nanosecond mtime/ctime. This is a consistency fence, not a digital signature; protected source identity and operational custody remain distinct.

Focused command: `uv run --locked --extra coworker pytest -q tests/test_staging_release_evidence.py tests/test_staging_backup_restore.py`. Required final-head jobs: `test-and-build`, `coworker`, `Frontend tests and builds`, `browser-qualification`, `PostgreSQL 18 staging compatibility`, `PR head ancestry`, and governance `ci-merge-gate`. A skipped PR `governance-audit` is not an operated main audit. Record each status for the **final SHA**, never extrapolate from test-only RED.

## Blocked handoffs: no row-level PASS from this source work alone

- **Admin/C:** Protected `V01_RULESET_APP_CLIENT_ID` and `V01_RULESET_APP_PRIVATE_KEY` in `v01-governance`/`pa10-staging`; approve and apply reviewed `scripts/reconcile_main_ruleset.py` diff against native ruleset 27324410 with expected main SHA and observed ruleset fingerprint. Prove one independent review, stale/last-push/threads, three strict native checks and both blocked/unblocked platform outcomes. Do not self-review.
- **C+Founder:** Authorize exact staging identity, storage/Temporal worker, hard budget/privacy limits, source/isolated target, backup custody and original-0070 preseed receipt before migration or any runtime deployment. Resume using `scripts/staging_backup_restore.py attest-original`, `prepare`, `verify` with full required protected receipt arguments documented by the existing runbook, not simulated placeholders or production credentials.
- **C/D:** Authenticate owner A own private PDF and denied owner B read in the real HTTPS API, PostgreSQL+S3 restore and Temporal recovery on a matched worker/API source SHA; retain private original and readback artifacts plus redacted immutable references. Supabase read-only at this checkpoint: `0070`, 84 tables, zero Auth users, zero storage records; Render staging API served SHA `0e0b662fad0a02817a79a4514abba8f94e0ad022`, with no persistent Shuddho worker in connected workspace.
- **Independent D/Founder:** Independently replace exposed 40 candidate cases, lock custody outside developer access with negative read proof, collect human first-attempt and real recovery trace evidence; sign exact source/release digest with separate Founder+C GO only if all requirements pass. Keep PostHog off without privacy approval, Vercel unrelated project and ProductOS unrelated demo untouched.

**Provenance:** source patch and exact-head CI are repository-level evidence; no operated staging, independent review, or authorized pilot proof is claimed. Historical v4 18/100 tasks, 5/54 exits, 0/10 accepted days are dated and not increased by this branch. Keep D01.T06/G03 blocked until actual C receipts.
