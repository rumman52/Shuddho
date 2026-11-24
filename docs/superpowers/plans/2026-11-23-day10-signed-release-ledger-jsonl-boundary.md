# 2026-11-23 — fail-closed signed release-ledger JSONL reader

## User intent and guardrails

Use Part 05 / Day 10 controlled-pilot qualifications. Work only on source-verifiable foundational correctness and open a draft PR. Human evaluator D and platform owner C must independently operate private custody, 40/80 scoring and 20 real recoveries; repository tests cannot satisfy those gates. Never activate a cohort or mutate unrelated cloud projects.

## Source-of-truth and interfaces

Base main SHA `e8d3e3c8180eaba2065468bf31f2dba96d682664`. `scripts/cohort_release_ledger.read_entries(path: Path) -> list[dict]` is the ingress for the signed event chain. Existing canonical HMAC verification happens downstream in `verify_entries`. `scripts.ruke_pilot_eval.strict_json_loads` and `MAX_BYTES` supply established strict, bounded evidence parsing. Preserve ledger schema 1–34 and append behavior.

## Steps — red/green/review

1. **RED:** Add valid signed fixture using existing `append` helper; insert an earlier hidden event_type to prove duplicate last-key-wins; add nonfinite number, final symlink, oversized otherwise-valid JSONL row and nonregular path. Verify missing ledger returns empty, and existing signed chain continues to verify. Observe actual full Python failure on test-only PR head. Correct test mistakes before source changes.
2. **GREEN:** Replace `read_entries` with one regular no-follow descriptor reader. Limit row bytes to 4,000,000 and total file bytes to 64 MiB. Reject malformed, ambiguous and nonfinite rows before HMAC. Preserve row order and old missing-file semantics. Do not change HMAC verification or event append procedures.
3. **VERIFY:** Require both test-only RED and corrected source-head GREEN GitHub Actions `test-and-build` job. Inspect exact final PR-head CI with browser, frontend, PostgreSQL compatibility and mandatory Coworker jobs. Governance audit skip or CI merge gate failure are release blockers, not success.
4. **HANDOFF:** Record actual SHAs, CI run IDs and non-qualifying skip counts in Part 05 task contract and PROGRESS. Open draft GitHub PR and route independent review plus human-operated blockers through Day 10 issue #736 and governance issue #484. No cloud mutations.

## Observed outcomes

Tests: `f9654ef72e317623b6059c17aa28041d11d0c6ef`, corrected fixture `c092becf7a29131ddecd14015eb61afc0aa72adb`, verified [RED #45225809032](https://github.com/rumman52/Shuddho/actions/runs/45225809032): 5 failed / 3,727 passed / 107 skipped. Implementation: `cfbe50b4ce30431e56d2f991d7119404cd72d28c`, verified [source-green test-and-build #45226323848](https://github.com/rumman52/Shuddho/actions/runs/45226323848): 3,732 passed / 107 skipped / 6 warnings, JS 551 passed. See [task contract](../../coworker-roadmap/DAY10_SIGNED_RELEASE_LEDGER_JSONL_BOUNDARY_2026-11-23.md). Full operated release remains NO-GO.
