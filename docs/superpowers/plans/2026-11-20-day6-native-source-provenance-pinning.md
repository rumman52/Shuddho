# Day 6 Native Source-Provenance Binding — Part 03

**Contract:** Rukh AI / Shuddho Part 03, Days 3–6, Day 6 D06.T02, T05, T06, T07 and G01/G04; issue #732; Linear MD-7.

**Goal:** A research/report native export must not be published when its source-manifest.json omits, substitutes, injects or changes the selected source metadata and digest from the saved reviewed draft. Preserve normal export recovery, owner scope and native rendering.

## RED — characterization before implementation

- Test-only commit `92a0f94601a3fa69b1a28d60ec7f247ab13c39b8` introduced mutated manifest test cases for absent sources, a substituted SHA-256, and a forged foreign source.
- Baseline implementation checked only that manifest.sources was a list of records without raw text. Those payloads have the correct four filenames, MIME types, and valid DOCX/PDF bytes, so format checks alone do not establish provenance.
- Completion tests must preserve the original source IDs while altering metadata so that the earlier reference-ID guard does not mask the provenance readback check.
- Treat this as source-level RED characterization unless the exact test-only CI job confirms the failing cases. Do not invent a CI receipt.

## GREEN — bounded change

1. Pass the saved and versioned `draft.sources` snapshot to `validate_day6_exports` at both `DocumentRunner.export` and `DocumentRunner.complete`.
2. Require manifest.sources to equal the snapshot, including IDs, version/digest metadata, length and ordering. Fail before object PUT on a renderer mismatch.
3. Repeat the check at storage readback; do not publish any artifacts from a stale or forged manifest after worker recovery.
4. Preserve the existing exactly-four file inventory, nonempty/native DOCX/PDF, MIME, language, expected headings, missing-information status, source-reference authorization, and owner-bound object SHA checks.
5. Do not add provider sends, role permissions, paid models, migrations, background AgentRuns or deployment.

## Verification

Required focused command, on the exact head:

```bash
uv run --locked --extra coworker pytest -q \
  tests/test_export_manifest_rejections.py \
  tests/test_coworker_office.py tests/test_coworker_research.py \
  tests/test_coworker_services.py
```

Review the mandatory Coworker CI Day 6 manifest-rejection and native export qualification steps, independent GitHub PR approval, and all affected full checks. Treat a running/cancelled/skipped job as nonpassing.

## Hosted release boundary

This change is **SOURCE_ONLY**, not proof of an operated Day 6 artifact. No current receipt establishes an approved two-owner staging source, real provider request, downloaded owner-A object bytes, owner-B denial, email send audit or a same-SHA API/worker/frontend rollout. No Day 3–6 hosted exit moves to PASS on this PR alone. Keep the #799 receipt-verifier contract and MD-6 Day 2 prerequisites open.
