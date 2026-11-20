# Day 10 first-run exact-release binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Reject mismatched or rewritten Day 9 first-run evidence at the Day 10 pilot decision, while preserving authentic original failures and independent operator custody.

**Architecture:** Validate the exact-release identity and 40-case scorecard parity between the evaluator's two generated receipts, before declaring `preserved_day9_first_run` passed. Keep `holdout_ok` and canonical quality/recovery/human approval gates independently in force.

**Tech Stack:** Python 3.11, pytest, GitHub Actions CI, `scripts/day10_release_decision.py` and `scripts/ruke_pilot_eval.py` report schema.

**Spec:** User-uploaded `05_Rukh_AI_Qualification_and_Handoff(1).docx`, pages 1–6, D09.T04/T05/G02/G06 and D10.T04/G04, plus `docs/coworker-roadmap/DAY10_FIRST_RUN_EXACT_RELEASE_BINDING_2026-11-20.md`.

## Global Constraints

- Preserve 40 first attempts, 80 original human score rows, 4 workflow/language cells × 10, ≥36/40 acceptance, ≥9/10 per cell and all 40 independent security PASS.
- Preserve historical first-run traces unmodified, but never count a differently bound frozen release as current GO.
- No new signing fiction, external writes, provider/DB/worker/flag changes or staging/production activation.

## Review Focus

- Historical first-run source/rollout digest rebound to a later green SHA → reject.
- Modified manifest digest or missing manifest proof on either receipt → reject.
- Reviewer rubric/quality totals altered without matching case output → reject.
- Same count but substituted/duplicate case IDs → reject.
- Valid 39/40 with legitimate zero-scoring rejected case → allow when the bound report and heldout receipt both accurately reflect it.

## Task 1 — pin failing source evidence

- [x] Read Part 05 and inspect evaluator output and Day 10 gate/tests at main `6bdcd9667ab89d91d296146ab14731fdfde797cd`.
- [x] Add 20 negative tests plus matching happy-path synthetic helper; commit test-only `1607724cc9fe71699b9d116dec393a1d2c15dcd1`.
- [x] Observe RED [CI #44755986612](https://github.com/rumman52/Shuddho/actions/runs/44755986612), 20 failed / 2595 passed / 102 skipped.

## Task 2 — source fix and repaired synthetic fixture

- [x] Add `first_run_matches_holdout(first_run, holdout, release, revision, rollout_hash)` and wire into the existing preserved evidence decision.
- [x] Require exact release/source/rollout/manifest parity and one-to-one 40-case parity; aggregate scores from original case booleans.
- [x] Correct historical test fixture contradiction and keep rejected original case legitimate only when its report also records the failure.
- [ ] Run final-head complete tests and inspect the genuine Python/Coworker/PG18/frontend/browser/ancestry results.

## Task 3 — independent review and operational gate

- [ ] Obtain independently attributable review and strict ruleset #27324410 evidence; do not self-merge.
- [ ] Have C and D independently authenticate hosted exact-release, original holdout bytes and operated 20-scenario receipts.
- [ ] Acquire separate Founder and Owner C signoffs on a qualifying release before any approved pilot admission.

**Levels:** implementation in PR #822; source-verification pending. Staging/production qualification and activation are **not established**.
