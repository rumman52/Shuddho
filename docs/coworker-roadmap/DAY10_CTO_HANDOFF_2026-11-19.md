# Rukh AI Day 10 CTO and incoming-operator handoff — 19 November 2026

**Disposition: SOURCE_ONLY / NO-GO.** This is a dated, read-only handoff, not a reviewed release receipt, actual migration, operator action, owner authorization or pilot admission. The full original execution form remains **18/100 verified task PASS**, **5/54 exit checks PASS**, and **0/10 days fully accepted** at this readback. GitHub merges, green source tests and synthetic replay are **not** substitutes for operated acceptance.

## Exact identity and evidence confidence

| Item | Independently observed state | What is still missing |
| --- | --- | --- |
| Repository | `rumman52/Shuddho`, **main** `33aefddc5a5fd918d334c981769c6f9cf1b0b5bf` at this check, after merged PRs #788–#795 | Reviewer-approved, release-frozen final commit and exact corresponding checks |
| [Main CI #44387626852](https://github.com/rumman52/Shuddho/actions/runs/44387626852) | `test-and-build`, frontend, browser, PostgreSQL 18 **passed**; `governance-audit` **failed** (`actions/create-github-app-token` client ID missing); Coworker still running at this readback | Completed Coworker and success of governance + actual merge gate; do **not** claim all-green |
| GitHub ruleset | Active native [ruleset 27324410](https://github.com/rumman52/Shuddho/rules/27324410): zero required approving reviews, no required status checks, `bypass_actors=[]` | An administrator-approved same-ID reconciliation and genuine independently reviewed negative/positive merge controls |
| Follow-up code | [Draft PR #796](https://github.com/rumman52/Shuddho/pull/796) at `c6fc507ae6423349fe82d4e90b35b890cf46a0f5`. Reproduced pilot member-identity false-positive in [RED CI #44390228483](https://github.com/rumman52/Shuddho/actions/runs/44390228483): 15 failed, 35 passed; corrected Day 10 mandatory source gate **passed** in [CI #44391026820](https://github.com/rumman52/Shuddho/actions/runs/44391026820); full Coworker ongoing at this snapshot | Complete exact-head CI, distinct human code review, merge; then real qualified pilot observation on a deployed immutable candidate |
| Release identity | **No frozen release ID, rollout-manifest digest, image/build pair, worker readback or authenticated provider/model identity** | Owner C+A+D attest the *same* exact candidate and 43-key Boolean capability manifest, including disabled keys |
| Staging DB | Connected Supabase `bsmbvjenpvcyfjzwtuax`, PostgreSQL **17.11**, private `shuddho_coworker` **84** base tables, Alembic **`0070`** vs source **`0072_merge_0071_heads`**; 0 Auth users, AgentRuns and stored objects | Approved independent backup/restore, both 0071 branches + 0072 migration, private object readback, final schema identity and real synthetic-owner receipts |
| DB security | 0/84 private tables with RLS, but `anon` and `authenticated` have no schema USAGE, 0 public buckets. Do not mislabel RLS absence as an exposed public API; authenticate runtime grants and exposed schema | Actual second-owner negative-read and separate private-object denial tests |
| Render | `shuddho-api-staging` currently live at old `0e0b662fad0a02817a79a4514abba8f94e0ad022` (autoDeploy off); `shuddho-api` is a separate older production deployment (autoDeploy off); connected workspace has **no Shuddho persistent worker** | Approved paid resource/cap, Temporal/S3 secret custody, same-digest API/worker release, recovery and audited rollback |
| Vercel | Connected team exposes only project `ali`; no verified Shuddho target | Independent frontend-origin/deployment manifest readback on the exact release |
| PostHog | Only connected `Default project` ID `675660`, `ingested_event=false`, **not** owner-approved as Rukh destination | Founder/C+D approve project, retention, consent, egress and kill switch; validate live allowlisted events without PII |
| Operations metrics | **Unmeasured** cost per accepted task, queue age, p50/p95 latency, token usage, recovery success, 99.9%-window denominator, storage growth and provider errors | Operated counters/receipts on one frozen release; never substitute zero for missing data |

This is an immutable *observation note*, not an assertion that the observed SHA was approved, deployed, or remains the latest. Refresh main, live services and exact CI before acting.

## Decision and task gates

The original Day 10 release task is still **BLOCKED**, and pilot admission **has not occurred**. Human and operated prerequisites cannot be signed by a repo commit:

1. **Repository administrator + different code reviewer:** set `V01_RULESET_APP_CLIENT_ID` and `V01_RULESET_APP_PRIVATE_KEY` in protected `v01-governance` and `pa10-staging` environments only. Inspect the dry-run SHA/fingerprint of `scripts.reconcile_main_ruleset`, receive independent exact-plan approval, apply to **existing** ruleset `27324410` (never create a duplicate); require one fresh distinct approval, stale-review dismissal, last-push approval, resolved threads, strict `test-and-build`, `coworker` and `ci-merge-gate`. Prove an unreviewed PR is rejected and an independently reviewed, otherwise passing PR accepted. Record actual actors and result links. Do not self-approve or bypass.
2. **Founder + Owner C:** date and authenticate explicit paid worker, private backup/restore, Temporal, S3, provider/model/budget, PostHog privacy, retention and synthetic identity scope decisions. A code PR cannot authorize real spend or data egress; until approval, maintain **NO-PROVISION**.
3. **C + A:** capture an approved snapshot, restore isolated DB/object data and compare counts plus content hashes; migrate both `0071` parents through `0072_merge_0071_heads` in the designated staging environment; deploy API and durable worker at one immutable reviewed SHA/build pair, read back runtime model/provider and all 43 flags; verify the private bucket and actual Temporal/outbox crash recovery.
4. **A + B + D:** run first real two-owner private PDF/report flow, source tracing and both-way negative owner reads; produce and independently inspect the delivered artifacts. Verify Day 3–7 browser, memory, research, automation and **two natural firings on separate local calendar days** with immutable first-attempt receipts; synthetic fixtures cannot compress calendar time.
5. **Independent human D + C:** establish external holdout custody before outputs, prove developer read denied and D read permitted, freeze 40 untouched cases, independently score first-run outputs with two blinded reviewers, preserving minimum 36/40 accepted, 9/10 in each cell, 40/40 safety. Operate all 20 recovery boundaries on real PostgreSQL/Temporal/object storage, plus rollback, cancellation, paused schedule, two-way isolation and multi-turn golden output. A missing comparator must be declared a comparison gap, never a win.
6. **Founder and C, separately:** review the *same* candidate SHA/release ID/manifest SHA-256, independently authenticate approvals. Only if `scripts/cohort_release_gate.py` gives canonical `GO_CONTROLLED_COHORT` and `scripts/day10_release_decision.py` gives `READY_FOR_OWNER_CONTROLLED_PILOT` with zero blockers may a *separate authorized operator* manually allowlist 5–10 people. After admission, use [`scripts/pilot_admission_verify.py`](../../scripts/pilot_admission_verify.py) to check **every** HTTPS `/api/v1/me` account identity matches its signed member token, and verify fresh nonmember 403 and no provisioning. No general release follows from this.

## Owner handoff and safe-state procedure

**Accountability** (roles, not personal contacts): Founder — business GO/NO-GO and cost authorization; C — incident commander, staging database/worker/deploy operator and budget ceiling; A — backend, Temporal, idempotent recovery and immutable API/worker identity; B — product UX, cross-owner private files and quality; D — independent holdout, privacy and release-quality signoff; repository administrator — GitHub App and ruleset. Personally identifying contacts and secret locations belong exclusively in privately approved on-call storage.

**Current safe state:** no new pilot users, no inferred approvals, no provider calls, no analytics ingestion, no unreviewed deployment, no new paid worker, no migration, no action egress. Preserve current data unchanged; do not “repair” a running deployment by enabling defaults.

**If a separately authorized controlled staging release later needs rollback:** C first stops new admissions and external actions, uses the approved capability kill switches (`SHUDDHO_COWORKER_ENABLED=false`, `SHUDDHO_AGENT_RUNTIME_ENABLED=false`, `SHUDDHO_AUTOMATIONS_ENABLED=false`, `SHUDDHO_ACTIONS_ENABLED=false`; also apply the complete source-defined capability/connector switches) and independently reads back **both** API and worker. Fence in-flight activities and outbox providers, stop the worker in an orderly manner, restore only the previously verified safe build/config and previously validated database/object checkpoint if recovery requires it, check Temporal history and outbox at-least-once/once-only effects, artifact hashes and private reads, then preserve timestamped before/after receipts. A list of flags is a plan; **none of these actions was executed during this handoff.** Follow [the existing complete operator sequence](DAY10_NO_GO_OPERATOR_HANDOFF_2026-11-18.md).

## Source-only reproducibility, not live qualification

```bash
uv run python -m scripts.release_contract_check
uv run --extra coworker pytest -q tests/test_pilot_admission_verify.py tests/test_day10_release_decision.py tests/test_cohort_release_gate.py
uv run --extra coworker python -m scripts.ruke_pilot_eval validate-registry
```

**Authoritative references:** [original Day 10 tracker](https://github.com/rumman52/Shuddho/issues/736), [Day 1 governance](https://github.com/rumman52/Shuddho/issues/727), [Day 2 staging](https://github.com/rumman52/Shuddho/issues/728), [Day 9 evaluation](DAY9_PILOT_QUALIFICATION_2026-11-12.md), [Day 10 operator access](DAY10_PILOT_ACCESS_FULL_COHORT_2026-11-19.md), [controlled-cohort gate](../../docs/FINAL_CONTROLLED_COHORT_GATE.md), [Day 10 original CTO snapshot](DAY10_CTO_HANDOFF_2026-11-17.md).

**CTO disposition: NO-GO.** Source improvement under review is not operational acceptance. An incoming operator must check the newest exact-head CI and live run receipts before updating this decision.
