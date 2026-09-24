# LinkedIn Social Publishing Production Activation

This runbook governs controlled production activation of personal LinkedIn text publishing.

## Invariants

The action remains intentionally narrow:

- one authenticated personal LinkedIn member;
- one exact UTF-8 text post;
- public visibility only;
- immediate execution only after explicit immutable-preview approval;
- no media or organization pages;
- no social-read, comments, reactions, scheduling, edit/delete, or Agent authority.

Production activation must never widen those boundaries.

## Preconditions

- The implementation and this release-qualification change are merged.
- CI is green.
- The rollout is a bounded production cohort.
- `actions=true` and `action_social_publishing=true`.
- `action_providers` includes `linkedin`.
- Exact kill switch: `SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=false`.
- A dedicated staging LinkedIn member is connected.
- Staging uses only synthetic, non-customer post text.
- Operator health is `CONTINUE_COHORT` with zero breaches.

## Live staging

Run the live validator only in controlled staging:

```bash
SHUDDHO_STAGING_ALLOW_LIVE_SOCIAL_PUBLISHING=true \
uv run --extra coworker python scripts/staging_live_social_publishing.py \
  --base-evidence /secure/release/staging-evidence.json \
  --output /secure/release/staging-evidence.social-publishing.json
```

The script requires the configured staging API/token environment and proves exact member/text/policy binding, no automatic execution, wrong-hash rejection, explicit approval, a single execution audit chain, and a confirmed provider post receipt.

## Activation

After the reviewed production deployment and a fresh clean operator snapshot:

```bash
uv run --extra coworker python scripts/action_social_publishing_activation.py \
  --staging-evidence /secure/release/staging-evidence.social-publishing.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/social-publishing-deployment.json \
  --operator-status /secure/release/post-social-publishing-status.json \
  --api-base-url https://api.example.com \
  --output /secure/release/social-publishing-activation.json
```

The production verification token is supplied only through the operations environment.

## Release ledger

Append the exact activation to the tamper-evident release chain:

```bash
uv run --extra coworker python scripts/cohort_release_ledger.py append-action-social-publishing \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference change-social-publishing-001 \
  --current-stage cohort-25 \
  --staging-evidence /secure/release/staging-evidence.social-publishing.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/social-publishing-deployment.json \
  --operator-status /secure/release/post-social-publishing-status.json \
  --action-social-publishing-activation /secure/release/social-publishing-activation.json
```

This creates schema-v14 `action_social_publishing_verified` evidence. Verify the chain and externally anchor the returned head hash.

## Expansion

When social publishing is enabled, `cohort_scale_activation.py` requires:

```text
--action-social-publishing-activation /secure/release/social-publishing-activation.json
```

The activation hash must match exactly one schema-v14 event at the current stage. Scale evidence is schema v9 while this capability is enabled.

## Recovery

After a global Coworker rollback, do not reuse the previous social activation. Deploy the reviewed state, run fresh live/activation verification after rollback completion, append a new schema-v14 social event after the rollback event, and provide the fresh activation to `cohort_recovery_verification.py`. Recovery evidence is schema v9 while social publishing is enabled.

## Rollback

Set:

```text
SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=false
```

New social publishing is blocked by the feature boundary. A provider request already issued cannot be recalled. Preserve action history and uncertain outcomes; never retry an uncertain LinkedIn mutation merely because the feature was toggled.

## Exit criteria

Social publishing is eligible for controlled activation only when:

- guarded live LinkedIn evidence passed;
- wrong-hash and no-auto-publish proofs passed;
- exact deployed revision/runtime/provider/cohort controls were verified;
- operator status is fresh and clean;
- activation hashes bind all reviewed inputs;
- schema-v14 ledger verification passes;
- scale and recovery checks fail closed if the social attestation is missing, stale, reordered, duplicated, or tampered.
