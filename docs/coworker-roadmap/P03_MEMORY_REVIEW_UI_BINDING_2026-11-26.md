# Day 5 memory review binding — 2026-11-26

Baseline: 43d99fd64467492a7da809cda0ae178191e53981.
Regression-test commit: f496326cab381f5628626257f3210abd29438ea5.
Implementation commit: 4b1d6a0e53a54257c01b6367e8bee232bb67ce28.

## Repair
- A proposal with an omitted memory selection has a different canonical digest from an explicitly empty selection. The frontend tracks the selection mode attached to the preview and requires a new validation when it changes.
- Review checks exact ordered fact IDs and versions; missing, stale and inactive pins in the loaded snapshot cannot be submitted. Server-side validation remains authoritative against concurrent changes.
- GET /memory publishes the effective minimum of the configured selection cap and the schema ceiling. The client honors this value; old APIs without the field retain the historical ceiling of 20.
- The review shows exact fact IDs, including on narrow panels; queued checkbox changes cannot exceed the cap. No new permissions or persistence changes.

## Verification
Isolated Node probe of the previous selection expression, cap and stale-check behavior: 3 failing, 1 passing. The exact new helper and four tests were copied from the GitHub commit and run via the local TypeScript transpilation harness: `node run.cjs && node --test taskMemoryReview.test.mjs` — 4 passing, 0 failing, 0 skipped.
Helper blob 0832ca7158689cc7e6b9d9817cb77a119ee8a1f6; test blob b8d6f56d62d1546d0e9722e83801d7c90e79e46a.
The React integration tests, FastAPI regression tests and full browser/build suites are committed but not locally executed (checkout DNS/dependencies unavailable). Require exact-head CI and independent human review before protected merge. No staging acceptance is claimed.

## Integration and rollback
The cap constant is shared by both server request schemas. Reconcile the separate strict version-validation PR (#944) if necessary; retain both changes. Roll back the frontend and server changes together if required. The additive optional API field is backward compatible. No deployment, migration, provider call, transaction or spend was performed.
