# Day 2 runtime build identity — candidate, not hosted qualification

Base: 52a0feb0bb0a674d0c0840a679a3941d78ef6314. Source-only candidate addresses the missing implementation behind merged tests in #971. It incorporates #974 as a second parent (merge commit 9409bc91fdab051cc609be5c40260b7064c2c377); do not separately merge overlapping changes. No managed DDL, deploy, paid provisioning, production activation or telemetry activation.

## Implementation
- Deterministic bounded, no-follow build-input hashing of source revision claim, pyproject and uv.lock bytes, installed distribution inventory, interpreter and platform metadata. This is not a signed build provenance or OCI image digest.
- Shared v2 capability projection and cohort-gated v3 API manifest; schema, model, queue, build and runtime identity; sanitized compatible fresh worker inventory with fail-closed readiness.
- Additive 0073 migration following 0072, nullable historical identity, PostgreSQL registration and immutability guard; transaction-local registration identity. Unversioned local development SQLite remains supported but not release-qualified.
- Freeze requires reviewed expected build, model and queue, real 0073 schema, v3 identity and matching healthy fleet; execution and acceptance bind run, worker, model, recovery and restored archive schema to the candidate.
- Both disposable PG17/18 migration branches now traverse 0070, separate 0071 parents, 0072 merge, 0073, rollback and replay. CI retains previous gates and requires the focused fingerprint tests without skips.

## Observed tests
- Fingerprint test-first import error, then 16 passed; runtime identity missing-function RED then 17 passed; fleet helper missing-function RED then 18 passed. Focused local harness used actual module with isolated config helper / synthetic settings and repository; not full application integration.
- Actual isolated SQLite migration: upgrade added all five nullable fields, legacy row preserved, downgrade and replay succeeded. Migration blob a3649512576f977ea3331b2552fe5361c0252d46. PostgreSQL trigger verification requires candidate CI.
- #974 CI run 46129458718: PG17 21 passed, PG18 21 passed, static 5 passed; all zero skips. Those rehearsals reached 0072, not 0073. Full PG compatibility step failed later with four pre-existing worker identity failures. Do not transfer these passing receipts to the new 0073 head.
- Main CI 46063866649 failed before this work (76 build failures; 8 Day 2 mandatory failures; 4 broad PG failures). Full exact candidate CI remains necessary.

## Remaining boundaries
- Full checkout was unavailable locally due DNS/network restrictions. Full integration and browser test results must come from candidate CI.
- Restored API readback still uses v2 source identity and owner-isolation checks; binding observed restored v3 identity independently to the original frozen release remains follow-up work. No hosted acceptance claimed.
- Original 0070 managed backup + restore, private object restore and distinct approved destinations, bounded worker authorization, actual staged worker/Temporal/model execution, exact candidate live readbacks, two owner accounts, and independent governance approval remain outstanding. No migration or release on managed infrastructure until those gates pass.
- Native GitHub ruleset and governance App credentials are owner-admin blockers; no merge, no bypass.
