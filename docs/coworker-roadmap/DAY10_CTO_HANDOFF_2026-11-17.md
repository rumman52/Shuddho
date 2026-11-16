# Rukh AI Day 10 CTO handoff — 17 November 2026 (Asia/Dhaka)

## Executive decision

**Disposition: SOURCE_ONLY / NO-GO.** No controlled pilot is authorized, no candidate release is frozen, and no production activation is permitted.

This is an evidence handoff, not a claim that the ten-day programme is operationally complete. Source validators and automated tests do not replace live staging operations, independent holdout custody, actual rollback/recovery receipts, or authentic owner approvals.

## Exact repository identity

- Repository: `rumman52/Shuddho`
- Default branch observed: `main`
- Main SHA at this snapshot: `8f92814ab5f25d1214596d63213824c7ba577a93`
- Source provider default in README: `SHUDDHO_LLM_PROVIDER=deepseek`, `DEEPSEEK_MODEL=deepseek-flash`; explicit Gemma rollback remains supported. This is source configuration, not a live API/worker model readback or frozen release identity.
- Day 10 tracker: [issue #736](https://github.com/rumman52/Shuddho/issues/736)
- Day 4 tracker: [issue #730](https://github.com/rumman52/Shuddho/issues/730)
- Previous Day 4 PR #726 is **closed without merging**. Its aggregate UTF-8 snapshot-budget fix is absent from this main SHA; [PR #746](https://github.com/rumman52/Shuddho/pull/746) re-applies it on current main.
- [PR #748](https://github.com/rumman52/Shuddho/pull/748) hardens the Day 10 operated-receipt validators. Both are draft and must receive independent review before merge.

### Current source branches

| Work | Exact head | State at handoff |
| --- | --- | --- |
| PR #746 — reviewed brief UTF-8 budget | `540f6a9ef46077a5764bf221dc3b9c648d087ea1` | Draft; corrected-head CI run #43946993548 in progress |
| PR #748 — Day 10 operated receipt contracts | `ee04e512254a5eecc7a0aac84e9fef58eb975a68` | Draft; latest corrected-head CI run #43949295652 in progress after synthetic-owner proof was added |

Other open work already exists and must not be duplicated: PR #741 (staging preflight), #742 (Day 5 memory isolation), #744 (Day 3 grounded replies), and #747 (Day 7 project-bound briefings). Refresh their exact heads and CI before depending on them.

## Main CI and governance

Main CI run [#43939411068](https://github.com/rumman52/Shuddho/actions/runs/43939411068) completed on the observed main SHA:

| Check | Result |
| --- | --- |
| test-and-build | success |
| Frontend tests and builds | success |
| coworker | success |
| browser-qualification | success |
| PostgreSQL 18 staging compatibility | success |
| governance-audit | failure |
| ci-merge-gate | failure |

The governance audit fails because the GitHub App client ID input is missing. Configure these values directly in GitHub Actions environments—never in chat or repository files:

- Environment variable: `V01_RULESET_APP_CLIENT_ID`
- Environment secret: `V01_RULESET_APP_PRIVATE_KEY`
- Required environments: `v01-governance` and `pa10-staging`

The native ruleset `27324410` is active and has no bypass actors, but its live readback is materially weaker than the checked-in `infra/github/main-ruleset.json` policy: `required_approving_review_count=0`, stale-review dismissal is false, last-push approval is false, review-thread resolution is false, and no required status-check rule is configured. The checked-in policy specifies one approval, stale-review dismissal, last-push approval, resolved review threads, and required CI checks. The material PR author must not be the sole reviewer. Do not self-approve or merge these changes. `scripts/apply_main_ruleset.py` refuses to replace an existing non-compliant active ruleset and directs the operator to manual reconciliation; do not blindly invoke a create/apply path.

## Staging readback

### Supabase

Fresh read-only checks on 17 November 2026:

- Project: `shuddho-staging` (`bsmbvjenpvcyfjzwtuax`), `ACTIVE_HEALTHY`, PostgreSQL 17.11.
- Private application schema: `shuddho_coworker`, 84 tables, Alembic revision `0070`.
- `cw_accounts=0`, `cw_conversations=0`, `cw_agent_runs=0`, `cw_artifacts=0`, `auth.users=0`, and `storage.objects=0`.
- Private bucket `shuddho-coworker-staging` exists with `public=false`.
- Security advisor: no security lints.
- All 84 private-schema tables report RLS disabled. However, live privilege checks found no `USAGE` on `shuddho_coworker` for `anon` or `authenticated`, and no table DML/SELECT privileges for those roles. This is not evidence of current anon/auth API access. Revalidate the actual runtime-role grants and exposed-schema configuration before any RLS change; do not apply blanket RLS without policies.
- Performance advisor: 32 informational unindexed-FK findings, 205 unused-index findings and one duplicate-index warning. No indexes were changed. Use workload/query-plan evidence before optimizing.

The database being healthy and migrated does not prove a working API/worker/Temporal/object-storage execution path.

### Render

No Render workspace was selected in this session. The only available workspace is named `Rumman`; a read-only inspection is pending explicit workspace confirmation.

The last repository-linked Render readback is from issue #291 on 16 November 2026, so it is historical, not a fresh 17 November verification. It reported no persistent `shuddho-worker-staging`, no Render PostgreSQL instance, an older `shuddho-api-staging` deployment behind main, and missing Temporal/S3 credentials. Refresh those facts after workspace selection.

The recorded owner budget boundary does **not** authorize a paid worker. Do not run the PROVISION workflow, sync a worker-creating Blueprint, or incur hosting/database charges without a separate explicit owner billing decision.

### Vercel

The connected Vercel account currently exposes only the `ali` project; no Shuddho project/deployment was identified. A GitHub Vercel preview status is not proof of an operated API/worker release.

## Day 10 exit-gate matrix

| Workbook task | Current evidence | Disposition |
| --- | --- | --- |
| 1. Final-head defects and checks | Main code checks pass; governance and merge gate fail. Day 4 budget fix is in PR #746. | **Not complete** |
| 2. Freeze API/worker/schema/model and all 43 flags | Freeze tooling exists; no operated exact API/worker readbacks or release manifest. | **Not complete** |
| 3. Live planner and curated-quality gates | No final-release live reports. | **Not run** |
| 4. Independent holdout and 20/20 recovery | Independent D custody is absent; no release-bound operated recovery receipts. | **Not complete** |
| 5. Rollback | PR #748 hardens the receipt validator; no actual candidate rollback/worker-stop/restore receipt. | **Source change in review; operation not done** |
| 6. Cancellation and paused schedule | PR #748 requires inference-time cancellation, late-result fencing, next-due observation and zero admissions; no live operation receipts. | **Source change in review; operation not done** |
| 7. Two-owner isolation and golden scenario | PR #748 requires both directions across documents, memory, artifacts and activity; no live synthetic-owner run or final golden artifact. | **Source change in review; operation not done** |
| 8. Founder and Owner-C approvals | No authentic, separate approvals bound to a frozen release. | **Blocked external** |
| 9. Controlled 5–10-user pilot | No GO decision and no manual allowlist action. | **Not authorized** |
| 10. CTO handoff | This document records known identity, CI, staging readback, blockers and next actions. Cost/latency, exact worker/model identity, operated receipts and controlled on-call contacts remain unavailable. | **Partial handoff** |

## Ranked next actions

1. Configure the GitHub App client ID/private key in both required GitHub environments; rerun main governance audit. Then have an authorized administrator manually reconcile live ruleset 27324410 against `infra/github/main-ruleset.json` (one approval, stale-review dismissal, last-push approval, thread resolution and required checks), and verify negative/positive merge-control tests. The current apply script intentionally refuses to overwrite a non-compliant active ruleset.
2. Confirm the `Rumman` Render workspace for read-only inspection. Verify current service/deployment identities, worker inventory, health and logs. Do not provision anything.
3. Obtain a fresh owner billing decision before any paid worker or hosting change. Secure Temporal and S3 credentials in their approved secret stores; do not paste them into issues or chat.
4. Establish approved synthetic Auth identities, selected private documents and a real Temporal schedule. Operate API/worker pairing, storage access and natural schedule firings on a non-production candidate.
5. Freeze one exact API/worker/schema/model/rollout candidate, including all 43 boolean capability flags. Re-run exact-head CI and live planner/curated-quality gates on that identity.
6. Obtain independent holdout custody; collect 40 reviewed outcomes and 20 release-bound operated recovery receipts.
7. Operate rollback, cancellation during inference, paused-schedule due-time observation, two-owner isolation and a final multi-turn golden run. Use actual receipts, not hand-edited evidence.
8. Obtain separate authentic Founder and Owner-C approvals against the same release ID and manifest digest.
9. Only after the canonical GO and every Day 10 gate pass may a separate operator manually admit 5–10 allowlisted users. No general launch is implied.

## Known limitations and safe-state guidance

- No exact API/worker release pair, image digest, schema/model freeze or 43-flag readback is established.
- No live cost/latency scorecard or operated 99.9% availability measurement exists.
- PostHog telemetry remains subject to explicit privacy-scope approval; do not enable it by assumption.
- No independent holdout, recovery, rollback, cancellation, paused-schedule, owner-isolation or final golden-run evidence is attached.
- The current staging database is empty of application accounts/runs/artifacts. No data-retrieval or restore drill is proven by that fact.
- Human contact details belong in a separately controlled on-call document, not this repository handoff or public issue comments.
- Keep production/high-authority flags off. Do not claim a known-safe deployment identity until the selected Render workspace and current service are verified.

**CTO disposition: NO-GO.** This handoff does not authorize deployment, paid provisioning, telemetry, external sends, mutating connectors, or pilot admission.
