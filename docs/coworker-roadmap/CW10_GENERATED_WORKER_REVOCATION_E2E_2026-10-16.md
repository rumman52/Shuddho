# CW-10 — model draft → owner review → worker revocation acceptance (phase 7)

**Exact baseline:** `main` `4b456bf41ad324d79e142c3dd39e4a49e9e2a612`, merged [PR #429](https://github.com/rumman52/Shuddho/pull/429); final-head [PR CI #38852014466](https://github.com/rumman52/Shuddho/actions/runs/38852014466) and merged-main [CI #38852778094](https://github.com/rumman52/Shuddho/actions/runs/38852778094) passed all three required jobs. No open PRs at branch creation.

## Missing acceptance evidence

Each prior CW-10 slice proved isolated pieces: owner-triggered model draft, review hash, user decision, one SQL-owned sandbox execution, claim authorization and generic stop handling. None proved the **combined** generated source identity across the full lifecycle, especially that owner revocation **after source release to a worker process** leads to a fail-closed stop without producing a success receipt or leaving the on-disk source in the Python worker's temporary directory.

## New synthetic end-to-end regression

In `tests/test_agent_code_proposal_persistence.py`, with actual owner-authenticated FastAPI endpoint and SQL/worker implementations:

1. Create an owned Runtime v3 run, enable independent inert model draft/dispatch flags *inside an isolated test fixture only*, stub the DeepSeek result and generate one immutable bounded Python proposal. Assert no code executed, no worker row until the human review and dispatch.
2. Record exact human approval through the real owner review endpoint. Dispatch with that exact hash; replay yields one identical execution/session identity without repeating the model call, and the SQL execution JSON stores **only the source reference**, never Python bytes.
3. Worker claim is allowed to return the exact approved source/hash; a successful synthetic worker observation settles one result; no duplicate claim or new execution on an owner retry.
4. In a separate path, after worker claim, call the actual Python sandbox worker `execute_claim`. Its bubblewrap process is **replaced by a synthetic Popen** to avoid unqualified bwrap/network-isolation claims. The test verifies the actual worker writes read-only `main.py`, the owner then revokes the stored source, the live `SandboxRepository.worker_control` returns STOP, the worker terminates its process, refuses to post completion, removes temporary source/scratch paths, and rejects late completion and retry. Assert the SQL source snapshot was erased and the lease revoked.

**Strict evidence boundary:** Popen/bwrap process is simulated, provider is mocked; API/SQL/worker/temporary-file control paths are real Python. This is a repository regression, **not** operated bubblewrap, real OS process-group kill, memory zeroization, S3 erasure, PostgreSQL concurrency/Temporals restart, security review or staging evidence. No capabilities are enabled in a deployment.

## Required CI

Exact final-head `test-and-build`, mandatory zero-skip `coworker` (this file is part of the required CW-10 suite), and `ci-merge-gate`. A failed fixture or unexpectedly passing late result must fail the CI. After CI, independently review the changed test and document why synthetic process evidence is not equivalent to operated isolation.

## Next acceptance

- Run a controlled staging worker with real bubblewrap, no-egress OS namespace, denied private mounts, actual revocation/worker process-group kill and observed ephemeral source deletion under PostgreSQL and Temporal replays. Verify exited process, output artifact and no duplicate/late receipts using an owned synthetic account.
- Test simultaneous owner dispatch, revoke and duplicate HTTP retries with real PostgreSQL under worker claim, including process restart.
- Finish CW-11 reviewed skill activation and CW-09 browser operated DNS/SSRF/cleanup qualifications; freeze English/Bangla coworker scenario and model-eval rubrics.

**Authority:** review branch only. Do not merge, deploy, enable model-generation/dispatch flags or claim release readiness without separately authorized gates.
