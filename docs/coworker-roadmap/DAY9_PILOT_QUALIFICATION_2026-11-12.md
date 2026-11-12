# Day 9 — Try to break the candidate (operator execution contract)

**Owners:** D runs independently controlled evaluations and blind reviews; C runs the operated fault rows against real PostgreSQL/Temporal boundaries; A/B repair only demonstrated blockers. This source-only implementation neither provisions staging nor turns on production capabilities.

**Starting repository revision:** f3bd787764a5a6c7ff4bbc54c986543ff7a745cf. The exact evaluated revision is the 40-character \`candidate_revision\` frozen by D in the run manifest. Never reuse an earlier CI pass as an exact-head result.

## Source implementation and qualification distinction

- \`tests/fixtures/ruke_pilot_tasks.jsonl\` is a **development** registry of 40 prompts: research brief and project report/email, ten Bangla and ten English per workflow, bound to the already source-verified Day 1 development dossiers. It contains no answer keys.
- \`scripts/ruke_pilot_eval.py\` validates an externally held 40-task corpus and records results. This script does **not** generate candidate/competitor answers, run model calls, validate actual hosted database state, verify human identities or attest access isolation.
- \`tests/test_ruke_pilot_eval.py\` uses synthetic input to prove fail-closed envelope contracts. Synthetic passing rows are **not staging evidence**.
- The old candidate holdout under \`tests/fixtures/pilot_workflows/holdout.jsonl\` is exposed in the developer-editable repository. Keep its existing fail-closed holdout API and frozen hash. D must replace exposed tasks as necessary, control the new corpus **outside** any agent/developer-writable checkout, and independently test that development identities receive **denied** reads.
- The operator must preserve the **first** run, even if it fails. Later use of held-out failures to fix code makes all retests **regression validation**, not a fresh independent benchmark.

## Exact-head source checks (no activation)

Run on the exact final candidate SHA with no mandatory skips:

\`\`\`bash
uv run --extra coworker python -m pytest -q tests/test_ruke_pilot_eval.py tests/test_pilot_workflow_eval.py tests/test_release_contract.py
uv run --extra coworker python -m scripts.ruke_pilot_eval validate-registry
uv run python -m scripts.release_contract_check
uv run --extra coworker python -m pytest -q tests/test_runtime_v3_qualification_helpers.py tests/test_runtime_v3_live_qualification.py
\`\`\`

The complete repository and workflow-specific tests, front-end/build/Playwright checks, PG18 compatibility, Coworker, required branch governance and CI merge gate **must also pass on the final SHA** under the existing repository rules. A local or unit-test pass cannot replace these. Any test explicitly requiring a live provider or real staging connection must remain opt-in; never lower thresholds or convert a required case to a skip.

The canonical release contract is \`scripts/release_contract.py\`, validated by \`scripts.release_contract_check\`. The separate, authoritative go/no-go decision remains \`scripts/cohort_release_gate.py\` and \`docs/FINAL_CONTROLLED_COHORT_GATE.md\`; Day 9's report cannot authorize activation.

## D — external held-out run

Create \`/secure/d/day9/\` or a comparable independently permissioned location **outside the repo**. This is an operator example, not a claim that such a path exists here. Record independently observed access-denied evidence for A/B developer identities and the physical custody handoff. The externally frozen JSONL contains **40** generation-facing rows with \`case_id\`, \`workflow\` and \`language\` (ten per cell) and task prompts plus permitted-source pointers; omit answer keys. Record its exact SHA-256 in the manifest.

Manifest JSON fields:

\`\`\`json
{
  "schema_version": 1,
  "split": "holdout",
  "candidate_revision": "<exact 40-character Git SHA>",
  "corpus_sha256": "<sha256 of independent tasks JSONL>",
  "source_set_sha256": "<sha256 of exactly comparable permitted sources>",
  "candidate_product_version": "<actual product release version>",
  "candidate_model": "<exact model ID>",
  "prompt_version": "<frozen prompt identity>",
  "tool_version": "<frozen tool and permissions identity>",
  "run_started_at": "<UTC timestamp>",
  "time_limit_seconds": 120
}
\`\`\`

Generate actual candidate outputs once with the frozen model, prompts, permissions, sources and per-task time/usage limits. Record output artifact SHA-256 plus deterministic/security check results **for all 40 IDs**; no missing task may disappear from the denominator. Store source links/claims and signed or human-controlled first-run evidence outside the development surface.

Each independent reviewer D1/D2 scores **four** rubric dimensions \`factual_source_fidelity\`, \`constraint_compliance\`, \`completeness_usefulness\`, \`language_quality\`, each an integer 0, 1 or 2 (failed, minor correction, usable as delivered). A task is accepted only if sum ≥7, all four nonzero, source-supported and deterministic/security checks pass. Both reviewers must provide per-task source-supported booleans and evidence-based notes; disagreement requires a **separate adjudicator's** reconciled rubric and rationale. Fluency, verbosity and polished wording never cure unsupported claims.

Required gate: **at least 36/40 accepted, and at least 9/10 in each cell.** Costs: calculate actual/estimated spend per accepted task only from recorded provider usage and independently approved pricing; missing usage is unavailable, not zero. Preserve source revision, output hashes, model and competitor versions, timestamps and time budgets.

## D — blinded competitor comparison

Use at least one **actually available** competitor. Its run records must specify product, exact version, model, recorded UTC run time, same \`source_set_sha256\` and same \`time_limit_seconds\`. If access is unavailable, submit an explicit comparison gap; do not fill it with an imaginary model or present a winner.

Generate the position-swapped packet from real same-task outputs:

\`\`\`bash
uv run --extra coworker python -m scripts.ruke_pilot_eval prepare-blind \
  --manifest /secure/d/day9/manifest.json --heldout /secure/d/day9/tasks.jsonl \
  --candidate /secure/d/day9/candidate-outputs.jsonl \
  --competitor-outputs /secure/d/day9/competitor-outputs.jsonl \
  --report /secure/d/day9/first-blind-packet.json
\`\`\`

Provide each reviewer only A/B response text (not product labels), randomized across IDs with the opposite ordering on the second pass. Judgments contain \`case_id\`, \`reviewer_id\`, \`position\` (AB or BA), \`preference\` (A/B/tie), and an evidence note; 2 reviewers × 2 positions × 40 cases = **160** rows. Position-inconsistent cases are reported and do not pass the comparator gate. Report candidate wins, ties, losses, actual versions, sample size and uncertainty. No unsupported claim may receive a preference simply due to fluency or length.

## C — operated scenario inventory

Each row below is required, not a simulated check. For every row record exact candidate SHA, \`execution=operated\`, pass/fail, UTC observation time, bounded trace hash, unauthorized-access/mutation flags, and the required real instance IDs and trace hashes under \`boundaries\`. The evaluator checks the **shape** of submitted evidence, not live truth. C must actually execute each step and an independent operator must inspect trace/receipt integrity before release.

| Row | Operated assertion | Required real boundaries |
|---:|---|---|
| 01 | Private upload/retrieval returns exact owner bytes | PostgreSQL, object storage |
| 02 | Foreign owner denied with no source exposure | PostgreSQL, object storage |
| 03 | Source removal during generation blocks stale final | PostgreSQL, Temporal, object storage |
| 04 | PDF instructions remain data, never grant authority | object storage |
| 05 | Prior conversation choice resolved or needs input | PostgreSQL |
| 06 | Stale conversation/brief returns conflict; no run | PostgreSQL |
| 07 | Identical retry returns same run; one outbox effect | PostgreSQL, Temporal |
| 08 | Changed brief/source replay conflicts; no admission | PostgreSQL, Temporal |
| 09 | Unselected same-category memory excluded | PostgreSQL |
| 10 | Corrected/expired/foreign pin invalidated | PostgreSQL |
| 11 | Worker termination resumes/reconciles; no duplication | PostgreSQL, Temporal |
| 12 | Cancel during inference blocks late resurrection | PostgreSQL, Temporal |
| 13 | Steer during inference rejects old revision commits | PostgreSQL, Temporal |
| 14 | Browser reconnect restores correct durable run | PostgreSQL, Temporal |
| 15 | Timeout/429/unknown usage bounded and accounted | PostgreSQL, Temporal |
| 16 | Missing/unreadable object cannot claim completion | PostgreSQL, object storage |
| 17 | Duplicate scheduled occurrence admits one run | PostgreSQL, Temporal |
| 18 | Paused/expired/deleted source prevents work | PostgreSQL, Temporal |
| 19 | Quiet hours/missed occurrence defers and catches up safely | PostgreSQL, Temporal |
| 20 | Rollback and isolated DB restore retain valid identity/data | PostgreSQL, Temporal, object storage |

**20/20 are mandatory.** Any high-severity open finding or unauthorized access/mutation is an immediate **NO-GO** regardless of aggregate quality. In particular, failures around wrong-owner/private-artifact access, stale source use, duplicate side effects, cancellation/steering resurrection, lost restores or uncontrolled scheduling cannot be averaged away.

## Evidence JSON and immutable first-run report

The external \`evidence.json\` has these keys:

- \`reviews\`: 80 rows, 2 fixed reviewer IDs; each row contains \`case_id\`, \`reviewer_id\`, \`scores\` (four rubric dimensions), \`source_supported\` (bool), \`evidence_note\`.
- \`adjudications\`: one row for each disagreement, with \`case_id\`, third \`adjudicator_id\`, \`scores\`, \`source_supported\`, \`evidence_note\`.
- \`deterministic\`: 40 rows with \`case_id\`, \`passed\`, \`security_passed\`, \`output_sha256\`.
- \`operations\`: 20 rows with \`row\` (1..20), exact \`scenario\` from \`OPERATED\`, \`candidate_revision\`, \`execution\`, \`status\`, \`unauthorized_access\`, \`unauthorized_mutation\`, \`observed_at\`, \`trace_sha256\`, and \`boundaries\` keyed by required component. Each boundary contains \`mode=real\`, \`instance\`, \`trace_sha256\`.
- \`competitor\`: identity fields and comparable limits described above (or omitted, with gap disclosed).
- \`comparisons\`: 160 blinded judgment records described above (or omitted, with gap disclosed).
- \`custody\`: external transfer receipt SHA, independent operator review=\`verified\`, developer negative read test=\`denied\`, replacement of exposed cases=\`true\`, custodian identity; these are **unverified operator statements to this CLI**, not cryptographic attestations.
- \`required_repository_checks\` and \`canonical_release_contract\`: both \`passed\` only with independently inspected exact-head evidence; \`unresolved_high_severity_failures\` is a required array.

\`\`\`bash
uv run --extra coworker python -m scripts.ruke_pilot_eval evaluate \
  --manifest /secure/d/day9/manifest.json \
  --heldout /secure/d/day9/tasks.jsonl \
  --evidence /secure/d/day9/evidence.json \
  --report /secure/d/day9/first-run-result.json
\`\`\`

The report uses an exclusive create (\`O_EXCL\`), never clobbering a previous result. A later attempt uses a **different** filename and \`--regression-rerun\` to classify the evidence honestly. No script may change these labels to claim new independent measurements. Exit 0 means submitted **operator evidence** passes mechanical gates, *not* that release is authorized. Exit 1 means incomplete/failed gate, exit 2 malformed or missing evidence.

**Important:** No document written in this repository, no developer-authored test fixture, no self-declared D identity, and no SHA alone proves access isolation, two actual human reviewers or 20 genuinely operated scenarios. The script emits \`custody_independently_verified_by_this_program=false\` and \`release_authorization=false\` even when operator inputs are mechanically complete. Human review plus the canonical cohort release gate remain required.

## Day 9 status on source commit

Implementation and local regressions can be reviewed in the Day 9 PR. **No independent held-out execution, real competitor contest, 20 live fault executions, staging restore, human adjudication or cohort activation is asserted here.** Capture each missing result as a blocker until D/C provide independently verified external evidence. Do not touch production flags or provider side effects as part of this source PR.
