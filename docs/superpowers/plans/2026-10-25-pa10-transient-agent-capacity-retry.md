# PA-10 transient Agent capacity admission retry

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Do not permanently lose a scheduled automation occurrence when AgentRun admission is rejected by the transient per-owner active-run limit.

**Architecture:** Keep the existing durable AutomationOccurrence ledger and stable idempotency key. A narrow retryable active_agent_limit rejection must leave the occurrence in the existing reclaimable accepting state with a safe reason and refreshed lease timestamp; permanent admission failures remain blocked. The existing worker reclaimer retries stale accepting occurrences after 30 seconds, and the catch-up window remains authoritative.

**Tech Stack:** Python 3.11, pytest, SQLAlchemy, FastAPI/Temporal integration tests.

**Spec:** docs/PA10_GOAL_DRIVEN_PROACTIVITY.md and the durable-acceptance contract in services/coworker/automation_repository.py::claim_buffered_occurrences.

## Global Constraints

- Do not create a second occurrence or AgentRun for the same automation/revision/due time.
- Preserve the stable automation idempotency key and existing owner/goal/revision/tool-scope validation.
- Retry only the explicit active_agent_limit (HTTP 429) error; do not make arbitrary admission failures retryable.
- Preserve catch-up-window expiry, automation kill switch, paused/cancelled state, goal revision, and current tool allowlist checks.
- No schema migration, external provider call, capability change, deployment, or production activation.

## Review Focus

- Transient capacity rejection leaves an occurrence reclaimable rather than permanently blocked.
- A later retry reuses the same occurrence identity and produces exactly one AgentRun and one start notification.
- Permanent admission errors remain blocked.
- Retry does not bypass catch-up expiry or current goal/automation checks.

---

## Tasks

- [ ] Add a regression to tests/test_automations.py that injects one CoworkerError(active_agent_limit, ..., 429) from agent.create, verifies no run is created and the occurrence remains reclaimable, then allows the next call to succeed with the same occurrence identity.
- [ ] Open a draft PR and observe the focused regression fail against current main before changing production code.
- [ ] Implement the narrow retryable-error branch in AutomationRepository.accept_occurrence; preserve permanent-error behavior.
- [ ] Re-run the exact-head coworker suite and all required CI jobs; verify zero skips in the targeted mandatory module.
- [ ] Read the final diff and document remaining staging/release blockers. Do not merge or deploy.