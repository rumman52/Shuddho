---
name: shuddho-engineering
description: Plan, implement, debug, review and qualify Shuddho coworker changes in bounded repository tasks. Use for Shuddho architecture, core agent, automation/proactivity, transactions, CI and production-readiness work, including resuming its coworker roadmap. Do not use for unrelated repositories or as permission to activate production.
---

# Shuddho engineering

## Establish source truth

1. Locate the Shuddho checkout or authorized GitHub connection. Read root AGENTS.md.
2. Read docs/coworker-roadmap/README.md, SPEC.md and PROGRESS.md. Read ROADMAP.md and the relevant CW task in docs/superpowers/plans/2026-10-12-coworker-evolution.md.
3. Refresh default-branch SHA, relevant open PRs, exact-head CI and accessible deployed identity. Treat report/checkpoint timestamps as historical. Do not infer production readiness from merge history.
4. Choose the first dependency-ready unfinished task within the user's scope. Start CW-01 unless fresher source/evidence shows it is done. Reuse completed PA/TX foundations.
5. If this skill is copied outside its repository, use the authorized Shuddho repo to obtain these documents; ask for the repo only if it cannot be identified. Do not infer contents from filenames.

## Implement one coherent slice

1. Create a dedicated review branch. Inspect actual touched interfaces and existing working tests.
2. Record the task contract using docs/coworker-roadmap/TASK_TEMPLATE.md.
3. Reproduce a bug before fixing it; for a meaningful new feature, pin acceptance behavior with tests.
4. Implement the smallest coherent patch. Do not weaken production behavior to satisfy an invalid new test.
5. Run focused checks and required CI with the needed extras. Report skipped/unavailable checks. Inspect exact final-head results and surrounding code before claiming repository verification.
6. Open a draft PR when requested/authorized; never treat a draft as merged.
7. Save a checkpoint with branch/SHA/PR/checks/blocker and next exact action before handoff.

Use docs/coworker-roadmap/CHATBOT_WORKFLOW.md for bootstrap, task, review, resume and staging prompts. Keep model recollection subordinate to current source and evidence.

## Preserve project invariants

- Preserve Bangla/multilingual free writing, local fallbacks, AI failure diagnostics, backend-only DeepSeek configuration and explicit Gemma rollback. Never silently switch providers.
- Keep PostgreSQL records, Temporal durable execution, private object storage and existing outboxes. Do not add another run/action/notification ledger or orchestrator.
- Preserve old history replay and additive schema compatibility.
- Bind context to owner/resource/version/purpose; recheck revocation/deletion at use. Memory and retrieved data are not permission.
- Keep tools typed and code-owned, budgets reserved across parent/child calls, completion backed by verified outputs.
- Keep credentials, deterministic authorization and egress enforcement outside untrusted model/code/browser execution.
- Require exact human approval for consequential actions. Reuse existing ExternalAction claims and immutable preview/source/terms bindings.
- Preserve identical action-binding replay as idempotent; reject a different binding.
- Treat accepted-then-lost provider response as uncertain/reconcile. Never blindly resend. Provider errors are definitive only under the provider contract.
- Keep generated skill/code inert or sandbox-local until reviewed; no automatic promotion to production authority.
- Keep new capabilities default-off and use canonical release contracts. A broad flag does not register a provider.

## Verify failure and release evidence

Use the complete 16-case matrix in ROADMAP.md. Exercise real dispatch boundaries with independent provider mutation counts, PostgreSQL/Temporal and process interruption where required.

For CW-01, inspect the current chaos file before editing: possible defects include absent heavy-suite collection, invented ORM fields/methods and invalid same-binding expectations. Confirm against fresh source; do not assume historical findings remain unfixed.

Distinguish:
- implemented: coherent code exists;
- repository-verified: required exact-head checks actually ran and passed;
- staging-verified: fresh real synthetic scenarios on matching non-production identity;
- production-qualified: reviewed full release requirements pass;
- activated: explicitly authorized capability/cohort enabled and observed.

Do not claim 99.9% from chaos tests. Define SLI/window/denominator and collect operated measurements. Keep safety invariants distinct from availability and eventual completion.

## Handle blockers

Complete independent authorized source/test/review work. State missing staging/provider/billing/human inputs precisely and leave affected capabilities disabled. Never invent commands run, access granted, provider receipts, model identities, evidence hashes or human review.

This skill supplies coding workflow, not standing approval for paid provisioning, production activation, external sends, purchases or broad permission changes. Follow explicit session authorization; ask only when a necessary consequential step is not authorized.

## Review and handoff

Review races, ownership, exact approval hashes, uncertainty, cancellation/revocation, budgets, egress, old readers/histories and misleading status claims. Fix concrete defects and rerun affected checks.

Update PROGRESS.md with implemented/repository/staging/production/activation levels separately, exact final head, checks and counts, external blockers, flags/authority, residual findings, and next action. Do not mark the full roadmap complete because the coding kit or one PR exists.
