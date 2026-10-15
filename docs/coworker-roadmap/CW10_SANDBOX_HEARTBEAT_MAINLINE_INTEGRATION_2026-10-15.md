# CW-10 — Sandbox heartbeat fail-closed mainline integration

**Mainline integration checkpoint:** 15 October 2026 (Asia/Dhaka). **Current main base:** `ce76803eb20e8383bb507f02e2cad17d9ff77d3f`, [merged PR #416](https://github.com/rumman52/Shuddho/pull/416). [PR #417](https://github.com/rumman52/Shuddho/pull/417) was merged into its *feature branch*, which did not integrate its worker changes onto `main`; inspection of `main:scripts/sandbox_worker.py` confirmed the heartbeat path still swallowed control errors and ignored unknown action values. **Review branch:** `codex/cw10-sandbox-heartbeat-mainline-20261015` is forked from current main and ports the worker/test-only source changes. **No merge or release authorization.**

The original reviewed task contract follows. Its older base/stacking notes are historical; this new review branch targets `main` directly. The final exact head requires fresh CI and an independent security review.

---

# CW-10 — fail closed when sandbox control heartbeat cannot confirm authority

**Date:** 15 October 2026 (Asia/Dhaka). **Base dependency:** [draft PR #416](https://github.com/rumman52/Shuddho/pull/416), branch head `e6902c6efe784dd1fbd93ad088357645eb3048b7` from main `baa484ef861e41daf7653a29f6aaa07720932055`. **Work branch:** `codex/cw10-sandbox-heartbeat-fail-closed-20261015`. Stacked so no unresolved same-file/different-protocol test conflict is hidden.

## Defect and trust boundary

`scripts/sandbox_worker.py::execute_claim` runs untrusted Python in a separate bubblewrap subprocess and periodically calls the authenticated sandbox `/control` endpoint for continued authority. It previously terminated the subprocess only for `sandbox_worker_claim_invalid` errors or an explicit `stop` response. Other `WorkerError` outcomes such as timeout, HTTP 500, revoked token or invalid response from the API were swallowed; an empty or unknown action was also treated as permission to continue running until another response or wall timeout.

Failing to obtain fresh heartbeat authority must **not** allow code to continue. This is source-level review of the real worker path; it is not evidence that such a live outage was exploited.

## Bounded implementation

- Any `WorkerError` from the heartbeat immediately calls `terminate_group` and breaks the execution loop. The process returns existing typed `WorkerError("worker_interrupted")` and the outer worker reports failure when the server is available.
- Accept only the explicit `continue` action to keep running; `stop` and unknown/missing action terminate.
- Keep the previously valid `continue`, sandbox resource ceilings, networkless executor policy, output validation and existing API/store semantics intact. Do not add a new execution ledger, alter Temporal history or grant code new authority.

## Acceptance and evidence

- Parameterized regression in `tests/test_sandbox_control_plane.py` drives real `execute_claim` with an instrumented fake subprocess and fake worker control HTTP client. A network timeout, HTTP 500, unauthorized worker, empty action, unknown action or explicit stop must make the worker call `terminate_group` exactly once, never call `/complete`, and raise `worker_interrupted`. This uses a fake process, so real process-group kill behavior remains staging-unverified.
- Exact final head must pass `test-and-build`, mandatory `coworker` including the sandbox regressions, and `ci-merge-gate`; inspect skips and logs. A green upstream PR SHA does not certify this changed worker script.
- Independently review API trust, cancellation/revocation and worker loss. Operated Linux bubblewrap, actual interrupted subprocess and process-group termination remain separate release evidence.
- Stacked PR must be rebased or retargeted onto final reviewed `main` after PR #416 is approved/merged. Do not bypass green CI, review or activation policy.

**Scope:** CW-10 safety only, not generated-model code approval, skills, browser SSRF, production activation, provider provisioning or external mutation.
