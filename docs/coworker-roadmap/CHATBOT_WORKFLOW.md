# Use a chatbot as Shuddho's coding medium

## What this kit installs

The repository contains one reusable `shuddho-engineering` skill under
`.agents/skills/`, a task queue, source-grounded roadmap, copy-paste prompts and a
progress ledger template. This consolidates architecture, implementation, debugging,
review and qualification into one bounded workflow.

A compatible repository-aware Codex environment can load repository skills from
`.agents/skills`. In a GitHub-connected chatbot without local discovery, ask it to read
that skill and the linked task documents explicitly. ChatGPT Skills-page installation
is a distinct operation; it was not available in this authoring session. No account
installation or production runtime dependency installation is claimed.

The skill is coding guidance, not Shuddho's production `services/coworker/skills.py`
catalog. Do not add a runtime capability merely because an engineering skill exists.

## Development setup on your coding machine

Use a clean checkout of the coding-kit PR branch, then:
```bash
uv lock --check
uv sync --frozen --group dev --extra coworker
npm ci
```

Use the repository's current README, `.env.coworker.example`, `infra/docker-compose.yml`
and CI workflow for service setup. Review example settings before populating a backend-
only local configuration. Do not copy production secrets into development or enable all
flags as a shortcut. Install optional ML engines only when that task needs them.

A GitHub connector reads/writes repository files; it is not automatically a terminal,
PostgreSQL server, Temporal worker, provider account or deployed test environment.
When local tests are unavailable, push a reviewable branch and inspect real CI runs.
Do not invent shell output or claim mocked tests constitute staging evidence.

## Bootstrap prompt

Paste this at the start of a fresh coding conversation:

```text
Work on https://github.com/rumman52/Shuddho.
Until coding-kit PR #362 is merged, read this kit from branch
codex/coworker-roadmap-coding-kit-20261012; inspect runtime code on
fresh main or the explicitly selected repair branch. Inspect existing
chaos PR #361 before creating a duplicate CW-01 implementation PR.
Read root AGENTS.md, .agents/skills/shuddho-engineering/SKILL.md,
docs/coworker-roadmap/README.md, SPEC.md, ROADMAP.md, PROGRESS.md,
and docs/superpowers/plans/2026-10-12-coworker-evolution.md.
Refresh main SHA, open relevant PRs, required CI results, and deployed
evidence if accessible. Treat historical checkpoints as historical.
Choose the first dependency-ready unfinished task, starting CW-01.
Complete only that task on a dedicated branch and open a draft PR.
Preserve current provider, tenant, approval, budget and default-off gates.
Do not activate production or provision paid infrastructure.
Do not recreate completed work or weaken production code to satisfy an
invalid new test. Reproduce defects, add meaningful regressions, implement,
run required checks, inspect exact-head CI and review the resulting diff.
Report implemented, repository-verified, staging-verified,
production-qualified and activated separately. Save a precise handoff.
If blocked externally, finish all independent authorized work and state the
missing access without manufacturing evidence.
```

## Task implementation prompt

```text
Use the Shuddho engineering skill. Complete CW-XX from the coworker
evolution plan. Refresh dependencies and read the actual touched modules.
Write a short task contract with exact files/interfaces and acceptance tests.
For a real bug, reproduce its failure before fixing the root cause.
Implement the smallest coherent patch; preserve old histories and readers.
Run relevant focused tests, affected quality/release checks and full required
CI. Report skipped tests and unavailable checks explicitly.
Self-review authorization, state ownership, retries, failure outcomes,
tenant isolation, credentials, cancellation, budgets and rollback.
Open a draft PR with behavior changes and exact validation evidence.
Update PROGRESS.md without converting code completion into live qualification.
```

## First task prompt: CW-01

```text
Repair Phase 11 chaos-test contracts and mandatory CI collection first.
Inspect tests/test_transaction_chaos_qualification.py,
tests/test_transaction_reconciliation.py, tests/test_personal_transactions.py,
services/coworker/transaction_repository.py, action_repository.py,
models.py, action_schemas.py, actions.py and .github/workflows/ci.yml.
Run the chaos file with the coworker extra and retain the initial failures.
Preserve same-action binding replay as idempotent; reject a different action.
Use real connection/action fixtures with exact transaction terms.
Replace invented ORM evidence fields and nonexistent advance_execution
with actual approval/claim/dispatch/reconciliation interfaces.
Count provider-applied mutations, including accepted-then-timeout behavior.
Add this file to the mandatory coworker CI invocation; require zero skips.
Expand the Phase 11 document to all 16 requested injections, clearly marking
which have executable/integration/live evidence and which remain pending.
Do not claim the full invariant or 99.9% qualification from this repair alone.
Open a draft PR and update the checkpoint with exact head and CI evidence.
```

## Review prompt for a separate review pass

```text
Review this Shuddho PR against root AGENTS.md, SPEC.md and its CW task.
Inspect the diff, surrounding code, actual tests and exact-head CI.
Find concrete correctness, authorization, race, retry, compatibility,
isolation, cost and evidence-claim defects. Prioritize by severity and
give file/location, trigger, consequence and minimal remedy.
Specifically check that accepted-then-lost provider responses cannot
trigger a second mutation and completion requires matching receipts.
Do not presume green CI executed every mandatory safety test.
Return findings or state the inspected scope and residual unverified risks.
```

## Resume prompt

```text
Resume Shuddho from docs/coworker-roadmap/PROGRESS.md.
Verify the saved branch/PR/head still exists and refresh CI/review status.
Read the last task's exact unfinished item and continue it first.
Do not redo completed implementation, silently widen scope, or equate
a historical staging record with the currently deployed release.
Before ending, save branch, SHA, PR, checks, blockers and next exact action.
```

## Staging qualification prompt

```text
Qualify the implemented CW task on the explicitly selected non-production
environment. Read the canonical release contract and current staging
runbooks before invoking collectors. Confirm source/API/worker/model/
rollout identity; use synthetic accounts and exact authorized resources.
Freeze the release before final qualification evidence collection.
Exercise public APIs, provider callbacks and real process recovery.
Record expected versus observed outcomes with hashes and timestamps.
If prerequisites are missing, report blocked; never fill evidence with mocks.
No production activation is included in this task.
```

## Everyday operating rules

One coherent task per branch/PR. End every session with a committed checkpoint.
A new conversation starts from the repository record, not the model's recollection.
Use the chatbot to inspect and implement; use tests and reviews to decide whether the
result works; use staging evidence to decide whether it can launch.

Relevant planning/debugging/testing skills are already available in the authoring
session. Reinstalling every generic skill does not add runtime intelligence and can
make overlapping instructions harder to follow. Use the focused project skill plus
appropriate built-in tools for the concrete task.

Do not paste private credentials into prompts. Grant the coding environment only the
repository/staging access the task requires. Human/provider/billing approvals and final
production activation remain distinct from source-code edits.

