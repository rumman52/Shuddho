# 20 November 2026 — Recover red main CI without weakening release controls

## Evidence and scope
Pinned base: `8abb5972e6b03e86bc891d736eb2854b63c53b61`; main CI [#44598107021](https://github.com/rumman52/Shuddho/actions/runs/44598107021).

1. The Day 2 synthetic owner-B artifact gate rejected before private writes; the test matched the wrong capitalization. Fix the asserted phrase, not the isolation logic.
2. The Day 7 one-notification success fixture omitted the existing `_enable_briefings` helper (runtime v3, bounded context, intelligent planner, work services). Apply it only to that test, not the default-disabled runtime. The new test also caught an incomplete Day 7 source contract: successful briefing completions were not bound to their unique occurrence ID. Add that binding only for briefing; non-briefing profiles keep their separate start/completion notices. Add a legacy start-notice negative test.
3. `_day8_cases` returns first-run records, reruns, and attempt-provenance status. The Day 8 evaluator treated this triple as a dictionary, causing 27 red cases. Unpack the contract; include all attempts in cost, retry, failure and provider-usage accounting while retaining 40 distinct first runs as quality/latency denominator. Reject missing/invalid attempt provenance; verify reuse/cost attack cases with synthetic tests.
4. Re-run focused, mandatory Coworker and core tests on the exact PR SHA, retain red/green receipts and avoid skips.
5. Update progress and route to an independent reviewer. Do not merge while the main ruleset remains underprotected.

## Explicit out-of-scope
No new app credentials, broad permissions, hosted provider calls, telemetry ingestion, migrations, production deployment, paid provisioning, external sends or pilot membership. The incomplete governance audit must fail closed until administrator/C restore identity and independently test enforced native review controls.

## Verification
```bash
uv run --locked --extra coworker pytest -q \
  tests/test_core_agent_observability.py \
  tests/test_staging_day2_execution.py \
  tests/test_automations.py
```
Additionally require the repository's exact-head `test-and-build`, `coworker`, browser, frontend, PostgreSQL 18, `governance-audit` (on protected main), and `ci-merge-gate` checks. A successful focused test does not qualify the Day 8 operated experiment or any release gate.
