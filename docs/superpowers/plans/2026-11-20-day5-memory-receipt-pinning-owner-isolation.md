# Day 5 Exact Memory Receipt and Two-Owner Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Part 03 Day 5 hosted receipt-consistency verifier must reject empty/v1/v2 experiments that drift from the fixed brief/document/tool policy, import unselected memory in the preview or worker, or lack both owners' memory isolation.

**Architecture:** Extend `scripts/staging_days3_6_acceptance.py::check_day5` only. Require each arm to record fixed experiment inputs, authoritative explicit selected-memory pins in preview and worker, and two independent owner-scoped probes. The existing verifier remains read-only and returns `evidence_internally_consistent_not_live_attested`; a platform reviewer authenticates all referenced provider, browser, DB and HTTP receipts separately.

**Tech Stack:** Python (stdlib/pytest), repository's `uv`-locked GitHub Actions. No migration, provider/model invocation, auth account creation or new dependency.

**Spec:** Uploaded `03_Rukh_AI_Product_Workflows.docx` pages 6–7 (D05.T01/T02/T05/T08/T09/T10 and D05.G01/G04/G05); GitHub issue #731; Linear MD-7.

## Global Constraints

- Preserve Day 5's three **independent** owner-A provider/AgentRun identities, output digests and fact change, with fixed model, budget, prompt/source SHA and new *fixed document version, reviewed brief SHA and tool policy SHA*.
- For `none`, exactly empty `preview_selected_memory` and `worker_selected_memory`; for `v1`/`v2`, one exact `{"fact_id": "...", "version": 1|2}` in both (reject bool versions and additional pins).
- Preserve preview and actual worker context receipt references for all three experiment arms.
- Witness omission of an unselected **same-category** fact; require the selected and excluded memory category identities to match.
- Both managed owners must each successfully read a distinct privately owned fact, and each must receive 403/404 reading the other owner's fact, worker model context and private output. Preserve positive/negative API receipt refs.
- No code-level PASS can substitute for independently authenticated source, provider, browser, Supabase, Render, Vercel or reviewer evidence. This PR must not authorize staging release or change hosted acceptance status.

## Review Focus

1. Empty-selection preview or worker contains a memory: reject `test_day5_rejects_preview_or_worker_pins_that_differ_from_explicit_selection`.
2. A selected fact has wrong version, a bool version, or an additional pin: reject the same matrix.
3. Document version, brief digest or tool-policy digest changes between runs: reject `test_day5_rejects_drift_in_frozen_memory_experiment_inputs`.
4. Owner A reads B's fact, owner B reads A's context/output, or a positive owner read is missing: reject `test_day5_rejects_foreign_memory_fact_context_or_private_output_access`.
5. An unrelated-category "excluded" memory is used to claim the same-category test: reject `test_day5_same_category_unselected_fact_must_be_witnessed`.

---

### Task 1: Add failing contractual tests

**Files:**
- Modify: `tests/test_staging_days3_6_acceptance.py`

**Interfaces:**
- Consumes: existing synthetic `evidence()` and `gate.validate(*evidence, expected_revision=SHA)`.
- New test fixture: per-arm `owner_ref`, `document_version_id`, `reviewed_brief_sha256`, `tool_policy_sha256`, `preview_selected_memory`, `worker_selected_memory`, `preview_receipt_ref`, `worker_context_receipt_ref`; `unselected_memory.selected_category`/`unselected_category`; `owner_access.owner_a`/`owner_b` fact/context/output access and refs.

- [x] **Step 1: Commit characterization tests first.** `9a10fcf993e1cf951527f5df7a6d537a01848644` (test-only).
- [x] **Step 2: Watch RED before implementation.** GitHub Actions [run #44785191572](https://github.com/rumman52/Shuddho/actions/runs/44785191572), `test-and-build → Run Python tests`: **34 failed** new `DID NOT RAISE` adversarial cases, **2786 passed**, **103 skipped**, **6 warnings** in 28.61 seconds. This proves the pre-fix verifier admitted missing evidence, not a live acceptance result.

### Task 2: Implement the minimum fail-closed Day 5 validator

**Files:**
- Modify: `scripts/staging_days3_6_acceptance.py:236-300`

**Interfaces:**
- Consumes: the new Day 5 evidence keys above, frozen `release.owner_a_ref`/`owner_b_ref`, release provider/model/budget, and existing `text`, `sha`, `obj`, `count`, `referenced` helpers.
- Produces: same `check_day5(release, data, frozen) -> datetime` on success; `Days36EvidenceError` on missing, foreign or inconsistent evidence.

- [x] **Step 1: Implement exact selected pin and frozen input checks** without introducing new model/provider code; reject boolean/nonnumeric pins.
- [x] **Step 2: Require same-category exclusion and reciprocal owner fact/context/output HTTP proofs** with nonempty independent readback references.
- [ ] **Step 3: Verify the exact-head GREEN with `uv run --locked pytest -q tests/test_staging_days3_6_acceptance.py`, mandatory Day 3–6 receipt contracts and entire Python test suite.** Observe CI before marking complete; cancelled/queued/skipped is not success.
- [ ] **Step 4: Independently review PR diff and governed source/hosted release boundaries** before merge.

## Hosted acceptance prerequisites and handoff

- MD-6: founder/C authorized budget and release, safeguarded Supabase backup, isolated restore, aligned 0071+0072 migration, same-SHA API/worker/browser and independent platform readback. Current Supabase project `shuddho-staging` returned **zero public tables and zero listed migrations**; no SQL, project changes or account provisioning performed.
- MD-7: real managed owners A/B; actual three provider runs, context SHA readback, previews and private artifacts, denial checks, owner-scoped counts, signed independent review. This repo verifier checks only structural/chronological internal consistency.
- Render connector requires explicit workspace selection confirmation before service actions. Connected Vercel account returns no project associated with the Shuddho repository. ProductOS active project is unrelated; do not misattribute its artifacts.
- Never present test fixture or platform project metadata as an operated Day 5 PASS. Keep full Part 03 release NO-GO until its actual acceptance checklist is completed.
