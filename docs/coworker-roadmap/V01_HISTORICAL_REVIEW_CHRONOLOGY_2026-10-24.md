# V-01 — chronological review evidence in post-merge audit (24 October 2026)

## Scope and baseline

Baseline main: `a14dee4870af05954936b88882e40f6db2374aab` (merged PR #557). This is a **read-only historical evidence classification fix**, not a required status check, native ruleset update, or approval to merge/deploy. V-01 issue #484 remains open.

## Demonstrated defect

`scripts/v01_merge_evidence.py::inspect_premerge_evidence` chose the latest actionable review using the GitHub review **ID**, even though a review may be created as pending and submitted after a newer-created review. Creation order is not submission order. It could therefore overlook a later-submitted change request or an old-head approval and report `no_incident_in_supplied_evidence` incorrectly; conversely, it could ignore a valid later-submitted reapproval.

The live independent-review gate already orders by submission timestamp. The historical auditor must use the same chronology principle, with different semantics: only decisions submitted **at or before merge** count.

## Change

- Parse timezone-aware `submitted_at` for every actionable review.
- Choose each reviewer's most recent **submitted** actionable state before merge; review ID only breaks ties for identical, non-contradictory evidence.
- Treat contradictory states/commit bindings at an identical timestamp for one reviewer as ambiguous evidence, raising `EvidenceError`.
- Ignore post-merge decisions for historical classification. Preserve distinct unverified-native-policy limitations in all outputs.
- Do not change merge permissions, credential handling, CI job names, run provenance, provider actions, release flags, or schema.

## Test contract

Added five regression cases to `tests/test_v01_merge_evidence.py`: lower review ID submitted later as change request, valid later reapproval, later old-head approval, contradictory same-time submissions, and post-merge change request. Existing historical/provenance/redirect assertions must remain green.

Test-only commit `1d5f2820118e43848c5853e357cd42aa11157ef1` preceded the implementation commit `4682243eae27d9e1bbe9296e3996ea9056d5ce21`. No claim of observed failing-first CI is made until an exact test-only run is available. Verify final documentation-inclusive PR head with `uv run pytest -q tests/test_v01_merge_evidence.py`, complete `test-and-build`, mandatory `coworker`, and `ci-merge-gate`, and independent human review before merging.

## Release evidence boundary

This read-only tool classifies supplied historical run/review evidence, not atomic GitHub merge authorization. It **cannot** prove that native branch protection is active or non-bypassable. Issue #484 needs administrator-visible required rules, source-pinned final-head checks, a separately trusted independent reviewer and real negative/positive merge controls. Staging #291 and all 17 A/C/P/V acceptance requirements retain their independent operated-qualification gates. No staging/production activation is authorized.
