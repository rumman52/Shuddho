# A-03 Temporal History Replay Harness

Base revision: b15070dc71907b819f7d148e77ccdc0558c686cd
Work branch: test/a03-temporal-history-replay-20261025
Status: implementation in progress; no staging or production qualification implied.

## Contract

Build a fail-closed, code-owned replay runner for version-bound Temporal history manifests. Start with the stable shuddho_work_services_v1 workflow and a frozen legacy definition copied from services/coworker/workflow.py at source revision b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d. The test-generated histories are synthetic compatibility fixtures, not exports from production Temporal.

## Tasks

1. Add the test and mandatory CI invocation before the runner. The test-only run was canceled by subsequent branch updates before it reached the new step, so no missing-module red is claimed. The first executed focused run exposed a fixture error: Temporal Worker rejected the legacy activity stubs because they lacked @activity.defn. Explicit decorators were added; rerun focused and full CI.
2. Implement scripts/temporal_history_replay.py with a fixed workflow registry, strict manifest validation, relative-path containment, a bounded history size, SHA-256 verification, Temporal WorkflowHistory parsing and Replayer execution. Never print raw history or exception messages.
3. Test success and handled-activity-failure history, unknown workflow type, path traversal, and checksum mismatch. The test fixture must use a fixed legacy workflow definition and current production workflow for replay.
4. Run the mandatory replay test in the coworker CI job and preserve JUnit evidence. The mandatory test gate must reject missing collection, skips, and failures.
5. Review the final branch diff and exact-head CI. The focused replay step passed at source head f4840b2c1b3293facc2d560b5459458f4e2ce645 in run 40176606296; that run's full coworker job was still in progress at the last observation. Update PROGRESS.md with this exact evidence and retain the remaining external A-03 gates.

## Acceptance

- Both generated legacy history paths replay against the current WorkServicesWorkflow.
- Manifest schema/version, workflow type, workflow ID, source revision, relative path and SHA-256 are validated before replay.
- A history cannot reference a path outside its manifest directory.
- Failure output includes only case ID, workflow type, status and error class; no history payload or error message.
- The required CI test executes with coworker dependencies and zero skips.

## Limits

This closes only the repository-level replay harness for one workflow type. A-03 remains incomplete until real archived production histories, declared old/new binary plus retained-schema combinations, migration/rollback behavior, and operated restore evidence are independently qualified. Do not mark A-03, production qualification or activation complete.
