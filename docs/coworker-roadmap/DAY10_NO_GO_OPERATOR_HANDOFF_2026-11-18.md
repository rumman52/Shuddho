# Rukh AI Day 10 operator handoff — source-only snapshot (18 November 2026)

**Decision: SOURCE_ONLY / NO-GO.** No eligible 5–10-user pilot candidate has been deployed/frozen. This document is a read-only technical handoff for [#736](https://github.com/rumman52/Shuddho/issues/736), not human approval, a signed release, or a general-launch decision.

## Source vs. immutable candidate
- **New review base:** [`aa705726f4c76cbb819a62211b7743aa44c59b17`](https://github.com/rumman52/Shuddho/commit/aa705726f4c76cbb819a62211b7743aa44c59b17), merge of #774, not a deployed or approved release. **Historical pre-#774 main:** [`c8aa7cf8444f1cf8c5408568e78b3cae6792f00a`](https://github.com/rumman52/Shuddho/commit/c8aa7cf8444f1cf8c5408568e78b3cae6792f00a) had Coworker, governance and merge-gate failures; do not transfer that CI verdict to new main without a new exact-head run.
- **Already-merged source work:** [PR #774](https://github.com/rumman52/Shuddho/pull/774) fixed the invalid export-fault test fixtures; this PR hardens the Day 10 identity/CI evaluator without duplicating #774.
- **Release ID:** **not assigned**. **Immutable rollout-manifest SHA-256:** **not available**. Do not substitute the git SHA or a handwritten placeholder for either. When an authorized freeze happens, use the *same actual* release ID and byte digest in every report, evidence receipt and signed owner decision.
- **API/worker build identities:** no paired exact-candidate authenticated readbacks. The historical staging API deployment is not equivalent to main. No worker release to compare.
- **Schema:** source's merged Alembic head is `0072_merge_0071_heads`; connected Supabase staging read-only ledger returned `0070` on 18 Nov. **No migration was applied.**
- **Provider/model:** source README policy is DeepSeek with explicit Gemma rollback, **not** an authenticated live provider/model identity. Do not infer canonical planner performance from source defaults. 43 feature flags: source inventory exists; exact API-and-worker readback and disabled values are not frozen.

## Exact-source CI scorecard
[Main run #44278207003](https://github.com/rumman52/Shuddho/actions/runs/44278207003) for `c8aa7cf8444f1cf8c5408568e78b3cae6792f00a`:
| Check (actual GitHub context) | Status |
|---|---|
| test-and-build | success |
| Frontend tests and builds | success |
| coworker | **failure:** 2 export-recovery fixture failures (1,628 passed / 2 failed / 4 skipped); [job](https://github.com/rumman52/Shuddho/actions/runs/44278207003/job/134711768177) |
| browser-qualification | success |
| PostgreSQL 18 staging compatibility | success |
| governance-audit | **failure:** missing GitHub App client-ID input; [job](https://github.com/rumman52/Shuddho/actions/runs/44278207003/job/134711766937) |
| ci-merge-gate | **failure** |

The live [ruleset 27324410](https://github.com/rumman52/Shuddho/rules/27324410) was read back with zero required approvals and no mandatory status-check rule; it does not enforce the checked-in `infra/github/main-ruleset.json`. **Owner-admin must manually reconcile governance and verify merge controls.** Do not override it via an insecure create/apply path.

## Read-only platform inventory
| System | Observed on 18 November | Acceptance gap |
|---|---|---|
| Supabase `shuddho-staging` | ACTIVE_HEALTHY, PostgreSQL 17.11, application schema `0070`; accounts/Auth users/agent runs/artifacts/stored objects all **0** | No approved backup/restore or data/worker migrations, no operated scenario |
| Render `shuddho-api-staging` | Live [deployment `dep-dbsbon4r5hns73b3dv9g`](https://dashboard.render.com/web/srv-dav98otg1s2s73cod4gg) built from `0e0b662fad0a02817a79a4514abba8f94e0ad022`, not main. Connected Shuddho service inventory has **no worker** | Need operator-authorized exact release pair, worker, Temporal, object-storage configuration |
| Vercel connection | Connected team inventory lists `ali`; direct `shuddho-web-editor` lookup returned 404. GitHub's Vercel preview comment on #774 is a separate integration signal | No connected Shuddho deployment/readback proof |
| Linear | [MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout) already tracks related Day 1 blockers; no new Day 10 issue was created | Use [GitHub #736](https://github.com/rumman52/Shuddho/issues/736) as Day 10 authority |
| PostHog | No approved Shuddho analytics project/telemetry scope identified in this check | No defensible production cost, latency or event-count report; do not start capture without privacy approval |

## Evidence gates and independent owners
| Gate | Status | Accountable next action |
|---|---|---|
| Exact final source CI + independent review | **NO** | A/B fix verified failures in #774, review this PR; C/Repo admin resolve governance |
| API + worker SHA/build, schema, provider/model, complete 43 flags | **NO** | C and A obtain authenticated readbacks and freeze a single candidate |
| Live planner / curated-quality / fact-recall | **NOT RUN** | D runs `scripts/agent_eval.py` and `scripts/coworker_quality_eval.py` on the exact provider/model, preserving 100% canonical thresholds where configured; bind real report bytes |
| Original Day 9 holdout | **NOT VERIFIED** | D independently checks 40 cases, 36/40 accepted, >=9/10 each cell, all 40 security-positive, reviewers and custody controls |
| 20 operated recovery receipts | **0 independently verified of 20** | D/C inspect each real boundary trace and bind release ID/SHA/digest; do not mark simulated data operated |
| Kill switches + worker stop/restore + safe rollback | **NOT OPERATED** | C/A operate in separately authorized staging and observe PostgreSQL/Temporal/object-store reconciliation |
| Cancel during inference + overdue paused schedule | **NOT OPERATED** | A/C/D verify zero late side effects and zero admissions after due time |
| Two-owner docs/memory/artifacts/activity isolation + multi-turn golden | **NOT OPERATED** | B/C/D run both cross-owner directions and inspect delivered files on final provider/model |
| Distinct founder + C signoffs | **MISSING** | Founder and C authenticate **separately** against the exact digest, via approved channels; JSON is not authentication |
| Allowlist 5–10 named pilot users | **NOT AUTHORIZED/NOT DONE** | Only an authorized operator after READY, separately record manual admission |

**Disposition rule:** SOURCE_ONLY until all technical gates pass; STAGING_ONLY only when verified technical gates pass and solely owner authorization remains; READY_FOR_OWNER_CONTROLLED_PILOT only after the canonical gate and two independent signoffs. Admission is a *separate operator action*. Never imply general release.

## Costs, latency, incident response, observability and data
- **Cost/latency scorecard:** no live release-bound provider token-cost, per-run charge, p50/p95 execution/inference latency, queue age, retrieval/storage growth, or error denominator is available; leave all **UNMEASURED**, not zero. D/C must capture provider invoices/usage and timestamped metrics with consent.
- **Monitoring to validate:** `queue_age`, `task_success`, `provider_errors`, `latency`, `token_cost`, `storage_growth`, `agent_failures`; include research/actions conditional checks when those capabilities are enabled. Prove alert routing to the privately maintained on-call record before GO.
- **Incident roles:** C is release incident commander/operator; A owns API/agent/worker restoration; B owns data isolation and artifacts; D owns independent quality/holdout verdict; Founder owns business GO/NO-GO. Individual names/phones and credential locations must remain in approved on-call storage, not this public repository.
- **Retention/backups:** no confirmed staging backup timestamp, independently restored snapshot, object-storage retention age, Temporal history retention or RPO/RTO measurement. Obtain approved PostgreSQL backup, object-store version/restore and Temporal reconciliation receipts before testing rollback. Do not delete data or change retention by inference.
- **Safe rollback sequence (not executed):** authorized C stops new admissions, sets `SHUDDHO_COWORKER_ENABLED=false`, `SHUDDHO_AGENT_RUNTIME_ENABLED=false`, `SHUDDHO_PERSONAL_GOALS_ENABLED=false`, `SHUDDHO_AUTOMATIONS_ENABLED=false`, `SHUDDHO_AGENT_RUNTIME_V3_ENABLED=false`, `SHUDDHO_CONTEXT_RETRIEVAL_ENABLED=false`, `SHUDDHO_ACTIONS_ENABLED=false`, `SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED=false`, `SHUDDHO_CONNECTOR_READS_ENABLED=false`, `SHUDDHO_BROWSER_PUSH_ENABLED=false`; read back API and worker; fence in-flight work; stop worker; restore the **operator-verified** previously safe SHA/config; verify database/Temporal/outbox/artifact consistency and file retrieval; record before/after timestamps and receipts. A switch list is a plan, not observed evidence.
- **Known limitations:** no deployed worker, incompatible staging schema, unqualified provider and model, no signed manifest/holdout, inadequate live GitHub protection, no approved production or billed staging authority; private storage remains private. Preserve default-off flags and all existing local Bangla/fallback behavior.

## Ranked executable backlog
1. **A/B:** finish and independently review #774; rerun focused tests and full exact-head CI. Review this evaluator hardening PR separately without self-approval.
2. **C / repository admin:** set GitHub App client ID and private key **only** in `v01-governance` and `pa10-staging` GitHub environments; enforce the existing reviewed ruleset and verify both positive/negative merges.
3. **Founder + C:** explicitly authorize the billable non-production worker/Temporal/S3/backup scope and synthetic test grants, or leave those tasks blocked. Avoid unapproved deployment and consumer activity.
4. **C/A:** operate a backed-up staging migration and exact API/worker deployment, then freeze provider/model/43 flags with `staging_release_freeze.py prepare/verify` and one immutable manifest digest.
5. **D:** independently run live planner/quality/fact recall, 40-case holdout and all 20 recovery boundaries on the exact candidate.
6. **A/B/C/D:** run rollback, cancel/inference fence, overdue paused schedule, both-direction owner isolation and golden deliverables; inspect real outputs.
7. **Founder + C:** separately authenticate approvals against the same digest; only then manually admit 5–10 allowlisted people. Maintain a separate pilot-outcome report and defer general release.

## Reproduction commands (source-only, do not invent evidence)
~~~bash
uv run --extra coworker pytest tests/test_day10_release_decision.py tests/test_cohort_release_gate.py tests/test_staging_release_freeze.py -q -rs
uv run --extra coworker python scripts/day10_release_decision.py --help
uv run --extra coworker python scripts/agent_eval.py --help
uv run --extra coworker python scripts/coworker_quality_eval.py --help
~~~
The actual release decision must be run with real reviewed input paths only after the operator has frozen the candidate. It reads evidence; it cannot authenticate receipt authors or activate the pilot.

**Pilot outcome:** no users admitted, no pilot observations, NO-GO. **General release:** separate future decision, not made.
