# CW-09 — Final Agent browser receipt authorization check (14 October 2026)

## Objective
A successful broker command is only a prior observation. If autonomous `browser.read` is disabled between broker completion and `AgentRepository.finish_invocation`, the final Agent transaction must not mint a new verified tool receipt. This closes a separate trust boundary from the previous worker kill-switch fix (#398).

## Baseline and code contract
- Base: `main` `ddc81711c8ccb4475d3a0053b26b5955a5be35b1` (PR #398 already merged).
- Branch: `codex/cw09-final-receipt-revocation-20261014`.
- Implementation: `services/coworker/agent_repository.py` / `finish_invocation`; uses the **existing** `settings.agent_browser_read_enabled`, no new authority or ledger.
- Regression: `tests/test_agent_browser_tool.py` / `test_agent_browser_kill_switch_after_success_denies_final_verified_receipt`.

## Proven source gap before the change
`AgentRuntime.execute_step` and `BrowserRepository` checked the feature switch at earlier stages. `AgentRepository.finish_invocation`, the final owned receipt commit, verified the bound session and succeeded command but did not recheck the Agent-specific switch. A command completed before a rollback could therefore still become a newly minted verified observation through this public repository method after the rollback.

## Expected behavior and safety
- For `resource_type == "browser_command"` when the feature is disabled, deny with `browser_agent_read_disabled` (409) before the inserted tool receipt is committed.
- The test completes a real broker command, toggles the AgentRepository switch and directly calls `finish_invocation`, then checks the error and absence of a persisted verified observation. It does not depend only on the planner guard.
- Existing supervised browser sessions remain governed by `browser_enabled`; no change to their result storage or grants.
- Existing owned session/command checking and cancellation precedence remain intact.
- Previously **already-committed** verified results are historical observations and are not retroactively destroyed by this patch.
- A request already on the network before revocation cannot be recalled; operated worker/process staging checks remain required.
- No new credentials, egress paths, providers, migrations or production flags. Rollback is an isolated PR revert.

## Verification contract
Inspect PR-head `test-and-build`, `coworker` (mandatory browser/PostgreSQL checks without skips), `ci-merge-gate`, and independent review. The test's actual prior failure is reasoned from the unguarded source; no executable pre-fix test invocation is claimed. Report exact-head CI results honestly.

## Completion levels
| Level | State |
| --- | --- |
| Implemented | Source + regression on isolated branch |
| Repository-verified | Pending exact-final-head CI and review |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No (read-only feature remains default off) |

## Next exact action
Review CI, fix any implementation or test defects, and seek independent authority-boundary review. Keep the PR unmerged under this prompt. Once the slice is accepted, continue CW-09 private bounded page-content provenance and canonical execution-time release attestation in separate PRs.
