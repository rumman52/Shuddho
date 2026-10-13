# CW-09 — Brokered read-only page-metadata tool (bounded implementation slice)

## Outcome and baseline
- **Workstream:** Architecture/Core Agent, CW-09.
- **Repository/default branch at bootstrap:** `rumman52/Shuddho` `main` `f5c11ec7db35721190b67212695e7612af63f09f`.
- **Previous evidence:** CW-08 explicit context [PR #386](https://github.com/rumman52/Shuddho/pull/386) merged; exact final-head [CI 38404758754](https://github.com/rumman52/Shuddho/actions/runs/38404758754) succeeded. Main CI 38408371736 was in progress when inspected. No open PR was returned at bootstrap.
- **Branch:** `codex/cw09-brokered-read-metadata-20261013` (draft PR pending).
- **Defect:** The existing supervised browser broker, DNS/SSRF policy and isolated worker are separately built, but `browser.read` is absent from the typed Agent tool registry and Runtime v3 dispatch, so the planner cannot consume authorized browser observations.

## Design, authority and scope
Introduce a **default-off metadata-only** `browser.read` tool. This is the first bounded integration slice, not a claim that all web-page content or a general browser agent is implemented. The only accepted destination is exactly one HTTPS URL explicitly written in the user's owned goal; the model provides only a tool selection/objective and **cannot supply URL, session ID, arbitrary scripts, clicks, forms, CDP, provider credentials or submission permissions**.

Reuse code-owned tool registration, validated goal URL, AgentRun/ToolInvocation/ToolReceipt and existing BrowserSession/BrowserCommand ledgers, broker worker, DNS/IP and redirect/port/HTTPS checks. New `SHUDDHO_AGENT_BROWSER_READ_ENABLED` must explicitly be true alongside the already configured supervised browser and Runtime v3/intelligent planner. It defaults false, separate from the existing browser UI flag. No migration or orchestration engine. Runtime makes `BrowserSession(purpose=research)` under reserved `agent:<run_id>:<ordinal>` identity, then atomically reuses or prepares **one navigate command**. Existing worker remains the sole page/network executor. A duplicate worker attempt or crash after session creation cannot enqueue two commands; owner mismatch and changed target fail closed.

Once the trusted broker marks navigation succeeded, Runtime verifies no submission, title and final HTTPS destination, and records the bounded `browser_command` receipt: `source_url`, `capture_time`, metadata `source_sha256`, `untrusted_page_title`, explicit `observation_scope=metadata_only`, `observation_trust=untrusted`, `submission_performed=false`. The SHA is **of the canonical URL+title pair, not HTML or screenshot content**. The model receives at most that untrusted metadata through already-filtered verified observations. It cannot widen tool grants. No claim that worker captured article text.

## Reviewable affected paths
- `services/coworker/config.py`: default-off independent flag and dependency validation.
- `services/coworker/agent_schemas.py`, `agent_tools.py`, `agent_planner.py`: typed input, registry and safe goal URL selector.
- `services/coworker/agent_repository.py`: server-derived v3 step arguments and bounded receipt propagation.
- `services/coworker/browser.py`: reserved session namespace and locked idempotent read command.
- `services/coworker/agent_runtime.py`: bounded prepare/observe/verify/receipt path.
- `apps/web-editor/src/coworker/client.ts`: tool-kind contract.
- `tests/test_agent_browser_tool.py`: flag, SSRF URL exclusions, owner scope, command replay, broker validation, untrusted observation and kill switch.

## Acceptance and failure outcomes
1. Tool absent by default; enabling without browser/v3/intelligent planner invalid; disabled after admission denies execution.
2. Missing/multiple/localhost/private-IP/metadata endpoint/nonstandard-port URLs do not enter planner tool surface.
3. Agent goal with one HTTPS URL may select read-only `browser.read`. A replay retrieves the same owned session and *same single* command.
4. Owner mismatch and a request to navigate a different URL fail; a public caller cannot allocate the reserved `agent:` idempotency namespace.
5. Broker enforces worker claims, DNS public-address evidence, same-origin redirects and no form submission; command success is required for a persisted observation.
6. The resulting receipt contains metadata-only untrusted source URL/title/time/hash; no submission or action permission. Subsequent replay cannot repeat the command.
7. Existing deterministic v1/v2 planning and the standalone human browser API remain compatible.

**Verification commands:** `uv run --extra coworker pytest tests/test_agent_browser_tool.py tests/test_browser_broker.py tests/test_coworker_temporal.py -q -rs`, `node --test scripts/browser_worker_policy.test.mjs`, required exact-head `test-and-build`, `coworker`, `ci-merge-gate`. This connector does not include an executable full checkout; GitHub CI is the required repository evidence.

## Security limitations, external dependencies and rollback
This slice does not yet provide page-body extraction/hash, full content-source provenance, a captured snapshot in private object storage, or staging-proven direct egress bypass resistance. Existing broker tests use synthetic worker observations; a genuine isolated browser worker and fail-closed network boundary need operated staging with a frozen release identity. An independent security reviewer and the canonical release eligibility evidence are required before considering activation. Do not infer production readiness from CI. The tool must stay **default-off** until those gates pass.

No new ExternalAction, payment, form submission, general page script, browser takeover authorization, secrets export, host mount, container socket or credential broker route is granted. A user-facing browser read is not a model-approved transaction.

**Rollback:** Set `SHUDDHO_AGENT_BROWSER_READ_ENABLED=false`; no previous browser sessions/ordinary Agent histories are rewritten. Revert typed registration/runtime bridge if a compatibility issue is found. Existing BrowserSession records remain governed by their own expiry/retention rules.

## Evidence checkpoint
| Level | Current |
| --- | --- |
| Implemented | Review branch, implementation code and synthetic broker regressions |
| Repository-verified | Pending exact-final-head GitHub CI |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No; separate flag default-off |

**Next exact action:** Open draft PR; fix any final-head mandatory CI failures without muting tests, obtain independent security review, run real network-isolated worker and SSRF/redirect/host-policy tests in staging, then extend to bounded captured page content and private source hash before claiming CW-09 full acceptance. Maintain separate CW-10/11 task branches.
