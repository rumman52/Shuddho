## Current release-readiness handoff — 25 October 2026 (Asia/Dhaka; refreshed after PR #568)

- **Current main:** `79d4e59a69350b3af9d7404102e285fd606fb04d`, merge of [PR #568](https://github.com/rumman52/Shuddho/pull/568), “fix(pa10): make deadline occurrences replay-safe after admission failure.” PR head: `3778511b9fb1e6415820280ff27cb5bf94a64ffd`. [Issue #566](https://github.com/rumman52/Shuddho/issues/566) is closed; the deadline-recovery source slice is merged.
- **Exact PR-head code evidence:** [run #40192139821](https://github.com/rumman52/Shuddho/actions/runs/40192139821) completed `test-and-build=success` and `coworker=success`; the full “Test accounts, real exports, PostgreSQL races, and Temporal recovery” step passed with no reported failure. The same run’s `ci-merge-gate` failed at “Require independent current-head review.” The submitted-review list for #568 is empty. Green code jobs do not establish the missing independent review or pre-merge enforcement.
- **Merge timing and post-merge checks:** PR #568 merged at **16:08:07 UTC** while exact-head run [#40210212873](https://github.com/rumman52/Shuddho/actions/runs/40210212873) was still running. That run subsequently completed `test-and-build=success` and `coworker=success` at **16:26:30 UTC**, then `ci-merge-gate=failure` at **16:26:40 UTC** because independent current-head review was missing. These later results confirm code-test completion after merge; they do not establish pre-merge review or enforcement.
- **Merged-main CI:** [run #40210229328](https://github.com/rumman52/Shuddho/actions/runs/40210229328) has `test-and-build=success`, `governance-audit=failure` (“main branch protection is not confirmed”), and `coworker=in_progress` at the full PostgreSQL/Temporal integration step as of this refresh. Recheck this exact main SHA before reporting the final coworker result. The source tests passing on the prior PR-head run do not turn the main governance failure green.
- **V-01 native governance:** the main governance audit fails closed. The connected rulesets read returned an empty list, and direct branch-protection inspection returned 403 to the integration; these connector observations alone do not rule out every inherited policy, but effective enforcement is **UNVERIFIED**. [Issue #484](https://github.com/rumman52/Shuddho/issues/484) now records the PR #568 merge-before-review incident and the post-merge evidence. An authorized repository administrator must apply/read back the existing ruleset policy and prove unsafe merges are blocked and a reviewed green PR is eligible. Do not weaken the audit or rebuild the operator.
- **Production deployment:** Render automatically deployed main commit `79d4e59a69350b3af9d7404102e285fd606fb04d` to [`shuddho-api`](https://dashboard.render.com/web/srv-d6oki2v5r7bs73e7isfg), deploy [`dep-dbf2iqdg1s2s739ss2j0`](https://dashboard.render.com/web/srv-d6oki2v5r7bs73e7isfg), which Render reports **LIVE** after successful build/deploy. The service remains `autoDeploy=yes`, `autoDeployTrigger=commit`; no setting was changed here. No error or 500/502/503 logs were returned in the inspected post-deploy window, but HTTP request/latency metrics were empty and no HTTP health-check path is configured. Endpoint correctness and user-facing health are **not verified**.
- **Controlled staging:** Render lists only `shuddho-api-staging` (`srv-dav98otg1s2s73cod4gg`) and no `shuddho-worker-staging`. The API remains on deploy `dep-davmrnu7bikc73emahdg`, source `fce72760456bd8bb03524ce98127120c7ac3dfb9` from 2 October, with the older build/start configuration and no HTTP health-check path. Render's `shuddho-staging-db` is available but on a free plan expiring **31 October 2026**. The linked Supabase `shuddho-staging` project (`bsmbvjenpvcyfjzwtuax`) now reports **INACTIVE**. Temporal/S3 credentials, managed synthetic identity and real Google/Microsoft/browser-push prerequisites remain operator-only blockers. [Issue #291](https://github.com/rumman52/Shuddho/issues/291) records the fresh inventory. Do not create a cron/web-service substitute for the persistent worker or expose secrets in GitHub/chat.
- **Vercel frontend evidence:** the connected account exposes `shuddho-web-editor` with a latest-deployment summary `READY`, but the project summary reports `live=false`; deployment-detail and runtime-error reads returned 404/403. The frontend's exact deployed SHA and runtime health therefore remain **unverified**.
- **Next actions, in dependency order:** (1) authorized GitHub admin applies and behaviorally proves native main protection; (2) authorized Render owner configures and verifies a fail-closed production deployment policy instead of deploying every commit; (3) staging operator restores/validates the inactive Supabase project if appropriate, securely completes credentials, syncs the reviewed Blueprint and provisions the approved persistent worker; (4) align API/worker source and health settings, freeze one exact staging revision, and run the PA-10 scenario/economics/quality evidence collection. Continue independent source work, but do not call Shuddho production-qualified or activate expanded coworker capabilities while these gates remain open.

### Current evidence levels

| Gate | Current state | What closes it |
| --- | --- | --- |
| PA-10 deadline occurrence recovery | **IMPLEMENTED AND MERGED; PR-head code jobs passed** | Confirm merged-main coworker completion; retain review/merge-governance incident separately |
| V-01 native merge enforcement | **BLOCKED_EXTERNAL / UNVERIFIED** | Admin-applied effective policy plus negative/positive merge-control evidence |
| Current-main CI | **PARTIALLY VERIFIED** | Exact-main coworker job must complete; governance audit must pass |
| PR #568 review/CI timing | **MERGED WITHOUT RECORDED SUBMITTED REVIEW; latest exact-head code jobs completed after merge** | Record as a governance incident; later green checks do not retroactively establish pre-merge review |
| Production auto-deploy control | **BLOCKED_EXTERNAL / UNVERIFIED** | Owner-authorized fail-closed deployment policy and failed-candidate deployment proof |
| Production API health | **DEPLOY LIVE; END-TO-END HEALTH UNVERIFIED** | Configured readiness check plus real endpoint/runtime evidence |
| Controlled staging | **BLOCKED_EXTERNAL** | Active Supabase project, persistent worker, required credentials/provider prerequisites, matching API/worker identity and frozen evidence |
| Frontend/Vercel | **DEPLOYMENT SUMMARY ONLY; SHA/HEALTH UNVERIFIED** | Authorized deployment details/runtime evidence |
| A/C/P/V acceptance | **NOT FULLY QUALIFIED** | Row-by-row repository, staging and operational evidence |
| Production activation | **NOT AUTHORIZED / NOT ESTABLISHED** | Explicit scope authorization after all relevant qualification gates pass |

---

## Historical checkpoint — P-01 connected read-context grant recovery — 24 October 2026 (superseded 25 October)

- **Current base:** main `c3472f76ca2725fd8928abd59cdce57dc524422e`, merge of #560; repository main has no enforced native required checks/review ruleset at source selection (V-01 issue #484).
- **Historical state at publication:** `fix/p01-connected-grant-admission-recovery-20261024` / [PR #561](https://github.com/rumman52/Shuddho/pull/561) was unmerged at that time. PR #561 subsequently merged into main on 24 October; do not resume or recreate that branch. See the current release-blocker checkpoint above.
- **P-01/C-01 scoped defect:** Agent UI loses a confirmed connector read-grant if first sync fails, and an accepted-but-lost grant creation response is retried with a fresh key *and* expiry. The patch retains the exact pending identity per connection, blocks same-tick duplicate grant admissions, displays/selects confirmed grants before first sync, and preserves manual Sync/revocation.
- **Test-first regression coverage:** four new React tests in `connectorGrantAdmission.test.tsx`, included in the shared web test registry. Tests-before-fix commits `f58c078b` and `4b49bbd`; source fix `29fc7ff9`; [contract](P01_CONNECTOR_READ_GRANT_ADMISSION_RECOVERY_2026-10-24.md). Test-only CI was cancelled by subsequent branch pushes before Node tests completed; no observed red run is claimed.
- **Verification level:** implementation exists in a draft branch; exact final-head `test-and-build`, `coworker` and `ci-merge-gate` must be observed and independent review obtained. Staging, production qualification and activation remain **not established**. Owner-only native merge controls and external staging/provider prerequisites remain separately open.
- **Historical next action at publication:** inspect PR #561 final-head CI and review before merge. This is superseded by the confirmed merge; current work is the V-01 native-policy and staging blockers recorded at the top of this file.

---

## A-02 / P-01 goal-run admission replay — 24 October 2026

- Baseline `main` `d1621e5e320bce44ce4e5f5c3c773df39412fdc1`, merged #558. PR #559 is now merged into main; it covers Agent-form identity, not this goal-run path.
- Defect: `GoalWorkspace.runNow()` minted a fresh random key on every click, so an admitted-but-lost HTTP response could create a second durable Agent run on retry. The UI now binds retry to owner-visible goal ID/revision/language, changes identity when target changes, rotates only upon confirmed admission (before refresh), and blocks reentrant in-flight calls.
- Four integrated React tests exercise exact same-key uncertain replay, two legitimate starts, different goal after uncertain response, and confirmed run with failed follow-up refresh. Test module and runner registration preceded source fix; no observed RED execution claimed.
- [Bounded task contract](A02_P01_GOAL_RUN_ADMISSION_REPLAY_2026-10-24.md). Implementation on independent review branch; final-head web tests/build, full required CI and human review **pending at publication**. No staging duplicate-effect witness, PostgreSQL/Temporal operated recovery, native main protection, production qualification or activation established. Retain all 17 A/C/P/V requirements as not fully qualified.

---

## P-01 / C-01 Agent submission identity — 24 October 2026

- Base main `a14dee4870af05954936b88882e40f6db2374aab`. New dedicated review branch `fix/p01-agent-run-submission-identity-20261024`; earlier draft #558 is independent and remains unmerged.
- Concrete defect: after successful bounded-Agent admission the form retained its idempotency key, so an explicit identical run request returned the existing run. The fix rotates the key **only after confirmed success**, preserving same-key recovery following a lost response and changed-payload rebinding. The submit guard also rejects in-flight/disabled/invalid synthetic submissions before changing identity.
- Regression coverage: [`agentSubmissionIdentity.test.tsx`](../../apps/web-editor/src/coworker/agentSubmissionIdentity.test.tsx) exercises repeated accepted goals, accepted-but-lost response replay/fresh next click, and edited uncertain input; registered with the existing web test runner. Tests committed first, but no observed failing-first run is claimed.
- [Task contract](P01_AGENT_SUBMISSION_IDENTITY_2026-10-24.md). Implementation on review branch; exact-head web tests/build and required repository CI pending, independent review pending. No claim of staging qualification, production readiness, or activation. Native V-01 main protection remains blocked on administrator action. All 17 A/C/P/V formal acceptance requirements remain not fully qualified.

---

## V-01 required governance aggregate — 24 October 2026 (Asia/Dhaka)

- Base main: `ddb58a308b9cd28de791c911bc1338f12d7bed5c`; no open PRs at selection. Main [CI #39954055394](https://github.com/rumman52/Shuddho/actions/runs/39954055394) passed code/coworker and aggregate jobs while governance failed; native main protection was false and rulesets empty.
- Branch: `fix/v01-required-governance-gate-20261024`. The aggregate job now waits for governance and rejects failed/cancelled/skipped/missing audit results on main push. PR/review events retain the intentional read-only audit skip and independent-current-head review. Unsupported events and unexpected audit failures are denied. No elevated PR permissions.
- Added an unapplied native ruleset payload and administrator verification runbook, plus a complete Code Editor implementation/verification prompt. [Task and operator runbook](V01_REQUIRED_GOVERNANCE_GATE_2026-10-24.md); [Codex prompt](CODEX_COMPLETION_PROMPT.md).
- Test-first: **15 failures, 38 passes** before the workflow/configuration change. Focused governance/review/redirect suite: **149 passed, zero skips**. Full lightweight Python suite: **1,529 passed, 71 skipped, 6 warnings**; the skipped optional integration coverage is not claimed as verified. Release-contract checker passed. `git diff --check` passed.
- Independent AI review of the code/configuration/handoff found no Critical, Important or Minor findings and independently reran the focused suite: **149 passed, zero skips**. This is not human approval or live governance evidence.
- Native protection is **not applied** by these files. The read-only token may lack visibility of ruleset bypass actors even after configuration; missing visibility remains a failure, not proof of no bypass. A trusted administrator evidence path and real negative/positive merge controls remain required.
- Levels: implemented on review branch; exact-final-head remote CI and independent human approval pending; staging/production/activation not established. All 17 acceptance rows retain their outstanding qualification gates. No provider transaction, deployment, paid provisioning, flag change or merge performed.
- Next: inspect the final PR-head code/integration jobs and review; apply and verify the concrete native policy through authorized admin tooling; refresh staging prerequisites (#291), then close evidence gaps rather than reimplementing existing Runtime v3/browser/code/skill foundations.

---

## CW-09 CONNECT handshake deadline — 21 October 2026 (Asia/Dhaka)

- Refreshed baseline: main `94fd180e895c3fd90e760874ac8ff83cf11c1e78` after PR #526. PR #527 private-IP defense is a separate open change; its exact-head `test-and-build` succeeded and `coworker` was still running at task selection. Do not infer complete CI or human review from this partial state.
- Bounded source defect: the real HTTPS CONNECT boundary awaited broker authorization without a timeout, then started a fresh upstream inactivity timeout. Slow authorization plus slow TCP setup could exceed the intended navigation budget.
- Branch `fix/cw09-connect-handshake-deadline-20261021`; draft [PR #528](https://github.com/rumman52/Shuddho/pull/528); [task contract](CW09_CONNECT_HANDSHAKE_DEADLINE_2026-10-21.md). Local test-only commit `43831763912852a22a55bb6b07d661bb8f423891` produced 2 intended deadline assertion failures, 22 passes and zero skips against unchanged production source. Local source commit `7edb613a1835a3ee11b644cb9033355816d13a33` adds one shared handshake deadline, paired socket teardown and safe late-result rejection; established active tunnels retain the existing idle timeout.
- Review found an elapsed-deadline race before timer callbacks execute. Test-only `7189e57` reproduced both late-authorization and late-TCP readiness failures; correction `24d59057637984a97e522a4cecb652cc550d58b3` adds monotonic expiry checks before both side-effect boundaries. Final local Node policy/proxy suite: **26 passed, zero failures/skips**; source syntax check passed. Fresh agent re-review confirmed the original real TCP and authorization reproductions now reject, with no remaining Critical/Important finding. This is not human approval.
- `npm test` passed all configured workspaces (including 120 editor tests); full workspace build passed. Backend browser/broker tests: **117 passed, zero skips**. All **26** proxy/policy tests also passed on Node 20, matching CI's major version. The full Python suite remains in progress and is not claimed as passed.
- GitHub account/owner verification resolved the initial publication rejection; PR #528 was published through the connected integration after the shell lacked credentials. Initial remote head `e217a281dee5fb5865ba56496c70b4da19790097` exactly matched reviewed local tree `c3c630b9cffe563fd03039d3d11ac4c92cdd7d8e`. Its [CI #39543526174](https://github.com/rumman52/Shuddho/actions/runs/39543526174) passed `test-and-build`; `coworker` was still running at refresh. This final documentation checkpoint requires fresh exact-head CI; inspect PR #528's latest revision rather than qualifying it with an earlier run. Local TCP tests do not establish operated Chromium/DNS-rebinding or isolated staging evidence.
- Existing #527 exact-head [CI #39540792404](https://github.com/rumman52/Shuddho/actions/runs/39540792404) completed: code jobs `test-and-build` and `coworker` passed; `ci-merge-gate` failed for missing independent current-head approval. Do not merge based on code-job success.
- Levels: implemented **yes, review branch**; full repository-verified **pending**; staging-verified **not established**; production-qualified **no**; activated **no**. V-01 native protection #484 and staging #291 remain open. No schema, credentials, permissions, deployment, provider calls or paid resources change.
- Next: resolve any review findings, inspect all required checks on the final documentation-inclusive PR head, and obtain independent human review. Keep draft/unmerged until those external gates are satisfied.

---

## CW-09 — worker-side browser private DNS fence (21 October 2026, Asia/Dhaka)

- Baseline main `0c4b8a7d049aad4ff4657a5f101af55d05c792b5`. Separate [draft PR #526](https://github.com/rumman52/Shuddho/pull/526) is still open/unmerged: its test-and-build and coworker succeeded but ci-merge-gate failed. V-01 governance [#484](https://github.com/rumman52/Shuddho/issues/484) remains BLOCKED; no native protection was configured.
- Chosen **independent CW-09 source-level defect:** after broker DNS network-check, the real HTTPS CONNECT worker in `scripts/browser_pinned_proxy.mjs` enforced valid IP *syntax* but not public routability. A syntactically valid `127.0.0.1` returned from an erroneous broker response could reach TCP dialing.
- Draft [PR #527](https://github.com/rumman52/Shuddho/pull/527). Test-only SHA `4431e5fa0d7136114353c075d2f7d12d6ed867b9` extends the actual real TCP proxy harness with 14 private/mapped/mixed-address DNS regressions. [Test-only workflow #39539992177](https://github.com/rumman52/Shuddho/actions/runs/39539992177) cancelled before coworker reached proxy tests; do **not** count that as a full observed red integration run. Local copied original predicate independently returned `true` for loopback and failed the intended rejection assertion.
- Source fix SHA `1d4334f709bc8b5875889dcb63e6ae3d4b121ad9`: Node CIDR blocklists refuse IPv4 reserved/private and IPv6 not globally routable (plus transition/documentation ranges) before pinned dial. Reject an entire DNS answer if any item is disallowed. Local Node probe: 16 blocked and 4 allowed classifications. [Task contract](CW09_WORKER_SIDE_DNS_EGRESS_FENCE_2026-10-21.md).
- **Levels:** Implemented on feature branch; exact-final-head mandatory coworker and full CI **pending**; operated staging, production qualification and activation **not proven**. No provider credentials, network permission, schema, flags, external mutations or deployments changed.
- **Next:** inspect exact doc-inclusive PR-head `test-and-build` / `coworker` real proxy step / `ci-merge-gate`, obtain independent human review, keep draft/unmerged until native main governance and staging dependencies proven.

---

## V-01 required-check source pinning — 21 October 2026 (Asia/Dhaka)

- **Current baseline for this branch:** main `0c4b8a7d049aad4ff4657a5f101af55d05c792b5` (merged PR #525). PR #525 exact-head [CI #39493914888](https://github.com/rumman52/Shuddho/actions/runs/39493914888) concluded failure: test-and-build and coworker succeeded, ci-merge-gate failed. Main protection endpoint reports `protected=false`. V-01 issue [#484](https://github.com/rumman52/Shuddho/issues/484) remains open.
- **Implementation branch:** `audit/v01-ci-check-source-pinning-20261021`; [task contract](V01_REQUIRED_CHECK_SOURCE_PIN_2026-10-21.md). The read-only native policy evaluator now requires explicit GitHub Actions App source (ID 15368) per required job, rejects arbitrary/unpinned/duplicated sources, and keeps 2=blocked or 3=configuration-candidate (never success 0).
- **Tests/review:** Expanded native audit from 11 to **15 authored tests**. No local Python test execution, successful final-head CI, human approval or review sign-off is claimed at this checkpoint; retrieve exact-head CI after PR creation.
- **Levels:** implemented as review-branch changes; repository-verified **pending**; staging-verified **not established**; production-qualified **NO**; activated **NO**. No settings, providers, deployments, release flags or privileges were changed.
- **Next exact action:** obtain exact-head CI and independent final-head review, then authorized owner configures effective native protection and demonstrates live red/unreviewed/stale-head negative controls and green/reviewed positive control. Do not merge or close #484 based on a source-only diagnostic.

---

## V-01 continuation — live review snapshot confirmation (21 October 2026, Asia/Dhaka)

- Baseline main `e937dd974c04c725faca74fb5d6c3569f83c1b2c` (merged PR #523). [PR #523](https://github.com/rumman52/Shuddho/pull/523) **merged 2026-10-20 20:06:45 UTC** with **zero submitted reviews**. Exact-head [CI #39487739882](https://github.com/rumman52/Shuddho/actions/runs/39487739882): `test-and-build` success, `coworker` cancelled, `ci-merge-gate` failure. Native controls still BLOCKED [#484](https://github.com/rumman52/Shuddho/issues/484).
- Next bounded defect: live `scripts/independent_review_gate.py` re-fetched PR metadata after review pagination, but failed to re-fetch independent review *state*; a dismissal or newly submitted change request could be absent from the stale approval snapshot. This is a source gate weakness, **not a native branch protection fix**.
- Draft [PR #524](https://github.com/rumman52/Shuddho/pull/524), test-first `1f19e502f60accae966de5b3620bb069dba736e3`; actual [RED CI #39490196014](https://github.com/rumman52/Shuddho/actions/runs/39490196014) showed **5 intended regression failures, 1,266 tests passed, 71 skipped**. Fix `dfcf9e1f7178a7a23cbafd5ab47be33c54e88f60` re-fetches bounded review pagination, rejects changed evidence, and rechecks PR metadata after second fetch. `200e8595b401d91479d0f660a07cfe6342fd151a` updates original test's exact API call assertions.
- [Task contract](V01_REVIEW_SNAPSHOT_CONFIRMATION_2026-10-21.md). **Verification pending on final doc-inclusive PR head:** all three required jobs must complete successfully; no early merge, no bypass, and no independent-approval claim from automation.
- V-01 [#484](https://github.com/rumman52/Shuddho/issues/484) still needs owner/admin enforced native branch protections and negative-control verification. Staging [#291](https://github.com/rumman52/Shuddho/issues/291) is separately blocked. No production enablement, schema, credentials, provider calls, payments or deployment changed.

---

## V-01 continuation — historical approval vs CI gate chronology (21 October 2026, Asia/Dhaka)

- Baseline `main` `13360a9cd4e2d64fa9f2f2bf8c35befd4ca531ad` after #522; PR #522 **merged 2026-10-20 19:45:33 UTC**, no submitted independent human reviews, after code job success but before `coworker` cancellation and `ci-merge-gate` failure on exact-head [CI #39484713573](https://github.com/rumman52/Shuddho/actions/runs/39484713573). Both latter conclusions occurred **after merge**. Recorded in [#484](https://github.com/rumman52/Shuddho/issues/484#issuecomment-6300108322).
- Next bounded bug: `scripts/v01_merge_evidence.py` could report no incident when the first effective independent current-head approval was submitted **after** the historical `ci-merge-gate` completed (yet before PR merge). This specific gate run could not have observed any of those later approvals.
- Draft [PR #523](https://github.com/rumman52/Shuddho/pull/523). Tests-only commit `f3f6be69616a693ddd9947398d90e0d911598bb0`; real [RED #39487371765](https://github.com/rumman52/Shuddho/actions/runs/39487371765) `test-and-build` showed **3 intended failures, 1,263 passed, 71 skipped**, with unaffected positive control passing. Source fix `8631ebec491180aba9fa7d3a4ea3a72900cc43ab` binds effective approval times to the exact CI gate completion and flags `ci-merge-gate:completed_before_independent_approval` when no such approval existed by that time.
- [Task contract](V01_APPROVAL_GATE_CHRONOLOGY_2026-10-21.md). **Final-head CI required**: inspect all three required jobs after documentation commit, do not infer the outcome from earlier RED, and do not merge without independent human review.
- V-01 [#484](https://github.com/rumman52/Shuddho/issues/484) remains **OPEN/BLOCKED on native owner/admin protections and negative-control verification**; staging [#291](https://github.com/rumman52/Shuddho/issues/291) is separate. No deployments, payments, provider grants, secrets, policy changes or production activation.

---

## V-01 continuation — independent review submission evidence (21 October 2026, Asia/Dhaka)

- Refreshed main `d335fe98dcd277daa02011c0900ad957f62e7495` was the merge commit of PR #521. [Exact-head CI #39481714982](https://github.com/rumman52/Shuddho/actions/runs/39481714982): `test-and-build` passed at 19:16:21 UTC; PR #521 **merged at 19:26:14 UTC without submitted reviews**; `coworker` was cancelled at 19:27:28 UTC and `ci-merge-gate` failed at 19:27:36 UTC. Both were **post-merge** outcomes. V-01 native governance is still blocked [#484](https://github.com/rumman52/Shuddho/issues/484#issuecomment-6299558811).
- Chosen bounded source defect: `scripts/independent_review_gate.py` did not verify submission timestamps for APPROVED/CHANGES_REQUESTED/DISMISSED reviews or reject duplicate review IDs. These are malformed-evidence acceptance gaps, **not** the cause or cure of the native settings misconfiguration.
- Draft [PR #522](https://github.com/rumman52/Shuddho/pull/522). Test-only SHA `4b5848c4088f672c7e86521413aee7d3afe4888d` produced authoritative [RED #39484280083](https://github.com/rumman52/Shuddho/actions/runs/39484280083): **6 expected failures, 1,256 passed, 71 skipped**. Fix SHA `e907878b3b5cca3252405131637f20f5792d0cf4` adds timezone-aware submitted-at and globally unique review-ID validation, preserving nonactionable PENDING/COMMENTED semantics.
- [Bounded task contract](V01_REVIEW_SUBMISSION_EVIDENCE_2026-10-21.md). At checkpoint, exact-final-head **GREEN and mandatory coworker** must be independently read from GitHub Actions. A test-only red result is not verification of implementation; a green `test-and-build` alone is not a green full workflow.
- **Do not merge**: owner/admin main branch controls and independent final-head human review are not proven; V-01 [#484](https://github.com/rumman52/Shuddho/issues/484) remains OPEN. No new permissions, releases, credentials, providers, production/staging deployments, or cost.

---

## V-01 continuation — workflow provenance binding for merge evidence (21 October 2026, Asia/Dhaka)

- Refreshed `main` at start: `25c79968d763ce8d5bdba53ed0d0d66ba7bb2562` after #520. The #520 draft was merged at **19:03:54 UTC** on 20 October 2026 **without reviews**, after `test-and-build` succeeded (18:59:43) but **before** `coworker` finished cancelled (19:04:38) and `ci-merge-gate` finished failure (19:04:46) on exact-head [CI #39479360250](https://github.com/rumman52/Shuddho/actions/runs/39479360250). This is a **new governance incident**, not V-01 acceptance.
- Bounded source defect: `scripts/v01_merge_evidence.py` checked exact commit SHA but not whether the workflow run belonged to the PR's source branch/head repository and target repository. Introduced nine provenance controls first on SHA `b3c8b594caf39078fb22fe8c274e0ce1a264c70e`; [RED CI #39481027487](https://github.com/rumman52/Shuddho/actions/runs/39481027487) confirmed **9 intended failures, 1,246 passed, 71 optional skips**, in test-and-build before implementation.
- Draft [PR #521](https://github.com/rumman52/Shuddho/pull/521), branch `fix/v01-evidence-run-provenance-20261021`. Production code now rejects missing/mismatched `head_branch`, `head_repository.id`, and base `repository.id` against PR metadata; invalid evidence remains fail-closed. [Task contract](V01_WORKFLOW_PROVENANCE_BINDING_2026-10-21.md).
- **Verification boundary:** only the test-first RED result is fully confirmed at this checkpoint. Need to inspect final SHA full CI and independent human review before even considering merge. The evidence script is read-only and not enforceable native branch protection.
- **Governance V-01 #484 BLOCKED** until an authorized admin configures and proves non-bypassable exact-head CI and independent-review rules with negative controls. External staging [#291](https://github.com/rumman52/Shuddho/issues/291) incomplete. No permissions, secrets, deployment, production flag, paid resources or activation were changed.
- **Next:** verify final-head tests and coworker, request independent maintainer review, keep the PR draft/unmerged. Native owner/admin policy work is an independently required release prerequisite.

---

## V-01 next bounded task — historical pre-merge evidence audit (21 October 2026, Asia/Dhaka)

- Fresh `main` before this work: `1f50654d514a5c3c0079886c7154cecc4e793e8e` (PR #519 merge). [#519](https://github.com/rumman52/Shuddho/pull/519) merged **20 October 2026 18:42:34 UTC** with **zero submitted reviews**, despite exact-head [CI #39471452728](https://github.com/rumman52/Shuddho/actions/runs/39471452728) ending **FAILURE** at 18:30:39 UTC. `test-and-build` and `coworker` had passed; `ci-merge-gate` failed at 18:30:38 UTC. This is a confirmed merge-after-failed-gate incident, not a merely pending job. Recorded in [issue #484](https://github.com/rumman52/Shuddho/issues/484#issuecomment-6298600506).
- Branch `audit/v01-premerge-evidence-20261021` adds a **read-only**, fail-closed historical evidence classifier and focused regression tests. The classifier binds the exact PR SHA, reviews, three job outcomes and pre-merge completion timestamps; it refuses to equate no observed incident with effective branch protection. [Contract](V01_PREMERGE_EVIDENCE_AUDIT_2026-10-21.md).
- Focused isolated local test suite: **15 passed**, no skips. Local `py_compile` passed. These are NOT full repository or exact-head GitHub CI results, and the script is not configured as a required merge check.
- Current main branch summary reported `protected: false`, enforcement off; the rulesets list was `[]`, while the detailed protection endpoint returned **403** to the installed GitHub integration. Effective organizational/admin policies and tested bypass actors still require authorized inspection. Source audit/CI cannot enforce repository merges.
- **V-01 #484 OPEN / native protection NOT VERIFIED.** No repository-settings write, deployment, secret, cost, staging/prod activation or new execution authority. External staging prerequisites #291 and all seventeen A/C/P/V acceptance rows remain incomplete. Do not merge this branch without independent human review and final-head checks.
- Next: exact-head CI and independent review of this draft PR; independently, repository owner/admin enforces main rules and proves a failed/unreviewed PR cannot merge and a final-head reviewed PR can. Only that admin proof can change V-01 status.

---

## V-01 continuation — PR metadata revalidation during review retrieval (21 October 2026, Asia/Dhaka)

- Refreshed base main: `3eba42fb767ca29e24eca4ead22273eae09dd535`, merged #518. GitHub reports #518 merged at 17:50:47 UTC on 20 October and zero submitted reviews. Its earlier exact-head run #39462233199 passed both code jobs but **failed** independent-review gating; later run #39469590777 was still running during task selection. No effective governance acceptance is inferred.
- Next bounded defect: `validate_live_review` fetched PR metadata only before paginating reviews. A concurrent push, draft conversion, close or merge during retrieval could leave old metadata accepted with an old-head review.
- Test-first evidence: test-only head `36ea88e83dcf5a6a01c3b720cc77b28152aa0e3f`, [CI #39471147429](https://github.com/rumman52/Shuddho/actions/runs/39471147429), job 118795217428: **9 failed, 1,219 passed, 71 skipped**. All failures were the intended new live-validator cases. Lightweight optional-dependency skips are not mandatory coworker evidence.
- Implementation on `fix/v01-review-fetch-revalidation-20261020`, draft [#519](https://github.com/rumman52/Shuddho/pull/519): preserve initial validation, refetch PR metadata after the terminating review page, then reapply the current-head/eligibility/independence policy. No workflow, permission, schema or release flag changes.
- Independent agent review of the design/tests found no Critical/Important issue and requested initial-invalid/final-valid coverage. Three such cases were added before implementation. Final whole-diff agent review and exact-head code CI remain pending at this checkpoint; consult the final PR description for fresh evidence. Agent review does not satisfy independent human approval.
- [Contract](V01_REVIEW_FETCH_REVALIDATION_2026-10-21.md). This check is defense in depth, not an atomic merge transaction. Review changes after collection or PR changes after the final read require native GitHub review/check protections and event-driven reevaluation.
- **V-01 #484 remains OPEN**. Do not merge this unreviewed draft or count code CI as branch-protection evidence. Owner/admin must enforce and negatively test required checks/reviews without routine bypass. Staging prerequisites #291 and the full A/C/P/V qualification requirements remain incomplete. No deployment or production activation was performed.

---

## Current continuation — TX-03 integrity regression and corrective PR #503 (20 October 2026, Asia/Dhaka)

- **Current main at the regression:** `e8dfccdde32604824f67975be0a170c2563caec4`, after PR #502.
- **Regression evidence:** main CI [#39397296464](https://github.com/rumman52/Shuddho/actions/runs/39397296464) completed with `test-and-build` success, `coworker` failure (**4 failed, 1,452 passed**), and `ci-merge-gate` failure. The failing tests reject tampered stored terms/price before review binding, action approval, and provider claim.
- **Root cause:** PR #502 changed only two test files; it did not change production code. `TransactionRepository._require_current_fresh_terms` and `ActionRepository._validate_transaction_source_binding` trusted the stored `terms_sha256` value without recomputing it from persisted terms/price/quote data.
- **Corrective work:** draft [PR #503](https://github.com/rumman52/Shuddho/pull/503) adds shared canonical snapshot verification, validates redundant currency/total fields, and checks integrity at review binding and transaction-bound action approval/execution. The PR remains unmerged.
- **Verification boundary:** inspect the final PR #503 head and require exact-head `test-and-build`, mandatory `coworker`, and `ci-merge-gate` to pass; perform independent review and do not weaken assertions. A test-only or stale-head green run is insufficient.
- **V-01 remains OPEN:** repository rulesets currently return an empty list; this connection receives 403 for branch-protection reads and cannot change effective protection. Owner/admin action is still required to configure and test merge rules.
- **Overall status: INCOMPLETE.** No staging/production qualification or activation is claimed.

---

## Current architecture/core continuation — post-merge verification and governance (20 October 2026, Asia/Dhaka)

- **Current main:** `41a22aab83d48d78b65ebc530cb2889aeb54947b`, merge commit for PR #500.
- **PR #500 exact-head CI:** [run #39378060158](https://github.com/rumman52/Shuddho/actions/runs/39378060158) ultimately passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate`. The PostgreSQL connected-read/revocation concurrency regression ran in the required coworker gate after the fixture's parent rows were explicitly flushed before dependent rows.
- **Critical timing detail:** PR #500 merged at 06:10:43 UTC. Its `coworker` job completed at 06:26:55 UTC and `ci-merge-gate` at 06:27:01 UTC; the submitted-review API returned zero reviews. The exact-head workflow passed eventually, but its later success does not prove pre-merge enforcement.
- **Merged-main CI:** [run #39378904314](https://github.com/rumman52/Shuddho/actions/runs/39378904314) passed all three required jobs on this exact main SHA.
- **V-01 remains OPEN:** the repository branch endpoint reports `protected: false` and repository-level required-check enforcement disabled. Applicable organization-level policy still needs owner/admin inspection. Require PR-only merges, final-head checks, independent approval and substantive review-thread resolution; avoid ordinary bypass and validate both blocked and allowed merge cases. No repository settings were changed here.
- **Staging remains separate:** external worker, Temporal, S3, synthetic identity and provider/release-freeze prerequisites remain tracked in [issue #291](https://github.com/rumman52/Shuddho/issues/291). Do not put secrets in GitHub/chat; no staging or production qualification/activation is claimed.
- **Next actionable work:** repository/organization owner/admin must resolve V-01 in GitHub settings. Continue source implementation only after refreshing the specific acceptance row and proving the proposed gap is still present on current main; do not repeat already-merged PRs #497–#500 or infer full completion from green CI.
- **Overall verdict: INCOMPLETE.** All 17 A/C/P/V requirements remain not fully qualified; independent review, operated staging, quality/SLO evidence and explicit release authorization remain separate gates.
---

## Part 01 — connected-read grant admission TOCTOU (20 October 2026, Asia/Dhaka)

- **Base main SHA:** `bb366506d07ab2748fbbc8ea8d36b7b799f9cfb7` (PR #496 merge).
- **Root cause:** `ConnectorReadRepository.create` validated a read connection in a separate session, then persisted the grant without rechecking active state or current scopes. A disconnect/scope change in that gap could leave an active grant row attached to revoked authority.
- **Implementation:** PR [#497](https://github.com/rumman52/Shuddho/pull/497) merged a connection-first lock and current identity/scope check in the grant-creation transaction, plus deterministic disconnect/scope-revocation regressions.
- **Verification boundary:** PR #497 was merged while mandatory `coworker` was still running and without a submitted independent review. Its merge is not proof of complete required CI or governance. Recheck the exact merge-head results.
- **Contract:** [PART01_CONNECTED_READ_GRANT_ADMISSION_2026-10-20.md](PART01_CONNECTED_READ_GRANT_ADMISSION_2026-10-20.md). No migration, capability default, API surface or production configuration changed.

---

## Part 00 governance audit — 20 October 2026 (Asia/Dhaka)

- **Current main:** `bdd12f24390077cc838d4f528b5d8c58eb8c8a78` (PR #495 merged). This supersedes older checkpoint references to `c2d029c4782768b8aba04c96105eae978d7e2c07`.
- **PR #495 / C-01:** the Runtime v3 finalization fix for cancelled/cancel-requested and missing runs is merged. Its exact-head `test-and-build`, `coworker`, and `ci-merge-gate` eventually passed ([run #39319946005](https://github.com/rumman52/Shuddho/actions/runs/39319946005)), but the PR merged before `coworker` and `ci-merge-gate` completed. No submitted PR review was recorded. Do not count later green checks as proof that pre-merge governance worked. [Contract](C01_CANCELLED_FINALIZATION_FENCE_2026-10-20.md).
- **Current main CI:** all three required checks passed on exact `main` SHA `bdd12f24390077cc838d4f528b5d8c58eb8c8a78` in [run #39320415139](https://github.com/rumman52/Shuddho/actions/runs/39320415139).
- **V-01 remains OPEN; repository-level enforcement is not demonstrated:** GitHub's branch endpoint reports `protected: false` for `main`, and the repository rulesets API returned an empty list. The detailed legacy branch-protection endpoint returned 403 to the connected integration; inspect any applicable organization-level policy in Settings → Rules/Branches. Prove pending/failing checks block merge and that a passing independently reviewed PR can merge. [Issue #484](https://github.com/rumman52/Shuddho/issues/484).
- **Staging remains blocked by external prerequisites:** [issue #291](https://github.com/rumman52/Shuddho/issues/291) still lists the persistent worker, Temporal/S3 credentials, synthetic identity, provider setup and release-freeze checks. No secrets in GitHub/chat; no production activation.
- All 17 A/C/P/V acceptance requirements remain **not fully qualified**. The next safe step is owner/admin completion of V-01 governance, while staging prerequisites are completed separately; do not enable unqualified capabilities.
---

## Architecture/core closure — C-01 final completion evidence (20 October 2026)

- Base `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`, dedicated branch `codex/c01-v3-completion-evidence-20261020`. Existing merged #490 replay behavior preserved.
- Reproduced three finalization bypasses: empty run, missing-information receipt, unconfirmed action receipt. Pre-fix run: **3 failed, 3 positive controls passed**. Finalization now reuses `v3_can_complete` inside the existing run-row transaction. No schema, new authority, capability default or activation change.
- Focused final recovery/finality checks: **56 passed, zero skips**; baseline **50 passed**. Independent read-only agent review found no Critical/Important findings. Full local suite is running; mandatory exact-head GitHub CI remains required. [Contract](C01_V3_COMPLETION_EVIDENCE_2026-10-20.md).
- Current staging preflight is **blocked_external: RENDER_API_KEY REQUIRED** in this session. This does not establish remote billing/deployment status. Operated browser/sandbox isolation, CW-11 mixed-version drain, sixteen CW-02 staging artifacts, realistic coworker/model quality and independent human release reviews remain unverified. The full 17-row A/C/P/V inventory remains in scope and INCOMPLETE.
- Next source tasks found by independent review: sandbox cleanup-before-completion and deadline enforcement during control I/O; conversation linked-run navigation and payload-bound UI retries. Each requires a separate reviewable task. No production activation or merge performed.

---

## Architecture/core closure — C-01 completed-step deadline retry (20 October 2026)

- **Starting main:** `7aa69522d8be40360123c4ec6d21896c3c9792cd` includes merged #489. PR #489's exact-head CI passed; post-merge CI was still in progress at snapshot.
- **Defect:** `execute_step` rejected a completed Runtime v3 invocation on delayed activity retry if the task deadline had passed, before consulting its existing durable state.
- **Patch:** [PR #490](https://github.com/rumman52/Shuddho/pull/490) replays previously completed v3 invocation without dispatch, but rejects cancellations/competing terminal outcomes and enforces deadline before fresh work. Legacy v1/v2 behavior preserved. [Contract](C01_V3_STEP_COMPLETION_DEADLINE_REPLAY_2026-10-20.md).
- **Evidence:** five regression instances committed before source change; must complete mandatory exact-head CI with zero skips and independent review. Synthetic receipt fixture does not establish operated Temporal/PostgreSQL or provider verification. C-01/A-02 and broader A/C/P/V acceptance remain open.

---

## Architecture/core closure — C-01 terminal tool state integrity (20 October 2026)

- **Base:** main `79c111d7bc3ec8ae1ad65b55e4f78595aec54e46`, merged #485. Independent [PR #486](https://github.com/rumman52/Shuddho/pull/486) prevents late Runtime v3 tool plan/start/receipt and approved-action readiness transitions from reviving an already-terminal run.
- **Root cause and scope:** `append_v3_step`, `begin_invocation` and `finish_invocation` did not check non-cancel terminal Runtime v3 outcomes under their existing row locks. The fix adds fail-closed guards while preserving legacy v1/v2 operations and exact committed result replay. [Contract](C01_TERMINAL_TOOL_STATE_FENCE_2026-10-20.md).
- **Evidence:** six regression instances were committed before implementation; four additional plan/action-readiness cases were added with the follow-up guards. Exact-head CI and independent review are required; unexecuted/cancelled test-only CI is not failing-first evidence. No live provider/worker or staged process-recovery proof is claimed.
- **Remaining:** C-01/A-02/P-03, CW-09 live isolation, CW-10 sandbox, CW-11 mixed worker and all operated quality, security, rollback, activation gates remain open. No schema, new authority, default flag or production action.

---

## Architecture/core checkpoint — A-03 compatibility inventory and combined verification (20 October 2026)

- Inspected main `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`; dedicated documentation branch `codex/a03-compatibility-inventory-20261020`. [62-revision review and rollback inventory](A03_MIGRATION_COMPATIBILITY_2026-10-20.md). Alembic ScriptDirectory and source metadata confirm one linear chain of 62 revisions with head0062; all local links resolve. Independent review corrected five explicitly refused expand-only downgrades and clarified reviewed research's database version versus Temporal type.
- Three separate, unmerged source PRs: [#491](https://github.com/rumman52/Shuddho/pull/491), head `e7644e64ac47fd81652894108dc2698bd4f02765`, final completion result validation; [#492](https://github.com/rumman52/Shuddho/pull/492), head `7e9d5f96658a80d6dc96e9dc4961e0250d1e1710`, sandbox supervision/cleanup; [#493](https://github.com/rumman52/Shuddho/pull/493), head `ab428153cb4828f945252f020062e7b48b205651`, conversation retry/navigation identity. Their source trees match the corresponding locally tested commits. No PR is treated as merged or activated.
- Combined local source head `6cc65704ea7fb9ad5005405dc5b253b39e848a30`, tree `d13cef85655742286560609215a2081cd11afba2`, applies all three without conflicts: **245 related Python tests passed, zero skips/failures**, mandatory collection gates passed. Full JavaScript workspaces passed, including web-editor **120 tests**; final TypeScript/Vite build passed. Independent source reviews resolved all substantiated Critical/Important findings.
- Full local Python run on the C-01 source tree matching #491: **2338 passed, 86 skipped, 17 warnings**, zero failed/error tests. Skips: 43 need PostgreSQL (41 dedicated DB, one concurrent admission, one post-mutation disconnect); 41 need a Temporal server; two ML collection skips need PyTorch. This is not a zero-skip mandatory-integration verdict. Local JUnit2 emitted record_property warnings; six proposal-fixture serialization warnings also occurred. Required GitHub coworker CI supplies separate PostgreSQL/Temporal/browser evidence.
- At this checkpoint, all three PRs have successful test-and-build checks; their full coworker/merge gates remain to be refreshed. CI runs: [#491](https://github.com/rumman52/Shuddho/actions/runs/39314867789), [#492](https://github.com/rumman52/Shuddho/actions/runs/39316114712), [#493](https://github.com/rumman52/Shuddho/actions/runs/39316327464).
- Offline evaluation gates passed: agent12/12, routing27/27, multilingual23/23, permanent suite410 scenarios, long-horizon6/6 scenarios with62/62 milestones, curated quality5/5. These are deterministic/offline contracts, not live model usefulness, cost/latency, human acceptance or availability measurements.
- **Remaining scope unchanged:** all17 A/C/P/V rows; archived-history replay corpus, exact old/new binary compatibility, sixteen operated CW-02 artifacts, live browser/sandbox isolation, CW-11 mixed-worker drain/rollback, four realistic coworker outcomes, human security/operations review and production qualification. A-01/A-02/A-04 contracts were reviewed at bounded source interfaces; A-03 inventory now exists but compatibility/replay/operated evidence remains unverified.
- Current staging preflight is blocked by missing RENDER_API_KEY in this session. Complete the remaining final-head CI/review gates, then use existing prerequisite/freeze/qualification collectors in the approved staging context. No paid infrastructure, external messages/transactions, schema change, deployment or activation was performed.

---

## Architecture/core closure — C-01 terminal Runtime v3 planner reservation fence (20 October 2026)

- **Starting main:** `7c2eced6396f2cdf93106bf05e006b7c423eecfb` includes merged #480–#483. Existing Core v3 committed retry and no-tool block fixes are preserved.
- **Root cause:** a new post-terminal Runtime v3 activity could enter `reserve_planner` after needs_input/blocked, reserving provider/daily tokens before eventual late-decision rejection. [Contract](C01_TERMINAL_RESERVATION_FENCE_2026-10-20.md).
- **Bounded fix / PR:** [#485](https://github.com/rumman52/Shuddho/pull/485) rejects new logical decisions early and under the AgentRun reservation lock; exact committed result replay, cancellation errors and v1/v2 behavior stay unchanged. No schema, grants, capability defaults, paid providers or activation.
- **Evidence boundary:** five test instances committed before implementation; require exact final-head CI and independent review before declaring repository verification. No deployed Postgres/Temporal, live provider/cost, mixed-version or operated staging evidence supplied. A-02/C-01 remain open at complete acceptance level.

---

## Architecture/core closure — P-01 conversation request and navigation identity (20 October 2026)

- Branch `codex/p01-conversation-request-navigation-20261020`, base `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`. [Contract](P01_CONVERSATION_REQUEST_NAVIGATION_2026-10-20.md).
- Reproduced three defects with mounted React components: an old linked run opens unrelated recent work; edited message/title retries reuse the original accepted payload key. Final source preserves exact linked-run GET even outside recent30 and binds retry keys to normalized request payloads, including conversation and ordered source identity.
- Six mounted component scenarios pass: old linked run, rejected target without fallback, identical message/title replay, changed message/title. Full JavaScript workspace suite passed; web-editor runner **120 passed, zero failures/skips/cancellations**. Final web-editor TypeScript/Vite build passed. Independent read-only agent review found no Critical/Important findings. React renderer is a development-only dependency; the test bundle uses the same native React instance to avoid hanging act MessagePorts.
- Required final-head CI remains pending at publication. Chromium download in this session failed; mounted component/client fixtures are not a full browser/API/worker reconnect qualification. No schema, approval, model provider, backend history limit, production dependency, deployment or activation change. P-01/P-03 and the full A/C/P/V inventory remain unqualified.

---

## Architecture/core closure — P-01 conversation activity refresh ordering (19 October 2026)

- **Starting main:** `bc88f124e61f003bcbf70dbba2303590992edd0a`, merged PR #482. [Task contract](P01_CONVERSATION_ACTIVITY_REFRESH_ORDER_2026-10-19.md).
- **Source-level defect:** `ConversationWorkspace` runs a 5-second activity polling loop without preventing simultaneous requests or rejecting older responses. A slow response can overwrite a more recent run state; a post-dispatch explicit refresh can also lose to a stale poll. The activity API is read-only, but misleading progress affects P-01 continuity.
- **Bounded change:** serialize only background polls and reject stale results using a monotonic request revision shared with explicit refreshes; invalidate on conversation switching/unmount, and avoid applying an old conversation's response. No new ledger, API, provider, navigation, or authorization behavior.
- **Regression coverage:** new Node unit tests for out-of-order completion, conversation switch, and explicit action refresh. Full frontend test/build, final-head mandatory CI, independent review and staging UI reconnect remain to be verified at the PR. No activation.

---

## Architecture/core closure — P-01/P-02 source identity (19 October 2026)

- Starting main `8a83844b148a811357b8906c58deb3ba8b76f1d3` contains merged #479; no open PR existed at fresh task selection. #479 exact-head required CI passed. Merged-main CI is checked separately.
- Branch `codex/core-context-source-closure-20261019` fixes three reproduced core/context failures: changed dispatch output-language replay, expired-source memory acceptance, and goal-memory acceptance after originating conversation erasure. [Contract](CORE_CONTEXT_SOURCE_CLOSURE_2026-10-19.md).
- Failing-first result: 3 failed, 1 positive control passed. Focused final result: 63 passed, zero skips/failures/errors across conversation admission/dispatch/context and memory; mandatory collection gate passed. Final-head full CI and independent review are pending at publication; inspect this branch's PR checks for final results.
- This is one coherent source slice in the user's full Architecture/Core scope. Remaining implementation review found durable Runtime v3 retry, sandbox cleanup/process-boundary and conversation steering/navigation gaps; these are being handled separately. The existing 17 A/C/P/V acceptance rows remain in scope.
- No staging, human security review, production qualification or activation is claimed. Current local staging access is not supplied; do not manufacture provider/deployment evidence.

---

## CW-02 retention reference snapshot ordering — 19 October 2026 (Asia/Dhaka)

- **Verified starting main:** `a95d87f6aea1f54139737a628675850f95524576`, merged [PR #478](https://github.com/rumman52/Shuddho/pull/478). Exact-main [CI #39260672598](https://github.com/rumman52/Shuddho/actions/runs/39260672598) passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate`. No open PR existed at selection. Historical pending PR/CI statements below are superseded for this starting revision.
- **Demonstrated defect:** orphan cleanup sampled database references before potentially slow object inventory. An age-eligible object checkpointed during the listing could be falsely identified and deleted. Both new preview/apply cases failed against unchanged production code.
- **Bounded implementation:** branch `codex/cw02-retention-reference-snapshot-20261019` reads references after inventory completes. Its real SQLite export checkpoint/local-store regressions preserve newly referenced bytes while retaining a genuine orphan cleanup control. Existing minimum-age, prefix, inventory-validation and failure/retry behavior remain unchanged. [Task contract and residual boundary](CW02_RETENTION_REFERENCE_SNAPSHOT_2026-10-19.md).
- **Verification:** baseline retention suite 20 passed; pre-fix regression 2 failed, 20 deselected; post-fix retention suite 22 passed, zero skips/failures/errors; mandatory JUnit collection gate passed. Full local suite is running; required final-head CI remains pending at publication. Independent final read-only branch review found no Critical/Important findings and independently reran both new cases (2 passed, 20 deselected). This is agent review, not human security/operations certification.
- **Residual boundary:** references committed after the post-inventory database read can still race deletion. This slice does not establish atomic garbage collection; operated cleanup requires quiescent writers until coordinated exclusion is qualified. Synthetic aged local objects are not real S3 outage/erasure evidence.
- **Review PR:** [#479](https://github.com/rumman52/Shuddho/pull/479), targeting `main`; code/test content commit `6ed3b6c66daf332b69bef219ff376c7a1a62ea69` has Git tree `7671246b5a588b353e81efaca357ab90a9d3e46a`, matching the locally tested/reviewed tree. This documentation follow-up records review and current preflight; inspect the PR head and its new CI before integration.
- **Fresh local staging preflight:** `uv run python -m scripts.staging_prerequisite_preflight --output /tmp/shuddho-staging-preflight.json` returned `blocked_external: RENDER_API_KEY REQUIRED`. This establishes missing access in this session only, not current Render billing/worker state or absence of repository secrets. The next environment owner step is to run the same preflight within the approved staging secret context, then freeze/verify matching API and worker identity and collect operated scenarios.
- **Completion:** implemented on review branch; full repository verification pending; staging/production qualification and activation not established. All sixteen operated CW-02 cases, matching staging identity, CW-11 mixed-version drain, live browser/sandbox isolation, measured coworker/model quality and independent release reviews remain open. No deployment or activation.
- **Next:** inspect final-head required CI and independent branch review, integrate through the review process, then execute controlled staging collectors when matching environment/provider access is available. Do not replace missing operated proof with more synthetic PASS records.

---

## Architecture/core closure — C-01 no-tool terminal retry integrity (19 October 2026)

- **Baseline:** `main` `129fa78a578df10ad861a9ded7a3a3a4fec90cf8`, after merged [#481](https://github.com/rumman52/Shuddho/pull/481). Dedicated [PR #482](https://github.com/rumman52/Shuddho/pull/482) addresses a bypass of that durable decision-result path when no tools are enabled.
- **Defect and scoped fix:** previously the no-tool branch persisted `blocked` without a logical activity result checkpoint, and could return `blocked` after a concurrent cancellation or `needs_input` transition. The existing AgentRun transaction now atomically checks active authority, records one blocked event and one retry-identity result. No additional ledger/schema, broader grant, new tool, workflow-history change or activation.
- **Evidence status:** three replay/cancellation/competing-terminal regression tests were committed before implementation; two additional lost-response/atomic-rollback tests were added after the fix. The test-only CI attempt was superseded/cancelled before coworker tests completed, so failing-first execution is **unverified**, not claimed. Exact final-head CI and independent review are required for repository verification. [Contract](C01_V3_NO_TOOLS_TERMINAL_RECOVERY_2026-10-19.md).
- **Closure boundary:** C-01 and A-02 remain partially implemented and not staging-qualified. Operated Temporal/PostgreSQL recovery, browser/sandbox and CW-11 mixed-version isolation, realistic coworker quality, independent operational/security review and production activation remain open.

---

## Architecture/core closure — durable v3 decision recovery (19 October 2026)

- Branch `codex/core-v3-durable-decision-retry-20261019`, base main `8a83844b148a811357b8906c58deb3ba8b76f1d3`. [Contract](CORE_V3_DURABLE_DECISION_RECOVERY_2026-10-19.md).
- Actual Temporal activity attempt 2 previously inferred again and failed `agent_loop_detected` after attempt 1 committed. The activity now derives a stable logical identity and atomically commits the decision, memory/step/terminal effect, exact result and idempotent token settlement through the existing Agent ledger/checkpoints. Uncommitted actual inference attempts remain bounded and charged.
- New recovery module: 8 passed, zero skips; includes lost commit response and pre-step interruption. Surrounding regressions, independent review and exact-head CI are finalized in the PR; full CI is pending at publication. No migration, workflow argument/history change, grant, default flag, deployment or activation change.
- Context slice is draft PR #480, independently reviewed with 63 passing local tests; exact-head CI pending. The finite 17 architecture/core acceptance IDs remain in scope; sandbox lifetime, conversation steering/navigation/explicit memory selection and final design/inventory closure continue separately. Operated staging and human qualification remain absent.

---

## CW-02 S3 inventory owner-scope and terminal-page integrity — 19 October 2026 (Asia/Dhaka)

- **Starting main:** `b91d7952da640cc59c9c826ca0c0a18f9f23599b`, merged [PR #477](https://github.com/rumman52/Shuddho/pull/477). At task selection exact-head [CI #39238717292](https://github.com/rumman52/Shuddho/actions/runs/39238717292) had `test-and-build` success and mandatory `coworker` in progress. No independent PR review recorded. Merged-main CI remains a separate check.
- **Demonstrated gap:** Although #477 rejects missing continuation tokens, cycles, duplicate keys and malformed dates, the S3 listing adapter still trusted `IsTruncated` values of arbitrary types and accepted S3 keys outside the requested owner/prefix. `RetentionRepository.cleanup_orphans` uses the returned list for deletion.
- **Bounded implementation:** require actual boolean `IsTruncated` and enforce the requested prefix on each listed object before returning any inventory. Added deterministic fake-S3 fixtures for invalid final-page values and foreign-prefix keys on first/second pages. Preserve all existing guards, permissions and object-store interface. Require exact-head mandatory CI and independent review before merging the review PR.
- **Limit:** synthetic response-integrity tests, not actual S3 outage/erasure evidence. Full 16 operated CW-02 fault cases, CW-11 staging, browser/code sandbox isolation, live coworker outcome quality and independent release review remain open.

---

## CW-02 S3 inventory pagination and orphan-recovery safety — 19 October 2026 (Asia/Dhaka)

- **Verified starting main:** `dfe7c3c5592c8bd8edc8d5487454c2e86c7eeddf`, [PR #476](https://github.com/rumman52/Shuddho/pull/476) merged to main. Its exact-head [CI #39228196768](https://github.com/rumman52/Shuddho/actions/runs/39228196768) passed `test-and-build`, mandatory `coworker` and `ci-merge-gate`. No submitted independent review was found. The merged-main CI must be checked separately.
- **Demonstrated code gap:** `S3ObjectStore.inventory` previously returned a partial inventory when `IsTruncated` was true but `NextContinuationToken` was absent. It also lacked repeated-token and duplicate-key guards. This threatens the integrity/boundedness of existing `RetentionRepository.orphan_candidates` and `cleanup_orphans`, which consume the listing.
- **Bounded fix:** retain the existing ObjectStore protocol; reject incomplete, cycling and duplicate-key S3 listings instead of reporting partial completion or looping. Deterministic fake-S3 tests cover a valid multi-page scan, absent/blank/invalid tokens, repeated token and duplicate keys. These tests are in existing mandatory `tests/test_coworker_retention.py`. Require exact-head CI and independent review before mainline merge.
- **Evidence boundary:** repository S3-response simulation only. Real S3 read/write failures, sixteen operated CW-02 provider/process faults, staging identities, CW-11 mixed-version drain, browser/sandbox isolation and human security/production qualification remain open. No activation.

---

## CW-02 exact fault artifact-set integrity — 19 October 2026 (Asia/Dhaka)

- **Inspected main:** `2cc3778c9219d943a0e56938f2d4e4c6f75727b5` (PR #475 merged), PR #475 exact-head CI [#39220814698](https://github.com/rumman52/Shuddho/actions/runs/39220814698) passed required `test-and-build`, `coworker` and `ci-merge-gate`; no independent PR review submitted. Its merged-main CI must be checked independently.
- **New bounded acceptance:** The 16 CW-02 artifact names constitute a closed set. Both standalone `verify_evidence_files` and signed `fault_tree_sha256` reject symlinked evidence directories and unmanifested extra entries; preserve checksums, source/run identity, per-file symlink rejection and the same signed witness trust model. The branch includes unit and signed-bundle synthetic tests for exact set, extras and alias directory. Require exact-head CI + independent review before merge.
- **Qualification boundary:** Structural evidence integrity is not operated staging proof. Full 16 real fault injections, provider-applied mutation counters, CW-11 mixed-version drain, live browser/sandbox isolation, quality, independent security/operations review and production activation remain OPEN.

---

## CW-02–04 signed release schema strictness — 19 October 2026 (Asia/Dhaka)

- **Starting revision:** `main` `e43762a1aeb43602edc9c88be082f2c9d1668b17`, merged [PR #474](https://github.com/rumman52/Shuddho/pull/474). PR exact-head [CI #39218975244](https://github.com/rumman52/Shuddho/actions/runs/39218975244) had test-and-build passed, mandatory coworker in progress; merged-main CI also running at task selection. No independent review found. Do not claim all gates complete.
- **Bounded task:** `codex/cw0204-signed-schema-type-fail-closed-20261019` rejects JSON `true` or `1.0` for `checkpoint.schema_version` and signed independent-review `schema_version`, complementing strict CW-02 manifest handling. Freshly signed synthetic fixtures test both, plus ensure only frozen API/worker observations define the review timestamp floor. Require final-head mandatory CI and independent review before merge.
- **Release boundary:** code and synthetic evidence integrity only. Sixteen operated fault cases, CW-11 mixed worker drain, browser/code isolation, independent security/operations review, staging model quality and production activation all remain OPEN.

---

## CW-02 chronology mainline integration checkpoint — 19 October 2026 (Asia/Dhaka)

- **Correct source-of-truth:** `main` at `f1ae5b643da3a4a6ef9be0b16638b653bf8ba3b5` contains [merged PR #472](https://github.com/rumman52/Shuddho/pull/472), whose head [CI #39215117594](https://github.com/rumman52/Shuddho/actions/runs/39215117594) passed all three required jobs. [PR #473](https://github.com/rumman52/Shuddho/pull/473) is reported merged, but **its base was the #472 feature branch, not main**, so the CW-02 signed-fault chronology check was absent from main at inspection. No independent GitHub PR reviews were recorded for #472/#473.
- **This integration task:** `codex/cw02-chronology-mainline-integration-20261019` reuses the exact functional implementation and signed synthetic regression tests already authored in #473, cherry-picking only `scripts/cw0204_qualification_gate.py`, `tests/test_cw0204_qualification_gate.py`, and the existing CW-02 contract onto current main. It verifies that fault observations cannot predate the later of frozen API and worker readiness, including timezone offsets and signed contradictory bundles. Publish one main-targeted PR and require exact-head mandatory CI and independent review before merge.
- **Evidence level:** implementation carried into a new branch; verification/merge pending until observed. The signed gate proves structural consistency, not an actual operated staging fault, provider mutation, reviewer identity, or production release. CW-02 sixteen operated cases, CW-11 staged worker drain, real browser/sandbox isolation, independent security review, live coworker task quality and activation remain OPEN.

---

## Current continuation — CW-02 fault evidence integrity hardening (19 October 2026, Asia/Dhaka)

- **Main:** `c04eccf3ce9ca8778da0931c2f1d96d4ac3270dc` (PR #471 merged). [PR #471 head CI #39213261699](https://github.com/rumman52/Shuddho/actions/runs/39213261699) had test-and-build passed, mandatory coworker still in progress at last inspection; [merged-main CI #39214301418](https://github.com/rumman52/Shuddho/actions/runs/39214301418) was also in progress. No independent PR #471 review was recorded.
- **CW-02 next bounded slice:** `codex/cw02-fault-evidence-identity-hardening-20261019` enforces operator/environment/result identity agreement between the manifest and each checksummed fault record; rejects duplicate JSON object keys, nonfinite JSON constants, and boolean schema-version substitutions. Update both CW-02-only and signed CW-02–04 synthetic fixtures so stronger checks run through mandatory CI. The branch must pass exact-head CI and independent review before merge.
- **Evidence boundary:** This is offline internal-consistency checking only, not confirmation of operator identity or independent provider observations. All sixteen real fault cases, controlled staging identity, real browser/sandbox isolation, CW-11 drain, human security review, model quality and production qualification remain open. No activation is authorized.

---

## Current continuation — CW-02 PR #471 conflict resolution and cleanup recovery (19 October 2026, Asia/Dhaka)

- **Base:** main `7e20e1bb9dd5f80af30e104d8cc71ab1635224a6` (merged #470); required mainline CI [#39164154651](https://github.com/rumman52/Shuddho/actions/runs/39164154651) completed successfully.
- **Work:** [PR #471](https://github.com/rumman52/Shuddho/pull/471), `codex/cw02-orphan-delete-failure-reporting-20261019`, retains the existing deletion-failure regression and adds a recovery retry: the first cleanup must report the failed key without deleting it; after restoring the store, a second age-bounded cleanup must delete the same orphan.
- **Previous branch verification:** exact-head [CI #39160757345](https://github.com/rumman52/Shuddho/actions/runs/39160757345) passed test-and-build, mandatory coworker and ci-merge-gate on `1a248f6317509ab8676ef71d23cc23acd674001c`; it does **not** validate the new merge/recovery commit, whose exact-head checks remain pending.
- **Integration:** merge the newer main tree without discarding #470 browser DNS protections or already-merged CW-02 recovery tests, and retain one canonical continuation record.
- **Evidence boundary:** local SQLite/object-store failure injection is not live S3 or operated staging. Sixteen distinct CW-02 staging artifacts, independent provider-side observations, CW-11 mixed-version drain, real browser/sandbox isolation, independent security review, quality qualification and authorized activation are still open.

---

## Current continuation — CW-02 and CW-09 gates (19 October 2026, Asia/Dhaka)

- **Main:** `1a852034576a9a5124187d9901203864b3664ed6`. PR #468 hard-worker-loss orphan-recovery test is merged and its exact-head `test-and-build`, mandatory `coworker`, and `ci-merge-gate` passed.
- **Merged-main CI:** run [#39159745525](https://github.com/actions/runs/39159745525) on this SHA was still running at the last refresh. Do not call mainline fully verified until all required jobs pass.
- **CW-09 follow-up branch:** `codex/cw09-proxy-dns-response-shape-20261019-v2` validates broker response hostname and resolved-IP structure before dialing from the real CONNECT handler. Local socket regressions cover missing/mismatched hostname, empty/non-array lists, invalid IP literals and excessive entries. Exact-head CI has not run yet.
- **Evidence boundaries:** no local checkout was available to execute these tests directly during authoring; GitHub CI remains the executable verification gate. Local proxy sockets do not prove live Chromium, DNS rebinding, private-network isolation or staging.
- **Still open:** the complete sixteen-row CW-02 operated evidence matrix; protected CW11-STAGING mixed-version drain; browser/sandbox isolation; independent review; personal-coworker quality and production qualification. No deployment, provider activation or production action is claimed.


---

## Current source-revalidation checkpoint — 18 October 2026 (Asia/Dhaka)

- Refreshed main: `9e52756e4de52d95cc69879ce7cdbb3a390c0ac7`; #461 is merged, not open. No open PRs existed at task selection. Main CI [#39147097140](https://github.com/rumman52/Shuddho/actions/runs/39147097140) was still running when this checkpoint was written; its `test-and-build` job passed. The earlier #461 code/test head passed all three required jobs in #39141823326. No formal independent review submission was recorded for #461.
- Work branch: `codex/c01-late-planner-source-revalidation-20261018`. [Task contract](C01_LATE_PLANNER_SOURCE_REVALIDATION_2026-10-18.md). Fresh Runtime v3 decisions now revalidate the original conversation's selected source pins after inference, before saving model output/checkpoints. Already-committed decisions retain idempotent replay; direct/legacy run semantics remain unchanged.
- Reproduction: six source-invalidated cases failed before the guard; unchanged-source control passed. Focused conversation/context/cancellation regressions: **41 passed, 92 deselected**, zero skips. The mandatory JUnit gate passed. Full local pytest and exact-head required CI remain pending at publication; consult this branch's PR checks for the final revision. These numbers are a focused selection, not a repository-wide total.

| Part | Evidence-supported status | Remaining gates |
| --- | --- | --- |
| Architecture A-01..04 | Existing state/trust foundations and repository recovery contracts; this slice adds no store, orchestrator or schema | Mixed-version operated recovery/rollback, staging boundary review |
| Core C-01..06 | #461 grounded adapter handoff is merged; late selected-source response guard locally verified in this branch | Final-head CI/review; real browser/sandbox isolation; CW-11 staged drain; live provider/model qualification |
| Context/experience P-01..03 | Existing owned conversations and explicit selected context; delayed invalidation regression added | Four operated study/work/separation/recovery scenarios and UI reconnect evidence |
| Verification V-01..04 | Focused regression evidence only for this branch | Full mandatory final-head CI, protected staging, human security/quality review and separately authorized production rollout |

Separate read-only agent review found no Critical/Important issues; this is not human security certification. Minor observation: the no-memory-proposal assertion is only incidental because the synthetic response proposes no memory. End-to-end Temporal failure-state persistence and PostgreSQL invalidation races remain outside this regression.

The full Architecture/Core Agent workstream remains **INCOMPLETE**. No staging, production qualification or activation is established. The guard observes invalidation committed before its source check; it does not claim serializable source-deletion locking or recall of data already submitted to inference. Historical checkpoints below are retained and superseded by this entry.

---

## Current continuation checkpoint — 18 October 2026 (Asia/Dhaka)

- Current `main`: `ea7ad398f69e898b152f4227cb6e0c1a193999c1`. PR #460 is merged; its exact-head CI [#39111138510](https://github.com/rumman52/Shuddho/actions/runs/39111138510) passed all three required jobs. Merged-main CI [#39138804133](https://github.com/rumman52/Shuddho/actions/runs/39138804133) also passed all three required jobs.
- C-01 code/test commit `b3d3cad4c93abaff3523b7f998529f4a6375c46e` passed exact-head CI [#39141823326](https://github.com/rumman52/Shuddho/actions/runs/39141823326): `test-and-build`, mandatory zero-skip `coworker`, and `ci-merge-gate`. The dedicated `c01-v3-handoff-evidence` JUnit artifact records 1 test, 0 failures, and 0 skips.
- PR #461 remains open; formal independent review, live provider quality, operated staging, production qualification, and activation remain unestablished. The repository CI result does not complete the overall Architecture/Core Agent scope.

---

## C-01 Runtime v3 grounded multi-step handoff — in progress (18 October 2026)

**Base:** `main` `ea7ad398f69e898b152f4227cb6e0c1a193999c1`. **Branch / PR:** `codex/c01-runtime-v3-adapter-e2e-20261018`, [#461](https://github.com/rumman52/Shuddho/pull/461).

**Implementation:** `test_agent_v3_deepseek_adapter_executes_grounded_multistep_workflow` uses the actual `DeepSeekAgentPlanner` adapter with deterministic `httpx.MockTransport`, the real Temporal test worker, and the existing server-owned `document.create` and `email.draft` tools. It verifies the completed document observation, exact upstream task artifact handoff, source digest/provenance, two completed receipts, completion ordering, planner/token accounting, and absence of task text or synthetic credentials from Temporal history. Handoff flags are enabled only in synthetic test settings. No production runtime, API, schema, migration, authority, or default-flag behavior changes.

**Failure correction:** run [#39126595594](https://github.com/rumman52/Shuddho/actions/runs/39126595594) exposed an assertion that incorrectly expected the original brief to be absent. A second source/schema audit found that the persisted draft stores the source digest in the manifest keyed by source ID and stores source references at `draft.source_ids`, not `draft.email.source_ids`. The assertions are corrected without weakening the acceptance criteria.

**Evidence status:** exact-head CI [#39141823326](https://github.com/rumman52/Shuddho/actions/runs/39141823326) passed all three required jobs on code/test commit `b3d3cad4c93abaff3523b7f998529f4a6375c46e`. The dedicated JUnit artifact records 1 test, 0 failures, and 0 skips. The model transport and draft model are synthetic, so this is adapter/workflow integration evidence only—not live provider quality, staging, production qualification, or activation. Independent review is not recorded.

---

## CW-02 planner retry regression follow-up — repository CI verified (18 October 2026)

PR [#456](https://github.com/rumman52/Shuddho/pull/456) merged the typed retryability propagation. The first regression assertion then failed because the run DTO retains an ordinal-zero run-created sentinel in `steps` while the executable `plan` excludes it. Follow-up PR [#457](https://github.com/rumman52/Shuddho/pull/457) corrected the assertion to require an empty executable plan, the non-executable sentinel, and zero tool invocations; its exact-head CI [#39099648984](https://github.com/rumman52/Shuddho/actions/runs/39099648984) passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate`.

This closes that repository-level regression slice only. It does not complete the CW-02 16-fault matrix, independent provider-side reconciliation, authorized staging qualification, production qualification, or activation.

---

## Runtime v3 late planner cancellation fence — 18 October 2026 (Asia/Dhaka)

**Roadmap mapping:** this is a cross-cutting correctness slice supporting the CW-06 acceptance criterion “cancellation beats delayed result.” It does **not** complete all of CW-06 and is not the roadmap's CW-02 transaction-chaos task. The branch name retains its historical `cw02` segment from the original failing-first test commit.

**Reproduction-first evidence:** the initial failing-first test commit `87a37898979455b62b248098d3c5027f3490f5cd` was based on `e52006c112c8b07623dbe1c07dc982406ce31084`, before 13 newer mainline commits. [CI run #39059380961](https://github.com/rumman52/Shuddho/actions/runs/39059380961) passed `test-and-build` but failed the mandatory `coworker` job with **2 failed, 1407 passed** in 647.14 seconds. The race test observed an `AgentDecision` persisted after cancellation; the direct memory test showed `propose_from_agent` accepted a proposal after cancellation. The `ci-merge-gate` failed because the required coworker job failed. This is the confirmed pre-fix reproduction.

**Implementation:** the candidate code/test commit `dcec2490057be63ad366a9aa4eda4c15a679a898` was rebased onto current `main` `515dbc8d842645e3b93403cbe003e707642a4955`. `AgentRepository.record_v3_decision` now checks cancellation/terminal state under the existing run-row lock after the planner-call idempotency lookup; an already-recorded decision still replays without duplication. `MemoryRepository.propose_from_agent` rejects cancelled/terminal runs under its existing run-row lock before proposal persistence. Regressions cover cancellation races, direct late proposals, non-cancelled terminal runs, and idempotent replay. Task contract: [Runtime v3 late planner cancellation](RUNTIME_V3_LATE_PLANNER_CANCELLATION_2026-10-18.md).

| Evidence level | Status |
| --- | --- |
| Implemented | Yes — source and regressions are on PR #455 |
| Repository-verified | Yes — PR #455 exact-head CI #39062674571 and merged-main CI #39063079528 passed all three required jobs |
| Staging-verified | Not established; operated CW-02 transaction-chaos and full CW-06 acceptance remain separate |
| Production-qualified | Not established |
| Activated | No |

No provider was called, no secret or protected staging environment was accessed, and no deployment or capability activation occurred. Independent review is not claimed. **Next exact action:** fix the separate CW-02 planner-retry regression assertion and obtain exact-head CI evidence, then complete the remaining CW-02 fault matrix and authorized operated cancellation/recovery qualification.

---

## CW-11 staging workflow shell-input hardening — 17 October 2026 (Asia/Dhaka)

PR [#453](https://github.com/rumman52/Shuddho/pull/453) merged as `e52006c112c8b07623dbe1c07dc982406ce31084`; its exact-head CI [#39053340279](https://github.com/rumman52/Shuddho/actions/runs/39053340279) passed all three required jobs. Final review then identified a separate security defect in the merged workflow: user-supplied old-source-revision and expected-publication-version inputs were interpolated into shell command source.

The follow-up branch `codex/cw11-staging-workflow-fail-closed-20261017` passes those values through step-scoped environment variables, quotes shell expansions, rejects non-main dispatches before staging access, validates the old revision and binds service responses to requested IDs, and adds regression tests for those boundaries. Exact-head CI for this follow-up is pending. Do not call this follow-up repository-verified until its own `test-and-build`, mandatory `coworker`, and `ci-merge-gate` pass. Staging remains unverified, no protected workflow has been dispatched, and CW-11 remains default-off.

---

## CW-11 staging workflow fail-closed hardening — 17 October 2026 (Asia/Dhaka)

**Fresh base:** `main` `e7a9f22834c8c84b5d4d2e81c33af7dc96d65f32`. PR [#452](https://github.com/rumman52/Shuddho/pull/452) is merged; merged-main [CI #39050236569](https://github.com/rumman52/Shuddho/actions/runs/39050236569) passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate`.

**Next implementation slice:** draft [PR #453](https://github.com/rumman52/Shuddho/pull/453), branch `codex/cw11-staging-workflow-fail-closed-20261017`. The staging workflow previously skipped its only evidence job when the confirmation token was wrong, potentially leaving a green run with no artifact. It also applied pending staging migrations before verifying the legacy Render service had zero instances and the candidate was running the exact qualification revision.

**Implemented:** separate no-secret confirmation job that fails on an incorrect token; evidence job depends on that success; live Render service/instance/revision validation precedes pending staging migrations; Render/database/auth credentials are injected only into the specific steps that need them; standard-library workflow-contract tests; rollout runbook and bounded task contract updated. The code change does not alter runtime authorization, provider behavior, schema, or capability flags.

| Evidence level | Status |
| --- | --- |
| Implemented | Yes — draft PR #453 |
| Repository-verified | Use the latest exact-head checks on PR #453; do not infer from the prior main run |
| Staging-verified | Not established; the protected workflow has not been run in this session |
| Production-qualified | Not established |
| Activated | No; CW-11 remains default-off |

No staging secrets were accessed, no protected workflow was dispatched, and no staging migration, deployment, publication selection or activation was performed. **Next exact action:** verify all three required CI jobs on PR #453's latest head; then an authorized operator must run the protected `CW11-STAGING` workflow with real service IDs and inspect the artifact, followed by independent operational review.

---

## CW-11 historical migration dispatch fence — 17 October 2026 (Asia/Dhaka)

**Fresh main baseline:** `main` `75521bdc77fea7366127c18ee854731880cff58b`. [PR #451](https://github.com/rumman52/Shuddho/pull/451) is merged. Its exact-head and merged-main CI runs passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate` ([PR CI #39028085374](https://github.com/rumman52/Shuddho/actions/runs/39028085374), [main CI #39030046227](https://github.com/rumman52/Shuddho/actions/runs/39030046227)). CW-11 still lacks protected staging, independent operational review, and production qualification.

**New bounded task:** [PR #452](https://github.com/rumman52/Shuddho/pull/452), branch `codex/cw11-legacy-migration-dispatch-fence-20261017`. The source change is in commit `e1768729fcb1420a3d6e95021391968b51a8c8fd`; regression cases are in `a12b65d3d627d0fde1e37053851344a48012f700` and the final test-fixture correction in `734077a899e1d84bdc79671401826140397b5a26`. Contract: [CW11_LEGACY_TASK_MIGRATION_DISPATCH_FENCE_2026-10-17.md](CW11_LEGACY_TASK_MIGRATION_DISPATCH_FENCE_2026-10-17.md).

**Gap reproduced from current source:** `migrate_legacy_reviewed_tasks()` checked only the Task phase and search-attempt record. A Task may still appear queued after its parent Temporal workflow has been dispatched, including a lost dispatch response. Rebinding that Task's workflow/publication identity in place would cross an uncertain execution boundary.

**Implemented on the review branch:** migration now requires Task state and phase to remain queued; a pristine, undispatched parent AgentOutbox; an undispatched planning-state AgentRun; a planned, never-started `research.search` step; a prepared, never-started matching invocation; no linked task resource and no ToolReceipt. Existing exact review-hash, selected-publication, grant, deadline, search-attempt and worker-drain checks remain. A single unsafe candidate aborts the whole migration transaction.

| Evidence level | Status |
| --- | --- |
| Implemented | Source and regression tests committed on PR #452 |
| Repository-verified | Pending exact-head `test-and-build`, zero-skip `coworker`, and `ci-merge-gate`; do not substitute PR #451 CI |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No; capability remains default-off |

No local test execution, independent review, protected staging run, deployment, or activation is claimed. **Next exact action:** inspect all required checks on PR #452's latest head; repair failures without weakening safety assertions, then obtain independent review. The outbox fence proves a repository pre-dispatch condition only; it does not certify live fleet drain, mixed-version Temporal recovery, or production rollout.

---

## CW-11 follow-up — selection and staging claim accounting — 17 October 2026

Parent [PR #450](https://github.com/rumman52/Shuddho/pull/450) merged as `bd4fc89b0d3d43f529a4014fa6c442f4442c726c`. Exact merged-main `test-and-build` passed; mandatory `coworker` and `ci-merge-gate` were still running at checkpoint. The automated independent review could not run because the configured review service reported its usage limit.

**Gap found after merge:** the fleet compatibility check used by reviewed-skill selection/rollback and the staging evidence collector did not independently account for active claim rows on a worker whose inventory state appeared drained.

**Follow-up branch:** `codex/cw11-claim-aware-selection-evidence-20261017`.
- Lock the worker fleet first, then reject reviewed-skill selection/rollback/legacy migration if any active dispatch claim remains, even when a worker row claims to be drained.
- Make CW-11 staging evidence reject a legacy worker row with active claims, reject a missing legacy worker row, and include old-fleet claim counts in the artifact.
- Second-pass review found that a drained row from an unexpected/third source revision could still carry an active claim. Reject active claims on every row marked drained, independent of source revision, and expose the aggregate plus an explicit evidence assertion.
- Add regression tests for a legacy false-drain row, a false-drained unexpected revision, and missing legacy inventory, proving registry controls and staging evidence fail closed.

This is repository code/test work only. Protected Render staging, independent operational review, four operated coworker scenarios, production qualification, deployment, and activation remain unverified.

---

## CW-11 per-claim dispatch drain fencing — 17 October 2026 (Asia/Dhaka)

**Active branch:** `codex/cw11-per-claim-drain-fencing-20261017`, [PR #450](https://github.com/rumman52/Shuddho/pull/450), initially at `950d3be74e6bc8a31ee07ae310f675821963f7e5`. Initial exact-head CI run [#39017961482](https://github.com/rumman52/Shuddho/actions/runs/39017961482): `test-and-build` passed; mandatory `coworker` failed with 1 failed / 67 passed in the CW-11 registry suite because the new task-claim test used `reviewed_task()` without selecting a reviewed publication first. The repository correctly failed closed. A test-only correction now explicitly publishes and selects the fixture publication before creating that task; all required checks must be rerun on the resulting head. The independent Codex review could not run because the configured review service reported its usage limit. No local test execution, staging qualification, deployment, or activation is claimed.

**Failure mode closed by this slice:** an outbox could be claimed by an Agent/action dispatcher without a registered worker identity, and the worker registry could mark a worker drained while a dispatch attempt was still in flight. A worker could also claim a batch, fail on the first dispatch, and leave the rest of that batch indistinguishable from active in-flight work.

**Implementation:**
- Add migration `0062` and durable `cw_worker_claims` records for task, Agent and approved-action dispatch claims. A second-pass schema review removed a redundant ORM-only worker index; the migration/model parity regression now checks index names as well as columns.
- Make task, Agent and action outbox claims lock the registered worker first, require a fresh `running` worker on the configured queue, and create claim records atomically with outbox leases.
- Require an active durable claim at the Agent dispatch boundary, including staging/operator helper paths.
- Complete claims after each dispatch attempt returns. On a batch failure, close claims for unattempted items without acknowledging their outbox rows, preserving normal lease-based retry.
- Keep the browser-test worker lifecycle aligned with production by recording drain only after the Temporal worker context exits; make cancellation outbox coverage use a real registered worker rather than a no-identity call that always returns an empty batch.
- Make `mark_worker_drained()` refuse completion while active claims remain; expose `active_claim_count` in worker inventory and require zero claims in drain evidence.
- Add tests for Agent/action/task claim blocking, rejection of Agent dispatch without an active claim, failed-batch cleanup for unattempted items, migration/model column-and-index parity, and a PostgreSQL interleaving where a drain waits behind an uncommitted claim.

**Safety boundary:** claims have no expiry-based auto-clear. A process crash that leaves an active claim blocks drain certification until evidence-driven reconciliation. The claim ledger tracks dispatcher work; it does not replace the existing requirement to await Temporal worker shutdown before marking the process drained. No production activation, external provider mutation, deployment or protected staging run is performed by this change.

**Remaining gates:** exact-head `test-and-build`, `coworker`, and `ci-merge-gate`; independent code/security review; protected `CW11-STAGING` with real worker identities and exact-revision evidence; the four operated coworker scenarios; and separate production qualification/activation authorization.

---

## CW-11 worker-registration phantom fence — 17 October 2026 (Asia/Dhaka)

**Mainline baseline:** PR #447 is merged as `e8de414e8b98eb503700a85474190304e28e58ed`. PR #448 then merged the initial queue advisory-lock and PostgreSQL registration-trigger implementation as `6b5aa1e2743bdbbdaa7c38a55670f6d39e8043da`. Its merged-main CI run [#39008038850](https://github.com/rumman52/Shuddho/actions/runs/39008038850) has `test-and-build` green; the mandatory `coworker` job was still running at this checkpoint.

**Remaining race:** PostgreSQL row locks protect existing worker rows, not a worker inserted after the inventory query. Without queue-membership serialization, a new incompatible worker could appear between the reviewed-skill fleet snapshot and selection commit.

**Follow-up implementation on branch `codex/cw11-worker-registration-guard-followup-20261017` (PR #448 is already merged at its earlier head):**
- Add a deterministic transaction-scoped PostgreSQL advisory lock per task queue.
- Acquire it in both the fleet-compatibility snapshot and `register_worker()`, before worker-row or selection/publication work.
- Require registrations on the configured queue to match the deployment-attested runtime revision while still allowing a candidate runtime to start before the old publication is switched.
- The merged Alembic migration 0061 installs a PostgreSQL `BEFORE INSERT` trigger requiring transaction-local `shuddho.worker_source_revision` attestation. The follow-up binds that attestation to the configured runtime setting. This blocks new registrations from legacy binaries that predate the lock protocol; existing legacy rows remain available for drain checks.
- Add a SQLite contract test, a barrier-controlled PostgreSQL race test, and a PostgreSQL regression proving un-attested inserts are rejected. The mandatory CW-11 JUnit gate must collect all PostgreSQL tests with zero skips.
- No public API change, expanded grant, external action, deployment or activation. A PostgreSQL schema migration is required.

**Validation status:** the follow-up branch carries additional runtime-revision and regression-fixture hardening beyond the merged PR #448 head. Exact-head CI and independent review for this follow-up are pending. No local test execution is claimed.

**Remaining gates:** per-claim drain fencing for Agent/action outboxes; protected `CW11-STAGING` using real authorized worker identities, confirmed drain and exact-revision evidence; four operated coworker scenarios; independent operational review; and separate production qualification/activation authorization. Existing legacy processes may continue running after migration but cannot re-register if they restart; rollout/rollback must account for that availability trade-off. The intermittent parallel SQLite malformed-schema/duplicate-index symptoms also remain unexplained; a serial rerun is not root-cause evidence.


---

## CW-11 staging collector task-ledger and evidence-boundary hardening — 17 October 2026 (Asia/Dhaka)

**Base and dependency:** stacked on the exact CI-green head of [PR #444](https://github.com/rumman52/Shuddho/pull/444), `fdad69dafbd887285e93d559b2a71927ea2bbfcb`, because main still contains the pre-fix CW-11 regression until #444 is merged. Working branch: `codex/cw11-staging-collector-ledger-guard-20261017`. This follow-up does not merge or activate #444.

**Gap:** `collect_evidence()` counted only nonterminal pre-fence Tasks that already had a reviewed identity Step. It did not block an active reviewed-workflow Task missing that identity or ambiguous active legacy Agent-owned research without one. External Render JSON was validated only by `main()`, so direct callers could bypass the boundary validator. Second-pass review also found that a lost worker on an undeclared revision, a stale active worker beside a fresh candidate, or an old worker row marked `drained` without a `drained_at` timestamp could be accepted despite the rollout contract requiring explicit drain evidence.

**Implementation:** reuse `inspect_reviewed_rollback()` and fail closed on any returned blocker; include its aggregate, non-authorizing ledger result in the evidence artifact. Validate external Render payloads inside `collect_evidence()` before database reads, reject non-object/extra-field payloads and boolean-as-integer schema versions, require strict integer counts, distinct nonblank service IDs and full 40-character lowercase Git SHAs, and compare both revisions to the requested/deployment-attested values. Block lost, unknown-state and stale-heartbeat active worker records regardless of whether their revision matches the declared old revision; also require a durable `drained_at` timestamp for any old-revision worker row marked drained. Add regressions for task-ledger gaps, uncertain workers, inconsistent drain state, malformed/unverified/revision-mismatched payloads and a clean ledger. Update the rollout contract and this checkpoint.

**Validation:** source/test implementation commit `001d1b515eb3846d4002d07ee57d4b6425a3678a`, included in main-targeted [PR #446](https://github.com/rumman52/Shuddho/pull/446) head `a0bd20832a84ef86915d3d2804d8d42e214ac25c`, passed exact-head [CI run #38964001167](https://github.com/rumman52/Shuddho/actions/runs/38964001167): `test-and-build`, mandatory `coworker`, and `ci-merge-gate` all succeeded. This run includes the task-ledger, strict Render evidence, uncertain-worker and durable drain-timestamp regressions. The present checkpoint-only documentation update changes no source/test files; its PR checks may rerun automatically, but the source/test tree has passed the required suite. The prior dependency PR #444 head `fdad69dafbd887285e93d559b2a71927ea2bbfcb` also passed [run #38948849904](https://github.com/rumman52/Shuddho/actions/runs/38948849904). No local test execution is claimed. The Codex review bot reported its review usage limit and did not produce an independent review; source-level second-pass review found and fixed the uncertain-worker and inconsistent-drain-state gaps, but independent review remains open.



**Still blocked:** protected `CW11-STAGING` has not been run. It requires the protected staging environment, operator confirmation, real old/candidate Render worker service IDs, actual drain state, and an inspectable artifact bound to the exact candidate revision. No staging/production qualification, deployment or activation is claimed.

**Next:** complete independent review and the dependent PR integration sequence (#444 before #445); then run the protected staging gate only with real authorized staging inputs and inspect the uploaded evidence artifact. The task-ledger query remains a point-in-time snapshot, not a substitute for admission quiescence or whole-fleet drain.

---

## CW-11 parallel scheduler fixture correction — 17 October 2026 (Asia/Dhaka)

**Resume base:** main `272186af38965ab60e6c551e8ebce9337c6e6ae0`; open [PR #444](https://github.com/rumman52/Shuddho/pull/444) head `c99cd56c0f774beed5995a794e444b54afc42971`. This session reproduced a remaining fixture defect before repairing it: the research/document/document plan derives `[[], [1], [2]]`, while the fan-in test asserts `[[], [], [1, 2]]`. The same sequential graph prevents the restart fixture's two-branch barrier from being reached.

**Correction:** a test-only helper seeds the explicit persisted three-node DAG for the three scheduler/recovery tests. The real SQL repository, dispatcher, Temporal workflow and runtime still execute the graph. Existing plan-derivation tests remain unchanged. Reviewed research remains one call per run; no production dependency rules, authority, budgets or default-off controls are changed.

**Local evidence:** affected Temporal tests **3 passed, 25 deselected**; reviewed/research tests in `test_coworker.py` **6 passed, 81 deselected**. Full Temporal suite is running; exact amended-head CI remains required. Independent bounded review is in progress. The GitHub automated review attempt on #444 failed due to account review quota, not a demonstrated code finding. No merge/deployment/activation performed.

**Next:** verify amended #444 with all three mandatory CI jobs and review. A separate staging-collector safety patch is preserved for independent review: reuse rollback task-ledger classification and validate external evidence at the collection boundary. Real staging worker/drain/replay evidence and overall A/C/P/V qualification remain incomplete.

---

## CW-11 reviewed research parallel-test contract repair — 16 October 2026

**Live mainline truth:** `main` `272186af38965ab60e6c551e8ebce9337c6e6ae0` includes merged [PR #443](https://github.com/rumman52/Shuddho/pull/443), but both its exact-head CI [#38944172227](https://github.com/rumman52/Shuddho/actions/runs/38944172227) and merged-main CI [#38944959166](https://github.com/rumman52/Shuddho/actions/runs/38944959166) failed the mandatory `coworker` job while `test-and-build` passed. The mainline is therefore **not repository-verified**.

**Failure analysis:** The earlier Temporal failures were caused by fan-out/fan-in/restart fixtures issuing two `research.search` calls after explicitly selecting the reviewed pilot, whose accepted manifest imposes a one-call-per-Agent-run limit. A temporary attempt to route around this by honoring the mutable feature flag contradicted the registry contract: explicit publication selection remains the Agent research gate even if that flag changes, as tested by `test_selected_publication_remains_the_agent_gate_after_feature_flag_off`. That attempt also caused the current mainline registry regression. Do not weaken the one-call limit or treat flag-off as permission to downgrade selected/pinned reviewed work.

**Correction branch:** `codex/cw11-regression-ci-fixes-20261016`, corrective source/test commit `f425760326b96739067d845a7b9ac88c4476e175` before this checkpoint update. It restores the registry-authoritative admission/replay behavior, removes the contradictory test, and keeps the Temporal concurrency/recovery tests meaningful with one reviewed research task plus one independent document task. The rollback preflight still fences both legacy reviewed v1 and current reviewed v2 workflow identities. No authority, provider budget, workflow version or release flag is widened.

**Evidence:** Correction is not yet verified until exact-head `test-and-build`, mandatory no-skip `coworker`, and `ci-merge-gate` all pass on the final corrective revision. The staging workflow has not been run; its actual staging environment, Render worker IDs and operated drain evidence remain separate required inputs. No staging, production qualification or activation is claimed.

**Next:** open a corrective PR from this branch, inspect the exact final-head CI and fix any remaining failures without changing the reviewed one-call contract. Only after CI is green, continue with the protected `CW11-STAGING` operated evidence gate and verify the artifact against the exact candidate revision. Overall CW-11 remains **INCOMPLETE**.

---

## CW-11 / A-03 rollback preflight mandatory-CI repair — 16 October 2026

**Fresh failure evidence:** merged `main` `b0d6c56f81e81fef8da1cc75a0a0a215c89c992f`; exact PR-head CI [#38915877509](https://github.com/rumman52/Shuddho/actions/runs/38915877509) for #437 failed only in mandatory `coworker`: `test-and-build` passed, `coworker` failed, and `ci-merge-gate` failed. The coworker suite reported **1402 passed, 2 failed**.

**Root cause:** two deterministic fixture defects, not a production authorization defect. The research cohort test enables research but omitted the current required backend-only search-key fixture, so `Settings` validation rejected the test setup. The rollback-inventory test created the default `report_email` TaskCreate with neither notes nor a document, which the current schema correctly rejects.

**Repair branch:** `codex/cw11-rollback-preflight-ci-repair-20261016`, first repair commit `7a966660be102da4ab518154781f89b3ac66ddcf`. It supplies the repository's existing `fixture-only-search-key` convention to the research test and gives synthetic rollback tasks a fixture note. No production code, authority, provider registration, release flag or schema contract is changed. [Task contract](CW11_ROLLBACK_PREFLIGHT_CI_REPAIR_2026-10-16.md).

**Evidence state:** implemented on repair branch; focused test and exact final-head CI are pending. No staging/production qualification or activation is claimed. Next exact action: run the focused cohort-health tests, then require all three final-head CI jobs to pass before repository verification of #437 can be considered restored. Historical worker-drain/Temporal/provider staging evidence remains a separate CW-11 gate.

---

## CW-11 / A-03 historical reviewed-skill rollback task-ledger preflight — 16 October 2026

**Baseline verified at task selection:** `main` `d757d165bbb36eaea829b683714f03b37d7206d9`, merged [#435](https://github.com/rumman52/Shuddho/pull/435). [#436](https://github.com/rumman52/Shuddho/pull/436) has since been merged into `main` at `8dba11cb3d288f374be12c96410f8ee276aff67a`; this reconciliation preserves its cohort-health regression and documentation. The initial checkpoint was written before that merge. Exact review/qualification evidence remains separately gated. The merged #435 required long-running coworker jobs and P1/P2 re-review were not fully qualified at last observation. Older checkpoint sections below predate those merges.

**Isolated new work:** `codex/cw11-legacy-reviewed-rollback-preflight-20261016` introduces read-only `scripts/reviewed_skill_rollback_preflight.py` and SQL regression cases in `tests/test_cohort_health_gate.py` to count nonterminal legacy-reviewed Tasks (pinned reviewed Step without the new workflow version), active new-version Tasks missing an identity, ambiguous active legacy Agent research without a review Step, safely fenced Tasks and terminal old-reviewed Tasks. The counts run in one SQL statement snapshot; missing review Step never creates an optimistic clean result. Nonzero blocker counts return `BLOCKED_TASK_LEDGER` / failed CLI exit. A clean task-ledger snapshot is only `TASK_LEDGER_CHECK_ONLY`, with explicit false `fleet_drained_verified`, `staging_verified` and `rollout_authorized`; no mutation/provider operation or owner data disclosure. [Bounded task and operated acceptance contract](CW11_LEGACY_REVIEWED_ROLLBACK_PREFLIGHT_2026-10-16.md). Exact final-head CI and independent review are pending, so this is **implemented on branch, not repository/staging verified**.

**Open P1 and next action:** A historic nonterminal Task admitted under #434 as `work_research_v1` plus reviewed Step can still execute on pre-#435 older workers. An isolated DB inventory cannot prove that all older API/Temporal/worker processes have drained or all in-flight provider operations are reconciled. Preserve default-off policy; perform a controlled real deployment drain, worker-version inventory, historical-work reconciliation and matching staging/replay proof before closing A-03/C-05 or activating the pilot. Trusted skill publication/version selection, cross-purpose coworker scenarios and CW-09/CW-10 operated tests remain separate obligations.

**Evidence and authority:** Source/docs/test commits only; no merge, deploy, provider charge, purchase or activation. No completion percentage claimed. Next exact checks: `uv run --extra coworker pytest tests/test_cohort_health_gate.py -k reviewed_skill_rollback -q` and all three required exact-head CI jobs with review findings resolved.

---

## CW-11 old-worker fence merged; cohort metric and rollout contract follow-up — 16 October 2026

**Current merged implementation baseline:** `main` `d757d165bbb36eaea829b683714f03b37d7206d9`, externally merged [PR #435](https://github.com/rumman52/Shuddho/pull/435) at last observed PR head `62665ecedeae26b4d1e7a541b41601dac1070fc9`. The merged patch gives *newly admitted* reviewed research Tasks distinct `work_research_reviewed_v1` workflow identity, which older `work_research_v1` workers fail to resolve and whose old paid-search reservation rejects. Current worker/runner maps this reviewed workflow to the existing source-reviewed WorkSkill; SQL pinned Step, grants and exact sources are still rechecked. Terminal reviewed Task idempotent replay is retained. No capability activation, external sends, or deployment is established.

**Evidence:** Last observed exact-head [PR #435 CI #38911379269](https://github.com/rumman52/Shuddho/actions/runs/38911379269): `test-and-build` passed, mandatory `coworker` in progress, dependent merge gate pending. Merged-main [CI #38911480448](https://github.com/rumman52/Shuddho/actions/runs/38911480448) also pending. The first independent review recorded P1 older-worker downgrade and P2 terminal replay; amended source addresses new Tasks and terminal replay, but the final re-review attempt failed to produce clean clearance and threads remained unresolved at observation. Do not treat merge as security qualification.

**Follow-up review branch:** `codex/cw11-reviewed-rollout-evidence-followup-20261016` updates the canonical rollback contract for the distinct task workflow and modifies `scripts/cohort_health_gate.py` to include `work_research_reviewed_v1` failures and samples in release stop-gate metrics. Adds a synthetic-cohort regression proving a failed reviewed Task raises the research failure rate and STOP_ROLLOUT. This evidence slice awaits final-HEAD mandatory CI and independent review and is **not merged**.

**Outstanding P1 rollout boundary:** Already admitted research Tasks from merged #434 may retain **legacy** `work_research_v1` with `reviewed_skill_identity`. An actually older worker ignoring that Step could still execute it after flag rollback. The new version fence protects **new** admissions, not historical in-flight ones. Block mixed-version activation until old workers are drained and a controlled, owned existing-task inventory/backfill/recovery plan is operated and verified with PostgreSQL, Temporal, and real provider-dispatch boundaries. Never silently retype a running task or declare old-worker coexistence safe. Trusted skill publication, version/revision rollback, CW-09/CW-10 operated isolation, P-01/P-03 scenarios and V staging/production qualification remain separate unmet gates.

**Next:** Inspect exact merged-main and follow-up PR CI; finish independent security review with old-worker/historical Task risk explicitly scoped. Prove a safe staged upgrade/drain/backfill and mixed-version compatibility contract before activating reviewed research. No automatic merge, deploy or activation.

---

## CW-11 persisted reviewed-skill rollback guard — 16 October 2026

**Refreshed baseline:** `main` `c4d047dc9ede00b3caac81239621f3dcca28d6ab` includes externally merged [PR #434](https://github.com/rumman52/Shuddho/pull/434), exact final PR head `c03406e5d84a5f3af500fa3a59556ecbf5d9ed0d`. Matching [PR-head mandatory CI #38904915894](https://github.com/rumman52/Shuddho/actions/runs/38904915894) passed `test-and-build`, `coworker` and `ci-merge-gate`. Merged-main [CI #38908427544](https://github.com/rumman52/Shuddho/actions/runs/38908427544) was **running** at first refresh. The original three P1 review threads on #434 remain **unresolved**, and repeat Codex reviews failed operationally; source/CI success is not independent security review clearance. Older #434 unmerged/pending status immediately below is historical.

**Next safety slice on isolated review branch:** `codex/cw11-reviewed-skill-rollback-boundary-20261016`. The merged reviewed research pilot persisted a Task-scoped reviewed manifest digest, but its worker read, Task replay and search credit reservation were gated solely by the live `SHUDDHO_AGENT_REVIEWED_RESEARCH_SKILL_ENABLED` flag. Disabling this flag post-admission could silently demote pinned Tasks to the unreviewed legacy path. New code independently checks the existing `reviewed_skill_identity` Step even when the flag is off, denying previously pinned Tasks at all three boundaries without new provider work. A synthetic SQL regression checks same Task across disable and re-enable, no search reservation after disable, and standalone legacy compatibility. [Task contract](CW11_REVIEWED_SKILL_FLAG_ROLLBACK_GUARD_2026-10-16.md).

**Evidence state:** Committed source/regression and task contract; exact final-head CI/reviewer evidence **not yet confirmed** at this checkpoint. This closes neither true mixed-version rollout safety (older workers remain unsafe) nor trusted publication/version selection/rollback, operated worker/PG/Temporal staging, or A/P/V full acceptance. Code is default-off; no merge/deploy/provider send/activation performed here.

**Next:** Inspect final-head mandatory CI and independent review; fix any failed denial/cleanup assertions; maintain old-worker downgrade as a rollout blocker. Then move to trusted reviewed skill publication/selection and operated version-replay acceptance.

---

## CW-11 / C-05 reviewed research worker binding — 16 October 2026

**Live baseline:** `main` `d4fccefdced8a68e8fb839525141d9796a6f4dac`. [PR #433](https://github.com/rumman52/Shuddho/pull/433) was merged externally; exact [PR-head CI #38877447028](https://github.com/rumman52/Shuddho/actions/runs/38877447028) passed `test-and-build`, `coworker` and `ci-merge-gate`; Codex review completed with no findings. Earlier checkpoint calling #433 open and pending is now historical.

**Separate unmerged implementation:** `codex/cw11-reviewed-research-worker-binding-20261016`, a bounded *default-off* Agent-owned `research.search` pilot. Existing inert reviewed `CoworkerSkillManifest` is now consumed at SQL-backed task creation, worker phase read and paid research reservation, checking exact owner/run/step/tool, pinned Task workflow/ToolSpec and newly persisted Task review SHA identity, explicit durable run grant, exact query/inputs, immutable selected DocumentVersion subset of the owning AgentRun, one-call ceiling, cancellation and live manifest/source policy. The parent AgentRun lock serializes a revocation against the search credit reservation. Standalone research remains unchanged; no new provider authority, runtime skill publishing, migration, action ledger or production rollout. Adds SQL regression tests including denial of grants/versions/owner/inputs and review drift. Independent Codex review of initial SHA `a263313` raised three P1 findings: public key replay collision, unexpired-state vs actual run deadline, and stale grant before research dispatch. Follow-up commits now check owner/run/step on replay with fresh reviewed validation, reject past-deadline runs, gate the credit reservation under AgentRun/Task locks, and recheck before provider invocation with a zero-credit settlement on denial. **The fixes still require exact-head CI and fresh independent re-review; original threads remain open.** [Task contract](CW11_REVIEWED_RESEARCH_WORKER_BINDING_2026-10-16.md).

**Evidence:** Source/tests committed to review branch; focused local checks and exact final-HEAD CI are **not yet confirmed** at this checkpoint. Independent review and operated PG/Temporal/staging remain pending. This is a real but incomplete step toward C-05, **not reviewed skill publication/rollback or production qualification**.

**Next:** Open/review independent draft PR; inspect final-head `test-and-build`, mandatory no-skip `coworker`, `ci-merge-gate`; fix actual failures and review findings. Then implement trusted publication/version rollback and later operated worker proof. No merge, deploy, model/provider spend or activation.

---

## CW-11 restricted planner attached-action review repair — 16 October 2026

**Live baseline:** `main` `41f457b04f2b1e466cbaafd7bbfff04cc5993186` includes merged [PR #432](https://github.com/rumman52/Shuddho/pull/432). Its exact-head [CI #38861042441](https://github.com/rumman52/Shuddho/actions/runs/38861042441) passed `test-and-build`, `coworker` and `ci-merge-gate`. Merged-main [CI #38876797929](https://github.com/rumman52/Shuddho/actions/runs/38876797929) was still in progress at this checkpoint. [Codex review thread on #432](https://github.com/rumman52/Shuddho/pull/432#discussion_r4291573554) identified an unresolved authorized-attached-action regression despite green CI.

**Review branch:** `codex/cw11-attached-action-scope-repair-20261016`. Ordinary tool suggestions remain filtered by the persisted run grant, but independently run-bound pending `attached.*` handles are no longer removed whenever that grant is nonempty. Added synthetic/SQL-backed action selection, opaque-handle, selected-vs-unselected release, and replan-after-renumbering regression assertions in `tests/test_coworker.py`. No additional provider authority, release flag, production operation or schema change. [Task contract](CW11_ATTACHED_ACTION_SCOPE_REPAIR_2026-10-16.md).

**Evidence:** Source and tests committed on dedicated branch; focused command and exact *final branch-head* required CI **not yet observed passing** when this checkpoint was written. Review feedback needs re-verification against the new diff. **Implemented on review branch; repository verification pending; staging, production qualification and activation not established.**

**Next:** Review the focused test and final-head `test-and-build`, `coworker`, `ci-merge-gate` results; repair failures rather than muting the check. Then proceed to CW-11 reviewed, grant/version-bound skill publication and rollback, with separate real worker/browser, cross-purpose and staging acceptance gates. No merge, deploy, activation, or external action authorized.

---

## CW-11 post-merge planner and fallback tool scope — 16 October 2026

**Live source:** [PR #431](https://github.com/rumman52/Shuddho/pull/431) merged at `main` `18068a48aae1dcd3f354638e525cdd2cf88fc185` (16 October 2026). Its earlier exact PR head was `b062f487ba2aa0de11fb367424c70d9eb9ce01cc`. Merged-main `CI #38860546551` was in progress at this review. Historical branch/open notes below predate the merge.

**Independent continuation branch:** `codex/cw11-planner-scope-continuation-20261016`. The merged worker-admission guard is insufficient alone: the initial intelligent planner and replan offered tool names without filtering the run's durable `tool_allowlist`; deterministic fallback and model proposal conversion also omitted it. This branch passes the persisted scope through all these routes and adds real repository regressions for restricted initial plan, replan, fallback and no-eligible-tool denial. The follow-up diff is **not merged** and neither exact final CI nor staging evidence is claimed. No model can grant extra tools via this change.

**Next:** create/review separate draft PR, inspect exact-head CI, resolve test/review findings and keep capability gates disabled. Full CW-11 reviewed skill publication and runtime version selection, CW-10 real worker isolation, CW-09 browser network proof, and broader A/P/V scenarios remain independently incomplete. [Acceptance details](CW11_RUNTIME_TASK_SCOPE_HARDENING_2026-10-16.md).

---

## CW-11 / A-04 restricted-run task scope at worker claim — 16 October 2026

**Refreshed default branch:** `main` `9b9e23a182ec212ce7f30e87d7a235ba886c2f5f`, with #430 merged and exact merged-main CI #38858449740 still in progress at first inspection; no open PRs were observed. Older 15 October recovery-claim CI checkpoint is superseded.

**New bounded security slice:** `codex/cw11-task-run-scope-claim-20261016` prevents any tool outside a stored nonempty Agent run `tool_allowlist` from being admitted by `save_plan`, `replace_remaining_plan` or `AgentRuntime.execute_step`. Additionally, initial intelligent planning, replanning and deterministic fallback now consume the exact stored scope so an unauthorized tool is not offered to the model and a valid restricted fallback can complete. All non-approved-action tools (including browser/sandbox) are restricted by this field; attached consequential actions retain their existing ExternalAction approval checks. Targeted SQL repository tests reject task/browser admission, simulate an altered persisted browser invocation and check no new Task/session is created; a separate regression covers initial model tool enumeration, replan and constrained fallback.

**Evidence state:** changes committed on a review branch; targeted test, exact-final-HEAD mandatory CI, independent review, PostgreSQL/Temporal racing worker replay and staging were **not yet verified** at checkpoint drafting. This narrows the authority gap but **does not** complete CW-11 publication or activation, CW-10 operated sandbox, CW-09 browser, A/P/V qualification. [Task acceptance](CW11_RUNTIME_TASK_SCOPE_HARDENING_2026-10-16.md).

**Next:** open review PR, inspect required final-head CI and review, fix failures without weakening scope. After review, implement independently version-pinned approved skill publication and runtime grants; no automatic merge, deployment or activation.

---

## CW-10 generated model source → worker revocation integration regression — 16 October 2026

**Verified baseline:** `main` `4b456bf41ad324d79e142c3dd39e4a49e9e2a612` contains merged #429 bounded owner DeepSeek model drafts. Its exact-head [PR CI #38852014466](https://github.com/rumman52/Shuddho/actions/runs/38852014466) and merged-main [CI #38852778094](https://github.com/rumman52/Shuddho/actions/runs/38852778094) passed all three required jobs; no open PRs at task selection.

**New test-only work:** isolated branch `codex/cw10-model-review-worker-revocation-e2e-20261016` adds full bounded synthetic acceptance from mocked DeepSeek output to authenticated model draft, immutable owner review SHA, atomic single sandbox dispatch, one authorized worker claim, and success/retry identity, plus an adversarial revocation *after claim*. The latter drives real owner revoke and SQL `worker_control` through the actual `scripts/sandbox_worker.py::execute_claim` loop, using simulated `Popen`. It asserts process kill request, refusal to send completion, destruction of temporary Python source paths, cleared SQL proposal and execution source, revoked lease and blocked late result/retry. [Acceptance and environment limits](CW10_GENERATED_WORKER_REVOCATION_E2E_2026-10-16.md).

**Verification:** tests and contract committed but final-head no-skip `test-and-build`, `coworker`, `ci-merge-gate` are pending. The process is synthetic, not operated `bwrap`; real kernel no-egress, PostgreSQL concurrent retries, Temporal restart, actual OS kill, in-memory wipe, real model/provider quality and independent security reviewer remain unverified. No product authority or deployment settings change; CW-10 remains **default-off, INCOMPLETE**.

**Next:** address CI errors on exact final branch SHA; then operated reviewed-source real bubblewrap/PG kill + cleanup, and CW-11 reviewed skills / CW-09 browser / P/V coworker scenario obligations.

---

## CW-10 owner-invoked model Python producer — 16 October 2026

**Source truth at task start:** `main` `08512aba78d5446c8115adbeafeded8a9e4f33cd` includes merged [PR #428](https://github.com/rumman52/Shuddho/pull/428). Its exact final-head [CI #38848800194](https://github.com/rumman52/Shuddho/actions/runs/38848800194) passed `test-and-build`, `coworker`, `ci-merge-gate`. New merged-main CI #38850518005 was in progress at start. No open PRs.

**First dependency-ready gap C-04:** An authenticated owner could inspect/approve manually submitted Python but could not request an actually model-generated source draft. The new branch `codex/cw10-owner-model-code-producer-20261016` adds an independent default-off `SHUDDHO_MODEL_CODE_PROPOSALS_ENABLED` flag; an explicit owner-only model-draft API and Agent review UI button; strict DeepSeek JSON→validated Python with no tool or execution grant; pre-provider owner/private-context checks, ordinary planner reservation/settlement, and immutable SHA-bound post-inference code proposal persistence. Exact-key replays return stored source without another model call; cancellation between inference and persistence fails closed. No private-input mounts, network or destinations. User-supplied HTTP proposals cannot forge the reserved model-origin idempotency namespace. [Detailed contract](CW10_MODEL_CODE_DRAFT_PRODUCER_2026-10-16.md).

**New tests:** disabled-before-provider, no cross-account or selected private-source generation, one-key replay, no sandbox execution, cancellation during inference, invalid provider output, provenance spoof rejection, typed frontend direct request without execution paths. **Not verified until exact final-head CI passes.** The provider is mocked in CI, no real paid DeepSeek performance or operated deployment proof. No merge, deploy or activation.

**Next:** confirm mandatory `test-and-build`, `coworker`, `ci-merge-gate` on final SHA and repair red checks. Then qualify human-approved model source → sandbox worker in synthetic PostgreSQL concurrency/real bwrap/revocation/crash experiments, in-flight filesystem erasure, and durable recovery. CW-11 reviewed skills, CW-09 operated browser and P/V scenarios remain separate. **INCOMPLETE**.

---

## CW-10 atomic reviewed-owner dispatch — 16 October 2026

**Verified starting state:** `main` `8d9420e5ebc38e7c188dc8bf1e4cb19873190a90`; merged #427 added exact owner Python review UI. Its [PR CI #38845738704](https://github.com/rumman52/Shuddho/actions/runs/38845738704) and merged-main [CI #38845856137](https://github.com/rumman52/Shuddho/actions/runs/38845856137) both passed all three required jobs. No open PRs before this branch.

**New source changes** on `codex/cw10-reviewed-dispatch-atomic-20261016`: independent default-off `SHUDDHO_CODE_PROPOSAL_DISPATCH_ENABLED`; authenticated exact-hash dispatch endpoint; `SandboxRepository.dispatch_reviewed_proposal` locks owner run → stored proposal → owner human approval, verifies admitted source, live expiry/permission/cancellation/limits, rejects unsupported private inputs, and creates one new session and its proposal-FK-linked prepared execution in one SQL transaction. Unique FK and run lock give duplicate POST one durable identity. Worker claim uses the same source/review guard and denies linked claims if the new gate is disabled. Added HTTP and worker negative/replay regressions. Existing direct-user sandbox path is unchanged, generated-code UI still has no execution control. [Detailed contract and rollout blockers](CW10_ATOMIC_REVIEWED_DISPATCH_2026-10-16.md).

**Evidence required:** final-head mandatory `test-and-build`/`coworker`/`ci-merge-gate`, independent security review, operated PostgreSQL concurrency/worker revocation/staging bwrap isolation. **Source erasure improvement:** queued reviewed execution stores a source reference, not a duplicate Python snapshot; revocation clears the original proposal snapshot before claim, and claim fails closed. Still unverified: source already released to worker memory, process cancellation latency, temporary file erasure, old legacy manually linked rows and operated isolation. Old workers do not know this gate: mixed-version dispatch forbidden. No deployment/activation or production qualification.

**Next:** prove actual worker process cancellation and in-memory/filesystem erasure after revocation; implement trusted model code proposal producer and qualify live full end-to-end CW-10 lifecycle. CW-11 skills, CW-09 operated browser and P/V coworker scenarios remain incomplete. Overall **INCOMPLETE**.

---

## CW-10 exact owner code inspection UI — 16 October 2026

**Current baseline:** `main` `d9d664c8b5a735260a17c1af58687e14e2b8c058` contains merged [PR #426](https://github.com/rumman52/Shuddho/pull/426), whose exact-head [CI #38843127126](https://github.com/rumman52/Shuddho/actions/runs/38843127126) passed all three mandatory jobs. The subsequent `main` push [CI #38844772799](https://github.com/rumman52/Shuddho/actions/runs/38844772799) was still in progress at task selection. No open PRs at bootstrap.

**First unresolved C-04 user-facing path:** Inert code proposals and owner human decisions exist in SQL, with secure claim checks behind default-off flags, but the actual coworker UI could neither discover nor inspect the full source/limits/destinations before review. Branch `codex/cw10-owner-code-inspection-20261016` adds a bounded, authenticated and no-store metadata-only code proposal list revalidated against live run/context scope, a typed exact owner review client, and a run-keyed React inspection panel displaying untrusted full source, digest, input SHA, compute limits, no egress and expiry. A checkbox confirms actual inspection before the existing exact-hash human decision. Reject/revoke erase the private bytes; owner review never creates a sandbox execution or grants credentials. Tests cover no-source metadata, cross-owner denial, stale/tampered/revoked source, typed exact API transport and absent execution path. [Acceptance contract](CW10_OWNER_CODE_REVIEW_UI_2026-10-16.md).

**Evidence:** Code and tests committed on review branch. This slice is not qualified until final HEAD `test-and-build` (including UI tests), zero-skip `coworker`, and `ci-merge-gate` pass. Browser rendering, staging and independent security review unverified. **No merge, deploy or activation.**

**Next:** trusted model-generated code proposal producer and explicit secure owner notification; then atomic server-side binding/dispatch of exactly one reviewed proposal into SQL-owned sandbox execution, with mixed-version worker safety and operated bubblewrap/PG/Temporal recovery. CW-11 skills and operated CW-09/P/V remain separate.

---

## Mandatory CI recovery — Alembic 0058 SQLite FK compatibility — 16 October 2026

**Current mainline truth:** `main` `e495a202720de658ef98cf55a21f3032ef4f1f12` has merged [PR #425](https://github.com/rumman52/Shuddho/pull/425), but **its final-head [PR CI #38838451837](https://github.com/rumman52/Shuddho/actions/runs/38838451837) and merged-main [CI #38842070652](https://github.com/rumman52/Shuddho/actions/runs/38842070652) both failed** mandatory `coworker` while `test-and-build` passed. Inspect log `coworker` step "Run mandatory transaction safety regressions without skips": seven transaction regression fixtures could not migrate new SQLite databases. The blocking traceback is `services/coworker/migrations/versions/0058_sandbox_code_proposal_binding.py:16`, `NotImplementedError: No support for ALTER of constraints in SQLite dialect` when adding the new `agent_code_proposal_id` foreign key. This is a failed **migration setup**, not a demonstrated transaction invariant failure. The merge did not satisfy the required final-head acceptance gate.

**Isolated CI safety repair:** branch `codex/cw10-0058-sqlite-fk-migration-ci-20261016` forked from exact main `e495a202720de658ef98cf55a21f3032ef4f1f12`. Migration 0058 now uses `op.batch_alter_table` for FK column addition and downgrade, following existing portable migration patterns 0032/0039; the original PostgreSQL non-null-safe nullable FK and **unique non-null index are retained**. Dedicated regression inspects SQLite migration metadata to require actual FK to `cw_agent_code_proposals.id` and unique claim origin index; transaction mandatory regressions are not skipped or weakened.

**Evidence pending:** Exact final repair-branch SHA `test-and-build`, no-skip `coworker` including transaction safety suite and PostgreSQL/Temporal, and `ci-merge-gate` must pass. Independent review and operated staging remain unproven. Keep draft. **No merge/deploy/activation authorized.**

**Next once green:** Continue CW-10 trusted generated-code producer + owner review UI and safe server dispatch, without allowing a model to self-grant authority; require real worker isolation/restart evidence. CW-11 reviewed skill activation and browser/P/V scenarios remain independently incomplete.

---

## CW-10 reviewed generated-code worker-claim guard — 16 October 2026

**Refreshed truth:** `main` `35287ac3ab0e2c691d76b2a1973166342c5ccf06`; [PR #424](https://github.com/rumman52/Shuddho/pull/424) merged at this SHA and its exact-head [PR CI #38792431386](https://github.com/rumman52/Shuddho/actions/runs/38792431386) passed. Merged-main [CI #38837201149](https://github.com/rumman52/Shuddho/actions/runs/38837201149) was still in progress when the branch was opened. No open PRs at that initial refresh. The original document's old red CI and earlier draft reviews have since been superseded by merged fixes.

**Missing real authority boundary:** The sandbox worker's claim/heartbeat/result path currently guards source integrity, lease and environment but never binds a model-generated proposal to its recorded owner decision. An `approve` record is inert; treating it as sufficient would bypass current source scope, budgets and revocation. This independent branch `codex/cw10-reviewed-sandbox-claim-guard-20261016` starts from the exact `main` above and adds nullable SQL-owned `agent_code_proposal_id` FK via migration `0058`. The current direct-user Python execution API never sets it.

**Implemented on review branch:** Source-origin-bound reviewer validation at claim, heartbeat and receipt acceptance. Under SQL locks, only an exact owned unexpired/unrevoked approved proposal with current live run+conversation/source permissions, hash and reviewed limits may release bytes or settle; all unsafe claims fail closed and scrub source. Private input versions are explicitly denied pending an operated reviewed input-mount path. Changed reviewer/submitted hash, source tampering, revoked/expired consent, cancelled run and excess resource ceilings are tested; direct-user executions are unaffected. [Acceptance/rollout contract](CW10_SANDBOX_REVIEW_CLAIM_GUARD_2026-10-16.md).

**Evidence:** Source and synthetic tests committed, required final-head no-skip `test-and-build`/`coworker`/`ci-merge-gate` still pending; real PostgreSQL migration test added. No independent security review or operated staging worker process evidence. Do not merge, deploy, or activate.

**Remaining:** CW-10 trusted model proposal producer and trusted owner-review UI; atomic privileged server-side producer/dispatch path that sets proposal binding; reviewed private-input mounts and isolation/rollback; CW-11 skill publication; operated CW-09 browser network security; P/V goal/work/recovery/security scenarios. Core/architecture qualification remains **INCOMPLETE**.

---

## CW-10 exact owner human review decision, no worker authority — 16 October 2026

**Fresh repo:** `main` `a8b60903268f4be4655fd8191305bc35c739a9bd`; [PR #423](https://github.com/rumman52/Shuddho/pull/423) has merged private code revocation/expiry/account erasure, but its exact-head [PR CI #38789767003](https://github.com/rumman52/Shuddho/actions/runs/38789767003) and merged-main [CI #38790723827](https://github.com/rumman52/Shuddho/actions/runs/38790723827) were **still running**, and therefore not qualified at this initial inspection. Older green jobs do not close the new revision. No other open PR was present.

**New C-04 review-only slice:** `codex/cw10-exact-human-review-decision-20261016` based on this exact main. New additive migration `0057` stores one `AgentCodeReview` per private proposal (owner/run/whole-envelope hash, approve/reject, server decision time, bounded owner expiry, revocation). Owner-authenticated `POST .../code-proposals/{proposal_id}/review` checks exact hash, original selected owned scope, active runtime-v3 run and current limits for an approve; rejection scrubs source. Concurrent approval/revocation use shared run+row lock and one-decision PK. Replay of identical decisions is stable, changed decisions conflict. Existing revocation, expired maintenance and account deletion now handle review records. No schema/runtime activation or worker code-execution permission, with `execution_authorized=false` and `code_executed=false` in all review responses. New API/DB and PostgreSQL FK tests provided. [Acceptance contract](CW10_HUMAN_REVIEW_DECISION_2026-10-16.md).

**Verification status:** Source committed on review branch, exact final-head mandatory `test-and-build`/`coworker`/`ci-merge-gate` still required; independent review and operated worker/staging unverified. Do not merge, deploy or activate.

**Next:** Finish trusted model-generated proposal producer and inspected owner UI, then a **separate** security slice atomically validates this reviewed identity against source/input/limits/run/worker lease at sandbox claim. Unconsumed human decision is not execution authority. CW-11 reviewed skills, operated browser isolation and P/V realistic scenarios remain incomplete.

---

## CW-10 inert proposal owner revocation and private source retention — 16 October 2026

**Repo truth:** `main` `0c292f635cc27515c12a5ae0158dc8db3c222c1f`, merged [PR #420](https://github.com/rumman52/Shuddho/pull/420) (inert proposal persistence), [PR #421](https://github.com/rumman52/Shuddho/pull/421) (admitted conversation source scope), and [PR #422](https://github.com/rumman52/Shuddho/pull/422) (real direct-chat test). These are already merged, not unfinished tasks. Main push [CI #38788446857](https://github.com/rumman52/Shuddho/actions/runs/38788446857) was in progress when this new branch was created.

**Safety/data-integrity gap:** `AgentCodeProposal.snapshot` retains untrusted private Python indefinitely after proposal expiry, has no owner revocation path, and `RetentionService.erase_account` did not remove proposal rows before the parent AgentRun. The latter violates the schema's foreign key and blocks full account erasure with code proposals present. No generated-code execution authority exists yet.

**Isolated implementation:** branch `codex/cw10-proposal-revocation-erasure-20261016` forked from that exact main. New owner-authenticated exact-review-hash `POST .../code-proposals/{proposal_id}/revoke` atomically scrubs source and leaves a non-executing tombstone; repeat revocations are idempotent, cross-owner/wrong hash fail closed, and GET/POST replay cannot disclose/resurrect erased code. Bounded expiry retention is wired into the existing five-minute worker maintenance pass. Account erasure now removes proposals before runs. Regression tests cover wrong owner/hash/run, cancelled run, expiry, idempotency and account FK deletion. No new permissions, model decisions, approval fields, schema migration or sandbox execution. [Task contract](CW10_PROPOSAL_REVOCATION_ERASURE_2026-10-16.md).

**Evidence:** Code and tests committed, final-head `test-and-build`, mandatory no-skip `coworker`, `ci-merge-gate` and independent review pending at this checkpoint. No direct local PostgreSQL/Temporal or operated worker/staging evidence. Keep default-off, draft and do not auto-merge/activate.

**Next:** Obtain exact-HEAD CI and independent security/retention review. Then complete trusted model proposal admission, explicit human decision with expiry/revocation and atomic worker-claim validation. CW-11 reviewed skill publication and remaining operated CW-09/P/V scenarios remain independently incomplete.

---

## CW-10 conversation-bound code proposal scope — 16 October 2026 (Asia/Dhaka)

**Refreshed main:** `badc8bbb66c8ead4a43c3463e32112b1bfd7e996`, merged [PR #420](https://github.com/rumman52/Shuddho/pull/420). Exact #420 PR head `f1ddb5d45c0b62f70f95c84db00374541621f420` passed required `test-and-build`, `coworker`, and `ci-merge-gate` in [CI #38780057144](https://github.com/rumman52/Shuddho/actions/runs/38780057144). Main push [CI #38783568443](https://github.com/rumman52/Shuddho/actions/runs/38783568443) was still running at this bootstrap. No open PRs were returned. The older document's `baa484e` red recovery-claim checkpoint is historical; do not repeat its repair.

**Bounded safety defect and fix:** Code-proposal creation/replay/GET checked current document rows but omitted CW-08's original conversation message/source/run validation. A same-ID document version change, removed source selection/run link, unavailable conversation or moved message still returned private source/accepted new snapshots. A new proposal could adopt substituted live source hashes. Reuse `require_admitted_conversation_run_sources` in the existing shared `_verify_code_proposal` path, preserving non-conversation semantics. This is an inert proposal scope correction, with no new authority or schema.

**Branch/contract:** `codex/cw10-conversation-proposal-scope-20261016`; [task contract](CW10_CONVERSATION_PROPOSAL_SCOPE_2026-10-16.md). Baseline focused suite **29 passed**. Final failing-first matrix **16 failed for successful HTTP 201/200 instead of 409** before the repair. An initial broader run had three invalid composite-owner fixture mutations; the fixture now moves the message and owner together into a real foreign conversation, preserving database constraints, and all sixteen were rerun against the pre-fix code. JavaScript tests and workspace build passed. Affected proposal/conversation/sandbox suite **164 passed, zero skips**, with six pre-existing adversarial-model Pydantic serializer warnings (63.00s). Full Python and exact new PR-head CI pending at this checkpoint.

**Evidence/authority:** Source repair local, remote review pending; required exact-head mandatory CI, independent security review, staged PostgreSQL/Temporal/sandbox and production qualification are not inferred. Flags remain unchanged/default-off. No deployment, merge, human approval, code execution or external transaction was performed. Review is a local second pass, not independent.

**Remaining work:** C-04's model-authored proposal admission/trusted review UI, persisted exact owner decision with expiry/revocation, and atomic approved sandbox claim remain incomplete; retain that dependent lifecycle as the next engineering task after this scope repair is reviewed/integrated. CW-11 trusted skill publication and operated C-02/P/V scenarios remain independent. Missing staging identity/credentials, real sandbox/container services and human quality/security evidence are external blockers, not completed checks. Current local environment has neither PostgreSQL nor Docker executable; mandatory remote CI must supply their required evidence.

---

## CW-10 proposal persistence CI repair and mainline integration — 15 October 2026

**Fresh main:** `be78fe057bce6d6d09271d1e0fb135b4b422bd74`; [PR #418](https://github.com/rumman52/Shuddho/pull/418) merged after final PR-head [CI #38775100942](https://github.com/rumman52/Shuddho/actions/runs/38775100942) passed `test-and-build`, mandatory `coworker` and `ci-merge-gate`. The original [PR #419](https://github.com/rumman52/Shuddho/pull/419) was not mergeable after #418 and [CI #38777496427](https://github.com/rumman52/Shuddho/actions/runs/38777496427) failed seven stored-code-proposal assertions, leaving mandatory `coworker` and merge gate red; `test-and-build` passed.

**Cause, repair, new branch:** The strict immutable reviewer accepts standard `datetime.timezone`/`ZoneInfo` values but API/JSON Pydantic parsing generates `pydantic_core.TzInfo`. Valid code proposals were rejected as `code_proposal_invalid`. A narrow `canonicalize_transport_code_proposal` converts this exact trusted parser timezone to a standard immutable timezone before **unchanged** review validation for POST, replay and stored GET. The normalization preserves JSON review identity, malicious extra fields and validator rejection; focused Pydantic-only local reproduction confirmed parser types and copied-field preservation. The replacement branch `codex/cw10-proposal-persistence-ci-repair-main-20261015` ports the entire owner-scoped inert proposal model, additive migration `0056`, API, PostgreSQL race tests, no-skip CI and all regressions onto the merged mainline. No human approval or worker-execution grant exists.

**Evidence:** Source patches and tests committed, but required exact-head `test-and-build`, `coworker`, `ci-merge-gate`, independent security/migration review and operated sandbox proof remain **unverified**. Full local repo tests unavailable because local GitHub clone/network access failed. Do not merge/deploy/activate. Next C-04: persist owner approval with expiry/revocation and enforce exact source/input/limits binding atomically at sandbox claim; CW-11 and P/V scenarios remain independent.

---

## CW-10 fail-closed sandbox heartbeat — actual mainline integration — 15 October 2026

**Fresh repo truth:** `main` `ce76803eb20e8383bb507f02e2cad17d9ff77d3f` contains [PR #416](https://github.com/rumman52/Shuddho/pull/416), whose exact [PR CI #38770425863](https://github.com/rumman52/Shuddho/actions/runs/38770425863) passed all three mandatory jobs. [PR #417](https://github.com/rumman52/Shuddho/pull/417) was marked merged into the earlier review branch, not `main`, and `main:scripts/sandbox_worker.py` still had the unguarded worker heartbeat behavior. #417's own earlier CI cannot qualify a new mainline integration.

**Source repair branch:** `codex/cw10-sandbox-heartbeat-mainline-20261015` created from that exact `main`. Ports the previously reviewed bounded `scripts/sandbox_worker.py` heartbeat fail-closed change and the associated negative/positive `tests/test_sandbox_control_plane.py` cases. Any control heartbeat error, unexpected/missing action or explicit `stop` terminates the subprocess; only explicit `continue` allows it to proceed. Keep default-off sandbox and deny model-created authorization. [Integration contract](CW10_SANDBOX_HEARTBEAT_MAINLINE_INTEGRATION_2026-10-15.md).

**Verification:** GitHub source commits recorded; exact final-head `test-and-build`, `coworker`, `ci-merge-gate` pending until this review branch CI runs. No independently operated bubblewrap process-kill proof, staging or release evidence. Do not conflate existing tests with real network/worker operation or mark C-04 complete.

**Next:** Review and qualify this **main-targeting** PR on final SHA, without auto-merging; then implement immutable model-generated proposal+owner decision+atomic claim approval under C-04. CW-09 operated browser/DNS/SSRF, CW-11 skill publisher, P-series coworker scenarios and V-series release checks remain independent blockers.

---

## CW-10 source-integrity recovery worker-control CI contract repair — 15 October 2026

**Refreshed main:** `baa484ef861e41daf7653a29f6aaa07720932055`, merged [PR #415](https://github.com/rumman52/Shuddho/pull/415); [main CI #38760717140](https://github.com/rumman52/Shuddho/actions/runs/38760717140) `test-and-build` successful, `coworker` failed eight stale-claim assertions (1,375 other tests passed in that invocation), `ci-merge-gate` failed. No open PRs at bootstrap. The integrity denial, terminal failure, source scrub and lease revocation assertions all passed; the outdated expectation that `worker_control` **raises** disagreed with the newer explicit `stop/session_closed` terminal protocol.

**Isolated review branch:** `codex/cw10-recovery-claim-stop-ci-repair-20261015`. Test-only repair keeps all 16 initial/recovery tamper cases, asserts worker receives `stop/session_closed`, then submits a stale success receipt to the real completion boundary and verifies typed rejection with no change to durable integrity failure, session terminal state or source/lease cleanup. Production code unchanged. [Task contract](CW10_RECOVERY_CLAIM_STOP_CONTRACT_2026-10-15.md). **Exact branch-head mandatory CI pending; no independent security review, operated sandbox/network proof, staging or activation.**

**Next:** Obtain exact-head `test-and-build`, `coworker` and `ci-merge-gate` on the draft PR; inspect no-skip sandbox/PG/Temporal/browser/transaction checks and review. Do not merge or activate automatically. Continue missing immutable model-generated proposal, human owner approval with expiry/revocation and atomic sandbox claim gate (C-04), followed by reviewed skill publication (CW-11) and operated coworker scenarios.

---

## CW-10 terminal-session worker authority guard — 15 October 2026

**Latest repository baseline:** `main` `4015dc9fc30525b2344f522d5e0b195ed5d35fd3`, merged [PR #414](https://github.com/rumman52/Shuddho/pull/414) at 2026-10-15 14:36 UTC. PR-head `test-and-build` passed, but mandatory `coworker` and new main CI were still in progress at initial refresh. No submitted independent PR #414 review was found. The merge does not establish full operated safety.

**Additional same-batch finding:** Claim rows are selected as a batch before the loop. After one corrupted job fails the owning session, an already-selected sibling could previously reset that session to `running` and still receive source. The same PR now rechecks terminal state for every selected claim row, fails/scrubs ineligible siblings and includes a batch regression. Unselected abandoned jobs still need general retention/reconciliation review.\n\n**New source-level CW-10 safety finding:** A first execution can remain leased after a *sibling* source-integrity failure makes the owning sandbox session `failed`. The real worker heartbeat and completion paths previously checked cancellation or wall-clock expiry only. With no cancel flag and future expiry, stale worker execution and result acceptance could continue under a failed session.

**Isolated implementation:** `codex/cw10-terminal-session-worker-guards-20261015` hardens `SandboxRepository.worker_control` and `complete_execution` to reject **all terminal session states**, with durable scrub/lease cleanup and no altered happy path. Parameterized SQLite real-worker regression and PostgreSQL persistence regression added. [Task contract](CW10_TERMINAL_SESSION_WORKER_GUARD_2026-10-15.md). **Code/tests committed; exact-head PR CI, independent security review and staging qualification pending at this checkpoint.** The model-generated code proposal/owner approval/worker claim lifecycle remains **absent**; C-04 not complete.

**Next:** Finish exact-head CI and review on the new isolated PR, preserve default-off sandbox and avoid auto-merge. Then implement reviewed generated-code proposal/approval and worker claim enforcement; qualify CW-09 live Chromium/DNS/SSRF, CW-11 reviewed skill publisher/grants and P/V operated coworker evidence separately.

---

## CW-10 late sandbox completion rollback repair — 15 October 2026

**Refreshed evidence:** `main` `9bdb73a9142bce6e9e9848373dddde44514ca144`, merged [PR #413](https://github.com/rumman52/Shuddho/pull/413), matching [CI #38746278784](https://github.com/rumman52/Shuddho/actions/runs/38746278784) passed `test-and-build`, `coworker`, `ci-merge-gate`. No open PRs at task start. Earlier CW-10 source/policy worker-claim integrity is merged and verified at repository CI level; actual model-generated proposal/approval and operated isolation remain absent.

**Defect:** A sandbox worker completion arriving after session expiry/cancellation updated terminal state, scrubbed source and revoked the lease, but raised typed `sandbox_session_closed` inside `sessions.begin()`, rolling all of that transaction back. SQLAlchemy rollback reproduced independently. This is a source-level data-integrity/race defect, not confirmed production exploitation.

**Bounded fix:** `codex/cw10-late-completion-commit-20261015` commits the persisted closed-session transition inside the existing transaction and raises 409 only afterward. Adds owner-bound audit event, SQLite regression for post-claim expiry/cancellation, no repeat claim and no accepted receipt. [Contract](CW10_LATE_SANDBOX_COMPLETION_COMMIT_2026-10-15.md). **Committed branch; final-head CI, review and staging pending** at this entry. No schema/permissions/feature activation changes.

**Next:** Open review PR; check exact-head required `test-and-build`, no-skip `coworker` and `ci-merge-gate`. Obtain review, avoid auto-merge. Then address CW-10 immutable *model-generated* proposal, human decision with expiry/revocation, atomic worker-claim recheck, and staging sandbox cleanup/isolation. Other architecture, personal context, CW-09 and CW-11 gates remain incomplete.

---

## CW-10 worker-claim source integrity at authorization boundary — 15 October 2026

**Bootstrap and dependency evidence:** `main` `e4381617fd51107b74b4aac25e76109caf1a0123`; [PR #412](https://github.com/rumman52/Shuddho/pull/412) merged the HTTPS CONNECT pending-socket cleanup after its rewritten exact-head [CI #38725411478](https://github.com/rumman52/Shuddho/actions/runs/38725411478) passed required `test-and-build`, `coworker`, and `ci-merge-gate`. [PR #411](https://github.com/rumman52/Shuddho/pull/411) exact user-code Agent replay/receipt protections were already merged. Latest post-merge main [CI #38727695049](https://github.com/rumman52/Shuddho/actions/runs/38727695049) had `test-and-build` success and `coworker` still running at refreshed checkpoint. No open PR at task bootstrap; no independent submitted security review or operated staging/production identity. Core, context and release acceptance remain incomplete.

**Selected first unblocked safety defect:** Existing `SandboxRepository.prepare_execution` records exact source UTF-8 SHA-256 and byte length. Real `SandboxRepository.claim_executions` releases `request_spec.source` to authenticated workers without verifying it still matches those fields or the originally recorded `untrusted` source/policy versions. A post-preparation mutated request spec can execute different source on initial worker claim or expired-lease re-claim, even though later Agent receipt verification would detect a mismatch. This is a source-level data-integrity defect, not evidence of live exploitation. [CW-10 worker claim contract](CW10_SANDBOX_WORKER_CLAIM_INTEGRITY_2026-10-15.md).

**Committed implementation:** Isolated branch `codex/cw10-sandbox-claim-source-integrity-20261015` from above exact `main`. Within the authoritative worker claim transaction, reject absent/nonobject/invalid-UTF8, missing, oversized, reencoded, same-length substituted or hash/byte-length different source, mismatched `source_trust` or `policy_version`, or a changed server-owned sandbox execution policy or purpose/runtime fingerprint. Instead of delivering any code, mark execution failed `sandbox_source_integrity_failed`, scrub source, clear active worker/lease, mark session failed, audit the integrity failure, and retain `cleanup_state=required` if an older worker lease was already claimed; no re-claim. No changes to model authority, sandbox network/credential policy, approval grants, schema, action ledger, environment or rollout flag. Existing correctly prepared user-authored source claim stays operational.

**Tests:** `tests/test_sandbox_control_plane.py` tests eight tamper forms on first worker claim and expired-lease recovery (16 controlled cases), verifies no code dispatched, failure/scrubbing/terminal session, no second claim and stale worker invalidation. `tests/test_coworker_postgres.py` drives actual owned PostgreSQL sandbox rows and confirms same-length altered source cannot be claimed, job is failed/scrubbed and never reclaimed. Existing mandatory `coworker` CI already includes both test modules. Code committed, **final PR-head CI not yet verified**; no local full repository execution, independent review or staged sandbox network isolation. Current branch is not merged; browser remains default off and sandbox remains gated.

**Next:** Open draft review PR, inspect final-head `test-and-build`, no-skip `coworker` (PostgreSQL/Temporal/browser/transactions/sandbox) and `ci-merge-gate`; repair failures without weaker assertions. Independently review first-claim and re-claim, cancellation/cleanup, source-hash and owner scope; stage sandbox isolation. Then deliver CW-10's separately required immutable exact **model-generated** proposal, owner human review decision/expiry/revocation, atomic approval recheck on worker claim and cleanup. CW-11 review/version/grant skill selection, personal context and full CW-09 staging remain. No auto-merge/deploy/activate.

---

## CW-09 PR #412 hotfix rebase and commit rewrite — 15 October 2026

**Observed:** `main` `fdba3a4f607184b10dacb359e980a37db5000d68` contains merged CW-10 source/receipt guards from [PR #411](https://github.com/rumman52/Shuddho/pull/411). [PR #412](https://github.com/rumman52/Shuddho/pull/412) based on older `main` passed all mandatory jobs in [run #38715542785](https://github.com/rumman52/Shuddho/actions/runs/38715542785), but could not merge after #411 changed the same canonical inventory and progress files. GitHub `mergeable_state=dirty` was a documentation conflict, not a new test failure.

**Action:** rewrite only PR #412's review-branch commit on current main using force-with-lease (no shared-main history rewrite). Preserve the exact verified prior-PR code/test contents for early inbound socket registration, deterministic disconnect/cancel tests and valid pinned hostname evidence; preserve CW-10's mainline source-binding code, its tests and complete progress history. Semantic documentation merge uses the current main file plus the original CW-09 incident checkpoint and this reconciliation record. No conflict markers, no disabled checks.

**Verification:** Previous #412 exact-head `test-and-build`, `coworker`, and `ci-merge-gate` passed but cannot qualify the rewritten SHA. All three jobs must pass on new PR head; request independent review, stage real Chromium/DNS rebinding/SSRF. Status: repository qualification pending, production not qualified, features not activated. Do not auto-merge/deploy/activate.

---

## CW-09 mandatory Node CONNECT CI hang and pending-socket cleanup — 15 October 2026

**Live repository baseline:** `main` `1a75eb2f66595ef6ec2f8ccd01156f03276c9566` ([merged PR #410](https://github.com/rumman52/Shuddho/pull/410)); no open PR at initial next-session bootstrap, then [draft PR #411](https://github.com/rumman52/Shuddho/pull/411) opened on exact sandbox source/receipt identity. Required PR #410 head [run #38711309533](https://github.com/rumman52/Shuddho/actions/runs/38711309533) and merged-main [run #38711977867](https://github.com/rumman52/Shuddho/actions/runs/38711977867) both passed `test-and-build` but spent extended time in mandatory browser Node CONNECT step without finishing `coworker` / `ci-merge-gate` at this checkpoint. In-progress job logs unavailable (`BlobNotFound`), so cannot claim green. Production not activated.

**Reproduced high-priority bug:** A reconstructed, locally executed Node test using the repo's actual proxy/test logic timed out in the first two CONNECT tests and did not exit until forcibly killed; test three could observe an outbound dial after a client closed but before the server knew, and the valid-tunnel assertion dereferenced an invalid hostname property. More importantly, the actual `createPinnedProxy` registered client sockets for `pause()/destroy()` only *after* asynchronous `network-check`, so a pending browser CONNECT was not in the cancellation cleanup set. This is a source-level pending-transport cleanup defect, not a confirmed outside-network breach. [CW-09 defect contract](CW09_PROXY_SOCKET_CI_HANG_2026-10-15.md).

**Isolated fix branch:** `codex/cw09-proxy-socket-test-hang-repair-20261015` from exact `main` baseline. Register inbound `clientSocket` and close cleanup at CONNECT admission, before DNS await; avoid double registration. Browser Node tests drain rejected responses and store bounded buffered response, assert inbound close before releasing stalled authorization, explicitly tear down the server end for disconnected-client simulation, and address `state.evidence["example.com"]` with valid literal key. An isolated Node rehearsal with equivalent actual callback + tests passed **5/5, no skipped tests, process exits**. This local rehearsal is **not** exact-head CI. Worker command/epoch and TLS/pinned DNS checks remain unchanged; no new grant/ledger/migration.

**Required next verification:** Open draft PR, run final-head mandatory `test-and-build`, `coworker` (including this Node suite, PG/Temporal/transaction and browser) and `ci-merge-gate` with no bypass. Inspect actual CI failures and review. Obtain independent security review and operated Chromium/DNS/SSRF staging separately. PR #411 CW-10 must reconcile a later merge with `main`, and remains blocked by actual CI plus human-reviewed generated-code lifecycle. **No auto-merge/deploy/activation.**


---
## CW-10 exact Agent sandbox source identity on resume — 15 October 2026

**Current truth:** `main` `1a75eb2f66595ef6ec2f8ccd01156f03276c9566`; [PR #410](https://github.com/rumman52/Shuddho/pull/410) merged the real CONNECT proxy tests, with exact PR-head [CI #38711309533](https://github.com/rumman52/Shuddho/actions/runs/38711309533) and new merged-main [CI #38711977867](https://github.com/rumman52/Shuddho/actions/runs/38711977867) showing `test-and-build` success, mandatory `coworker` still running at initial refresh. Previous PR #409 exact-head [CI #38709409366](https://github.com/rumman52/Shuddho/actions/runs/38709409366) and matching-main [CI #38709819435](https://github.com/rumman52/Shuddho/actions/runs/38709819435) had passed all three. No relevant open PRs at bootstrap; PR #410 merged externally, without this session authorizing merge. No independent submitted reviews, operated browser/staging/production evidence missing.

**Selected immediate CW-10 safety defect:** The real `sandbox.execute_python` Agent tool intentionally executes **only exact user-authored fenced code**, never generated model code. It persistently binds one sandbox session to the Agent step. On resume, the runtime simply uses `list_executions(...)[0]` and proceeds with polling/receipt settlement without checking that the existing execution's source digest and byte size match the step's current exact source. Changed/restored ToolInvocation arguments could cause mismatched output attribution. [Bounded contract](CW10_SANDBOX_AGENT_SOURCE_BINDING_2026-10-15.md).

**Committed isolated fix:** `codex/cw10-agent-sandbox-source-binding-20261015` branched from current `main`. In `services/coworker/agent_runtime.py`, before accepting any existing execution as prepared/running/succeeded, require exactly one owned execution and equality of UTF-8 bytes count and SHA-256 against current `args.source`. **At the independent ToolReceipt commit transaction**, lock and verify the Agent-bound owned sandbox session, succeeded execution, exactly one execution, current invocation code SHA/byte size, and matching worker isolation, exact bounded stdout/stderr text and hashes, exit code and artifact identity. Deny mismatches with typed 409 `sandbox_source_binding_mismatch` without a false receipt. `tests/test_sandbox_control_plane.py` has two real Agent repository and sandbox integration fixtures: same-byte-length code substitution after an execution is prepared and after the independent sandbox worker completed. Require no second execution and no ToolReceipt, including a direct forged final-receipt attempt after the original worker has succeeded. A separate integration case submits a forged stdout excerpt with matching hash, proves denial, then completes the genuine result. **Real PostgreSQL integration coverage** in `tests/test_coworker_postgres.py` repeats source-substitution and forged-output denial directly at ToolReceipt settlement, and holds a PostgreSQL sandbox execution lock during a concurrent receipt attempt to prove fail-closed `SKIP LOCKED` behavior without a deadlock. It then verifies legitimate completion; no mandatory suite skip. User-supplied unaltered code path still covered by existing full sandbox tests. No schema migration, extra permissions/provider/action ledger, or feature activation. The generated-code path still requires durable human approval and sandbox claim enforcement; do not label C-04 complete.

**Evidence:** Product/test changes committed on GitHub review branch. Exact new PR SHA `test-and-build`, mandatory zero-skip `coworker` (PG/Temporal/transactions/browser/sandbox), `ci-merge-gate` **pending**; no local full checkout, independent review or operated staging. Browser proxy #410 new-head and main CI need final check. Staging S3/DNS/SSRF/prompt injection, CW-10 full approval lifecycle, CW-11 publisher, P-01/P-02/P-03 scenarios and release V-02–04 remain incomplete.

**Next:** Open draft PR, inspect exact final-head CI, repair any failures without skipping or weakening assertions. Obtain independent security review; qualify live browser sandbox/network staging separately. Then implement immutable generated-code proposal, owner human decision, atomic worker claim and bounded sandbox cleanup under CW-10, followed by CW-11 trusted skill publication and user grant selection. No merge/deploy/activation.

---

## CW-09 production HTTPS CONNECT socket-race qualification — 15 October 2026

**Fresh bootstrap:** `main` `74902c9223d648d3422a7d70b18991e8266f0281`; PR [#409](https://github.com/rumman52/Shuddho/pull/409) merged its reconciled old head `6993024eee41961e7c22cda76817939dc1eb193d`. Exact merged-PR [CI #38709409366](https://github.com/rumman52/Shuddho/actions/runs/38709409366) and new merged-main [CI #38709819435](https://github.com/rumman52/Shuddho/actions/runs/38709819435) had `test-and-build` success while `coworker` was **still in progress** at this initial checkpoint; do not count fully green until verified. PR #408 individual source erasure already merged. No open PRs at bootstrap, no independent submitted #409 review, operated Chromium/S3/staging/SSRF not available. Current architecture/core inventory remains incomplete.

**Selected safety qualification gap (C-02/C-03):** #409's Node suite checks `browserProxyClaimValid` as a predicate, not the actual asynchronous `http.Server` HTTPS CONNECT proxy, TCP socket registration or cancellation. That permits a broken control flow to remain untested despite pure-predicate success. `scripts/browser_worker.mjs` additionally dialed a pinned upstream after the client disconnected during a pending authorization, even if the claim remained live. New isolated branch `codex/cw09-proxy-socket-race-qualification-20261015` from fresh `main`. [Task contract](CW09_REAL_PROXY_SOCKET_RACE_2026-10-15.md).

**Code committed:** Extract the worker's same proxy handler into `scripts/browser_pinned_proxy.mjs`, preserving HTTPS-only authority, 443, broker `network-check`, pinned response IP, owner command/epoch/evidence triple gates before/after async authorization and TCP connect before 200. Worker now calls this module with its code-owned host validator and configured timeout; no user/model-supplied injection. Strengthen the post-await gate to refuse TCP dial if `clientSocket.destroyed`. Add `scripts/browser_pinned_proxy.test.mjs`: local socket-level CONNECT with asynchronous network authorization and controlled dial tests for command cancellation, ABA same-ID resumption, browser-client disconnect, revoked TCP handshake before acknowledgement, and an allowed pinned tunnel. Extend the **existing mandatory** `coworker` CI policy test step to run this new file as well as the unchanged policy tests. No new ledger, DB migration, provider, external action, broad grant or activation. Browser remains default-off.

**Evidence level:** Code and tests committed in GitHub branch; final SHA exact-head `test-and-build`, no-skip `coworker` including owned browser/PG/Temporal/transactions/Node proxy, and `ci-merge-gate` **pending** until new PR checks. No local checkout/test in this GitHub-only coding session; staging real Chromium + egress firewall/DNS/SSRF and independent review missing; production not qualified, activated no. CI green on #409 old head or main before this code does not qualify new branch.

**Next:** Open draft PR; review actual diff and code path; inspect final-head CI logs; repair any concrete failure without disabling checks or relaxing ownership. Obtain independent security review and operated staging worker egress/SSRF/DNS rebinding; continue CW-10 exact approved generated-code lifecycle, CW-11 review-bound skills, personal context scopes and four realistic coworker scenarios. Do not auto-merge/deploy/activate.

---

## CW-09 PR #409 conflict reconciliation — 15 October 2026

**Actual cause:** [PR #409](https://github.com/rumman52/Shuddho/pull/409) was based on `main` `896b5014bc371f5549fb9daa815338d932506a73`. [PR #408](https://github.com/rumman52/Shuddho/pull/408) subsequently merged into `main` `546e9a97c6ecda1abc34186bdb26971852539a75` and changed the same acceptance inventory and progress checkpoint lines. GitHub correctly reported a dirty merge in exactly those **two documentation files**, despite original #409's [CI #38704339583](https://github.com/rumman52/Shuddho/actions/runs/38704339583) being green. PR #408 [CI #38703355409](https://github.com/rumman52/Shuddho/actions/runs/38703355409) and merged-main [CI #38706921819](https://github.com/rumman52/Shuddho/actions/runs/38706921819) completed with all three mandatory jobs successful.

**Resolution design:** incorporate the exact new main tree, preserve all #408 source-erasure changes, retain #409's browser worker/policy/Node test and security contract unchanged, and reconcile the two conflicting docs semantically. Preserve full historical checkpoints for both workstreams; never choose either version wholesale or leave conflict markers. Update PR #409 branch through one actual two-parent merge commit, with old PR head as first parent and latest `main` as second parent; do not alter `main`, squash unrelated code or merge PR.

**Validation gate:** previous source head checks are historical, **not** final merge-head checks. After the merge commit, require exact final-head `test-and-build`, mandatory `coworker`, `ci-merge-gate`, mergeability and independent review. Staging browser DNS/revocation, SSRF and S3 evidence remain unverified, full CW-09 and CW-10/CW-11 incomplete, default-off and no deployment/activation authority.

---

## CW-09 async proxy CONNECT stale-claim race — 15 October 2026

**Baseline:** `main` `896b5014bc371f5549fb9daa815338d932506a73`, #406 merged with successful exact-head + main CI. Concurrent direct-main [merged PR #408](https://github.com/rumman52/Shuddho/pull/408) is separately repairing PR #407's deletion functionality which merged into a historical feature branch, not main; its required CI is pending. **Isolated worker safety branch:** `codex/cw09-browser-proxy-revocation-race-20261015`, created directly from this main; no PR branch dependencies or production changes.

**Observed source-level race:** HTTPS CONNECT pinned proxy asynchronously awaits DNS + server `network-check` and then opens an upstream socket; `pause`/cancel can happen during that await before client/upstream sockets are registered. An out-of-date authorized answer could open or acknowledge a tunnel after claim revocation. The original code did not revalidate worker claim generation after network check or on TCP connect.

**Committed bounded fix:** monotonic `proxyClaimEpoch` increment on set/pause/destroy; snapshot `{commandId, epoch, evidence}` per CONNECT; revalidate before DNS call, after network-check before `net.connect`, and on socket connect before sending HTTP 200/forwarding bytes. Stale/reused same-command snapshots fail closed. Pure Node policy regression tests cover cancelled in-flight check, ABA resume, evidence swap, wrong command, malformed generation. [Task contract](CW09_PROXY_DNS_REVOCATION_RACE_2026-10-15.md). Browser stays default-off, supervised controls intact. No new tool grant, action/outbox ledger, API or migration.

**Evidence:** GitHub source committed, exact-head required CI pending until PR checks; independent review not available; local full checkout/browser integration not available; **staging network race/SSRF/DNS rebinding not operated**, production qualification unavailable, activated no. Old proxy policy CI is not final revision evidence. No claim of observed live exploit.

**Next:** draft independent PR; final-head `test-and-build`, zero-skip `coworker`, `ci-merge-gate` and adversarial review; inspect actual failures, fix without disabling tests; independently stage live proxy cancellation + rebinding and comprehensive CW-09 browser security, then CW-10 immutable human-approved generated-code and CW-11 reviewed skills. Do not auto-merge/deploy/activate.


---
## CW-09 direct-main source-erasure integration — 15 October 2026

**Current baseline verified:** `main` `896b5014bc371f5549fb9daa815338d932506a73` (merged [#406](https://github.com/rumman52/Shuddho/pull/406) retained private browser-source artifacts). #406 final-head required [CI #38696966902](https://github.com/rumman52/Shuddho/actions/runs/38696966902) and latest matching main-push [CI #38699094958](https://github.com/rumman52/Shuddho/actions/runs/38699094958): all required `test-and-build`, `coworker`, `ci-merge-gate` completed **success**. PR [#407](https://github.com/rumman52/Shuddho/pull/407) was **merged into the historical #406 feature branch**, not `main`; its exact-head [CI #38697102026](https://github.com/rumman52/Shuddho/actions/runs/38697102026) passed, but its `DELETE /api/v1/browser-source-artifacts/{artifact_id}` route was absent on `main`. No relevant open PR at bootstrap. No independent submitted review for #407, no operated staging evidence.

**Selected first unresolved dependency (C-02/CW-09):** Restore the already-tested owner-scoped browser-source erasure behavior to the **actual default branch integration path**, without repeating or merging an old feature branch. Created isolated `codex/cw09-source-erasure-main-20261015` **from current main SHA above**. Ported only relevant `retention.py`, `api.py`, `agent_repository.py`, SQLite API/end-to-end `tests/test_agent_browser_tool.py`, and real PostgreSQL `tests/test_coworker_postgres.py` source diff. [Updated task contract](CW09_BROWSER_SOURCE_ERASURE_2026-10-15.md); updated [versioned acceptance inventory](ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md).

**Behavior:** authenticated owner-only deletion for one completed/cancelled/failed browser-source Agent run. Validate exactly one owned `browser.read` receipt, lock AgentRun and Artifact/ToolReceipt; refuse active runs with 409; atomically delete Artifact row and redact source URL/text/digest/size/artifact ID from persisted receipt, set `source_deleted=true`, and write audit. Then delete private object using existing ObjectStore. If object deletion fails, return truthful `metadata_erased=true, object_deleted=false, object_cleanup_pending=true` for existing aged orphan cleanup; no stale metadata-driven user downloads. Cross-user, active-run, confirmed object deletion, repeat attempts, storage outage and PostgreSQL JSON source-reference coverage ported. Existing presigned-browser-source URL prohibition maintained. No schema migration, new ledger, permissions, activation, deployment or external effects.

**Evidence distinctions:** source/test changes **committed** on direct-main branch, new exact-head repository CI **pending** until opened PR checks complete; no local full-checkout tests run in GitHub-only authoring environment. Previous #407 green CI on its **different target branch** is only supporting prior evidence, not qualification of this direct-main integration. Independent review **pending**, staging **not tested**, production **not qualified**, feature remains **default off**.

**Remaining highest priority:** open reviewable draft PR from direct-main branch, collect latest exact-head mandatory `test-and-build`, `coworker` (PostgreSQL/Temporal/browser/transaction no skip) and `ci-merge-gate`, review any failures and repair them without weakened assertions, request independent review and collect operated S3/source-revocation evidence. Next complete CW-09 worker network/redirect/DNS/SSRF and adversarial prompt-injection qualification, CW-10 exact user-approved generated-code lifecycle, CW-11 reviewed skills and the four operated personal coworker scenarios. Do not auto-merge/deploy/activate.

---

## CW-09 owner-bound durable visible source artifact — 15 October 2026

**Repository bootstrap:** `main` `599002b8e80089ac658548fdd6ed9e3dafc5ec22`; [PR #405](https://github.com/rumman52/Shuddho/pull/405) merged, exact final-head [CI #38692852396](https://github.com/rumman52/Shuddho/actions/runs/38692852396) has mandatory `test-and-build`, `coworker`, and `ci-merge-gate` all **success**. [#404](https://github.com/rumman52/Shuddho/pull/404) exact-head full CI also passed. Merged #405 main push [CI #38694104016](https://github.com/rumman52/Shuddho/actions/runs/38694104016) still running at initial refresh. No open PRs at branch creation, and neither #405 nor #404 had an independent submitted review observed. No operated staging or release eligibility evidence.

**Selected next gap:** CW-09 browser capture became a bounded text receipt but the full bounded source vanished at ToolReceipt settlement. Existing `Artifact` record, private `ObjectStore`, owner-authenticated artifact content API and `RetentionService` already provide the correct durable store, with no schema or orchestrator replacement. **Branch:** `codex/cw09-owned-browser-source-artifact-20261015` from above `main`. [Contract](CW09_OWNED_BROWSER_SOURCE_ARTIFACT_2026-10-15.md).

**Implemented on review branch:** `browser_sources.py` derives stable owner/command-bound UUID artifact identity and code-owned private object key. Runtime writes exactly the verified bounded UTF-8 visible text to existing private object storage and reads back to verify; storage errors fail closed without a verified receipt. The final `AgentRepository.finish_invocation` transaction rechecks live owned session, succeeded command and full bytes/digest/size/truncation/excerpt/URL/trust, inserts one existing `Artifact(artifact_class="browser_source")` alongside ToolReceipt atomically and scrubs transient browser ledger ciphertext on successful settlement. ToolReceipt references the artifact ID and exact content SHA. The authenticated artifact download gateway refuses S3 presigned URLs for `browser_source` while preserving ordinary export downloads; a regression test traps attempted presigning. Retention/account deletion and orphan cleanup are reused; an aborted post-blob DB commit is explicitly an orphan, not a verified source. No new UI, artifact list, migration, authority, activation or consequential action. Normal task artifact listing remains unchanged. Content is *bounded worker-visible text*, not raw HTML. Tests extended for owner/cross-owner object access, hashed capture bytes, fake content, S3-like storage failure, same-command retry/idempotence and real PostgreSQL + local ObjectStore.

**Evidence at branch implementation:** GitHub source committed on [draft PR #406](https://github.com/rumman52/Shuddho/pull/406); required exact-final-head CI **pending** until PR head checked; no local checkout or locally executed tests in this authoring environment, no independent review and no staged S3/Chromium. **Staging:** unverified. **Production:** not qualified. **Activation:** no (existing Agent browser flag remains default off). User-controlled per-source deletion, purpose-bound sharing and operated egress/SSRF/prompt-injection remain incomplete.

**Next:** open draft PR; inspect exact-head Python, Node, full no-skip `coworker` with real PostgreSQL/Temporal and `ci-merge-gate`; repair failures rather than disabling checks, independent adversarial review and staged source erasure/network/object-store proof. Follow with CW-10 human-approved generated code and CW-11 trusted skill publication/selection, plus four operated coworker scenarios. Do **not** auto-merge, deploy or activate.

---

## CW-09 final receipt authorization expiry guard — 15 October 2026

**Repository baseline:** main `96462220bb4d418227b322e55c6b4e4b60e67cd5` (PR [#404](https://github.com/rumman52/Shuddho/pull/404) merged). [PR #404 exact-head CI](https://github.com/rumman52/Shuddho/actions/runs/38691117096) and [merged-main push CI](https://github.com/rumman52/Shuddho/actions/runs/38691443218) had `test-and-build` success but mandatory `coworker` still **running** when reviewed; no independent submitted PR #404 review observed. No open PR at bootstrap. Previous PR #403 exact-head full CI green, but neither an old check nor an external merge establishes operational readiness.

**Reproduced first unresolved integrity boundary:** Browser content getter rechecked expiry, but final Agent ToolReceipt transaction and `_settle_agent_browser_session(completed=True)` did not. A session that expires between read and receipt could be falsely marked verified. New bounded branch `codex/cw09-expired-agent-receipt-guard-20261015` started exactly from the main SHA above. Code adds expiry guards **at final settlement and in canonical helper**, without broadening authority. PostgreSQL-backed test covers metadata-only and bounded content, including successful pre-expiry getter, post-expiry denied receipt, no ToolReceipt, no recovery by replay, and broker cleanup of transient sealed content. [Task contract](CW09_AGENT_BROWSER_LATE_RECEIPT_EXPIRY_2026-10-15.md).

**Additional PostgreSQL qualifier:** `tests/test_coworker_postgres.py` now runs the same expired capture-to-receipt boundary on the CI-provided real PostgreSQL service, verifying locked stale receipt denial and sealed source scrubbing. Source commit `798239e475b222a2ad9a703aa8ab4b910ca2fe5a`. The existing `tests/test_agent_browser_tool.py` container fixture uses SQLite; do not describe that fixture as PostgreSQL. **Draft PR:** [#405](https://github.com/rumman52/Shuddho/pull/405). All commits must be requalified at new final head.
**Change and evidence:** committed source, tests and refreshed [inventory](ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md) on branch; mandatory exact-final-head CI not yet established, independent review pending, staging not tested, production not qualified, capability not activated. Local full checkout/test unavailable via current GitHub-only authoring route; repository CI is primary evidence. No merge, deployment or activation performed. All edits committed through GitHub isolated branch; no local dirty checkout.

**Next:** open draft review PR, inspect exact SHA `test-and-build`, mandatory `coworker` (PG/Temporal/transaction/browser no skips), `ci-merge-gate`; repair any failures without weakening safety, obtain independent review, then continue CW-09 durable source artifact and operated egress/SSRF. CW-10 generated code, CW-11 reviewed skills and full operated coworker scenarios remain incomplete.

---

## CW-09 bounded page text: code review and exact-head qualification checkpoint — 15 October 2026

**Base:** main `e4a2e671ccaef9ab212f77cbd02521eec9866bd6`; previous [#403 exact PR-head CI](https://github.com/rumman52/Shuddho/actions/runs/38686360933) passed all three jobs. Main [push CI #38689490563](https://github.com/rumman52/Shuddho/actions/runs/38689490563) also completed with `test-and-build`, `coworker`, `ci-merge-gate` success. **Branch:** `codex/cw09-owned-page-text-capture-20261015`. **Draft PR:** [#404](https://github.com/rumman52/Shuddho/pull/404). **Latest substantive implementation/test head before this checkpoint:** `50be66cf67f09c18c64eb42343a23278608d9dcd`.

**Implemented on review branch:** isolated worker bounded UTF-8 visible-page-text extraction; strict typed worker evidence with exact whitespace preservation; broker AES-GCM owner/session/command-bound transient sealed text and SHA-256 of captured bytes; public DTO redaction; owner-scoped getter; Runtime v3 untrusted <=1200-byte excerpt and distinct `captured_text_excerpt` provenance. Blank text stays metadata-only. Settlement, cancellation and expiry remove sealed text. Expiry cleanup commits in an independent transaction before returning read denial, preventing accidental rollback of deletion. Regression tests cover Bangla bounds, owner isolation, exact digest, blank text, invalid receipts, source cancellation, stale expiry and typed schema compatibility. No new approval authority, schema migrations, production flags or outgoing consequential actions.

**Observed verification at handoff:** [PR #404 exact code-head CI #38691005056](https://github.com/rumman52/Shuddho/actions/runs/38691005056) running at the latest refresh for source SHA above; superseded runs were canceled due to ongoing changes. This docs checkpoint itself advances the branch and **requires a fresh exact final PR-head CI**. Full mandatory `test-and-build`, no-skip `coworker` and `ci-merge-gate` results **not yet established** for final head. Author self-review found and fixed (1) premature grounded claim on empty content, (2) expiring capture cleanup rolled back by read denial. **Not independently reviewed**.

**Evidence:** implemented in branch source; repository-verified **pending**, staging **not tested**, production qualification **not established**, activated **no** (Agent browser remains default off). Local full-repo tests unavailable because the authoring container cannot resolve GitHub; GitHub CI is authoritative. Owner-scoped PostgreSQL encrypted transient text **is not** a durable versioned source/artifact or full upstream HTML digest. Staging Chromium/egress and redirect/DNS/SSRF + model prompt-injection evaluations and release eligibility are outstanding, along with CW-10 exact approved code+worker sandbox and CW-11 trusted reviewed skills.

**Next exact action:** inspect #404 latest final-head CI `test-and-build`, `coworker` (PostgreSQL/Temporal/transaction/Agent browser no skips), `ci-merge-gate`, review and repair any failures without weakening enforcement. Obtain independent review and operated staging evidence. Do not auto-merge, deploy or activate.

---

## CW-09 bounded visible page text content slice — 15 October 2026

**Bootstrap truth:** `main` `e4a2e671ccaef9ab212f77cbd02521eec9866bd6`; [PR #403](https://github.com/rumman52/Shuddho/pull/403) was **merged**, its final-head [CI #38686360933](https://github.com/rumman52/Shuddho/actions/runs/38686360933) **passed all three** `test-and-build`, mandatory `coworker` and `ci-merge-gate` jobs. Matching main push [CI #38689490563](https://github.com/rumman52/Shuddho/actions/runs/38689490563) was running at bootstrap; no open PR at that point. No staging, production qualification or activation demonstrated.

**Next selected gap:** Agent browser source output remained metadata-only title/URL, insufficient for grounded public-page research. **Implementation branch:** `codex/cw09-owned-page-text-capture-20261015` based on the above main revision. [Contract](CW09_VISIBLE_PAGE_TEXT_CAPTURE_2026-10-15.md). In real Runtime v3 broker read path, isolated worker now returns optional bounded visible text; PostgreSQL command stores text encrypted with owner/session/command TokenVault binding and true digest of captured UTF-8 bytes; only owned server runtime obtains a <=1,200-byte untrusted excerpt. Browser user DTO excludes ciphertext/plaintext; Agent settlement, cancellation and expiry scrub temporary sealed text; malformed claims remain terminal. Legacy metadata-only worker receipts retain truthful metadata scope. New Python/JS tests and strict worker HTTP schema fixture update provided.

**Evidence levels:** Source implementation on review branch; **repository required exact-head CI and independent review still pending**, local checkout unavailable due GitHub DNS failure; **staging not tested**, **production not qualified**, **not activated**. The digest is of *bounded extracted visible text*, not complete HTML, and persistent private source artifacts remain a separate missing deliverable.

**Remaining:** CW-09 real isolated worker egress, SSRF/redirect/rebinding, source artifact retention/provenance, prompt injection, cancellation/staging; CW-10 exact generated-code human-approval+sandbox claim; CW-11 versioned trusted publish/grants/rollback; context continuity/recovery operated scenarios and production release contracts. See [versioned acceptance inventory](ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md). No auto-merge, deployment, paid provisioning or runtime activation.

---

## CW-09 Agent browser credential and HTTP mutation isolation — 15 October 2026

**Current main at bootstrap:** `45906f87cf2eba9f6abb5afc654f834166fa5820`; [PR #402](https://github.com/rumman52/Shuddho/pull/402) **merged**. Its exact-PR-head [CI #38685207628](https://github.com/rumman52/Shuddho/actions/runs/38685207628) `test-and-build` passed and mandatory `coworker` was **in progress** at initial review; merged-main [push CI #38685347836](https://github.com/rumman52/Shuddho/actions/runs/38685347836) also in progress. Do not report these green until refreshed. No other open PRs at bootstrap.

**Next security slice:** The browser worker previously replayed and persisted storage state for Agent reads and did not block page-originated POST/PUT/PATCH/DELETE for the Agent `navigate` command. Isolated implementation branch `codex/cw09-agent-read-cookie-isolation-20261015`, based on main SHA above. Added broker and worker defense-in-depth plus JS policy and real PostgreSQL-backed broker regression coverage. Human-supervised state continuity and takeover policy unchanged. [Contract](CW09_AGENT_BROWSER_CREDENTIAL_AND_MUTATION_ISOLATION_2026-10-15.md).

**Latest focused regression commit:** `90b38cdeef39f7faba5a1196daf4cbd75c3b102e` tests that even deliberately injected legacy encrypted session state never reaches an Agent worker claim. **PR:** [#403](https://github.com/rumman52/Shuddho/pull/403) (draft; not merged).
\n**Evidence (this new slice):** Source/test implemented and committed on branch; **required exact-final-head CI pending**, independent reviewer pending; **staging no, production qualification no, activation no**. Confirm JS worker policy runs via `test-and-build` and Python cookie-receipt terminality via `coworker`. Next: investigate failures and review PR without weakening checks. Then implement private bounded page text and real provenance/egress, not metadata as content. See the [versioned architecture/core acceptance inventory](ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md).

**Security:** Agent browser remains disabled unless separately qualified/authorized; no merge, deployment, paid provision, external action or activation performed.

---

## CW-09 post-#401 exact server-bound destination fixture — 15 October 2026

**Source truth:** PR #401 merged at `main` `052194a2b27eafc13d37b701cd90d25e887993eb` but its [CI #38681248077](https://github.com/rumman52/Shuddho/actions/runs/38681248077) had **1 failed, 35 passed** on mandatory Agent browser; `test-and-build` passed, `coworker` and `ci-merge-gate` failed. Original test remediation did not complete CI. Root cause: new DNS terminal-receipt test session start URL `/` differed from locked `/article` prepare command, provoking the intended `browser_agent_scope` guard before DNS was tested.

**Correction:** One-line fixture binding on `codex/cw09-bound-destination-ci-fixture-20261015` based on main SHA above. Set session start URL to exact `https://example.com/article` (matching prepare and final URL). No runtime or authorization changes. [Task contract](CW09_EXACT_AGENT_BROWSER_DESTINATION_FIXTURE_2026-10-15.md). Initial source commit `1e629fb47842d6fdbd32cdc314c4d8a0e8aadd10`.

**Evidence:** source implementation on branch; **exact final-head CI, no-skip PostgreSQL/Temporal/browser/transactions and independent safety review pending**; staging no; production qualified no; activated no. **Next:** get all three required CI jobs green, review, then address actual CW-09 content capture/SSRF worker staging and CW-10/11 missing real integration. No auto-merge, deployment or runtime activation.

---

## CW-09 mandatory browser CI repair — 15 October 2026

**Fresh default branch:** `main` `a305652a0be05b6d6a3768afbe6a14a029bd91c8`; PR #400 merged, no open PRs at task bootstrap. [Exact-main CI #38612375324](https://github.com/rumman52/Shuddho/actions/runs/38612375324): `test-and-build` success; `coworker` failed mandatory Agent browser gate (**2 failed, 33 passed**); `ci-merge-gate` failed. Earlier notes about #400 remaining draft or repository-green are superseded.

**Contract:** [CW09_MAIN_BROWSER_CI_TEST_CONTRACT_REPAIR_2026-10-15.md](CW09_MAIN_BROWSER_CI_TEST_CONTRACT_REPAIR_2026-10-15.md). **Branch:** `codex/cw09-browser-ci-regression-repair-20261015` based on `a305652a`. Focused correction commit `fe989fffb46116d4c24d46d9b521b19c4f749a07` before documentation. Invalid DNS terminality now tested in a dedicated negative scenario, not followed by success on the same failed command; authorized clean browser route still tested. The malformed-Unicode fixture now uses a real lone surrogate `chr(0xD800)` rather than literal escape text. Test-only fix, no relaxed assertions or broker change.

| Architecture/core part | Source status | Required remaining evidence |
| --- | --- | --- |
| Part 1: Architecture/contracts | Durable owner-bound, Temporal/outbox, permission boundaries exist in merged foundations; design not exhaustively qualified | Resolve and evidence residual state/trust/migration and operated boundaries |
| Part 2: Core agent/tool execution | CW-05–CW-08 foundations integrated, CW-09 metadata-only browser and inert CW-10/11 contracts; this browser test correction on isolated branch | Required exact-head CI; private page content/digest, generated-code stored approval+sandbox, reviewed skill runtime selection |
| Part 3: Context/coworker continuity | Owned context, message/activity and memory foundations present | Operated reconnect, erasure, purpose isolation, steering and resume |
| Part 4: Verification/release | Main mandatory Agent browser red at bootstrap | Corrected PR exact-final-head required CI and review; staging/operated release evidence absent |

**Evidence for this change:** implemented on branch; repository verified **pending exact-final-head tests**; staging verified **no**; production qualified **no**; activated **no**. **Next exact action:** inspect branch CI jobs and review comments, fix findings while retaining fail-closed tests. Then tackle next remaining CW-09 private-content worker receipt slice. No automatic merge, deployment, flag activation, provider action, or production claim.

---

# Coworker evolution progress

## CW-09 malformed Agent read receipt terminality — 14 October 2026

**Bootstrap/main:** `607b828274f9f4c580cd3dbd2ea5889d947904fc`. CW-09 [PR #399](https://github.com/rumman52/Shuddho/pull/399) **merged**; the historical section below calling it a draft is superseded. Its preceding main `ddc81711` [CI #38548692557](https://github.com/rumman52/Shuddho/actions/runs/38548692557) passed all three required jobs; the latest main `607b828` [run #38600101218](https://github.com/rumman52/Shuddho/actions/runs/38600101218) was still in progress at bootstrap. No staging or production qualification established. No open PRs at bootstrap.

**Selected first dependency-ready gap:** `_bounded_observation` rejects a malformed Agent worker result before committing a failed command; the same worker could resubmit a clean result. This differs from already fixed interaction signals, which terminally fail. **Branch:** `codex/cw09-terminal-malformed-agent-browser-evidence-20261014`, base `607b828274f9f4c580cd3dbd2ea5889d947904fc`; source and regression SHA `846f7f5a72edef2025fbcfed496594605a84c8c1` (initial); post-P1 source/test head `5832dce5eff5bdb04a8efab07f3861e8fb7d27b0` before latest docs. [Task contract](CW09_MALFORMED_AGENT_READ_TERMINAL_RECEIPT_2026-10-14.md).

**Change:** in code-owned broker completion, after malformed receipt detection lock BrowserSession then BrowserCommand; for the claimed Agent read only, commit failure, revoke session, clean claims/state/frame and audit, then propagate original error. Non-Agent sessions keep original validation/retry semantics. New regressions cover malformed object shape, missing URL, malformed DNS/title, terminality and no resubmission, plus ordinary browser retry acceptance. No feature or authority granted.

| CW task | Integrated source status | Remaining acceptance |
| --- | --- | --- |
| CW-05–CW-07 | Owner-scoped messages, dispatch/activity foundations | Operated replay/reconnect/deletion and UI acceptance |
| CW-08 | Selected source/context foundations | Revocation, expiry, erasure and versioned memory staging |
| **CW-09** | Metadata broker, Agent kill switch, verified prior changes including #399; this terminality fix isolated on review branch | Final-head tests/review; private page text and hash, egress/SSRF redirect worker staging, runtime release eligibility |
| CW-10 | Inert immutable proposal schema merged | DB persistence, exact human approval, sandbox claim enforcement, isolation tests |
| CW-11 | Inert reviewed manifest validator merged | Trusted publish/version rollback/runtime grant selection and evaluation |

| Evidence | Selected repair |
| --- | --- |
| Implemented | Isolated branch code/tests and contract |
| Repository verified | **Pending exact final PR SHA CI and independent review** |
| Staging verified | Not run |
| Production qualified | Not established |
| Activated | No; Agent browser flag remains default-off |

**Additional P1 review resolution:** The reviewer found FastAPI `BrowserWorkerObservation` returning HTTP 422 before the broker could terminally fail a claimed Agent read, and `UnicodeEncodeError` bypassing the typed failure from `storage_state`. Corrected in source/test commit `3c05b2161b836010dc14d411eb3463101706c8b5` before final docs: authenticated endpoint retains strict Pydantic model validation, uses broker session-before-command failure for a correctly claimed Agent command, preserves non-Agent and wrong-worker behavior, handles invalid Unicode as a typed error, and calls blocking repository operations via threadpool. HTTP tests cover bad final URL/title/DNS/storage/extra fields and denial of a successful rewrite. **Newest exact-head CI and independent re-review required.** No release evidence granted.

**Review and resolution:** On [draft PR #400](https://github.com/rumman52/Shuddho/pull/400), the independent reviewer found a **P1**: post-envelope validation exceptions rolled back and allowed rewritten Agent reads. Added a shared committed terminal transition after the failed completion transaction, excluding legitimate cancellation/worker-claim/revocation control errors. Added DB-backed invalid storage, DNS, URL and redirect cases, and wrong-worker regression. **Next exact action:** Verify newest PR #400 exact-head `test-and-build`, no-skip `coworker` browser/PG/Temporal, `ci-merge-gate` and independent re-review; correct findings. Continue private page content capture and operated worker tests. Do not auto-merge, deploy or activate.

## Architecture/core status refresh — 14 October 2026, PR #399

**Default branch:** `main` `ddc81711c8ccb4475d3a0053b26b5955a5be35b1`; [CI #38548692557](https://github.com/rumman52/Shuddho/actions/runs/38548692557) passed `test-and-build`, `coworker` and `ci-merge-gate`. [#398](https://github.com/rumman52/Shuddho/pull/398) merged (CW-09 autonomous browser kill-switch broker repair), [PR CI #38547893525](https://github.com/rumman52/Shuddho/actions/runs/38547893525) all three required jobs passed. No open PR at bootstrap. No fresh staging/production evidence established.

**Selected unfinished task:** CW-09 typed worker receipt shape validation; malformed JSON arrays/scalars/null triggered unhandled `AttributeError` at `_bounded_observation`. [Contract](CW09_BROWSER_RECEIPT_TYPE_VALIDATION_2026-10-14.md). On branch `codex/cw09-observation-type-validation-20261014` based on main SHA above. Test commit `a0601c01e1ddd770ef5a4632a8570223ff588fdf`; source commit `edd7fa8bb9dfaccccd19de6edd6c3bdd9646ee01`; this documentation checkpoint follows. [Draft PR #399](https://github.com/rumman52/Shuddho/pull/399) is **unmerged**, its exact-final-head CI and independent review remain **pending**. Five regression values exercise real worker claim and valid subsequent completion. No authority or feature flags changed.

| Canonical acceptance | Integrated on main | Remaining acceptance |
| --- | --- | --- |
| CW-05–CW-07 | Owner-bound chat, routing/activity foundations | Operated replay/reconnect, keyboard/mobile and ownership verification |
| CW-08 | Selected source/context foundations | Fresh staging deletion/revocation/retention |
| CW-09 | Metadata read broker and Agent kill-switch repair #398 | New malformed-receipt fix #399 review/CI; private page-text/hash/provenance, egress staging, canonical release eligibility |
| CW-10 | Inert source/proposal schema | Persisted immutable proposal, reviewed identity/approval and isolated compute claim |
| CW-11 | Inert reviewed manifest validator | Trusted publish/rollback, runtime grant selection, evaluations and staging |

**Evidence separation:** New #399 slice implemented on draft branch, **not integrated main or repository-verified** pending CI/review. Staging-verified no; production-qualified no; activated no. Historical checkpoints below describe their respective earlier branch states.

**Next exact action:** Retrieve PR #399 exact head and all three required GitHub CI job conclusions; self/independent review and correct any failed check. Maintain draft status. Then implement independently gated CW-09 private browser content capture and provenance, not infer a working page reader from metadata.

---


## CW-09 Agent browser worker-time kill-switch — 14 October 2026

**Refreshed default branch:** `main` `7da39a13e0207b96a2b05dde72e1fb876a970a5c`; no open PRs at bootstrap. Main `test-and-build` passed while `coworker` and `ci-merge-gate` were not yet complete on [CI #38546539014](https://github.com/rumman52/Shuddho/actions/runs/38546539014). The previous CW-11 #396/#397 work has been merged; earlier PROGRESS notes treating it as draft are historical. No deployed release or staging evidence was established.

**Current task:** CW-09 autonomous browser read revocation at the actual worker/broker boundary. [Contract](CW09_AGENT_READ_REVOCATION_BOUNDARY_2026-10-14.md). Review branch `codex/cw09-agent-read-revocation-boundary-20261014`; base as above; initial source commit `28ebf7a7f2edc3e84d3a15ab977aa9ac8de71981`, regression tests commit `605b65cf180784645b31043e9d54474e9520560a`, task-contract commit `fa21d61a54720fe66464ee1f5b5ded3d0ac680d1`, before this progress update. Exact final implementation SHA and PR number must be obtained from GitHub after this checkpoint.

**Gap:** Existing runtime/tool gating was not enough: a prepared `agent_read_only` browser command could be claimed by a worker after the Agent-specific switch was disabled; an already-claimed command could still pass independent broker network preflight and submit a late verified receipt. The broker now denies new server-agent sessions and preparation when disabled, terminally fails queued/claimed Agent reads at claim/control and completion, and explicitly rejects network egress preflight after revocation. Human-supervised browser reads retain their separate capability. Tests cover queued revocation, claimed network/control/receipt and supervised non-regression. No migration, second ledger, external provider, human approval bypass or production activation.

| Architecture/core acceptance | Integrated evidence | Remaining |
| --- | --- | --- |
| CW-05–CW-07 | Conversation and activity foundations merged | Owned operated replay/reconnect/UX qualification |
| CW-08 | Selected-source validation and memory controls merged | Staging revocation/deletion and retention |
| **CW-09** | Broker and tool foundations on main; new revocation repair on isolated branch | **Final-head CI/review**, private bounded page text provenance, worker egress staging, canonical runtime release eligibility |
| CW-10 | Inert reviewed code-proposal envelope merged | Persisted immutable proposal, explicit reviewed approval and sandbox worker claim |
| CW-11 | Inert reviewed manifest integrated via #396/#397 | Trusted publication/rollback enforcement, runtime grant-selection and staging evaluations |

**Evidence:** implemented on isolated review branch, repository-verified **pending exact-head CI and independent review**, staging-verified **no**, production-qualified **no**, activated **no**. An in-flight request already allowed just before a revocation cannot be undone; the worker stop/egress and shutdown staging boundary still needs testing. Flags unchanged and default-off.

**Next exact action:** Open draft PR for the review branch, inspect `tests/test_agent_browser_tool.py`, `tests/test_browser_broker.py`, exact-head `test-and-build`, `coworker` and `ci-merge-gate` (zero mandatory skips), repair any failures, obtain independent review. Then take a separate CW-09 page-content/private receipt and runtime release-gate slice without treating this guard as CW-09 closure.


## CW-11 schema-generator dependency-pinning repair — 14 October 2026

**Live verified bootstrap:** `main` `4acea1d245030101aff657d80f89b1c66c7ca097`, CI [#38527867446](https://github.com/rumman52/Shuddho/actions/runs/38527867446) **success** (`test-and-build`, mandatory `coworker` incl. browser, `ci-merge-gate`). Historical merged-red CW-09 notes below are superseded by this newer integrated CI. **Open #396:** CW-11 inert manifest pilot was green on `9b80e39ddb3c129726ec85f2779f52b5bd4bbf1b` ([CI #38527404758](https://github.com/rumman52/Shuddho/actions/runs/38527404758)) but unmerged; [P2 review](https://github.com/rumman52/Shuddho/pull/396#discussion_r4267904354) found a dependency-upgrade bypass. The other three P2 findings were addressed in that earlier branch revision.

**Correction:** continue the existing branch `codex/cw11-inert-reviewed-skill-manifest-20261014`, no duplicate PR. Code/tests SHA `045830b2afc2e5645438c00a769929b36ae03953` before docs. Initially pinned whole `uv.lock` bytes, but [CI #38539292291](https://github.com/rumman52/Shuddho/actions/runs/38539292291) exposed an incorrectly escaped Git blob NUL separator (33 failed, 1110 passed, 66 skipped), not an actual generator upgrade. Replaced byte hash with exact pinned **Pydantic/core/typing generator versions in both parsed lockfile and installed environment**; lock version mutation and installed version mismatch still fail closed. Latest source/test commit `931507c348f686282d9c9e35023875fb06639e31` before docs. Independent [P2 shared nested limits](https://github.com/rumman52/Shuddho/pull/396#discussion_r4268811787) review fixed: returned manifest copies do not share limits/reference object, and exact scalar ceilings are checked before equality. Added malicious `object.__setattr__` regression. The earlier Git blob separator P1 was resolved by removing the brittle whole-file hash in favor of exact locked+installed generator versions; final-head full CI is pending. **Evidence level: implemented on open PR #396, exact-new-head CI and independent re-review pending.** This is an *inert* data validator, not skill publication, agent tool selection, or provider/grant activation. A deployment without its reviewed dependency identity fails closed.

| Canonical item | Integrated state | Still required |
| --- | --- | --- |
| CW-05–CW-07 | Conversation/activity integrated; main CI green | Operated replay/reconnect and UI |
| CW-08 | Selected source/context integrated; main CI green | Operated deletion/revocation |
| CW-09 | Read broker and ledger corrections merged; main CI green | Real private page text/content digest, isolated browser egress staging, runtime release guard |
| CW-10 | Inert reviewed code-envelope source merged; main CI green | Persisted proposal+exact approval+isolated claim |
| **CW-11** | Inert reviewed manifest **on PR #396, not integrated** | Re-review and exact-head CI on pinned generator deps; persisted reviewed publish/rollback and runtime grant filter |

**CI correction:** [#38540161508](https://github.com/rumman52/Shuddho/actions/runs/38540161508) had 1 failed/1143 passed/66 skipped in broad Python checks solely because the generator drift test used literal backslash-n rather than a newline in its TOML fixture string. Corrected to `chr(10)` without weakening the negative assertion; exact-final-head CI still required. **Next exact action:** inspect PR #396 latest-head CI, mandatory no-skip tests and independent review. Repair actual failures on that branch without automatic merge or activation. Read-only synthetic tests do not qualify production.

## CW-11 first code-owned reviewed manifest pilot — 14 October 2026

**Live reference:** `main` `3505c5029891d488678b1f2e8b302694ce0a96e4`; merged #393 exact-head [CI #38513869839](https://github.com/rumman52/Shuddho/actions/runs/38513869839) green. #394 merged initial CW-10 envelope, with new independent datetime-subclass P2 addressed on separate [draft PR #395](https://github.com/rumman52/Shuddho/pull/395), **not a dependency automatically merged here**. Main CI #38524741451 and #395 CI #38525432542 were in progress at this checkpoint.

**Independent first CW-11 dependency-ready slice:** branch `codex/cw11-inert-reviewed-skill-manifest-20261014`, base `3505c5029891d488678b1f2e8b302694ce0a96e4`, initial source/tests SHA `6f11f841c8427620d62b9e897eda96fe80fda57c`; latest source/test SHA `d0264e22cf4c6ae6a606f8f6bafb8e36b7270bc6` before docs. Independent [#396 review](https://github.com/rumman52/Shuddho/pull/396) identified three P2 issues: regenerated unpinned policy, subclassed comparison identities, retry-unaware wall cap. Corrected via static Git blob source attestations, one frozen code-reviewed pilot snapshot plus live drift checks, exact field identity guards and 481-second retry-aware budget. New regression cases added. **Draft PR #396**, unmerged; exact final-head CI and independent re-review still required. [Task contract](CW11_INERT_REVIEWED_SKILL_MANIFEST_2026-10-14.md). New **pure, inert** `CoworkerSkillManifest` pilot for existing `research` / `research.search`; pins current WorkSkill version and instruction/guidance hash, exact ToolSpec input and output schema hashes, full registered tool-policy hash (including permissions), immutable resource ceilings, rollback version and code-owned `allowed_tools` subset. Negative tests reject new tools, connected email/browser escalation, changed source/schema/policy, permission drift, subclass/mutable values and wider limits. No dynamic skill install/loader, feature flag or production capability change.

| Task | Integrated code | Missing acceptance |
| --- | --- | --- |
| CW-05–07 | Owned conversation/run/activity integrated | Staging replay and UX/accessibility |
| CW-08 | Owned source/context foundation integrated | Revocation/deletion retention staging |
| CW-09 | #393 merged with exact CI pass | Page text private checksum, worker/network SSRF staging, runtime release eligibility |
| CW-10 | #392/#394 merged inert envelope; #395 draft correction | #395 final-head CI/review; persisted proposal/approval and isolated worker claim |
| **CW-11** | Static WorkSkill/ToolSpec registry; inert pilot manifest **on isolated review branch** | Final-head CI and review, publication/rollback authority, skill-selection gate, quality/cost evaluation and operated staging |

| Evidence level | CW-11 pilot |
| --- | --- |
| Implemented | Isolated source/test/doc changes |
| Repository-verified | **Pending exact-final-head CI** |
| Staging-verified | No |
| Production-qualified | No |
| Activated | No (no registry/dispatch/permission mutation) |

**Next exact action:** open CW-11 draft PR, inspect `tests/test_coworker_skill_manifests.py`, full `test-and-build`, `coworker`, `ci-merge-gate`, and independent review on exact final head. Fix failures without weakening checks; no merge/activation. Continue CW-09/10 operational contracts in separate dependency-reviewed slices.

## CW-10 exact timestamp / UUID class review repair — 14 October 2026

**Live bootstrap:** `main` `3505c5029891d488678b1f2e8b302694ce0a96e4`, after merges [#393](https://github.com/rumman52/Shuddho/pull/393) and [#394](https://github.com/rumman52/Shuddho/pull/394); **no open PRs** at bootstrap. #393 exact-head [CI 38513869839](https://github.com/rumman52/Shuddho/actions/runs/38513869839) passed `test-and-build`, all `coworker` (including mandatory browser tests) and `ci-merge-gate`; merged source corrects exact integer schema versions. #394 exact-head [CI 38521982865](https://github.com/rumman52/Shuddho/actions/runs/38521982865) passed, but the latest independent [P2 review](https://github.com/rumman52/Shuddho/pull/394#discussion_r4267484974) documented an unguarded subclassed `datetime.astimezone` bypass during immutable proposal review. Main [CI 38524741451](https://github.com/rumman52/Shuddho/actions/runs/38524741451) was still in progress at bootstrap.

**Coherent correction:** branch `codex/cw10-exact-timestamp-uuid-review-20261014`, baseline `3505c5029891d488678b1f2e8b302694ce0a96e4`, initial code/test head `6624209e7f7b2b778a9897e005fcc1aef39733e2`; earlier reviewed source/test head `b5b49bc9e9e1f7855cd6475cfee1bbdd07751682`; latest test-only correction head `cdc1fb1338ca57b2ce744365760780ffabfd69d2` before final docs. Prior CI `a018236` had 3 **test fixture setup** failures from stdlib UUID construction receiving an equality-overriding `int` subclass. The fixture now constructs a standard UUID and injects the hostile payload directly; exact latest-head CI and independent review remain mandatory, after final-head review found [P2 hostile tzinfo](https://github.com/rumman52/Shuddho/pull/395#discussion_r4267754497) and [P2 UUID integer subclass](https://github.com/rumman52/Shuddho/pull/395#discussion_r4267754504) bypasses. Code now checks exact canonical timezone/clock and UUID integer payload; matching-digest negative tests added. **Draft [#395](https://github.com/rumman52/Shuddho/pull/395)**, unmerged; refreshed exact-head CI/review required; [task contract](CW10_SUBCLASSED_REVIEW_IDENTITY_REPAIR_2026-10-14.md). Verifier now requires exact `datetime` and `UUID` types on original proposal and nested input identities **before invoking subclass-overridable normalization or serialization**; tests use self-consistent hashes with adversarial subclassed three-hour expiry and UUID references. Unchanged finite limits, source hash, owner, version, immutable nested type, and `egress_profile=none` gates. No new authority.

| Acceptance item | Integration | Unmet acceptance / next action |
| --- | --- | --- |
| CW-05/CW-06/CW-07 | Existing merged implementation | Operated owned chat, steering, resume and deletion |
| CW-08 context/memory | Existing merged core | Revocation, expiry, retention staging |
| CW-09 brokered browser | #387–#393 integrated; #393 final CI green | Actual bounded webpage text/private digest, isolated-worker egress/DNS/SSRF proof, execution-time eligibility, staging |
| **CW-10 reviewed code** | #392/#394 integrated inert envelope, current subclass correction on new review branch | Exact-head CI/review, persisted immutable proposal/approval, sandbox worker claim and execution safety |
| CW-11 reviewed skills | Static registered code-owned tools | Strict versioned manifests, no authority expansion, rollback + qualification |

| Evidence | Current CW-10 correction |
| --- | --- |
| Implemented | Source/test/docs in isolated review branch |
| Repository-verified | **Pending exact-final-head mandatory CI and independent review** |
| Staging-verified | Not run |
| Production-qualified | Not established |
| Activated | No: code proposals remain inert and browser.read default-off |

**Next exact action:** Open draft PR, verify `test-and-build`, `coworker`, `ci-merge-gate`, and `tests/test_agent_code_proposals.py` on that final SHA, obtain independent review; correct failures without reducing guard/test strength. Then select next dependency-ready CW-09/10/11 coherent slice. No automatic merge, credential change or activation.

## CW-10 #394 copied-state and subclass integrity repair — 14 October 2026

**Source/PR:** [#394](https://github.com/rumman52/Shuddho/pull/394), branch `codex/cw10-review-envelope-revalidate-20261014`; source/regression commit `4f060279cc38895e1f04f7ab5255724b1451ba8b`. Original branch baseline `9f8cf53a422ba5eee7d5a0772b2943328d3faaaa`; reconciled with main `81cc0cd9d679b568a98722ca6cb53b91c9170eb2` (merged [#393](https://github.com/rumman52/Shuddho/pull/393)). Current PR head is resolved from GitHub at review and CI time; do not substitute older SHA checks.

**Reproduced risk and fix:** Review on #394 found inherited/subclass serializers can disguise original proposal state, and `model_copy(update={"approved": True})` can add an undeclared field that `model_dump` omits, while a matching review hash still verifies. `verify_reviewed_code_identity` now rejects subclasses and requires exact declared stored fields (including nested limits and input versions), with no hidden Pydantic extra/private state before strict reconstruction. Added six negative parameter cases covering copied undeclared top-level fields, nested extras and subclass overrides. These remain inert checks; no code execution, approval, grants or rollout.

**Previous CI diagnosis:** [old #394 CI](https://github.com/rumman52/Shuddho/actions/runs/38514097821) had successful `test-and-build`, 1340 general coworker tests passed, but mandatory CW-09 browser gate failed `21 passed, 1 error` on missing `signed_client` fixture, therefore `ci-merge-gate` failed. This was a pre-#393 base; #393 deleted/relocated the fixture-dependent test. The new combined head needs its own complete required CI. Do **not** claim it green yet.

**Evidence levels:** implemented on a GitHub review branch; repository-verified **pending exact-head no-skip CI** and review; staging-verified **no**; production-qualified **no**; activated **no**. Existing CW-09 and CW-10 incomplete operational requirements remain separate.

**Next exact action:** Inspect the reconciled PR head, run `uv run --extra coworker pytest tests/test_agent_code_proposals.py -q`, require `test-and-build`, `coworker` and `ci-merge-gate` on the final head with zero mandatory skips. Resolve outstanding review threads only on evidence; do not merge, deploy or activate. Then implement CW-10 persisted code proposal, exact human approval and sandbox claim as a separate reviewed slice.

## CW-10 #394 immutable nested copy integrity — 14 October 2026

Second independent [P2](https://github.com/rumman52/Shuddho/pull/394#discussion_r4266920978) found that strict Pydantic reconstruction can accept a valid `limits`/input plain mapping and normalize it, leaving the original copied proposal mutable for downstream use. Added checks for exact `CodeComputeLimits`, `CodeInputVersion` and immutable tuple types **on the original object** before the strict round trip. Three new self-hashed negative cases test same-value limits/input mappings and mutable empty destinations. Latest source/test SHA `9285ff38408f9099bcf3d80c3794169589700507` before docs. Draft [PR #394](https://github.com/rumman52/Shuddho/pull/394), unmerged; exact final-head full required CI, review and authority/compatibility checks pending. No execution grant.

## CW-10 #394 strict typed validation review correction — 14 October 2026

CW-10 [draft PR #394](https://github.com/rumman52/Shuddho/pull/394) independent review [P2](https://github.com/rumman52/Shuddho/pull/394#discussion_r4266890920) found `model_validate()` can coerce untrusted copied timestamps and other field types instead of proving immutable typed identity. Revalidation now uses `strict=True`, rejects boolean schema version explicitly, and includes rehashed copied string-expiry/boolean-schema/float-CPU negative cases; latest source/test commit `db2aafa7feca94a399c816f1fc0437da51dded65` before documentation. Earlier `test-and-build` success was on an older SHA. Exact-final-head `test-and-build`, `coworker`, `ci-merge-gate` and independent review remain required. No code execution or production flag enabled.

## CW-10 copied inert review-envelope validation — 14 October 2026

**Live main baseline:** `9f8cf53a422ba5eee7d5a0772b2943328d3faaaa`, #392 immutable schema merged. New **independent** branch `codex/cw10-review-envelope-revalidate-20261014`; code/tests SHA `d3740983443bdf450422ebcab9b60e8ca9cdb9f7` before docs. [Task contract](CW10_COPIED_REVIEW_ENVELOPE_VALIDATION_2026-10-14.md).

**Bug and change:** although Pydantic `CodeProposalEnvelope` is frozen, unvalidated `model_copy(update=...)` can change forbidden egress/destinations/source checksum/nested CPU policy/expiry without model validators. `verify_reviewed_code_identity` now reconstructs and validates the entire existing proposal object before digest/owner/run/time/input ceiling checks, rejecting invalid copies even when a newly recomputed hash matches them; five corresponding no-authority regressions added. No DB approval, grant, credential, generated-code execution or production flag is created.

**Verification:** exact-final-head task tests and full required CI **pending**; independent review **pending**. CW-09 remains separately red on merged main, addressed by [draft PR #393](https://github.com/rumman52/Shuddho/pull/393) with its own mandatory CI and review. These are two independent draft changes; both must pass before claiming an integrated green repository.

| Evidence | CW-10 copied-envelope validator |
| --- | --- |
| Implemented | Separate source/test/docs branch |
| Repository verified | **Not yet: exact-head CI pending** |
| Staging verified | Not attempted |
| Production qualified | Not established |
| Activated | No; inert contract only |

**Next exact action:** Open CW-10 independent draft PR, run `tests/test_agent_code_proposals.py` and exact full CI, obtain independent review and fix any findings. Then move to persisted owner/run immutable proposal, human approval and sandbox worker claim (still unimplemented), only after preserving existing no-grant and user-supplied-Python behavior. No automatic merge/deploy/activation.## CW-09 #393 embedded runtime typed-schema P2 repair — 14 October 2026

Second independent [P2](https://github.com/rumman52/Shuddho/pull/393#discussion_r4266898374) on #393 found `runtime.schema_version = true` or `1.0` accepted by Python equality even after outer activation type hardening. Added `type(runtime.schema_version) is int and runtime.schema_version == 1` and two synthetic self-rehashed runtime-manifest negative tests, source/test SHA `06a172051e951b3a832374087d617d8a3353f8b2` before docs. Earlier tests on old head are **superseded**; request a fresh independent review and exact-final-head CI of browser no-skip, PostgreSQL, full coworker, test-and-build and merge gate. Branch remains draft/unmerged and default-off. CW-10 separate #394 is likewise draft and requires its own checks.

## CW-09 PR #393 independent P2 review fix — 14 October 2026

[#393](https://github.com/rumman52/Shuddho/pull/393) review [P2](https://github.com/rumman52/Shuddho/pull/393#discussion_r4266861068) found a malformed activation with JSON `true` or `1.0` could pass `schema_version == 1` through Python bool/float equality; corrected with exact integer type check and two synthetic negative regressions, source/test SHA `121280e82b9856366dec8ccf1f0a20ff810b2356`. Earlier CI on `6ec683d5` passed `test-and-build` and PG safety, but was superseded. **Require final-head `coworker` browser no-skip, `test-and-build`, `ci-merge-gate` and final review.** CW-10 independent [draft PR #394](https://github.com/rumman52/Shuddho/pull/394) closes a copied Pydantic immutable-schema trust-boundary bypass separately; do not conflate branches. No merge/deployment/activation in this continuation.

## 14 October 2026 — CW-09 merged-red mandatory CI and ledger review correction

**Verified at bootstrap:** `main` `9f8cf53a422ba5eee7d5a0772b2943328d3faaaa`; [PR #391](https://github.com/rumman52/Shuddho/pull/391) **merged** (`0e6ea7182ffae6e5bf8dbdfc4e229cb6472dcd46`), [PR #392](https://github.com/rumman52/Shuddho/pull/392) **merged** (`4248966e445f535a19027f6c3aa2d11a213ddd8e`), **no open PRs** before this correction. Historical entries below calling #391/#392 unmerged are superseded. PR #391 [exact-head workflow #38463696028](https://github.com/rumman52/Shuddho/actions/runs/38463696028) failed mandatory Agent browser test gate (21 passed, one `signed_client` **fixture not found** setup error); latest main [workflow #38465787058](https://github.com/rumman52/Shuddho/actions/runs/38465787058) also failed that gate. `test-and-build` passed in both, but `coworker` and `ci-merge-gate` failed. Production is **not qualified**.

**Review findings:** latest #391 [P1/P1/P2 security review](https://github.com/rumman52/Shuddho/pull/391#pullrequestreview-5509664548) identified missing canonical rollout `incident.change_reference` semantic match, acceptance of arbitrary non-Git deployment revision and acceptance of activation without version 1 schema. Prior rollout digest, post-deploy status chronology and kill-switch checks remain in place.

**Corrective source branch:** `codex/cw09-main-red-ci-ledger-review-repair-20261014` based on `9f8cf53a422ba5eee7d5a0772b2943328d3faaaa`, source/tests head `b4f5e0c32fcaa96c05c73aaf7b971a7481f7bb42` before documentation. [Task contract](CW09_MAIN_CI_RELEASE_LEDGER_CORRECTION_2026-10-14.md). Move the out-of-module authenticated manifest assertion into the actual API test fixture; browser mandatory suite remains no-skip. Add schema 34 review-bound incident, canonical Git SHA-1 and activation v1 enforcement, synthetic adversarial tests with rehashed documents. **No generated proof, provider operation, activation or changed model grants.**

| CW item | Integrated status | Unfinished verification/acceptance |
| --- | --- | --- |
| CW-05 owner-bound conversation | Existing integrated implementation | Actual staging replay, deletion and recovery |
| CW-06 steering/durable dispatch | Existing integrated implementation | Operated Temporal/late observation |
| CW-07 activity and reconnect | Merged previous PRs | Browser/mobile keyboard and reconnection staging |
| CW-08 context and memory | Merged previous PRs | Retention, source revocation and ownership staging |
| **CW-09 read-only browser** | Broker/read and controlled-release contracts merged, but **main CI red and schema34 review P1**; corrective isolated branch implemented | Final-head no-skip CI, reviewed release changes, bounded actual page content with private checksum/provenance, isolated worker DNS/SSRF/redirect tests and execution-time canonical eligibility |
| CW-10 immutable generated-code proposal | Initial inert envelope merged #392 | Actual immutable persistence, grant/approval binding and sandbox claim tests |
| CW-11 versioned skills | Existing static tool contracts only | Versioned reviewed manifest, constraints and budget authority controls |

| Evidence level | CW-09 merged-red correction |
| --- | --- |
| Implemented | Source/test changes on isolated branch |
| Repository verified | **Pending final-head CI + independent review** |
| Staging verified | **No** |
| Production qualified | **No** |
| Activated | **No**; defaults remain off |

**Next exact action:** Open draft PR; inspect full final-head `test-and-build`, `coworker` (PostgreSQL/Temporal/transactions/browser no-skip) and `ci-merge-gate`; request independent security review, correct any failures without loosening mandatory tests. Continue only other independent CW-09/CW-10/CW-11 work while release is gated. **No automatic merge, deploy or activation.**

## CW-10 first inert review-envelope contract — 14 October 2026

**Source bootstrap:** `main` `76a07600328d0c6ff0ed73b69d2c7933d38bf927`. CW-09 corrective [PR #391](https://github.com/rumman52/Shuddho/pull/391) was merged into main at `905a09c3a5e2931be46d9053ba4af09ecd331125`, while exact-final-head mandatory CI and security review still require confirmation; do not infer production qualification. Do not conflate this dependent CW-09 safety review with CW-10 work.

**Independent dependency-ready CW-10 preparatory slice:** `codex/cw10-immutable-proposal-envelope-20261014`, base `76a07600328d0c6ff0ed73b69d2c7933d38bf927`, initial source/test head `cd5463231a9a18043f26363b33777c2a251d7b4d`, latest source/test head `804a875ddfa4f3a104b21c301a6d039eb7131084` before final docs; second independent [P2 DST lifetime issue](https://github.com/rumman52/Shuddho/pull/392#discussion_r4263771173) fixed with UTC-normalized lifetime and regression. CW-10 branch reconciled onto main `905a09c3a5e2931be46d9053ba4af09ecd331125` using a two-parent merge preserving CW-09 progress after [independent P2 future-validity review](https://github.com/rumman52/Shuddho/pull/392#discussion_r4263712225) and not-before test; [draft PR #392](https://github.com/rumman52/Shuddho/pull/392), not merged; new frozen, strict `CodeProposalEnvelope`, exact source/content and owner-version SHA, full canonical review digest, offline `verify_reviewed_code_identity` comparing live owner/run/input versions, expiry and sandbox policy ceiling; zero grant or execution. Regressions: cross owner/run, modified code/input/limits/expiry, network expansion, bad hash. [Task contract](CW10_IMMUTABLE_INERT_PROPOSAL_ENVELOPE_2026-10-14.md). Draft PR and final-head checks pending. **This satisfies only the immutable-envelope contract precursor, not CW-10 operational completion.**

| Acceptance | Integrated/source evidence | Remaining proof |
| --- | --- | --- |
| CW-05–CW-07 conversation/activity | Existing integrated source and prior CI | Staging reconnection/erasure/steering |
| CW-08 selected context/memory | Integrated source | Operated revocation and retention |
| CW-09 brokered read-only browser | #387–#390 merged; #391 unmerged P1 repair | #391 final-head CI/review, private webpage content provenance, isolated egress staging and runtime release gate |
| **CW-10 reviewed generated code** | Inert schema/test review branch only | Database proposal authority, exact human approval, claim validation in existing sandbox, UI, isolation tests and release gate |
| CW-11 versioned skills | Existing fixed static registry | Versioned reviewed manifests after CW-10 core dependencies |

| Evidence level | CW-10 prep |
| --- | --- |
| Implemented | Bounded isolated source/tests/docs |
| Repository-verified | Not yet: draft PR exact-head CI pending |
| Staging-verified | No |
| Production-qualified | No |
| Activated | No: no generated-code route or approval exists |

**Next exact action:** Open CW-10 draft PR, request independent review, inspect exact-head Python tests, coworker mandatory gates and ci-merge-gate. Correct findings before code acceptance. Continue first actual persisted proposal+approval slice separately; never equate a pure validator with an execution permission.


## CW-09 merged release contract P1 corrective slice — 14 October 2026

**Current baseline at bootstrap:** `main` `76a07600328d0c6ff0ed73b69d2c7933d38bf927`. [PR #390](https://github.com/rumman52/Shuddho/pull/390) is **merged** despite three unresolved P1 automated-review findings and exact-final-head [CI #38458791465](https://github.com/rumman52/Shuddho/actions/runs/38458791465) still in progress on inspection. Historical section below refers to the PR as draft; that is superseded by live GitHub evidence. Previously merged #389 [CI #38456526299](https://github.com/rumman52/Shuddho/actions/runs/38456526299) passed required gates, but did not prove the new release contract.

**Repair:** `codex/cw09-release-attestation-repair-20261014`, base `76a07600328d0c6ff0ed73b69d2c7933d38bf927`, initial code/tests head `2e03cb331a8833826d9ffd5a92a015713fe57bb3`; latest source/test head `f07b6da0d416e0794f36155a1473bed0367bfee8` before final docs; exact enabled manifest and newly added deployment rollout digest, strict timestamp ordering, mandatory dedicated kill-switch regressions. PR #391 independent first review flagged [rollout binding P1](https://github.com/rumman52/Shuddho/pull/391#discussion_r4263640759), [stale status P1](https://github.com/rumman52/Shuddho/pull/391#discussion_r4263640771) and [rollback P2](https://github.com/rumman52/Shuddho/pull/391#discussion_r4263640779); all addressed in new source/tests, pending exact-head CI and renewed review. **Draft PR [#391](https://github.com/rumman52/Shuddho/pull/391)**, unmerged. Earlier PR-head `test-and-build` succeeded but was superseded by this test addition; requalify exact final head. Independent review of #390: (1) [P1 recovery/rollback](https://github.com/rumman52/Shuddho/pull/390#discussion_r4263411541), (2) [P1 schema34 missing](https://github.com/rumman52/Shuddho/pull/390#discussion_r4263411549), (3) [P1 manifest missing](https://github.com/rumman52/Shuddho/pull/390#discussion_r4263411559). The repair updates the existing recovery mapping, rollback mode, runtime manifest, HMAC schema 34 validation/append CLI and negative regressions. [Task contract](CW09_RELEASE_ATTESTATION_P1_REPAIR_2026-10-14.md). **No deployment, release proof or production activation.**

| Acceptance | Current source/PR integration | Remaining proof |
| --- | --- | --- |
| CW-05 owned conversations | Integrated source, prior repository checks | Operated owner erasure/duplicate replay |
| CW-06 dispatch, steering, cancellation | Integrated runtime | Real Temporal/recovery/late observation |
| CW-07 active chat/reconnect | #385 merged | Mobile/keyboard/events/reconnect |
| CW-08 context and memory | #384/#386 merged | Owned deletion and source revocation staging |
| **CW-09** read-only brokered Agent browser | #387-#390 merged; new P1 corrective review branch | **Exact-head full CI and independent review of schema34 repair**; bounded webpage text/private digest; isolated egress/SSRF/redirect staging; runtime release eligibility; human acceptance |
| CW-10 inert reviewed generated code | Existing sandbox accepts exact *user-provided* fenced Python | Immutable model-code proposal and exact owner/run/input/limits/egress approval |
| CW-11 reviewed versioned skills | Static code-owned tools | Manifest hashes/grant subset/version rollback |

| Evidence type | Release repair |
| --- | --- |
| Implemented | Branch source/tests/docs checkpoint |
| Repository-verified | **Pending final implementation SHA CI** |
| Staging-verified | Not performed |
| Production-qualified | Not established |
| Activated | No; `agent_browser_read` remains default off |

**Next exact action:** Open draft P1 repair PR and inspect full mandatory CI, especially `tests/test_agent_browser_release_attestation.py`, `tests/test_cohort_recovery_verification.py`, `tests/test_cohort_rollback_completion.py`, `tests/test_coworker.py`, and existing full browser/Temporal/PG suites. Request independent review, resolve findings on actual final SHA, keep no-merge/activation boundary. Continue independent CW-09/CW-10 work only after maintaining this checkpoint.

## CW-09 independent browser.read release gate — 14 October 2026

**Authoritative repository bootstrap:** `main` `d6ba9c183860284207cafd5f8cc2052205080837`; no open PRs at bootstrap. [PR #389](https://github.com/rumman52/Shuddho/pull/389) was already **merged** (the earlier 14 October checkpoint below calling it an unmerged draft is historical and superseded). The exact-head [CI #38456526299](https://github.com/rumman52/Shuddho/actions/runs/38456526299) had successful `test-and-build`, mandatory PostgreSQL/conversation race checks **and** dedicated CW-09 brokered Agent browser suite; its broader `coworker` and merge gate were still in progress when last inspected. Main [CI #38457535194](https://github.com/rumman52/Shuddho/actions/runs/38457535194) also remained in progress. CI success is not staging qualification or permission to activate.

**First dependency-ready gap:** the code-owned `browser.read` flag exists, but controlled release had no independent staging/capability/rollback/activation evidence entry. **Branch:** `codex/cw09-agent-browser-release-contract-20261014`, based on `d6ba9c183860284207cafd5f8cc2052205080837`. **Initial implementation/test SHA:** `a069daf5d2567e84d5bff3c1e525553e1d98d9b4`. **Current code+test SHA:** `f2c8c4099674000a0930c60d09560efe4a2b7e4f` before final docs, including exact gate-map test correction for new default-off key. **Draft PR [#390](https://github.com/rumman52/Shuddho/pull/390)**, unmerged. Initial PR-head `test-and-build` failed only the canonical feature-gate equality assertion (new independent `agent_browser_read: false` absent in old expected map); the test remains strict and has been corrected. Latest final-head CI must be rechecked after this documentation checkpoint. **Task contract: [CW09_AGENT_BROWSER_RELEASE_CONTRACT_2026-10-14.md](CW09_AGENT_BROWSER_RELEASE_CONTRACT_2026-10-14.md). Draft PR not yet opened at this checkpoint; inspect actual GitHub head and CI when reviewing.

**Change:** the canonical rollout gate now recognizes **default-off** `agent_browser_read`, requiring the existing `browser`, `runtime_v3` and `connector_trust_boundary` capabilities, a distinct staged browser Agent read evidence gate, a separate `SHUDDHO_AGENT_BROWSER_READ_ENABLED=false` rollback, and `agent_browser_read_verified` activation ledger proof. Templates remain pending/false. Tests cover absence/default-off, dependency, rollback, and independent activation proof. This patch **does not** add page content capture, mint approval, or enforce live release proof at tool execution; no authority is granted by documentation or rollout registration alone.

| Architecture/core acceptance | Integration evidence | Remaining acceptance |
| --- | --- | --- |
| CW-05 owned conversation | Merged existing source and prior repository checks | Staging replay/privacy/erasure |
| CW-06 dispatch and steering | Merged source and durable dispatch | Operated cancellations/races and UX |
| CW-07 active chat/reconnect | Merged #385, prior exact-head PR CI | UI mobile/keyboard/event cursor |
| CW-08 context/memory | Merged #384/#386, previous exact-head CI | Staging source revocation and memory lifecycle |
| **CW-09 read-only browser** | Merged #387/#388/#389; #389 core safety tests green, full checks pending | New release contract in isolated branch, full content capture and private hash, execution-time canonical eligibility, isolated worker egress/cancel security evidence |
| CW-10 reviewed generated Python | No signed inert code proposal envelope | Proposal hash/approval/sandbox claim and tests |
| CW-11 versioned skills | Static tool contracts only | Reviewed manifest + version/grant subset |

| Evidence level | CW-09 release contract |
| --- | --- |
| Implemented | Review branch with source/templates/tests/docs |
| Repository-verified | **Pending exact final-head CI** |
| Staging-verified | **No** |
| Production-qualified | **No** |
| Activated | **No**; both broker and Agent read flags remain default off |

**Review/next action:** Open independent draft PR; verify exact-head `test-and-build`, `coworker` and `ci-merge-gate`, plus explicit `tests/test_release_contract.py`. Obtain independent review and resolve findings without weakening tests. No auto-merge or flag activation. Continue CW-09 content-capture/private provenance and runtime release enforcement after this contract, and subsequently CW-10/CW-11 in dependency order.

## CW-09 receipt/cancellation correction — 14 October 2026

**Refreshed main:** `fd4cb99a2d7925bcdd0faafad5a3eae041496a80`, after merged [PR #388](https://github.com/rumman52/Shuddho/pull/388). Unlike the historical entry below that calls #388 draft/unmerged, **it is merged**, but [exact-head CI #38432751315](https://github.com/rumman52/Shuddho/actions/runs/38432751315) and [main CI #38436567016](https://github.com/rumman52/Shuddho/actions/runs/38436567016) failed. In PR CI `test-and-build` passed; mandatory PostgreSQL conversation step failed (59 pass, 1 failure, OAuth test setup missing); `coworker` stopped before mandatory CW-09 browser tests; `ci-merge-gate` failed. The merged PR's final automated review identified a remaining **P1 BrowserCommand-before-BrowserSession row-lock inversion** in `finish_invocation`.

**Chosen first dependency-ready task:** Repair exact-session-before-command locking at browser receipt settlement, and correctly configure the real PostgreSQL race tests. **Base:** main `fd4cb99a2d7925bcdd0faafad5a3eae041496a80`. **Branch:** `codex/cw09-receipt-lock-postgres-fixture-20261014`. **Initial implementation+test SHA:** `7afabac1dc6c1fdada5ffdfe20994c60a0cc3aa9`. **Current source/test SHA:** `67df97ab0e125e48e18d3b36a143cf59af98d6b5` before final docs; independent PR #389 review flagged that a cancellation-only race does not lock an already succeeded command, so added an actual PostgreSQL `SELECT ... FOR UPDATE` session-before-command ordering assertion in addition to concurrent receipt/cancel coverage. **Draft PR [#389](https://github.com/rumman52/Shuddho/pull/389)**, unmerged. **Task contract:** [CW09_RECEIPT_CANCELLATION_LOCK_REPAIR_2026-10-14.md](CW09_RECEIPT_CANCELLATION_LOCK_REPAIR_2026-10-14.md). A draft PR will link this branch; never assume it is merged. Configuration uses the existing simulated test OAuth values without bypassing validation; added actual concurrent PostgreSQL receipt/revoke regression, preserving no late receipt and one command invariants.

| Acceptance item | Source / integration status | Unmet evidence / next action |
| --- | --- | --- |
| CW-05 owner messages | Existing integrated ledger | Staging identity/replay and deletion |
| CW-06 dispatch/cancel | Existing integrated source | Operated revocation/steering recovery |
| CW-07 activity continuity | PR #385 merged; prior final-head CI successful | Accessibility/reconnect/event-level cursor |
| CW-08 owner-scoped context | PRs #384/#386 merged with prior successful PR-head CI | Full memory and source-retention qualification |
| **CW-09 brokered read** | PR #387/#388 **merged despite failing mandatory CI**; current receipt/fixture safety repair isolated on review branch | Exact-head CI including real PostgreSQL/browser with no skips; human security review; bounded actual page content + private hash; isolated-worker staging and release eligibility |
| CW-10 generated-code proposals | Only existing sandbox foundation | Immutable inert code review/approval envelope |
| CW-11 reviewed skill manifests | Static tool registry | Version/hash/rollback with fixed authority |

| Evidence level | CW-09 current correction |
| --- | --- |
| Implemented | Review branch, code/test/doc changes |
| Repository-verified | **No**; final-head CI pending |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | No change; independent browser tool flag remains default off |

**Next exact action:** Open the draft PR, inspect exact-head GitHub `test-and-build`, `coworker` PostgreSQL & Agent browser no-skip gates, `ci-merge-gate`, obtain independent review, fix failures, retain blocked production state. Then continue independently dependency-ready CW-08/CW-10 preparation if infrastructure prevents operating CW-09.

## CW-09 post-merge safety recovery — 13 October 2026

**Authoritative bootstrap:** current `main` `8de8aa9bb672f0b77ddb250e3718bc3ae060dfbd`. [PR #387](https://github.com/rumman52/Shuddho/pull/387) was merged at this revision **with failed required exact-head CI** ([run 38412412901](https://github.com/rumman52/Shuddho/actions/runs/38412412901): `test-and-build` pass; `coworker` fail, 1/9 CW-09 mandatory test failed; merge gate fail). Postmerge main [CI 38414646497](https://github.com/rumman52/Shuddho/actions/runs/38414646497) also failed the same gate. Historical lower entries that say PR #387 was unmerged are superseded by this dated correction. No open PR existed when this repair was selected.

**First dependency-ready task:** CW-09 correctness and safety repair before CW-10/11. Five unresolved automated review findings from PR #387 were triaged: (1) cancel broker command with owning Agent, (2) release Agent sessions after receipt, (3) terminally persist attempted worker interaction, (4) Bangla read intents, (5) browser-read questions. The failing test observed an eligible read classified as `unsupported` because previous route ordering allowed other rules to block it.

**Work branch:** `codex/cw09-postmerge-safety-repair-20261013`, based on `8de8aa9bb672f0b77ddb250e3718bc3ae060dfbd`. **Initial implementation/test SHA:** `4a3698db81c00a65c3865f5b93567e23aceb7f34`. **Latest implementation/test SHA:** `d742870d2ce3deef9c1af27518722f9c975f606b` before this checkpoint, also aligning the browser worker-control poll to canonical BrowserSession→BrowserCommand locks and adding a concurrent PostgreSQL Agent cancellation/work-control regression. Earlier source `581f5b63c0db02a1ee59c682c2a3a4acb0062dff` addressed malformed interaction evidence and multilingual intent. The prior revision `e1068cbfea9389a45de5e2d793c8630d43e3496a` added a revoked-session receipt race regression. **Draft PR [#388](https://github.com/rumman52/Shuddho/pull/388)**, still unmerged. **Contract:** [CW09_POSTMERGE_SAFETY_REPAIR_2026-10-13.md](CW09_POSTMERGE_SAFETY_REPAIR_2026-10-13.md). Verify mandatory CI against the latest exact PR head **after this documentation checkpoint**; earlier workflow attempts may be cancelled. The patch strengthens the **existing** Agent and browser ledgers; no replacement engine, migration, live egress or provider actions.

| Workstream item | Current source/integration | Missing evidence and next work |
| --- | --- | --- |
| CW-05 owner message ledger | Merged established source | Operated race/retention and source lifecycle |
| CW-06 conversation dispatch | Merged established source | Operated cancellation/steering and late worker checks |
| CW-07 owned activity cursor | Merged PR #385, prior successful PR CI | Real UI reconnect/mobile/keyboard/event cursor |
| CW-08 selected context/memory | Merged PRs #384/#386, prior successful PR CI | Staging revocation/use races, broader consent lifecycle |
| **CW-09 typed browser** | PR #387 merged **without passing CI**; corrective code on isolated branch only | Final-head CI with no skips, independent review of five findings, real isolated-worker/egress tests, captured webpage content/source digest, canonical release eligibility |
| CW-10 reviewed generated code | Sandbox exists, no immutable approved proposal | Store review/immutable hash envelope and sandbox claim in independent branch |
| CW-11 reviewed skills | Static registry, no reviewed manifest | Validated versioned manifests and authority subset |

| Evidence level | CW-09 correction |
| --- | --- |
| Implemented | Branch only, review pending |
| Repository-verified | **No**; exact-final-head GitHub checks required |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | No new activation; browser tool still defaults off |

**Verification and next exact action:** Open corrective draft PR, verify `test-and-build`, `coworker` including required `tests/test_agent_browser_tool.py` without skips, and `ci-merge-gate` on the final PR implementation revision. Inspect logs for any failed assertions and adjust code/tests only to preserve documented intent. Obtain an independent security review, then run frozen real isolated-worker staging SSRF/cancel/takeover/egress tests. Do not auto-merge or activate. Follow CW-09 with independent dependency-ready CW-10/CW-11 review work when this is repository-verified.

## CW-09 default-off Agent browser metadata read — 13 October 2026

**Refreshed baseline:** `main` at `f5c11ec7db35721190b67212695e7612af63f09f`, with [CW-08 source-consent PR #386](https://github.com/rumman52/Shuddho/pull/386) merged and exact-head [CI #38404758754](https://github.com/rumman52/Shuddho/actions/runs/38404758754) successful; latest main [CI #38408371736](https://github.com/rumman52/Shuddho/actions/runs/38408371736) still in progress when inspected. No open PRs at bootstrap.

**Current bounded CW-09 task:** Register default-off typed `browser.read` as a Runtime v3 tool, qualify explicit user-authored read requests at the public Agent router, and connect it to the existing owner-scoped supervised broker and worker. Deterministic `explicit_browser_url` derives one HTTPS URL from the user's *original run goal*, not a model-chosen destination. Runtime creates/reuses a reserved `agent:<run_id>:<ordinal>` browser session, atomically prepares one read-only navigate command, and persists the broker-verified page URL/title/time/hash as **untrusted metadata-only**, not full page text or HTML capture. No new run or transaction ledger. A separate `SHUDDHO_AGENT_BROWSER_READ_ENABLED` flag defaults off and requires existing browser/v3/intelligent planner dependencies.

**Base:** `f5c11ec7db35721190b67212695e7612af63f09f`. **Branch:** `codex/cw09-brokered-read-metadata-20261013`. **Initial source + regression SHA:** `4d7c2521bdf083177c9f34cd8693007cf75ef535`. **Latest implementation SHA:** `bf155122aa50060fcb682eb978f7a9a8cd5bade3` before this checkpoint commit, including public read-only admission routing and broker no-interaction enforcement. **Final review PR:** [draft #387](https://github.com/rumman52/Shuddho/pull/387), unmerged. Prior CI was superseded by code edits; inspect the GitHub workflow run matching the **current PR head** for `test-and-build`, `coworker`, dedicated mandatory CW-09 browser suite and `ci-merge-gate`; no such final-head pass is yet claimed. **Contract:** [CW09_BROKERED_AGENT_READ_METADATA_2026-10-13.md](CW09_BROKERED_AGENT_READ_METADATA_2026-10-13.md). **Draft PR:** [#387](https://github.com/rumman52/Shuddho/pull/387), still unmerged; dedicated no-skip test step added in `.github/workflows/ci.yml`. Final implementation/test SHA preceding this documentation checkpoint: `c596a3e9ed4af211fbfaf4e65e3413079d53ae45`. Latest exact-head CI must be refreshed after this commit; older runs were superseded.

| Item | Verified/current state | Pending acceptance |
| --- | --- | --- |
| CW-05 owned messages | Merged ledger/owner source + prior repository tests | Staging races/replay and deletion |
| CW-06 dispatch/cancel | Merged routing/dispatch, revision cancellation | Operating steering and terminal precedence |
| CW-07 activity continuity | PR #385 merged, full final-head CI passed | Mobile/keyboard/reconnect operated evidence, event-level cursor |
| CW-08 pinned context/memory | PR #384 and #386 merged, exact-head PR CI passed; prior-task implicit read sealed for conversations | Full lifecycle/revocation races, broader purpose consent, multilingual human acceptance |
| CW-09 browser read | Current branch: metadata-only typed v3 tool with default-off flag/broker command+receipt | Exact-head CI, actual page-body/private digest, real worker/SSRF/redirect/egress and release gates |
| CW-10 generated code | Sandbox foundation exists; approval-bound immutable code proposal not completed | Independent code-proposal and sandbox approval route |
| CW-11 skill manifests | Static skill registry; reviewed manifests not completed | Version/hash, authority subsets, compatible rollback |

| Evidence | CW-09 metadata slice |
| --- | --- |
| Implemented | Branch-only code + synthetic worker/broker tests |
| Repository-verified | Pending exact-final-head no-skip GitHub Actions |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | **No** — flag remains default-off |

**Review:** Self-review only. Explicit user URL and reserved server resource identity reduce planner authority; test covers denied destinations and replay. A separate full content capture and canonical release eligibility policy still need integration; metadata hash is explicitly not claimed as web content hash. An independent security reviewer and frozen live isolated-worker evidence are mandatory before activation. Existing PHP/Node/web dependencies, transaction provider and writing/DeepSeek configuration remain unchanged.

**Next exact action:** Open draft PR and verify current-head `test-and-build`, `coworker`, `ci-merge-gate`, and targeted `tests/test_agent_browser_tool.py`. Resolve any failure, obtain independent review, then implement CW-09 bounded page-body capture/private checksum on its own review slice or advance independent CW-10 proposal contract. Do not merge or activate automatically.

## CW-08 explicit conversation source-selection boundary — 13 October 2026 (Asia/Dhaka)

**Repository bootstrap:** `main` `b2a6920d2fea10dfc5a813746e19c7241597846b`. [CW-07 PR #385](https://github.com/rumman52/Shuddho/pull/385) was **merged**; its final-head [CI #38402405574](https://github.com/rumman52/Shuddho/actions/runs/38402405574) was still in progress as inspected, so completion of its broad checks is not inferred. New main [CI #38403290676](https://github.com/rumman52/Shuddho/actions/runs/38403290676) also in progress. No other open PRs at bootstrap.

**Selected dependency-ready task:** CW-08's selected-only conversation planning context. Source finding: `ContextService._resolved` included lexical-matching prior completed/needs-input `Task` content from the owner workspace even when a conversation message carried `selected_sources=[]`. The conversation admission ledger bound only selected document versions; this prior-task inclusion lacked message source consent. **Repair** bypasses implicit prior-task retrieval for server-created conversation Agent runs, retaining standalone Agent compatibility and already-enforced conversation document pin, owner, revocation and checksum checks.

**Base and branch:** `main` `b2a6920d2fea10dfc5a813746e19c7241597846b`; `codex/cw08-explicit-conversation-context-20261013`. **Implementation/regression SHA:** `00cbe0d8dbe32a242dc458c83fc37ed383941d52` before documentation. **Task contract:** [CW08_EXPLICIT_CONVERSATION_CONTEXT_2026-10-13.md](CW08_EXPLICIT_CONVERSATION_CONTEXT_2026-10-13.md). **Review:** [draft PR #386](https://github.com/rumman52/Shuddho/pull/386), original review head `bd5e5bfaa7fdbc545e22e13d9b2a6e61e55ea308` before this final checkpoint; required exact-current-head CI [run 38404234208](https://github.com/rumman52/Shuddho/actions/runs/38404234208) was in progress and will be superseded by new commits. Always refresh the actual PR head and checks before closure. A same-owner real completed task with private notes/draft is excluded from an unselected conversation's planner and context while remaining available to existing direct Agent continuity.

| Scope requirement | Integration/evidence | Unmet acceptance |
| --- | --- | --- |
| CW-05 messages | Existing merged implementation, prior tests | Operated consent/replay/race/deletion qualification |
| CW-06 routing and revisioned cancellation | Existing merged implementation | Steering and late/cancel operational checks |
| CW-07 resumable activity and UI | PR #385 merged; final-head broad CI pending when inspected | Verify exact-main CI, independent/mobile/reconnect and combined event cursor |
| CW-08 context and reviewable memory | Pinned source integrity #384 merged; new prior-task consent repair only on review branch; memory edit/delete UI exists | Exact-head CI, source revocation race, explicit whole-context consent, Bangla/English task evidence |
| CW-09 typed browser read | Isolated browser broker/worker but no Agent `browser.read` registered at inspection | Typed default-off dispatch and isolated SSRF/takeover validation |
| CW-10 reviewed generated code | Sandbox foundation only | Stored immutable approved code-to-execution envelope |
| CW-11 versioned skill manifests | Static skill registry only | Validated reviewed manifest and rollback after CW-09/10 |

| Evidence level | This CW-08 slice |
| --- | --- |
| Implemented | On isolated branch only |
| Repository-verified | Pending exact-final-head PR `test-and-build`, `coworker`, `ci-merge-gate`; local full-repo execution unavailable |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | No flags or external authority changed |

**Review:** Self review before PR; no independent review claimed. Owner-bound conversation prefix only comes from server dispatcher and is already protected at worker-use context source validation. Existing standalone Agent retrieval intentionally unchanged. The cursor in merged CW-07 remains message-based, not per-Agent-event. No new schema, orchestration engine, ledger, provider credential, grant or rollout.

**Next exact action:** Open draft PR for `codex/cw08-explicit-conversation-context-20261013`, compare exact PR SHA and required CI, resolve failures without weakening tests, seek independent review and only then classify repository verification. Continue an independent CW-08 lifecycle or CW-09 browser capability slice without merging or production activation.

## CW-07 Architecture/Core Agent — owned activity cursor continuation (13 October 2026)

**Fresh repository evidence:** `main` at `4b369fa99b9a7c4784f5060aa3399a58e340815f`. [CW-08 source-pin PR #384](https://github.com/rumman52/Shuddho/pull/384) is **merged**, and its exact-final-head [CI #38395801164](https://github.com/rumman52/Shuddho/actions/runs/38395801164) passed. Main CI [38400940687](https://github.com/rumman52/Shuddho/actions/runs/38400940687) was in progress at bootstrap; a skipped separate run does not count as green. There were no open PRs when selecting this new bounded slice.

**Active task:** CW-07 — durable owner-bound cursor pagination for the read-only continuous-chat activity projection. Main only exposed latest-N activity, so older launched work cards were missing on reconnect for longer conversations. The current slice adds `after=start` + forward owner/conversation-bound cursor, `next_cursor`, `has_more`, HTTP support, frontend paginated replay and regression tests, without another run ledger or side effect. Omitted `after` retains latest-N polling for run-state changes with no new message. The cursor is an owned read checkpoint, not a permission grant or durable all-events stream.

**Review branch:** `codex/cw07-owner-bound-activity-cursors-20261013`. **Base:** `4b369fa99b9a7c4784f5060aa3399a58e340815f`. **Initial implementation/test:** `99d3934803227721f4d2e0dac71b65686be52329` (prior to documentation). **Contract:** [CW07_OWNER_SCOPED_ACTIVITY_CURSOR_2026-10-13.md](CW07_OWNER_SCOPED_ACTIVITY_CURSOR_2026-10-13.md). PR and final exact-head CI must be read from GitHub once created.

| Acceptance item | Current code/integration | Remaining qualification |
| --- | --- | --- |
| CW-05 message ownership | Existing main source and prior CI | Operated replay, deletion and PostgreSQL races |
| CW-06 routing/admission/cancel | Merged CW-06 #383 and durable dispatch | Steering, terminal-order and operated cancellation |
| CW-07 unified activity | Owner cursor + frontend history replay on current review branch only | Exact-head CI, independent review, mobile/keyboard/reconnect and live run-state proof |
| CW-08 workspace/memory | Merged pinned-source #384; existing memory edit/delete and manifest | Source-use races, bounded context + human multilingual acceptance |
| CW-09 browser | Broker/workers exist but no registered v3 `browser.read` | Gated typed tool, SSRF, takeover, worker tests |
| CW-10 reviewed generated code | Sandbox exists | Immutable approved proposal-to-execution envelope |
| CW-11 skill manifests | Static skills exist | Reviewed manifest validation and authority subset |

| Evidence level | CW-07 cursor slice |
| --- | --- |
| Implemented | Yes, only on isolated review branch |
| Repository-verified | Pending exact-final-head mandatory GitHub Actions; no local full-repo pytest/build |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No authority, provider, flag, paid resources or production changes |

**Next exact action:** Open draft PR for CW-07 branch, inspect final-head `coworker`, `test-and-build` and `ci-merge-gate`, correct test/source issues and seek independent code review. Do not merge automatically. Continue remaining dependency-ready CW-08/CW-09 implementation separately after evidence checkpoint. No success percentage inferred from task labels.

## CW-08 Architecture/Core Agent continuation — 13 October 2026 (Asia/Dhaka)

**Source baseline:** `main` at `fb3c8994edc2d6a7db2781b9a798a21a7a9beec6`. Main CI [38393963804](https://github.com/rumman52/Shuddho/actions/runs/38393963804) was in progress when inspected; no claim of successful final-head CI is made for it. Earlier CW-06 [PR #383](https://github.com/rumman52/Shuddho/pull/383) is **merged**; final PR SHA `1312877604520fec49e00970d12ff14a4b9c7294` passed [CI 38391641647](https://github.com/rumman52/Shuddho/actions/runs/38391641647). No open PRs appeared before this CW-08 work.

**Selected task:** CW-08 worker-time conversation source-pin enforcement, scoped to a single reviewable code slice. `ConversationMessage.selected_sources` already preserves exact version/hash/owner selection, but `AgentRun.input_versions` records only IDs and `ContextService._run_and_sources` previously trusted the *current* DocumentVersion row at worker time. A same-ID in-place changed digest/version could bypass the admitted selection. The new shared validator revalidates the original owner-scoped message, document pin, run link and live resource status both at `AgentRepository.worker_run` entry (v1/v2/v3) and at planner context load; pre-existing non-conversation runs retain their former logic.

**Branch:** `codex/cw08-conversation-pinned-context-20261013` from `fb3c8994edc2d6a7db2781b9a798a21a7a9beec6`. **Implementation/test head:** `cea2c57eeb1ddd2c38526c9a2e8475333526a11f` before checkpoint update. **Task contract:** [CW08_CONVERSATION_SOURCE_BINDING_2026-10-13.md](CW08_CONVERSATION_SOURCE_BINDING_2026-10-13.md). **Review PR:** [draft #384](https://github.com/rumman52/Shuddho/pull/384); exact final head and CI are verified on the PR.

| Acceptance task | Source evidence level | Remaining gate |
| --- | --- | --- |
| CW-05 owner-scoped messages | Existing implementation and prior main CI | Staging race/replay/deletion qualification |
| CW-06 bounded message dispatch/cancel | Merged CW-06 routing repair, previously green exact-head CI | Full steering and operational cancellation proof |
| CW-07 continuous activity | Existing UI and owner-scoped activity projection | Cursor/reconnect/mobile and staging qualification |
| CW-08 context/memory | Existing source and memory controls; new exact conversation pin worker check on review branch | Final-head CI, live revoke/replacement race, remaining bounded context/memory lifecycle and quality review |
| CW-09 browser read | Existing broker/isolated worker, no registered Agent `browser.read` | Gated typed integration and isolated-worker testing |
| CW-10 reviewed generated code | Existing sandbox control plane | Immutable reviewed code proposal/approval/execution binding |
| CW-11 skill manifests | Existing static versioned work skills | Reviewed manifest hashes, authority subsets and compatible rollback |

| Evidence level | CW-08 source-pin task |
| --- | --- |
| Implemented | Branch-only implementation + focused regression cases |
| Repository-verified | Pending required exact-final-head PR CI; local full-repository pytest not run |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | None; no grant, provider or rollout changed |

**Next exact action:** Inspect draft PR #384 exact-PR-head `coworker`, `test-and-build` and `ci-merge-gate`; fix source defects without silencing tests; obtain independent review. Then continue remaining dependency-ready CW-08 and CW-09 code slices in separate PRs. No merge or production activation is authorized by this execution prompt.


## Current Architecture/Core Agent checkpoint — 13 October 2026

Refreshed default branch: `main` at `339d6924b244c0bb1641764dabd68c4f55488bb3`. Exact-main CI [run 38338728994](https://github.com/rumman52/Shuddho/actions/runs/38338728994) passed its coworker, test-and-build and merge-gate jobs. No open PR was returned before beginning this slice.

CW-06 contract gap: the `report.create` registered tool declares public capability `report` but internal durable task skill `report_email`. The old single-tool router emitted the internal skill into public route decisions while `tests/fixtures/core_agent_route_cases.jsonl` expects `report`. This finding is based on current canonical tool/route source, not historical completion percentages.

Review branch `codex/cw-core-router-report-contract-20261013`, [draft PR #383](https://github.com/rumman52/Shuddho/pull/383), initial implementation/test head `aeb00b2cdd5994e3e8236bc049d2f916f9ad7862`. Changed only the single-tool router capability mapping to server-owned route intent and added a regression asserting that the public `report` route still uses `report.create` and the legacy `report_email` skill. The reviewed task contract is [CW06_REPORT_ROUTE_CONTRACT_2026-10-13.md](CW06_REPORT_ROUTE_CONTRACT_2026-10-13.md).

| Evidence level | Status |
| --- | --- |
| Implemented | On isolated review branch; not integrated into `main` |
| Repository-verified | Pending exact-final-head PR CI; local package tests not run in this GitHub connector environment |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | No provider, capability, or production activation |

Scope: CW-05–CW-11 Architecture/Core Agent. CW-01–04 supply prerequisite evidence, not renewed assignments. The merged CW-09–14 qualification registry is a default-off metadata foundation, not a working browser/generated-code/skill runtime or live release qualification. Preserve prior transaction checkpoints below as historical. Pending CW-08 context/memory integration and CW-09–11 actual implementations must be rechecked against live source; staging/billing/provider/human evidence cannot be inferred from CI.

Acceptance inventory based on inspected `main` source and available CI (per-task staging and full acceptance remain separate):

| Task | Main source / current state | Next unmet acceptance / evidence |
| --- | --- | --- |
| CW-05 | Conversation schemas, repository and durable message tests exist; main CI includes PostgreSQL conversation races | Complete operated owner/deletion/replay qualification on a frozen staging release |
| CW-06 | Atomic conversation dispatch and revision-checked cancellation exist; one report public-route mismatch repaired only on PR #383 | Verify PR exact-head CI; inspect missing/non-mutating steering contract and late-result precedence |
| CW-07 | Conversation UI and read-only activity projection exist | Verify reconnect/mobile flows and add durable owner-scoped activity cursor if canonical contract remains unmet |
| CW-08 | Source admission validation and read-only workspace manifest exist | Prove worker-use revocation/version checks, reviewable memory edits/deletion and bounded multilingual context |
| CW-09 | Isolated browser broker/worker foundation exists; no `browser.read` in core `agent_tools.py` | Register and safely wire typed default-off read-only tool; prove SSRF/ownership/takeover boundaries |
| CW-10 | Isolated sandbox control plane exists | Store immutable generated-code proposals and exact reviewed approval binding before execution |
| CW-11 | Static versioned `WorkSkill` definitions exist | Validate reviewed manifest hashes, tool authority subset and compatible rollback after CW-09/10 |

These are discovery statuses, not assertions that each full CW acceptance suite has passed. A successful green CI run on a revision does not substitute for missing staging, adversarial or human quality evidence.

Next exact action: inspect exact-head GitHub Actions on PR #383 and obtain independent review; if a check fails, repair code without weakening expected behavior. Then choose the next smallest dependency-ready CW-08/09/10/11 capability slice while keeping external activation gated.


## Current Transactions qualification recovery — 13 October 2026 (Asia/Dhaka)

Refreshed main: `fb1a08059cd242f5da4d72dbf72da0c6971bfe30`, latest merge PR #379.
PR #375 process recovery, #376 attestation chronology/file binding and #377's
checkpoint are now merged. There were no open PRs at the start of this continuation.
[Exact-main CI 38292932568](https://github.com/rumman52/Shuddho/actions/runs/38292932568)
failed both required upstream jobs: lightweight collection imported optional
SQLAlchemy without a guard, and Temporal `before_claim` recovery hit the workflow
deadline. The merged boundary/reconciliation tests were absent from the explicit
heavyweight transaction safety command.

Branch `codex/transactions-ci-recovery-20261013` repairs that qualification boundary:

Review: [PR #380](https://github.com/rumman52/Shuddho/pull/380). Initial implementation
head: `7ae84f757a696116f3aade9aaeeced296b7078a3`. This checkpoint precedes the final
required CI result; the PR records its final head/run and review readiness.

- Optional-dependency collection follows the existing lightweight/heavyweight split.
- All newly merged execution, reconciliation and mutation-guard test modules are
  mandatory in the safety JUnit report, with collection and zero-skip checks.
- A parent-owned barrier keeps the restarted real Temporal worker connected but
  not polling while only the interrupted activity timeout/first retry is advanced.
  Automatic result time skipping is then disabled. Production workflow timeouts,
  authorization, durable claims, receipt validation and uncertainty remain unchanged.
- Enabling the omitted reconciliation test reproduced a nonexistent fixture field
  (`SimulatedGoogle.provider`). Its corrected receipt assertions check the actual
  configured Google provider, confirmed state, one send and another owner's 404.
- Added execution diagnostics identify the exception class before the Temporal
  activity redacts its error; that diagnostic prints no raw SQL parameters,
  credentials or message contents.

Local verification: the lightweight project suite passed **1,052 tests, 65 optional
skips** (8.56 seconds); the final combined process/Temporal/HTTP/safety/boundary run
passed **41 tests with one PostgreSQL-only admission-race skip** (60.14 seconds).
The mandatory safety subset passed **25 tests, zero skips** (4.88 seconds), and
its gate confirmed collection from all five required modules. Neighboring transaction/
action/permission/gate checks passed **103 tests** (46.58 seconds).
The initial combined run also failed before its first crash barrier;
four isolated Temporal cases and the final combined run passed after adding safe
setup diagnostics. These local SQLite runs do not establish PostgreSQL qualification.
The required exact-head CI must run all 17 process cases on real PostgreSQL and
all 25 transaction safety cases with zero mandatory skips before review readiness.

| Evidence level | Current status |
| --- | --- |
| Implemented | Bounded test/CI repair exists on the review branch |
| Repository-verified | Pending exact final-head required CI; record its SHA/run in the PR |
| Staging-verified | Not established by this continuation |
| Production-qualified | Pending operated matrix, selected-provider evidence and release reviews |
| Activated | No capability/provider/production activation |

PR #379's `TransactionMutationGuard` is an unused, process-local qualification helper:
its unit tests do not establish distributed provider deduplication. Production
authority remains the existing durable ExternalAction boundary. Complete Transactions
qualification still requires the full sixteen-fault operated staging matrix and
selected real-provider receipts/counters; shopping/travel registration remains disabled.

Next exact action: independently review this repair, inspect exact final-head CI,
then collect the controlled staging/provider evidence on a frozen matching release.
See [the bounded task plan](../superpowers/plans/2026-10-13-transactions-qualification-recovery.md).

## Historical process-recovery checkpoint — 12 October 2026

Reviewed main `1c41907594dd8dd93a6eac747494d5491587b709` (PR #373); merged-main CI #1368
passed `test-and-build`, `coworker` and `ci-merge-gate`. Draft PR #374 remains a separate
offline CW-02–04 witness-gate proposal. Historical entries below predate newer merges.

Branch `codex/cw02-transaction-process-recovery-20261012` implements the next CW-02 slice:
counted real HTTP to a loopback provider, abrupt disposable worker loss at four commit/
dispatch boundaries, the same four boundaries in real Temporal activities, six provider
failure/uncertainty cases, PostgreSQL public-API duplicate admission, hard API loss after
commit and actual Temporal-server unavailability/outbox recovery. Seventeen executable
tests are mandatory in the heavy CI job, with PostgreSQL required and zero skips allowed.

Review PR: [#375](https://github.com/rumman52/Shuddho/pull/375). Initial implementation
commit: `b8a5a2b2130991b383cc8a9bfd16472b903a8ed4`; the follow-up also binds restarted
Temporal worker readiness before unlocking its virtual retry clock. The PR check suite
records the exact final head and required CI evidence; this checkpoint precedes that result.
CI run `38240791655` remained in rendering dependency installation for more than fifteen
minutes. The final follow-up makes apt/debconf/needrestart noninteractive and bounds the
installer to ten minutes, triggering a fresh runner without removing any required check.
The cause of the stalled installer was not observable from unfinished GitHub job logs.

The final focused local process/Temporal/HTTP plus existing safety/matrix run passed
35 tests with one explicitly PostgreSQL-only skip (46.14 seconds). The new module itself
passed sixteen tests and skipped its PostgreSQL admission race. Surrounding transaction/
permission/action checks passed 97 tests (38.63 seconds). Exact-head full CI with real
PostgreSQL and zero mandatory skips remains required before repository qualification.

No production source interface, migration, provider authority or activation changed.
JUnit records are integration evidence with a simulated provider, not live certification.
CW-01 and CW-05–07 foundations are on main; CW-08 continuity remains partially qualified.
CW-02–04 full operated staging, exact provider reviews and CW-14–20 release requirements
remain unfinished. Do not activate transactions from this slice alone.

Next: review the new source/test/CI changes, verify exact-head CI, then execute the full
sixteen-fault matrix on a frozen controlled staging release with independent provider
counters. See [the task contract](CW02_PROCESS_RECOVERY_TASK_2026-10-12.md).

## Historical checkpoints

Updated: 11 October 2026 UTC. Base: `c6389b3702aae93019c2ec5643f4e4d5dd76ea2a`.
The coding kit from PR #362 is merged.

## Three-stage execution

| Stage | Tasks | Status |
| --- | --- | --- |
| 1. Safety and operated foundation | CW-01..04 | CW-01 implemented and locally verified; full recovery/deployed qualification pending |
| 2. Continuous coworker | CW-05..13 | CW-05 in progress; later tasks planned |
| 3. Transactions and production pilot | CW-14..20 | Provider/live review and operated evidence required; not qualified or activated |

## CW-01 result

Branch: `codex/cw01-safety-foundation-20261011`.
Repairs invalid fixtures/assertions without changing production behavior; same binding
replays and another action conflicts. Simulated real-transport tests count dispatches and
applied mutations after a lost reply, check actual approval/claim expiry and exact receipts.
The existing coworker CI job runs a separate mandatory suite with locked extras,
JUnit upload and empty/skip/failure/error/required-module rejection.

Verification:
- Original three tests reproduced three failures before reaching the safety boundary.
- Final focused transaction/gate suite: **44 passed, zero skips**, 17.18 seconds.
- Surrounding action/permission/personal-transaction suite: **57 passed, zero skips**, 25.92 seconds.
- Chaos-only CLI gate: **5 collected, zero skips/failures/errors**.
- Fresh review: no Critical findings; one Important mandatory-collection gap fixed
  with a failing regression, required-module check and separate reports.
- Deferred minor: successful replay checks applied mutations but could also assert
  HTTP dispatch count; lost-reply coverage already checks both.
- Exact-head remote CI pending. Local checks do not establish complete repository CI.

Existing PR #363 is open/conflicted at inspected head
`3ba85a5c66582dc9cd27a5e7653291ec97c099f4`; it still calls unsupported
interfaces and installs missing requirements.txt. This main-based branch replaces that
repair; maintainers should retain one implementation, not merge both conflicting patches.

## External qualification blockers

Fresh local CW-03 preflight: `blocked_external: RENDER_API_KEY REQUIRED`.
This execution has no Render connector, staging synthetic identity, Temporal credentials
or private S3 access. Historical PA-10 billing/worker observations were not re-certified.
CW-02 needs the full public API/PostgreSQL/Temporal process-interruption matrix.
CW-04 requires matching frozen API/worker/model/rollout identity.
CW-12..20 additionally require live connector/push/provider access, concrete registered
shopping/travel providers, human Bangla/English and security review, real cost/load,
restore/rollback and an operated availability window.

## Scope and next action

CW-05 may proceed independently while staging access is blocked. Use existing task/run
outboxes and ledgers for CW-06/07. Preserve all capabilities default-off; this work has
not activated production, broadened provider authority, provisioned paid infrastructure,
or executed external sends/purchases. All CW-02..20 acceptance gates remain unfinished
until their exact evidence passes. Refresh main/open PRs/CI before resuming.

## Latest five-commit security and integration review — 12 October 2026

Reviewed main head `ec41ac8b55de99a50e8214a58b22bfc797ae5256` and the four preceding main commits
(`79070ea`, `039093b`, `bb77b28`, `b90b6a4`).

- CW-05 PR #368 is now merged into main. PR #369 marked merged **into the CW-05 feature branch**, not main, so CW-08 source revalidation did not reach main from that merge.
- Repaired CW-05 source selection to reject an expired uploaded document version before message admission; previous behavior pinned expired documents.
- Ported CW-08 read-only, owner-bound document/artifact source revalidation and its seven tests to a new main-based review branch. This is a foundation, **not yet connected to CW-06 admission**.
- Added both the CW-08 unit tests and the PostgreSQL conversation-race module to mandatory coworker CI gating.
- Source changes remain default-off; exact-head CI and PostgreSQL migration/race evidence must be independently reviewed.
- CW-01 source safety foundation remains implemented. CW-02–04 operated staging checks and CW-06/07/08 full task-level acceptance criteria remain incomplete.
- Do not turn on conversations, transactions, or external-action providers from this patch alone.

Next: review/qualify this branch, merge through normal protections, implement CW-06 atomic admission/steering with source validation at the same transaction boundary, then CW-07 UI and complete CW-08 workspace/context lifecycle.


---

## Core routing authenticated API regression repair — 16 October 2026 (Asia/Dhaka)

**Base:** main `badc8bbb66c8ead4a43c3463e32112b1bfd7e996`. Independent [PR #422](https://github.com/rumman52/Shuddho/pull/422), branch `codex/core-router-api-regression-20261016`; CW-10 conversation scope remains on separate [draft PR #421](https://github.com/rumman52/Shuddho/pull/421), source head `27c32e37a89da3af25b14d9757273329dd46e4e0` (164 focused passes; exact-head CI pending at this checkpoint).

**Observed full-suite failure:** `tests/test_core_agent_router.py::test_simple_question_does_not_create_agent_run` raises AttributeError because the stale Agent test double lacks the actual API's `public_idempotent_replay` method. Independently reproduced on unchanged main. The lightweight CI skips the boundary without JWT and the heavy pytest list omits that module. This finding does not establish incorrect production routing.

**Bounded repair:** move the single API boundary test to existing authenticated/DB `test_coworker.py` fixtures, assert two direct-answer refusals and no AgentRun/AgentOutbox/Task. Retain lightweight pure routing tests. Include the precise API test node and required-module gate in the already mandatory no-skip conversation/PG report. No product code or authority changed. [Contract](CORE_ROUTER_API_REGRESSION_2026-10-16.md).

**Local evidence:** pure routing plus real API boundary **18 passed, zero skips**, mandatory JUnit gate passed. Initial real fixture enabled research without credentials; removed that unrelated flag and revalidated settings. Independent read-only agent review found no Critical/Important/Minor findings; this is not human security certification. Full branch pytest and exact new PR-head mandatory CI pending. The separate #421 full run finished 2068 passed, 70 service skips and the one stale test failure (480.60s). Do not infer repository-wide qualification or merge/activation from this focused result. All C-04/CW-11 and operated A/P/V gates remain unfinished.


**Integration:** this entry is appended rather than prepended to avoid conflicting with #421's simultaneous canonical-progress prepend. Both PRs remain separately reviewable against the same base; refresh main/CI after either is integrated. Direct git push was unavailable (no transport credentials); authorized connector writes were used and remote/local Git tree identities verified.


---

## CW-02 artifact storage failure continuation — 19 October 2026 (Asia/Dhaka)

**Refreshed main:** `1344348707066556a0a21e4ec0620e16499294cf`, merge commit for [PR #465](https://github.com/rumman52/Shuddho/pull/465). The export-write failure regression and cleanup are now on main. At the checkpoint refreshed for this follow-up, the `test-and-build` job passed but the required `coworker` job remained in progress; do not describe the exact main revision as fully CI-verified until that job finishes.

**Next bounded slice:** branch `codex/cw02-storage-read-recovery-20261019` now tests (1) transient required-artifact GET failure at the actual `DocumentRunner.phase(..., "complete")` boundary, with no terminal success or published Artifact records and a retry that verifies existing bytes without additional object PUTs; and (2) a lost database response after the export checkpoint commits. The second case exposed a data-loss hazard in PR #465's cleanup logic: a committed checkpoint could reference blobs that unconditional exception cleanup then deleted.

**Correction in this branch:** partial-export cleanup runs only before checkpoint submission. Once checkpoint submission starts, the commit outcome is uncertain, so object deletion is suppressed; retry observes a committed checkpoint and reuses its referenced objects. This deliberately favors preserving potentially referenced data over eager orphan cleanup. Exact-head CI is required before merging.

**Evidence boundary:** test-store fault injection is not live S3 staging evidence. Persistent storage outage, cleanup after hard process death, the remaining CW-02 fault matrix, CW11-STAGING mixed-version drain, browser/sandbox isolation and complete personal-coworker scenarios remain unqualified. No deployment, provider activation or production action was performed.

---

## Architecture/core closure — C-01 terminal completion/replan finality (20 October 2026)

- **Starting main:** `79c111d7bc3ec8ae1ad65b55e4f78595aec54e46` already includes merged #485. The concurrent draft #486 addresses late tool start/receipt; this slice intentionally does not modify it.
- **Root cause:** `complete_run` could turn a v3 run already `needs_input` or `blocked` into `completed` if existing receipt counts match. `replace_remaining_plan` could also change prepared tool steps after a terminal outcome.
- **Correction:** [PR #487](https://github.com/rumman52/Shuddho/pull/487) inserts v3-only `agent_run_closed` checks under the owning AgentRun row lock. Already-completed and cancelled idempotence and legacy v1/v2 behavior are preserved. [Contract](C01_TERMINAL_COMPLETION_REPLAN_FINALITY_2026-10-20.md).
- **Evidence:** five regression test instances committed before implementation; the CI suite now explicitly includes this module with a required-module/no-skips gate. Mandatory exact-head CI and independent review pending. No live staging, worker-restart, PostgreSQL race, provider cost, human security signoff or production activation claimed. C-01/A-02 and full Architecture/Core acceptance remain incomplete.

---

## Architecture/core closure — C-01 committed decision replay after deadline (20 October 2026)

- **Starting main:** `9d830f3d7f9fe405020a45c42ab99bf05dea5b65`, merged PRs #486/#487 preserved. [PR #488](https://github.com/rumman52/Shuddho/pull/488) covers a distinct committed-activity replay/deadline ordering gap.
- **Defect:** `decide_v3` checked the task deadline before looking up an exact committed retry result. A lost response retried after expiry could reject an already-durable result; the no-tools repository helper had a similar internal race.
- **Scope:** move only the committed-result lookup ahead of deadline validation, keeping cancellation first and maintaining deadline checks on all *new* work. [Task contract](C01_V3_DEADLINE_REPLAY_2026-10-20.md). No new provider calls, ledger, flags or authority.
- **Evidence:** five cases committed before implementation, plus one internal no-tools helper test; mandatory test module collection already configured in CI. Exact final-head CI, independent review and operated PostgreSQL/Temporal qualification remain open until verified. Full A/C/P/V not closed.

---

## Architecture/core closure — C-01 late-inference deadline write fence (20 October 2026)

- **Base:** `main` `b1cb627b620a6ab7706efb5e41a67018a46100af` includes merged #488. This task is a separate commit-time validity defect, not a duplicate of committed retry replay after deadline.
- **Defect:** the provider can finish after expiry; `record_v3_decision` checked terminal state and context but not the deadline, allowing fresh `needs_input`/`blocked`/`wait` outcomes to persist late.
- **Review branch:** [PR #489](https://github.com/rumman52/Shuddho/pull/489) adds the deadline fence under the existing run lock before fresh decision persistence, preserving exact previously committed replay and provider usage settlement. [Task contract](C01_LATE_INFERENCE_DEADLINE_FENCE_2026-10-20.md).
- **Evidence:** five tests committed before implementation, one direct-record test added during patch. Full exact-head CI and independent review pending; no live PostgreSQL/Temporal operated staging evidence or production activation. C-01/A-02 and full A/C/P/V inventory remain incomplete.


## C-04 / CW-10 worker lifetime and cleanup — 20 October 2026

- Dedicated branch `codex/cw10-sandbox-cleanup-order-20261020`, base `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`. [Task contract](CW10_WORKER_LIFETIME_CLEANUP_2026-10-20.md).
- Five real local subprocess regressions failed before implementation: source/scratch still present during normal/lost-response completion, cleanup failure after a false destruction claim, blocked-control wall overrun, and unexpected supervisor exception leaving code alive. A watchdog now enforces wall/disk limits during control I/O; final cleanup always reaps a live child; completion is published only after output handles and private directories close.
- Independent review found an Important watchdog exception hole. A sixth real-child regression reproduced thread termination on RecursionError; unexpected inspection exceptions now fail closed and stop the child. Reviewer also independently verified interactive output preservation and Thread.start failure cleanup. No remaining substantiated Critical/Important finding is open in this slice.
- Final sandbox/lifecycle/code-proposal suites: **189 passed, zero skips**, six existing Pydantic invalid-input serialization warnings. Mandatory lifecycle collection and syntax checks passed. Required exact-head CI remains pending at publication.
- Tests substitute namespace launch with a real local child; they establish supervision/cleanup ordering, not real bubblewrap, mount/network isolation or memory zeroization. This host cannot create the required bubblewrap UID mapping. Staging preflight lacks RENDER_API_KEY. C-04, other A/C/P/V gates, human security review and production qualification remain open. No merge, deployment, activation, policy version, approval or capability-default change.
