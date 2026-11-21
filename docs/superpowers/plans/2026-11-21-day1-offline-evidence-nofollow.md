# Day 1 offline governance JSON evidence — atomic no-follow read

> Execute this bounded branch using the test-driven-development and verification-before-completion Superpowers skills. Checklist state is evidence-based.

**Authoritative source:** [Ruke AI Ten Day Completion Plan, Day 1 ¶141–152](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit); [Day 1 issue #727](https://github.com/rumman52/Shuddho/issues/727); [review policy source](../../infra/github/main-ruleset.json) and existing `scripts/day1_ruleset_drift.py` / `tests/test_day1_ruleset_drift.py`.

**Goal:** Keep native-ruleset offline evidence fail closed if its source file is swapped to a symlink between filesystem inspection and reading. Use one no-follow file descriptor, bound the bytes read, require a regular file, preserve exact-byte SHA-256 evidence and all existing CLI statuses.

**Base SHA:** `500afb5c0c08d6988fd55959a6a1185bc0b98c9e` (merged PR #861). **Branch:** `fix/day1-offline-evidence-nofollow-20261121`.

## Existing root cause and ruling

`_read_json(path)` currently performs `path.is_symlink()`, `path.is_file()`, `path.stat().st_size`, then `path.read_bytes()`. A symlink substitution after the checks and before the final open is accepted if the replacement contains a valid JSON object. This violates the existing documented rejection of symlinked inputs. Checking the bytes length after reading also allocates the entire post-swap file rather than bounding the read. A genuine owner-approved snapshot must not be replaced between validation and read.

**Ruling:** Treat the input as adversarial local evidence. Open with `os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK` (no silent downgrade where `O_NOFOLLOW` unavailable), `os.fstat` the opened descriptor, require `stat.S_ISREG` and size no greater than `MAX_READ_BYTES`, read at most `MAX_READ_BYTES+1`, reject oversized input, close the descriptor in all paths. Continue to compute `sha256` from the actual read bytes rather than metadata. No filesystem writes or network calls. This closes the *direct path symlink swap* only; an untrusted administrator readback cannot be promoted into authenticated live merge controls.

## Task 1 — RED reproducible source defect

- [x] Modify `tests/test_day1_ruleset_drift.py` to create three valid JSON inputs plus a valid shadow branch snapshot. Use a deterministic monkeypatch that substitutes a direct symlink at whichever operation opens the source: original `Path.read_bytes` for existing implementation and `os.open` for the protected implementation. Assert that the CLI fails with exit 2 and `status=blocked_input` when a file is replaced just before opening.
- [x] Commit **tests only**; run GitHub Actions against the exact test-only head. Read `test-and-build` failure trace to ensure the new test returned an unacceptable successful candidate (rather than import errors or missing dependencies). Record RED SHA, run, pass/fail/skip.
- [x] Existing positive offline receipt tests must remain unchanged and pass on GREEN.

## Task 2 — minimal production correction

- [x] In `scripts/day1_ruleset_drift.py::_read_json`, replace only precheck-then-read with a descriptor-based nofollow, regular-file, bounded read, always close the FD. Keep existing JSON duplicate-key / non-finite / invalid decoding protections, SHA and report fields.
- [ ] Run the exact final-head GitHub Actions `test-and-build`, `coworker`, frontend, browser, PostgreSQL 18 compatibility and ancestry. Inspect `ci-merge-gate` and explain any failure; PR-event `governance-audit` SKIPPED is not a live privileged audit. If local checkout unavailable, do not claim the focused local `uv run --extra coworker pytest -q tests/test_day1_ruleset_drift.py tests/test_main_protection_audit.py` ran.
- [x] Confirm no change to native GitHub controls, application secrets, provider budgets, generated code execution, staging migrations, telemetry, held-out cases or pilot admission.

## Task 3 — operator handoff

- [x] Create `docs/coworker-roadmap/DAY1_OFFLINE_EVIDENCE_NOFOLLOW_2026-11-21.md`, prepend `docs/coworker-roadmap/PROGRESS.md`; record RED/GREEN exact revisions, statuses, limits and owner-controlled blockers.
- [x] Open a *draft* PR, link Day 1 issue #727 and Linear MD-5, request distinct human review. Do not merge or mark release-qualified without actual native denied/permitted controls, owner-approved staging restore/resource, D-only holdout and Founder/C GO/NO-GO.
- [x] Treat all code-only results as SOURCE_ONLY; do not falsify external approvals.

**Review caution:** The new patch is evidence-path hardening, not an actual authenticated administrator readback. A no-follow read cannot prove a GitHub rule is enforced; operational evidence remains a separate Day 1 gate.

### Actual execution checkpoint — 21 November 2026

- **Base:** `500afb5c0c08d6988fd55959a6a1185bc0b98c9e` (merged PR #861, separately scoped from this task).
- **Actual test-only RED SHA:** `d70664d3b38f84a3fdc02ee2c79b2680405ad1a1`; [Actions #44916640894](https://github.com/rumman52/Shuddho/actions/runs/44916640894) `test-and-build` **3 expected FAILED / 3359 PASSED / 105 SKIPPED / 6 WARNINGS**. Test assertions explicitly `assert 0 == 2` on `branch`, `ruleset`, `policy`; no unrelated collection failure.
- **Source patch:** `84c09b339b5a50de079419485ed138effe0101db`; reads through no-follow descriptor, validates `fstat` regular mode/size, bounds `os.read` and closes descriptor; preserves error status and digest.
- **Task contract:** `docs/coworker-roadmap/DAY1_OFFLINE_EVIDENCE_NOFOLLOW_2026-11-21.md`; evidence checkpoint in `PROGRESS.md`; [draft PR #863](https://github.com/rumman52/Shuddho/pull/863).
- **Final-head CI:** Pending readback after documentation commits; PR governance audit SKIPPED is not a success, and draft independent review remains a separate gate.
