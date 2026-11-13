# Day 10 — exact-candidate release decision and controlled handoff

**Date:** 12 November 2026 (UTC+06:00)  
**Repository:** `rumman52/Shuddho`  
**Decision authority:** owner C and the founder. A, B and independent D provide evidence; CI and this script cannot substitute for authorization.  
**Initial decision:** **SOURCE_ONLY / NO-GO**. No pilot admission, production activation or deploy occurred as part of this source change.

**Current operated readback (12 November 2026):** Render `shuddho-staging-db` (`dpg-dav98hfpn0mc739mndvg-a`) is `suspended` by `billing` and expired 31 October 2026. `shuddho-api-staging` (`srv-dav98otg1s2s73cod4gg`) lists its last live deployment from `fce72760456bd8bb03524ce98127120c7ac3dfb9` (2 October 2026), not the current reviewed source. Only three web services appear in the Render workspace; **no persistent Shuddho staging worker**. Supabase `shuddho-staging` being healthy does not prove this Render database or worker are operational. These are read-only inventories, not restored databases or live runtime execution receipts.

## Scope and non-negotiable qualification

Existing `scripts/cohort_release_gate.py` remains the **canonical** `GO_CONTROLLED_COHORT` decision and keeps its existing 100% live planner pass-rate and 100% live curated-quality pass-rate/fact-recall thresholds (plus all previously defined infrastructure, feature, capability and rollback gates). `scripts/day10_release_decision.py` **adds** exact-release, operations and owner-signoff requirements; it never weakens or bypasses the canonical gate and never activates a pilot.

1. Freeze one immutable rollout manifest and its literal SHA-256; record a 40-character API source revision, worker source revision, image/build and deploy receipts, schema/migration readback and **all 43 runtime-v2 boolean capability keys (including disabled ones)**. The reviewed rollout and authenticated API manifest must both declare exactly `scripts/staging_release_freeze.py::RUNTIME_CAPABILITY_KEYS` with identical boolean values; omitted or extra false flags are not an acceptable runtime freeze. The v2 runtime manifest is read from authenticated staging/protected API; a source config is not a runtime receipt. For PA-10 staging use the existing `scripts/staging_release_freeze.py prepare` and `verify` contract, including its provider-policy plan, before relying on staging claims. A new source commit invalidates any earlier exact-head receipt.
2. Close defects and obtain actual GitHub final-head `test-and-build`, `frontend`, `coworker`, `browser-qualification`, `postgres-18-qualification`, `governance-audit` and `ci-merge-gate` success without skipped required checks. Confirm protected-main policy via native GitHub governance controls and independent review. Source test execution alone is not CI qualification.
3. Produce authenticated live `scripts/agent_eval.py --live --release-id ... --rollout ...` and `scripts/coworker_quality_eval.py --live --release-id ... --rollout ...` reports against the exact release/provider model; do not substitute offline calibration. The canonical gate consumes the resulting JSON, plus `scripts/staging_api_exercise.py` and the other existing required staging collectors/receipts for this rollout. Where `artifact_services=true`, require the existing `--artifact-quality-eval` report.
4. On that exact API/worker/schema/model release, actually demonstrate global/agent flag rollback, cancellation/no late side effects, paused schedule/no execution and two-owner isolation; preserve individual operated receipts. The `rollback` receipt must name the actual toggle and return-to-safe-state procedure. Run the integrated multi-turn golden case against the **final candidate**, not a nearby preview or source-only test. Record provider outcome, failures, latency/tokens/cost and the unmodified first-run Day 9 results in **different** artifacts/run IDs; the post-fix rerun must never overwrite the first run.
5. Independent human D obtains genuine access-excluded heldout custody and a negative access test. A repo-readable candidate fixture does **not** establish custody. Two human reviewers score 40 generated outcomes across the four required workflow/language cells (10 each); require **≥36/40 overall, ≥9/10 in each cell and both reviewers at least 7/8 on accepted cases**. Record real provider generation identity, artifacts, reviewed rubric, independent verdicts, a separately controlled D custody reference and an observed denied developer-read test. **Each of the 40 independent holdout cases must include an actual boolean `security_passed=true` result. One false, missing or non-boolean result is an absolute SOURCE_ONLY / NO-GO regardless of 39/40 or higher human acceptance; quality rejection does not waive the security requirement.** This is a shape check on D's externally controlled evidence, not independent authentication by the CLI. Separately complete **20/20 operated recovery scenarios** with individual receipts. Neither source-authored development calibration nor an offline generator test counts as human acceptance/recovery.
6. Only when the unchanged canonical gate is GO, all Day 10 receipts pass on the same candidate, and **founder+C give separate authentic written approval** may an operator manually admit **5–10 allowlisted users**. This script deliberately stops at `READY_FOR_OWNER_CONTROLLED_PILOT`: it does not change flags or add users. Otherwise report `STAGING_ONLY` only when *all* technical gates pass but authorization is missing; all other missing evidence reports `SOURCE_ONLY` with explicit blockers.

## Machine handoff (read-only; does not perform a rollout)

Create the rollout from `docs/cohort-rollout.template.json` in a secure location, **adjust `cohort.max_users` from its generic 25-user example to 5–10 and fill every capability named in `RUNTIME_CAPABILITY_KEYS`**; the generic template is not a ready-to-run Day 10 rollout. Then collect real JSON receipts in an access-controlled release directory. Every operated receipt for `--rollback`, `--cancellation`, `--paused-schedule`, `--owner-isolation`, `--worker`, and `--schema` must contain the actual `release_id`, `source_revision`, `rollout_manifest_sha256`, `status="passed"`, `evidence_ref` and timezone-aware `verified_at` for that release; the schema receipt additionally binds `migration_revision=api_revision=worker_revision`. Do not put credentials or sensitive data into receipts. Additional facts: rollback must list actual verified global/agent kill switches plus observed worker stop and restoration; cancellation requires a run ID and zero late side effects; paused schedule requires a schedule ID and zero executions while paused; owner isolation requires distinct synthetic owner references and an observed cross-owner denial. Each of the 20 recovery cases must have its *own* evidence reference. Final golden must identify the same provider model as the live planner. The independent D holdout must contain a release-bound `custody_receipt` with independently controlled access and a negative developer-read check (the CLI cannot itself authenticate that claim).

```bash
uv run --extra coworker python scripts/day10_release_decision.py \
  --rollout /secure/release/cohort-rollout.json \
  --source-revision "<final exact 40-character API/worker SHA>" \
  --api /secure/release/runtime-manifest-v2.json \
  --worker /secure/release/worker-deploy.json \
  --schema /secure/release/schema-readback.json \
  --ci /secure/release/final-head-ci.json \
  --rollback /secure/release/rollback.json \
  --cancellation /secure/release/cancellation.json \
  --paused-schedule /secure/release/paused-schedule.json \
  --owner-isolation /secure/release/owner-isolation.json \
  --golden /secure/release/final-golden-rerun.json \
  --day9-first-run /secure/release/day9-original-first-run.json \
  --holdout /secure/release/independent-D-holdout.json \
  --recovery /secure/release/operated-recovery.json \
  --staging /secure/release/staging-evidence.json \
  --model /secure/release/live-planner-eval.json \
  --quality /secure/release/live-curated-quality-eval.json \
  --approval /secure/release/founder-C-approval.json \
  --output /secure/release/day10-decision.json
```

When `artifact_services=true`, supply the separate `--artifact-quality` artifact. Omitting it causes the existing canonical gate to remain NO-GO. For source-only assessment, run with just `--rollout` and `--source-revision`; missing evidence is an explicit blocker and the process exits nonzero. The output preserves the original Day 9 score object and its file SHA-256 independently from the final golden run ID. **Do not use a manually edited JSON file as independent evidence:** owners must validate CI links, Render/Supabase readbacks, signed logs, independent D custody and reviewer identity in their source systems. A self-asserted file has no automatic authenticity.

## Rollback and support ownership

The operator must retain and test the rollout manifest's exact kill switches. Core fail-closed controls include `SHUDDHO_COWORKER_ENABLED=false`, `SHUDDHO_AGENT_RUNTIME_ENABLED=false`, `SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false`, `SHUDDHO_RESEARCH_SERVICES_ENABLED=false`, and `SHUDDHO_ACTIONS_ENABLED=false`; the staged PA-10 feature controls additionally include `SHUDDHO_AUTOMATIONS_ENABLED=false`, `SHUDDHO_AGENT_RUNTIME_V3_ENABLED=false`, `SHUDDHO_CONTEXT_RETRIEVAL_ENABLED=false`, `SHUDDHO_PERSONAL_GOALS_ENABLED=false`, `SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED=false`, `SHUDDHO_CONNECTOR_READS_ENABLED=false` and `SHUDDHO_BROWSER_PUSH_ENABLED=false`. Capability-specific switches (e.g. attachments, recipients, email threading, browser/sandbox) are mandatory whenever enabled by the reviewed rollout. Stop new admission, disable all relevant flags in the authenticated deployment configuration, confirm API and worker reload/readback, fence outstanding work, retain receipts and exercise the reviewed revert/deploy route. Flag changes without observed worker-side stop, ledger consistency, and recovery verification are not a rollback demonstration. Do not blindly write a database value or delete user data.

Owner C and founder jointly own **GO/NO-GO**, the allowlist, change control and kill decision. Owner A owns the exact frontend/API candidate, defects, CI and release manifest; B owns worker/Temporal, schema, cancellation, paused schedules and restoration; independent D owns access-excluded holdout and reviewer custody; C owns stage receipts, security/isolation, dashboards, on-call incident response and the final scorecard. Record named humans and pagers in a separately controlled on-call document, not invented placeholders.

## Scorecard / known limitations at source checkpoint

| Field | Verified now | Release requirement |
|---|---|---|
| Source code | Day 10 PR #675 merged on 12 Nov; new 13 Nov hardening checks complete runtime-v2 capability inventory | Independent review plus exact-head green |
| Final-head CI | On 13 Nov, `main` run `43390800435` at `2ce3012` had test-and-build, frontend, browser and PostgreSQL-18 successes; Coworker was still running and governance-audit **failed** due to missing protected-main control. All checks on a fresh final head remain required. | All seven checks successful on the exact final head, including governance |
| Exact API/worker/schema/model readbacks | **Not established** | Identical candidate and verified runtime receipts |
| Live planner / quality at existing thresholds | **Not established** | Both live, canonical gate PASS |
| Day 9 first-run results | **Not supplied** | Preserve original scores + artifact hash; never fabricate |
| Independent human holdout | **Not established** | ≥36/40 and ≥9/10 per cell, genuine D custody |
| 20 operated recovery cases | **Not established** | 20/20 passed on exact candidate |
| Golden multi-turn regression | **Not established** | Fresh exact-SHA, distinct from Day 9 first run |
| Rollback / cancellation / paused schedule / owner isolation | **Not established** | Four operated receipts |
| Founder+C pilot authorization | **Absent** | Separate verified decision, only 5–10 allowlisted users |
| Actual pilot | **Not enabled** | Only after all gates, owner-executed manual admission |

## Operational CI and preview distinction

The earlier Coworker Playwright regression waited for the `What are we working on?` heading, but the authenticated chat design deliberately hides the `cw-header` in conversation mode. The corrected browser test must assert the visible `#cw-conversation-message` and conversation layout after the Writing Assistant route switch. Do not suppress or skip the browser suite. PR #668's navigation link fix is already merged into main; separate PRs #678 and #679 merged the four-artifact recovery-test fixes, superseding closed-unmerged PR #680. The latest Coworker browser navigation or upload-path result must be verified on the fresh final head. Separately, Vercel reported its free-tier deployment quota (`api-deployments-free-per-day`, over 100/day); this is a provider limit, not evidence of an application build defect. Wait for quota availability or obtain independently authorized billing capacity; do not disable required checks or provision a paid service without approval.

## Ranked next backlog

**P0:** (1) Resolve Coworker browser CI and native protected-main governance, obtain real reviews and all exact-head checks. (2) Recover/replace staging PostgreSQL with backup and isolated restore proof, provision/verify a persistent isolated worker only after billing authorization, and read back real API/worker/schema versions. (3) Freeze the final manifest, repair runtime drift and collect genuine provider/Temporal/S3 evidence. (4) Establish independent D holdout access separation and replacement of already-exposed candidate tasks, then complete the 40 human reviews and 20 recovery scenarios. (5) Run final live planner/quality/golden and operated rollback/isolation drills and obtain formal C/founder go/no-go.

**P1:** Fill privacy-approved monitoring and alert dashboards for queue age, error rate, latency, cost, storage, failures; review support on-call and documentation; remediate observed quality regressions *without changing thresholds*; capture pilot feedback and revised regression evidence. **P2:** Plan wider cohorts only after a separately authorized monitored pilot with measured outcomes; do not infer general availability from a ten-day schedule.

This document and the handoff script are **source changes**, not proof that Day 10's operational release criteria have been achieved.

The release decision additionally checks that the canonical rollout cohort maximum is **5–10**, the authenticated API enforces membership and reports a matching cap, and the separate authorization cap equals the exact rollout cap. A not-yet-activated rollout may have zero configured members; the manual operator must validate the actual 5–10 account list at admission time.