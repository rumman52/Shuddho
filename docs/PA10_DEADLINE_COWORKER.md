# PA-10 bounded Deadline Coworker

**Status: repository implementation slice stacked after Email Coworker; default-off behind existing automation/runtime/planner/context/work-service gates.**

## Outcome

Deadline Coworker reuses an existing reviewed daily/weekly Temporal automation. At each scan it revalidates the owner, automation, active goal and exact goal revision. It selects the earliest active goal or incomplete-milestone deadline and admits a bounded recovery-plan run only after that target enters one of four meaningful urgency bands: 7 days, 72 hours, 24 hours, or overdue.

Repeated scans inside the same unchanged band reuse the same deterministic occurrence identity and do not create another run or notification. A new run is allowed only when the urgency band or reviewed goal revision meaningfully changes.

## Work performed

The bounded Runtime v3 run receives:
- the reviewed goal objective;
- current milestone completion metadata;
- exact target deadline and urgency band;
- still-owned goal documents.

The run is restricted to `daily_plan.create` and prepares a prioritized recovery plan. It receives no ExternalAction IDs and no connector-write authority.

## Safety

- paused/cancelled/stale goals fail closed;
- stale automation revisions fail closed;
- goal revision changes require the existing automation review boundary;
- no send, publish, booking, purchase, payment or calendar mutation is granted;
- provider/context permissions are not expanded;
- existing quiet hours and notification consent are reused.

## Dedupe identity

The deadline occurrence key is derived from owner + automation + automation revision + goal revision + target kind/label + canonical deadline + urgency band.

This makes unchanged daily scans inert while allowing a new bounded run after a meaningful threshold transition.

## Qualification boundary

Repository tests validate deterministic threshold selection, dedupe, escalation, paused-goal suppression, exact Runtime-v3 tool scope and completion-notice dedupe.

Controlled staging still must verify timezone/DST schedules, app/worker restart, edited deadlines after user review, overdue goals, milestone completion changes, quiet hours, Browser Push and rollback. Repository CI does not establish staging or production qualification.
