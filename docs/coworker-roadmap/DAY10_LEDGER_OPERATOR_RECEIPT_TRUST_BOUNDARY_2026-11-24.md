# Part 05 / Day 10 — fail closed before signing operator receipt JSON

**Checkpoint date:** 24 November 2026 (Asia/Dhaka). **PR:** [#908](https://github.com/rumman52/Shuddho/pull/908). **Disposition:** source-only correction; controlled pilot **NO-GO**.

## Contract, evidence and ownership

The operator-held HMAC release ledger signs and verifies canonical entry dictionaries, not all duplicate or dangerous raw JSON. Merged [PR #901](https://github.com/rumman52/Shuddho/pull/901) already strictly reads ledger *history*; the remaining pre-sign ingress `scripts/cohort_release_ledger.load_json_object(path, label)` still used `json.loads(Path.read_text())` to validate the `rollout manifest`, `canary plan`, `progression decision` and `operator status`.

A raw progression file can contain `"decision": "STOP_ROLLOUT", "decision": "ELIGIBLE_FOR_EXPANSION"`. Python's default JSON loader applies last-key-wins, so a `stage_approved` event can be HMAC-signed on the second value without rejecting the contradictory STOP. The reader also followed final symlinks and accepted nonfinite values and unbounded files. This source correction closes that narrow ingress, not all other ledger/append races.

- **Base main SHA:** `a3e8dba039436e2553d10f2147f886cdf1877815`
- **Work branch:** `fix/day10-release-ledger-event-input-trust-20261124`
- **Owner roles:** A source engineering and tests; B independent review; C authenticated deployment/recovery evidence; D independent human custody, scores and safety.
- **Existing implementation interface:** `load_json_object(Path, str) -> dict`, `validate_bound_inputs`, `append_event`, `read_entries`, `verify_entries`.
- **Implementation:** reuse `scripts.ruke_pilot_eval.read_json` for bounded 4,000,000-byte, one-descriptor final-symlink-resistant regular-file JSON parsing with duplicate-key/nonfinite rejection, mapping all `OSError`/`ValueError`/`UnicodeError` to `ReleaseLedgerError`. Preserve valid dict type, existing schema/HMAC logic, event order, signed event contents and single-append outcomes.

## TDD evidence and verification

1. **Tests before implementation:** `8dfdf9aaab3a35d14e41430e172c522e506d340e` added six synthetic cases to `tests/test_cohort_release_ledger.py`. They use the real local signed-ledger append and verification contract.
2. **Observed RED:** [GitHub Actions #45246504107](https://github.com/rumman52/Shuddho/actions/runs/45246504107) `test-and-build` Python: **4 failed / 3,783 passed / 109 skipped / 6 warnings**. All four failures were newly added, isolated missing rejections for shadowed stage decision, linked rollout, oversized canary plan and nonfinite member cap. The nonregular-directory and valid signed-history checks already passed; neither was counted as failed.
3. **Minimal production change:** `ace514e03d114b6f91040904c879e2cb3e804d75`: change only the operator JSON ingestion call and import, plus explicit `UnicodeError` domain mapping. There is no weakening of STOP/rollback/canary semantics.
4. **Verification still required:** inspect *exact final PR-head* GitHub Python/build, frontend, browser, PostgreSQL compatibility and Coworker CI. Mandatory safety skips remain nonqualifying. A green source CI result cannot be represented as an actual operated Day 9 or Day 10 exit.

## Residual boundaries, access, rollback

This fix does **not** hash the exact bytes parsed during `load_json_object`: many event appenders separately call `file_sha256` and reopen input paths. A post-validation filename change can still cause a parse/digest TOCTOU, and ledger write/append concurrency or symlinked parent components also remain separate review risks. No documentation in this PR claims to close them. Record a separate bounded improvement for parse/hash binding and append atomicity; avoid broad blind changes to the 30+ ledger schema branches. A large legacy signed operator receipt above 4 MB will now be rejected; do **not** truncate or rewrite old evidence—retain it and require a new properly reviewed lineage. Rollback of the code is by exact reviewed source revision only, not old event mutation.

**No cloud mutation authorized** by this task: no secrets, paid provider inference, migrations, app/worker deployment, product activation, unapproved owner traffic, telemetry ingestion or admission. Read-only Supabase `shuddho-staging` is ACTIVE_HEALTHY PG17.11.0.003 and Alembic revision `0070` at inspection; this is not matched frozen staging runtime. Render only workspaces inventoried; Vercel is linked to unrelated `ali`/`hero-dev-code`, ProductOS to unrelated `Dust2Glow`, PostHog default project 675660 reported no ingested events. Linear MD-5–MD-8 are existing tracker references.

## Completion classification

| Required level | Evidence state |
| --- | --- |
| Implemented | Source commit `ace514e03d114b6f91040904c879e2cb3e804d75` |
| Repository-verified | Pending exact-final-head run readback |
| Staging-verified | **NO** — authentic frozen deployment and operated receipts absent |
| Production-qualified | **NO** — independent D/C/Founder evidence absent |
| Activated | **NO** — never admit a pilot on synthetic source checks |

Part 05 requires 40 fresh first attempts across four cells; 80 independent blinded reviewer grades; at least 36/40 accepted and 9/10 per cell; 40/40 security; 20 distinct **operated** PostgreSQL/Temporal/private-object storage recovery traces; exact source SHA, runtime/worker/schema/model + all 43 explicit capability booleans, actual rollback/cancel/pause/golden/owner isolation, and distinct Founder/Owner-C authorization. The separate authorized 5–10 member HTTPS allowlist/non-member denial is later. None was obtained here.

**Governance NO-GO:** main ruleset 27324410 remains active with 0 approving reviews and no required status checks. Prior [PR #901](https://github.com/rumman52/Shuddho/pull/901) merged without independent review although its CI merge gate failed. Repo admin must enforce checks/review and demonstrate denied merge before relying on a release. Historical v4 ledger 18/100 tasks, 5/54 exit checks and 0/10 days accepted remains historical and unchanged by this PR.


## Integration regression and resolution — 24 November

[First full documentation-head CI #45247132455](https://github.com/rumman52/Shuddho/actions/runs/45247132455) reported **2 FAILED / 3,785 PASSED / 109 SKIPPED / 6 WARNINGS** in Python `test-and-build`, although the new operator-input tests passed. Both failures were preexisting `tests/test_cohort_canary_progression.py` regression fixtures, `test_signed_recovery_epoch_rejects_ambiguous_verified_at` and `test_signed_recovery_epoch_rejects_oversized_verification`. Their helper `build_recovery_ledger(..., mutate_recovery=...)` injected intentionally corrupted JSON **before** creating the signed recovery event; the hardened signer correctly rejected these inputs, so fixture construction raised `ReleaseLedgerError` before the downstream canary checker ran. This is evidence of the new earlier STOP boundary, not grounds to weaken it.

Test-integration fix commit `727b5abe8e819c0937f9749cfb862e05760dadd6` moves the mutation to **after the legitimate signed recovery event** is appended. The same downstream tests now exercise corruption after signing, ensuring the canary verifier still rejects ambiguity or oversized bytes without making the signer accept invalid evidence. The production function was **not weakened or changed**. Require a fresh exact-final-head CI result after this fixture correction; until then source verification is not green.
