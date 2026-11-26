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
