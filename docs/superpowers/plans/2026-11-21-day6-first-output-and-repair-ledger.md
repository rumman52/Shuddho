# Day 6 Original Development Outputs and Separate Repair Reruns — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development, superpowers:verification-before-completion, and superpowers:requesting-code-review. Treat synthetic receipts as structural tests, not independent proof of hosted work.

**Goal:** Preserve the original 40 quality-scored outputs as immutable first attempts, explicitly repair the greatest demonstrated original failure, and prevent reruns from replacing first-run scores or inflating the >=9/10 per workflow-language cell requirement.

**Architecture:** Extend the existing read-only `scripts/staging_days3_6_acceptance.check_day6` contract with per-development-case first output digest, original run and model IDs, provider/storage/score receipt references, positive byte count and timestamps. Validate the four-cell rate against the 40 first outputs before evaluating a distinct `repair_reruns` ledger, binding each repair to the original failed case and requiring better independently scored output with a new run/request. No runtime, schema, provider, or artifact writing changes are made.

**Tech stack:** Python/pytest, GitHub Actions. No new dependencies or migrations.

**Original source:** `03_Rukh_AI_Product_Workflows.docx` pp. 8–9, D06.T10, D06.T07 and G05; p.10 independent review. Related GitHub [#732](https://github.com/rumman52/Shuddho/issues/732), Linear [MD-7](https://linear.app/md-rumman-ali/issue/MD-7/rukh-ai-days-3-6-complete-hosted-golden-workflow-and-same-release).

## Task 1 — RED: show original acceptance can be gamed

- [x] Add test fixture preserving 40 unique initial provider requests and first run IDs, canonical output SHA-256, byte lengths, provider/output readback refs, and timestamps for original scoring; record one scored initial failure in a cell while retaining 9/10.
- [x] Add separate repair ledger for that worst failure: retained original run/output hash/ref, distinct rerun/run/provider IDs, changed output SHA, improved score anchored to the repaired output digest, separate retrieval/receipt references, chronology, factual/owner/citation/no-send checks.
- [x] Add adversarial tests for first-output replacement, duplicate IDs, missing/synthetic readbacks, model/score subject mismatch, rerun adoption into the initial 40, missing original failure, wrong target, unrepaired lowest score, overwritten original and non-improving reruns.
- [x] Commit tests **before production**: `ea8074f9505fcbd70b3eac5681f4f92fd2955750`. GitHub Actions **RED** [#44916394511](https://github.com/rumman52/Shuddho/actions/runs/44916394511) Python step shows **84 expected missing-guard failures, 3,340 passed, 105 skipped, six warnings**.

## Task 2 — GREEN candidate: require preserved first attempts and independently scored repairs

- [x] Bind each original case to an isolated unique first run/model identity, nonzero bytes, canonical output SHA-256, matching scored digest, chronologically valid provider/score receipts.
- [x] Compute exactly ten original cases per workflow/language and >=9 quality scores of >=7 from **initial outputs alone**.
- [x] Require one or more first-run failed cases and an entirely separate repair for at least one worst-scoring case. The repaired output must remain associated with the original first run/provider/digest and an authentic original readback reference, use new provider/run IDs, have changed content hash, retained original file, and scored improvement to >=7, <=8.
- [x] Preserve fact, owner isolation, citations and zero external-send checks for both first-run and repaired cases.
- [x] Implementation commit: `cf958e59cbbabb114bd92ab6a337fab2b498c69d`.

## Task 3 — Verify, independently review and document release boundaries

- [ ] Verify full Python and Days3–6 hosted receipt contract suite at final PR head; inspect exact-head Coworker, PostgreSQL 18, browser, frontend, ancestry, governance and any CI merge-gate.
- [ ] Request independent code review; do not self-approve or merge without mandatory checks.
- [ ] Link PR and test receipts to issue #732 / Linear MD-7. Keep Day6 and full Part03 **hosted NO-GO** until actual operator-hosted provider requests, 40 first-run model outputs, original stored hashes, separate scored repair readbacks, A/B owner authorization, same-SHA release and independently authenticated review are collected.

**Caveat:** `scripts.staging_days3_6_acceptance` validates internal consistency of user-provided JSON receipts only and returns `evidence_internally_consistent_not_live_attested`. It cannot verify raw model bytes or the first-run custody chain without authentic platform readbacks. Do not claim hosting, create synthetic users as a substitute for real managed owners, deploy paid resources, send email, or alter staging schema for this source-level PR. Linked Supabase staging project has no managed public schema or Auth users. Connected ProductOS project is unrelated; Vercel has no Shuddho-linked project, Render workspace selection needs explicit confirmation, PostHog project is not confirmed.
