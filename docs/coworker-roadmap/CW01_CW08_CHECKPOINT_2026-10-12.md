# CW-01–CW-08 engineering checkpoint — 12 October 2026

Baseline reviewed: `f88d703c2e21b485203d340cd84552ca124f14e7`
(merged PR #370, repository `rumman52/Shuddho`).

## Evidence levels

| Work | Implemented in repository / current branch | Still needed to pass task exit gate |
| --- | --- | --- |
| CW-01 transaction invariant repair | Mandatory simulated-transport test suite, duplicate binding, uncertainty and approval expiry safeguards on main | Review exact-head CI and keep provider activation disabled |
| CW-02 sixteen-fault qualification | Evidence-schema, file checksums and mandatory matrix tests on main | Execute each fault against controlled live PostgreSQL, Temporal, API, worker, storage and provider sandbox; independently verify dispatch/applied counters and revisions |
| CW-03 operated staging prerequisites | Existing preflight/release-freeze tooling | Confirm live Render worker, PostgreSQL, Temporal TLS, S3 credentials, synthetic identity, model, API and rollout; freeze identical release and attach evidence |
| CW-04 baseline workflow qualification | Existing scoped read/draft/goal/reminder/restore/rollback collectors | Execute and attach evidence against frozen staging identity, restart, permissions, backups, rollback |
| CW-05 durable conversations | Migration 0055, owner-scoped idempotent message API, deletion and erasure checks on main | Exact-head PostgreSQL race and migration CI; activation collector schema 33 is still reserved, not qualified |
| CW-06 dispatch & steering | This branch adds explicit message-to-run atomic admission, same-transaction Agent outbox and immutable link; revision-checked cancellation reuses existing Agent ledger and stops queued outbox | Qualify exact-head CI, concurrent PostgreSQL admission, worker restart/replay, task/action cancellation, context deletion races |
| CW-07 chat/activity | This branch adds typed client and private conversation UI with explicit work launch, separate cancellation, run-state polling and owned activity projection | Browser/session reconnect, a11y/load/e2e, complete interactive result/artifact experience |
| CW-08 workspace and memory | Main has owner-scoped source/hash/expiry revalidation; this branch invokes it in the Agent admission transaction and freezes exact version IDs | Persistent versioned workspace manifest, memory review/edit controls across conversations, revocation races and full context integration |

## Security and reliability contracts

- Persisting a chat message **does not** create a task or approve an ExternalAction.
- Only a server-qualified non-consequential `agent_run` route can be admitted; all actions, scheduled sends, purchases and transactions stay in their existing explicit approval workflows.
- Each explicit dispatch locks Account, Conversation and Message in one transaction and commits an owned AgentRun, AgentStep, AgentOutbox, checkpoint, event and message link atomically. Retries return the existing link; changes to the source conversation revision fail closed.
- Exact selected document versions are revalidated in the same transaction. Unsupported selected artifacts fail closed instead of leaking a generic object reference into Agent work.
- Cancellation is revision-checked and enters the existing Agent cancellation logic within the same transaction. Queued outboxes are disarmed. Active linked work must be cancelled before conversation deletion.
- All conversation and transaction execution flags remain **default off**. No production emails, payment attempts, provider mutations, provisioning or feature activation were performed.
- Tests proposed on the branch must run in the locked heavyweight coworker CI; optional-dependency skips on lightweight CI do **not** satisfy the heavy-job mandatory test gate.

## Deployment and release

The coding branch is **not** an attestation that CW-01–CW-08 are fully finished. In particular,
CW-02–04 require external access and operated staging evidence. Only the owner of that
infrastructure can authorize or supply the requisite credentials, release rollout identity
and observable provider/test receipts. Never record invented evidence or change kill switches
to bypass those gates.

Next: inspect exact-head CI, fix observed backend/frontend regressions, validate real
PostgreSQL concurrency, then perform controlled staging and human security review before
any production activation.
