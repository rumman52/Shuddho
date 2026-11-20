# Day 6 independently verified research source identity — TDD plan

> Superpowers: use systematic-debugging, test-driven-development, verification-before-completion, and independent code review. The original user-supplied Part 03 document remains the acceptance contract.

## Goal and proven root cause

Day 6 D06.T02 / D06.G01 requires an evidence-backed research comparison using independently checked sources. The merged receipt verifier at `scripts/staging_days3_6_acceptance.py::check_day6` insists on three citations but does not reject repeating the same source ID, retrieval URL or identical source content digest three times. A single synthetic source can be counted as three independently checked sources.

This change only strengthens internal receipt consistency; it does not authenticate hosted browser/model/provider/storage events. Keep `evidence_internally_consistent_not_live_attested` and never mark D06.G01 hosted PASS from synthetic fixtures.

## Task 1 — RED

Files: `tests/test_staging_days3_6_acceptance.py`.

- Add three adversarial, parametrized cases for a research cell: duplicate ID with otherwise different URL/digest, duplicate URL with otherwise different ID/digest, duplicate SHA-256 with otherwise different ID/URL. Add the URL-fragment variant to catch different anchors on the same document.
- Retain the allowed positive case: two language outputs may cite the *same* three independent sources, but each language cell must have three distinct sources.
- Run test-only head in Actions and record the expected `DID NOT RAISE Days36EvidenceError` in the new tests.
- Keep the 40-case quality and source-level test suite independently qualified.

## Task 2 — GREEN

File: `scripts/staging_days3_6_acceptance.py`, inside the research case path only.

- Track unique `source_id`, normalized fragment-free URL identity and nonrepeated source SHA-256 per research cell.
- Reject duplicate provenance identity before accepting a cell, independent of different titles/receipt labels.
- Preserve quote verification, HTTPS URL checks, retrieved timestamps, existing owner denial and native artifact checks.
- Do **not** enforce uniqueness across language cases: reuse of legitimate approved sources between Bangla/English is intended.

Update the synthetic fixture to use three different source digests, making its independence explicit.

## Task 3 — verify and PR

- Re-run the exact-head focused mandatory Days 3–6 receipt suite (zero skips) and the full general Python suite via GitHub Actions.
- Record RED→GREEN, final head SHA, run IDs, failed or canceled unrelated jobs, and the release/governance boundary in the PR.
- Open one bounded PR for independent review; do not merge without required checks, branch rules and real staging approval.
