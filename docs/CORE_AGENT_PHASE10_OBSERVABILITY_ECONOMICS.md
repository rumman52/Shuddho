# Core Agent Phase 10 — Observability + Agent Economics

Phase 10 moves the bounded Core Agent from evaluation-only confidence to production-operable economics and reliability controls.

## Scope

This phase records one sanitized operational record per durable Agent run with:

- run ID;
- model/model set;
- conservatively accounted tokens;
- end-to-end run latency;
- successful planner inference latency persisted on each Runtime v3 decision;
- child-model inference latency from model attempts;
- tool-call count and tool latency;
- bounded retry count;
- routing decision and planner mode;
- approval-wait count and duration;
- provider-failure count;
- conservatively accounted model cost;
- completion state;
- duplicate attempts;
- uncertain outcomes;
- abandonment/deadline state.

The export is implemented in `scripts/core_agent_observability.py`. JSON preserves per-run operational records for restricted operator analysis. OpenMetrics deliberately contains no labels, user text, account IDs, prompts, recipients, transaction terms, or other user-derived dimensions.

## Dashboard metrics

The Phase 10 export provides run success ratio, tool failure ratio, model failure ratio, p50/p95/p99 end-to-end run latency, model inference latency and tool execution latency percentiles, latency coverage, execution retry rate, separate Temporal dispatch retries, aggregate token consumption and provider-reported input/output token totals when complete, token-direction coverage, cost-estimate completeness, duplicate attempts, `outcome_unknown`, abandoned/deadline runs, and provider failures. Planner latency is sourced from persisted `AgentDecision.latency_ms`; child-model latency is sourced from `ModelAttempt.latency_ms`. Failed planner attempts without a persisted latency are excluded from latency percentiles and lower the reported coverage.

Transactions are measured as a separate safety domain: terminal transaction samples, confirmed transactions, failed transactions, and transaction `outcome_unknown` count/ratio. An uncertain transaction remains a reconciliation event and is never transformed into an automatic retry.

## Per-run production budgets

| Policy | Environment variable | Default |
| --- | --- | ---: |
| Max model calls/run | `SHUDDHO_AGENT_MAX_MODEL_CALLS_PER_RUN` | 12 |
| Max tokens/run | `SHUDDHO_AGENT_MAX_TOKENS_PER_RUN` | 250000 |
| Max tool calls/run | `SHUDDHO_AGENT_MAX_TOOL_CALLS_PER_RUN` | 8 |
| Max runtime | `SHUDDHO_AGENT_RUN_TIMEOUT_SECONDS` | 1800s |
| Max cost/run | `SHUDDHO_AGENT_MAX_COST_MICROUSD_PER_RUN` | 1000000 µUSD |

The model-call and token ceilings span both planner calls and model attempts made by child tasks. Reservations lock the durable Agent run before accounting, so concurrent planner/task calls cannot race past a per-run limit.

The cost ceiling uses the deployment-reviewed `SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS` rate. Unknown or failed calls retain conservative token reservations for economics accounting. The exporter reports a cost estimate from this configured blended effective rate, not a provider invoice. If nonzero token usage has no positive reviewed rate, the per-run and aggregate cost are unavailable (`NaN` in OpenMetrics), never fabricated as zero. Production must set and review the effective rate before enabling monetary stop gates.

Budget failures are explicit: `agent_model_call_limit` (429), `agent_token_limit` (429), `agent_step_limit` (429), `agent_deadline` (bounded runtime failure), and `agent_cost_limit` (402). This turns prior router 429 / budget-402 behavior into server-owned policy instead of an incidental provider error.

## Transaction safety

Transactions remain outside ordinary autonomous Agent tool execution. The Phase 9 router sends transaction intent to the Transactions surface, and Phase 10 observes that domain rather than weakening the boundary.

Consequential actions keep exactly one reviewed execution attempt, immutable reviewed terms/preview binding, provider idempotency where supported, no blind retry after an uncertain provider result, and explicit `outcome_unknown` followed by reconciliation or manual verification.

The Core Agent dashboard counts `outcome_unknown` attached actions for Agent runs, while the transaction dashboard reports transaction-domain uncertain outcomes separately.

## Failure classes from production incidents

- **invalid invocation ID** — tool invocation identity remains server-created and bound to one persisted step; clients/models do not supply executable invocation IDs.
- **TokenLimitExceededError** — planner and child-task usage now share a total per-run token ceiling in addition to existing per-call/task/daily limits.
- **router/provider 429** — call, token, tool and provider capacity limits remain explicit bounded failures and are visible in failure metrics.
- **AgentRouter 402 budget** — the per-run monetary ceiling fails before another provider reservation with `agent_cost_limit`.
- **unknown provider outcome** — conservative accounting is retained and consequential work is not blindly repeated.

## Export

Example operator command:

    uv run --extra coworker python -m scripts.core_agent_observability \
      --window-minutes 60 \
      --json-output /var/lib/shuddho/ops/core-agent.json \
      --prom-output /var/lib/shuddho/ops/core-agent.prom

The JSON file is restricted operator evidence because it contains run IDs. The Prometheus/OpenMetrics file is intentionally label-free and safe for the existing metrics collection path.

## Release evidence

Phase 10 is code-complete only when repository tests for budget enforcement and observability pass, the permanent Phase 9 evaluation suite passes, staging exports contain real Agent and Transaction samples, every `outcome_unknown` has explicit reconciliation evidence, production pricing metadata is reviewed/non-zero before monetary gating, and no CI failure is hidden by an external deployment quota/rate-limit issue.

The previous Phase 9 PR had a CI invocation defect: the evaluation file imported `scripts.*` while CI executed it as a file. Phase 10 changes the CI command to `python -m scripts.core_agent_eval_suite`, preserving the repository root on the module import path.


## Added inference and execution telemetry

Migration `0067` adds nullable `cw_agent_decisions.latency_ms`; migration `0071` adds nullable planner and child-attempt input/output token fields. They are nullable so pre-migration and incomplete provider calls remain readable. Runtime v3 persists planner round-trip latency and aggregates provider-reported prompt/completion counts only when every planner reservation is settled with both directions. Child `ModelAttempt` rows persist each attempt's provider-reported directions. The exporter reports p50/p95/p99 model latency, tool latency and token-direction coverage without substituting reserved totals for directional usage.

The execution retry/failure rate counts planner failures, child-model retries and tool retries divided by model calls plus tool calls in the selected window. Temporal outbox dispatch retries are reported separately because they have a different denominator. Counts and rates remain aggregate; no per-user or per-run labels are added.

## Monitoring and concurrent-load evidence

The exporter and label-free OpenMetrics contract are repository-verified by tests. Metrics receiver ingestion, dashboard panels, alert delivery, threshold calibration and concurrent workload measurements require an operated staging environment and owner-approved SLO/alert thresholds. They are not claimed as verified by this source change.


## Day 8 measured-cost comparison and configuration freeze (development evidence only)

This uses the existing exporter, pilot evaluator and DeepSeek provider. It introduces
no new router, provider, connector, PostHog SDK or agent framework. No model
settings are changed without bounded, quality-preserving evaluation.

### Evidence capture

The normal observability export remains available:

    uv run --extra coworker python -m scripts.core_agent_observability \
      --window-minutes 1440 \
      --json-output /var/lib/shuddho/ops/core-agent.json \
      --prom-output /var/lib/shuddho/ops/core-agent.prom

Create operator report directories with mode 0700 and retain JSON locally behind
access control. OpenMetrics remains label-free. The exporter reports aggregate
input/output token totals only when every planner call is settled with both
provider-reported directions and every child-model attempt has both counts.
Historical, failed-without-usage, interrupted and partially measured calls remain
null; reserved/charged totals are never split or relabeled as provider directions.
Runtime completion does not automatically verify artifacts or human-accepted
outcomes; unverified references stay empty.

The two Day 8 reports must contain exactly the 40 frozen development task IDs
with matching workflow/language and the same provider, model, model-parameter
hash, and tool-surface hash. Baseline and bounded-context/compact-observation
behavior and prompt hashes may differ. Do not evaluate a stronger reasoning
model without approved provider capability and funded budget.

Required report fields:

- Schema: schema_version=1, split=development, exact suite_id,
  source_revision and case_file_sha256 from the existing pilot suite.
- Receipt evidence: generation_identity_verified and
  receipts_independently_verified are explicit booleans; report-level
  provider_usage_receipt_sha256 and review_ledger_sha256 refer to independently
  retained original receipts. Hashes alone do not establish verification.
- Configuration: profile is baseline or bounded_context_compact_observations,
  provider is deepseek, model is the approved actual name, and full lowercase
  model_settings_sha256, behavior_sha256, prompt_sha256 and tool_sha256 are set.
- Each task result includes id, workflow, language, reviewed booleans
  passed/human_accepted/safety_passed, measured input_tokens, output_tokens,
  model_time_ms, tool_time_ms, retry_count and cost_microusd, or null when a
  measurement is unavailable. Include verified_artifact_refs and
  accepted_outcome_ref for accepted results. Do not replace unknown or
  reserved usage with zero or substitute unsupported pricing estimates.

Run the comparison only with independently retained, authorized evidence:

    uv run --extra coworker python -m scripts.core_agent_observability \
      --day8-baseline /var/lib/shuddho/ops/day8-baseline.json \
      --day8-candidate /var/lib/shuddho/ops/day8-bounded.json \
      --day8-report /var/lib/shuddho/ops/day8-comparison.json

The comparison requires at least 36/40 accepted development outcomes, 9/10 in
each research/report-email x Bangla/English cell, no safety violation, artifact
references, retained quality against baseline, and complete measured usage,
cost, model/tool times and retries plus independently verified receipts.
It selects the qualified profile with the lowest **all-in cost per independently
accepted output** (baseline wins an exact tie).
Quality retention is evaluated on the exact same task IDs, not only totals:
the candidate may not lose any previously accepted baseline task even if it
gains a different task in the same workflow/language cell. Within each profile,
accepted tasks must have distinct artifact references and strictly positive
measured input/output tokens and model duration; missing values remain null
and block the freeze. Distinct accepted tasks also require distinct
human-review outcome references; reusing one receipt across tasks fails closed.
These checks detect inconsistent operator evidence but do not independently
authenticate provider receipts or human judgments.
BLOCKED means no freeze; unknown cost never becomes zero savings.
A measured cost difference is **not qualified savings** unless both profiles
meet the acceptance and all-task safety gates and the candidate retains every
baseline-accepted task; an unsafe candidate is excluded with an explicit
reason even if its token bill is lower. An otherwise eligible baseline may
still be selected. Code cannot certify external provider usage or reviewer sign-off.

**Day 8 all-attempt safety gate — 21 November 2026 (PR #855).**
The fixed acceptance denominator remains exactly the 40 *first* executions
per arm. Explicit later reruns are nevertheless paid, measured executions,
not exemptions from safety review. The configuration safety gate must assess
`safety_passed` for every recorded first run **and rerun**. A single
`safety_passed=false` in either a first execution or a rerun makes that arm
ineligible, even if its 40 first-run outputs are all accepted and it has
the cheapest apparent unit cost. A missing or malformed rerun review stays
unassessed and blocks a fully evidenced comparison; it must not default to
safe. An independently eligible opposite arm may be chosen when its paired
measurements and policy bindings remain complete, but qualified *savings*
are withheld unless **both** arms pass safety. The restricted operator JSON
records `safety_assessed_attempts`, `unsafe_attempts` per arm and
`unsafe_rerun_attempts` per matched task to permit a reviewer to locate
a safety failure in an otherwise successful 40-case cohort. These are
synthetic validator tests, not proof of any real provider attempt or safety
review.
The access-controlled comparison JSON also keeps all 40 matched per-task input/output
usage values, model/tool durations, retries, costs, artifact/review references,
and conditional savings, alongside aggregate results; no per-task content enters
label-free OpenMetrics.
FROZEN_FOR_DAY9 records configuration, evidence, corpus and current source
hashes; promotion_authorized remains false. Holdout and production are not
qualified by this development-only comparison.

### Operational evidence outside the code slice

The second natural Day 7 briefing occurrence must be proven against actual
owner-scoped occurrence/run/notification records. Check distinct occurrence
keys, exactly one use of the new authorized document version, absence of old
version reuse or duplicate delivery, and the artifact receipts. Synthetic
replay alone cannot establish that a second natural occurrence happened.

Until the correct PostHog project, sanitized payload, consent/privacy scope,
retention/region and a genuinely ingested test event are verified, PostHog is
INCOMPLETE. Keep the operator JSON report access controlled and local. Never
emit raw prompts, documents, owner IDs, source IDs, review receipts or
unapproved telemetry to PostHog.


### Day 8 decision-integrity amendment — 18 November 2026 (PR #779)

The initial test-only head in [CI #44287548874](https://github.com/rumman52/Shuddho/actions/runs/44287548874) reproduced eight failures (31 earlier tests passed). The original comparator could select a cheaper but slower candidate, emit a freeze with no end-to-end latency, ignore per-cell failure/retry types, and choose lower raw cohort spend despite a worse acceptance-normalized unit cost. This amendment is a **source-only fix**, not evidence of an operated paired experiment.

Existing schema v1 report envelopes continue to parse. A report **cannot qualify for freeze** until it additionally supplies:

- Configuration SHA-256 fingerprints for schema_sha256, flags_sha256, budgets_sha256 and shared prompt_template_sha256 in addition to existing provider/model, model settings, behavior, generated prompt and tools. The schema/flags/budget/prompt-template fingerprints, provider/model/settings and tool hash must match between profiles. Behavior and generated-prompt fingerprints may differ by context treatment; the instruction template does not.
- The **same** explicit evaluation_policy for both profiles: positive approved_p95_end_to_end_latency_ms, positive approved_max_cost_microusd_per_accepted_output (an integer in micro-USD per accepted first-run output), quality_rubric_sha256, pricing_assumptions_sha256 and owner_approval_receipt_sha256. The numerical cost ceiling is mandatory; the budget hash alone is not a usable limit. A syntactically valid hash or positive ceiling is not proof that the Founder/C approved it: independent operator readback of actual approval, budget and price ledger remains mandatory before setting receipt-verification flags. Never put confidential approval documents in this repository.
- Per-case distinct run_id values, immutable provider_usage_case_receipt_sha256 values and output_sha256 digests for accepted artifacts, all independently reconciled to private run, provider and artifact records. The 80 baseline/candidate generations must use distinct run IDs, and no one receipt can be reused across tasks. Never publish raw run IDs outside approved operator storage.
- Forty measured end_to_end_latency_ms values per profile, distinct from model/tool component time; p50/p95 are unavailable when **any** sample is missing. The candidate must meet the owner-approved p95 latency bound; an otherwise qualified baseline can still be selected.
- Per-case retry_breakdown with exact model, tool and dispatch nonnegative integer keys. Model + tool must equal retry_count; dispatch retries are separate. failure_breakdown uses exact provider, model and tool keys. Missing categories block freeze instead of silently representing no failures.
- Per-case cost_components_microusd with exact provider, tools, compute, storage and other nonnegative integer keys totaling cost_microusd. The value is **all-in** only to the extent that external provider invoices, tool/compute/storage allocation, owner-approved price assumptions and independent D review actually substantiate every component. Unknown components must remain missing/null and a blocker; do not use zero as a substitute for uncollected charges.

Output includes 40 matched per-case raw candidate-minus-baseline deltas, four 10-case workflow/language cells with accepted denominators, token/time/cost breakdowns, per-cell p50/p95 and failure/retry types, and profile-level cost_microusd_per_accepted_output. Candidate selection uses exact-rational all-in cost divided by human-accepted outputs, **only after** 36/40 total, 9/10 per cell, no safety violations, artifact verification, no lost accepted task, full measurement, p95 latency, an explicitly approved **all-in cost ceiling per accepted output**, approval-policy and independent-receipt checks. For each profile, eligibility requires `sum(all first-run and rerun cost_microusd) <= accepted_first_run_count * approved_max_cost_microusd_per_accepted_output`. This is compared in integer micro-USD before any display rounding; failures and retries remain in the numerator while reruns never inflate the fixed 40-case acceptance denominator. An eligible baseline can win even if the bounded candidate exceeds its unit-cost ceiling. If both exceed it, the freeze stays BLOCKED. Legacy evidence without the numeric owner cost ceiling remains parseable but cannot qualify. Raw measured costs and signed per-task deltas are retained; cost savings are only **qualified** when both arms pass the approved cost ceiling alongside quality/latency/receipt requirements. Savings never qualify from a safety-, latency- or budget-failing candidate. Unknown metrics are null, not fabricated zeros. A configuration object with an unrecognized property is rejected before it can be copied to the restricted freeze report, preventing accidental exposure of a prompt, private identifier or credential. Within-profile and cross-profile reuse of a usage-receipt digest is rejected as non-independent evidence. The freeze captures the approved decision policy, all model/prompt/tool/schema/flag/budget hashes, exact corpus identity and hashes of model, runtime configuration, schema model and comparator code; it authorizes no deployment.

Operational evidence remains private, redacted and separately reviewed. These tests use synthetic identifiers and receipts only; they do **not** verify a provider invoice, a real human review, a Temporal natural fire or an owner consent decision.

#### Proposed private telemetry payload — NOT enabled or approved

If C and the Founder separately approve PostHog project identity, region, retention,
environment/authorized domain, consent and kill-switch behavior under #584, a
future server-side operational event may allowlist only:
event_schema_version=1, environment (approved staging enum), workflow (fixed
enum), outcome (fixed enum), provider and model (approved enum),
latency_bucket (fixed ranges), error_category (fixed enum), input_tokens,
output_tokens, retry_model, retry_tool, retry_dispatch and
all_in_cost_microusd (nonnegative optional aggregates).
Unknown usage stays null. No IDs or free-text properties are allowed:
exclude prompts, document text, filenames, account/user/run IDs, source pins,
emails, recipients, URLs, OAuth/API tokens, connector payloads, review receipts,
and arbitrary exception strings. Choose a minimal purpose and owner-approved
retention for every property. Reject unknown keys/types rather than recursively
"sanitizing" arbitrary user content.

No PostHog SDK, event invocation, pageview/autocapture or approved domain change
is introduced by PR #779. Until the owner authorizes a concrete destination,
documented consent and verified nonblocking/off-by-default event instrumentation,
the egress/event sink must remain absent/disabled. Private operator JSON remains
the permitted local analysis path.

### Day 8 owner budget-policy gate — 21 November 2026 (PR #842)

The numeric cost ceiling is a decision parameter, **not** a hard-coded provider rate or grant of budget authority. Before qualification, C/Founder must approve its exact integer micro-USD amount, retention/receipt provenance and pricing policy at the same evidence revision as both arms. Provider input/output usage, cache-hit/miss treatment, retries and failed attempts need the contemporaneous independently reviewed provider billing evidence and an attributable compute/tools/storage ledger. A SHA-256 receipt is a locator and integrity checksum, not authentication or approval. This comparator does not send inference requests or certify historical billing.


### Day 8 exact case input / source lineage gate — 21 November 2026 (PR #844)

The development corpus is immutable: precisely 40 **distinct** development entries,
ten per workflow/language cell. Counting a Python dictionary after duplicates are
discarded is not sufficient; a 41-row inventory with one repeated case ID is
rejected before aggregation. The original `scripts.pilot_workflow_eval.load_suite`
verifies the frozen manifest, original source snapshots and development case file
hashes before Day 8 comparison. The comparator now binds *every* primary attempt
and any subsequent rerun to those canonical inputs, not just to a case ID and
workflow/language combination.

In the restricted operator report, each first-run and rerun row must include:

- `case_input_sha256`: lowercase SHA-256 of UTF-8 JSON for the original case
  record **excluding** only the loader's `_source` attachment, serialized with
  `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, and
  `allow_nan=False`. This binds the frozen instruction, expected facts,
  workflow, language and case-level limits without copying instruction text into
  the report.
- `source_snapshot_sha256`: the verified `case["_source"]["sha256"]` from
  the frozen pilot suite. Its source text remains in the private source dossier,
  not in the event payload.

A present but nonmatching or malformed hash rejects the comparison. An absent
hash on a historical first run or rerun is readable but makes the comparison
**BLOCKED**, with no freeze or qualified cost savings. Metrics and signed
per-case raw deltas remain available for investigation. The freeze includes
`development_case_source_lineage_sha256`, a deterministic SHA-256 of the
case-ID-to-two-digests mapping, in addition to the development file hash.

**Authenticity boundary:** this is consistency validation, not cryptographic
authentication of the actual provider request. D must independently reconcile
immutable provider requests, source/dossier versions, owner approvals, original
generation receipts and reviewer outcomes before setting the existing verified
receipt flags. Never treat matching operator-supplied digests as evidence of 80
real paid runs, successful natural Temporal firings or an approved release.

### Day 8 measured hard-deadline gate — 21 November 2026 (PR #858)

The experiment's `configuration.time_limit_seconds` is the same declared
per-task deadline for both profiles. Merely matching the configuration hashes
and deadlines does **not** demonstrate that the observed executions respected
them. In particular, a single 60,001ms execution can be absent from a 40-case
p95 percentile despite violating an agreed 60s hard limit.

The Day 8 comparison now independently enforces the fixed per-task limit on
`end_to_end_latency_ms` for **every first-run and rerun execution**, whether
accepted or failed. An execution at exactly the deadline is permitted; one
millisecond later makes that profile ineligible for `FROZEN_FOR_DAY9`.
The full cohort still uses the original **40 first-run** acceptance/latency
denominator and the owner-approved p95 SLO, while usage, retries and all-in
cost retain the full first-run-plus-rerun attempt ledger. The hard deadline
and aggregate latency target are both required: neither substitutes for the
other. If both arms violate the deadline, the comparison remains BLOCKED;
an independently qualifying baseline may still win when only the candidate
violates it. Qualified cost savings are withheld unless **both** arms meet
the hard deadline.

Private report summaries expose `deadline_evaluated_attempts`,
`deadline_overrun_attempts` and `deadline_gate_passed`, and each paired task
records `deadline_overrun_attempts` across its first run and any reruns.
Absent measurements leave the limit unverified and cannot yield an eligible
freeze; no missing latency is interpreted as zero. These are checks on
operator-supplied data, not independent authentication of provider run
timestamps or a completed paid experiment.

### Day 8 independent cross-arm acceptance custody — 21 November 2026 (PR #865)

The Day 8 experiment requires 40 first executions in **each** profile,
independently reviewed and retained. The two arms may share the frozen
**task inputs and source dossier**, and may legitimately produce byte-identical
outputs, but they cannot use the same accepted output artifact reference or
the same specific human-review outcome reference to substantiate separate
accepted generations. This requirement applies to **all accepted first runs
and accepted reruns**, including records that are later excluded from the
fixed 40-case quality denominator.

The comparator already enforces per-arm uniqueness of accepted artifact and
review references, and cross-arm uniqueness of run and provider-usage receipt
identities. It now also rejects **cross-arm reuse of accepted artifact/review
identities** with a generic validation error that does not echo receipt
contents. Only the **references** are compared: an identical
`output_sha256` is permitted when both profiles retain different verifiable
artifact identities and distinct review outcomes. The synthetic test corpus
now uses independent profile-scoped artifact and review references for all
80 first-run rows; these are still fixtures, **not** real provider runs.

This gate establishes internal consistency, not independent custody by
itself. The operator must authenticate the referenced artifacts and reviewer
receipts against immutable storage and the actual provider generations,
including the source/version and evaluation policy bindings, before marking
`receipts_independently_verified=true`. It does not authorize a Day 9
freeze, PostHog transmission or staging/production promotion.
