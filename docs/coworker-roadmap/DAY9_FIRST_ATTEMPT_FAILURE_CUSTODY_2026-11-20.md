# Day 9 / First-run failure and timeout custody contract

- **Objective:** Preserve genuine first-run failures and timeouts among the 40 independent heldout rows without inventing a valid draft, hiding the failure, relaxing security, or changing denominator arithmetic.
- **Owner / scope:** D09.T04, D09.T05 and D09.G02/G06; D controls independent heldout bytes and judges, A repairs only the source evidence validator, C authenticates protected platform receipts.
- **Base SHA:** `f5090638be33d7e648736daf533e4b25c307d13d` (main on 20 November 2026).
- **Review branch / PR:** `codex/day9-first-attempt-failure-evidence-20261120`, [#817](https://github.com/rumman52/Shuddho/pull/817).
- **Interfaces:** `candidate_ledger`, `score_reviews`, `ruke_pilot_eval.main`; no new endpoint, database schema or application side effects.
- **Files:** `scripts/ruke_pilot_eval.py`, `tests/test_ruke_pilot_eval.py`, Day 9 operator manual, dated progress and this task/plan.
- **RED:** test-only head `3042a737cdf1fafc9495bfd54b9e4c7142341dd8`, [Actions #44739458984](https://github.com/rumman52/Shuddho/actions/runs/44739458984), main Python step **11 failed / 2545 passed / 101 skipped**. Source rejected real no-draft attempt as a malformed draft.
- **New failure-row interface:** `attempt_status` = `failed` or `timed_out`; `output=null`; `source_refs=[]`; normalized `failure_code`; lowercase `trace_sha256`; UTC `attempt_started_at`, `attempt_finished_at`. Include existing full frozen manifest/run/provider/model/registry/rollout/time identity. A legacy successful row remains valid without `attempt_status`.
- **Tamper-resistant receipt:** The `output_sha256` of a failure row is the canonical *failure-record* SHA (not a synthetic output). Include case ID, distinct run ID, manifest digest, failure code, status, timestamps and private trace digest in the preimage. The public receipt marks `evidence_kind=failure_record`, `output_present=false`, `failure_trace_sha256`. C/D must independently inspect/authenticate private trace bytes.
- **Acceptance:** exactly 40 rows and unique runs; all successes still parse production draft/citations; failed rows cannot claim a passing deterministic check or count as accepted; 80 independent scores and 40 independent security booleans required; failures remain in the relevant 10-case cell; missing usage remains unknown, never zero.
- **Tests:** `uv run --locked --extra coworker pytest -q tests/test_ruke_pilot_eval.py tests/test_day10_release_decision.py tests/test_cohort_release_gate.py`, full `test-and-build`, Coworker, PG18, frontend, browser, ancestry and governance gates on exact head. No mandatory skips.
- **Safety:** no private corpus, key, holdout, real provider payload, account identity or source content in repository. No authority to operate protected staging, run paid workers, alter flags or admit a pilot.
- **Rollback:** revert the one bounded feature commit; valid historical `succeeded` inputs retain original behavior.
- **External blockers:** D must establish access denial and private corpus; C must authenticate storage/PostgreSQL/Temporal operated receipts; admin fixes App/ruleset; Founder/Owner C provide separate release approvals on exact digest.

## Completion levels

| Level | Evidence status |
| --- | --- |
| Implemented | Fix committed on PR #817 review branch; exact head recorded in GitHub |
| Repository-verified | Await full exact-head CI, independent review |
| Staging-verified | Not established |
| Production-qualified | NO-GO; human review and operated evidence missing |
| Activated | No |

