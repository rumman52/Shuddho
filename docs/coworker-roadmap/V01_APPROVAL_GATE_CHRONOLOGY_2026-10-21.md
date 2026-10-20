# V-01 historical review-to-CI chronology — bounded engineering task

**Date:** 21 October 2026 (Asia/Dhaka)  
**Base:** `13360a9cd4e2d64fa9f2f2bf8c35befd4ca531ad` (merged PR #522)  
**Draft PR:** [#523](https://github.com/rumman52/Shuddho/pull/523)

## Root cause

The read-only historical classifier `scripts/v01_merge_evidence.py` accepted separately (1) a successful `ci-merge-gate` job completed before PR merge and (2) independent head-matching approval submitted before PR merge. The checks were not chronologically joined. If **every currently effective eligible approval was submitted after the CI review gate finished**, the report could incorrectly say `no_incident_in_supplied_evidence` even though that exact run could not have validated any eventual approval.

This applies to **historical supplied evidence**, not repository-authoritative merge control. A code audit cannot enforce branch rules.

## Test-first reproduction

- **RED-only SHA:** `f3f6be69616a693ddd9947398d90e0d911598bb0`, tests-only edit.
- [Actual RED CI #39487371765](https://github.com/rumman52/Shuddho/actions/runs/39487371765), `test-and-build`: **3 expected failures, 1,263 passed, 71 optional skips, six warnings**. Failed cases: post-gate only approval, multiple post-gate approvals, dismissed-then-late-reapproval. Existing evidence classifier erroneously reported no findings. Pre-gate independent approval plus later other reviewer **passed** as positive control.
- **Fix SHA:** `8631ebec491180aba9fa7d3a4ea3a72900cc43ab`. Minimal isolated change caches all required job completion timestamps and eligible latest-approval submitted timestamps. If approvals exist but every approval postdates the selected `ci-merge-gate` completion, add `ci-merge-gate:completed_before_independent_approval` and classify as observed governance incident. Reuses existing timezone-aware `_when` parser and validation.
- **GREEN requirement:** exact *final PR head* `test-and-build` plus mandatory `coworker` integration and `ci-merge-gate` must each succeed. Consult run timestamps and avoid treating an earlier test-only RED run, a cancelled run or a code-only green job as complete.

## Boundaries

- Valid, latest, independent current-head approval **before** gate completion remains a no-incident control even if an additional independent reviewer approves after the gate.
- A prior approval later dismissed and only re-approved after the gate **does not** retroactively satisfy the earlier gate.
- Approval after merge remains excluded by existing classifier; missing/malformed evidence remains fail-closed.
- Even a no-incident report cannot prove required native GitHub branch protection, current permissions, merge locks or out-of-band reviews.
- Existing historical classifier is read-only. No workflow policy, credentials, deployment, provider, release flags, schema or paid infrastructure changes.

## Actual repository governance is still blocked

[PR #522](https://github.com/rumman52/Shuddho/pull/522) merged at **2026-10-20 19:45:33 UTC** with **zero submitted reviews**. Its [exact-head CI #39484713573](https://github.com/rumman52/Shuddho/actions/runs/39484713573) showed `test-and-build` success (19:38:26), but `coworker` cancelled only **after merge** (19:45:58) and `ci-merge-gate` failed **after merge** (19:46:08). Incident recorded on [V-01 issue #484](https://github.com/rumman52/Shuddho/issues/484#issuecomment-6300108322).

Native effective rulesets/protection are not proven. Repository owner/admin must configure required final-head CI, independent human approval and non-bypassable ordinary merge restrictions, then run negative and positive-control merge tests. **PR #523 remains draft and unmerged pending human review and all required CI.** [Staging issue #291](https://github.com/rumman52/Shuddho/issues/291) is separately blocked.
