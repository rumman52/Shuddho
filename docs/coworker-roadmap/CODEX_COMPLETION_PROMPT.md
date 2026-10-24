# Shuddho — Codex implementation and verification mandate

Copy this document into Codex in your code editor, or ask Codex to read this file
and carry out its mandate. It is an execution brief, not a completion certificate.

## Mission

Work on `https://github.com/rumman52/Shuddho`. Establish what is actually
implemented, identify the highest-impact incomplete requirements, implement the
dependency-ready work, and verify the resulting behavior. Continue beyond an
audit or plan into code, tests, reviewable commits and an evidence-backed handoff.
Use careful engineering judgment; optimize for correctness and useful outcomes,
not commit counts, artificial completion percentages or the number of tools used.

The primary scope is architecture A-01..A-04 and core agent C-01..C-06, with
personal-context P-01..P-03 and verification/release V-01..V-04 as required
acceptance dependencies. Preserve the existing CW/PA/TX task identifiers.

The user authorizes repository inspection, local development, disposable local
test resources, focused fixes, regression tests, documentation and draft PRs.
Proceed autonomously within that scope. Reuse any explicit session authorization
for additional actions. Do not infer permission to activate production, incur new
cloud spending, alter unrelated account policies, send real messages, reserve
restaurants, buy products or book travel. Prepare a concrete reviewed action when
an external step needs authorization; ask only for the missing boundary.

## 1. Establish current truth before choosing work

Read root `AGENTS.md` and any instructions applicable to touched paths. Then read:

1. `.agents/skills/shuddho-engineering/SKILL.md`;
2. `docs/coworker-roadmap/README.md` and `SPEC.md`;
3. the latest entries in `docs/coworker-roadmap/PROGRESS.md`;
4. `docs/coworker-roadmap/ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md`;
5. `docs/coworker-roadmap/ROADMAP.md` and `THREE_STEP_EXECUTION.md`;
6. the relevant task in `docs/superpowers/plans/2026-10-12-coworker-evolution.md`;
7. `docs/coworker-roadmap/V01_REQUIRED_GOVERNANCE_GATE_2026-10-24.md` if present.

Load relevant sections progressively; do not repeatedly fill context with old
checkpoint history. Apply installed debugging, context-engineering, testing and
review skills when they fit the task. If a tool/plugin is unavailable, state that
and use an authorized equivalent. Do not claim an unavailable plugin was used.

Inspect the workspace before editing:

```bash
git status --short
git remote -v
git branch --show-current
git rev-parse HEAD
git fetch origin
git log -8 --oneline origin/main
git diff --stat origin/main...HEAD
```

Preserve user changes. Do not reset, clean, force-push, or overwrite unrelated
work. Use an isolated branch/worktree when needed. Verify the repository identity
before writes. Refresh open PRs, review threads, exact PR head, default-branch SHA,
CI job results, rulesets and current relevant issues through GitHub/`gh`.

Historical baseline only: on 24 October 2026 main was
`ddb58a308b9cd28de791c911bc1338f12d7bed5c`, after PR #556. Main CI
`39954055394` passed the code and coworker jobs but failed `governance-audit`.
The branch endpoint reported `protected=false`, and rulesets were empty. These
facts MUST be refreshed; do not treat them as today's state in a later session.

The branch `fix/v01-required-governance-gate-20261024` adds audit-result propagation,
regression tests and an unapplied native ruleset payload. Check whether this work
is open, merged, superseded or absent before recreating it. A draft PR is not main.

## 2. Produce a requirements-to-evidence inventory

Use the existing acceptance inventory as the canonical record. Refresh its dated
summary instead of introducing a competing completion ledger. Cover every row:

| ID | Acceptance area |
| --- | --- |
| A-01 | Authoritative state ownership, tenant isolation and trust boundaries |
| A-02 | Temporal/outbox recovery, cancellation and duplicate-effect prevention |
| A-03 | Schema/API compatibility, old-history replay and rollback |
| A-04 | Current tool grants, revocation, expiry and worker authority |
| C-01 | Runtime v3 admission, reasoning, execution, observation and verified completion |
| C-02 | Real browser content capture, provenance and network isolation |
| C-03 | Credential-free autonomous browsing and receipt integrity |
| C-04 | Exact reviewed model-generated code and isolated execution lifecycle |
| C-05 | Reviewed skill publication, version selection, drain and rollback |
| C-06 | Exact approved external actions, uncertainty and reconciliation |
| P-01 | Durable conversations, dispatch identity, steering and activity |
| P-02 | Owner/version/purpose-scoped context, provenance, revocation and deletion |
| P-03 | Real study/work/context-separation/recovery scenarios |
| V-01 | Final-head CI, independent review and effective native merge protection |
| V-02 | Evidence-bound runtime and worker capability eligibility |
| V-03 | Grounded bilingual quality, safety, economics and measured SLOs |
| V-04 | Pinned release evidence, independent release review and controlled activation |

For each row record: intended behavior; concrete source paths/symbols; executable
test names; observed result and tested SHA; PR/main integration state; deployed
identity if checked; missing acceptance evidence; dependencies; next action.

Keep these dimensions separate:

- **Implementation:** absent / partial / present. Trace the real caller-to-worker
  path, persistence and receipt handling. A class, stub, README or test double is
  not proof of a reachable implementation.
- **Verification:** not run / failed / local verified / CI verified / staging
  verified. Give counts, skipped coverage and exact evidence references.
- **Release:** unqualified / qualified / activated. Qualification and activation
  need their own evidence and authority; neither follows from green CI alone.
- **Gap type:** missing implementation / concrete defect / missing test /
  missing operated evidence / external dependency / human review / authorized
  future scope. Mark uncertainty explicitly rather than guessing.

Do not classify all 17 rows as absent merely because none is fully qualified.
Do not classify them as finished because individual PRs merged. Trace tests to
the actual acceptance condition and check that CI collected and executed them.
Search default-off controls, runtime registry entries, TODOs and placeholders as
leads, then inspect their consumers. A text search alone cannot prove absence.

## 3. Prioritize by concrete risk and dependencies

Order work by unauthorized effects/data exposure, state corruption/duplicate
effects, recovery correctness, core user workflows, then quality and efficiency.
Choose one bounded, demonstrable gap per PR. Explain its trigger, impact,
root cause, acceptance test and why it precedes alternatives.

### First: release-control truth, without endless diagnostic-only patches

- Refresh issue #484 and #339, native policies and exact-head review/CI evidence.
- Verify the aggregate gate propagates main-push governance failure, cancellation,
  unexpected skip and missing results, while preserving independent PR review.
- Inspect `infra/github/main-ruleset.json` and its accompanying operator runbook.
  It is desired configuration, not an applied GitHub policy. If authorized admin
  tooling is available, compare and apply the reviewed change without weakening
  stronger existing rules. Otherwise prepare the exact diff and name the access
  blocker. Never put an administrator token in a PR-controlled workflow.
- GitHub can hide `bypass_actors` from a read-only caller. Missing fields mean
  unverified, not an empty bypass list. Use a trusted administrator evidence path;
  do not make the audit pass by deleting the check or assuming permissions.
- Verify pending/red CI, absent/stale approval and unresolved threads block merge,
  and a current reviewed green head is eligible. Retain real IDs and timestamps.
- Fix concrete source defects, but do not keep polishing audit scripts while the
  real blocker is unapplied native protection or missing human review. Continue
  useful independent core work and report the external blocker plainly.

### Next: recovery and architecture correctness

Reconcile existing coverage before adding code. Exercise real public admission,
PostgreSQL transactions, Temporal histories/outboxes, worker claims and receipts.
Audit mixed-version migration/old-reader behavior and retained-schema rollback.
Preserve committed decision replay without creating new work after cancellation,
expiry or terminal completion.

Map all 16 failure scenarios to actual executable coverage and missing operated
evidence: model 429, model 500, model timeout; provider 401, 403, 429, 500; malformed
response; database disconnect; S3 disconnect; Temporal outage; worker crash; API
crash; duplicate message; lost provider response; approval after expiration.
Use the existing `scripts/transaction_chaos_matrix.py` and test harness.
Count requests, applied provider mutations and committed receipts separately.
Uncertain mutation outcomes must not cause a blind resend.

### Then: browser, generated code, reviewed skills and context

- Trace `browser.read` through the actual broker/worker/storage path. Check
  public-IP/DNS/redirect/CNAME enforcement, cancellation during connection setup,
  secret/cookie exclusion, exact content digest, owner scope, expiry and deletion.
- Trace model-generated code from immutable proposal through owner inspection,
  source/input hashes, bounded policy, atomic claim, revocation, process-group
  termination and filesystem cleanup. Local process tests are not proof of real
  namespace or deployed egress isolation.
- Verify reviewed-skill version pinning, worker registration, in-flight drain,
  legacy dispatch fences and rollback using real mixed-version workers where
  available. Sandbox-generated code must not register itself as a trusted tool.
- Trace conversation retry keys, steering/cancel revisions, reconnect, selected
  context, use-time grants, provenance, deletion and cross-project isolation.
  Memory and retrieved text cannot grant authority.

### Staging, providers and useful outcomes

Refresh issue #291 and actual staging API/worker/storage/Temporal/auth identities.
Do not assume old missing resources are still absent. Use the existing prerequisite
and release-freeze tooling. Prepare, deploy only within authorization, verify the
same exact source/configuration on API and workers, and require a genuine frozen
release before collecting final evidence. Use synthetic accounts and disposable
resources; never substitute invented provider observations.

Verify four realistic scenarios: student study work, office grounded artifacts,
cross-project context separation, and interruption/reconnect/recovery. Validate
artifact contents, references, usability, owner isolation and truthful UI status.
For a simple scheduled reminder, preserve the intended lightweight path: one
occurrence/delivery, zero new Agent runs, and `run_id=null`.

Refresh issue #378 and the actual `ACTION_SPECS` registry. Shopping/travel review
contracts are not live providers. Implement a concrete adapter only after a
provider is selected and its current primary API contract is verified. Require
registered operations, constrained credentials, approval binding, provider
conformance, user-present hosted handoff and exact completion receipts. A handoff
is not a purchase/booking. Never fabricate provider access or make a live booking
as an ordinary test.

Measure live-model Bangla/English task quality with a frozen rubric, counts and
human review. Keep mocked/curated contract tests distinct from live outcomes.
Preserve the stricter current thresholds. Measure actual cost/latency and define
availability denominator, eligibility, window and exclusions before an SLO claim.
CI and chaos tests cannot establish 99.9% availability.

## 4. Implement with controlled scope

For each chosen task:

1. Refresh the branch base and check whether another PR already implements it.
2. Create a task contract using `docs/coworker-roadmap/TASK_TEMPLATE.md`.
3. Reproduce the defect or write the unmet acceptance test. Observe the expected
   failure against unchanged production code; distinguish test setup failures.
4. Make the smallest coherent fix. Reuse existing interfaces and authority.
5. Test positive behavior and the actual failure boundary: races, retries,
   revocation, stale state, malformed input, cancellation or process death as
   applicable. Avoid tests that only repeat implementation constants or mocks.
6. Review correctness, compatibility and security. Obtain a fresh independent
   code review when available; resolve material findings. An AI review is not
   independent human approval in GitHub.
7. Commit only intended files and open/update a draft PR. Preserve real newlines
   in descriptions; summarize problem, behavior, tests, limitations and blockers.
8. Inspect final-head CI after the last change, including documentation commits.
   Keep the PR unmerged while required checks/review/native controls are unmet.

Preserve FastAPI, PostgreSQL, Temporal, private object storage and the existing
run/action/outbox ledgers. Do not add another orchestrator, a duplicate authority
store, broad permissions or a large rewrite to solve a bounded problem.

Preserve multilingual/Bangla writing, local fallback engines, explicit provider
failure diagnostics, backend-only DeepSeek configuration and explicit Gemma
rollback. Do not silently switch model providers. Reserve parent/child budgets
and bound waits/retries. Completion must be backed by verified output, not prose.

## 5. Verification discipline and commands

Inspect current lockfiles/workflows first. Typical repository setup is:

```bash
uv sync --frozen --group dev --extra coworker
npm ci
```

For the governance slice, if these files still exist:

```bash
uv run pytest tests/test_main_protection_audit.py tests/test_v01_native_protection_audit.py tests/test_v01_merge_evidence.py tests/test_independent_review_gate.py tests/test_v01_remaining_governance_auth_redirects.py -q -rs
```

Then run the applicable project checks, matching CI's dependency/profile setup:

```bash
uv run pytest -q -rs
uv run python -m scripts.release_contract_check
npm test
npm run build
node --test scripts/browser_worker_policy.test.mjs scripts/browser_pinned_proxy.test.mjs
git diff --check
```

The exact current `.github/workflows/ci.yml` is authoritative for mandatory
PostgreSQL/Temporal, sandbox, browser, routing and quality commands. Start only
disposable local services with clearly isolated test databases; never point
fault-injection tests at production. Use the existing mandatory JUnit gate so
missing collection/skips cannot masquerade as a pass. Do not lower thresholds,
weaken assertions or add skips merely to make CI green.

For each claim retain command, exit code, pass/fail/skip counts, source SHA,
runtime/dependency profile and evidence location. Report unrelated failures by
name and distinguish baseline defects from regressions. A focused green suite
does not prove the full suite passed. A lightweight run with missing integration
extras does not qualify PostgreSQL/Temporal or browser/sandbox deployment safety.

Inspect GitHub job results, not only the workflow headline. Pending, cancelled,
skipped, failing, absent and successful are different states. Post-merge success
does not retroactively establish pre-merge review or enforcement. Never reuse
evidence from an earlier head after a source change without explaining its scope.

## 6. Persistence, blockers and completion report

Update the existing PROGRESS.md with the task, branch, base/final SHA, PR URL,
exact checks, evidence levels, unresolved findings and next executable action.
Use concise current summaries; label older checkpoints historical. Keep secrets,
private provider payloads, auth tokens and personal account contents out of logs,
commits, prompts and evidence files. Use references/digests where appropriate.

When blocked, state: exact missing prerequisite, affected acceptance IDs, evidence
for the blocker, responsible role and smallest next action. Continue independent
authorized tasks. Ask for secure setup or a secret reference, never raw credentials
in chat. Do not repeatedly ask for already-granted permission.

Before context exhaustion, save a resumable checkpoint with current diff/branch,
last test result, pending CI/review, blockers and next command. A later session must
revalidate remote state before continuing. Stop at a clean reviewable boundary,
not with unreported partial edits or fabricated completion.

Return:

1. What changed and why, with file/PR links.
2. Exactly what passed, failed, skipped or remains pending, tied to final SHA.
3. Updated status of all 17 acceptance rows, separating implementation from
   verification and release.
4. Remaining code work versus external staging/provider/reviewer dependencies.
5. Whether anything was deployed or activated; state none when none occurred.
6. The next highest-impact task and its acceptance test.

Do not claim the entire workstream complete until every required row has matching
evidence. Do not promise production readiness or a percentage without a defined,
defensible denominator. Do not stop after writing this inventory: begin now with
the current-state audit and complete the first dependency-ready implementation
slice, then continue through independent authorized work.
