# Day 1 D — source-grounded workflow corpus and bounded evaluator

This slice prepares 80 repository-grounded workflow scenarios and starts an
**offline evaluator calibration**. It does not measure a model, real customer
outcomes, staging or production. No external inference, provider call, paid
resource, permission change or email send was performed.

## Contract and source truth

The corpus is based on repository revision
`602f76f73ad845fe3ac4b4cb133fd8a07dbd20a8`. Each input is a byte-for-byte frozen
snapshot of an existing dated repository handoff, with original path, SHA-256 and
Git revision in `tests/fixtures/pilot_workflows/suite_manifest.json`.
These are simulated pilot tasks about actual recorded repository evidence;
they are not user/customer source documents or fresh operational observations.
Historical test counts and capability states must remain explicitly historical.

Each scenario contains three known expected facts, localized expected meanings,
bounded lexical assertions, exact supporting quote, source hash and original
line citation. Validation checks every quote and line against frozen bytes.
A regression also compares every snapshot with `git show <revision>:<path>`.
Scenario IDs, dossier IDs and source IDs are unique within their required scope.

| Split | Research bn | Research en | Report + email bn | Report + email en | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Development | 10 | 10 | 10 | 10 | 40 |
| Candidate holdout | 10 | 10 | 10 | 10 | 40 |
| Total | 20 | 20 | 20 | 20 | 80 |

There are **20 distinct evidence dossiers**, ten per split, with no cross-split
dossier/source overlap. Each dossier intentionally has bilingual counterparts
and two different artifact workflows. Thus 80 scenarios are not 80 independent
source topics. Research requires cited findings; report/email requires facts in
both report paragraphs and a reviewable email body. These are content outcome
tasks, not routing-label substitutes.

Development topics: uncertain goal-run retry identity; archived-history replay;
report capability compatibility; exact conversation-source pins; browser
credential/method isolation; worker source revocation; fleet registration;
truthful cleanup; connected-read grant admission; Gmail receipt integrity.

Candidate holdout topics: backup preflight; endpoint validation; governance
result propagation; S3 pagination; cancellation finality; Projects entry;
browser-source erasure; owner code-review limits; text previews; pending-memory
source validity. Prompts ask dossier-specific questions about behavior,
compatibility, recorded results and limits, without supplying the answer key.

## Evaluator and rubric

`scripts/pilot_workflow_eval.py` reuses production `parse_draft` and
`source_references`. It does not import a model adapter, search provider or
network client. The existing research schema's `web-1` citation identifier is a
case-local compatibility alias for a supplied file snapshot; it does **not**
claim a web retrieval. Source IDs and hashes bind that alias to one exact dossier.

Deterministic checks are separately reported:

- Artifact schema and output byte ceiling; declared and observed language smoke
  checks. Bangla must appear in substantive prose, not just metadata.
- Required facts in research finding text or report paragraphs. Titles,
  summaries, source quotes and `missing_information` cannot satisfy facts.
- Exact source scope, research quote grounding and fact-to-citation alignment.
  Report facts must occur in a cited section; email body must contain all facts.
- Explicit historical scope and known false send/activation claims.
- Submission identity, duplicate/missing/unknown outputs and valid resource
  telemetry; unknown telemetry stays unknown rather than becoming zero usage.

Lexical assertions are a bounded regression aid. They can miss paraphrases and
cannot establish semantic entailment, detect every invented claim, judge fluent
Bangla, or establish that an email is useful. No machine score is labeled human
acceptance. Every result retains `human_review_required=true` and the overall
report keeps `human_accepted_outcomes=null`, `quality_qualified=false`.

Independent human review must score semantic factual accuracy, completeness,
citation entailment, language quality, draft usefulness and honest historical
scope. Freeze the human rubric and denominator before any real model run.
The existing SPEC's proposed target of at least 90% human-accepted outcomes is
unchanged; report accepted/total counts per workflow and language. The 40
source-authored development references calibrate scoring and never count as
human-accepted model outcomes.

The executable is bounded to 40 cases per invocation, 2 MB input files and
24 KB draft outputs. It performs zero provider calls and zero external spend.
Reported generation tokens/cost/latency are optional submission evidence and
remain null for the handcrafted calibration outputs. The evaluator does not
claim to enforce a future generation provider's billing budget.

## Frozen integrity and real D blocker

Candidate holdout integrity manifest SHA-256:
`18b856397a33f2cc0c9cafac8b60ef04b39abee313c769c68b9d21b6273a3ac4`.

The same digest is pinned in code, the suite manifest and
`holdout_integrity.sha256`. Case/source drift, even followed by an edited local
manifest checksum, fails validation unless the reviewed code anchor changes.
This is an **integrity freeze, not access isolation**. Developers can read the
candidate prompts, expected facts and all source documents in this repository.
The author has necessarily seen the candidate holdout. A file permission, local
self-attestation or checksum cannot undo that exposure or establish D custody.

`tests/fixtures/pilot_workflows/holdout_transfer_request.json` is the concrete
blocked transfer request. It records that no transfer/access change has occurred
and names the evidence needed from the actual independent human D: a separately
controlled destination, exclusion of development identities demonstrated by a
negative read check, an exposure review and replacement of disclosed tasks,
exact-byte transfer receipt, frozen generation/rubric identities and independently
verified receipt/checksums. Do not paste secrets or administrative credentials
into this repository. No messages or permission changes are authorized here.

Both API evaluation entry point and CLI reject `split=holdout` with a typed
blocker until a separately reviewed follow-up integrates genuinely segregated D
custody. This is a conservative workflow stop, not a security boundary around
Python helpers or readable files. No option accepts a developer-written receipt
as proof. A future D corpus may need a new version because this candidate has
already been exposed.

## Commands and observed evidence

From the repository root, using the existing local `.venv`:

```bash
.venv/bin/python -m pytest tests/test_pilot_workflow_eval.py -q --junitxml=/tmp/day1-pilot-eval.xml
.venv/bin/python -m scripts.pilot_workflow_eval --validate-only
.venv/bin/python -m scripts.pilot_workflow_eval --calibrate --report /tmp/day1-calibration.json
.venv/bin/python -m scripts.pilot_workflow_eval --outputs /path/to/development-outputs.jsonl --report /tmp/day1-results.json
.venv/bin/python -m scripts.pilot_workflow_eval --calibrate --split holdout
```

JSONL submissions have `case_id`, `draft` in the production research/report_email
schema and optional `telemetry` with exactly `tokens`, `latency_ms`,
`cost_microusd` nonnegative integers. Null telemetry is explicitly unknown.
A missing output counts as failure in the full 40-case denominator; duplicate or
unknown IDs fail the invocation. Exit codes: 0 for valid corpus/all deterministic
checks passed; 1 for evaluated failures; 2 for invalid inputs or blocked custody.

Observed on 10 November 2026:

- RED: before implementation, `.venv/bin/python -m pytest
  tests/test_pilot_workflow_eval.py -q` failed collection with
  `ModuleNotFoundError: scripts.pilot_workflow_eval`. The default system Python
  lacked pytest, so it was not used as test evidence.
- GREEN: focused acceptance suite **18 passed, zero skips**. It includes genuine
  mutation failures for changed numeric facts, forged/irrelevant citations,
  unsupplied sources, report-only facts, false send claims, language-content
  mismatch, duplicate/missing outputs, source/case tampering, locally rewritten
  holdout manifests, telemetry and bounds.
- Manifest validation: **80 cases, 40 development, 40 candidate holdout**.
- Development calibration: **40/40 pass**, all four cells **10/10** and required
  fact recall 1.0. Saved report:
  `tests/fixtures/pilot_workflows/development_calibration_report.json`.
- Candidate holdout invocation: **exit 2**, explicitly blocked for independent D
  custody. No holdout outputs generated or scored as qualification evidence.
- Combined new and existing quality-evaluator regressions: **31 passed, zero skips**.
- Python compilation passed. No exact-head CI, independent human acceptance,
  deployed worker, provider model or production qualification is claimed.

## Handoff

Implemented: scenarios, exact-source/line evidence, integrity manifests,
production-schema offline scorer, development calibration references/report,
negative regression coverage and explicit transfer blocker.

Next dependency: an authorized owner and independent human D establish actual
custody and replace exposed tasks as appropriate. Then freeze model/prompt and
resource ceilings, generate real bounded development outputs and review them
before a separately controlled heldout pilot. Keep inference and spend disabled
under this Day 1 slice. Shared progress/CI/ledger updates belong to the parent
integration task; this slice does not edit them.

## Independent-review corrections

Five added regression instances reproduced headings escaping known unsafe-claim checks and metadata bypassing the 2 MB input-file ceiling. The scorer now examines every schema-validated displayed field for known false dispatch/activation claims; fact coverage and language still require substantive text. Hash/checksum metadata is size-checked before reads. New plus existing quality tests: **36 passed, zero skips**. CI uses complete history in its lightweight job because exact historical blob comparisons cannot pass in depth-one checkouts. No human-quality or heldout-isolation claim follows from these checks.
