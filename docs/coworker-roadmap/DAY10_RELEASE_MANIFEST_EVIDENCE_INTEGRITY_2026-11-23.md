# Part 05 Day 10 — canonical cohort rollout manifest and first-decision receipt integrity

**Dated:** 2026-11-23, Asia/Dhaka. **Scope:** source-only, draft PR #900, **NO-GO for operated qualification and cohort admission**. Base main: `01314ce5e6502b48d85852324b9208bd1f72873b`. Release operator: `scripts/cohort_release_gate.py`. Review plan: [dated plan](../superpowers/plans/2026-11-23-day10-cohort-release-manifest-receipt-integrity.md).

## Defect and risk

The canonical controlled-cohort operator read its `--rollout` with `json.loads(Path.read_text)` but independently reopened the path with `file_sha256` after other evidence. Before the change, it accepted duplicate capability keys, nonfinite numbers, linked and oversized JSON. A pathname mutation between parsing and digest could make the `evaluate_release` decision use one manifest but authenticate a different digest. Optional `--output` used `Path.write_text`, overwrote a prior report and was world-readable with default 022 umask.

The risk is **false release identity, ambiguous security flags, or evidence loss**, not an assertion of a live exploit or that real Founder/Owner-C human approval happened. This code path belongs to the source-level release preflight and does not authorize admission.

## Design/compatibility

Reuse `scripts.ruke_pilot_eval._read_json_and_sha256`, which opens a regular inode with no-follow, enforces the existing 4,000,000 byte cap, rejects duplicate keys and nonfinite JSON, then hashes the *same bytes*. Add `load_rollout_with_sha(Path)->tuple[dict,str]`; retain `load_rollout(Path)->dict` for other established callers. The CLI passes the saved SHA-256 into `evaluate_release` rather than independently reopening `--rollout`. Write an optional result with existing `immutable_write` (exclusive O_EXCL, 0600, fsync) so a second invocation on the same path exits and leaves first bytes intact. Maintain existing result schema, printed JSON and source gate semantics.

No new schema migration, PostgreSQL/Temporal/storage ledger, model/provider calls, runtime flags, deployments, auth/allowlist changes, or telemetry.

## Recorded RED, before production code

Behavior tests first commit `11e8378d5fbadc8b9020d72c7524557fd9267807` added eight executable synthetic cases in `tests/test_cohort_release_gate.py`: baseline valid dict; duplicate nested `coworker`; nonfinite cohort limit; symlinked target; >4 MB JSON; deterministic `load_evidence`-driven pathname replacement exposing mismatched `rollout_sha256`; private 0600 output; and write-once first report.

[Test-first Actions #45064988770](https://github.com/rumman52/Shuddho/actions/runs/45064988770): Python `test-and-build` step **7 FAILED / 3,701 PASSED / 107 SKIPPED / six warnings**. All seven were the expected behavior assertions, not collection/import errors; compatibility test passed. Source fix committed second at `392c3c7e3ed172a425be48bbcb212142fe90f97f`.

## Verification evidence and limitations

Require **exact final-head** Python/build, mandatory Coworker, browser, frontend, PostgreSQL compatibility, release-contract validation, native governance audit and `ci-merge-gate`. No claim of full green until logs are inspected. Draft governance audit may be skipped; owner configuration of mandatory 1+ independent approving reviewer and required status contexts is missing (ruleset 27324410). Keep PR unmerged pending proper review.

Read-only inventory: Supabase `shuddho-staging` ACTIVE_HEALTHY PG17.11.0.003 with SQL Alembic `0070`, **not** proof of source-aligned migration/restore or runtime identity. Render has an unselected workspace (no authorized workspace selection this turn); no deployment performed. Vercel Git mapping only found `ali` linked to unrelated `hero-dev-code`. ProductOS only offered unrelated Dust2Glow project. PostHog default project 675660 recorded `ingested_event=false`; no capture was added. Linear MD-5 through MD-8 remain task-tracking references. No cloud mutations.

## External acceptance still blocking

Authoritative Part 05: real human D holds a separately frozen corpus, answer key and rubric with actual developer denied readbacks; **40 first attempts** over four workflow/language cells, **80 independent human scores** with blind/adjudication evidence, at least 36/40 and 9/cell, 40/40 security; **20 distinct operated** PostgreSQL/Temporal/private-storage recovery traces on the exact release; all 43 authoritative worker/rollout flags with API derived field; live quality and golden-run checks; separate authenticated Founder and Owner C approval of the exact digest; and **subsequent** distinct 5–10-person admission plus nonmember 403. No synthetic regression here counts for any of these.

Historical Part 05 v4 ledger remains **18/100 tasks, 5/54 exits, 0/10 accepted days** until new observed independent receipts upgrade it. Pilot stays **NO-GO**. Branch #897 canary recovery receipt parser and #895 cohort health gate are distinct pending changes.
