# Action Recipient Activation Runbook

This runbook governs production enablement of `SHUDDHO_ACTION_RECIPIENTS_ENABLED`.

## Preconditions

- PR containing migration 0014 and recipient release gates is deployed to staging.
- Existing Coworker controlled-cohort gates are green.
- Two dedicated staging identities contain no customer data.
- `SHUDDHO_ACTIONS_ENABLED=true` and `SHUDDHO_ACTION_RECIPIENTS_ENABLED=true` only in the intended staging/controlled production scope.
- The reviewed rollout declares `action_recipients=true`.
- The exact rollback switch is `SHUDDHO_ACTION_RECIPIENTS_ENABLED=false`.

## Evidence chain

The release is eligible only when all links refer to the same reviewed release and exact artifacts:

`live staging -> reviewed rollout -> deployment change -> fresh operator status -> deployed runtime manifest -> action_recipients_verified activation -> schema-v11 release-ledger event`.

The activation fails closed on stale staging evidence, stale/failed health, source-revision drift, capability drift, cohort-ceiling drift, a missing kill switch, or altered input hashes.

## Rollback

Set `SHUDDHO_ACTION_RECIPIENTS_ENABLED=false`. Existing recipient rows remain listable and deletable so personal data is not trapped behind the feature flag; create/update and UI selection are disabled. The underlying action execution boundary is unchanged.

After a global Coworker rollback, do not restore recipient creation/selection from the old activation artifact. Run a fresh live recipient activation after the recovery deployment and append a new schema-v11 attestation. Recovery and future cohort expansion require that fresh exact artifact.

## Exit criteria

Production recipient shortcuts are qualified only when:

- controlled live CRUD/isolation/cleanup evidence passed;
- production runtime reports the reviewed source revision and exact capability set;
- cohort enforcement is active within the reviewed ceiling;
- operator health is fresh and clean;
- the activation artifact hashes every reviewed input;
- the release ledger verifies and contains exactly the intended `action_recipients_verified` artifact;
- scale/recovery tools reject missing, stale, or un-attested recipient activation.
