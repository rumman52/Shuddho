# CW-02: per-scenario mutation/outcome contract

- Date: 18 October 2026 (Asia/Dhaka)
- Base branch/SHA: `main` / `ab3ae23b5b84cea8613a93d340a3e0f2c05753f0`
- Work branch: `codex/cw02-scenario-outcome-contract-20261018`
- Objective: reject a transaction-chaos evidence manifest when provider-dispatch/applied-mutation counters or the reported outcome contradict the named fault scenario.
- User-visible effect: no UI/API change. Release reviewers receive a stricter fail-closed evidence contract rather than accepting internally inconsistent evidence.
- Production behavior: unchanged. No provider, schema, workflow, feature flag, external authority, deployment, or activation changes.

## Observed gap

The existing `scripts/transaction_chaos_matrix.py` required all 16 scenario IDs, bound each manifest to source revision/rollout, checked provider-observation references, and rejected invalid generic counters. It did not fully bind each scenario to its expected dispatch count and outcome. Consequently, a well-formed manifest could still describe a model failure that dispatched a transaction, an API crash that applied a provider mutation, or a lost provider response reported as confirmed.

## Implementation

- Added `SCENARIO_CONTRACTS` for every canonical scenario ID.
- Each contract enumerates allowed `attempted_mutations:applied_mutations` pairs and outcome values for each pair.
- Derive the zero-dispatch and zero-mutation scenario sets from the contracts, avoiding a second manually maintained source of truth.
- Reject any count pair or outcome not explicitly permitted by the scenario contract.
- Add tests that the contract covers every scenario, each allowed pair has an outcome set, and contradictory counts/outcomes are rejected.
- Update the Phase 11 runbook, roadmap, canonical progress, and architecture/core acceptance inventory.

## Contract summary

| Scenario | Allowed counter pairs | Required outcome rule |
| --- | --- | --- |
| Model 429/500/timeout | 0 dispatch / 0 applied | `failed` or `blocked`; no transaction provider dispatch |
| Provider 401/403/429 | 1 dispatch / 0 applied | `failed` or `rejected` |
| Provider 500; malformed response | 1/0 or 1/1 | 1/0 must be `failed`; 1/1 must remain `uncertain` |
| Database disconnect | 0/0, 1/0, or 1/1 | Outcome must match the allowed recovery state for those counters |
| S3 disconnect | 0/0, 1/0, or 1/1 | Artifact failure cannot be represented as a successful `confirmed` task result |
| Temporal outage | 1/1 | `recovered` or `confirmed` |
| Worker crash | 0/0 or 1/1 | 0/0 remains `uncertain`/`blocked`; 1/1 is `uncertain`, `recovered`, or `confirmed` |
| API crash | 0/0 | `recovered`; committed request replay cannot imply a provider mutation |
| Duplicate message/admission | 0/0 | `recovered`; same key resolves to the same identity and changed input conflicts |
| Lost provider response | 1/1 | `uncertain`; no invented confirmation |
| Approval after expiration | 0/0 | `rejected` or `blocked` |

This is a manifest consistency contract, not an assertion that every listed fault has already been operated. Boundary-specific execution evidence remains required.

## Acceptance and verification

- All 16 canonical IDs have a contract.
- Every allowed counter pair has a nonempty outcome set.
- Counts remain nonnegative integers, applied mutations never exceed attempts, and at most one applied mutation is allowed for an approved identity.
- Model failures and expired approval cannot dispatch an external mutation.
- Provider rejection does not claim an applied mutation.
- Ambiguous provider outcomes cannot be reported as confirmed without a separate exact reconciliation path.
- API replay and duplicate admission cannot claim provider mutation.
- The synthetic fixture remains explicitly a structure-only test; it is not staging proof.
- CI must pass the mandatory `transaction-safety` JUnit gate and the full exact-head `test-and-build`, `coworker`, and `ci-merge-gate` jobs with zero required skips.

## Evidence state

| Level | Status |
| --- | --- |
| Implemented | Yes — branch contains validator, tests, and docs |
| Repository-verified | Pending exact-head CI |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No |

Base evidence: PR #457 exact-head CI [#39099648984](https://github.com/rumman52/Shuddho/actions/runs/39099648984) and merged-main CI [#39101295869](https://github.com/rumman52/Shuddho/actions/runs/39101295869) passed all three required jobs before this branch. Those runs do not verify this new change.

## External blockers and next action

The complete CW-02 fault matrix still requires executable database/S3 fault injection, all specified process/Temporal boundaries, independent provider-side mutation counters, and authorized frozen staging evidence. The manifest validator does not run those scenarios or certify the live provider. Next: pass exact-head CI for this contract, inspect the JUnit evidence, then implement the next missing executable fault boundary without weakening safety assertions.
