# Plan: native export rejection regression gate

## Goal
Preserve both Day 6 fail-closed boundaries: reject malformed native output before object-store publication, and reject a corrupted persisted export manifest before task completion.

## Diagnosis
The original three-case test supplied placeholder DOCX/PDF bytes and a noncanonical text MIME type. DocumentRunner.export correctly calls validate_day6_exports before storage, so the test raised during export and never reached its completion assertion. This is a fixture/phase mismatch, not a reason to weaken production validation.

## Evidence-led implementation
1. Keep the production contract unchanged: validate_day6_exports runs before object-store PUT and export-checkpoint publication; DocumentRunner.complete independently validates the persisted manifest and object identity/readback.
2. Exercise the early export boundary with the real native renderer, then separately corrupt the file inventory (missing, duplicate, unexpected) and DOCX/PDF bytes. Assert export_invalid, a still-running task, no export checkpoint, no published artifacts and an empty task-scoped object prefix.
3. Exercise the completion boundary only after a valid four-file native export. Corrupt the persisted Step.output["artifacts"] with a missing, duplicate or unexpected entry. Assert completion rejects with export_invalid, the task remains running, no Artifact rows are published, and the valid private objects remain private.
4. Keep tests/test_export_manifest_rejections.py in the mandatory Day 6 CI command with required-module/no-skip enforcement.
5. Re-run the four Day 1 #664 baseline regressions in the same required Coworker job.
6. Preserve the initial RED run, inspect exact-head CI, update the progress ledger, and request independent human review. Keep the PR unmerged while governance/review controls remain unmet.

## Scope
Tests, CI coverage already added on this branch, and engineering evidence only. No production runtime change, database migration, RLS change, credential, ruleset, deployment, paid resource, feature flag, telemetry ingestion, provider change or pilot activation.
