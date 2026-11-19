# Day 6 export-manifest rejection regressions — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Repair the Day 6 export-manifest regression contract so malformed renderer output fails before storage and malformed persisted manifests fail before task completion.

**Architecture:** Preserve the existing production validator in `services/coworker/exports.py` and the completion guard in `services/coworker/runner.py`. Split the test boundary: invalid renderer output is rejected during export; a valid native export whose persisted manifest is later incomplete, duplicated, or unexpected is rejected during completion. Make the regression module an explicit zero-skip Coworker CI gate.

**Tech Stack:** Python 3.11, pytest, python-docx, pypdf, WeasyPrint, GitHub Actions, existing local test storage.

**Spec:** Rukh AI / Shuddho Part 03, Day 6 export regression (pages 8–9); GitHub issue #732; existing `validate_day6_exports` and `DocumentRunner` contracts.

## Global Constraints

- Malformed file sets and malformed native bytes fail before storage publication.
- Persisted manifests are revalidated before completion, even after a valid native export.
- Persisted-manifest rejection tests use valid native DOCX/PDF fixtures from the existing renderer.
- Assert task state and zero published artifact records for every rejected path.
- Preserve production validators, private storage ownership, checksums, and retry semantics.
- Synthetic/local-only tests; no real provider, email send, staging mutation, deployment, migration, telemetry ingestion, or paid resource.

## Review Focus

- Missing renderer output: reject before any storage PUT.
- Duplicate renderer filename: reject before any storage PUT.
- Unexpected renderer filename: reject before any storage PUT.
- Invalid DOCX or PDF bytes with otherwise valid names/MIME: reject before any storage PUT.
- Missing, duplicate, or unexpected persisted manifest entries after a valid export: refuse completion and create no artifact records.

---

## Task contract (based on `docs/coworker-roadmap/TASK_TEMPLATE.md`)

- **Objective and user-visible behavior:** A task cannot be marked completed or expose downloadable artifacts unless all four expected native outputs have passed validation and the persisted manifest remains complete.
- **Dependency tasks and current evidence:** Existing native export validation from #766 and native recovery fixture repair #774 are present. Day 6 tracker #732 remains open. PR #801 records three failures in this regression module on the earlier base; the current main still contains the unchanged failing test file.
- **Base branch/SHA:** `main` at `8afcfccf409c5a01fd70a7966fb4b538575f502f`.
- **Work branch/PR:** `codex/day6-export-manifest-rejections-20261119`; [draft PR #804](https://github.com/rumman52/Shuddho/pull/804).
- **Existing interfaces to reuse:** `DocumentRunner.run_for_test`, `DocumentRunner.phase`, `render_in_subprocess`, `validate_day6_exports`, `container.storage.put`, `container.repository.step`, and `container.repository.get_task`.
- **Exact files to create/modify:** `tests/test_export_manifest_rejections.py`, `.github/workflows/ci.yml`, this plan, and `docs/coworker-roadmap/PROGRESS.md`.
- **New interfaces/schema:** None.
- **Acceptance scenarios and assertions:** (1) missing/duplicate/unexpected renderer file sets fail during export; (2) invalid native DOCX/PDF bytes fail during export; (3) valid native outputs followed by a corrupted persisted manifest fail during completion; (4) every rejection leaves task state failed, with no published artifact records; (5) export-time rejection performs zero storage PUTs; (6) completion-time manifest rejection follows four successful native PUTs but still publishes no artifact records.
- **Reproduction / initial failure:** The existing parametrized test supplies synthetic non-DOCX/PDF bytes, mutates the renderer output set, and expects the error from the later completion phase. The production export validator correctly rejects those malformed renderer outputs first. PR #801 records the three failures in `tests/test_export_manifest_rejections.py`; current main still has the same test blob.
- **Expected failure outcomes:** Export-time invalid sets/bytes return `export_invalid` before storage. Completion-time invalid persisted manifests return `export_invalid` before artifact publication.
- **Tests and required CI commands:**
  ```bash
  uv run --locked --extra coworker pytest -q tests/test_export_manifest_rejections.py
  uv run --locked --extra coworker pytest -q tests/test_export_manifest_rejections.py tests/test_coworker_office.py tests/test_coworker_research.py tests/test_coworker_services.py
  ```
  The Coworker job must run this module with `scripts.mandatory_test_gate` and preserve its JUnit report.
- **Secrets / owner / grant / approval / egress boundaries:** FakeModel and synthetic project notes only; local SQLite and local storage; no credentials or network providers.
- **Budget / timeout / cancellation / revocation behavior:** No external provider calls or paid resources; renderer subprocess uses the existing bounded timeout.
- **Default-off gate and rollback:** No feature flag or runtime authority changes. Revert the test/CI/documentation commit if the regression contract is wrong.
- **External prerequisites:** None for repository tests. Staging acceptance remains separately blocked by approved synthetic owners, matching API/worker/schema identity, and independent review.
- **Out of scope:** Full Day 6 golden workflow, live Bangla/English provider outputs, two-owner hosted retrieval, worker/browser restart, 40-case evaluation, email sending, staging deployment, schema migration, PostHog ingestion, pilot or production activation.

## Execution steps

### Task 1 — Establish the failing CI baseline

- [x] Add an explicit JUnit-backed Coworker CI step for `tests/test_export_manifest_rejections.py`.
- [x] Open draft PR #804 and capture the initial failing job before changing the test contract.

### Task 2 — Separate export-time rejection from completion-time manifest rejection

- [x] Rewrite renderer-set cases to assert `export_invalid` during `run_for_test`, zero storage PUTs, failed task state, and no artifact records.
- [x] Add DOCX and PDF malformed-byte cases using `render_in_subprocess` for the otherwise-valid native outputs, corrupting only the selected native body.
- [x] Add missing/duplicate/unexpected persisted-manifest cases. Use the real renderer, alter only a copied `repository.step("export")` result at completion, and assert rejection after four storage PUTs with no artifact records.

### Task 3 — Verify and hand off

- [x] Run the focused regression module and the full impacted Day 6 suite.
- [x] Inspect the exact PR code-head test/build, frontend, browser, PostgreSQL 18, and Day 6-specific Coworker gates; record results and skips honestly.
- [ ] Wait for the full Coworker job in run #44583092791 to finish; at the last readback it was still running downstream qualification at step 47/79. Do not claim the full Coworker job is green.
- [x] Review the diff against #732 and the Part 03 acceptance contract; update `docs/coworker-roadmap/PROGRESS.md` with the verified code SHA, PR, CI run, test counts, and remaining live blockers.
- [x] Keep the PR draft; do not merge or claim Day 6/staging acceptance.
