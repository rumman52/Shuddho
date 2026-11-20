# Day 2 private PDF content-fidelity check

This is an additional **source-level acceptance safeguard**, not evidence that hosted
staging was operated. It supplements the [Day 2 execution contract](../scripts/staging_day2_execution.py)
and the [Day 2 acceptance gate](../scripts/staging_day2_acceptance.py).

## Prepare a synthetic source PDF

Create an **unencrypted, text-based synthetic PDF**, not a customer document, with
a unique uppercase ASCII marker embedded in one of its factual sentences. For example:

> The synthetic sample budget is forty-two units. SYNTHETIC_BUDGET_42_UNITS.

Use the exact marker **SYNTHETIC_BUDGET_42_UNITS** for the example, or another
`SYNTHETIC_`-prefixed uppercase identifier containing 8–56 additional letters,
digits or underscores. Keep it contiguous and extractable from the source PDF
(one PDF line is safest). The marker encodes a synthetic fact, not a password,
API token, email address or personal information. Ensure the PDF and operator
evidence directory are owner-only (mode `0600` files / `0700` directory).

## Live operator invocation

In the approved protected staging operator environment, after the frozen
release, real owner identities and owner-B synthetic artifact are verified,
use the normal Day 2 entry point:

```bash
uv run --locked --extra coworker python scripts/staging_day2_execution.py \
  --freeze-evidence /private/staging/day2/freeze.json \
  --source-pdf /private/staging/day2/synthetic-source.pdf \
  --owner-b-artifact-id "$APPROVED_OWNER_B_SYNTHETIC_ARTIFACT_UUID" \
  --expected-source-anchor SYNTHETIC_BUDGET_42_UNITS \
  --output /private/staging/day2/execution.json
```

The operator must supply the existing protected environment variables and
release authority separately. The command is guarded; do not bypass the guards
or provision a worker just to run it. No synthetic account or provider model
call is authorized by this documentation.

The runner checks the selected source PDF **before API writes**, asks the real
`report_email` task to preserve that exact marker in the English summary and
`report.pdf`, then validates:

- the summary text returned by the owned task contains the exact marker;
- the downloaded `report.pdf` bytes agree with private API metadata and its
  signed object-store download SHA-256 and length;
- the PDF is genuinely readable, unencrypted, 1–40 pages, with extractable text,
  and its page text contains the same marker.

Failure blocks the Day 2 receipt. The marker itself, source text, tokens and
signed download URLs are **not** included in the operator receipt. The
`content_anchor_verification: passed` field is accepted by the Day 2 evidence
reconciler; legacy receipts with no anchor proof or `unverified` are rejected.
For compatibility, the programmatic `run_probe` call without an anchor produces
an **unverified**, never acceptance-eligible receipt.

**Limitations:** Exact marker inclusion is an objective content-binding check.
It does not establish that the rest of the report is factually correct, written
in natural English, safe for distribution, or was genuinely produced by the
configured provider; an independent reviewer must inspect the private source,
the model/provider history, and the downloaded PDF. Neither synthetic API tests
nor the receipt reconciler substitute for hosted proof, owner isolation, live
Temporal worker interruption, or a database-plus-object isolated restore.

## Regression verification

```bash
uv run --locked --extra coworker pytest -q \
  tests/test_staging_day2_execution.py tests/test_staging_day2_acceptance.py \
  tests/test_staging_migration_alignment.py tests/test_staging_backup_restore.py
```

Only mark D02.T07–T10 and D02.G01–G05 completed after the complete **independent
hosted** evidence required by the Part 02 prompt and tracker #728 exists.
