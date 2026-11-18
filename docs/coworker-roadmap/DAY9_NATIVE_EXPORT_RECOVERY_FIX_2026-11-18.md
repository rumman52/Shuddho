# Day 9 — native export recovery CI fixture compatibility (18 November 2026)

- **Objective and user-visible behavior:** restore the required Coworker CI coverage of lost object-store PUT response and hard worker-loss/orphan recovery after Day 6 native-artifact validation. Preserve the production validation and fail-closed release gate.
- **Dependencies/evidence:** [Day 9 #735](https://github.com/rumman52/Shuddho/issues/735), [D custody #665](https://github.com/rumman52/Shuddho/issues/665), merged [native validation #766](https://github.com/rumman52/Shuddho/pull/766). The exact-main [CI run 44278207003](https://github.com/rumman52/Shuddho/actions/runs/44278207003) failed these two test nodes while 1,628 Coworker tests passed and 4 skipped. Governance and merge gate failed separately on unconfigured GitHub App client-id.
- **Base branch / SHA:** `main` / `c8aa7cf8444f1cf8c5408568e78b3cae6792f00a`.
- **Work branch:** `codex/day9-native-export-recovery-tests-20261118`; draft PR (see GitHub branch).
- **Existing interfaces reused:** `DocumentRunner.export`, `render_in_subprocess`, `validate_day6_exports`, `LocalObjectStore.inventory/get`, retention orphan cleanup, SQLite tests. No runtime interface, migration, configuration or permission changes.
- **Modified code:** `tests/test_coworker.py` and `tests/test_coworker_retention.py`; this contract and `PROGRESS.md`.
- **Compatibility:** use the existing production renderer to create the canonical four native exports; move injected lost PUT response to `report.pdf` (the second PUT), keep reverse-order cleanup and checkpoint/byte-integrity assertions; verify the original, content-addressed DOCX bytes survive SIGKILL and age-bounded orphan cleanup.
- **Failure reproduction:** the unmodified base's exact-head Coworker job failed with `export_invalid` before the faulting storage boundary, because both tests returned malformed text-only outputs; the worker-loss test timed out waiting for a PUT.
- **Negative/positive behavior:** malformed native artifacts must still fail before any PUT. Valid native artifacts must reach the injected failure boundary and preserve the pre/post-checkpoint ownership and retention invariants.
- **Focused test command:**
  ```bash
  uv run --extra coworker pytest \
    tests/test_coworker.py::test_partial_export_storage_failure_cleans_unpublished_objects_before_retry \
    tests/test_coworker_retention.py::test_hard_worker_loss_after_object_put_is_reconciled_without_deleting_checkpointed_outputs -q -rs
  ```
- **Required Day 9 source checks:**
  ```bash
  uv run --extra coworker pytest tests/test_ruke_pilot_eval.py tests/test_pilot_workflow_eval.py tests/test_release_contract.py -q -rs
  uv run --extra coworker python -m scripts.ruke_pilot_eval validate-registry
  uv run --extra coworker python -m scripts.release_contract_check
  ```
  The mandatory final-head CI checks must pass on the final candidate, including governance and merge gate.
- **Owner, security and egress boundaries:** no production changes, paid provisioning, live sends, D-held input reads, credentials or broad permissions. Human D must authenticate custody and perform 40 first-run tasks/two independent reviews; C must operate the full 20-row matrix; authorized owner/admin must configure governance inputs and verify release readbacks.
- **Budget/cancellation/revocation/rollback:** existing production logic unchanged. Only isolated test fixtures updated. No activation or feature-flag change.
- **Out of scope:** claiming any independent holdout or operated recovery acceptance, modifying Alembic or storage access policies, and bypassing native validation.

## Completion evidence

| Level | Status | Exact evidence |
| --- | --- | --- |
| Implemented | Source changes on review branch | Inspect branch diff and PR head |
| Repository-verified | Pending | Require exact final-head CI and focused run; baseline failures are not passes |
| Staging-verified | Not established | No operated C scenario receipts / matching frozen runtime |
| Production-qualified | No — Day 9 NO-GO | #665 open; 0/40 independently qualified and 0/20 operated |
| Activated | No | Owner authorization absent |

- **Test pass/fail/skip counts:** baseline Coworker 1,628 pass / 2 fail / 4 skip. Post-fix counts pending CI verification.
- **Independent review:** pending human reviewers. Source-side review confirmed native validator executes before any PUT.
- **Residual risk:** provider-backed render subprocess timing, external governance failure and staging schema drift are unqualified, independently of this test repair.
- **Next executable action:** run focused regression and required CI on the review head; obtain independent review and merge only on green exact-head checks. C/D must then produce real staging/custody evidence without retroactively treating this PR as acceptance.
