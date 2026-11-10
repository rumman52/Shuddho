# Day 1 baseline continuation — 10 November 2026

## Task contract

Make the existing baseline testable and prepare the bounded pilot without representing source work as operated infrastructure. Base main `1f6dae72e1de6f38ec4d9cf60180d856dbecb403`; continue draft [PR #664](https://github.com/rumman52/Shuddho/pull/664), branch `fix/fly-workspace-subject-regression-20261109`, starting head `5816cdbbce340b8bd286ec8ea7ab9a57e3e9e735`. User's Day 1 instructions govern; the remaining ten-day features are outside this patch.

Reuse Settings validation, the existing sandbox command builder, canonical conversation/client, existing recovery/governance scripts and current progress/acceptance ledger. No new application ledger, orchestrator, migration or production authority. Relevant work interfaces: the Fly reservation must remain valid when testing provider capacity; Python-only sandbox mount assertions must not include repository-test Node mounts; evaluator development inputs must not imply independent holdout custody.

## Reproduction and correction

[Previous exact-head CI #42706002584](https://github.com/rumman52/Shuddho/actions/runs/42706002584) failed `coworker` with 2 failed, 1572 passed, 4 skipped. Logs identify precisely the two cases below. Frontend, test-and-build, browser and PostgreSQL 18 jobs passed; merge gate failed and governance was skipped on the PR event.

| Case | RED on starting head | Cause and correction | GREEN |
| --- | --- | --- | --- |
| `test_provider_capacity_settings_fail_closed` | 1 failed; expected `token reserve`, received Fly reservation error | Workspace reserve 2000 was already below Fly's default 8000. Test 8000 global / 16000 workspace instead, so Fly is valid and the intended global/workspace invariant rejects. Production still fails closed. | 1 passed |
| `test_sandbox_worker_command_is_networkless_minimal_and_fail_closed` | 1 failed on `/usr/bin not in command` | The argument creates an empty directory and sets PATH. Enumerate bind operands and require the exact existing read-only interpreter/libs, private writable scratch and read-only source. A host `/usr/bin` or any extra bind now fails. | 1 passed |
| `tests/test_fly_repository_coding.py` | 2 passed | Preserve #664's authenticated subject/foreign-owner 404 correction. | 2 passed |

Requested combined command: `uv run --extra coworker pytest tests/test_coworker.py::test_provider_capacity_settings_fail_closed tests/test_sandbox_control_plane.py::test_sandbox_worker_command_is_networkless_minimal_and_fail_closed tests/test_fly_repository_coding.py -q -rs`: **4 passed, zero skips**. JUnit `/tmp/rukh-day1/focused.xml`; existing mandatory module gates passed for all three modules. This is command-construction evidence, not real bubblewrap namespace qualification.

Ruling: correct invalid test premises; do not change validation order or relax sandbox mounts. Cost if wrong: a missing production isolation defect could be hidden; exact mount checks and required real worker CI remain necessary.

## Bounded model and resource configuration

`infra/render.staging.yaml` previously omitted model identity and provider/run ceilings on both services, relying on mutable source defaults. Pin the existing source policy explicitly on API and worker. No new provider, increased ceiling, automatic fallback, credential value or live deployment is introduced.

| Scope | Pinned policy |
| --- | --- |
| Provider/model | backend DeepSeek, `deepseek-flash` (repository default); `gemma-4-26b-a4b-it` available only through explicit rollback |
| Provider concurrency | 8 total; 2 per workspace |
| Token reservations | 800000 total; 200000 per workspace |
| Daily tokens | 5000000 total; 500000 per workspace |
| Task / Agent tokens | 100000 per task; 250000 aggregate per Agent run |
| Agent calls | 12 model calls; 8 tool calls; 4 v3 planner calls / 24000 planner tokens; planner output 1200 tokens |
| Runtime | Agent 1800 seconds; provider lease 120 seconds; 2 parallel steps; 2 active tasks per workspace |
| Context | 5 selected items; 12288 total bytes (existing per-item limit remains 4096) |
| Cost | existing 1000000 microUSD per-run accounting ceiling; zero external calls in this implementation |
| Model source constants | model timeout 90 seconds; document output 4096 tokens; 2 attempts. These are source Settings constants, not unsupported environment keys. |

Validated both service literal environments by loading `Settings.from_env()` with nonsecret development stand-ins; policy and disabled execution/action gates match. Live model revision, provider quota, actual rate/cost accuracy and spending/retention approval remain unverified. The model name is a provider alias, not an immutable weight revision. The v3 planner's default price estimate is zero; the accounting ceiling alone does not establish a real dollar limit. Token/call/time reservations remain finite; require operator pricing/quota review before paid inference. No claim of a newly approved spend budget.

## Owner/blocker checkpoint

- C / Render owner: user selected workspace Rumman for inspection. Staging DB is suspended for billing after expiry; hosted read-only query blocked by empty external allowlist. No recoverability claim. See [operational evidence and runbook](DAY1_OPERATIONS_2026-11-10.md).
- C / GitHub administrator: `main` unprotected and native ruleset list empty; production API initially auto-deployed `main`; later disabled through the administrator UI and confirmed `autoDeploy=no/off` by Render API. Native ruleset is prepared but saving awaits GitHub account verification. No merge, deployment or native denied/permitted result is claimed.
- B: [canonical UI/client ownership and checks](DAY1_UI_OWNERSHIP_2026-11-10.md). Advertised upload formats exceed client support; per-run independent steering drafts are not established. Map only on Day 1; future UI work must resolve these.
- D: [evaluation contract and calibration](DAY1_EVALUATION_2026-11-10.md). Same-repository fixtures cannot supply independent D-only custody. Held-out qualification must remain blocked until a real transfer/access boundary exists.
- ProductOS has only an unrelated cleaning demo connected; no Rukh writes there. PostHog project 675660 is `Default project`, `ingested_event=false`; no telemetry activated and no live performance claims.

## Verification status

Focused tests and source policy loading pass. Broader suites, evaluator calibration, independent source review and final-head GitHub checks will be appended after they finish. Full initial pytest collection encountered the evaluator test while its module was still being authored; no implementation result is inferred from that transient error. Existing-suite run excludes that in-progress module; the evaluator suite is verified separately after implementation.

Day 1 remains **BLOCKED for operational acceptance** until DB/resource retention, native enforcement, production promotion and D holdout custody are genuinely resolved. Source, repository CI, staging, production qualification and activation are distinct.

## Review and source verification checkpoint

Independent source reviewer examined the baseline changes, evaluator, malformed drafts, source provenance and scope. Two Important findings were verified and fixed: exact false-send/activation strings in artifact headings now fail, and CI's lightweight job fetches history for source-provenance checks. Eight new regression instances first failed (three heading fields with single-line and newline claims plus two oversized metadata files); all then passed. The metadata size finding was regraded from Minor to Important because a custom fixture directory otherwise violated the evaluator's input resource ceiling. Hash and checksum metadata are now bounded before reading.

A depth-one local clone of the evaluator commit could not resolve historical source blob `602f76f...:docs/coworker-roadmap/A02_P01_GOAL_RUN_ADMISSION_REPLAY_2026-10-24.md`; fetching complete history recovered exactly 3265 bytes. This demonstrates why `fetch-depth: 0` is required in the `test-and-build` checkout; no CI job or test gate was removed or weakened.

Verification completed at source candidate `1dc6641e89cecf9f9dc2c44abe02b9f179b18c99`:
- Coworker/sandbox/Fly full modules: **162 passed, zero skips**, 553.55 seconds.
- New evaluator plus existing curated quality evaluator: **39 passed, zero skips**, 1.66 seconds (26 new tests including review regressions).
- Development reference-output calibration: **40/40**, four cells of 10. This measures the evaluator against handcrafted references, not model quality.
- Manifest validation: **80**, 40/40, independent holdout isolation false; scoring holdout exits **2** as required pending actual D custody.
- Frontend shared workspace suite **240 passed**, standalone shell/navigation **7 passed**, zero skips; canonical web-editor build passed.
- Existing administrator/governance test harness **94 passed**; existing backup preflight **9 passed**, zero skips. These are local controlled tests, not live enforcement or restore.
- `git diff --check` passed. Existing full repository pytest is still running; PostgreSQL/Temporal/real-worker/optional-ML requirements may skip locally and must be reported. Exact-head CI is pending and PR remains draft.

Final: Ruling: leave semantic entailment, fluent language and useful artifacts to the explicit human evaluation rubric; lexical scoring is a bounded smoke gate, with `quality_qualified=false`. Cost if wrong: a misleading automated pass could overstate quality; release requires separate human evidence.

Final: Ruling: no real namespace, deployed provider, DB restore, native merge, or D access-exclusion claim is made without operated proof. Cost if wrong: premature release or contaminated holdout results. These are recorded blockers, not silent acceptance.

Final: Ruling: retain source-configured provider/model defaults while pinning finite ceilings; no new spend/resource approval is inferred. Cost if wrong: existing defaults may be inappropriate for the future cohort; activation remains blocked pending operator quota/pricing review.

No deferred reviewer Minor remains: the only Minor finding was regraded and fixed. B's mapped upload/steering integration gaps remain future task work, not fixes to this Day 1 baseline. The independent agent reviewer supplies source review only; no human GitHub approval was submitted on the owner's behalf.

The source-review fix pass also reproduced three newline-claim evasions introduced by scanning JSON-escaped text. Scanning the actual schema-validated string leaves preserves whitespace normalization in every displayed field. Final evaluator/quality result: **39 passed, zero skips**.
