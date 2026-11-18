# Day 8 — Measurement decision integrity (2026-11-18)

## Task contract

- **Objective:** do not freeze a 40-case candidate with unknown end-to-end latency, unapproved decision criteria, incomplete per-type failures/retries or unpriced cost components; select the least all-in cost per human-accepted output among quality/latency-eligible profiles.
- **Dependencies:** issue #734, merged PR #749 directional usage fields, PR #700 receipt safeguards, the 40 development tasks from source revision 602f76f73ad845fe3ac4b4cb133fd8a07dbd20a8, and issue #733's natural schedule.
- **Base:** c8aa7cf8444f1cf8c5408568e78b3cae6792f00a (main observed 18 Nov 2026).
- **Work branch/PR:** fix/day8-measurement-freeze-gate-20261118, [#779](https://github.com/rumman52/Shuddho/pull/779) (draft; no release).
- **Existing interfaces:** scripts/core_agent_observability.py -> compare_day8_development; tests/test_core_agent_observability.py; docs/CORE_AGENT_PHASE10_OBSERVABILITY_ECONOMICS.md.
- **Files:** the comparator, focused tests, this contract and Phase 10 operations docs plus progress. No runtime provider/adapters, database schema, Temporal worker, telemetry SDK or deployment files.
- **Compatibility:** schema v1 outer envelope unchanged; incomplete evidence produces BLOCKED and null aggregates. Configuration hashes and policy are additive requirements before freeze.
- **Acceptance:** 40 paired records per profile, 10 per language/workflow cell, matched model/tools/input suite and approved policy. Require >=36 accepted, >=9 in each cell, all-task safety, artifact/review receipts, no accepted baseline case lost, complete provider token directions, e2e p50/p95 meeting owner threshold, breakdowns and all-in cost component reconciliation. Never infer actual invoices or owner approval from a synthetic fixture.
- **Reproduction:** test-only commit 81d1af2fb97258901df6ad4a7c5844d6d71ba139, [CI #44287548874](https://github.com/rumman52/Shuddho/actions/runs/44287548874), Coworker suite **8 failed, 31 passed**. Failures exhibited false freezes on missing/slow end-to-end latency and missing policy, and wrong cost/yield selection, absent cell metrics.
- **Expected failure outcomes:** invalid breakdown/cost sum or mismatched approved policy raises ValueError; missing measurements or approval lineage produce BLOCKED with no freeze; latency-breaching candidate is excluded while an eligible baseline may freeze.
- **Checks:** uv run --extra coworker pytest tests/test_core_agent_observability.py tests/test_task_economics_evidence.py -q -rs; full CI on exact PR head. Local checkout unavailable in this connector-only session; report red and corrected CI distinctly. Separate operated commands for the 40-case comparison and two-day verifier remain blocked on private receipts/worker.
- **Secrets and owner gates:** provider API keys, approval evidence, private run output, Temporal credentials and owner-scoped documents remain in approved private stores, not GitHub. Founder + C own PostHog project/retention/consent/egress approval and spend ceilings. A owns stable model/prompt/tool/context choice. D owns independent paired scoring and private receipt custody.
- **Budget/timeout/revocation:** experiments must not call provider before approved per-run and total budgets and model pricing. Keep current runtime budgets, default flags, cancellation, scopes and transaction uncertainty behavior unchanged.
- **Default-off and rollback:** no telemetry integration, payment, external send, deployment, provider/model switch, migration or index addition. Roll back the PR if review/CI rejects; previous report parsing remains available but does not qualify incomplete evidence.
- **Out of scope:** claiming first/second natural fires, posthog ingestion, real provider economics, independent holdout or production eligibility without operated evidence.

## Evidence levels

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | PR under review | Draft #779 |
| Reproduced | yes | Test-only head 81d1af2; CI #44287548874, 8 failed and 31 passed |
| Repository-verified | Pending final exact-head CI | Required Day 8 focused suite + full required PR CI |
| Staging-verified | Blocked | No authentic owner-approved worker/Temporal two-day evidence; zero staged run rows in latest read-only record |
| Production-qualified | No | Independent scores, pricing approval, privacy/egress approvals and operational threshold evidence absent |
| Activated | No | Explicitly prohibited without additional owner authorization |

## Next exact actions

1. Review final-head CI; fix any new failures without weakening source contracts.
2. C + Founder: write approved PostHog project ID, domains, environment, retention, consent, kill switch and current spend ceilings in #734/#584 in non-sensitive form. Do not provision a worker or enable telemetry based only on historical price discussions.
3. With authorized synthetic owner/doc/Temporal worker, D + C capture first and second natural local-date schedule histories, version change, dedupe and paused zero admissions. Run existing staging_day7_two_day_gate.py on independently authenticated files.
4. A + D record immutable model/prompt/tool/context/rubric/pricing/budget identities, run 40 paired tasks under explicit ceilings, verify all receipts privately and run the Day 8 comparator. Publish only redacted aggregate gaps; hold Day 9 freeze until qualified.
