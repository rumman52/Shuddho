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

**Independent custody chronology (new qualifying first-run evidence):** The custodian's actual positive-read and developer negative-read checks, exposure history, and separate answer/rubric digests must be authenticated **before** opening the protected heldout or running the frozen first attempt. The signed/audited `evidence.custody.verified_at` is a timezone-aware, nonfuture instant **strictly earlier** than `manifest.run_started_at`: equality or a later time fails custody validation before the evaluator reads heldout bytes. D and C retain the independent identity, access-policy/readback, and private audit proofs outside the repository. A timestamp submitted in JSON is not proof that those controls actually operated, and an earlier run cannot be retrospectively qualified by changing the receipt.

The `candidate_readbacks.api` and `candidate_readbacks.worker` objects each contain exactly `release_id`, `source_revision`, `build_digest`, `alembic_revision`, `provider_id`, `model_id`, `prompt_registry_sha256`, `tool_registry_sha256`, `context_budget_bytes`, `rollout_manifest_sha256`, `runtime_capabilities` and `readback_sha256`. The `schema` object contains exactly `release_id`, `source_revision`, `migration_revision`, `api_revision`, `worker_revision`, `rollout_manifest_sha256` and `readback_sha256`. Each readback digest is SHA-256 over canonical UTF-8 JSON with the `readback_sha256` field omitted. These are composite readback envelopes: source revision/capabilities come from the authenticated runtime manifest; build digests from the deployed image/build record; provider/model and context budget from live runtime configuration; prompt/tool hashes from the deployed registries; and the schema tuple from a live Alembic/database readback. Do not fill them from source defaults or a nearby deployment. C/D must independently authenticate each underlying source and preserve its access/observation receipt.
Generate actual candidate outputs once with the frozen model, prompts, permissions, sources and per-task time/usage limits. Record output artifact SHA-256 plus deterministic/security check results **for all 40 IDs**; no missing task may disappear from the denominator. Store source links/claims and signed or human-controlled first-run evidence outside the development surface.

**Successful and unsuccessful first-attempt chronology (new qualification reports only):** Every manifest-bound candidate JSONL row — **whether it produced a successful draft, a failure or a timeout** — must have a unique original `run_id` and timezone-aware, nonfuture `attempt_started_at` and `attempt_finished_at`. The evaluator enforces `manifest.run_started_at <= attempt_started_at <= attempt_finished_at` and preserves both timestamps in each original `case_run_receipts` row, the `scores.cases` export and `day10_holdout.cases`. The two original blind `reviewed_at` instants must each be **strictly later** than that case's `attempt_finished_at`; third-party `adjudicated_at` must be later than both reviews. The Day 10 gate independently checks the exact timestamp bytes against each original first-attempt receipt and rejects missing, reordered or backdated events. A successful output without timestamps is not a fresh qualifying attempt. Do not fabricate, rewrite or retroactively add times to old operator artifacts; their value is historical only. These submitted clock fields are evidence claims to be authenticated against protected runtime/human audit logs by independent D, not proof of a live run by themselves.


Each independent reviewer D1/D2 scores **four** rubric dimensions `factual_source_fidelity`, `constraint_compliance`, `completeness_usefulness`, `language_quality`, each an integer 0, 1 or 2 (failed, minor correction, usable as delivered). For an accepted task, **each original reviewer** must independently score at least 7/8 with no zero dimension; the final adjudicated rubric must also meet that floor, be source-supported and pass deterministic/security checks. Adjudication resolves disagreement but never erases or overwrites either original rating. Both reviewers must provide per-task source-supported booleans and evidence-based notes; disagreement requires a **separate adjudicator's** reconciled rubric and rationale. Fluency, verbosity and polished wording never cure unsupported claims.

**Recorded-original-output review contract (new qualifying reports only):** Each of the 80 independently submitted `evidence.reviews[*]` records must additionally specify `output_sha256` (the exact lowercase 64-hex hash of that case's first candidate output, or the preserved original failure record) and a timezone-aware, nonfuture `reviewed_at`. The reviewer may see only the anonymized original output; D separately authenticates the protected timestamped submission history. A review tied to a substitute hash is rejected even if its `case_id` and scores match. The public report preserves each reviewer's original four scores, source-support verdict, output hash, review timestamp and SHA-256 of its private evidence note, but **never** the note's text. Two independently recorded reviews must predate the third person's adjudication.

For any case on which the two original reviewers disagree (rubric **or** source-support verdict), `evidence.adjudications[*]` must additionally specify the same original `output_sha256` and `adjudicated_at` as a timezone-aware, nonfuture timestamp **strictly later** than both reviewers' `reviewed_at` instants. The `final_rubric` exported to Day 10 carries those two fields and the existing distinct third identity/rationale digest. Unanimous votes export the original output hash with `adjudicated_at=null` and no third identity or rationale. Day 10 must independently verify this shape and each per-case output-hash equality against its immutable first-attempt receipt, and reject any impossible review/adjudication order. Submitted timestamps and hashes are **claims**, not authentication of human independence; D must preserve underlying original receipts, evidence-note contents and independent access checks separately. Old reports without this contract remain archival only, never an edited substitute for a fresh holdout.



**Final adjudication handoff, effective on new first-run reports:** Every row in `scores.results`, `scores.cases` and `day10_holdout.cases` carries the two original `reviewer_rubrics` (each `reviewer_id`, four `scores` and independent boolean `source_supported`) **and** a separate `final_rubric` with `scores`, `source_supported`, `adjudicator_id`, `evidence_note_sha256`. When the two original reviewers disagree in scores or source support, the final result must name a **third distinct reviewer** and include a lowercase SHA-256 digest of that adjudicator's private evidence note. The note text remains in protected D custody; a digest is not proof of independence. When the two votes are identical, the final result reproduces their rubric/source verdict and has null adjudicator and null note digest; do not invent an adjudicator. Accepted cases require both originals and the final rubric to meet the existing 7/8, no-zero and source-support gates, in addition to deterministic/security PASS. Day 10 cross-checks identical per-case `final_rubric` in the preserved first-run and exported holdout artifacts, rejecting substituted, incomplete or self-contradictory adjudication. Historical pre-contract reports are archival only and cannot be silently edited or reused as new qualifying evidence.

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

**Day 10 original-recovery lineage (new qualifying reports only):** `verify_operations` emits exact IDs `day9-scenario-01` through `day9-scenario-20`, with each scenario's name and required PostgreSQL/Temporal/object-storage boundaries; release/source/rollout and the frozen `manifest_sha256` appear on both the top-level recovery report and each row. Every passing row must have `evidence_ref=sha256:<lowercase trace_sha256>` with a **distinct** 64-hex trace digest, and timezone-aware, nonfuture `manifest.run_started_at <= observed_at <= verified_at`. Day 9's qualifying evaluator now binds each of the 20 observations to the **same frozen run start** that precedes the candidate's first attempts; Day 10 independently rechecks that boundary using the original `day9_first_run.run_started_at`, including UTC-offset normalization. It also requires the separately exported `day10-recovery.json` to be structurally identical as a JSON object to the `day9_first_run.day10_recovery` retained in the immutable first-run report; its `manifest_sha256` must equal that first run's manifest. Edited or relabeled Day 10 receipts cannot qualify even if they claim `status=passed`; historical exports lacking this binding remain archival only. Neither digest equality nor a self-declared `mode=real` authenticates a real recovery. C and independent D must still validate original private system histories and verifier identity out of band.

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
- `deterministic`: exactly 40 rows with `case_id`, `passed`, `security_passed`, `output_sha256`. For successful attempts, hash actual candidate draft JSON using UTF-8 JSON with sorted keys, compact separators and no NaN. For failed/timed-out attempts, use the **canonical failure-record digest** returned by `candidate_ledger`, require `passed=false`, preserve a separately reviewed `security_passed` boolean, and never count that case accepted. A missing or mismatched digest blocks evaluation.
- `candidate-outputs.jsonl`: exactly 40 first-run rows with the same frozen identity (`case_id`, `manifest_sha256`, `release_id`, `source_revision`, `rollout_manifest_sha256`, `source_set_sha256`, unique `run_id`, provider/model, registry hashes, budget and time limit). Successful attempts omit `attempt_status` or set it to `succeeded`, and carry the full `output` draft object with its exact `source_refs` list. A genuinely `failed` or `timed_out` first attempt **must remain one of those 40 rows** and set `output: null`, `source_refs: []`, `attempt_status`, a short normalized `failure_code`, a SHA-256 `trace_sha256` of the **private** attempt trace, and ordered UTC `attempt_started_at` / `attempt_finished_at`. This structured failure receipt is canonically hashed (bound to case, run and manifest) in the deterministic `output_sha256` field, with `evidence_kind: failure_record`, `output_present: false`, and its trace digest explicit in the generated case receipt. This is a **failure-record hash**, not an invented draft-output hash. Supply reviewer and deterministic/security rows for the failed case; the deterministic `passed` field must be false and the case can never be accepted even if ratings are favorable. `telemetry` is optional on either status, with exactly `tokens`, `latency_ms`, `cost_microusd` nonnegative integers; missing usage remains unknown, **not zero**. Operator C/D must authenticate the trace outside the developer surface. No retry may replace the original row.
- `competitor-outputs.jsonl`: 40 same-task output rows, each carrying the same `manifest_sha256`; competitor metadata in `evidence.json` also carries the same `release_id` and `rollout_manifest_sha256`.
- `operations`: 20 rows with `row` (1..20), exact `scenario` from `OPERATED`, `candidate_revision`, `release_id`, `rollout_manifest_sha256`, `manifest_sha256`, `execution`, `status`, `unauthorized_access`, `unauthorized_mutation`, `observed_at`, `verified_at`, `trace_sha256`, `evidence_ref=sha256:<trace_sha256>`, and `boundaries` keyed by required component. Each boundary contains `mode=real`, `instance`, `trace_sha256`. `observed_at` and `verified_at` must be timezone-aware and nonfuture; `verified_at` must not precede `observed_at`, and `observed_at` must not precede the frozen manifest's `run_started_at`; `evidence_ref` must equal `sha256:<trace_sha256>` and be unique across all 20 scenarios. Boundary `instance` values must be non-sensitive staging labels, never raw user/account identifiers.
- `manifest_sha256`: exact SHA-256 of the frozen manifest file.
- `generation_identity_verified=true` plus `generation_identity_receipt_sha256`: independent D/C verification that the 40 unique run IDs, output hashes, source references, provider/model, prompt/tool registries, context budget and candidate deployment match the frozen candidate. A syntactically valid digest is not authentication; the independent reviewer must inspect the underlying provider/runtime receipts.
- `required_repository_checks=passed` and `canonical_release_contract=passed` from the exact candidate SHA; the CLI refuses to read holdout bytes until both are present alongside custody and readback receipts.
- `candidate_readbacks`: exact `api`, `worker` and `schema` readback objects. Each includes a canonical `readback_sha256` computed over that object with the digest field omitted; API/worker objects must agree with every identity field and all 43 boolean capability keys in the manifest. The CLI checks digest consistency, not source-system authenticity; C/D must independently authenticate the readbacks.
- `competitor`: identity fields and comparable limits described above plus the same `manifest_sha256`, `release_id` and `rollout_manifest_sha256`; if access is unavailable, omit competitor/comparison rows and provide a nonempty `competitor_access_gap` explanation. A missing judgment file when a competitor was available is incomplete evidence, not an access gap.
- `comparisons`: 160 blinded judgment records described above (or omitted, with gap disclosed).
- `comparison_adjudications`: independent third-reviewer A/B decisions with source rationales for every unresolved comparative disagreement.
- `custody`: three distinct pseudonymous IDs `custodian_id`, `developer_id`, `corpus_author_id`; independent operator review=`verified`; custodian positive-read test=`allowed`; developer negative-read test=`denied`; exposure-history review=`true`; replacement of exposed cases=`true`; timezone-aware `verified_at`; and SHA-256 digests for frozen inputs, frozen answers, rubric, exposure history, access log and custody receipt. These are **unverified operator statements to this CLI**, not cryptographic attestations.

The CLI requires this complete receipt and the candidate readbacks before it reads any holdout bytes. The frozen-input, answer-key and rubric digests in the custody receipt must exactly match the corresponding manifest digests. Both `evaluate` and `prepare-blind` require the external custody/readback evidence JSON. C/D must independently authenticate the human identities, positive/negative access tests, source access logs and isolated storage; the CLI's digest checks are not proof of custody.
- `required_repository_checks`: exact map containing `test-and-build`, `Frontend tests and builds`, `coworker`, `browser-qualification`, `PostgreSQL 18 staging compatibility`, `governance-audit` and `ci-merge-gate`, each `success`; `ci_source_revision` must equal the manifest candidate SHA and `ci_evidence_sha256` must identify the exact-head workflow evidence.
- `canonical_release_contract=passed`, `release_contract_source_revision` equal to the same candidate SHA, and a valid `release_contract_evidence_sha256`; `unresolved_high_severity_failures` is a required array.

```bash
# Create the reviewer-facing packet. The packet file contains no candidate identity.
uv run --extra coworker python -m scripts.ruke_pilot_eval prepare-blind \
  --manifest /secure/d/day9/manifest.json \
  --heldout /secure/d/day9/tasks.jsonl \
  --candidate /secure/d/day9/candidate-outputs.jsonl \
  --competitor-outputs /secure/d/day9/competitor-outputs.jsonl \
  --blinding-key /secure/d/day9/blind.key \
  --evidence /secure/d/day9/custody-and-generation-evidence.json \
  --report /secure/d/day9/blind-review-packet.json

# Evaluate after the independent reviewers and all 20 operated receipts are complete.
uv run --extra coworker python -m scripts.ruke_pilot_eval evaluate \
  --manifest /secure/d/day9/manifest.json \
  --heldout /secure/d/day9/tasks.jsonl \
  --candidate /secure/d/day9/candidate-outputs.jsonl \
  --evidence /secure/d/day9/evidence.json \
  --report /secure/d/day9/first-run-result.json \
  --holdout-report /secure/d/day9/day10-holdout.json \
  --recovery-report /secure/d/day9/day10-recovery.json
```

The report uses an exclusive create (`O_EXCL`), never clobbering a previous result. It emits a Day 10 `day10_holdout` artifact (export with `--holdout-report`) carrying the independently verified generation identity, D custody receipt, two reviewers and all 40 security-scored outcomes; this is the exact input shape expected by `scripts/day10_release_decision.py`. It also emits a `day10_recovery` object with all 20 uniquely referenced, release-bound scenario receipts in the exact shape consumed by `scripts/day10_release_decision.py`. Pass `--recovery-report <external-path>` to write that object as a separate immutable artifact directly consumable as the Day 10 `recovery` input, and `--holdout-report <external-path>` to export the independent holdout/custody artifact directly consumable as the Day 10 `holdout` input. Its per-case run receipts preserve unique AgentRun IDs, output hashes, source references, provider/model identity, prompt/tool registry hashes, context budget, time budget and token/cost telemetry. Its first-run receipt also emits the exact Day 10 handoff fields `release_id`, `source_revision`, `rollout_manifest_sha256`, `run_id`, `run_kind=first_run` and per-case `scores` with both reviewers' 0–8 totals and a strict boolean security verdict. The blind reviewer packet contains only task IDs, randomized positions and response A/B. Do not place release IDs, source SHAs, manifest digests, run IDs or the candidate/competitor mapping in the reviewer-facing packet. The operator records the packet SHA-256 and its manifest binding separately in the private evidence log. **A malformed or incomplete first run also writes a failure report** (when the supplied report path is valid) so failure evidence is not lost. Evaluation and blind-packet inputs and reports must be outside the repository; the run manifest's exact candidate revision must match the checkout HEAD. A later attempt uses a **different** filename and `--regression-rerun` to classify the evidence honestly. No script may change these labels to claim new independent measurements. Exit 0 means submitted **operator evidence** passes mechanical gates, *not* that release is authorized. Exit 1 means incomplete/failed gate, exit 2 malformed or missing evidence.


**First-attempt Day 10 lineage (new qualification reports):** The evaluator now copies every original `case_run_receipts` identity into both the preserved `scores.cases` and separately exported `day10_holdout.cases`: `run_id`, `output_sha256`, `attempt_status`, `evidence_kind`, `output_present`, `failure_code`, `failure_trace_sha256`, `attempt_started_at` and `attempt_finished_at`. The primary report also keeps its `candidate_outputs_sha256` and the 40 release/manifest-bound `case_run_receipts`. Day 10 refuses to qualify a first run if a scored/held-out case lacks these fields, reuses a run ID, has a malformed failure record, differs from its original case receipt, or has a missing/duplicate case. A failure/timeout remains rejected with deterministic pass=false and retains its private-trace digest and ordered original timestamps; it is never converted to an output or dropped from the denominator. Earlier first-run reports that omit this cross-binding remain historical evidence, **not qualifying evidence** for a new release; do not edit or overwrite them. Store original private candidate JSONL and independently authenticate its SHA-256 and traces outside the repository. The CLI verifies receipt consistency, **not** that a genuine provider operation occurred or that the custodian is independent.

**Day 10 custody export lineage (new qualification reports):** The original write-once Day 9 first-run report embeds the complete `day10_holdout` object, which is also exported with `--holdout-report` for Day 10. The Day 10 release gate requires the **entire separately supplied holdout object** (including its independent D custody receipt and all 40 cases) to equal the embedded original object; matching only the scored case arrays is insufficient. It independently enforces `holdout.custody_receipt.verified_at < day9_first_run.run_started_at` on normalized timezone-aware timestamps. Missing original exports, substituted custody envelopes, or retroactive access-control verification block `preserved_day9_first_run` and overall release eligibility. Old reports lacking this lineage are archival: do not mutate, replace, or silently backfill first-run evidence to satisfy the revised contract.

**Important:** No document written in this repository, no developer-authored test fixture, no self-declared D identity, and no SHA alone proves access isolation, two actual human reviewers or 20 genuinely operated scenarios. The script emits `custody_independently_verified_by_this_program=false` and `release_authorization=false` even when operator inputs are mechanically complete. Human review plus the canonical cohort release gate remain required.

## Day 9 status on source commit

Implementation and local regressions can be reviewed in the Day 9 PR. **No independent held-out execution, real competitor contest, 20 live fault executions, staging restore, human adjudication or cohort activation is asserted here.** Capture each missing result as a blocker until D/C provide independently verified external evidence. Do not touch production flags or provider side effects as part of this source PR.
