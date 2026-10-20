# V-01 — bind historical merge evidence to the original PR workflow

## Why this next task is needed
- `main` at task start: `25c79968d763ce8d5bdba53ed0d0d66ba7bb2562` (PR #520 merged).
- [PR #520](https://github.com/rumman52/Shuddho/pull/520) merged on 2026-10-20 **19:03:54 UTC** with zero submitted reviews. At merge, exact-head [workflow #39479360250](https://github.com/rumman52/Shuddho/actions/runs/39479360250) was **incomplete**: `test-and-build` had succeeded at 18:59:43; `coworker` only finished **CANCELLED at 19:04:38**, and `ci-merge-gate` only finished **FAILURE at 19:04:46**, both **after** the merge. The overall run concluded cancelled. This is a merge-before-gates-finished incident, not a pre-merge gate rejection; V-01 remains blocked.
- The read-only classifier in `scripts/v01_merge_evidence.py` previously matched `run.head_sha` to `pr.head.sha` but did **not** verify the originating head branch or head/base repositories. A foreign run at the same SHA could be misreported as clean evidence.

## Bounded contract
- **Goal:** for a merged PR's historical workflow evidence, reject a wrong or missing head branch, head repository identity, and base repository identity before reporting clean evidence.
- **Inputs:** existing read-only GitHub REST PR and workflow-run responses, completed required jobs, pre-merge review records. No new provider, token permission, ledger, schema or network destination.
- **Implementation:** `scripts/v01_merge_evidence.py`; nine regression tests in `tests/test_v01_merge_evidence.py`; this contract and `PROGRESS.md`.
- **Checks:** match `run.head_branch == pr.head.ref`, `run.head_repository.id == pr.head.repo.id`, `run.repository.id == pr.base.repo.id`, and the existing final head SHA; fail closed (`EvidenceError`, CLI exit code 2) on absent, non-integer or conflicting identity evidence. A deleted source repository may make historical evidence inconclusive, **not** clean.
- **Read-only scope:** no GitHub merges, PR approval, branch-protection edits, deployment, secret mutation, billing or production flag change.
- **Test-first proof:** [draft PR #521](https://github.com/rumman52/Shuddho/pull/521), tests-only SHA `b3c8b594caf39078fb22fe8c274e0ce1a264c70e` [CI #39481027487](https://github.com/rumman52/Shuddho/actions/runs/39481027487) **RED: 9 expected regression failures, 1,246 passed, 71 optional skipped**, in `test-and-build`. Implementation commit `d7030749785881a177a74ae1d1905c07a9396f04` follows.
- **Acceptance:** focused provenance + existing historical audit cases pass; exact-final-head CI `test-and-build` and `coworker` are checked, and a separate independent human review is obtained. `ci-merge-gate` must not be reported green merely because code tests pass without review.
- **Limitations:** the branch/ref and repository IDs are provenance checks, not immutable proof of a PR-number association when GitHub's `run.pull_requests` is empty on a merged PR. Historical reviewer privileges and mutable review status remain unverified. `no_incident_in_supplied_evidence` **never** proves GitHub's native branch policy.
- **Rollback:** revert the source, nine tests, and this documentation as a bounded change.

## External blocking controls
- [V-01 #484](https://github.com/rumman52/Shuddho/issues/484) remains OPEN: only an authorized GitHub owner/admin can configure and **negatively test** a non-bypassable `main` protection/ruleset requiring final-head `ci-merge-gate` and independent review. Do not merge draft PR #521 until final-head checks, independent human review and native enforcement have been demonstrated.
- [Staging prerequisites #291](https://github.com/rumman52/Shuddho/issues/291) remain separate and blocked. Production qualification/activation is not claimed.
