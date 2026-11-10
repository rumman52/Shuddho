# C-04 / CW-10 — bounded worker lifetime and truthful cleanup

- Base: main `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`; branch `codex/cw10-sandbox-cleanup-order-20261020`.
- Objective: no completion can attest destruction while private source/scratch files remain; blocking control I/O cannot suspend wall/disk supervision; unexpected supervisor failure must stop the child.
- Reuse: existing `execute_claim`, process-group termination, canonical policy, claim API and cleanup contexts. No policy version, schema, approval, grant or capability-default change.
- Reproduction: five real local subprocess lifecycle cases failed against unchanged code: normal/lost-response completion before deletion, cleanup failure after publication, code running beyond a one-second reviewed wall bound during a two-second control delay, and unexpected control exception leaving the process alive.
- Plan: independent watchdog for wall/disk checks while main thread waits for control; unconditional process cleanup on exit; collect bounded result privately, close output handles and remove source/scratch, then publish. Add mandatory zero-skip lifecycle collection. Run old/new sandbox tests, mandatory collection, syntax, full suite and independent review.
- Files: `scripts/sandbox_worker.py`, `tests/test_sandbox_worker_lifecycle.py`, `.github/workflows/ci.yml`, this contract and canonical progress.
- Acceptance: five regressions green; old stop/continue authorization behavior preserved; actual subprocess killed at short wall bound and on unexpected supervisor failure; no completion during failed cleanup; one bounded completion after successful cleanup, including response loss.
- Evidence boundary: the lifecycle tests replace only namespace launch with a real local Python child. They do not attest real bubblewrap namespace, network/mount isolation, memory zeroization or protected staging. Existing worker policy remains default-off until operated qualification.
- Residual: OS scheduling and process-reap latency apply; watchdog samples every 50 ms. Abrupt host death before successful cleanup requires separate operated cleanup proof. Cleanup errors fail closed without false receipt; runtime should be quarantined by its existing process supervisor on unexpected exceptions.
- External gates: actual bubblewrap UID mapping is unavailable in this host; staging preflight lacks RENDER_API_KEY. Matching deployed identities, real namespace/network cleanup, PostgreSQL/Temporal recovery and human security review remain unverified.

## Completion evidence

Pre-fix: 5 failed; review follow-up watchdog exception: 1 failed before repair. Final related suites: 189 passed, zero skips; 6 existing Pydantic invalid-input serialization warnings. Independent review finding repaired with failing-first coverage; mandatory lifecycle collection and syntax passed. Required final-head CI: pending. Staging/production: unverified. Activated: no.
