# TX-05: Bound provider receipt timestamps to execution

## Investigated gap
The success-receipt validation required an offset-aware `confirmed_at` but accepted events dated before execution started or after it finished. An impossible acceptance time could still project a confirmed transaction.

## Patch
Reconciliation requires server-written `started_at` and `finished_at`. Only receipts within `[started_at - 5 minutes, finished_at + 5 minutes]` are eligible to confirm. This is a chronology/plausibility check, not a cryptographic provider attestation.

Two new parameterized integration cases send success receipts with timestamps one day before execution and one day after execution. They assert `transaction_receipt_invalid`, non-confirmed state, and zero reconciliation evidence.

## Verification gates
The Temporal/SQLAlchemy integration suite has not been executed locally in this session; use exact-head GitHub Actions. Do not merge the draft until all required CI is green and independent human approval is submitted. V-01 native main ruleset protection remains unconfigured. No provider execution, migrations, flags, release, or production deployment are modified.
