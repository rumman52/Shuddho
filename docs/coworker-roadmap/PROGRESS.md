# Coworker evolution progress

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
