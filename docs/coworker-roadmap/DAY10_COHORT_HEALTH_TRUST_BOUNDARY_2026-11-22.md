# Part 05 / Day 10 — cohort health and rollout control evidence integrity

**Status: SOURCE-ONLY / CONTROLLED PILOT NO-GO.** Date: 2026-11-22. [Draft PR #895](https://github.com/rumman52/Shuddho/pull/895), base main `4eee61c4389b507b95670203618c0ed980d5ccf8`.

## Authority and narrow objective

Part 05 pp. 5–7 requires an exact-release 43-flag freeze, independent 40 first attempts / 80 blind scores, 20 operated PostgreSQL/Temporal/object-storage recovery traces, real rollback and a distinct 5–10-member admission before live cohort monitoring. A health-window gate must not accept a rewritten first decision, silently relaxed thresholds, or a different rollout cohort cap.

This source-only follow-up strengthens **two trust boundaries** without changing the actual thresholds, Stage 5→10 logic, or STOP/CONTINUE semantics:

1. `scripts/cohort_release_gate.load_rollout`: canonical cohort manifest input, already consumed by `cohort_health_gate`.
2. `scripts/cohort_health_gate.load_thresholds` and `main`: health STOP thresholds plus its snapshot and decision output receipts.

## Root cause from reviewed source

The rollout and threshold JSON readers previously called `json.loads(Path.read_text())`, silently selecting the last duplicate key, following symlinks and reading unbounded input. The rollout parser even accepted nonfinite `NaN` values. A duplicated `cohort.max_users` could change the evaluated population cap; duplicated failure-rate keys could conceal a stricter STOP threshold.

The health CLI used `Path.write_text` for both reports, overwriting earlier operator evidence and creating `0644` files under a default POSIX `umask 022`. Separate invocations could replace original STOP evidence with a later CONTINUE report. These are source trust-boundary defects; they do **not** prove any malicious actor or operated fault occurred.

## Test-first evidence and implementation

| Artifact | Observed scope |
| --- | --- |
| Test commit `df4a3fa982f7a392fa144ddffaef8611dd4dec90` | 8 new synthetic health-boundary assertions: duplicate STOP-rate key, linked thresholds, >4MB thresholds, private snapshot and decision, first-write collisions and same-path rejection |
| Test commit `aede08744ba62900ea15b701c6dbf39c96f39626` | 5 new rollout assertions: duplicate cohort cap, symlink, >4MB, nonfinite `NaN`, and correct valid/false-flag readback |
| [Test-only Actions #45041430584](https://github.com/rumman52/Shuddho/actions/runs/45041430584), Python job | **Observed RED: 4 failed / 3,684 passed / 107 skipped / 6 warnings.** The 4 failing tests all specifically involve the rollout reader, which silently accepted ambiguous/linked/oversized/nonfinite input. The health test file has `pytest.importorskip("sqlalchemy")` and is not independently shown RED by this lightweight Python job; do not count its assertions as observed RED |
| Source commit `c29a062343904f3179f531343c2ae6852166c6d0` | Canonical rollout reader now delegates to existing `scripts.ruke_pilot_eval.read_json` (strict duplicate/nonfinite JSON, bounded regular inode, no-follow final path) |
| Source commit `3f6b91284264693163f253271222ed2e65ac341d` | Threshold reader delegates to same helper and wraps rejection as `CohortHealthError`; health CLI rejects equivalent/same or existing output paths, then writes each first report via `immutable_write` (exclusive 0600, fsync) |

Verify actual **exact final-head** GitHub Actions test-and-build, browser-qualification, frontend, PostgreSQL 18 compatibility and Coworker jobs before calling this patch GREEN. The SQLAlchemy-backed health tests require the Coworker extra; run them explicitly during review:

```bash
uv run --locked --extra coworker pytest -q \
  tests/test_cohort_health_gate.py tests/test_cohort_release_gate.py
uv run --locked --extra coworker python -m scripts.release_contract_check
uv run --locked --extra coworker pytest -q
```

The health CLI test substitutes a synthetic snapshot at the external database collection boundary but executes the actual CLI parsing and evidence writer. It is **not a real staging health measurement**. Independent code review should examine O_EXCL races and side effects when one of two evidence outputs collides.

## Acceptance and limits

- Reject ambiguous JSON thresholds, duplicate rollout cohort caps, linked/nonregular files, oversized evidence and nonfinite rollout values.
- Preserve all existing canonical limits and explicit false flags; no implied pilot approval from a valid file.
- Keep first snapshots and first health decisions private and write-once. An existing report should produce a nonzero failure and preserve original bytes; no covert update.
- Require actual 5–10-user identities and deny a fresh nonmember on HTTPS before monitoring can support D10.G08.
- **Not attempted here:** migrations or staging restore, paid providers, 40/80 heldout, 20 operated recoveries, independent owner signoff, CI ruleset modification, live cohort enrollment, PostHog event recording, Render/Vercel deploy, ProductOS application development or Linear task closure.

## External release blockers, still held by authorized people

- **Human D:** real protected custody and independent blind scores; 40/40 first attempts, >=36/40 overall, >=9/10 per cell, 100% security and twenty distinct operated recovery receipts.
- **Owner C/staging operators:** approve and execute compatible backup/restore, bind exact source/API/worker/schema/provider/model and **all 43** authoritative booleans, and authenticate all trace/system IDs.
- **Founder and Owner C:** independent dated signoffs for exact rollout digest, cap, rollback and separate admission authority; distinct full-member + nonmember HTTPS admission proof.
- **GitHub repo administrator:** native main ruleset `27324410` currently requires zero independent reviews and no required CI check. An audit job reporting FAIL does not stop merges unless the branch rules require it.
- Supabase `shuddho-staging` readback remains PG17.11 migration `0070`, not a hosted qualification proof; connected PostHog project 675660 had `ingested_event=false`; Render workspace not selected for an approved Shuddho service; connected Vercel `ali` and ProductOS `Dust2Glow` point to unrelated projects.

Historical v4 ledger baseline 18/100 task PASS, 5/54 exit checks, 0/10 accepted days is not increased by source-only fixes. **Controlled pilot NO-GO until independent operated and reviewed evidence exists.**
