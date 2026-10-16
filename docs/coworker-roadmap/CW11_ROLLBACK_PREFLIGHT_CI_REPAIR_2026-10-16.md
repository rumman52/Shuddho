# CW-11 / A-03 — Rollback preflight mandatory-CI repair

Date: 16 October 2026 (Asia/Dhaka)

## Objective

Repair the two deterministic fixture/configuration defects exposed by the mandatory coworker CI run for the merged CW-11 historical reviewed-task rollback preflight. Preserve the production rollback-preflight implementation and its fail-closed acceptance contract.

## Evidence at task selection

- Base: `main` `b0d6c56f81e81fef8da1cc75a0a0a215c89c992f` (merged PR #437).
- Exact implementation head tested by PR CI: `01c06271ee662f2d77304fc54165eaa66d926d1a`.
- CI run: #38915877509.
- `test-and-build`: passed.
- `coworker`: failed.
- `ci-merge-gate`: failed because `coworker` failed.
- Coworker result: 1402 passed, 2 failed.

## Reproduced failures

1. `test_reviewed_research_version_is_measured_by_cohort_stop_gate` enables the research service but constructs `Settings` without the backend-only search key required by current configuration validation. The test never calls a real provider.
2. `test_reviewed_skill_rollback_preflight_rejects_unfenced_or_unpinned_live_tasks` constructs the default `report_email` TaskCreate with no notes or document, which the current schema correctly rejects.

These are test-fixture defects. They do not demonstrate a production authorization failure.

## Repair

- Supply the existing repository test convention `fixture-only-search-key` and explicit `tavily` provider to the research cohort fixture. No provider call or real credential is used.
- Give each synthetic rollback-inventory task a bounded fixture note so it satisfies the existing TaskCreate contract.
- Do not change production rollback-preflight logic, permissions, worker authority, provider behavior, release flags or schema contracts.

## Acceptance

- The two previously failing tests pass.
- `tests/test_cohort_health_gate.py` passes with zero skips in the mandatory coworker job.
- Final branch-head `test-and-build`, `coworker` and `ci-merge-gate` all pass.
- No product authority or activation is introduced.

## Verification commands

```bash
uv run --extra coworker pytest tests/test_cohort_health_gate.py -k 'reviewed_research_version_is_measured_by_cohort_stop_gate or reviewed_skill_rollback' -q
```

Then rely on the repository's full mandatory CI job for the final exact-head evidence.

## Boundaries

No staging deployment, provider dispatch, production activation, paid provisioning or external transaction is performed by this task. The separate CW-11 historical worker-drain/staging qualification remains required after repository verification.
