# Coworker evolution progress

## CW-09 default-off Agent browser metadata read — 13 October 2026

**Refreshed baseline:** `main` at `f5c11ec7db35721190b67212695e7612af63f09f`, with [CW-08 source-consent PR #386](https://github.com/rumman52/Shuddho/pull/386) merged and exact-head [CI #38404758754](https://github.com/rumman52/Shuddho/actions/runs/38404758754) successful; latest main [CI #38408371736](https://github.com/rumman52/Shuddho/actions/runs/38408371736) still in progress when inspected. No open PRs at bootstrap.

**Current bounded CW-09 task:** Register default-off typed `browser.read` as a Runtime v3 tool, qualify explicit user-authored read requests at the public Agent router, and connect it to the existing owner-scoped supervised broker and worker. Deterministic `explicit_browser_url` derives one HTTPS URL from the user's *original run goal*, not a model-chosen destination. Runtime creates/reuses a reserved `agent:<run_id>:<ordinal>` browser session, atomically prepares one read-only navigate command, and persists the broker-verified page URL/title/time/hash as **untrusted metadata-only**, not full page text or HTML capture. No new run or transaction ledger. A separate `SHUDDHO_AGENT_BROWSER_READ_ENABLED` flag defaults off and requires existing browser/v3/intelligent planner dependencies.

**Base:** `f5c11ec7db35721190b67212695e7612af63f09f`. **Branch:** `codex/cw09-brokered-read-metadata-20261013`. **Initial source + regression SHA:** `4d7c2521bdf083177c9f34cd8693007cf75ef535` before frontend/tool contract and doc commits. **Contract:** [CW09_BROKERED_AGENT_READ_METADATA_2026-10-13.md](CW09_BROKERED_AGENT_READ_METADATA_2026-10-13.md). **Draft PR:** [#387](https://github.com/rumman52/Shuddho/pull/387), still unmerged; dedicated no-skip test step added in `.github/workflows/ci.yml`. Final implementation/test SHA preceding this documentation checkpoint: `c596a3e9ed4af211fbfaf4e65e3413079d53ae45`. Latest exact-head CI must be refreshed after this commit; older runs were superseded.

| Item | Verified/current state | Pending acceptance |
| --- | --- | --- |
| CW-05 owned messages | Merged ledger/owner source + prior repository tests | Staging races/replay and deletion |
| CW-06 dispatch/cancel | Merged routing/dispatch, revision cancellation | Operating steering and terminal precedence |
| CW-07 activity continuity | PR #385 merged, full final-head CI passed | Mobile/keyboard/reconnect operated evidence, event-level cursor |
| CW-08 pinned context/memory | PR #384 and #386 merged, exact-head PR CI passed; prior-task implicit read sealed for conversations | Full lifecycle/revocation races, broader purpose consent, multilingual human acceptance |
| CW-09 browser read | Current branch: metadata-only typed v3 tool with default-off flag/broker command+receipt | Exact-head CI, actual page-body/private digest, real worker/SSRF/redirect/egress and release gates |
| CW-10 generated code | Sandbox foundation exists; approval-bound immutable code proposal not completed | Independent code-proposal and sandbox approval route |
| CW-11 skill manifests | Static skill registry; reviewed manifests not completed | Version/hash, authority subsets, compatible rollback |

| Evidence | CW-09 metadata slice |
| --- | --- |
| Implemented | Branch-only code + synthetic worker/broker tests |
| Repository-verified | Pending exact-final-head no-skip GitHub Actions |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | **No** — flag remains default-off |

**Review:** Self-review only. Explicit user URL and reserved server resource identity reduce planner authority; test covers denied destinations and replay. A separate full content capture and canonical release eligibility policy still need integration; metadata hash is explicitly not claimed as web content hash. An independent security reviewer and frozen live isolated-worker evidence are mandatory before activation. Existing PHP/Node/web dependencies, transaction provider and writing/DeepSeek configuration remain unchanged.

**Next exact action:** Open draft PR and verify current-head `test-and-build`, `coworker`, `ci-merge-gate`, and targeted `tests/test_agent_browser_tool.py`. Resolve any failure, obtain independent review, then implement CW-09 bounded page-body capture/private checksum on its own review slice or advance independent CW-10 proposal contract. Do not merge or activate automatically.

## CW-08 explicit conversation source-selection boundary — 13 October 2026 (Asia/Dhaka)

**Repository bootstrap:** `main` `b2a6920d2fea10dfc5a813746e19c7241597846b`. [CW-07 PR #385](https://github.com/rumman52/Shuddho/pull/385) was **merged**; its final-head [CI #38402405574](https://github.com/rumman52/Shuddho/actions/runs/38402405574) was still in progress as inspected, so completion of its broad checks is not inferred. New main [CI #38403290676](https://github.com/rumman52/Shuddho/actions/runs/38403290676) also in progress. No other open PRs at bootstrap.

**Selected dependency-ready task:** CW-08's selected-only conversation planning context. Source finding: `ContextService._resolved` included lexical-matching prior completed/needs-input `Task` content from the owner workspace even when a conversation message carried `selected_sources=[]`. The conversation admission ledger bound only selected document versions; this prior-task inclusion lacked message source consent. **Repair** bypasses implicit prior-task retrieval for server-created conversation Agent runs, retaining standalone Agent compatibility and already-enforced conversation document pin, owner, revocation and checksum checks.

**Base and branch:** `main` `b2a6920d2fea10dfc5a813746e19c7241597846b`; `codex/cw08-explicit-conversation-context-20261013`. **Implementation/regression SHA:** `00cbe0d8dbe32a242dc458c83fc37ed383941d52` before documentation. **Task contract:** [CW08_EXPLICIT_CONVERSATION_CONTEXT_2026-10-13.md](CW08_EXPLICIT_CONVERSATION_CONTEXT_2026-10-13.md). **Review:** [draft PR #386](https://github.com/rumman52/Shuddho/pull/386), original review head `bd5e5bfaa7fdbc545e22e13d9b2a6e61e55ea308` before this final checkpoint; required exact-current-head CI [run 38404234208](https://github.com/rumman52/Shuddho/actions/runs/38404234208) was in progress and will be superseded by new commits. Always refresh the actual PR head and checks before closure. A same-owner real completed task with private notes/draft is excluded from an unselected conversation's planner and context while remaining available to existing direct Agent continuity.

| Scope requirement | Integration/evidence | Unmet acceptance |
| --- | --- | --- |
| CW-05 messages | Existing merged implementation, prior tests | Operated consent/replay/race/deletion qualification |
| CW-06 routing and revisioned cancellation | Existing merged implementation | Steering and late/cancel operational checks |
| CW-07 resumable activity and UI | PR #385 merged; final-head broad CI pending when inspected | Verify exact-main CI, independent/mobile/reconnect and combined event cursor |
| CW-08 context and reviewable memory | Pinned source integrity #384 merged; new prior-task consent repair only on review branch; memory edit/delete UI exists | Exact-head CI, source revocation race, explicit whole-context consent, Bangla/English task evidence |
| CW-09 typed browser read | Isolated browser broker/worker but no Agent `browser.read` registered at inspection | Typed default-off dispatch and isolated SSRF/takeover validation |
| CW-10 reviewed generated code | Sandbox foundation only | Stored immutable approved code-to-execution envelope |
| CW-11 versioned skill manifests | Static skill registry only | Validated reviewed manifest and rollback after CW-09/10 |

| Evidence level | This CW-08 slice |
| --- | --- |
| Implemented | On isolated branch only |
| Repository-verified | Pending exact-final-head PR `test-and-build`, `coworker`, `ci-merge-gate`; local full-repo execution unavailable |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | No flags or external authority changed |

**Review:** Self review before PR; no independent review claimed. Owner-bound conversation prefix only comes from server dispatcher and is already protected at worker-use context source validation. Existing standalone Agent retrieval intentionally unchanged. The cursor in merged CW-07 remains message-based, not per-Agent-event. No new schema, orchestration engine, ledger, provider credential, grant or rollout.

**Next exact action:** Open draft PR for `codex/cw08-explicit-conversation-context-20261013`, compare exact PR SHA and required CI, resolve failures without weakening tests, seek independent review and only then classify repository verification. Continue an independent CW-08 lifecycle or CW-09 browser capability slice without merging or production activation.

## CW-07 Architecture/Core Agent — owned activity cursor continuation (13 October 2026)

**Fresh repository evidence:** `main` at `4b369fa99b9a7c4784f5060aa3399a58e340815f`. [CW-08 source-pin PR #384](https://github.com/rumman52/Shuddho/pull/384) is **merged**, and its exact-final-head [CI #38395801164](https://github.com/rumman52/Shuddho/actions/runs/38395801164) passed. Main CI [38400940687](https://github.com/rumman52/Shuddho/actions/runs/38400940687) was in progress at bootstrap; a skipped separate run does not count as green. There were no open PRs when selecting this new bounded slice.

**Active task:** CW-07 — durable owner-bound cursor pagination for the read-only continuous-chat activity projection. Main only exposed latest-N activity, so older launched work cards were missing on reconnect for longer conversations. The current slice adds `after=start` + forward owner/conversation-bound cursor, `next_cursor`, `has_more`, HTTP support, frontend paginated replay and regression tests, without another run ledger or side effect. Omitted `after` retains latest-N polling for run-state changes with no new message. The cursor is an owned read checkpoint, not a permission grant or durable all-events stream.

**Review branch:** `codex/cw07-owner-bound-activity-cursors-20261013`. **Base:** `4b369fa99b9a7c4784f5060aa3399a58e340815f`. **Initial implementation/test:** `99d3934803227721f4d2e0dac71b65686be52329` (prior to documentation). **Contract:** [CW07_OWNER_SCOPED_ACTIVITY_CURSOR_2026-10-13.md](CW07_OWNER_SCOPED_ACTIVITY_CURSOR_2026-10-13.md). PR and final exact-head CI must be read from GitHub once created.

| Acceptance item | Current code/integration | Remaining qualification |
| --- | --- | --- |
| CW-05 message ownership | Existing main source and prior CI | Operated replay, deletion and PostgreSQL races |
| CW-06 routing/admission/cancel | Merged CW-06 #383 and durable dispatch | Steering, terminal-order and operated cancellation |
| CW-07 unified activity | Owner cursor + frontend history replay on current review branch only | Exact-head CI, independent review, mobile/keyboard/reconnect and live run-state proof |
| CW-08 workspace/memory | Merged pinned-source #384; existing memory edit/delete and manifest | Source-use races, bounded context + human multilingual acceptance |
| CW-09 browser | Broker/workers exist but no registered v3 `browser.read` | Gated typed tool, SSRF, takeover, worker tests |
| CW-10 reviewed generated code | Sandbox exists | Immutable approved proposal-to-execution envelope |
| CW-11 skill manifests | Static skills exist | Reviewed manifest validation and authority subset |

| Evidence level | CW-07 cursor slice |
| --- | --- |
| Implemented | Yes, only on isolated review branch |
| Repository-verified | Pending exact-final-head mandatory GitHub Actions; no local full-repo pytest/build |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No authority, provider, flag, paid resources or production changes |

**Next exact action:** Open draft PR for CW-07 branch, inspect final-head `coworker`, `test-and-build` and `ci-merge-gate`, correct test/source issues and seek independent code review. Do not merge automatically. Continue remaining dependency-ready CW-08/CW-09 implementation separately after evidence checkpoint. No success percentage inferred from task labels.

## CW-08 Architecture/Core Agent continuation — 13 October 2026 (Asia/Dhaka)

**Source baseline:** `main` at `fb3c8994edc2d6a7db2781b9a798a21a7a9beec6`. Main CI [38393963804](https://github.com/rumman52/Shuddho/actions/runs/38393963804) was in progress when inspected; no claim of successful final-head CI is made for it. Earlier CW-06 [PR #383](https://github.com/rumman52/Shuddho/pull/383) is **merged**; final PR SHA `1312877604520fec49e00970d12ff14a4b9c7294` passed [CI 38391641647](https://github.com/rumman52/Shuddho/actions/runs/38391641647). No open PRs appeared before this CW-08 work.

**Selected task:** CW-08 worker-time conversation source-pin enforcement, scoped to a single reviewable code slice. `ConversationMessage.selected_sources` already preserves exact version/hash/owner selection, but `AgentRun.input_versions` records only IDs and `ContextService._run_and_sources` previously trusted the *current* DocumentVersion row at worker time. A same-ID in-place changed digest/version could bypass the admitted selection. The new shared validator revalidates the original owner-scoped message, document pin, run link and live resource status both at `AgentRepository.worker_run` entry (v1/v2/v3) and at planner context load; pre-existing non-conversation runs retain their former logic.

**Branch:** `codex/cw08-conversation-pinned-context-20261013` from `fb3c8994edc2d6a7db2781b9a798a21a7a9beec6`. **Implementation/test head:** `cea2c57eeb1ddd2c38526c9a2e8475333526a11f` before checkpoint update. **Task contract:** [CW08_CONVERSATION_SOURCE_BINDING_2026-10-13.md](CW08_CONVERSATION_SOURCE_BINDING_2026-10-13.md). **Review PR:** [draft #384](https://github.com/rumman52/Shuddho/pull/384); exact final head and CI are verified on the PR.

| Acceptance task | Source evidence level | Remaining gate |
| --- | --- | --- |
| CW-05 owner-scoped messages | Existing implementation and prior main CI | Staging race/replay/deletion qualification |
| CW-06 bounded message dispatch/cancel | Merged CW-06 routing repair, previously green exact-head CI | Full steering and operational cancellation proof |
| CW-07 continuous activity | Existing UI and owner-scoped activity projection | Cursor/reconnect/mobile and staging qualification |
| CW-08 context/memory | Existing source and memory controls; new exact conversation pin worker check on review branch | Final-head CI, live revoke/replacement race, remaining bounded context/memory lifecycle and quality review |
| CW-09 browser read | Existing broker/isolated worker, no registered Agent `browser.read` | Gated typed integration and isolated-worker testing |
| CW-10 reviewed generated code | Existing sandbox control plane | Immutable reviewed code proposal/approval/execution binding |
| CW-11 skill manifests | Existing static versioned work skills | Reviewed manifest hashes, authority subsets and compatible rollback |

| Evidence level | CW-08 source-pin task |
| --- | --- |
| Implemented | Branch-only implementation + focused regression cases |
| Repository-verified | Pending required exact-final-head PR CI; local full-repository pytest not run |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | None; no grant, provider or rollout changed |

**Next exact action:** Inspect draft PR #384 exact-PR-head `coworker`, `test-and-build` and `ci-merge-gate`; fix source defects without silencing tests; obtain independent review. Then continue remaining dependency-ready CW-08 and CW-09 code slices in separate PRs. No merge or production activation is authorized by this execution prompt.


## Current Architecture/Core Agent checkpoint — 13 October 2026

Refreshed default branch: `main` at `339d6924b244c0bb1641764dabd68c4f55488bb3`. Exact-main CI [run 38338728994](https://github.com/rumman52/Shuddho/actions/runs/38338728994) passed its coworker, test-and-build and merge-gate jobs. No open PR was returned before beginning this slice.

CW-06 contract gap: the `report.create` registered tool declares public capability `report` but internal durable task skill `report_email`. The old single-tool router emitted the internal skill into public route decisions while `tests/fixtures/core_agent_route_cases.jsonl` expects `report`. This finding is based on current canonical tool/route source, not historical completion percentages.

Review branch `codex/cw-core-router-report-contract-20261013`, [draft PR #383](https://github.com/rumman52/Shuddho/pull/383), initial implementation/test head `aeb00b2cdd5994e3e8236bc049d2f916f9ad7862`. Changed only the single-tool router capability mapping to server-owned route intent and added a regression asserting that the public `report` route still uses `report.create` and the legacy `report_email` skill. The reviewed task contract is [CW06_REPORT_ROUTE_CONTRACT_2026-10-13.md](CW06_REPORT_ROUTE_CONTRACT_2026-10-13.md).

| Evidence level | Status |
| --- | --- |
| Implemented | On isolated review branch; not integrated into `main` |
| Repository-verified | Pending exact-final-head PR CI; local package tests not run in this GitHub connector environment |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | No provider, capability, or production activation |

Scope: CW-05–CW-11 Architecture/Core Agent. CW-01–04 supply prerequisite evidence, not renewed assignments. The merged CW-09–14 qualification registry is a default-off metadata foundation, not a working browser/generated-code/skill runtime or live release qualification. Preserve prior transaction checkpoints below as historical. Pending CW-08 context/memory integration and CW-09–11 actual implementations must be rechecked against live source; staging/billing/provider/human evidence cannot be inferred from CI.

Acceptance inventory based on inspected `main` source and available CI (per-task staging and full acceptance remain separate):

| Task | Main source / current state | Next unmet acceptance / evidence |
| --- | --- | --- |
| CW-05 | Conversation schemas, repository and durable message tests exist; main CI includes PostgreSQL conversation races | Complete operated owner/deletion/replay qualification on a frozen staging release |
| CW-06 | Atomic conversation dispatch and revision-checked cancellation exist; one report public-route mismatch repaired only on PR #383 | Verify PR exact-head CI; inspect missing/non-mutating steering contract and late-result precedence |
| CW-07 | Conversation UI and read-only activity projection exist | Verify reconnect/mobile flows and add durable owner-scoped activity cursor if canonical contract remains unmet |
| CW-08 | Source admission validation and read-only workspace manifest exist | Prove worker-use revocation/version checks, reviewable memory edits/deletion and bounded multilingual context |
| CW-09 | Isolated browser broker/worker foundation exists; no `browser.read` in core `agent_tools.py` | Register and safely wire typed default-off read-only tool; prove SSRF/ownership/takeover boundaries |
| CW-10 | Isolated sandbox control plane exists | Store immutable generated-code proposals and exact reviewed approval binding before execution |
| CW-11 | Static versioned `WorkSkill` definitions exist | Validate reviewed manifest hashes, tool authority subset and compatible rollback after CW-09/10 |

These are discovery statuses, not assertions that each full CW acceptance suite has passed. A successful green CI run on a revision does not substitute for missing staging, adversarial or human quality evidence.

Next exact action: inspect exact-head GitHub Actions on PR #383 and obtain independent review; if a check fails, repair code without weakening expected behavior. Then choose the next smallest dependency-ready CW-08/09/10/11 capability slice while keeping external activation gated.


## Current Transactions qualification recovery — 13 October 2026 (Asia/Dhaka)

Refreshed main: `fb1a08059cd242f5da4d72dbf72da0c6971bfe30`, latest merge PR #379.
PR #375 process recovery, #376 attestation chronology/file binding and #377's
checkpoint are now merged. There were no open PRs at the start of this continuation.
[Exact-main CI 38292932568](https://github.com/rumman52/Shuddho/actions/runs/38292932568)
failed both required upstream jobs: lightweight collection imported optional
SQLAlchemy without a guard, and Temporal `before_claim` recovery hit the workflow
deadline. The merged boundary/reconciliation tests were absent from the explicit
heavyweight transaction safety command.

Branch `codex/transactions-ci-recovery-20261013` repairs that qualification boundary:

Review: [PR #380](https://github.com/rumman52/Shuddho/pull/380). Initial implementation
head: `7ae84f757a696116f3aade9aaeeced296b7078a3`. This checkpoint precedes the final
required CI result; the PR records its final head/run and review readiness.

- Optional-dependency collection follows the existing lightweight/heavyweight split.
- All newly merged execution, reconciliation and mutation-guard test modules are
  mandatory in the safety JUnit report, with collection and zero-skip checks.
- A parent-owned barrier keeps the restarted real Temporal worker connected but
  not polling while only the interrupted activity timeout/first retry is advanced.
  Automatic result time skipping is then disabled. Production workflow timeouts,
  authorization, durable claims, receipt validation and uncertainty remain unchanged.
- Enabling the omitted reconciliation test reproduced a nonexistent fixture field
  (`SimulatedGoogle.provider`). Its corrected receipt assertions check the actual
  configured Google provider, confirmed state, one send and another owner's 404.
- Added execution diagnostics identify the exception class before the Temporal
  activity redacts its error; that diagnostic prints no raw SQL parameters,
  credentials or message contents.

Local verification: the lightweight project suite passed **1,052 tests, 65 optional
skips** (8.56 seconds); the final combined process/Temporal/HTTP/safety/boundary run
passed **41 tests with one PostgreSQL-only admission-race skip** (60.14 seconds).
The mandatory safety subset passed **25 tests, zero skips** (4.88 seconds), and
its gate confirmed collection from all five required modules. Neighboring transaction/
action/permission/gate checks passed **103 tests** (46.58 seconds).
The initial combined run also failed before its first crash barrier;
four isolated Temporal cases and the final combined run passed after adding safe
setup diagnostics. These local SQLite runs do not establish PostgreSQL qualification.
The required exact-head CI must run all 17 process cases on real PostgreSQL and
all 25 transaction safety cases with zero mandatory skips before review readiness.

| Evidence level | Current status |
| --- | --- |
| Implemented | Bounded test/CI repair exists on the review branch |
| Repository-verified | Pending exact final-head required CI; record its SHA/run in the PR |
| Staging-verified | Not established by this continuation |
| Production-qualified | Pending operated matrix, selected-provider evidence and release reviews |
| Activated | No capability/provider/production activation |

PR #379's `TransactionMutationGuard` is an unused, process-local qualification helper:
its unit tests do not establish distributed provider deduplication. Production
authority remains the existing durable ExternalAction boundary. Complete Transactions
qualification still requires the full sixteen-fault operated staging matrix and
selected real-provider receipts/counters; shopping/travel registration remains disabled.

Next exact action: independently review this repair, inspect exact final-head CI,
then collect the controlled staging/provider evidence on a frozen matching release.
See [the bounded task plan](../superpowers/plans/2026-10-13-transactions-qualification-recovery.md).

## Historical process-recovery checkpoint — 12 October 2026

Reviewed main `1c41907594dd8dd93a6eac747494d5491587b709` (PR #373); merged-main CI #1368
passed `test-and-build`, `coworker` and `ci-merge-gate`. Draft PR #374 remains a separate
offline CW-02–04 witness-gate proposal. Historical entries below predate newer merges.

Branch `codex/cw02-transaction-process-recovery-20261012` implements the next CW-02 slice:
counted real HTTP to a loopback provider, abrupt disposable worker loss at four commit/
dispatch boundaries, the same four boundaries in real Temporal activities, six provider
failure/uncertainty cases, PostgreSQL public-API duplicate admission, hard API loss after
commit and actual Temporal-server unavailability/outbox recovery. Seventeen executable
tests are mandatory in the heavy CI job, with PostgreSQL required and zero skips allowed.

Review PR: [#375](https://github.com/rumman52/Shuddho/pull/375). Initial implementation
commit: `b8a5a2b2130991b383cc8a9bfd16472b903a8ed4`; the follow-up also binds restarted
Temporal worker readiness before unlocking its virtual retry clock. The PR check suite
records the exact final head and required CI evidence; this checkpoint precedes that result.
CI run `38240791655` remained in rendering dependency installation for more than fifteen
minutes. The final follow-up makes apt/debconf/needrestart noninteractive and bounds the
installer to ten minutes, triggering a fresh runner without removing any required check.
The cause of the stalled installer was not observable from unfinished GitHub job logs.

The final focused local process/Temporal/HTTP plus existing safety/matrix run passed
35 tests with one explicitly PostgreSQL-only skip (46.14 seconds). The new module itself
passed sixteen tests and skipped its PostgreSQL admission race. Surrounding transaction/
permission/action checks passed 97 tests (38.63 seconds). Exact-head full CI with real
PostgreSQL and zero mandatory skips remains required before repository qualification.

No production source interface, migration, provider authority or activation changed.
JUnit records are integration evidence with a simulated provider, not live certification.
CW-01 and CW-05–07 foundations are on main; CW-08 continuity remains partially qualified.
CW-02–04 full operated staging, exact provider reviews and CW-14–20 release requirements
remain unfinished. Do not activate transactions from this slice alone.

Next: review the new source/test/CI changes, verify exact-head CI, then execute the full
sixteen-fault matrix on a frozen controlled staging release with independent provider
counters. See [the task contract](CW02_PROCESS_RECOVERY_TASK_2026-10-12.md).

## Historical checkpoints

Updated: 11 October 2026 UTC. Base: `c6389b3702aae93019c2ec5643f4e4d5dd76ea2a`.
The coding kit from PR #362 is merged.

## Three-stage execution

| Stage | Tasks | Status |
| --- | --- | --- |
| 1. Safety and operated foundation | CW-01..04 | CW-01 implemented and locally verified; full recovery/deployed qualification pending |
| 2. Continuous coworker | CW-05..13 | CW-05 in progress; later tasks planned |
| 3. Transactions and production pilot | CW-14..20 | Provider/live review and operated evidence required; not qualified or activated |

## CW-01 result

Branch: `codex/cw01-safety-foundation-20261011`.
Repairs invalid fixtures/assertions without changing production behavior; same binding
replays and another action conflicts. Simulated real-transport tests count dispatches and
applied mutations after a lost reply, check actual approval/claim expiry and exact receipts.
The existing coworker CI job runs a separate mandatory suite with locked extras,
JUnit upload and empty/skip/failure/error/required-module rejection.

Verification:
- Original three tests reproduced three failures before reaching the safety boundary.
- Final focused transaction/gate suite: **44 passed, zero skips**, 17.18 seconds.
- Surrounding action/permission/personal-transaction suite: **57 passed, zero skips**, 25.92 seconds.
- Chaos-only CLI gate: **5 collected, zero skips/failures/errors**.
- Fresh review: no Critical findings; one Important mandatory-collection gap fixed
  with a failing regression, required-module check and separate reports.
- Deferred minor: successful replay checks applied mutations but could also assert
  HTTP dispatch count; lost-reply coverage already checks both.
- Exact-head remote CI pending. Local checks do not establish complete repository CI.

Existing PR #363 is open/conflicted at inspected head
`3ba85a5c66582dc9cd27a5e7653291ec97c099f4`; it still calls unsupported
interfaces and installs missing requirements.txt. This main-based branch replaces that
repair; maintainers should retain one implementation, not merge both conflicting patches.

## External qualification blockers

Fresh local CW-03 preflight: `blocked_external: RENDER_API_KEY REQUIRED`.
This execution has no Render connector, staging synthetic identity, Temporal credentials
or private S3 access. Historical PA-10 billing/worker observations were not re-certified.
CW-02 needs the full public API/PostgreSQL/Temporal process-interruption matrix.
CW-04 requires matching frozen API/worker/model/rollout identity.
CW-12..20 additionally require live connector/push/provider access, concrete registered
shopping/travel providers, human Bangla/English and security review, real cost/load,
restore/rollback and an operated availability window.

## Scope and next action

CW-05 may proceed independently while staging access is blocked. Use existing task/run
outboxes and ledgers for CW-06/07. Preserve all capabilities default-off; this work has
not activated production, broadened provider authority, provisioned paid infrastructure,
or executed external sends/purchases. All CW-02..20 acceptance gates remain unfinished
until their exact evidence passes. Refresh main/open PRs/CI before resuming.

## Latest five-commit security and integration review — 12 October 2026

Reviewed main head `ec41ac8b55de99a50e8214a58b22bfc797ae5256` and the four preceding main commits
(`79070ea`, `039093b`, `bb77b28`, `b90b6a4`).

- CW-05 PR #368 is now merged into main. PR #369 marked merged **into the CW-05 feature branch**, not main, so CW-08 source revalidation did not reach main from that merge.
- Repaired CW-05 source selection to reject an expired uploaded document version before message admission; previous behavior pinned expired documents.
- Ported CW-08 read-only, owner-bound document/artifact source revalidation and its seven tests to a new main-based review branch. This is a foundation, **not yet connected to CW-06 admission**.
- Added both the CW-08 unit tests and the PostgreSQL conversation-race module to mandatory coworker CI gating.
- Source changes remain default-off; exact-head CI and PostgreSQL migration/race evidence must be independently reviewed.
- CW-01 source safety foundation remains implemented. CW-02–04 operated staging checks and CW-06/07/08 full task-level acceptance criteria remain incomplete.
- Do not turn on conversations, transactions, or external-action providers from this patch alone.

Next: review/qualify this branch, merge through normal protections, implement CW-06 atomic admission/steering with source validation at the same transaction boundary, then CW-07 UI and complete CW-08 workspace/context lifecycle.
