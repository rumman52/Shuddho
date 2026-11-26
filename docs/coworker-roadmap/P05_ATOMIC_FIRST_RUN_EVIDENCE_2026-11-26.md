# Prompt 05 — atomic first-run evidence publication (26 November 2026)

Scope: D09 first-run evidence integrity, reused by the Day 10 decision writer. Base: 43d99fd64467492a7da809cda0ae178191e53981.

The existing Day 9 writer opened the destination exclusively before writing and syncing its bytes. Write or file-sync failure could leave partial evidence permanently published. Reuse the staging evidence writer's same-directory temporary file and exclusive hard-link publication, with a shared byte-level helper. File bytes, JSON formatting, returned SHA-256, no-overwrite semantics and native filesystem exceptions for the Day 9 caller are retained. POSIX mode is 0600. The staging wrapper retains its exception class but consolidates filesystem diagnostic wording.

Tests-first commit: 33b33071c5b88217ec15a444360af5b7c2f37efa. Shared helper: 1baf4423c60d8b571a1d87f9244ea0173446e1ae. Day 9 caller: 7c39e3f91aac64b53b350cf4fa1934b9bce61e40.

Isolated filesystem reproduction: RED 4 failed / 2 passed, GREEN 6 passed. Cases: exact serialization/digest/mode, existing destination, file fsync error, partial write failure, no publication before fsync, directory fsync error. Repository regression tests added but not locally executed because GitHub DNS prevented a clone. Require complete exact-head CI and separate reviewer before merging. A trusted, existing parent directory with hard-link support is required; if directory fsync fails after publication, retain the complete file and fail the operation rather than overwrite/retry the same name.

No assertion of independently controlled custody, tamper-proof storage, full release qualification, or real operated faults. No new approvals, provider calls, deployment, production activation, or spending.

## Failure-boundary follow-up

A truthy non-object manifest was rejected by the main validator but the error-report construction attempted its .get() method, losing the original failure receipt. Tests-first 7bb19a73adc4672daf9da68b3dfe80121e211cb6; source c30f2aadd03011c3f14a5e9a65dedabea78261fd. Require dict before reading its version in the exception path. Six synthetic manifest shapes: isolated RED 4 failed/2 passed, GREEN 6 passed. Integrated tests assert failure artifact digest, no heldout read, and no release authority; repository CI pending. No release or operational credit.
