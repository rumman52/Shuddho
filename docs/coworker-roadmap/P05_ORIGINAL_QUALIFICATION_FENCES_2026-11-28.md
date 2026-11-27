# Prompt 05 — original qualification fences (28 November 2026, Asia/Dhaka)

- Objective: preserve the independently recorded Day 9 veto into Day 10, reject reviewer conflicts before protected corpus access, and stream strict bounded post-admission evidence.
- Dependency and base: `8821f1151b95ded7c7ccb67a145ce8e49ab5e764`; prior integrated qualification #960 merged, but independent review gate failed. Current main workflow [45889495608](https://github.com/rumman52/Shuddho/actions/runs/45889495608) passed application and coworker checks but failed governance/merge. No authorization follows.
- Work: integrate the exact source/test changes from #961 (`8a7f38a038499bbde4cec3e54ba21a13c699c99a`), #962 (`e231eb0a0f3811ad7a702145a212c835ec096b51`), #963 (`1dd9fd7400dd63fc3bb4e6420b72ad84cf2ae88a`); these are alternative review branches, not three additional merges to apply after this candidate.
- Interfaces: existing Day 9 report and holdout, existing reviewer identity normalization, existing staging JSON reader (HTTP 200 default, 403 for denial). No public API or DB schema change.
- Files: `scripts/day10_release_decision.py`, `tests/test_day10_release_decision.py`, `scripts/ruke_pilot_eval.py`, `tests/test_ruke_pilot_eval.py`, `scripts/pilot_admission_verify.py`, `scripts/staging_release_freeze.py`, `tests/test_pilot_admission_verify.py`; this contract and the progress journal.
- Acceptance: original operator gate must literally pass; no unresolved high-severity finding; compare receipt must be complete or explicitly document access limitation; original generation receipt must agree. Reviewer and adjudicator cannot alias developer or corpus author (including Unicode width and case). D may independently review if not either conflicted role. Runtime, admitted and nonmember probes must use strict bounded streamed JSON and reject duplicates, nonfinite values, oversized bodies and nonidentity encoding; no secrets in errors.
- Reproduction: #961 tests-only workflow 46059418443: 22 intended failures, 4333 passed, 110 skipped. Fixed head workflow 46059641409: 4355 passed, 110 skipped; 551 separate. #962 tests-only workflow 46059733897: 30 intended failures, 4341 passed, 110 skipped. Fixed head workflow 46059938961: 4371 passed, 110 skipped; 551 separate. #963 locally extracted actual source and exercised HTTPX MockTransport: 18 failed before, 18 passed after. Its mandatory coworker CI is still required; lightweight CI skips its dependency-gated module.
- Verify: exact integration head mandatory application/coworker/browser/frontend/PostgreSQL18 CI, governance, independent review; inspect logs. No threshold reductions.
- Boundaries: no holdout bytes, genuine token, live provider call, production mutation, paid resource, telemetry, or pilot activation. Receipt structure is not independent attestation. Existing rollback/authorization gates unchanged.
- External prerequisites: owner/admin protected GitHub App credentials and required approval/check rules, independent D custody and genuine held-out results, operated recovery evidence and release proofs, staging migration parity, confirmed Render workspace, separate authentic Founder and Owner C approval.
- Out of scope: broad capability expansion, production deployment, live evaluation without the required authorization.

| Level | Status |
| --- | --- |
| Implemented | Integrated candidate, review pending |
| Repository-verified | Individual evidence above; integrated exact-head CI pending |
| Staging-verified | Not attested |
| Production-qualified | NO-GO |
| Activated | No |

Next: finish exact-head CI, address failures without weakening gates, obtain independent review and operational prerequisites. Do not merge sibling alternatives concurrently.

Additional integrated defect: JSON array/object workflow or language cells were used as hash keys, causing an uncaught TypeError and preventing a durable NO-GO decision. Test-first head `e36726e0cbe4d8e2be3cbb566eb785c8a13aace3`, [CI 46060638989](https://github.com/rumman52/Shuddho/actions/runs/46060638989): 10 intended failures, 4394 passed, 110 skipped, 6 warnings. A shared typed cell validator rejects malformed/unknown cells in both holdout and first-run binding. CLI tests require a write-once SOURCE_ONLY decision. New exact-head GREEN CI required.
