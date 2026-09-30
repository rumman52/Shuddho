# PA-11 Artifact Quality Evidence

This bounded PA-11 slice converts the existing native Office regression suite into explicit release evidence for a reviewed rollout with `artifact_services=true`.

It does **not** increase slide, row, file, model, provider, cohort, or execution limits. It does not enable a feature flag or authorize an external action.

## Evidence layers

1. **Native machine QA** — `tests/verify_office_native.py` renders and recalculates the existing editable Office fixtures and writes `native-results.json`.
2. **Explicit human review** — a reviewer starts from `docs/artifact-quality-review.template.json`, inspects the exact generated files/screenshots, and binds the review to the native-results SHA-256, source revision, and canonical SHA-256 digest of the editable/rendered/recalculated artifact bytes.
3. **Rollout-bound compiler** — `scripts/artifact_quality_evidence.py` validates both layers and emits an `artifact_quality` evidence object bound to the exact reviewed rollout SHA-256.
4. **Final cohort gate** — when `artifact_services=true`, the structured evidence is mandatory; a passed staging-evidence string by itself cannot qualify artifacts.
5. **Activation handoff** — the release activation bundle records the exact artifact-quality evidence SHA-256, and schema-v16 append independently rechecks that exact file before ledger-attesting the bundle.

## Required native coverage

The native result uses schema v3 and records content hashes for the editable PPTX/XLSX files, rendered PDFs and PNGs, and recalculated XLSX workbooks. The compiler re-reads those files and refuses substituted or missing bytes.

The native result must contain exactly:

- English, Bangla and Arabic PPTX/XLSX renders;
- the dense Chinese PPTX render;
- the long-cell Chinese XLSX render;
- changed, zero, missing and negative spreadsheet recalculation outcomes;
- the known values and recalculation behavior already enforced by the native QA script.

This is bounded regression evidence. It is **not** a universal language-quality guarantee and does not prove identical rendering in every Office application.

## Human review

Copy the template and replace every placeholder. Copy both `native_results_sha256` and `artifact_set_sha256` from the exact reviewed run. All checks must be `true`, `failures` must be empty, and the review timestamp must not predate the native QA results or be more than five minutes in the future.

The review checks:

- editable files open in the supported review application;
- expected text is visible rather than clipped or missing;
- Arabic/RTL layout is usable;
- charts and pagination are intact;
- edited spreadsheet values recalculate correctly;
- no visual overflow is observed in the reviewed fixtures;
- a human confirms the rendered content remains semantically usable.

## Controlled run

Check out the exact release revision before running native QA. Release evidence requires a full source revision, supplied through `SHUDDHO_SOURCE_REVISION`, `RENDER_GIT_COMMIT`, or `GITHUB_SHA`. The command below derives the revision from the checked-out commit with `git rev-parse --verify HEAD`. The native QA command now fails immediately if none is present; it never emits a successful release-evidence file with `source_revision: null`.

```bash
export SHUDDHO_SOURCE_REVISION="$(git rev-parse --verify HEAD)"
PYTHONPATH=.:tests uv run --extra coworker python tests/verify_office_native.py /secure/artifact-qa

cp docs/artifact-quality-review.template.json /secure/artifact-qa/human-review.json
# Review the exact files/screenshots and fill the review JSON.

uv run python scripts/artifact_quality_evidence.py \
  --rollout /secure/release/cohort-rollout.json \
  --native-results /secure/artifact-qa/native-results.json \
  --human-review /secure/artifact-qa/human-review.json \
  --output /secure/release/artifact-quality-evidence.json
```

Reference the output from the `artifact_quality` record in staging evidence and pass the same file to both the final cohort gate and the release activation bundle.

## Failure and rollback semantics

A changed rollout, source revision, native-results file, review file, missing render case, recalculation mismatch, or failed human check makes the evidence invalid.

The gate does not modify runtime state. If artifact quality is not qualified, keep `SHUDDHO_ARTIFACT_SERVICES_ENABLED=false` for the reviewed rollout or remove Artifact Services from that rollout and regenerate its evidence. Existing accepted work and stored artifacts retain their current compatibility behavior.
