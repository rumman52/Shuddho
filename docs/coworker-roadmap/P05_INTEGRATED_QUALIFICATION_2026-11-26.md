# Prompt 05 integration candidate — 26 November 2026

Base main: `43d99fd64467492a7da809cda0ae178191e53981`. Original PR heads:

- #932: `9345e90daed107f3492f626113e9aae0e1074ba9`
- #936: `94d025006bfc35a313ff38c5f6b7f42cff595031`
- #940: `f70107ad83a81fa064c2e4de8f8b551901720f8a`
- #943: `337d7633f3539e98feeea16e1acca5e4b08e7397`
- #952: `80714e24fb82c7bd5f0b9c32697df7391e917b1b`
- #953: `c4314aefb21ee922bd252ff5974cbea63d8253b6`
- #954: `9022118b5558f1373f12fcce80ea275a7eea4896`

This integration-only change combines all 21 paths from seven existing draft PRs without altering their branches or main. Shared test additions and progress notes are all retained; the overlapping Day 10 import retains canonical_sha256 and validate_candidate_readbacks, and the approval helper accepts both rollout and final_readbacks keyword-only parameters. The call site supplies both. Individual upstream patches are reconstructed against the original base and matched to exact head file contents for the eight shared source/test/runbook paths. The seven progress prefixes are preserved verbatim. Unique-file blobs are reused unchanged. This is a source integration candidate, not independent qualification.

Run exact integrated PR CI, inspect all jobs (including coworker, browser and PG18), obtain independent review and resolve governance #484 before any protected main merge. Do not use individually passing runs as combined evidence. Holdout #665 remains blocked; no secret read, deployment, provider calls or admission. Render workspace confirmation, staging migration/backup-restore, independent human signoffs and operated evidence remain external prerequisites.

## Evidence nesting correction (same integration branch)

Initial combined head 2afcb0afe6fb2a42bc10d3a2d55abbd245632615, CI 45786546832, test-and-build job 139794726771: 4017 passed, 109 skipped, 6 warnings; separate 551 passed, frontend/browser and ancestry succeeded; coworker and PG18 still running when inspected. No transfer of these results to the updated head.

The shared strict JSON reader let parser RecursionError escape the ordinary evidence boundary, and on Python 3.13 a nesting depth above Python's configured recursion limit could still decode/encode. This risks losing the first failure report and makes depth acceptance interpreter-dependent. Tests-first f2f38c859744176dfc0289074c2a9791098305a9 and 6ab37bd49c6464eef950f34d3665c63b4de3a11a; source 3d41a72213ea964bf3580c74c63bdb5abfad9c73. Require maximum 128 nested JSON containers using an iterative depth-only stack; normalize parser/encoder recursion as existing EvidenceError. No change to the size cap or legitimate quality/security thresholds. Actual isolated source excerpt RED 5 failed/6 passed, GREEN 11 passed; exact 128 boundary, Unicode string brackets, flat arrays, duplicate/nonfinite and cycles covered. New repository tests check actual Day 9 pre-custody failure and immutable Day 10 NO-GO. Full updated CI required. No protected evidence opened.
