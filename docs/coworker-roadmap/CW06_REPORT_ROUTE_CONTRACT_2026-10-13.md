# CW-06 — Core Agent report route capability contract

- Objective and user-visible behavior: A report request returns the documented public capability `report` while preserving the legacy durable `report_email` task skill.
- Dependency tasks and current evidence: CW-05/06 conversation routing foundations are present on main; CI for main `339d6924b244c0bb1641764dabd68c4f55488bb3` succeeded (run 38338728994). CW-02..04 staging qualification remains separate.
- Base branch/SHA: `main` / `339d6924b244c0bb1641764dabd68c4f55488bb3`.
- Work branch/PR: `codex/cw-core-router-report-contract-20261013` / https://github.com/rumman52/Shuddho/pull/383 (draft).
- Existing interfaces to reuse: `qualify_agent_goal`, `_AGENT_RULES`, and `tool("report.create")` registered `ToolSpec`.
- Exact files changed: `services/coworker/agent_router.py`; `tests/test_core_agent_router.py`.
- Interface signatures / compatibility: No new API, schema, migration, provider, workflow or tool names. `ToolSpec.skill_id="report_email"` continues to govern durable report execution. Public route capability now comes from the server-owned matching route intent for a single selected tool.
- Acceptance: `Create a concise project status report.` => `agent_run`, `report`, `["report.create"]`, non-consequential. Existing direct-question, multilingual, email, research, consequential and multi-tool cases remain unchanged. The pre-existing canonical fixture `tests/fixtures/core_agent_route_cases.jsonl` separately expects `report`.
- Reproduction / initial failure: Main's `agent_router.py` chooses `tool(selected[0]).skill_id` for public capability, but registered `report.create` has `skill_id="report_email"` and `capability="report"`. The fixture's expectation therefore disagrees with code.
- Expected failure outcomes: Unknown or disabled capabilities remain rejected, arbitrary provider/action names remain unregistered, and any regression in neighboring routes fails required routing CI.
- Tests and required CI: `uv run --frozen --extra coworker pytest tests/test_core_agent_router.py -q`; GitHub CI jobs `coworker`, `test-and-build`, and `ci-merge-gate` on the final implementation SHA. No local package runtime was available through the GitHub-only connection; remote exact-head check is required.
- Secrets / owner / grant / approval / egress boundaries: None changed. No generated provider request or ExternalAction mutation introduced.
- Budget / timeout / cancellation / revocation behavior: Not changed; preserve existing limits and fail-closed cases.
- Default-off gate and rollback: This changes reporting only; no capability activation. Revert router line and regression if review finds a compatibility issue.
- External prerequisites: None for code CI; staging/production qualification is distinct and remains pending.
- Out of scope: Browser execution CW-09, reviewed code CW-10, versioned skills CW-11, proactive automation, transaction actions, production deployment.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Yes, review branch | `aeb00b2cdd5994e3e8236bc049d2f916f9ad7862` initial code and test head; see PR #383 for final head |
| Repository-verified | Pending final-head CI | https://github.com/rumman52/Shuddho/pull/383/checks |
| Staging-verified | Not established | Not exercised |
| Production-qualified | Not established | Not exercised |
| Activated | No | Existing activation policy unchanged |

- Test pass/fail/skip counts: Not run locally; pending exact-head CI.
- Review: Self-review of code-owned intent mapping, no independent reviewer yet.
- Residual risks: Verify consumers of public route capability and exact-head integration/quality tests; do not mistake green predecessor CI for feature verification.
- Next exact action: Inspect PR #383 final-head required CI, review code diff and fixtures; correct any failure without suppressing tests, then obtain independent review before merge.
