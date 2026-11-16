# Day 9 — Try to break the candidate (operator execution contract)

**Owners:** D runs independently controlled evaluations and blind reviews; C runs the operated fault rows against real PostgreSQL/Temporal boundaries; A/B repair only demonstrated blockers. This source-only implementation neither provisions staging nor turns on production capabilities.

**Starting repository revision:** f3bd787764a5a6c7ff4bbc54c986543ff7a745cf. The exact evaluated revision is the 40-character `candidate_revision` frozen by D in the run manifest. Never reuse an earlier CI pass as an exact-head result.

## Source implementation and qualification distinction

- `tests/fixtures/ruke_pilot_tasks.jsonl` is a **development** registry of 40 prompts: research brief and project report/email, ten Bangla and ten English per workflow, bound to the already source-verified Day 1 development dossiers. It contains no answer keys.
- `scripts/ruke_pilot_eval.py` validates an externally held 40-task corpus and records results. This script does **not** generate candidate/competitor answers, run model calls, validate actual hosted database state, verify human identities or attest access isolation.
- `tests/test_ruke_pilot_eval.py` uses synthetic input to prove fail-closed envelope contracts. Synthetic passing rows are **not staging evidence**.
- The old candidate holdout under `tests/fixtures/pilot_workflows/holdout.jsonl` is exposed in the developer-editable repository. Keep its existing fail-closed holdout API and frozen hash. D must replace exposed tasks as necessary, control the new corpus **outside** any agent/developer-writable checkout, and independently test that development identities receive **denied** reads.
- The operator must preserve the **first** run, even if it fails. Later use of held-out failures to fix code makes all retests **regression validation**, not a fresh independent benchmark.

## Exact-head source checks (no activation)

Run on the exact final candidate SHA with no mandatory skips:

```bash
uv run --extra coworker python -m pytest -q tests/test_ruke_pilot_eval.py tests/test_pilot_workflow_eval.py tests/test_release_contract.py
uv run --extra coworker python -m scripts.ruke_pilot_eval validate-registry
uv run python -m scripts.release_contract_check
uv run --extra coworker python -m pytest -q tests/test_runtime_v3_qualification_helpers.py tests/test_runtime_v3_live_qualification.py
```

The complete repository and workflow-specific tests, front-end/build/Playwright checks, PG18 compatibility, Coworker, required branch governance and CI merge gate **must also pass on the final SHA** under the existing repository rules. A local or unit-test pass cannot replace these. Any test explicitly requiring a live provider or real staging connection must remain opt-in; never lower thresholds or convert a required case to a skip.

The canonical release contract is `scripts/release_contract.py`, validated by `scripts.release_contract_check`. The separate, authoritative go/no-go decision remains `scripts/cohort_release_gate.py` and `docs/FINAL_CONTROLLED_COHORT_GATE.md`; Day 9's report cannot authorize activation.

## D — external held-out run

Create `/secure/d/day9/` or a comparable independently permissioned location **outside the repo**. This is an operator example, not a claim that such a path exists here. Record independently observed access-denied evidence for A/B developer identities and the physical custody handoff. The externally frozen JSONL contains **40** generation-facing rows with `case_id`, `workflow` and `language` (ten per cell) and task prompts plus permitted-source pointers; omit answer keys. Each JSONL row must include nonempty `instruction`, `source_id`, `citation_id`, SHA-256 `source_sha256` and `max_output_bytes` (1..24000). Make the separate file read-only (e.g. `chmod 0444 tasks.jsonl` in D's independent workspace), and record its exact SHA-256 in the manifest.

Manifest JSON fields:

```json
{
  "schema_version": 2,
  "split": "holdout",
  "release_id": "<frozen staging release ID>",
  "run_id": "<unique immutable first-run ID>",
  "candidate_revision": "<exact 40-character API/worker Git SHA>",
  "corpus_sha256": "<sha256 of independent tasks JSONL>",
  "source_set_sha256": "<sha256 of exactly comparable permitted sources>",
  "rollout_manifest_sha256": "<sha256 of frozen staging rollout manifest>",
  "answer_key_sha256": "<sha256 of frozen answers outside developer checkout>",
  "rubric_sha256": "<sha256 of frozen scoring rubric outside developer checkout>",
  "candidate_product_version": "<actual product release version>",
  "candidate_model": "<exact model ID>",
  "prompt_version": "<frozen prompt identity>",
  "tool_version": "<frozen tool and permissions identity>",
  "run_started_at": "<UTC timestamp>",
  "time_limit_seconds": 120,
  "candidate_identity": {
    "api_source_revision": "<same exact candidate SHA>",
    "worker_source_revision": "<same exact candidate SHA>",
    "api_build_digest": "sha256:<64 lowercase hex>",
    "worker_build_digest": "sha256:<64 lowercase hex>",
    "alembic_revision": "<exact migration revision>",
    "provider_id": "<provider ID>",
    "model_id": "<same exact model ID>",
    "prompt_registry_sha256": "<64 lowercase hex>",
    "tool_registry_sha256": "<64 lowercase hex>",
    "context_budget_bytes": 12288,
    "runtime_capabilities": {"<exactly 43 keys from scripts.staging_release_freeze.RUNTIME_CAPABILITY_KEYS>": false},
    "api_readback_sha256": "<canonical API readback digest>",
    "worker_readback_sha256": "<canonical worker readback digest>",
    "schema_readback_sha256": "<canonical schema readback digest>"
  }
}
```


The block above is a **schema sketch**, not a usable manifest. The capability placeholder is shorthand only: a real manifest must contain all 43 keys exactly once with their exact runtime boolean values, including false values. Replace the illustrative context-budget integer with the authenticated runtime value. The CLI rejects placeholders, missing/extra flags, non-boolean flags and inconsistent readback digests. Schema-v1 manifests remain readable only through the explicit legacy-read helper and are rejected for new qualification runs.

The `candidate_readbacks.api` and `candidate_readbacks.worker` objects each contain exactly `release_id`, `source_revision`, `build_digest`, `alembic_revision`, `provider_id`, `model_id`, `prompt_registry_sha256`, `tool_registry_sha256`, `context_budget_bytes`, `rollout_manifest_sha256`, `runtime_capabilities` and `readback_sha256`. The `schema` object contains exactly `release_id`, `source_revision`, `migration_revision`, `api_revision`, `worker_revision`, `rollout_manifest_sha256` and `readback_sha256`. Each readback digest is SHA-256 over canonical UTF-8 JSON with the `readback_sha256` field omitted. These are composite readback envelopes: source revision/capabilities come from the authenticated runtime manifest; build digests from the deployed image/build record; provider/model and context budget from live runtime configuration; prompt/tool hashes from the deployed registries; and the schema tuple from a live Alembic/database readback. Do not fill them from source defaults or a nearby deployment. C/D must independently authenticate each underlying source and preserve its access/observation receipt.
Generate actual candidate outputs once with the frozen model, prompts, permissions, sources and per-task time/usage limits. Record output artifact SHA-256 plus deterministic/security check results **for all 40 IDs**; no missing task may disappear from the denominator. Store source links/claims and signed or human-controlled first-run evidence outside the development surface.

Each independent reviewer D1/D2 scores **four** rubric dimensions `factual_source_fidelity`, `constraint_compliance`, `completeness_usefulness`, `language_quality`, each an integer 0, 1 or 2 (failed, minor correction, usable as delivered). For an accepted task, **each original reviewer** must independently score at least 7/8 with no zero dimension; the final adjudicated rubric must also meet that floor, be source-supported and pass deterministic/security checks. Adjudication resolves disagreement but never erases or overwrites either original rating. Both reviewers must provide per-task source-supported booleans and evidence-based notes; disagreement requires a **separate adjudicator's** reconciled rubric and rationale. Fluency, verbosity and polished wording never cure unsupported claims.

Required gate: **at least 36/40 accepted, and at least 9/10 in each cell.** Costs: calculate actual/estimated spend per accepted task only from recorded provider usage and independently approved pricing; missing usage is unavailable, not zero. Preserve source revision, output hashes, model and competitor versions, timestamps and time budgets.

## D — blinded competitor comparison

Use at least one **actually available** competitor. Its run records must specify product, exact version, model, recorded UTC run time, same `source_set_sha256` and same `time_limit_seconds`. If access is unavailable, submit an explicit comparison gap; do not fill it with an imaginary model or present a winner. A clearly recorded access gap is an acceptable Day 9 report outcome; it is not a competitor win/loss result and must not be presented as a superiority comparison.

The D custodian must generate a **fresh 32-byte cryptographic blinding key**, keep it in a restricted (mode 0600/0400) file outside the repository, and never expose it to either reviewer. A public task ID or corpus hash is **not** a secret blinding seed. For example, from D's independently permissioned workspace:

```bash
python -c 'from pathlib import Path; from secrets import token_bytes; p=Path("/secure/d/day9/blind.key"); p.write_bytes(token_bytes(32)); p.chmod(0o600)'
```

Do not disclose the key or candidate/competitor mapping in review packets. The script records only its SHA-256 fingerprint, not its contents. Generate the position-swapped packet from real same-task outputs:

```bash
uv run --extra coworker python -m scripts.ruke_pilot_eval prepare-blind \
  --manifest /secure/d/day9/manifest.json --heldout /secure/d/day9/tasks.jsonl \
  --candidate /secure/d/day9/candidate-outputs.jsonl \
  --competitor-outputs /secure/d/day9/competitor-outputs.jsonl \
  --blinding-key /secure/d/day9/blind.key \
  --report /secure/d/day9/first-blind-packet.json
```

Provide each reviewer only A/B response text (not product labels), randomized across IDs with the opposite ordering on the second pass. Judgments contain `case_id`, `reviewer_id`, `position` (AB or BA), `preference` (A/B/tie), and an evidence note; 2 reviewers × 2 positions × 40 cases = **160** rows. Position-inconsistent cases require a separate **blind comparative adjudication**, never majority-vote override. For each disputed case, the `comparison_adjudications` array supplies `case_id`, a third `adjudicator_id` (not D1/D2), blinded `position` (AB or BA), `preference` (A/B/tie), and an evidence-based note. Unresolved disagreements block the comparator gate. Report candidate wins, ties, losses, actual versions, sample size and uncertainty. No unsupported claim may receive a preference simply due to fluency or length.

## C — operated scenario inventory

Each row below is required, not a simulated check. For every row record exact candidate SHA, `execution=operated`, pass/fail, UTC observation time, bounded trace hash, unauthorized-access/mutation flags, and the required real instance IDs and trace hashes under `boundaries`. The evaluator checks the **shape** of submitted evidence, not live truth. C must actually execute each step and an independent operator must inspect trace/receipt integrity before release.

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

**20/20 are mandatory.** Any high-severity open finding or unauthorized access/mutation is an immediate **NO-GO** regardless of aggregate quality.

A `deterministic` row with `security_passed=false` for **any** of the 40 holdout tasks is an independent absolute NO-GO, even if the same row is the only quality failure (39/40 otherwise accepted and all four cells meet 9/10). The report exposes `outcomes.security_gate_pass` and `outcomes.security_failed_cases` so a quality pass cannot obscure security failure. A nonsecurity `passed=false` remains an ordinary task-quality miss subject to the existing acceptance limits. In particular, failures around wrong-owner/private-artifact access, stale source use, duplicate side effects, cancellation/steering resurrection, lost restores or uncontrolled scheduling cannot be averaged away.

## Evidence JSON and immutable first-run report

The external `evidence.json` has these keys:

- `reviews`: 80 rows, 2 fixed reviewer IDs; each row contains `case_id`, `reviewer_id`, `scores` (four rubric dimensions), `source_supported` (bool), `evidence_note`.
- `adjudications`: one row for each disagreement, with `case_id`, third `adjudicator_id`, `scores`, `source_supported`, `evidence_note`.
- `deterministic`: 40 rows with `case_id`, `passed`, `security_passed`, `output_sha256`. Hash each actual candidate output using UTF-8 JSON with sorted keys, compact separators and no NaN; a mismatch blocks evaluation.
- `candidate-outputs.jsonl`: 40 rows with `case_id`, `manifest_sha256` equal to the exact frozen manifest file digest, and the full `output` draft JSON object; optional nonnegative integer `telemetry` with exactly `tokens`, `latency_ms`, `cost_microusd`. Incomplete telemetry yields unknown aggregate cost and cost-per-accepted-task, **not zero**.
- `competitor-outputs.jsonl`: 40 same-task output rows, each carrying the same `manifest_sha256`; competitor metadata in `evidence.json` also carries the same `release_id` and `rollout_manifest_sha256`.
- `operations`: 20 rows with `row` (1..20), exact `scenario` from `OPERATED`, `candidate_revision`, `release_id`, `rollout_manifest_sha256`, `manifest_sha256`, `execution`, `status`, `unauthorized_access`, `unauthorized_mutation`, `observed_at`, `trace_sha256`, and `boundaries` keyed by required component. Each boundary contains `mode=real`, `instance`, `trace_sha256`.
- `manifest_sha256`: exact SHA-256 of the frozen manifest file.
- `required_repository_checks=passed` and `canonical_release_contract=passed` from the exact candidate SHA; the CLI refuses to read holdout bytes until both are present alongside custody and readback receipts.
- `candidate_readbacks`: exact `api`, `worker` and `schema` readback objects. Each includes a canonical `readback_sha256` computed over that object with the digest field omitted; API/worker objects must agree with every identity field and all 43 boolean capability keys in the manifest. The CLI checks digest consistency, not source-system authenticity; C/D must independently authenticate the readbacks.
- `competitor`: identity fields and comparable limits described above plus the same `manifest_sha256`, `release_id` and `rollout_manifest_sha256`; if access is unavailable, omit competitor/comparison rows and provide a nonempty `competitor_access_gap` explanation. A missing judgment file when a competitor was available is incomplete evidence, not an access gap.
- `comparisons`: 160 blinded judgment records described above (or omitted, with gap disclosed).
- `comparison_adjudications`: independent third-reviewer A/B decisions with source rationales for every unresolved comparative disagreement.
- `custody`: three distinct pseudonymous IDs `custodian_id`, `developer_id`, `corpus_author_id`; independent operator review=`verified`; custodian positive-read test=`allowed`; developer negative-read test=`denied`; exposure-history review=`true`; replacement of exposed cases=`true`; and SHA-256 digests for frozen inputs, frozen answers, rubric, exposure history, access log and custody receipt. These are **unverified operator statements to this CLI**, not cryptographic attestations.

The CLI requires this complete receipt and the candidate readbacks before it reads any holdout bytes. The frozen-input, answer-key and rubric digests in the custody receipt must exactly match the corresponding manifest digests. Both `evaluate` and `prepare-blind` require the external custody/readback evidence JSON. C/D must independently authenticate the human identities, positive/negative access tests, source access logs and isolated storage; the CLI's digest checks are not proof of custody.
- `required_repository_checks` and `canonical_release_contract`: both `passed` only with independently inspected exact-head evidence; `unresolved_high_severity_failures` is a required array.

```bash
uv run --extra coworker python -m scripts.ruke_pilot_eval evaluate \
  --manifest /secure/d/day9/manifest.json \
  --heldout /secure/d/day9/tasks.jsonl \
  --candidate /secure/d/day9/candidate-outputs.jsonl \
  --blinding-key /secure/d/day9/blind.key \
  --evidence /secure/d/day9/evidence.json \
  --report /secure/d/day9/first-run-result.json
```

The report uses an exclusive create (`O_EXCL`), never clobbering a previous result. Its first-run receipt also emits the exact Day 10 handoff fields `release_id`, `source_revision`, `rollout_manifest_sha256`, `run_id`, `run_kind=first_run` and per-case `scores` with both reviewers' 0–8 totals and a strict boolean security verdict. The blind packet is wrapped with the same manifest digest and release identity. **A malformed or incomplete first run also writes a failure report** (when the supplied report path is valid) so failure evidence is not lost. Evaluation and blind-packet inputs and reports must be outside the repository; the run manifest's exact candidate revision must match the checkout HEAD. A later attempt uses a **different** filename and `--regression-rerun` to classify the evidence honestly. No script may change these labels to claim new independent measurements. Exit 0 means submitted **operator evidence** passes mechanical gates, *not* that release is authorized. Exit 1 means incomplete/failed gate, exit 2 malformed or missing evidence.

**Important:** No document written in this repository, no developer-authored test fixture, no self-declared D identity, and no SHA alone proves access isolation, two actual human reviewers or 20 genuinely operated scenarios. The script emits `custody_independently_verified_by_this_program=false` and `release_authorization=false` even when operator inputs are mechanically complete. Human review plus the canonical cohort release gate remain required.

## Day 9 status on source commit

Implementation and local regressions can be reviewed in the Day 9 PR. **No independent held-out execution, real competitor contest, 20 live fault executions, staging restore, human adjudication or cohort activation is asserted here.** Capture each missing result as a blocker until D/C provide independently verified external evidence. Do not touch production flags or provider side effects as part of this source PR.
