# PA-10 transient Agent capacity admission retry — contract

- **Base:** main cd4ee79bd610ead4f333c297c71a064065a076d2.
- **Scope:** AgentRun admission for scheduled, connected-event/email and meeting-preparation occurrences; simple reminders remain unchanged. Deadline admission is deliberately excluded.
- **Observed code path:** three replay-safe AgentRun admission paths in AutomationRepository persist an accepting occurrence, call AgentRepository.create, and currently mark every CoworkerError as terminal blocked. The worker's claim_buffered_occurrences explicitly reclaims stale accepting occurrences after 30 seconds.
- **Failure mode:** AgentRepository.create can reject with active_agent_limit / HTTP 429 before creating a run. Marking that occurrence blocked makes the existing recovery path unable to retry it after capacity becomes available.
- **Required behavior:** only active_agent_limit with status 429 leaves the occurrence accepting, records the error code as its reason, refreshes updated_at, and returns an accepting result. Other CoworkerError values remain blocked.
- **Idempotency:** reuse the same occurrence key and deterministic AgentRun idempotency key; retries must create at most one run and one start notification.
- **Verification:** failing-first test, green focused test that ages the accepting lease and exercises claim_buffered_occurrences, exact-head CI with mandatory test collection and no skips.
- **Evidence boundary:** repository-level retry regression only. No claim of deployed worker behavior, staging, provider qualification, V-01 enforcement or production readiness.
- **No side effects:** no schema, flag, provider, credential, Render, Supabase or production change.