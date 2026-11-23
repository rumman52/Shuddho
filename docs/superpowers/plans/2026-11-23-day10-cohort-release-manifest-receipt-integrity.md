# 2026-11-23 — Part 05 Day 10 canonical cohort release operator evidence integrity

## Goal and status
Source-only bounded engineering slice for `scripts/cohort_release_gate.py`. Does not certify pilot GO or activate a cohort. Base main `01314ce5e6502b48d85852324b9208bd1f72873b` (2026-11-23 Dhaka). Distinct from open #897 canary *recovery* parser and #895 health thresholds.

## Root cause (observed on main)
`load_rollout` uses `json.loads(path.read_text(...))`, silently accepting nested duplicate booleans, nonfinite values, symlinked and oversized manifests. `main` calls `load_rollout` for the decision, but separately calls `file_sha256(args.rollout)` **after reading other evidence** for its release digest. An intervening path replacement can bind a successful decision to a different rollout. Optional `--output` uses `Path.write_text`, silently overwriting the first operator result and exposing it under default umask.

## Files and responsibilities
- `tests/test_cohort_release_gate.py`: behavior-first tests for duplicate nested capability, nonfinite input, symlink and oversized manifest, deterministic swap between parse and hash, original input digest, private exclusive output. All fixtures synthetic; no platform/custody receipt.
- `scripts/cohort_release_gate.py`: reuse `scripts.ruke_pilot_eval._read_json_and_sha256` to parse+digest one bounded regular nonlink descriptor; offer existing `load_rollout` with same dict return signature for all callers; use bound digest in CLI; use existing `immutable_write` to protect output first attempt at 0600.
- `docs/coworker-roadmap/DAY10_RELEASE_MANIFEST_EVIDENCE_INTEGRITY_2026-11-23.md`: exact observed root cause, test RED and post-fix CI, residual risks/NO-GO.
- `docs/coworker-roadmap/PROGRESS.md`: prepend dated checkpoint without rewriting historical entries.

## Ordered test-first implementation
1. Confirm current main and all overlapping PRs. Lock branch on exact baseline above. Read AGENTS, README, SPEC, current operator and existing tests.
2. Commit six or more behavioral regressions only; run exact test-only GitHub Actions Python job to establish **RED for new assertions** and unaffected baseline. Reject setup/import failures as invalid red.
3. Implement minimal bounded strict single-inode manifest reader and digest; output via private exclusive writer, preserve existing CLI decision behavior and API signature. No schema migrations, env changes, flags, or production services.
4. Run final-head checks on unchanged source: Python focused + complete, coworker, browser, frontend, PG18 compatibility, repository contract; report skipped governance and failing required merge gate honestly.
5. Record scoped contract/progress, open **draft PR**, request independent review; never merge without review or assert independent D custody, 40/80 scores, 20 operated recoveries, Founder/Owner C signatures, exact runtime/43 flags, or 5–10 admission.
