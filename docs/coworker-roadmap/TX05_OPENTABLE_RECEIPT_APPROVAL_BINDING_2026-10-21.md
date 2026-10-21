# TX-05: OpenTable receipt must match approved reservation

## Root cause
`TransactionRepository._append_execution_evidence` checked that a successful
OpenTable receipt had plausible types, a confirmation number, and no payment,
but did not compare confirmed restaurant, local time, party size, or seating
fields against the immutable approved `ExternalAction.preview.payload`.
A corrupted success receipt could therefore be projected as a confirmed
transaction with details the user did not authorize.

## Fix
A pure OpenTable adapter helper compares confirmed restaurant ID/name, party
size, time zone, reservation attribute, dining area, environment, and exact
local minute against the approved payload. OpenTable returns local times
without offsets, whereas approved action input requires an offset. The
helper reuses `local_provider_time`'s wall-clock normalization.

Reconciliation rejects mismatches as `transaction_receipt_invalid` before
it appends provider evidence or projects `confirmed`. Existing receipt
status, no-payment, confirmation-number, and timestamp validation remain.

## Test evidence
- Locally verified isolated helper red/green using an equivalent minimal
  local module: missing matcher failed; implemented matcher yielded
  **13 passed**. This was not the repository suite.
- Added 13 pure helper test cases to mandatory test discovery (1 positive,
  8 mismatched fields, 4 malformed inputs).
- Added 8 database-backed regression cases using the simulated OpenTable
  execution: mutate persisted success receipts after a single provider POST;
  each must fail reconciliation with unchanged transaction state, zero evidence,
  and no retry. These tests need GitHub CI with the Temporal fixture.

## Qualification
No new provider requests, no live booking, no changes to approvals, leases,
transaction enablement, migrations, deployment, or production flags.
Exact-head CI and an independent human approval are mandatory for merger.
V-01 enforced native branch rules and controlled provider/staging
qualification remain separately incomplete. This is integrity validation,
not a signature/authenticity check of OpenTable responses.
