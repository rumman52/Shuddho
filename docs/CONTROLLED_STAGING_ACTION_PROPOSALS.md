# Controlled Live Agent Action-Proposal Staging

This gate verifies the deployed non-executable Agent action-proposal boundary using the real intelligent planner and the public staging API.

It is intentionally non-destructive: no action is approved and no provider mutation is allowed.

## What must be true

The deployed staging environment must have:

- `SHUDDHO_WORK_SERVICES_ENABLED=true`
- `SHUDDHO_ACTIONS_ENABLED=true`
- `SHUDDHO_AGENT_RUNTIME_ENABLED=true`
- `SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED=true`
- `SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=true`
- a short-lived staging token for an admitted test account
- exactly one active staging email connection for the selected provider

For Microsoft, `SHUDDHO_MICROSOFT_ACTIONS_ENABLED=true` is also required.

The operator must explicitly opt in:

```bash
export SHUDDHO_STAGING_ALLOW_LIVE_ACTION_PROPOSALS=true
```

## Run

Google:

```bash
uv run --extra coworker python scripts/staging_live_action_proposals.py \
  --provider google \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.with-action-proposals.json
```

Microsoft:

```bash
uv run --extra coworker python scripts/staging_live_action_proposals.py \
  --provider microsoft \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.with-action-proposals.json
```

Required operator secrets/environment include:

- `SHUDDHO_STAGING_API_BASE_URL`
- `SHUDDHO_STAGING_TOKEN_A`
- the normal backend configuration required by `Settings.from_env()`

The staging API base must be a clean HTTPS origin.

## Proof sequence

The verifier creates a unique marker and asks the live intelligent planner to create one email draft plus exactly one inert email action proposal.

It then proves all of these conditions:

1. no existing external action contains the unique marker;
2. the run used the intelligent planner;
3. the run contains exactly one `action_proposals` item;
4. the proposal is `email_send`, state `suggested`, and has no `promoted_action_id`;
5. recipient/subject/body match the explicitly requested bounded staging scope;
6. the stored proposal hash exactly binds run ID + payload + rationale;
7. the saved Agent plan contains no `action_ids`;
8. no consequential or approval-required Agent invocation exists;
9. the unique marker is still absent from `/api/v1/actions`, proving model output did not create an `ExternalAction`;
10. promotion with a wrong proposal hash is rejected with HTTP 409 and leaves the proposal unchanged;
11. exact promotion with a user-selected owned connection creates one standalone action preview;
12. the promoted preview is schema v2, immutable, provider/connection bound, and payload-identical to the proposal;
13. replaying the exact promotion returns the same action/preview;
14. after a delay, the action remains `awaiting_approval`;
15. no approval timestamp or provider receipt exists;
16. audit contains exactly one `action.prepared` and no `action.approved`, `action.execution_started`, or `action.succeeded`;
17. the proposal becomes `promoted` and points to the standalone action;
18. the saved Agent run still has no `action_ids` and no consequential invocation;
19. exactly one matching external action exists after promotion.

The verifier cancels the synthetic preview and Agent run during cleanup. It never calls the approval endpoint.

## Evidence

A passing run adds:

```json
{
  "action_proposals": {
    "status": "passed",
    "evidence": "live intelligent Agent produced one inert typed email proposal ...",
    "verified_at": "..."
  }
}
```

The final controlled-cohort gate already requires this independent record when `action_proposals=true`.

## What this does not prove

This gate does not:

- enable the production flag;
- approve an action;
- send email;
- create a calendar event;
- prove frontend proposal UX;
- authorize broader model-created executable actions;
- prove general availability.

It proves only the deployed backend trust transition:

```text
model suggestion
→ inert proposal
→ explicit user promotion
→ standalone immutable preview
→ STOP before approval
```

## Rollback

If the live proof fails, keep or restore:

```text
SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false
```

This disables new proposal generation/promotion without changing the ordinary user-prepared action path or deleting prior history.


## Production activation handoff

A passing live staging file is not itself proof that production runs the reviewed revision/configuration.

After the reviewed production deployment, run [Agent Action-Proposal Production Activation](ACTION_PROPOSALS_ACTIVATION.md). That verifier binds this exact evidence file and the exact reviewed rollout manifest to the deployment record, checks the deployed backend revision/capabilities/providers through an authenticated runtime manifest, and requires fresh clean post-deploy cohort health before emitting `action_proposals_verified`.
