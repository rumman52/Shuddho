# Agent Action Selection Rollout Activation

This gate verifies that bounded Agent action selection is actually deployed in the reviewed controlled-cohort configuration.

A passed live `action_selection` staging probe is necessary but not sufficient. Production activation must prove that the exact staging evidence was reviewed, the deployment occurred after that proof, the required runtime flags are enabled, cohort enforcement is active, and post-deploy health is clean.

## Required order

1. Complete the live action-selection staging exercise.
2. Retain the exact resulting staging evidence file.
3. Prepare a deployment record from `docs/action-selection-deployment.template.json`.
4. Set its `staging_evidence_sha256` to the SHA-256 of the exact staging evidence.
5. Deploy the reviewed production configuration.
6. Generate a fresh controlled-cohort operator status after deployment.
7. Run the activation verifier.
8. Treat action selection as production-verified only if the output status is exactly `action_selection_verified`.

## Required runtime controls

The verifier requires all of these to be enabled in the deployed runtime:

- `SHUDDHO_COWORKER_ENABLED=true`;
- `SHUDDHO_AGENT_RUNTIME_ENABLED=true`;
- `SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED=true`;
- `SHUDDHO_ACTIONS_ENABLED=true`;
- `SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=true`;
- `SHUDDHO_COWORKER_COHORT_ENFORCED=true`.

This gate does not enable any flag itself.

## Deployment record

The deployment record binds:

- the active controlled-cohort `release_id`;
- the reviewed change reference;
- the current cohort stage;
- deployment time;
- SHA-256 of the exact live action-selection staging evidence.

The deployment time must not precede the live staging verification.

## Operator health

The post-deploy operator status must:

- use the same release ID;
- be generated after deployment;
- be fresh within the configured window;
- have `decision == CONTINUE_COHORT`;
- contain zero breaches.

## Run

```bash
uv run --extra coworker python scripts/action_selection_activation.py \
  --staging-evidence /secure/release/staging-evidence.action-selection.json \
  --deployment-change /secure/release/action-selection-deployment.json \
  --operator-status /secure/release/post-action-selection-status.json \
  --max-staging-age-minutes 1440 \
  --freshness-minutes 30 \
  --output /secure/release/action-selection-activation.json
```

A successful result has:

```text
action_selection_verified
```

## Evidence contents

The activation artifact records only sanitized control-plane state:

- release ID and current stage;
- approved change reference;
- deployment and verification timestamps;
- boolean runtime controls;
- configured cohort size/limit;
- SHA-256 of the exact staging evidence;
- SHA-256 of the deployment record;
- SHA-256 of the post-deploy operator status.

It does not contain user prompts, model output, action IDs, recipients, message content, provider credentials, OAuth tokens, or connection identifiers.

## Rollback

If action selection causes unexpected planner, approval, or user-experience behavior, disable:

```text
SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=false
```

If the broader Agent runtime must stop:

```text
SHUDDHO_AGENT_RUNTIME_ENABLED=false
```

If all consequential actions must stop:

```text
SHUDDHO_ACTIONS_ENABLED=false
```

Do not delete action history, approvals, audit events, or release evidence as part of routine rollback.

## Architecture boundary

This verifier proves **deployment consistency and release health**.

The preceding live staging gate proves the runtime behavior:

```text
opaque planner candidate
→ server-side action resolution
→ unselected draft release
→ selected draft pauses at approval
→ no provider execution
```

The activation gate then proves:

```text
exact staging proof
→ reviewed deployment
→ deployed runtime flags
→ fresh post-deploy health
→ action_selection_verified
```

After activation verification passes, record the exact artifact in the tamper-evident controlled-cohort release ledger:

```bash
uv run python scripts/cohort_release_ledger.py append-action-selection \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference change-action-selection-001 \
  --current-stage cohort-25 \
  --staging-evidence /secure/release/staging-evidence.action-selection.json \
  --deployment-change /secure/release/action-selection-deployment.json \
  --operator-status /secure/release/post-action-selection-status.json \
  --action-selection-activation /secure/release/action-selection-activation.json
```

This creates schema-v7 `action_selection_verified` evidence inside the existing release chain. Verify the ledger afterward and externally anchor the returned head hash.

The ledger event is evidence-only. It does not enable action selection or authorize an external action.
