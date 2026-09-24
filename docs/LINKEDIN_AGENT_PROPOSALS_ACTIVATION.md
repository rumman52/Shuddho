# LinkedIn Agent Proposal Production Activation

This runbook release-qualifies `SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=true` for a reviewed controlled cohort. The flag remains false by default.

## Required dependency state

The reviewed rollout must enable all of:

```text
SHUDDHO_ACTIONS_ENABLED=true
SHUDDHO_AGENT_RUNTIME_ENABLED=true
SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED=true
SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=true
SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=true
SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=true
```

The rollout must declare the LinkedIn provider and the exact emergency rollback switch:

```text
SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=false
```

Current-stage release history must already contain:

- schema-v8 `action_proposals_verified`;
- schema-v14 `action_social_publishing_verified`.

## 1. Controlled live staging

Use a dedicated authorized staging LinkedIn personal member and an intelligent-planner deployment. No post is approved or published by this probe.

```bash
SHUDDHO_STAGING_ALLOW_LIVE_LINKEDIN_AGENT_PROPOSALS=true \
uv run --extra coworker python scripts/staging_live_linkedin_agent_proposals.py \
  --base-evidence /secure/release/staging-evidence.json \
  --output /secure/release/staging-evidence.linkedin-agent-proposals.json
```

The probe must prove:

1. one exact `social_publish_linkedin` proposal is created by the intelligent planner;
2. no matching `ExternalAction` exists before promotion;
3. no provider/account/member is model-selected;
4. wrong-hash promotion returns 409 and leaves the proposal suggested;
5. the operator-selected owned LinkedIn social connection is required;
6. exact promotion creates one immutable version-5 LinkedIn preview in `awaiting_approval`;
7. the approval scope binds the personal member, exact text, public visibility and the existing no-media/no-scheduling/no-social-read policy;
8. the saved Agent plan gains no consequential LinkedIn tool step;
9. no approval, execution audit, provider receipt or LinkedIn mutation occurs.

The final cohort gate requires this evidence under the exact key:

```text
agent_linkedin_proposals
```

## 2. Reviewed production deployment

Deploy the exact reviewed source revision with controlled-cohort admission enforced. Record a deployment JSON that binds:

- release ID;
- change reference;
- current stage;
- full lowercase 40-character source SHA;
- deployment timestamp;
- SHA-256 of the exact live staging evidence;
- SHA-256 of the exact reviewed rollout manifest.

Generate fresh clean operator health after deployment.

## 3. Production activation verification

Set an authenticated read-only verification token and run:

```bash
SHUDDHO_PRODUCTION_VERIFICATION_TOKEN=... \
uv run --extra coworker python scripts/linkedin_agent_proposals_activation.py \
  --staging-evidence /secure/release/staging-evidence.linkedin-agent-proposals.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/linkedin-agent-proposals-deployment.json \
  --operator-status /secure/release/operator-status.json \
  --api-base-url https://api.example.com \
  --output /secure/release/linkedin-agent-proposals-activation.json
```

A passing artifact has:

```text
status = agent_linkedin_proposals_verified
```

The verifier requires exact equality between reviewed and deployed source revision, environment, normalized capability map, provider set and cohort ceiling.

## 4. Record schema-v15 release attestation

After activation passes:

```bash
uv run python scripts/cohort_release_ledger.py append-agent-linkedin-proposals \
  --ledger /secure/release/coworker-cohort.jsonl \
  --release-id <release-id> \
  --actor-reference <operator-reference> \
  --change-reference <change-reference> \
  --current-stage <stage> \
  --staging-evidence /secure/release/staging-evidence.linkedin-agent-proposals.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/linkedin-agent-proposals-deployment.json \
  --operator-status /secure/release/operator-status.json \
  --agent-linkedin-proposals-activation /secure/release/linkedin-agent-proposals-activation.json
```

Schema v15 rejects duplicate activation recording and refuses to append unless the current stage already contains the required schema-v8 and schema-v14 prerequisite attestations.

## 5. Scale and recovery

When `SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=true`:

- bounded scale emits schema-v10 evidence and requires the exact schema-v15 activation/ledger pair;
- post-global-rollback recovery emits schema-v10 evidence and requires a fresh post-rollback schema-v15 activation/ledger pair;
- release-ledger verification independently consumes schema-v9 social-publishing evidence and schema-v10 LinkedIn Agent-proposal evidence.

Missing, stale, reordered, mismatched or tampered evidence is a hard failure.

## Emergency rollback

Set on API and workers:

```text
SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=false
```

This immediately blocks new LinkedIn Agent proposal persistence and promotion. It does not change ordinary email/calendar proposals or the independently controlled LinkedIn publishing capability.
