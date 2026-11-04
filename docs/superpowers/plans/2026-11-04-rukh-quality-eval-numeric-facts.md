# Rukh AI Coworker Quality Gate — Numeric Fact Preservation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the current-main Coworker quality-evaluation failure without lowering its 100% pass-rate or required-fact-recall gates.

**Architecture:** Keep the evaluator deterministic and schema-agnostic. Treat JSON numeric leaves as factual content when checking required terms, using a stable human-readable representation for integral floats. Keep boolean values excluded from numeric matching. Correct the synthetic image-prompt reference draft so it contains the exact required phrase already asserted by the fixture.

**Tech Stack:** Python 3.11+, pytest, existing Coworker schemas and offline quality evaluator.

**Spec:** `docs/frontend/CHATBOX_COMPLETION_2026-11-04.md` and the user-supplied Rukh AI engineering execution specification.

## Global Constraints

- Do not lower `pass_rate` or `required_fact_recall` thresholds.
- Do not skip, xfail, or weaken existing quality assertions.
- Preserve existing Coworker task schemas and provider contracts.
- Do not change production settings, feature flags, secrets, databases, deployments, or provider authority.
- Work only in `rumman52/Shuddho`; do not touch Long-Running.
- Keep all changes on `fix/rukh-quality-eval-numeric-facts-20261104` until reviewed.

## Review Focus

- Integral JSON floats such as `120.0` must satisfy a required term `"120"` without losing numeric type in the actual artifact.
- A changed numeric fact such as `121.0` must not satisfy required term `"120"`.
- Boolean values must not be treated as numeric facts (`True` must not satisfy `"1"`).
- Multilingual text, existing source-reference validation, forbidden-term checks and citation validation must remain unchanged.
- Synthetic fixtures must satisfy their own explicit required-term contracts without weakening those contracts.

---

### Task 1: Pin numeric structured-fact evaluation with a failing regression test

**Files:**
- Modify: `tests/test_coworker_quality_eval.py`

**Interfaces:**
- Consumes: `score(case, draft_value)` and the existing `spreadsheet-en-regional-orders` fixture.
- Produces: regression coverage proving that numeric JSON leaves count as required facts and mismatched values are rejected.

- [x] Add `test_numeric_structured_values_count_as_required_facts`.
- [x] Convert the fixture's 120 and 80 numeric cells to integral floats in a deep copy and assert required-fact preservation passes.
- [x] Change the North value to 121.0 and assert `"120"` appears in `missing_required_terms`.
- [x] Confirmed RED in PR CI run #41780272070: numeric regression failed at required-fact preservation before implementation.

### Task 2: Fix numeric fact extraction and fixture consistency

**Files:**
- Modify: `scripts/coworker_quality_eval.py`
- Modify: `tests/fixtures/coworker_quality_eval_cases.jsonl`

**Interfaces:**
- Consumes: JSON-compatible draft values traversed by `strings(value)`.
- Produces: strings from textual and numeric leaves, with booleans excluded and integral floats rendered without a trailing `.0`.

- [x] Extend `strings` to include `int` and `float` leaves while excluding `bool`.
- [x] Normalize integral floats to their integer-form text; preserve a stable representation for non-integral values.
- [x] Update the image-prompt fixture draft to include the exact required phrase `No text or logos`; do not change the required-term list.
- [x] Included in exact-head `uv run pytest -q`: 1,743 passed, 73 skipped, 6 warnings.
- [x] Exact-head `uv run pytest -q`: 1,743 passed, 73 skipped, 6 warnings. Heavy Coworker job still in progress.

### Task 3: Record evidence and review the bounded patch

**Files:**
- Create: `docs/engineering/RUKH_CURRENT_STATE_AUDIT.md`
- Create: `docs/engineering/RUKH_ROOT_CAUSE_REPORT.md`
- Create: `docs/engineering/RUKH_FEATURE_PRESERVATION_MATRIX.md`
- Create: `docs/engineering/RUKH_TECHNICAL_RISK_REGISTER.md`
- Create: `docs/engineering/RUKH_QA_REPORT.md`
- Create: `docs/engineering/RUKH_REMAINING_BLOCKERS.md`
- Modify: `docs/coworker-roadmap/PROGRESS.md`

- [ ] Record current-main SHA, merged PRs, current exact-head CI evidence, and the confirmed quality-evaluation root cause.
- [ ] Distinguish source implementation, repository CI, staging verification, production qualification and activation.
- [ ] Record external infrastructure items as NOT VERIFIED unless freshly checked in the current task.
- [ ] Review the diff for threshold weakening, boolean coercion, schema changes, secret exposure and unrelated edits.
- [ ] Run `uv run pytest tests/test_coworker_quality_eval.py -q` and the complete Python suite after the final change.
- [ ] Keep production unchanged; do not deploy, migrate, enable feature flags or merge.



## Execution evidence — 4 November 2026

- Base main: `56b1678ec92233df45b7a95911808c2fca222ccf`.
- Regression RED: run [#41780272070](https://github.com/rumman52/Shuddho/actions/runs/41780272070), test-and-build failed on the new numeric regression and the existing 0.8333 quality fixture; 1,741 passed.
- Fix head: `944b18ec56ab3faee69b028b0485c4904c4415c8`.
- Exact-head run [#41780778140](https://github.com/rumman52/Shuddho/actions/runs/41780778140): frontend passed; full lightweight Python suite passed 1,743 tests with 73 skips and 6 warnings; heavy Coworker suite still running at this checkpoint.
- Review: author self-review pending final CI; no independent review or merge claimed.
