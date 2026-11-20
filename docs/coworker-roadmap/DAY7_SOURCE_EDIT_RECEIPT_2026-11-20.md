# D07.T04 / D08.T07 — dated source-edit receipt guard

**Date:** 2026-11-20. **Scope:** GitHub issues #733/#734, Linear MD-8, Rukh AI Part 04 pp. 1–2 and 4. **Base:** `d88e606615195b88a876317ebb5a8ef79852da41`.

## Gap and source-only change

The two-day gate already required exactly one changed authorized document version between local-date briefing occurrences. It did not require the **time of the owner edit** or an independently inspectable source-history reference. A version difference is not evidence that the authorized owner edited that document after the first observed briefing and before the second natural due time.

The Day 8 `staging_pa10_scheduled_profile verify` command now accepts `--source-edit-receipt PATH` **only alongside** `--prior-evidence` on a daily briefing. It fails immediately if the second-day receipt is missing, and disallows the receipt on first-day/other profiles. The receipt is copied to the Day 8 evidence for strict validation by `staging_day7_two_day_gate`.

The receipt must be a JSON object with exactly the fields below; the example uses **synthetic placeholders only**:

```json
{
  "owner_id": "synthetic-owner-id",
  "project_id": "owner-project-id",
  "document_id": "selected-document-id",
  "previous_version_id": "prior-immutable-version",
  "current_version_id": "new-immutable-version",
  "edited_at": "2026-11-20T10:35:00+06:00",
  "operator_case_reference": "controlled-case-reference",
  "evidence_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

The final gate enforces owner, project, operator case, changed document ID, prior/new immutable version pins and a lowercase 64-character evidence digest. `edited_at` must include an explicit UTC offset and be **strictly later than first `verified_at` and earlier than second `due_at`**. It retains both the edit's original offset-bearing timestamp and the owner-IANA-zone rendering in the report. It rejects missing/extra fields, swapped owner/scope, stale pins, bad digest, naive timestamps, and out-of-window edits. Synthetic tests cover daylight-saving offsets as well as the controlled pause opportunity.

## Trust boundary and remaining work

This shape validator **cannot authenticate the edit receipt**. Independent operator D must read back the owner's real document version/edit event, attest that the retained original evidence bytes hash to `evidence_sha256`, and validate that the effective edit time was between natural firings. The printed report and synthetic tests **do not prove** that a Temporal timer fired naturally or an owner notification was actually delivered; those require independent Temporal/transport logs, deployed worker/SHA readbacks and the post-pause zero-admission opportunity.

No live schedule was created, worker provisioned, paid provider called, database mutated, PostHog event transmitted, production feature enabled, or Day 9 freeze authorized by this patch. Owner/Founder budget, privacy and staging authority and the 80-first-run Day 8 experiment remain separate, blocked operational gates. **Status: SOURCE_ONLY / NO-GO** until those receipts exist.

## Reproduction and verification

```bash
uv run --locked --extra coworker pytest -q tests/test_staging_day7_two_day_gate.py tests/test_staging_pa10_scheduled_profile.py
uv run --locked --extra coworker pytest -q tests/test_automations.py tests/test_coworker_temporal.py tests/test_day8_telemetry_privacy.py tests/test_core_agent_observability.py tests/test_task_economics_evidence.py
```

Required exact-head GitHub Actions jobs and independent code review must be read back before merge. Keep the original evidence privately; do not upload raw document contents, credentials or user identifiers to PR comments.
