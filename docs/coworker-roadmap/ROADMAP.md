# Shuddho: from bounded coworker foundations to a continuous AI coworker

## Decision and evidence

Evolve the existing architecture. Preserve FastAPI, PostgreSQL, Temporal, private object
storage, typed tools, external-action approvals, and Bangla writing. Add continuity and
qualified capabilities around them.

Shuddho is beyond a simple writing MVP. It is not yet a demonstrated production Muse
equivalent. No defensible percentage-complete estimate follows from merged PR counts.

Inspected baseline: `ed1467d3e9ce230d1a8d9b24fdfa5594ebc0df40`.
[Main CI #1332](https://github.com/rumman52/Shuddho/actions/runs/38163844235) passed
`test-and-build`, `coworker`, and `ci-merge-gate`.
This is repository CI evidence, not a live reliability or transaction-safety certification.

Muse's first-party design describes continuous chat, goals, persistent memory, background
work, a browser/terminal/filesystem and rich artifacts. Its security description says the
agent executes in an isolated cell; independent credential and Sentinel services govern
external access. These are publicly described capabilities, not independently measured
performance or a complete disclosure of its internals.

Our recommendation is a persistent logical workspace with ephemeral isolated compute.
A dedicated VM per user is a later option if security/latency/utilization measurements
justify its operating cost. This is a Shuddho design choice, not a claim of equivalence to
Muse's dedicated-VM threat model.

## Where Shuddho stands

| Area | Verified repository evidence | Assessment | Next work |
| --- | --- | --- | --- |
| Architecture design | Personal-agent architecture; Temporal workflow, PostgreSQL models, private artifacts; permission gateway and credential broker | Strong foundations already designed and partially implemented | Declare ownership of each state, close orchestration/tool integration gaps, validate deployed boundaries |
| Core agent | Runtime v3 reads verified observations and scoped context; typed next-step decisions, budget reservations, verified completion, older workflow compatibility | Bounded coordinator exists; general computer coworker remains incomplete | Continuous conversation/task dispatch; browser tool; qualified generated-code workflow; measured route/model quality |
| Automation/proactivity | Goals, schedules, occurrence dedupe, notifications/digests, event reads, Daily/Weekly/Meeting/Email/Deadline/goal-driven modules | Repository foundations exist; canonical staging checkpoint still records unresolved operational prerequisites | Refresh infrastructure state; freeze release; execute real scheduled/event, recovery, consent, usefulness and cost scenarios |
| Transactions | Generic ledger, immutable terms, one action binding, uncertainty/reconciliation; negotiation email and bounded no-payment restaurant path; shopping/travel contracts and hosted-handoff foundations | Safety-oriented foundations exist; broad provider execution and full chaos qualification are not demonstrated | Repair chaos-test defects/coverage; prove dispatch invariant; qualify exact providers individually |
| Production qualification | CI, evaluations, release contract, activation bundle/ledger, rollback/restore tooling | Tooling exists; fresh live evidence and measured 99.9% SLO are not established by the inspected material | Operated staging, isolated execution/security tests, provider proof, cost/load/restore measurements, small reviewed canary |

Evidence anchors:
- [Architecture](https://github.com/rumman52/Shuddho/blob/ed1467d3e9ce230d1a8d9b24fdfa5594ebc0df40/docs/PERSONAL_AGENT_ARCHITECTURE.md)
- [Implementation history](https://github.com/rumman52/Shuddho/blob/ed1467d3e9ce230d1a8d9b24fdfa5594ebc0df40/docs/PERSONAL_AGENT_IMPLEMENTATION.md)
- [Canonical staging checkpoint](https://github.com/rumman52/Shuddho/blob/ed1467d3e9ce230d1a8d9b24fdfa5594ebc0df40/docs/PA10_CONTROLLED_STAGING_CHECKPOINT.md)
- [TX-28 provider boundaries](https://github.com/rumman52/Shuddho/blob/ed1467d3e9ce230d1a8d9b24fdfa5594ebc0df40/docs/TX28_TRANSACTIONS_REPOSITORY_COMPLETION.md)
- [Runtime v3](https://github.com/rumman52/Shuddho/blob/ed1467d3e9ce230d1a8d9b24fdfa5594ebc0df40/services/coworker/agent_runtime.py)

## Immediate qualification defects

The newest chaos test file must be repaired before citing it as safety evidence.

1. `tests/test_transaction_chaos_qualification.py` is absent from the explicit heavy
   coworker pytest command. The lightweight job installs no coworker extra; the file
   uses `pytest.importorskip("sqlalchemy")` and `pytest.importorskip("temporalio")`.
   Therefore green CI does not establish that this file ran. Inspect logs to establish
   the actual collection/skip result; require zero skips for the mandatory new suite.
2. The duplicate-binding test expects a second bind to the *same* action ID to fail.
   `TransactionRepository.bind_external_action` intentionally returns the existing
   link for that replay; a different action ID is the conflict. Preserve that
   idempotent contract and test both cases.
3. The timeout test passes `evidence_type` and `evidence` to
   `TransactionReconciliationEvidence`; the inspected ORM model declares neither.
   Its real fields bind the external action, provider, state, receipt and evidence hash.
   Exercise the dispatcher and repository reconciliation path instead of inserting
   invented evidence.
4. The expiration test calls `container.transactions.advance_execution`; no such
   method exists in the inspected transaction repository. Use the real action
   approval/claim boundary and verify zero provider mutations.
5. The new Phase 11 document lists only five outcomes, not the requested 16 injections.

These are source/CI-configuration findings. The current chaos suite was not executed
locally during this planning review. CW-01 requires a real reproduction before repair.
The findings do not establish that the production action service duplicates actions.

Open [chaos PR #361](https://github.com/rumman52/Shuddho/pull/361), inspected at
`f543573220c2254c6f16c8777d0ff9783efcd92c`, changes this file but is not merged.
It still constructs undeclared ORM fields, references an absent
`review_binding["external_action_id"]`, and its expiry test only checks a nonempty ID.
Inspect/reconcile that work before starting another repair PR; do not consider it
qualified merely because it replaces the missing-method call.

## The target experience

A student says: "Use my syllabus to help me prepare for this course. Brief me each morning."

Shuddho retains the selected syllabus, goal, milestones and progress. It admits bounded
runs, creates editable artifacts, and works while the browser is closed. A later message
changes the goal through a versioned edit. Approved scheduled work produces useful
updates. Preparing an email creates an exact review card; sending requires approval.
A worker restart resumes the same run; a lost send response becomes uncertain or is
reconciled with a matching receipt. The UI explains what happened.

Pilot three workflows first:
- Student: syllabus -> goal -> study plan -> daily briefing -> editable quiz/deck.
- Office: selected documents -> grounded report -> editable artifacts -> exact email review.
- Calendar: consented calendar -> meeting preparation/conflict detection -> approved event.

Qualify transaction families after the safe read/draft/compute pilot. Do not promise every
website, general payments, or unrestricted browser execution.

## Architecture and state ownership

| Concern | Authority / existing base | Planned addition |
| --- | --- | --- |
| Conversation and user intent | New owner-scoped PostgreSQL conversation records | Messages, explicit request identity, links to existing goals/tasks/runs/actions |
| Goal/task progress | Existing goal and agent repositories | Unified read projection; no second run ledger |
| Durable execution | Temporal workflows and existing outboxes | New adapters and versioned histories; no competing orchestration engine |
| Application records and approvals | PostgreSQL repositories | Additive schema and exact immutable approval bindings |
| Files/artifacts | Private object storage plus owned DB metadata | Versioned logical workspace and provenance; isolated previews |
| Reasoning | Evaluated DeepSeek planning/drafting adapters | Scoped context, observations and capability-aware routing |
| Permission and credentials | Permission gateway, credential broker, action registry | Narrow worker identities and network-enforced egress |
| Browser/code execution | Isolated existing browser/sandbox workers | Qualified typed browser tool and generated-code preparation flow |
| Proactivity | Automation scheduler, connector events, notifications | Controlled admission, source freshness and measured notification usefulness |
| External mutation | Existing ExternalAction ledger and provider adapters | Provider-specific conformance/reconciliation; no alternate send/checkout path |

The language model proposes. Deterministic services authorize, persist, execute and
verify. A fluent completion message is never a provider receipt.

Do not add Kafka, a graph database, another durable agent framework, a permanent VM per
free user or broad Kubernetes migration until a measured need warrants it. Read-only
specialists may be added after evaluation shows better outcomes within shared budgets.

## Where to change

| Change | Existing entry points | New records/components if needed |
| --- | --- | --- |
| Main conversation and unified activity | `WorkspaceShell.tsx`, `CoworkerWorkspace.tsx`, `client.ts`, `api.py`, `container.py` | Conversation repository/schemas/UI; unified activity projection |
| Route and task continuity | `agent_router.py`, `agent_runtime.py`, `agent_repository.py`, `workflow.py` | Conversation dispatch service; explicit task links and user steering |
| Owned workspace/context | `repository.py`, `storage.py`, `context.py`, `memory_repository.py` | Versioned workspace manifest and conversation-scoped context projection |
| Agent browser access | `agent_tools.py`, `agent_runtime.py`, `browser.py`, browser workers | New typed read-only browser tool; existing ownership/egress constraints |
| Agent-generated code | `agent_tools.py`, `agent_runtime.py`, `sandbox.py`, `sandbox_worker.py` | Versioned code proposal and exact-source reviewed execution |
| Proactive execution | `automation_repository.py`, `automation_scheduler.py`, `connector_reads.py`, notification modules | Qualification/evidence extensions only where scenarios reveal gaps |
| Transaction guarantees | `actions.py`, `action_repository.py`, `transaction_repository.py`, `action_registry.py` | Process-level injection harness; concrete provider adapters only after selection |
| Production release | `release_contract.py`, staging/evidence/activation/ledger scripts, `ci.yml` | Evidence matrix, SLO definitions and version-bound qualification |

Backend paths in this table are under `services/coworker/`; frontend paths are under
`apps/web-editor/src/` or `apps/web-editor/src/coworker/`; script paths are under
`scripts/`. The implementation plan spells out exact paths.

## Complete route and gates

| Milestone | Tasks | Deliverable / exit gate | Dependency |
| --- | --- | --- | --- |
| M0: evidence repair | CW-01, CW-02 | Mandatory chaos test runs; invalid test contracts repaired; 16 injection outcomes; dispatcher/process proof | First |
| M1: qualified foundation | CW-03, CW-04 | Refreshed live prerequisites; same-release API/worker identity; read/draft/goal/reminder/recovery scenarios | M0; external staging access |
| M2: continuous coworker | CW-05..CW-08 | Durable conversation, idempotent request dispatch, activity, owned file/context continuity | M0; staging verification before activation |
| M3: practical tools | CW-09..CW-11 | Typed browser research, reviewed generated-code execution and versioned skills; all default-off until qualified | M1/M2 |
| M4: proactive pilot | CW-12, CW-13 | Real scheduled/event work, revocation and restart proof; useful quiet notifications | M1/M2 |
| M5: qualified transactions | CW-14..CW-16 | Negotiation/no-payment restaurant proofs; selected shopping/travel providers and exact hosted receipt | M0/M1; provider credentials/contracts |
| M6: production qualification | CW-17..CW-19 | Quality/security/economics, load/restore/rollback and 99.9% measurement plan | Relevant earlier capability gates |
| M7: controlled beta | CW-20 | Release-bound activation, observed small cohort, owned operations and support | M6 passes |

M2 product development can proceed while external staging setup is blocked. M5 shopping/
travel provider evaluation can occur independently, but cannot invent access or bypass
M0. Activation is never implied by completing a coding task.

This is an engineering queue, not a promised parity date. Estimate each task after
reproduction/discovery; provider approval and deployed qualification need separate
calendar time. Launch a small set of successful workflows before expanding the catalog.

## Phase 11: all requested failure outcomes

For read-only/model work use bounded retries when permitted. For mutation distinguish
failure before dispatch, a definitive rejection, and ambiguous submission. Do not infer
"nothing happened" merely from an HTTP error. A provider's documented contract controls
whether a response is definitive.

| Injection | Expected behavior | Required evidence |
| --- | --- | --- |
| Model 429 | Bounded backoff under reservation/deadline; explicit rate-limit state at exhaustion | Attempts, budget and wait bounds; no action dispatch from failed decision |
| Model 500 | Bounded provider retry if allowed; transparent failure/fallback under configured policy | No silent provider switching or invented successful plan |
| Model timeout | Bound cancellation/attempts; conservative unknown usage; resumable/blocked outcome | No stale response overriding cancellation; no budget overspend |
| Provider 401 | Stop; reconnect/credential diagnostic; no unauthorized mutation | Counter and credential-access denial |
| Provider 403 | Stop; scope/permission diagnostic; no broadening grant | Denied scope and zero mutation |
| Provider 429 | Read retry only within policy; mutation retry only with definitive no-submission/idempotency contract | Same action identity; no blind resend |
| Provider 500 | Definitive rejection -> failed; ambiguous submission -> uncertain/reconcile | Provider outcome contract and mutation count |
| Malformed response | No fake receipt; model response rejected; post-dispatch provider response reconciled/uncertain | Schema rejection plus receipt binding |
| Database disconnect | No claim -> no mutation; post-claim/post-mutation crash -> preserve one attempt and reconcile on recovery | PostgreSQL reconnect/process restart at both boundaries |
| S3 disconnect | No success without required artifact; bounded safe storage retry; do not repeat completed mutation | Exact export identity/checksum; action unaffected by missing artifact |
| Temporal outage | Persist accepted intent/outbox; do not claim admission succeeded when DB commit failed; dispatch after recovery once | Outbox/run identity before and after server interruption |
| Worker crash | Before dispatch recover safely; after claim/submission reconcile, never blind-repeat | Process kill and restart with provider-side counters |
| API crash | Committed request replays to same resource; uncommitted request creates at most one accepted record | Public API idempotency and PostgreSQL races |
| Duplicate message | Same owner+request key+payload -> same run/action; changed payload+same key -> conflict | Concurrent delivery and one accepted identity |
| Lost provider response | Keep same action in uncertain/reconcile state until exact receipt; unresolved stays uncertain | Provider applied mutation, response dropped, mutation count stays one |
| Approval after expiration | Reject actual approval/claim; changed or expired terms require fresh preview | Clock boundary at approval and claim; zero provider mutations |

Also test revocation at claim, changed price/terms/destination, duplicate/out-of-order
receipts, tenant isolation and cancellation. Use independent provider-side applied-mutation
counts as well as application ledger counts.

The invariant is **at most one consequential mutation for one approved execution
identity**. It does not prevent a user knowingly approving a fresh, separate transaction.
Without provider idempotency or authoritative reconciliation, absolute end-to-end
exactly-once execution cannot be guaranteed across arbitrary network/process failures.
Choose safety: leave uncertain work unresolved rather than blindly retrying. Duplicate
safety and eventual completion are separate objectives.

## Production qualification and 99.9%

99.9% is a target, not an observed current result. First define the SLI denominator,
eligible requests, endpoints, measurement window, latency threshold and exclusions.
Keep API availability, admitted background-run completion and scheduled-delivery
timeliness separate. Report dependency failures separately without erasing user-visible
failures from the chosen user-facing SLI.

For a time-based 30-day availability SLI, 99.9% permits 43.2 minutes of unavailability;
99.75% permits 108 minutes. For a request-based SLI, the budget is failed eligible
requests, not minutes. Passing 16 chaos cases does not establish either SLO.

Require:
- Owner identity, tenant isolation, credential exclusion and enforced egress.
- Deterministic old-history replay, duplicate admission, fan-in and restart recovery.
- Model/route/artifact quality in Bangla and English, human review and sample sizes.
- Real provider and notification consent/expiry/revocation evidence.
- Cost per accepted outcome, global/account/run reservations and reviewed nonzero pricing.
- Forecast-load and overload tests; queues must not starve interactive writing.
- Actual backup restoration, deletion, key rotation, rollback and sandbox cleanup.
- Every uncertain transaction has a receipt reconciliation or explicit manual status.
- Evidence binds exact source, rollout, model configuration, capability and provider.
- On-call owner, alerts, incident/support/deletion runbooks and small canary observation.

No P0/P1 correctness/security finding may remain unresolved in a launched capability.
Zero observed safety failures means the evaluated cases passed, not mathematical proof
that all future executions are safe.

## External setup the chatbot cannot manufacture

The canonical staging checkpoint records a missing paid worker after Render returned
`need_payment_info`, unverified live Temporal/S3 access, synthetic-account/OAuth gaps,
push-device requirements, human language review and missing live economics samples.
These are historical recorded blockers, not a fresh probe of today's deployed account.

Refresh those before buying or provisioning anything. Provide named staging identities
and secret references through secure backend configuration; never paste raw secrets into
chat, frontend files or commits. The coding assistant can inspect/develop probes and
collect permitted evidence once access exists. It cannot invent provider access,
human approval, billing acceptance, actual receipts or live SLO measurements.

Development dependencies already declared by the repository:
`uv sync --frozen --group dev --extra coworker`, `npm ci`.
PostgreSQL, private storage, Temporal and isolated workers are separate services, not
Python package installs. Optional ML weights are unnecessary for the normal coworker kit.

## Sources checked

- https://introducing.muse.ai/
- https://research.meta.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse
- https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/
- https://learn.chatgpt.com/docs/build-skills
- Repository source at the baseline SHA above; attached engineering research report.

Use these as references. Do not infer Muse's private backend implementation or capacity
beyond what its first-party documentation states.

