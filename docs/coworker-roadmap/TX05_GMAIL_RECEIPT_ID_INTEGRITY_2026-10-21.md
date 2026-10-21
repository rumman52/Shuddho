# TX-05: Gmail provider receipt identity validation (2026-10-21)

## Observed gap
The Gmail send adapter rejects provider message IDs that are missing or outside the pattern `[a-zA-Z0-9_-]{1,200}`, but transaction reconciliation previously accepted a `succeeded` action receipt if it only contained `provider=google`, `status=accepted_by_gmail`, and an aware `confirmed_at`. A forged, truncated, or corrupted durable receipt could therefore project a confirmed transaction without even a syntactically valid Gmail-assigned identity.

## Changes
- Apply the existing Gmail adapter's provider message ID contract again at the durable TX-05 reconciliation boundary, for `negotiation_commitment_email` with `google` only.
- Reject missing, empty, whitespace-only, non-string, invalid-character, and overlength IDs before evidence is appended or a transaction is confirmed.
- Add parameterized DB-backed regressions that assert deterministic `transaction_receipt_invalid`, no reconciliation evidence, and unchanged non-terminal transaction state.
- Preserve the Microsoft Graph send receipt contract (Graph send can succeed with empty response), and preserve all existing ExternalAction authority, lease, owner scope, approval, retry, and idempotency policies.

## Verification and qualification
- No local Shuddho DB/Temporal integration run was executed in this isolated environment; `temporalio` is not installed.
- GitHub exact-head CI must run the targeted regression as part of the full suite, including `test-and-build`, `coworker`, and `ci-merge-gate`.
- Independent review is required prior to merge. No provider execution, release flag changes, or production deployment in this change.
- This is receipt **format/integrity** validation, not cryptographic or live provider attestation, and does not qualify real-money transaction execution.
