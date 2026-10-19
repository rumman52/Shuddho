# A-03 migration compatibility and retained-evidence rollback inventory

Source reviewed: main `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`, 20 October 2026 (Asia/Dhaka).
This is a 62-revision source inventory and bounded architecture decision review. It is not evidence that an arbitrary older binary can read the current database or replay old Temporal histories. The separate proposed C-01/C-04/P-01 repairs are PRs [491](https://github.com/rumman52/Shuddho/pull/491), [492](https://github.com/rumman52/Shuddho/pull/492), and [493](https://github.com/rumman52/Shuddho/pull/493); they are not treated as merged here.

## Reviewed architecture boundaries

| Acceptance row | Reviewed authority and interfaces | Verdict and missing evidence |
| --- | --- | --- |
| A-01 | PostgreSQL records own accounts, runs, task/action links, approvals, receipts and source identity; Temporal histories carry IDs/status. `AgentRepository._run`, owned task/artifact accessors, conversation source admission, PermissionGateway and CredentialBroker enforce deterministic ownership. | Contracts specified in the reviewed interfaces. Operated owner/purpose isolation, deletion and credential-boundary security review remain open. |
| A-02 | Versioned Temporal workflows perform I/O in activities; existing outboxes and durable worker claims precede dispatch. Action claims and read-only reconciliation retain uncertainty after possible provider application. | Contracts specified; complete sixteen-case staging/provider observations and operated restart recovery remain open. |
| A-03 | Upgrade-only release entry point; retained schema and workflow registrations; selected/pinned skill publication and explicit worker drain. Inventory below covers every migration file at the reviewed SHA. | Documentation gap addressed by this inventory. Exact old-reader pairs, archived-history corpus/replay, and operated rollback/restore remain unverified. |
| A-04 | Code-owned ToolSpec, current persisted grants, exact approval/source/review/expiry binding, selected publication identity and compatible fleet checks at claim/use. | Contracts specified for the existing bounded scope. Real isolation/revocation and mixed-worker/drain/rollback evidence remain open; unsupported private sandbox input mounts remain denied. |

This independent AI review found no new contradiction in the cited A-01/A-02/A-04 interfaces. It is not an exhaustive security audit, human sign-off, or proof of architecture completion.

## Existing supported rollback contract

The release entry point, [`services/coworker/migrate.py`](../../services/coworker/migrate.py), calls Alembic **upgrade to head**. It does not automatically call downgrade. Existing rules in [personal-agent architecture](../PERSONAL_AGENT_ARCHITECTURE.md), [flag rollback](../CONTROLLED_STAGING_FLAG_ROLLBACK.md), [cohort rollback completion](../CONTROLLED_COHORT_ROLLBACK_COMPLETION.md), and [reviewed-skill rollout](../CW11_TRUSTED_SKILL_ROLLOUT.md) govern this inventory:

1. Disable admission using the exact approved capability/cohort flag and retain the expanded schema. Keep required workflow types registered for accepted histories. A flag change is not evidence that work drained.
2. Inventory/drain active tasks, Agent runs, claims and outboxes; resolve uncertain provider outcomes through the existing read-only reconciliation path. Never clear a claim to retry a possible mutation.
3. For reviewed skills, use the declared compatible publication rollback target and current fleet guards. Do not reinterpret a task pinned to a rolled-back publication under a new identity. Follow the CW-11 legacy migration/drain procedure.
4. Code rollback is conditional on the exact candidate binary being compatible with retained schema, workflow histories and current worker registration/claim requirements. Keep compatible worker code if an older binary cannot satisfy those fences; a mixed old/new fleet is not presumed safe.
5. Manual Alembic downgrade is **not the supported operational rollback**. Do not remove accepted-run checkpoints, approvals, source bindings, publication/control history or worker claims. The presence of a downgrade function is not authorization or proof that using it preserves data. Destructive recovery on a disposable database is separate from rollback of retained user work.
6. Restore is a separate controlled procedure requiring current approved backup/restore evidence. Reconcile external actions after restore; database restoration does not undo external effects.

This consolidates existing rules; it does not add a new operator command, deployment action or approval exception.

## Per-migration inventory

The chain is linear `0001` through `0062` at this SHA. Each row links the actual source. The scope label follows that file's purpose; the operation summary records declared Alembic operations, including batch alterations. It does not certify data/constraint compatibility. Downgrade hazards name operation classes, not a claim that a downgrade was executed.

**Gate B**, required for every row: exact old/new API and worker binaries must be tested against the retained expanded PostgreSQL schema and representative owned records. No per-revision B result was produced in this review. **Gate H** additionally requires archived workflow-history replay/recovery when the row affects durable execution. **Gate W** requires worker/publication fence and mixed-version drain verification. All gate codes below are requirements, not PASS statuses.

| Revision / source | Upgrade scope and operation classes | Manual downgrade hazard | Required gate |
| --- | --- | --- | --- |
| [0001](../../services/coworker/migrations/versions/0001_coworker_accounts_documents_tasks_and_.py) | coworker accounts documents tasks and: create_index, create_table | drops persisted tables | B + H |
| [0002](../../services/coworker/migrations/versions/0002_approved_email_and_calendar_actions.py) | approved email and calendar actions: create_index, create_table | drops persisted tables | B + H |
| [0003](../../services/coworker/migrations/versions/0003_agent_runtime_foundation.py) | agent runtime foundation: create_index, create_table | drops persisted tables | B + H |
| [0004](../../services/coworker/migrations/versions/0004_agent_workflow_outbox.py) | agent workflow outbox: create_index, create_table | drops persisted tables | B + H |
| [0005](../../services/coworker/migrations/versions/0005_agent_action_bindings.py) | agent action bindings: add_column, create_index | drops retained columns/bindings | B + H |
| [0006](../../services/coworker/migrations/versions/0006_structured_agent_memory.py) | structured agent memory: add_column, create_index, create_table | drops persisted tables; drops retained columns/bindings | B + H |
| [0007](../../services/coworker/migrations/versions/0007_bounded_intelligent_planner.py) | bounded intelligent planner: add_column | drops retained columns/bindings | B + H |
| [0008](../../services/coworker/migrations/versions/0008_agent_step_handoffs.py) | agent step handoffs: add_column, create_index | drops retained columns/bindings | B + H |
| [0009](../../services/coworker/migrations/versions/0009_bounded_dependency_graph.py) | bounded dependency graph: add_column | drops retained columns/bindings | B + H |
| [0010](../../services/coworker/migrations/versions/0010_provider_capacity_leases.py) | provider capacity leases: create_index, create_table | drops persisted tables | B + H |
| [0011](../../services/coworker/migrations/versions/0011_provider_daily_budget.py) | provider daily budget: create_table | drops persisted tables | B + H |
| [0012](../../services/coworker/migrations/versions/0012_oauth_provider_binding.py) | oauth provider binding: add_column | drops retained columns/bindings | B + H |
| [0013](../../services/coworker/migrations/versions/0013_agent_action_proposals.py) | agent action proposals: create_index, create_table | drops persisted tables | B + H |
| [0014](../../services/coworker/migrations/versions/0014_owned_action_recipients.py) | owned action recipients: create_index, create_table | drops persisted tables | B + H |
| [0015](../../services/coworker/migrations/versions/0015_personal_goals.py) | personal goals: add_column, create_index, create_table | drops persisted tables; drops retained columns/bindings | B + H |
| [0016](../../services/coworker/migrations/versions/0016_automations_notifications.py) | automations notifications: create_index, create_table | drops persisted tables | B + H |
| [0017](../../services/coworker/migrations/versions/0017_agent_runtime_v3.py) | agent runtime v3: add_column, create_index, create_table | drops persisted tables; drops retained columns/bindings | B + H + W |
| [0018](../../services/coworker/migrations/versions/0018_context_memory.py) | context memory: create_index, create_table | drops persisted tables | B + H |
| [0019](../../services/coworker/migrations/versions/0019_trust_boundary.py) | trust boundary: create_index, create_table | drops persisted tables | B + H |
| [0020](../../services/coworker/migrations/versions/0020_connected_reads.py) | connected reads: add_column, create_index, create_table | drops persisted tables; drops retained columns/bindings | B + H |
| [0021](../../services/coworker/migrations/versions/0021_connector_events.py) | connector events: create_index, create_table | drops persisted tables | B + H |
| [0022](../../services/coworker/migrations/versions/0022_connector_cursor_text.py) | connector cursor text: alter_column, batch_alter_table | alters/narrows column contract | B + H |
| [0023](../../services/coworker/migrations/versions/0023_browser_sessions.py) | browser sessions: create_index, create_table | drops persisted tables | B + H |
| [0024](../../services/coworker/migrations/versions/0024_browser_worker_leases.py) | browser worker leases: add_column, create_index | drops retained columns/bindings | B + H + W |
| [0025](../../services/coworker/migrations/versions/0025_browser_session_continuity.py) | browser session continuity: add_column | drops retained columns/bindings | B + H |
| [0026](../../services/coworker/migrations/versions/0026_browser_takeover_secrets.py) | browser takeover secrets: add_column | drops retained columns/bindings | B + H |
| [0027](../../services/coworker/migrations/versions/0027_browser_takeover_frames.py) | browser takeover frames: add_column | drops retained columns/bindings | B + H |
| [0028](../../services/coworker/migrations/versions/0028_browser_takeover_interaction.py) | browser takeover interaction: add_column | drops retained columns/bindings | B + H |
| [0029](../../services/coworker/migrations/versions/0029_browser_takeover_worker_affinity.py) | browser takeover worker affinity: add_column, create_index | drops retained columns/bindings | B + H + W |
| [0030](../../services/coworker/migrations/versions/0030_sandbox_control_plane.py) | sandbox control plane: create_index, create_table | drops persisted tables | B + H |
| [0031](../../services/coworker/migrations/versions/0031_sandbox_worker_leases.py) | sandbox worker leases: add_column, create_index | drops retained columns/bindings | B + H + W |
| [0032](../../services/coworker/migrations/versions/0032_sandbox_artifact_metadata.py) | sandbox artifact metadata: add_column, alter_column, batch_alter_table, create_foreign_key, create_index, create_unique_constraint | explicitly refused (expand-only); retain schema for application/flag rollback | B + H |
| [0033](../../services/coworker/migrations/versions/0033_negotiation_case_ledger.py) | negotiation case ledger: create_index, create_table | drops persisted tables | B + H |
| [0034](../../services/coworker/migrations/versions/0034_reviewable_negotiation_proposals.py) | reviewable negotiation proposals: create_index, create_table | drops persisted tables | B + H |
| [0035](../../services/coworker/migrations/versions/0035_negotiation_proposal_promotion.py) | negotiation proposal promotion: add_column, batch_alter_table, create_foreign_key, create_index, create_unique_constraint | drops retained columns/bindings | B + H |
| [0036](../../services/coworker/migrations/versions/0036_notification_source_binding.py) | notification source binding: add_column, batch_alter_table, create_unique_constraint | drops retained columns/bindings | B + H |
| [0037](../../services/coworker/migrations/versions/0037_browser_push.py) | browser push: create_index, create_table | drops persisted tables | B + H |
| [0038](../../services/coworker/migrations/versions/0038_browser_push_hardening.py) | browser push hardening: create_index | removes index/constraint contract | B + H |
| [0039](../../services/coworker/migrations/versions/0039_event_automation_occurrence.py) | event automation occurrence: add_column, batch_alter_table, create_foreign_key, create_index | explicitly refused (expand-only); retain schema for application/flag rollback | B + H |
| [0040](../../services/coworker/migrations/versions/0040_proactive_briefings.py) | proactive briefings: add_column | drops retained columns/bindings | B + H |
| [0041](../../services/coworker/migrations/versions/0041_meeting_coworker.py) | meeting coworker: add_column, batch_alter_table, create_foreign_key, create_index | explicitly refused (expand-only); retain schema for application/flag rollback | B + H |
| [0042](../../services/coworker/migrations/versions/0042_email_coworker.py) | email coworker: add_column | explicitly refused (expand-only); retain schema for application/flag rollback | B + H |
| [0043](../../services/coworker/migrations/versions/0043_goal_driven_proactivity.py) | goal driven proactivity: add_column | explicitly refused (expand-only); retain schema for application/flag rollback | B + H |
| [0044](../../services/coworker/migrations/versions/0044_generic_transaction_domain.py) | generic transaction domain: create_index, create_table | drops persisted tables | B + H |
| [0045](../../services/coworker/migrations/versions/0045_transaction_terms_quote_freshness.py) | transaction terms quote freshness: add_column, batch_alter_table, create_check_constraint, create_index, create_table | drops persisted tables; drops retained columns/bindings | B + H |
| [0046](../../services/coworker/migrations/versions/0046_transaction_reconciliation.py) | transaction reconciliation: add_column, batch_alter_table, create_check_constraint, create_index, create_table, create_unique_constraint | drops persisted tables; drops retained columns/bindings | B + H |
| [0047](../../services/coworker/migrations/versions/0047_restaurant_reservation_intents.py) | restaurant reservation intents: create_index, create_table | drops persisted tables | B + H |
| [0048](../../services/coworker/migrations/versions/0048_travel_quote_intents.py) | travel quote intents: create_index, create_table | drops persisted tables | B + H |
| [0049](../../services/coworker/migrations/versions/0049_travel_quote_verifications.py) | travel quote verifications: create_index, create_table | drops persisted tables | B + H |
| [0050](../../services/coworker/migrations/versions/0050_shopping_cart_intents.py) | shopping cart intents: create_index, create_table | drops persisted tables | B + H |
| [0051](../../services/coworker/migrations/versions/0051_shopping_cart_verifications.py) | shopping cart verifications: create_index, create_table | drops persisted tables | B + H |
| [0052](../../services/coworker/migrations/versions/0052_shopping_checkout_bindings.py) | shopping checkout bindings: create_index, create_table | drops persisted tables | B + H |
| [0053](../../services/coworker/migrations/versions/0053_travel_booking_bindings.py) | travel booking bindings: create_index, create_table | drops persisted tables | B + H |
| [0054](../../services/coworker/migrations/versions/0054_agent_execution_checkpoints.py) | agent execution checkpoints: create_index, create_table | drops persisted tables | B + H |
| [0055](../../services/coworker/migrations/versions/0055_coworker_conversations.py) | coworker conversations: create_index, create_table | drops persisted tables | B + H |
| [0056](../../services/coworker/migrations/versions/0056_agent_code_proposals.py) | agent code proposals: create_index, create_table | drops persisted tables | B + H + W |
| [0057](../../services/coworker/migrations/versions/0057_agent_code_review_decisions.py) | agent code review decisions: create_index, create_table | drops persisted tables | B + H + W |
| [0058](../../services/coworker/migrations/versions/0058_sandbox_code_proposal_binding.py) | sandbox code proposal binding: add_column, batch_alter_table, create_index | drops retained columns/bindings | B + H + W |
| [0059](../../services/coworker/migrations/versions/0059_reviewed_skill_registry_and_worker_inventory.py) | reviewed skill registry and worker inventory: create_index, create_table | drops persisted tables | B + H + W |
| [0060](../../services/coworker/migrations/versions/0060_reviewed_skill_registry_control_events.py) | reviewed skill registry control events: create_index, create_table | drops persisted tables | B + H + W |
| [0061](../../services/coworker/migrations/versions/0061_worker_registration_revision_guard.py) | worker registration revision guard: execute | removes SQL registration guard | B + H + W |
| [0062](../../services/coworker/migrations/versions/0062_worker_dispatch_claims.py) | worker dispatch claims: create_index, create_table | drops persisted tables | B + H + W |

## Compatibility boundaries requiring explicit qualification

- **0017 / Agent v3:** a new workflow identity does not establish old-history replay. Keep v1/v2/v3 definitions and matching activities; current-workflow synthetic integration is a different evidence level.
- **0022 / cursor text:** inspect the declared type conversion with realistic long provider cursors. A narrower old reader or manual type downgrade is not presumed lossless.
- **0032, 0035, 0036, 0039, 0041, 0045, 0046, 0058:** batch/FK/unique/check additions require populated PostgreSQL migration and old-writer verification. SQLite table recreation tests do not prove old PostgreSQL readers/writers.
- **0054–0055:** deleting execution checkpoints or conversation/message identity can destroy replay or ownership/continuity evidence. Preserve their rows through application rollback.
- **0056–0058:** retain immutable proposals, human review decisions and the sandbox execution/proposal binding. Do not re-enable generated execution beside a worker that does not enforce the review binding.
- **0059–0060:** retain publication selections, worker inventory and append-only registry control events. Use publication rollback/drain controls; deleting these tables loses the decision trail.
- **0061:** PostgreSQL worker insertion requires transaction-local `shuddho.worker_source_revision` matching the row. Legacy code may be denied restart/registration. Do not remove this trigger to make an incompatible rollback appear healthy; retain compatible worker code and qualify the availability/recovery consequence.
- **0062:** retain durable worker claims until exact drain/reconciliation is proven. Dropping the table can make in-flight work disappear from the drain evidence.

## Evidence map and next executable gates

Existing regressions to reuse, without relabeling them as operated proof:

- `tests/test_coworker_postgres.py::test_migrations_use_private_schema_and_repeat_safely` checks fresh/repeated migrations, not every historical populated old-reader pair.
- `tests/test_coworker_temporal.py` covers current versioned workflow dispatch and runtime assignment. No archived-history replay corpus or Temporal Replayer suite was identified in this review.
- `tests/test_cw11_registry.py`, `tests/test_cw11_registry_postgres.py` cover selected/pinned registry/fleet/drain and legacy migration contracts.
- `tests/test_staging_flag_rollback.py`, `tests/test_cohort_rollback_completion.py` exercise existing collector/gate logic. Actual matching staging output is still required.

For a declared rollback candidate, the release owner must supply exact old/new API/worker revisions, schema head, feature/publication selections and rollout identity. Then:

1. Build a disposable PostgreSQL copy with representative retained work, including checkpoints, approvals, unknown external outcomes, reviewed code, publications, worker claims and source deletion markers. Record counts/bindings before/after forward upgrade and the exact prior binary's attempted reads/writes. Require no lost evidence or unauthorized dispatch.
2. Collect redacted archived histories for retained Agent v1/v2/v3 and research execution, including timers, signals, pending/retried activities, approval waits, cancellation and accepted-then-lost outcomes. Pair reviewed research database `Task.workflow_version=work_research_reviewed_v2` with its actual Temporal workflow type `shuddho_research_v1` (ResearchWorkflow); the database task-version fence is not a new Temporal type. Replay with each supported candidate worker; historical fixtures need exact producer identity and checksums.
3. Exercise actual drain, publication/flag rollback and safe restart against matching staged identities. Preserve existing fail-closed fences; capture an operator-reviewed artifact, not a fabricated PASS record.
4. Apply the existing rollback-completion/restore gates with fresh evidence. Keep unqualified capabilities disabled.

No production or staging mutation was performed. Current session preflight: `uv run python -m scripts.staging_prerequisite_preflight --output /tmp/shuddho-current-staging-preflight.json` reported `blocked_external: RENDER_API_KEY REQUIRED`. This is missing access in this session, not a diagnosis of remote service health.

**A-03 verdict:** inventory/documentation implemented for this finite source revision; old-reader compatibility, archived-history replay and operated rollback remain UNVERIFIED. All 17 A/C/P/V acceptance requirements remain in scope; no 100% architecture or production qualification is claimed.
