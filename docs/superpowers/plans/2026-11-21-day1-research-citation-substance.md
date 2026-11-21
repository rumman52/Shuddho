# Day 1 D research evaluator — reject quote padding masquerading as grounding

**Source of truth:** The five-part Rukh AI instruction prompt, particularly Part 01 D corpus/scoring and Part 03 source-grounded outcomes; [Ruke AI 10-day plan Day 1 ¶141–152](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit), [CTO board #737](https://github.com/rumman52/Shuddho/issues/737), [Day 1 #727](https://github.com/rumman52/Shuddho/issues/727), [D custody #665](https://github.com/rumman52/Shuddho/issues/665), `AGENTS.md`, `docs/coworker-roadmap/SPEC.md`, [Day 1 evaluation contract](../../coworker-roadmap/DAY1_EVALUATION_2026-11-10.md), and the actual `scripts/pilot_workflow_eval.py::score`.

**Baseline:** `main` commit `05e582d6a5e6174668b3287685966929d3b87460`, after merged PR #870 on exact-byte evidence input. No open PR at baseline readback.

## Root cause and narrow design

In `score`'s `research_brief` case, the `citation_grounding` check validates `_norm(citation.quote) in _norm(source.text)`. The production `ResearchCitation.quote` schema strips leading/trailing whitespace and enforces a 20-character *raw* minimum, but **internal** whitespace runs still contribute to its character count. For example `Keep` + 20 spaces + `the` passes the 20-character schema while `_norm` collapses the string to `keep the` (8 characters), which occurs in the pinned historical source. A padded source-looking fragment therefore appears grounded even though its substantive normalized quote is below the required 20-character minimum. Genuine frozen development reference citations have normalized lengths of at least 22, so normal calibration remains valid.

**Ruling:** Harden only the offline scorer, not the production draft schema. Require each normalized citation quote to contain *at least 20 characters of meaningful normalized text* and occur within the normalized, verified source snapshot. Keep separate source-id equality and fact-specific citation alignment. This is a deterministic floor against padding, not a semantic entailment/human-quality proof. Preserve the native research schema, 40 development / 40 blocked heldout, historical/false-send claims, costs and budgets, all existing public interfaces.

## Task 1 — prove RED with cases that remain schema-valid

- [ ] Add four parameterized negative tests to `tests/test_pilot_workflow_eval.py`, English and Bangla with two inputs: a short source fragment whose two existing words are separated by 20 ordinary spaces or 20 newline characters (both normalized to 8 characters). Append a *fourth* finding containing a non-fact extra claim and its source-id bound padded quote while retaining the original three fact-grounded findings. Assert `schema_valid=true`, `citation_grounding=false`, `passed=false`. The old scorer should fail only these assertions, not schema parsing.
- [ ] Commit tests alone, run GitHub Actions on exact test-only SHA and record the four actual failures (or adjust test if a wrong failure happens) before production correction. Do not call an unobserved RED test a pass.
- [ ] Positives: all 40 reference outputs, both languages and both workflows, still qualify *only* as source-authored calibration, `quality_qualified=false`, zero provider calls.

## Task 2 — implement minimal GREEN

- [ ] In `scripts/pilot_workflow_eval.py::score`, replace the nested `all` quote substring predicate with a condition checking `len(_norm(c.quote)) >= 20` before source substring check. Do not alter `ResearchCitation` production Pydantic rules.
- [ ] Inspect exact corrected GitHub Actions head `test-and-build` (Python + contracts), full `coworker`, PG18, frontend, browser and ancestry. `governance-audit` skipped on PR is not native merge protection and `ci-merge-gate` may report failure without actual approved independent review. No local checkout command is claimed unless actually executed.

## Task 3 — evidence and handoff

- [ ] Create `docs/coworker-roadmap/DAY1_PILOT_RESEARCH_CITATION_SUBSTANCE_2026-11-21.md` and prepend `PROGRESS.md` with RED/GREEN revision+run and scoped limits. Open a DRAFT PR from the dedicated branch; link Day 1 #727, D custody #665 and Linear MD-5.
- [ ] Record external blocker: the real native protected-main rule has previously allowed merged PRs with `ci-merge-gate=FAIL`, PR governance SKIPPED, no submitted human reviews. Do not weaken the source checks; require C/admin action, an operated negative and positive merge test and actual independent review.
- [ ] No paid inference, real customer data, D heldout, Supabase migration, Render provisioning, Vercel deploy, ProductOS demo changes, PostHog telemetry or pilot activation. Founder/C staging resources/restore and exact release signoff remain separately blocked.

**Done for this branch:** Source-only fix and a reviewable draft PR with observed RED and passing final-head focused/full test evidence. **Not done by this branch:** Independent D custody, actual staging recovery, native governance or release GO.
