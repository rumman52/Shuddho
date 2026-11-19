# Day 10 runtime capability contract — 19 November 2026

**Scope:** a reproducible **source-level** freeze defect, not a new GO, admission,
deployment, schema migration or operated pilot result.

## Task contract

- **Objective:** allow the actual authenticated `/api/v1/runtime-manifest`
  shape to pass its **exact** Day 9–10 API evidence checks without silently
  expanding the original 43 independently reviewed release capabilities.
- **Base:** `main` at `33aefddc5a5fd918d334c981769c6f9cf1b0b5bf`.
- **Dependency:** merged [PR #794](https://github.com/rumman52/Shuddho/pull/794);
  distinct pilot-identity [PR #796](https://github.com/rumman52/Shuddho/pull/796)
  is a concurrent draft and must receive independent review/rebase.
- **Reproduced source failure:** `services/coworker/api.py` emits **44**
  runtime-manifest boolean keys. The strict shared
  `RUNTIME_CAPABILITY_KEYS` contains **43**. The extra
  `grounded_conversation_replies` field is read by the existing
  ConversationWorkspace UI and is computed from the **same expression**
  as `conversation_replies`. Before this fix, three separate gates rejected
  the actual API response simply because the complete key sets differed:
  `staging_release_freeze.verify_runtime`,
  `day10_release_decision.decide`, and
  `pilot_admission_verify.verify_live_runtime`.
- **Required source interface:** `RUNTIME_CAPABILITY_KEYS` remains the
  authoritative 43-key rollout, candidate generation and **worker** contract.
  The API inventory is exactly those 43 plus one named derived UI indicator.
  `api_runtime_capabilities_match_rollout(actual, declared)` requires
  strict dictionaries, exact key sets, all values exact `bool`, exact
  equality for each 43-key authority flag and
  `actual["grounded_conversation_replies"] is actual["conversation_replies"]`.
  Any new, unknown, omitted, numeric or independently toggled field fails.
- **Compatibility:** no API response, UI behavior, provider selection,
  schema, flag default or worker runtime contract is changed. No generated
  capability can gain independent execution authority.
- **Tests:** source AST inventory matches the *real* API handler, staging
  freeze passes correct 44-field readback, strict negative cases reject
  drift, the final Day 10 decision distinguishes API 44 from worker 43,
  and the post-admission verifier checks the same invariant.
- **Source checks:**

```bash
uv run --extra coworker pytest -q tests/test_staging_release_freeze.py \
  tests/test_day10_release_decision.py tests/test_pilot_admission_verify.py
```

The full exact-head Coworker CI and independent PR review are required
separately. Tests here are synthetic; the original project 100-task / 54-exit
ledger **does not gain any accepted item** from these tests alone.

## Evidence classification

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Source branch | Patch and fail-closed tests; PR-head SHA recorded in GitHub |
| Repository-verified | Pending exact-head CI | Run URL and JUnit required |
| Staging-verified | **NO** | No matching actual frozen API/worker deployment |
| Production-qualified | **NO-GO** | Independent D holdout, C recovery and live gates still absent |
| Activated | **NO** | No pilot admission or allowlist edits |

## Independent release prerequisites (unchanged)

One exact release ID, API/worker source and image digests, frozen manifest
SHA-256, schema/model/provider identity, reviewed 43 authority flags and this
derived API-field check. Independent D must control a fresh 40-case
research/report-email × Bangla/English holdout (10 per cell), prove developer
negative-read and D positive-read, have two blinded human reviewers, retain
first-run receipts and meet **>=36/40 overall, >=9/10 per cell, and all 40
security checks**. C must operate **20/20** real PostgreSQL/Temporal/storage
recovery scenarios. Live planner, curated quality, rollback/restore,
in-flight cancellation, paused scheduling, both-way owner isolation and
golden multi-turn deliverable must also pass. Run the unchanged canonical
cohort and Day 10 decision gates on authentic exact-release evidence.
Founder and owner C approvals must be distinct, authenticated and bound to
that release; an authorized operator alone may then manually admit 5–10
allowlisted users and verify full-cohort access/nonmember denial.

**Any new source commit changes the release candidate** and invalidates
older exact-SHA freeze/test/approval receipts. Do not use synthetic CI,
inherited earlier runtime readbacks or a green source PR as GO.

**Next action:** exact PR-head CI and independent code review. Owner C must
independently authorize staging costs and resource changes, perform backup
and backed-up schema alignment, provision matching worker/Temporal/storage,
and operate real identity/recovery checks. D and reviewers must operate
their own custody and blinded evaluation. **Release state: SOURCE_ONLY / NO-GO.**
