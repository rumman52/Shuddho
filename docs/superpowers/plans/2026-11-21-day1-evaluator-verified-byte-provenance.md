# Day 1 evaluator: bind checked source snapshots to the bytes actually scored

> Execute using the Superpowers systematic-debugging, test-driven-development, executing-plans and verification-before-completion skills.

**Authority:** Attached five-part Rukh AI execution instructions (Part 01 requires first testable missing foundation behavior and independent D custody, Part 03 Day 6 requires exact source/file integrity), repository `AGENTS.md`, [10-day plan Day 1 ¶141–152](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit), [board #737](https://github.com/rumman52/Shuddho/issues/737), [issue #727](https://github.com/rumman52/Shuddho/issues/727), [D corpus issue #665](https://github.com/rumman52/Shuddho/issues/665), [Day 1 evaluation contract](../../coworker-roadmap/DAY1_EVALUATION_2026-11-10.md).

**Base main:** `57b0cbce15eaf5517cc6e78fff399d93faee87ad`. **Branch:** `fix/day1-evaluator-verified-bytes-20261121`. No preceding PR should be duplicated: earlier export tests already guard malformed native and persisted manifests; prior Day 1 PR #863 made a separate governance JSON reader no-follow.

## Root cause, scope and design

`scripts/pilot_workflow_eval.py::_verified` reads and checks a file hash, returns only its `Path`, and `load_suite` then *reopens* that path for `path.read_text` (sources) or `read_outputs(path)` (case and reference-output JSONL). The scored source and case rows can therefore differ from the bytes whose digest was checked. `sha256_file`, `_json` and `read_outputs` also check `path.stat().st_size` then call unbounded `Path.read_bytes/read_text`; intervening symlink swaps or growth can bypass the pre-read bound and direct symlink policy. This matters because the Day 1 D corpus is only source-calibration evidence, and even that evidence must describe the bytes actually consumed.

Choose one bounded implementation rather than a new evaluator or custody mechanism:
- Add a private `_read_regular_bytes(path,label)`: one POSIX `O_NOFOLLOW|O_RDONLY|O_NONBLOCK` FD (fail closed if `O_NOFOLLOW` unavailable), `fstat` opened regular inode/size, read at most `MAX_FILE_BYTES+1`, close on every path. Raise `ValueError` on missing/symlink/oversize without echoing paths/secrets. Preserve raw-byte SHA-256.
- Change `_verified` to return the *verified bytes*, not a re-openable path, and parse sources, cases and reference outputs from those exact bytes.
- Bind the frozen suite/holdout manifest JSON decoding and digest comparison to their *same raw bytes*. Read checksum with the same bounded helper. Keep `read_outputs(path)` as a backwards-compatible public interface that parses bytes loaded by that helper.
- Preserve duplicate-key rejection, stable case matrix, human `quality_qualified=false`, `--validate-only`, the explicit independent D holdout block, model-free provider-free execution and current CLI statuses.
- Do not claim this fixes compromised parent-directory swaps, mutable source after a verified read, privileged storage custody, or a live operated model outcome; bound the security claim to what the code actually guarantees.

## Task 1 — TDD actual RED

- [x] Add deterministic regression cases in `tests/test_pilot_workflow_eval.py`: monkeypatch `Path.read_text` of one source and one case JSONL so *the second read* delivers additional, valid but unreviewed content. Require that `load_suite` can only load content matching the pinned digest, with no injected marker.
- [x] Direct symlink to an otherwise valid JSONL output must be refused by `read_outputs` even if the file is small.
- [x] Commit tests only, run exact test-only GitHub Actions, retain the three targeted failures and original suite pass/fail/skip. A failed CI run is RED, not readiness.

## Task 2 — GREEN minimum patch

- [x] Implement the single-read byte contract in `scripts/pilot_workflow_eval.py`, not the renderer or production artifact paths.
- [ ] Run `uv run --locked --extra coworker pytest -q tests/test_pilot_workflow_eval.py` if a real checkout is available; otherwise rely on exact GitHub Actions and disclose local unavailability.
- [ ] Read exact final-head `test-and-build`, frontend, PostgreSQL 18, browser, full Coworker, PR ancestry, governance and merge gate. Do not treat skipped governance / draft-approval check failure as native merge success.

## Task 3 — evidence and independent review

- [x] Create `docs/coworker-roadmap/DAY1_EVALUATOR_VERIFIED_BYTES_2026-11-21.md`, update historical `PROGRESS.md` with exact RED and GREEN SHA and run links.
- [x] Open a DRAFT PR; link Day 1 #727, independent custodian #665, CTO #737 and Linear MD-5. Require real independent reviewer and operator receipts before merge/pilot.
- [x] Preserve original review, cost, staging and custody requirements: approved GitHub App/native negative+positive merge test; Founder+C approved isolated DB+objects restore, API/worker/Temporal identity and bounded model/spend; independent D replacement, freeze and denial proof for 40 holdout cases and 20 real recoveries; separate Founder/C exact-release GO/NO-GO.

**Stop condition:** The branch can be SOURCE_ONLY repository-verified with exact-head passing CI, but the 100-row ten-day project is still NO-GO without external owner-controlled gates. A reviewed PR is not pilot enrollment.

## Actual test-first execution checkpoint — 21 November 2026

- Test-only RED final SHA `b93587ed3f987356e5285c1cfc1be5f505764647`; [Actions #44921905522](https://github.com/rumman52/Shuddho/actions/runs/44921905522) `test-and-build` 3 targeted FAILED / 3494 PASSED / 105 SKIPPED / 6 WARNINGS. The recorded failure messages respectively showed source hash mismatch, extra unreviewed case field accepted, and `DID NOT RAISE ValueError` for symlink submission. Previous cancelled PR event `fbeaf1f9c074617bafa968f38e7746636bad4f63` was not counted as RED.
- Implementation commit `3bfc83d98364080024c6eedf6db9327e986c30ff` binds the scorer to one bounded nofollow regular inode read. Dedicated [task contract](../../coworker-roadmap/DAY1_EVALUATOR_VERIFIED_BYTES_2026-11-21.md) and `PROGRESS.md` evidence saved. [Draft PR #870](https://github.com/rumman52/Shuddho/pull/870).
- Exact final-head GREEN must be inspected after documentation commits; PR-event governance audit SKIPPED and pending independent human review are operational blockers, not software test success.
