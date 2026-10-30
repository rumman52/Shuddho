# Shuddho Live Release-Readiness Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Replace stale current-state handoffs with one exact, dated Shuddho release-readiness snapshot based on live GitHub, Render, Supabase, PostHog, Vercel, Linear and ProductOS evidence.

**Architecture:** Add a new dated release-readiness report as the operational source of truth. Update only the current pointers at the top of the existing progress, ledger, acceptance inventory and roadmap README; preserve historical checkpoints below them. Keep all runtime and infrastructure behavior unchanged.

**Tech Stack:** Markdown, GitHub repository content APIs, GitHub Actions verification.

**Spec:** Live Shuddho evidence inspected on 31 October 2026; current main SHA 38c5b8d0d3eafa5692f848a5e664897a500fcfe2.

## Global Constraints

- No secrets, raw tokens, customer data or private provider payloads in documentation.
- No database data, schema, connection, allowlist, plan, backup or migration changes.
- No Render service creation, restart, deployment, billing or environment-variable changes.
- No production flags, detector/corrector checkpoints or release promotion.
- No PostHog SDK, event, dashboard, alert or data collection until privacy scope is approved.
- No GitHub merge, branch-rule bypass or direct write to main.
- Preserve the 17-row acceptance denominator and historical evidence.

## Review Focus

- Distinguish exact-main CI success from governance failure and release qualification.
- Convert UTC expiry to Asia/Dhaka correctly and state the 14-day grace period accurately.
- Do not infer database contents when the hosted read-only query is blocked.
- Do not treat Supabase project health as a valid Render database replacement.
- Do not treat a live Render deployment or empty error logs as production health.
- Do not treat CI transaction tests as real provider-side mutation/reconciliation proof.
- Keep connector permission failures explicit for GitHub, Vercel and Render.

---

### Task 1: Add the dated release-readiness report

**Files:**
- Create: docs/coworker-roadmap/RELEASE_READINESS_REFRESH_2026-10-31.md

- [x] Collect current exact-main, CI, Render, Supabase, PostHog, Vercel, Linear and ProductOS evidence.
- [x] Record unresolved gates and owner actions without claiming release qualification.
- [x] Record that no infrastructure, data, telemetry or production changes were made.

### Task 2: Refresh current navigation and status pointers

**Files:**
- Modify: docs/coworker-roadmap/PROGRESS.md
- Modify: docs/coworker-roadmap/CORE_AGENT_COMPLETION_LEDGER.md
- Modify: docs/coworker-roadmap/ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md
- Modify: docs/coworker-roadmap/README.md

- [x] Add a dated 31 October handoff at the top of PROGRESS.md.
- [x] Replace only the stale top status block in the completion ledger.
- [x] Replace only the stale top acceptance refresh block.
- [x] Point the roadmap README to the new dated report.
- [x] Preserve all historical records below the current pointers.

### Task 3: Verify and publish a review-only handoff

- [ ] Verify every updated document against the exact current main source and the report.
- [ ] Verify the branch contains only the plan and documentation changes.
- [ ] Create a draft pull request; do not merge while native main governance is unverified.
- [ ] Inspect exact-head CI results and record any failed governance gate.
