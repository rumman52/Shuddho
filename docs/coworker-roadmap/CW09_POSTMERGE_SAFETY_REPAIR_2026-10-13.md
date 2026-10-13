# CW-09 post-merge safety repair — 13 October 2026

- **Objective:** Restore valid explicit multilingual/browser-question routing and make Agent browser navigation cleanup, cancellation, and invalid worker evidence fail closed.
- **Dependency and initial evidence:** CW-09 PR [#387](https://github.com/rumman52/Shuddho/pull/387) was merged into `main` at `8de8aa9bb672f0b77ddb250e3718bc3ae060dfbd` despite failing exact-head [PR CI 38412412901](https://github.com/rumman52/Shuddho/actions/runs/38412412901) and [main CI 38414646497](https://github.com/rumman52/Shuddho/actions/runs/38414646497). `test-and-build` passed, `coworker` failed at required `tests/test_agent_browser_tool.py` (1 failed, 8 passed; the public route returned `unsupported` for an explicit browser read), and `ci-merge-gate` failed. All five automated [review findings](https://github.com/rumman52/Shuddho/pull/387) were unresolved at bootstrap.
- **Base:** `main` `8de8aa9bb672f0b77ddb250e3718bc3ae060dfbd`.
- **Work branch:** `codex/cw09-postmerge-safety-repair-20261013`; draft PR to be created.
- **Existing authority:** Runtime v3 owned AgentRun/AgentStep/ToolInvocation/ToolReceipt + BrowserRepository sessions/commands; no new ledger/migration/worker.
- **Touched paths:** `services/coworker/agent_router.py`, `agent_repository.py`, `agent_runtime.py`, `browser.py`, `tests/test_agent_browser_tool.py`, progress.
- **Route repair:** Explicit single safe HTTPS browser read must be routed **after** consequential transaction/action precedence but **before** generic direct-question and phrase-rule selection. English/Bangla/Spanish/Arabic bounded read intent; destination is extracted from the original goal, not model output. Browser flag remains off by default.
- **Cancellation/cleanup:** In the same PostgreSQL transaction as Agent cancellation, cancel the owned single-use browser session and all prepared/running commands; clear session state and worker leases. Recheck run cancellation under row lock when linking a session; if cancel wins before link, clean its reserved session. On run failure, clean owned active sessions. On verified broker receipt, atomically close the session so bounded slots are released, without losing the receipt.
- **Interaction violation:** A worker report of an Agent read click/field prep/submission/takeover frame must irreversibly fail the command/session **in a committed transaction before responding 409**; the same worker cannot submit a clean rewritten observation. The ordinary human-browser broker remains unchanged.
- **Acceptance scenarios:** Original failing explicit browser routing case; question-form and Bangla (plus Spanish/Arabic) routing; cancelled run leaves no runnable command and rejects late completion; completed read frees browser capacity; forbidden interaction leaves terminal failed command and clean replay fails; existing broker SSRF/redirect and Temporal/Agent tests remain green; mandatory new CW-09 tests run with **no skips**.
- **Failure semantics:** Revoked/cancelled run is terminal, cannot publish a late ToolReceipt; malformed/hostile worker observations never widen authority; external provider changes forbidden.
- **Verification:** `uv run --extra coworker pytest tests/test_agent_browser_tool.py tests/test_browser_broker.py tests/test_coworker_temporal.py -q -rs`, `node --test scripts/browser_worker_policy.test.mjs`, and exact-head GitHub `test-and-build`, `coworker` (including mandatory browser gate), `ci-merge-gate`. No local full checkout/operated staging supplied.
- **Scope/security:** Keep independent `SHUDDHO_AGENT_BROWSER_READ_ENABLED` **default off**. No form click, JS execution, outbound transaction, credential access or production release. A metadata hash remains **not** a page-content hash. Owner/session controls and worker egress checks remain required; real network bypass/staging and page-body capture are still open CW-09 gates.
- **Rollback:** Turn off independent Agent browser flag; revert bounded source changes if necessary. No database schema change. Do not auto-merge.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | On review branch; code+regressions | Code SHA before this document: `4a3698db81c00a65c3865f5b93567e23aceb7f34` |
| Repository-verified | Pending exact-final-head checks | Latest PR head must be refreshed |
| Staging-verified | Unverified | No frozen isolated worker run |
| Production-qualified | Not established | No reviewer-approved release gates |
| Activated | No change; default off | No deployment/flag changes |

- **Independent review:** PR #387 automated findings reproduced and addressed in this review branch; independent review of the new patch not yet established.
- **Remaining hazards:** Full captured webpage content, metadata-only provenance, default-off canonical release eligibility and operated egress bypass qualification; transaction/cancellation races require PostgreSQL CI and staging.
- **Next exact action:** Open a draft PR; inspect mandatory exact-head tests and resolve every failure without weakening checks. Obtain independent review and staging worker qualification before CW-09 is promoted; continue independent CW-10/CW-11 separately after evidence checkpoint.
