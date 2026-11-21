# Days 7–8 foundational readiness and evidence boundary (22 November 2026)

Source of truth: Rukh AI Part 04 (Days 7–8); GitHub #733, #734, #584; Linear MD-8.

## What this branch proves

- `services/coworker/day8_telemetry.py` accepts only the existing fixed, redacted operational event schema when all opt-in policy gates pass.
- Sink rejection (`False`) and an unawaited asynchronous sink do **not** produce a positive handoff result. Sink exceptions remain isolated from the agent run; the default remains disabled.
- The regression tests are **source-only**. A synchronous sink accepting an event is not evidence that PostHog persisted it, and neither test fixtures nor a matching approval hash substitute for a human-signed decision.

## Read-only staging findings

At the time of this source review, the connected `shuddho-staging` Supabase project was healthy, but its coworker `accounts`, `personal_goals`, `automations`, `automation_occurrences`, `agent_runs`, and `notifications` tables each reported **zero rows**. These observations do not prove a natural Temporal firing, an owner delivery, or Day 8 usage receipts. The performance advisor reported informational unindexed foreign keys without query-plan proof of a hot path; no speculative migration was applied.

The existing Linear MD-8 record states that an approved Rukh PostHog destination and Founder/C privacy approval are missing, and that a dedicated staging Temporal worker has not been verified. Therefore **all operated Day 7 / Day 8 exits remain blocked**; do not infer completion from this PR.

## Operator-controlled work needed to graduate the release

1. After preceding private-staging acceptance, obtain the dated owner-approved synthetic account, goal, project documents, profile, local time zone, quiet hours, expiry, catch-up bound, destination and Temporal queue/worker revision. Preserve authenticated same-release API and worker readbacks.
2. Observe the **first natural scheduled firing** on one local date, including independent Temporal history, occurrence, run, immutable document pins and one confirmed owner completion delivery. Capture actual local date and UTC offset.
3. Change exactly one authorized source after the first verification; retain old/new pins and the source-edit audit evidence. Observe the **second natural scheduled firing** on the next local date with the revised source exactly once. Pause and observe a subsequent due opportunity through its catch-up window; ensure zero admissions/deliveries. Use controlled tests only for replay, restart, expiry, deletion, quiet hours and missed events.
4. Run `uv run --locked --extra coworker python -m scripts.staging_day7_two_day_gate --first "$FIRST" --second "$SECOND" --pause "$PAUSE" --output "$DAY7_REPORT"` with operator-authenticated receipts. Its shape validator explicitly **cannot authenticate natural timer provenance or transport delivery**; corroborating Temporal and delivery logs are mandatory.
5. Get a dated Founder/C PostHog decision naming the intended project, region, retention, consent, destination hosts, permitted event keys and kill switch (or an explicit allowed disabled decision). Verify denial causes zero transmissions before any approved staging delivery is attempted.
6. Freeze the 40-case development manifest (10 cases per research/report-email × Bangla/English cell). Execute **80 first runs** across the baseline and bounded arms with the same model, tools, source, task and budget; retain provider receipts, actual input/output usage, retries and failed attempts, latency and artifact hashes. Independently review all attempts. No missing usage is treated as zero.
7. Compute acceptance and all-in cost per accepted output. Each eligible arm needs ≥36/40 accepted, ≥9/10 per cell, complete measurements and safety passes; bounded context must not lose a baseline-accepted case. Enforce the approved latency/cost policy. Freeze only the least-cost *eligible* profile; block if none qualify. Keep Day 9 holdout isolated.
8. On the exact release candidate, run `uv run --locked --extra coworker pytest -q tests/test_automations.py tests/test_coworker_temporal.py tests/test_staging_day7_two_day_gate.py tests/test_day8_telemetry_privacy.py tests/test_core_agent_observability.py tests/test_task_economics_evidence.py`. Preserve exact-head CI and independent review before merging or changing any release tracker.

No schema, hosted services, budgets, secret settings, privacy settings, delivery destinations or worker schedules are changed by this branch.
