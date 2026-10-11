# Complete Shuddho roadmap in three stages

Three stages organize all twenty CW tasks; each stage ends only when its evidence
passes. SPEC.md, ROADMAP.md and the detailed task plan remain authoritative.

| Step | Tasks | Deliverable | Exit gate |
| --- | --- | --- | --- |
| 1. Safety and operated staging | CW-01..04 | Executable safety tests, complete fault/recovery harness, matching API/worker and frozen release | Required CI with zero mandatory skips; all sixteen fault outcomes; owned workflow/reminder/restore/rollback scenarios |
| 2. Continuous coworker | CW-05..13 | Durable chat, existing run/task links, activity UI, authorized sources/memory, typed browser/code tools, reviewed skills and useful proactivity | Race/replay/owner/revocation/cancellation checks, verified receipts, old histories, real schedules/push and Bangla/English review |
| 3. Transactions and qualified pilot | CW-14..20 | Qualified transaction providers, human quality/security review, measured economics/availability, recovery drills and rollout | Exact approval and receipts, one mutation per identity, complete release evidence and authorized bounded activation |

## Step 1

Install the locked dependencies in a dedicated branch:

```bash
git clone https://github.com/rumman52/Shuddho.git
cd Shuddho
git switch -c coworker/next-task
uv sync --frozen --group dev --extra coworker
npm ci
```

Refresh main, open PRs and exact-head CI. CW-01's main-based repair is PR #364;
it replaces the conflicting repair in #363. Do not automatically merge.
CW-02 exercises public API/PostgreSQL/Temporal with process interruption before
and after claim, submission and receipt commit. Count provider requests and applied
mutations separately; defining sixteen matrix rows does not run those failures.

CW-03 needs Render staging access, a persistent worker, PostgreSQL, Temporal TLS/
namespace credentials, private S3 access, backend DeepSeek configuration and owned
synthetic identities. Use deployment secret management; never paste keys into chat.
Inspect the existing prerequisite and release-freeze scripts, then use their
prepare/deploy/verify contract. Paid provisioning requires separate authorization.
CW-04 runs existing workflow/reminder/recovery/restore/deletion/rollback collectors
against the same frozen release. Missing access remains blocked. CW-05 can develop
independently after the safety repair while staging access is unavailable.

## Step 2

CW-05 persists private conversations. CW-06 atomically links each message to existing
work/outboxes and adds explicit revision-checked steering/cancel. CW-07 exposes chat
and unified activity, reconnecting without dispatching twice. A freeform yes grants
no consequential-action authority.

CW-08 revalidates source owner/version/hash/deletion at actual use and supplies
reviewable memory controls. CW-09 adds a default-off read-only browser tool through
the existing broker. CW-10 stores immutable generated-code proposals and executes
only the reviewed source hash/limits in existing isolated compute. CW-11 keeps
skill manifests code-reviewed and unable to expand provider/tool authority.
CW-12/13 qualify real consented scheduling/events, quiet-hour digests, device push
and human Bangla/English usefulness. Local tests cannot prove real device delivery.

## Step 3

CW-14 qualifies existing negotiation/no-payment reservation workflows. CW-15/16
require concrete registered shopping/travel providers and user-present hosted
handoffs. Handoff creation is not purchase/booking success. Reconcile uncertain
submissions read-only; never blindly resend a claimed mutation.

CW-17 records human-accepted outcomes with counts/language breakdown and independent
security review. CW-18 measures actual costs/load and an explicit availability SLI
over an operated window; CI does not certify 99.9%. CW-19 runs deployed restore/
rollback/trust-enforcement drills. CW-20 binds every gate to exact source/API/worker/
model/rollout identity and presents a concrete, authorized bounded activation.

The default-off conversation scaffold reserves activation schema 33. Its collector
and ledger support remain CW-20 work; activation is blocked until implemented and
qualified. Do not manufacture an attestation to bypass missing evidence.

## Instruction to use with your coding chatbot

```text
Work in https://github.com/rumman52/Shuddho.
Read AGENTS.md, .agents/skills/shuddho-engineering/SKILL.md and the coworker
SPEC/ROADMAP/PROGRESS documents. Follow the CW task plan. Refresh main/open
PRs/exact-head CI and resume the first dependency-ready unfinished task.
Implement one bounded task in a dedicated branch; reproduce defects, write
meaningful acceptance tests, preserve permission/idempotency/recovery contracts,
run appropriate checks, obtain fresh review and open a draft PR. Update PROGRESS
with exact branch/SHA/PR, checks, evidence level, blockers and next action.
Continue independent authorized work when live inputs are missing. Keep
implemented, repository-verified, staging-verified, production-qualified and
activated separate. Never invent evidence or mark all twenty tasks done because
the roadmap exists. Do not automatically merge, provision paid services,
activate production, send external messages or execute purchases.
```

Use PROGRESS.md to resume; use the full task's dependencies/acceptance criteria
when this overview omits an implementation detail.
