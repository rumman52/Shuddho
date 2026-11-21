# Day 1 D — citation quote substance in the bilingual research scorer

**Disposition: SOURCE_ONLY; controlled-pilot NO-GO.** Narrow scorer change; does not measure a model, deliver semantic entailment, establish D-only holdout custody, or approve release.

## Task contract and authority

- **Objective:** Reject research citations whose raw quote length is inflated with *internal whitespace* so the normalized quote is too short to substantiate a finding. Preserve 40 development/40 candidate holdout; score both English/Bangla as a deterministic regression only, not human acceptance.
- **Source:** User's Rukh AI five-part execution prompt (Part 01 foundation D; Part 03 grounded research and reports), [Ruke AI ten-day plan Day 1 ¶141–152](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit), [CTO #737](https://github.com/rumman52/Shuddho/issues/737), [Day 1 #727](https://github.com/rumman52/Shuddho/issues/727), [independent D #665](https://github.com/rumman52/Shuddho/issues/665), `AGENTS.md`, `SPEC.md`, [D evaluator source record](DAY1_EVALUATION_2026-11-10.md).
- **Dependency baseline:** `main=05e582d6a5e6174668b3287685966929d3b87460` after merged exact-byte evaluator PR #870, private candidates still developer-readable. No open PR at initial readback.
- **Branch and review:** `fix/day1-pilot-research-citation-substance-20261121`; [draft PR #872](https://github.com/rumman52/Shuddho/pull/872).
- **Existing interfaces:** `scripts/pilot_workflow_eval.py::score(case:dict,draft_value:dict)->dict`, `_norm(text)->str`, `services/coworker/schemas.py::ResearchCitation`. No public interface or production schema change.
- **Observed root cause:** Production Pydantic `StrictModel` strips *leading/trailing* whitespace before `quote` min_length=20 but does not collapse *internal* runs. `"Keep" + " "*20 + "the"` passes Pydantic then normalizes to `keep the` (8 characters). That string occurs in the already hash-verified source, so the old scorer's substring-only `citation_grounding` admitted an extra non-fact finding as cited. The same works with internal newlines. This is false-positive deterministic evidence-shape scoring, not proof of an actual external hallucination.
- **TDD RED:** Test-only SHA `564a8c2191c643cdfde885c7eb95a2cb43c718a1`, [Actions #44923376923](https://github.com/rumman52/Shuddho/actions/runs/44923376923) `test-and-build`: **4 expected FAILED / 3,537 PASSED / 105 SKIPPED / 6 WARN**. `test_research_rejects_whitespace_padded_short_evidence` failed [spaces-en], [spaces-bn], [newlines-en], [newlines-bn] with `assert True is False` on `citation_grounding`, *not schema or collection*. Original fact-grounded findings remain untouched, appended source-id bound finding is still a schema-valid `ResearchFinding`.
- **Minimal correction:** `4ae1afcaacef7403f14669b3e7c6b84ae5308d03` adds `len(_norm(c.quote)) >= 20` before source-substring matching in research `score`. Frozen development citation quotes have normalized minimum length 22; positives should remain valid. Existing fact-to-citation alignment, direct language checks, false-send checks, source scope, JSON/hash/provenance checking and `HeldoutAccessBlocked` remain unchanged.
- **Tests:** Exact final-head GitHub Actions [PR checks](https://github.com/rumman52/Shuddho/pull/872/checks): `test-and-build`, frontend, browser, PostgreSQL 18 compatibility, `coworker`, ancestry and merge-gate; do not infer native protection from PR-event skipped `governance-audit`. If no local checkout command executed, none is claimed. The repo skill's focused command is `uv run --extra coworker pytest -q tests/test_pilot_workflow_eval.py`.
- **Secrets, owner, network and budget:** 0 model/provider calls, 0 external spend, 0 customer data access, 0 new secrets or egress; no change to inference timeout/cost/approval/cancellation. Deterministic local offline scorer remains 2 MB input bounded and 40 cases per invocation; no release gate bypass. Roll back by reviewed PR, not by weakening corpus requirements.
- **Host read-only context:** Connected Supabase `shuddho-staging` ACTIVE_HEALTHY PG17.11; source/host schema mismatch (actual `0070` vs repo `0072_merge_0071_heads`), no authorized isolated restore. Render only unselected owner workspace, Vercel Shuddho project search empty, ProductOS demo unrelated, PostHog capture unapproved; no resource/DB/credential/telemetry mutation.
- **Known limitations:** Normalized quote length is a lexical floor, not semantic proof that a cited passage supports the claim, and source-authored calibration is not a live model success. Human review required on every scored output. Direct corpus developer-readable holdout still blocked.

## Completion evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Reproducible RED | **PROVED** | [Run #44923376923](https://github.com/rumman52/Shuddho/actions/runs/44923376923): 4 fail / 3537 pass / 105 skip / 6 warnings |
| Source correction | **IMPLEMENTED** | `4ae1afcaacef7403f14669b3e7c6b84ae5308d03` |
| Final-head CI | **PENDING readback** | [PR #872](https://github.com/rumman52/Shuddho/pull/872/checks) |
| Independent human PR review | **BLOCKED_EXTERNAL** | No automated code agent can self-sign the independent native approval |
| Native protected-main | **BLOCKED_EXTERNAL** | Prior PRs #863/#870 merged with failed merge gate, 0 submitted reviews; Owner C/admin to reconcile protected App, ruleset 27324410 and operate denied/permitted controls |
| Staging operated restore | **BLOCKED_EXTERNAL** | Founder+C approved DB/objects/identity/worker/Temporal and retention/spend resource decisions plus actual isolated restore |
| 40-case blind holdout/20 recoveries | **BLOCKED_EXTERNAL** | Human D access isolation, replacement of exposed candidates, freeze and operated traces |
| Exact-release pilot activation | **NO-GO / off** | Independent Founder+Owner C GO/NO-GO receipts are still required |

**Historical progress caution:** The 19 Nov v4 ledger's 18/100 tasks PASS, 5/54 exit gates PASS, 0/10 days accepted is not automatically upgraded by merged PRs. Only a fresh per-row actual receipt review may alter those numbers.
