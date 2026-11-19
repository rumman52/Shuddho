# Plan: native export rejection regression gate

## Goal
Correct the three malformed native-export regression tests to match the existing fail-closed publication boundary, and make the tests mandatory in the Day 6 CI gate. Re-run the four Day 1 #664 baseline regressions on the pinned current source tree.

## Evidence-led implementation
1. Preserve the current production contract: `validate_day6_exports` runs in `DocumentRunner.export` before object-store PUT and export checkpoint publication; `complete` independently verifies the persisted inventory, owner/task-bound object keys, sizes, and SHA-256 readback.
2. Promote `tests/test_export_manifest_rejections.py` into the Day 6 focused CI command and require its JUnit module with zero skips.
3. Change each missing/duplicate/unexpected inventory regression to expect `export_invalid` during `export`, then assert the task remains running, no export checkpoint or published artifacts exist, and the task-scoped object-store prefix is empty.
4. Add a mandatory no-skip CI step for the four #664 baseline tests: provider capacity, networkless minimal sandbox command/mount isolation, and both Fly repository coding tests.
5. Verify the final PR head through GitHub Actions, retain the initial three-failure RED run, update the progress ledger without crediting any release gate, and request independent review.

## Out of scope
No production runtime changes, database migrations, RLS changes, credentials, rulesets, deployments, paid resources, feature flags, telemetry ingestion, provider changes, or pilot activation.
