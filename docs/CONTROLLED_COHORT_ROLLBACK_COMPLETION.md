# Controlled Cohort Rollback Completion

A `STOP_ROLLOUT` decision is not the same thing as a completed rollback.

This increment verifies that the selected deployment kill switch was actually applied, already accepted work drained or was reconciled, and a fresh post-rollback health snapshot is clean before operations records `rollback_completed`.

## Why the worker may remain running

`SHUDDHO_COWORKER_ENABLED=false` removes the Coworker API boundary, preventing new submissions through the product. The worker process does not use that flag as its loop condition; it may remain online to finish or reconcile already accepted durable work.

That is intentional.

Rollback completion therefore requires durable drain evidence rather than assuming "flag off" means "nothing is running."

## Supported rollback modes

The verifier supports:

- `global` → `SHUDDHO_COWORKER_ENABLED=false`
- `agent` → `SHUDDHO_AGENT_RUNTIME_ENABLED=false`
- `parallel` → `SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false`
- `research` → `SHUDDHO_RESEARCH_SERVICES_ENABLED=false`
- `actions` → `SHUDDHO_ACTIONS_ENABLED=false`

The selected switch must exactly match the approved rollout manifest.

For a full controlled-cohort STOP, use `global`.

## Global rollback completion conditions

The global mode requires all of the following across configured cohort accounts:

- no active Coworker tasks;
- no active Agent runs;
- no active provider actions, including previews awaiting approval;
- no `outcome_unknown` consequential actions;
- no undelivered task outbox rows;
- no undelivered Agent outbox rows.

This is intentionally stricter than simply waiting for running activities to stop. Pending durable work must also be acknowledged or reconciled.

## Post-rollback health

After the deployment change and drain/reconciliation are complete, run the existing cohort observability exporter again.

The resulting operator status must:

- use the same release ID;
- be generated after the rollback deployment timestamp;
- report `CONTINUE_COHORT`;
- contain no breaches;
- contain a valid configured cohort-member count.

`CONTINUE_COHORT` here means the **remaining disabled/drained system state is operationally clean**. It is not permission to re-enable Coworker or expand the cohort.

## Run the verifier

Example global rollback:

```bash
uv run --extra coworker python scripts/cohort_rollback_completion.py \
  --rollout /secure/release/cohort-rollout.json \
  --post-status /secure/release/post-rollback-status.json \
  --mode global \
  --deployment-reference deploy-rollback-20260922-01 \
  --deployed-at 2026-09-22T07:00:00+00:00 \
  --output /secure/release/rollback-completion.json
```

The output contains only:

- release ID;
- rollback mode and exact applied switch;
- deployment/change reference;
- deployment and verification timestamps;
- aggregate drain counts;
- post-rollback health timestamp/member count;
- SHA-256 hashes of the rollout manifest and post-rollback operator status.

It contains no prompts, files, OAuth material, account IDs, email/calendar content or provider response bodies.

## Record completion in the release ledger

A rollback-completion ledger entry is schema v2. Existing HOLD/EXPAND/STOP entries remain schema v1 and continue to verify unchanged.

The ledger requires:

- an earlier `stop_rollout` entry;
- the same release ID;
- the same current stage;
- the exact same rollout manifest, canary plan and STOP progression decision as that STOP event;
- a healthy post-rollback operator status;
- the exact rollback-completion evidence file.

Append:

```bash
uv run python scripts/cohort_release_ledger.py append-rollback \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference incident-123 \
  --current-stage canary-5 \
  --rollout /secure/release/cohort-rollout.json \
  --canary-plan /secure/release/cohort-canary-plan.json \
  --progression-decision /secure/release/stop-progression.json \
  --operator-status /secure/release/post-rollback-status.json \
  --rollback-completion /secure/release/rollback-completion.json
```

Anchor the returned ledger head hash in the independent incident/change record.

## Consequential-action uncertainty

Any `outcome_unknown` action blocks rollback completion.

Calendar uncertainty can use Shuddho's existing read-only reconciliation path.

Gmail send-only scope cannot reliably reconcile a lost provider receipt. Operations must resolve that uncertainty according to the approved incident procedure before declaring the rollback complete; do not simply retry the send.

## What completion does not mean

`rollback_completed` does not authorize recovery or re-enable traffic.

A later recovery/re-enable increment should require its own reviewed evidence and ledger event. Until then, keep the selected kill switch in the rolled-back state.
