# Days 3–6 Cross-Case Artifact Identity Verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps follow TDD and preserve real hosted acceptance boundaries.

**Goal:** Reject a Day 6 four-cell receipt if a native artifact ID appears in more than one workflow/language output, even when each cell independently lists a DOCX and PDF.

**Architecture:** Extend the already merged `scripts/staging_days3_6_acceptance.py::check_day6` evidence-consistency guard, without adding a new model/provider/storage path. Keep a single set of all artifact IDs across the four cases and reject a reuse before accepting a cell. Continue returning `evidence_internally_consistent_not_live_attested` on internally consistent synthetic fixtures.

**Tech Stack:** Python 3.11+, pytest, GitHub Actions mandatory JUnit test gate.

**Spec:** User-supplied `03_Rukh_AI_Product_Workflows(1).docx` Part 03, Day 6 D06.T05–T07, especially native owner-retrievable files and the four workflow/language outputs; original tracked issue #732.

## Global Constraints

- Never invent operated browser/model/worker/storage receipts. Synthetic test data remains synthetic.
- Preserve one frozen source/API/worker/model/schema release identity across the four-day verifier.
- Require native editable DOCX and PDF per Day 6 workflow/language cell.
- Preserve owner A readback and owner B denial; no external email sending or new permissions.
- Change only the consistency validator, its existing synthetic tests and this plan; no live deploy/migration.

## Review Focus

1. Same artifact ID reused for two languages of one workflow must fail.
2. Same artifact ID reused for separate workflows must fail.
3. Same artifact ID with different checksums/receipt references must still fail.
4. Four independent pairs must remain accepted as internally consistent, **not** live verified.
5. Existing owner/hash/MIME/missing artifact checks must not be weakened.

---

### Task 1: Reproduce reused cross-cell identity

**Files:** Modify `tests/test_staging_days3_6_acceptance.py`.

**Interfaces:** Use `evidence()`, `validate(args)`, and `gate.Days36EvidenceError` in the current suite.

- [ ] Add parametrized tests that duplicate a native file `artifact_id` between two different Day 6 cases.
- [ ] Run the existing CI test-only head: `uv run pytest tests/test_staging_days3_6_acceptance.py -q`.
- [ ] Confirm the new cases fail because the current implementation accepts cross-case duplicates.

### Task 2: Reject reused IDs, preserving existing per-case checks

**Files:** Modify `scripts/staging_days3_6_acceptance.py::check_day6`.

**Interfaces:** Existing `check_day6(release, data, frozen) -> datetime` and `Days36EvidenceError` unchanged.

- [ ] Add one day-wide native artifact ID set before the four-cell loop.
- [ ] Reject any repeated ID, including IDs shared across case boundaries, before adding to the set.
- [ ] Verify the focused test passes; retain the existing combined uniqueness checks.

### Task 3: Qualify and document

**Files:** Existing `.github/workflows/ci.yml` already runs the full acceptance test module under `mandatory_test_gate`; do not duplicate.

- [ ] Inspect exact-head mandatory JUnit job result, not prior commits.
- [ ] Record RED→GREEN proof and all unresolved governance/operated-release blockers in PR.
- [ ] Open PR for independent review; never merge around an incomplete governance gate.
