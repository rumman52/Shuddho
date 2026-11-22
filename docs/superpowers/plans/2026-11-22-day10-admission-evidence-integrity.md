# Day 10 post-admission evidence integrity implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Make the pilot-access verifier consume a rollout and its approval digest from the same bounded read, and preserve private, exclusive first-run receipts.

**Architecture:** Do not create a second evidence format or path reader. Reuse Day 10's existing descriptor-scoped `read_json_with_sha` and Day 9's `immutable_write` inside the current Day 10 admission verifier. Preserve all existing cohort/approval checks.

**Tech Stack:** Python 3.11, pytest, GitHub Actions Coworker `--extra coworker` mandatory zero-skip gate.

**Spec:** `docs/coworker-roadmap/DAY10_ADMISSION_VERIFIED_ROLLOUT_PRIVATE_RECEIPT_2026-11-22.md`, Part 05 pp. 5–7.

## Global constraints

- No live admission or allowlist mutation; five to ten distinct members and an explicitly denied nonmember remain mandatory.
- Do not disclose private tokens/subject identifiers, or infer Founder/Owner C approvals from JSON.
- Preserve current `require_release_decision` and `immutable_report` function interfaces.
- Retain exact 43 runtime booleans, canonical cohort GO and no owner/production side effects.

## Review focus

- A rollout pathname swapped after the initial read must not change its attested digest.
- Pre-existing report path must remain immutable, including symlink targets.
- New report must be private even when the operator's umask permits group/other reads.
- Malformed, missing, oversized or linked release input must continue to fail closed.
- A source-level synthetic test is not evidence that 5–10 live credentials were admitted.

---

### Task 1 — Trustworthy rollout SHA and private receipt

**Files:** `scripts/pilot_admission_verify.py`, `tests/test_pilot_admission_verify.py`.

**Interfaces:** Input `require_release_decision(Path, Path, str) -> tuple[dict, str]`, output `immutable_report(Path, dict) -> None`; no schema changes.

- [x] **Step 1: Add red tests.** Simulate path replacement after the bounded rollout JSON read but before the old hash read. Force `umask 022` and assert `0600` on first access receipt.
- [x] **Step 2: Observe RED.** Test-only commit `2444c60f8c9c61d672115700b85271b1b0345896`, [Actions run #45019756125](https://github.com/rumman52/Shuddho/actions/runs/45019756125) Coworker mandatory Day 10 step: `2 failed, 385 passed`; observed digest mismatch and mode `0644`.
- [x] **Step 3: Minimal correction.** Import `read_json_with_sha` from Day 10, use the returned digest without reopening; import `immutable_write` from Day 9 and retain the existing collision error. Code commit `375d9525a861a8c497a8f95fe8636a47913ad090`.
- [ ] **Step 4: Observe GREEN on final head.** Run mandatory CI with `tests.test_pilot_admission_verify` zero-skips, `tests/test_day10_release_decision.py`, release-contract check and surrounding suite; inspect whole final-head workflow and record any failed/skipped jobs.
- [ ] **Step 5: Independent review.** Ask a separate real reviewer to verify byte-identity, ownership, file permissions and remaining runtime controls; do not merge unreviewed.

### Task 2 — Evidence and review handoff

**Files:** `docs/coworker-roadmap/DAY10_ADMISSION_VERIFIED_ROLLOUT_PRIVATE_RECEIPT_2026-11-22.md`, `docs/coworker-roadmap/PROGRESS.md`.

- [x] **Step 1: Record the exact RED receipt and source-only fix.** Preserve the test-only commit, code fix SHA, scope, blocker owner and no admission.
- [ ] **Step 2: Attach final-head check/review receipts.** Do not promote historical v4 task/exit counts from source changes.
- [ ] **Step 3: Owner action.** Owner C/admin enforces main CI/review protections and D/C, Founder/Owner C separately fulfill real custody, operated recovery and signoff prerequisites before any pilot enrollment.

**End state:** Draft PR and source regression evidence; no claim of operated staging, independent human validation, pilot readiness or activation.
