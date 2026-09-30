# PA-10 bounded Daily/Weekly Coworker briefings

**Status: repository implementation slice; default-off with the existing automation/runtime release gates.**

This slice turns the existing PA-02 daily/weekly schedule into a bounded proactive Coworker briefing without creating another scheduler, adding delegated write authority, or treating connected provider content as instructions.

## User outcome

A user can attach a **private briefing** profile to an active persistent goal and choose a daily or selected-weekday schedule. At each accepted due occurrence Shuddho creates exactly one bounded Agent Runtime v3 run. The run is restricted to the existing `daily_plan.create` tool and may optionally read only connector grants the user explicitly selected.

The briefing result remains a private Coworker task/artifact. A generic completion notice tells the user that the briefing is ready to review in Shuddho.

## Authority boundary

The profile reuses existing authority instead of inventing a new one:

- Temporal Schedule remains the only due-time authority for daily/weekly work.
- PostgreSQL remains the automation, occurrence, run and notification ledger.
- Persistent-goal owner/revision/state binding is rechecked by normal Agent admission.
- Optional connected context is limited to explicit owner-scoped `planner_context` read grants.
- Connector snapshots remain untrusted provider data and never grant tool or action permission.
- A briefing run has a persisted `tool_allowlist=["daily_plan.create"]`.
- Runtime v3 filters its visible tools by that allowlist and rechecks the allowlist again when admitting a model-selected step.
- No email send, calendar write, booking, purchase, payment, publishing, browser mutation, sandbox execution or ExternalAction is granted by the briefing profile.
- Existing consequential actions continue to require their own immutable preview and explicit approval.

## Admission contract

A briefing automation is accepted only when:

1. the normal automation, personal-goal and Agent Runtime gates are enabled;
2. the trigger is `daily` or `weekly`, never a connector event;
3. Runtime v3, the bounded intelligent planner and Work Services are enabled;
4. every optional connector grant belongs to the owner, is active and unexpired, and is scoped to `agent_context -> planner_context`;
5. every selected connector grant has an active/pending/renewing provider event subscription; and
6. the selected source count is at most four.

A normal goal automation cannot attach connector grants through this path. This keeps connected context specific to the reviewed briefing contract rather than silently widening every scheduled Agent run.

## Durable state and recovery

Migration 0040 adds:

- `cw_agent_runs.tool_allowlist` — the exact non-consequential tool scope frozen onto the run;
- `cw_automations.run_profile` — `goal` or `briefing`;
- `cw_automations.connector_read_grant_ids` — the explicit connected-read scope for the briefing.

The existing automation occurrence key remains owner + automation + revision + canonical UTC due instant. Duplicate Temporal delivery therefore reuses the same occurrence/run. `BUFFER_ONE` and stale-accepting recovery continue through the existing PA-02 path.

A process loss after occurrence admission does not expand authority: replay reconstructs the same automation revision, same persistent goal revision, same connector grant set and same tool allowlist.

## Notifications

The existing start notification remains deduplicated by occurrence. Briefing starts use generic copy.

After the Agent run reaches verified completion, a deterministic completion-notice ID is derived from the occurrence and run. Repeated completion handling therefore produces one `automation_completed` notice. The notice contains no email/calendar body or provider text, observes the automation quiet-hours policy and uses the same `automation_updates_enabled` consent as scheduled-work start notices.

Browser Push, when separately qualified and consented, can only mirror the already-delivered generic in-app notice under its existing PA-10 contract.

## Rollback

No new production flag is introduced. Rollback uses the existing boundaries:

- `SHUDDHO_AUTOMATIONS_ENABLED=false` stops new automation admission and reconciles schedules off;
- Runtime-v3 / planner / Work Services gates independently prevent briefing admission;
- connector-read revocation causes a selected connected source to fail closed before a new occurrence can start;
- changing an automation or goal revision causes stale occurrences to fail closed.

Existing completed runs, artifacts and receipts remain inspectable.

## Qualification boundary

Repository tests and CI prove only the implemented contracts. Controlled staging still must exercise:

- daily and weekly schedules across timezone/DST cases;
- app closure and worker restart;
- duplicate occurrence recovery;
- optional Gmail/Calendar read context and revocation races;
- exact daily-plan-only runtime tool exposure;
- quiet-hours delivery and completion-notice dedupe;
- Browser Push only when separately enabled/qualified; and
- rollback without provider writes or duplicated work.

No live provider, controlled-staging or production qualification is claimed by merging this slice.
