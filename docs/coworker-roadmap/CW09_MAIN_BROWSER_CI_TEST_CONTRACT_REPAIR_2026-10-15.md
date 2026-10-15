# CW-09 mandatory browser CI safety-contract regression repair — 15 October 2026

- **Objective and user-visible behavior:** Keep autonomous browser evidence trustworthy: rejected private-network DNS evidence terminally fails an Agent read and cannot be replaced by a forged clean receipt; normal, separately authorized reads still complete. A true lone-surrogate storage payload is rejected and cannot be rewritten.
- **Dependency tasks/current evidence:** Merged PR #400 changed Agent browser post-validation failures to committed terminal rejection. Main `a305652a0be05b6d6a3768afbe6a14a029bd91c8` [CI run 38612375324](https://github.com/rumman52/Shuddho/actions/runs/38612375324) had `test-and-build=success`, `coworker=failure` (Agent browser: **2 failed, 33 passed**), `ci-merge-gate=failure`.
- **Base:** `main` `a305652a0be05b6d6a3768afbe6a14a029bd91c8`.
- **Work branch:** `codex/cw09-browser-ci-regression-repair-20261015`. Initial focused correction commit: `fe989fffb46116d4c24d46d9b521b19c4f749a07`.
- **Interfaces:** `tests/test_agent_browser_tool.py`; current browser broker `BrowserRepository.complete_command`, `_bounded_observation` and `_bounded_storage_state` are **unchanged**.
- **Compatibility:** Test-only correction; no data migration, new API, secret, environment flag or production authority.
- **Regression 1:** Prior positive Runtime v3 browser route reused a command after receiving disallowed `127.0.0.1` DNS evidence. After #400 that rejection is *intentionally terminal*, so the old positive fixture was invalid. Put negative DNS proof on a separate Agent command and assert failed session, cancelled flag, failed command, immutable receipt on resubmission. Positive end-to-end Runtime v3 route retains its authorized good-DNS completion checks.
- **Regression 2:** Invalid-storage fixture contained literal backslash-u text (`"\\\\ud800"` in Python source), not a lone UTF-16 surrogate. Pass `chr(0xD800)` to trigger the actual `UnicodeEncodeError` branch; assert typed `browser_storage_state_invalid`, committed failure, no later rewrite.
- **Expected failures:** Disallowed DNS => `browser_network_blocked` then a failed/terminal Agent read. Invalid surrogate storage => `browser_storage_state_invalid`, failed/terminal read. A clean verified read on a fresh command succeeds.
- **Acceptance:** Mandatory `uv run --extra coworker pytest tests/test_agent_browser_tool.py -q -rs --junitxml=/tmp/cw09-agent-browser.xml` with zero required skips; mandatory gate; exact-final-head `test-and-build`, `coworker`, `ci-merge-gate`; security second-pass/independent review.
- **Boundaries:** No weakening of DNS/SSRF protection, no grant expansion, no replay of invalid receipts, no automatic production activation. CW-09 private page text/digest, isolated egress, runtime release eligibility and staging remain separate.
- **Default-off/rollback:** Agent browser remains default-off; no feature-switch changes. Revert this test-only patch if review identifies mismatched contractual expectations.
- **External prerequisites:** CI PostgreSQL, Temporal test process and sandbox worker image; staging environment and independent reviewer unavailable in this session.

## Current completion evidence

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Test changes committed on isolated branch | `fe989fff` and subsequent documentation commits |
| Repository verified | Pending exact-final-head CI | No success claimed before required jobs pass |
| Staging verified | No | No operated staging test |
| Production qualified | No | No operated qualification |
| Activated | No | Default-off |

**Next action:** Verify exact PR head against mandatory browser suite and remaining CI, inspect any failures, correct without weakening assertions, and solicit independent security review. Complete CW-09 substantive page-text/egress work in a later slice.
