# Controlled Cohort Recovery Verification

Recovery after a completed rollback is a separate release decision. A disabled system becoming healthy does not automatically authorize traffic to return.

This verifier proves that Coworker was re-enabled **only with the previously approved rollout shape**, then exercises a real synthetic workflow before accepting the recovered state.

## Preconditions

Recovery is allowed only after:

- a passed global rollback-completion artifact;
- the same rollout manifest and canary plan used by the stopped release;
- an explicit recovery deployment/change record;
- the current cohort stage still exists in the approved canary plan.

The recovery deployment must occur after rollback completion was verified.

## Required deployed state

The verifier requires:

- `SHUDDHO_COWORKER_ENABLED=true`;
- backend cohort enforcement still enabled;
- configured cohort size inside the current canary-stage bounds;
- configured cohort size not above the rollout-manifest maximum;
- every capability flag to match the approved rollout manifest exactly.

This prevents recovery from silently enabling Research, Actions, memory, parallel execution, or another capability that was not part of the approved release.

## Live recovery probe

Provide two short-lived staging/production verification identities:

```bash
SHUDDHO_RECOVERY_API_BASE_URL=https://api.example.com
SHUDDHO_RECOVERY_TOKEN_ALLOWED=<approved cohort member token>
SHUDDHO_RECOVERY_TOKEN_DENIED=<non-member token>
```

The verifier confirms:

1. approved identity receives HTTP 200 from `/api/v1/me`;
2. denied identity receives HTTP 403 `cohort_not_enabled`;
3. the approved identity creates one synthetic `report_email` task;
4. the task completes through API → durable queue/Temporal → worker → model;
5. the task produces at least one artifact;
6. the approved identity can retrieve non-empty artifact content;
7. the smoke task completed after the recovery deployment.

No real Gmail send, Calendar creation, social publishing or other consequential action is performed.

## Post-recovery health ordering

Only after the synthetic task completes does the verifier collect a fresh health snapshot using the existing cohort-health evaluator.

Recovery fails unless that new status:

- returns `CONTINUE_COHORT`;
- contains zero breaches;
- reports the same configured cohort count;
- was generated after the smoke task completed.

This prevents an old pre-recovery health file from being reused as recovery proof.

## Run

```bash
uv run --extra coworker python scripts/cohort_recovery_verification.py \
  --rollout /secure/release/cohort-rollout.json \
  --canary-plan /secure/release/cohort-canary-plan.json \
  --rollback-completion /secure/release/rollback-completion.json \
  --thresholds /secure/release/cohort-health-thresholds.json \
  --current-stage canary-5 \
  --deployment-reference deploy-recovery-20260922-01 \
  --deployed-at 2026-09-22T08:00:00+00:00 \
  --status-output /secure/release/post-recovery-status.json \
  --microsoft-rollout-activation /secure/release/post-rollback-microsoft-rollout-activation.json \
  --action-selection-activation /secure/release/post-rollback-action-selection-activation.json \
  --release-ledger /secure/release/coworker-cohort-001.jsonl \
  --output /secure/release/recovery-verification.json
```

The evidence output is sanitized. It records:

- release/stage and deployment reference;
- configured member count;
- declared capability booleans;
- synthetic task state, artifact count and aggregate model accounting;
- admission HTTP outcomes;
- post-recovery health timestamp/decision;
- SHA-256 hashes of the rollout manifest, canary plan, rollback completion and post-recovery status.

It does not store tokens, account IDs, prompts from real users, OAuth secrets, provider response bodies, email/calendar content or artifact bytes.

## Release ledger

Schema v3 adds only `recovery_verified`.

Existing ledger history remains:

- schema v1: HOLD / expansion / STOP;
- schema v2: rollback_completed;
- schema v3: recovery_verified.

A recovery entry requires:

- an earlier `stop_rollout`;
- an earlier `rollback_completed`;
- the same release ID and current stage;
- the same rollout manifest, canary plan and original STOP progression decision;
- the exact rollback-completion artifact already recorded in the v2 entry;
- the exact post-recovery status and recovery-verification artifact.

Append:

```bash
uv run python scripts/cohort_release_ledger.py append-recovery \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference incident-123 \
  --current-stage canary-5 \
  --rollout /secure/release/cohort-rollout.json \
  --canary-plan /secure/release/cohort-canary-plan.json \
  --progression-decision /secure/release/stop-progression.json \
  --operator-status /secure/release/post-recovery-status.json \
  --rollback-completion /secure/release/rollback-completion.json \
  --recovery-verification /secure/release/recovery-verification.json
```

Anchor the returned ledger head hash in the independent incident/change record.

## After recovery

Recovery returns the release only to its **existing canary stage**.

It does not:

- advance from 5 → 10 or 10 → 25 users;
- reset prior STOP history for progression calculations;
- authorize a new capability;
- bypass the normal health/observability scheduler.

Resume health collection from the recovered stage. Any later cohort expansion remains a separate reviewed decision.


## Microsoft-enabled recovery

Google-only recovery remains unchanged when `SHUDDHO_MICROSOFT_ACTIONS_ENABLED=false`.

When the recovered backend has `SHUDDHO_MICROSOFT_ACTIONS_ENABLED=true`, recovery now fails closed unless a **fresh post-rollback Microsoft rollout activation** is supplied and recorded in the same tamper-evident release ledger.

The recovery verifier requires:

- the Microsoft activation status to be `microsoft_rollout_verified`;
- the same release ID as the recovery;
- backend global actions and Microsoft actions enabled;
- Coworker frontend and Microsoft provider UI enabled;
- the Microsoft deployment to occur no earlier than the recovery deployment;
- Microsoft verification to occur after that Microsoft deployment and after rollback completion;
- the exact rollback-completion artifact to have one matching schema-v2 `rollback_completed` ledger event;
- the exact Microsoft activation artifact to have one matching schema-v6 `microsoft_rollout_verified` event for the current stage;
- the schema-v6 event sequence to be later than the exact rollback-completion ledger event.

The resulting recovery artifact records the exact Microsoft activation SHA-256 and the matching ledger sequence/head reference. The existing schema-v3 `recovery_verified` ledger event then hashes the complete recovery artifact, so Microsoft proof becomes part of the established recovery chain without introducing a new ledger schema.


## Action-selection-enabled recovery

Legacy rollout manifests that do not contain `action_selection` are normalized to `false`.

When the approved rollout and recovered backend enable action selection, recovery requires a **fresh post-rollback** `action_selection_verified` activation. The verifier requires:

- the same release ID and current stage;
- all required action-selection runtime controls enabled;
- the action-selection deployment to occur no earlier than the recovery deployment;
- action-selection verification to occur after its deployment and after rollback completion;
- the exact rollback-completion artifact to have one matching schema-v2 ledger event;
- the exact action-selection activation to have one matching schema-v7 event;
- the schema-v7 event sequence to be later than that exact rollback-completion event.

Historical action-selection-aware recovery evidence uses schema v2. New verifier output uses schema v3, preserving those schema-v7 action-selection references and adding action-proposals requirements when applicable.

When schema-v3 `recovery_verified` is appended, the ledger writer independently re-checks historical v2 and new v3 consumer requirements. A recovery artifact cannot silently remove a required Microsoft, action-selection, or action-proposals attestation after runtime verification.

## Fresh action-proposals proof after rollback

If the approved recovered runtime enables `action_proposals`, recovery requires a **fresh post-rollback** schema-v8 `action_proposals_verified` attestation.

Supply:

```bash
--action-proposals-activation /secure/release/post-rollback-action-proposals-activation.json
--release-ledger /secure/release/coworker-cohort-001.jsonl
```

The recovery verifier requires:

- the same release ID and current stage;
- action-proposals runtime prerequisites enabled under controlled-cohort enforcement;
- proposal activation deployment not older than the recovery deployment;
- proposal activation verification after its deployment and after rollback completion;
- the exact schema-v8 ledger event to occur after the exact schema-v2 `rollback_completed` event;
- exact activation SHA-256 matching.

New recovery evidence is schema v3. It records `action_proposals_enabled`, the exact proposal activation SHA-256, and the satisfying schema-v8 ledger sequence/hash.

When `append-recovery` records the recovery result, it independently verifies that same schema-v8 attestation and its post-rollback ordering. A required proposal proof cannot be stripped or swapped between recovery verification and ledger recording.

Action-proposals-disabled recovery remains compatible and requires no schema-v8 proof. Historical schema-v1/v2 recovery evidence remains valid.
