# V-01 — read-only historical pre-merge evidence audit (21 October 2026)

- **Objective:** make already-observed unauthorized/early merge evidence reproducible from GitHub's final PR revision, exact-head workflow, job completion timestamps, and submitted reviews. **This is detection and documentation, not enforcement.**
- **Dependency / source truth:** `main` merge commit `1f50654d514a5c3c0079886c7154cecc4e793e8e` includes PR #519. Its [exact-head workflow #39471452728](https://github.com/rumman52/Shuddho/actions/runs/39471452728) failed the review gate at 18:30:38 UTC on 20 October, while the merge occurred at 18:42:34 UTC with zero submitted reviews. `test-and-build` and `coworker` passed.
- **Base:** `main` after #519; **branch:** `audit/v01-premerge-evidence-20261021`; draft PR for this source-only task.
- **Reused interfaces:** public/read-only GitHub REST PR, workflow, workflow job, and review endpoints; no new storage, ledger, approval authority, or runtime service.
- **Source:** `scripts/v01_merge_evidence.py`; **tests:** `tests/test_v01_merge_evidence.py`; this contract and `PROGRESS.md`.
- **Interface:** `python -m scripts.v01_merge_evidence --repository rumman52/Shuddho --pr 519 --run 39471452728`. Optional `GITHUB_TOKEN` enables authenticated **read-only** requests; never supply secrets in arguments, logs or issue comments.
- **Acceptance:** bound evidence to the final PR head, require a completed PR-triggered run, inspect all three named job conclusions and finish times relative to merge, reject false reviewer eligibility and stale/self/post-merge approvals, fail closed on malformed/partial/inconsistent evidence and pagination overflow.
- **Classification:** `observed_governance_incident` flags failures, late checks, missing independent current-head approval or open independent change requests. `no_incident_in_supplied_evidence` means only that these incidents were **not observed** in the supplied API snapshots. Neither classification proves effective native branch protection.
- **Exit codes:** 1 observed incident; 2 unusable/unavailable evidence; 0 no incident observed in bounded supplied evidence (NOT a merge-authorization signal).
- **Tests:** `PYTHONPATH=. python -m pytest tests/test_v01_merge_evidence.py -q`; Python syntax `python -m py_compile scripts/v01_merge_evidence.py`; then full exact-final-head GitHub CI.
- **Security:** 20-second bounded read-only HTTPS requests; bounded pagination (10 pages, 100 entries per page); fail closed; no external side effects beyond reads. Tests use local synthetic evidence, not live policy operations.
- **Rollback:** remove the read-only script and tests. No feature enabled, schema migration, provider changes, permissions, production settings, stage/production activation or workflow wiring.
- **External blocker:** Issue [#484](https://github.com/rumman52/Shuddho/issues/484) remains OPEN. Authorized repository/organization admin must configure mandatory independent reviews, stale-approval dismissal, required final-head `ci-merge-gate`, protected workflow/review-source ownership and no ordinary bypass. A temporary PR must demonstrate that a failed gate **cannot** merge, plus a positive reviewed case. This connector's branch-protection GET returns 403, while branch summary currently reports `protected: false` and ruleset list `[]`. A read-only audit is not a substitute.

## Completion levels

| Level | Current evidence |
| --- | --- |
| Implemented | Script and focused regression tests committed on a review branch |
| Repository-verified | Focused local tests only at publication; exact-head GitHub CI required |
| Native merge policy verified | **NO — #484 blocked on admin and negative controls** |
| Staging-verified | Not applicable to the script; staging program remains blocked by #291 |
| Production-qualified | No |
| Activated | No |

**Next action:** inspect exact-final-head PR CI; arrange independent human source review. Separately, authorized GitHub admin must enforce and demonstrate native protection before V-01 acceptance.
