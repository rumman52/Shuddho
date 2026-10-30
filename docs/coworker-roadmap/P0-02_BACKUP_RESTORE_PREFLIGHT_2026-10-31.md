# P0-02 source subtask — backup/restore local preflight

- Objective and user-visible behavior: The controlled staging backup/restore `prepare` command must validate its rollout manifest and private local state-file destination before making staging API, PostgreSQL, or object-storage changes. Invalid local inputs must fail without creating a synthetic upload, object, or task.
- Dependency tasks and current evidence: P0-02 owner decision and a real backup/restore remain external. Current Render metadata still reports the Free PostgreSQL 18 source as available with expiry at 2026-10-31T17:11:33.79468Z; the source inventory and a restorable backup are not verified.
- Base branch/SHA: `main` / `31fdc80f364a795002371721c2a132cbfb8b687b`.
- Work branch/PR: `fix/p0-02-backup-restore-preflight-20261031` / [draft PR #600](https://github.com/rumman52/Shuddho/pull/600).
- Existing interfaces to reuse: `prepared_release_context(settings, rollout_path)`, `write_private_json(path, value)`, `resolve_owner()`, `Container.create(settings)`, and the existing explicit `SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE` guard.
- Exact files to create/modify: `scripts/staging_backup_restore.py`; `tests/test_staging_backup_restore.py`; this task contract; update `docs/coworker-roadmap/PROGRESS.md` after exact-head verification.
- New interface signatures / schema and compatibility: Add private helper `_preflight_private_json_destination(path: Path) -> None`. It rejects an existing file or symlink, requires an existing parent directory, and verifies the same private atomic JSON writer by creating and removing a unique same-directory probe. No public CLI/schema or migration change.
- Acceptance scenarios and assertions:
  1. Existing state file: reject before owner lookup, container creation, upload, storage write, or task creation.
  2. Missing/invalid rollout manifest: reject before any staging call.
  3. Missing state parent: reject before any staging call.
  4. Existing or dangling symlink state path: reject before any staging call and preserve its target.
  5. Valid path: preflight writer runs before the first staging call; final state is JSON, mode 0600 on POSIX, and probe file is removed.
  6. Test fixture IDs satisfy the production `TaskCreate.document_ids` UUID contract.
- Reproduction / initial failure: On test-only commit `db5d654afc2dd52b42d84909fb6982f4b3ce8112`, exact PR-head coworker run [#41125745464](https://github.com/rumman52/Shuddho/actions/runs/41125745464) ran the focused module with valid UUID fixtures: **5 failed, 4 passed**. Failures showed all nine staging calls occurring before invalid local inputs were rejected, and the success path wrote the final state only after remote work.
- Expected failure outcomes: Invalid local manifest/destination must raise `StagingReleaseEvidenceError`; no owner lookup or remote staging operation may occur. Valid prepare must retain the existing guarded synthetic upload/task flow and private manifest format.
- Tests and required CI commands:
  ```bash
  uv run --extra coworker pytest tests/test_staging_backup_restore.py -q -rs
  uv run --extra coworker python -m scripts.mandatory_test_gate <junit.xml> --required-module tests.test_staging_backup_restore
  ```
  Required PR-head checks: `test-and-build`, `coworker`, `ci-merge-gate`; inspect `governance-audit` separately.
- Secrets / owner / grant / approval / egress boundaries: Unit tests use synthetic fixtures only. No staging credentials or secrets are added. No network allowlist, database, storage, or provider action is performed by CI tests.
- Budget / timeout / cancellation / revocation behavior: No change to budgets, cancellation, Temporal, provider, or transaction logic.
- Default-off gate and rollback: Preserve `SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE`; do not enable or invoke the live exercise as part of this source patch.
- External prerequisites: Actual source preservation requires owner-approved export access or same-region execution, a real backup, isolated restore, and verified evidence. This PR does not supply that operational evidence.
- Out of scope: Render upgrade, network allowlist changes, database export/restore, persistent worker provisioning, GitHub ruleset administration, production deployment/activation, PostHog telemetry, and provider mutations.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Pending | PR #600; final implementation SHA pending |
| Repository-verified | Pending | Exact-head coworker and test-and-build checks pending |
| Staging-verified | Pending / not yet possible | No live backup/restore run |
| Production-qualified | Pending / not applicable to this source subtask | No production approval |
| Activated | No | No runtime flags or production state changed |

- Test pass/fail/skip counts: Red reproduction: 5 failed / 4 passed on test-only commit; green count pending.
- Exact-head CI links: [PR #600](https://github.com/rumman52/Shuddho/pull/600); [red run #41125745464](https://github.com/rumman52/Shuddho/actions/runs/41125745464); implementation run pending.
- Review findings and resolution: Independent review not yet received. Self-review must inspect no-overwrite semantics, symlink handling, probe cleanup and unchanged staging guard.
- Residual risks: A filesystem race or disk failure after successful preflight can still make the final state publish fail after synthetic staging records have been created. The final writer still refuses overwrite. This narrow race is not claimed eliminated by a preflight probe.
- Next exact action: Verify implementation CI on the exact PR head, fix any failure, request independent human review, and keep PR unmerged until review and required checks pass.
