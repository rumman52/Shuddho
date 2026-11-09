# Part 3 — Reliability, Evaluation and Production Qualification

**Status date:** 9 November 2026  
**Combined implementation:** [PR #658](https://github.com/rumman52/Shuddho/pull/658)  
**Base revision:** `85118f7522c005eb3e3600c559f041793f3632b7`  
**Disposition:** `CODE_COMPLETE_UNQUALIFIED` for source work only until exact-head CI and review pass; overall release remains `NOT RELEASE-QUALIFIED`.

## Acceptance matrix

| Requirement | Source/repository evidence | Operated evidence | Current status |
|---|---|---|---|
| 3.1 Evaluation | Deterministic Phase 9 suite; budgeted live Runtime v3 evaluator; 18 synthetic planner cases (13 English, 4 Bangla and 1 Spanish); multi-step, no-tool, forbidden-tool and context/memory checks | Paid live planner run and curated multilingual output-quality run on exact staged SHA | Live run pending |
| 3.2 Observability | Nullable planner latency on AgentDecision; child model latency; model/tool percentiles; retry rate; cost-estimate availability; label-free OpenMetrics | Real Agent/Transaction samples, metrics receiver, alert delivery, concurrency load and reviewed pricing | Partially repository-verified; operated evidence pending |
| 3.3 Staging | Existing Runtime v3 and staging release harnesses; documented preflight | Durable DB, persistent worker, Temporal, private storage, managed identity, exact-SHA deployment and independent receipts | Blocked external |
| 3.4 CI/regressions | Writing Assistant Documents-first browser expectation; expanded evaluator tests; exact-SHA evaluation artifacts | Full final-head CI and independent review | Pending final-head checks |
| 3.5 Documentation/release | Design, plan, runbook, completion ledger and acceptance inventory updates | Security/operations sign-off, rollback exercise, branch-protection enforcement and release approval | Pending |

## Evaluation boundaries

The permanent Phase 9 CI suite is deterministic and provider-free. It measures server-owned routing, policy and contract regressions; it does not measure DeepSeek quality. The live Runtime v3 evaluator is separate and manual. It binds the rollout manifest, exact source SHA, fixture hash, model, measured tokens/latency and configured cost rate. It has total token and cost ceilings and stops if usage accounting is missing. The separate generated-output quality evaluator also has total token/cost ceilings and reports pass rate and required-fact recall independently by fixture language.

The live Runtime v3 planner fixture now includes a three-step research → report → email-draft plan followed by verified completion; unsupported capability rejection without a tool; a send-email adversarial request that may only remain a draft; and context-grounded reporting with an embedded untrusted instruction that must not become authority. It also checks forbidden tools and memory-proposal source IDs.

The live evaluator does not execute provider tools. Existing Runtime v3 Temporal tests use the Temporal test server plus isolated SQLite/local object storage. They are not a deployed staging environment.

## Observability semantics

- Planner latency: measured provider round-trip from the live planner, persisted on successful `AgentDecision` rows by additive migration `0067`.
- Child model latency: existing `ModelAttempt.latency_ms`.
- Model percentiles: combined successful planner and child-model latency samples; failed planner calls without persisted timing are excluded and reduce coverage.
- Tool percentiles: measured from persisted tool invocation start/finish timestamps.
- Retry rate: retry attempts / (model calls + tool calls) for the exported window.
- Cost: a configured blended-rate estimate, not an invoice. Nonzero token use with no positive reviewed rate yields unavailable cost, never zero.

OpenMetrics remains label-free. It does not include run IDs, owner IDs, prompts, source text, recipients, transaction terms or credentials. The repository does not install telemetry ingestion, dashboards or alert destinations.

## Read-only staging preflight — 9 November 2026

Render workspace inspection found:

| Resource | Observed state |
|---|---|
| `shuddho-api-staging` | Service exists; auto-deploy disabled; last live deployment is `fce72760456bd8bb03524ce98127120c7ac3dfb9` from 2 October 2026 |
| `shuddho-staging-db` | PostgreSQL 18, `suspended` by billing; metadata expiry `2026-10-31T17:11:33Z` |
| Persistent staging worker | No `shuddho-worker-staging` service is present in the inspected Render workspace |
| `shuddho-api` production | Live on main revision `1288ccf88ead3e63cfca45beeaf49777a58f3e14`; auto-deploy from main remains enabled |

No Render service, database, billing, secret, deployment, Temporal, provider or feature-flag changes were made. The combined PR branch is not the production service branch and no staging promotion is configured.

Staging qualification cannot proceed until an authorized owner restores durable PostgreSQL continuity, provisions/authorizes a persistent worker, configures protected Temporal/private-storage/identity credentials, and confirms a frozen release candidate. No replacement database or paid service was created.

## CI and governance

The browser regression was in the test sequence: the Coworker-enabled Writing Assistant route opens the Documents dashboard first, but the browser test waited for the editor-only subtitle before clicking a hidden back-to-documents control. The corrected test verifies Documents and New document first, then explicitly opens the editor and preserves the existing layout/mobile assertions.

The governance audit on main previously failed because branch protection was not confirmed. PR checks do not repair repository policy. An authorized GitHub administrator must configure and verify protected-main rules and required checks; this PR does not bypass that requirement.

## Rollback

- Migration `0067` is additive and nullable. The downgrade drops only `cw_agent_decisions.latency_ms`; existing rows remain compatible with the old source because latency is optional.
- Source rollback is a revert of the Part 3 PR/merge commit after stopping any new exporter consumer that expects the added metrics.
- No hosted migration has been run by this PR. Do not downgrade or alter a hosted database as part of this repository-only work.

## Release decision

Do not claim staging-qualified or production-ready from this PR alone. Final acceptance still requires exact final-head CI including the full Coworker/Temporal and Chromium browser jobs; independent security/operations review; live planner and multilingual quality results against the exact controlled-staging SHA; real staging Agent/Transaction samples, reconciled unknown outcomes, backup/restore, worker restart and concurrent-load evidence; metrics receiver and alert verification over an owner-approved window; effective branch protection; and separate release authorization.
