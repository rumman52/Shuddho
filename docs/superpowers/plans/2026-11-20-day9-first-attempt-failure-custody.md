# Day 9 — preserve no-draft failures among all 40 first attempts

**Goal:** Repair a reproducible acceptance-harness defect without weakening developer access denial, honest quality denominators or real platform evidence requirements.

**Architecture:** Keep the existing `candidate_ledger` entry point and report. Add an explicit discriminated failure/timeout row, hash its canonical non-output evidence, thread its failed case ID into `score_reviews`, and preserve all successful draft parsing/quality gates. Zero DB/API/provider/permission/schema changes.

## Task 1 — RED regression (complete)

- [x] Reopen Part 05, Day 9, tracker #735 and exact repository implementation at `f5090638be33d7e648736daf533e4b25c307d13d`.
- [x] Add separate synthetic `failed` and `timed_out` rows, 40-denominator assertions, forged success denial, trace/run mutation and missing provenance negatives.
- [x] Commit test-only `3042a737cdf1fafc9495bfd54b9e4c7142341dd8` and reproduce on GitHub CI [#44739458984](https://github.com/rumman52/Shuddho/actions/runs/44739458984), **11 failed / 2545 passed / 101 skipped**. The old source rejects a missing draft.

## Task 2 — minimal source patch (implemented)

- [x] Accept only `succeeded`, `failed`, `timed_out`; default to historic `succeeded` input when the field is absent.
- [x] For failed/timed-out rows: require explicit null output, empty source refs, normalized reason, private trace SHA, unique run and ordered nonfuture timestamps.
- [x] Hash a canonical failure envelope (case, run, manifest, status, reason, trace, timestamps), mark the receipt as failure evidence, never pretend it is draft output.
- [x] Pass failed case IDs to `score_reviews`, require deterministic `passed=false`, retain case in 40 denominator, and preserve 80 independent reviewer and security result gates.
- [x] Update the operator's supported JSONL format and execution ledger.

## Task 3 — exact-head validation and review

- [ ] Inspect final-head `test-and-build` (all Python), mandatory Day 9 Coworker gate, PostgreSQL18, frontend, browser and source/release controls.
- [ ] Check regression tests for 0 required skips; record final SHA, run ID and counts.
- [ ] Obtain distinct human review and admin-managed native ruleset approvals/status checks; do not self-approve or merge around governance.
- [ ] Run real heldout/custody and 20 recoveries only with authenticated C/D operators and explicit environment approval. Never turn source output into a live signoff.

**Out of scope:** Changing release thresholds, holding real private corpus/keys in checkout, provisioning/billing, starting/stopping services, provider mutation, production flags, autonomous emails, pilot enrollment or making Founder/Owner-C decisions. **NO-GO until separate operated evidence.**
