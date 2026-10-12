# CW-01 to CW-08 Qualification Execution Tracker

## Scope
This document tracks repository-side completion work for CW-01 through CW-08.

## Completed repository checks
- Transaction safety CI workflow exists and runs mandatory transaction regression suites.
- PostgreSQL transaction boundary qualification is enforced in CI.
- Temporal/process recovery transaction qualification is enforced in CI.
- Mandatory test evidence validation is enforced through the test gate.

## Remaining evidence requirements
The following require controlled execution evidence and must not be marked complete from source inspection alone:

- CW-01: exact-head chaos evidence artifact.
- CW-02: full fault matrix execution with independent provider mutation counters.
- CW-03: concrete provider sandbox qualification.
- CW-04: signed release identity, rollback drill, and reviewer evidence.
- CW-05: current conversation ownership and migration evidence.
- CW-06: dispatch idempotency and recovery evidence.
- CW-07: UI permission/state/accessibility evidence.
- CW-08: context provenance/revocation/deletion evidence.

## Safety constraints
- No production provider mutation.
- No real booking, checkout, or spending.
- Unknown transaction outcomes require reconciliation.
- External mutations remain behind approved action boundaries.
