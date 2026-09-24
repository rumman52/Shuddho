# Release Contract Propagation

This increment carries the canonical controlled-release capability contract beyond final cohort admission into production activation, release-ledger verification, and recovery configuration checks.

## Problem

Shuddho's optional action and Agent capabilities were introduced over multiple bounded releases. Historical activation and ledger code therefore accumulated local lists such as:

- approved attachments;
- reminders;
- saved recipients;
- document sharing;
- email threading;
- social publishing;
- Agent action selection/proposals;
- LinkedIn Agent proposals.

Those lists were not all updated at the same time. A safe older rollout can omit a capability that did not exist when its evidence was created, while a newer runtime manifest may correctly expose that capability as `false`. Comparing those shapes without canonical normalization can reject valid historical evidence or force each downstream verifier to know every future optional capability.

## Contract

`scripts/release_contract.py` owns optional capability shape.

`normalize_capabilities()`:

1. copies the supplied capability object;
2. preserves every explicit value;
3. adds every currently registered optional capability that is absent;
4. defaults only those absent optional capabilities to `false`;
5. never mutates the caller's object;
6. does not default required/base capability keys.

Production activation verifiers, release-ledger attestation verification, and recovery configuration validation consume that helper instead of maintaining local optional-capability lists.

## Backward compatibility

Missing optional capability means disabled.

For example, a schema-v8 action-proposal rollout created before Gmail threading or LinkedIn publishing existed may omit those keys. A current runtime manifest may report:

```json
{
  "action_email_threading": false,
  "action_social_publishing": false
}
```

The release ledger normalizes both capability objects before exact comparison, so the safe false values do not invalidate the historical attestation.

Explicit drift still fails closed. If either side reports a capability as `true` while the other reports or normalizes it to `false`, exact runtime comparison still rejects the evidence.

## Deliberately unchanged

This increment does not derive historical release schema versions from the current capability registry.

Schema versions in scale/recovery and release-ledger events encode the evidence format that existed when each release was produced. Those version ladders stay explicit so old evidence remains verifiable and adding a future capability cannot silently reinterpret historical records.

The change also does not:

- enable a feature flag;
- widen Agent authority;
- approve or execute an external action;
- modify provider receipts;
- rewrite the release ledger;
- expand a production cohort.

## Verification

CI covers:

- canonical normalization of all registered optional capabilities;
- non-mutation of input capability objects;
- legacy recovery manifests defaulting newer optional capabilities off;
- schema-v8 action-proposal ledger verification when a newer runtime explicitly reports later capabilities as `false`;
- the existing activation, ledger, scale, recovery, and browser suites.
