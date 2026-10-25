# A-03 Temporal history replay harness — task contract

- Objective and user-visible behavior: provide a repeatable, fail-closed way to replay version-bound Temporal history JSON against the current registered workflow implementation.
- Dependency tasks and current evidence: V-01 native merge protection and staging provisioning are externally blocked. The source inventory says A-03 lacks an archived-history replay corpus; current CI covers Temporal workflows but does not run Temporal Replayer over archived histories.
- Base branch/SHA: main at b15070dc71907b819f7d148e77ccdc0558c686cd.
- Work branch/PR: test/a03-temporal-history-replay-20261025; PR to be created after the red test is observed.
- Existing interfaces to reuse: temporalio.client.WorkflowHistory, temporalio.worker.Replayer, services.coworker.workflow.WorkServicesWorkflow, WorkflowEnvironment and Worker.
- Exact files to create/modify: tests/test_temporal_history_replay.py; scripts/temporal_history_replay.py; .github/workflows/ci.yml; docs/superpowers/plans/2026-10-25-a03-temporal-history-replay.md; this contract; current progress entry after exact-head verification.
- New interface signatures / schema and compatibility: replay_manifest(manifest_path) asynchronously validates schema version 1 and replays only workflow types in a fixed code-owned registry. Each history entry binds case_id, workflow_type, workflow_id, relative path and SHA-256. Manifest source_revision is a 40-character Git SHA.
- Acceptance scenarios and assertions: successful legacy workflow history; handled activity-failure history; invalid workflow type; path traversal/symlink escape; hash mismatch; malformed manifest; mandatory CI collection with no skips.
- Reproduction / initial failure: the test-only head was canceled before its new step ran, so the missing-module failure was not observed. The first executed focused run failed because Temporal Worker requires activity stubs to be decorated with @activity.defn. The test fixture was corrected; final focused and full CI must be rechecked.
- Expected failure outcomes: invalid manifests fail closed; replay mismatch exits nonzero; output omits history bodies and raw exception messages.
- Tests and required CI commands: uv run --extra coworker pytest tests/test_temporal_history_replay.py -q -rs --junitxml=/tmp/a03-temporal-history-replay.xml; scripts.mandatory_test_gate must pass for tests.test_temporal_history_replay.
- Secrets / owner / grant / approval / egress boundaries: no credentials or live providers; only synthetic IDs and a loopback Temporal test environment.
- Budget / timeout / cancellation / revocation behavior: bounded history size and Temporal test runtime; no production execution.
- Default-off gate and rollback: test harness only; no capability flag, schema migration, deployment or activation change.
- External prerequisites: real production history exports and representative old/new binary + retained-schema test environments remain external A-03 requirements.
- Out of scope: changing workflow behavior, database schema, Temporal task queue, production Render settings or native GitHub protection.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Pending | |
| Repository-verified | Pending | |
| Staging-verified | Not established | |
| Production-qualified | Not established | |
| Activated | No | |

- Test pass/fail/skip counts: A-03 focused step passed at f4840b2c1b3293facc2d560b5459458f4e2ce645 in run 40176606296 after the activity-registration fix; full required CI on the final head pending.
- Exact-head CI links: pending.
- Review findings and resolution: pending independent review.
- Residual risks: generated legacy histories are synthetic; they do not replace archived production history replay or rollback drills.
- Next exact action: finish full CI on the final head, inspect the generated synthetic history artifact, then obtain independent review. The initial test-only run was canceled before it reached the new step; do not claim a missing-module red run.
