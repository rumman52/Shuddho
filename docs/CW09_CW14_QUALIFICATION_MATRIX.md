# CW-09 → CW-14 Qualification Matrix

## Purpose

Track implementation qualification boundaries for the next Shuddho engineering cycle.

## CW-09 Agent Runtime

- Verify versioned workflow identities remain isolated.
- Verify bounded execution limits.
- Verify server-owned scheduling decisions.

## CW-10 Reliability

- Verify retry behavior is bounded.
- Verify Temporal recovery and replay safety.
- Verify idempotent task execution.

## CW-11 AI Evaluation

- Maintain deterministic offline evaluation fixtures.
- Keep model/provider evaluation separate from CI release approval.
- Prevent sensitive user data in evaluation artifacts.

## CW-12 Security

- Verify owner isolation.
- Verify authorization boundaries.
- Verify secrets and credentials never enter evidence artifacts.

## CW-13 Platform Operations

- Verify observability evidence.
- Verify staging probes.
- Verify rollback procedures.

## CW-14 Release Qualification

- Require evidence before capability enablement.
- Keep high-authority features disabled until approved.
- Preserve auditability of rollout decisions.
