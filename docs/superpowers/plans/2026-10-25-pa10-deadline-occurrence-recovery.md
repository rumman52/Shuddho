# PA-10 deadline occurrence recovery — implementation and verification record

**Issue:** [#566](https://github.com/rumman52/Shuddho/issues/566)  
**PR:** [#568](https://github.com/rumman52/Shuddho/pull/568)  
**Current main:** `79d4e59a69350b3af9d7404102e285fd606fb04d`  
**PR head:** `3778511b9fb1e6415820280ff27cb5bf94a64ffd`

## Goal and architecture

Make deadline automation occurrences safely recoverable after transient admission failures and worker restarts without allowing stale or ineligible work to start. Reuse the durable `AutomationOccurrence` ledger, stable deadline key, shared narrow admission-error recorder, and AgentRun idempotency boundary. No schema migration or provider/credential change was made.

## Implementation completed

- Resolve a pending occurrence before eligibility/target early returns can strand it in `accepting`.
- Retry only an existing `accepting` occurrence; accepted/blocked/skipped/buffered states remain terminal.
- Treat only `active_agent_limit` with HTTP 429 as retryable; other admission errors remain terminal.
- Revalidate automation revision/state/expiry, goal state/revision, deadline target, authority and bounded catch-up before admission.
- Reuse the original occurrence identity and deterministic AgentRun idempotency key, including recovery after AgentRun creation but before occurrence/notification commit.
- Preserve temporary overlap deferral rather than terminalizing work solely because another run is active.

## Regression coverage and verification

- Eight deadline-recovery regression tests cover transient capacity failure across a fresh Container, permanent admission failure, expired catch-up, target removal, goal revision change/pause, automation pause, duplicate run/notification prevention, and process loss after AgentRun creation.
- The focused mandatory deadline-recovery CI gate passed with the JUnit/no-skips check.
- Exact PR-head [run #40192139821](https://github.com/rumman52/Shuddho/actions/runs/40192139821) completed `test-and-build=success` and `coworker=success`. The full “Test accounts, real exports, PostgreSQL races, and Temporal recovery” step passed.
- The same run's `ci-merge-gate` failed at **Require independent current-head review**. PR #568 had zero submitted reviews.
- PR #568 merged at **16:08:07 UTC** while a later exact-head run [#40210212873](https://github.com/rumman52/Shuddho/actions/runs/40210212873) was still running the full coworker integration step. Merged-main run [#40210229328](https://github.com/rumman52/Shuddho/actions/runs/40210229328) has `test-and-build=success`, `governance-audit=failure`, and `coworker=in_progress` at this refresh. Recheck that run before claiming final merged-main verification.

## Post-merge review and release disposition

The implementation was merged without the independent-review/native-protection gate required by this plan. This is recorded in [V-01 issue #484](https://github.com/rumman52/Shuddho/issues/484); do not represent this plan as having satisfied pre-merge review.

Render automatically deployed merge commit `79d4e59a69350b3af9d7404102e285fd606fb04d` to production deploy `dep-dbf2iqdg1s2s739ss2j0`, which Render reports LIVE. No deployment setting was changed as part of the implementation. Error/5xx logs were empty in the inspected window, but HTTP request/latency metrics were empty and no HTTP health-check path is configured, so end-to-end health remains unverified.

**PA-10 deadline occurrence recovery is implemented and merged; full PA-10 controlled-staging qualification and production readiness remain incomplete.** Native merge enforcement, fail-closed production deployment control, the persistent staging worker, active Supabase staging, required secrets/provider/device prerequisites, and frozen staging evidence remain external blockers. No production activation is authorized.
