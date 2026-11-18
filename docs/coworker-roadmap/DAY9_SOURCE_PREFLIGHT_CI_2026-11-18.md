# Day 9 — mandatory source preflight in Coworker CI (18 November 2026)

- **Objective:** enforce the already canonical Day 9 source-only validation commands in required exact-head Coworker CI, without accessing held-out inputs or changing any runtime behavior.
- **Dependency and source truth:** [Day 9 #735](https://github.com/rumman52/Shuddho/issues/735); [operator contract](DAY9_PILOT_QUALIFICATION_2026-11-12.md); [independent holdout blocker #665](https://github.com/rumman52/Shuddho/issues/665). The native fault-boundary issue was independently fixed in merged [#774](https://github.com/rumman52/Shuddho/pull/774) after main CI [#44278207003](https://github.com/rumman52/Shuddho/actions/runs/44278207003) reproduced the two stale fixtures; this PR does not repeat it.
- **Starting base:** `main` at `aa705726f4c76cbb819a62211b7743aa44c59b17`, with reviewed-branch head pinned by the PR.
- **Reproduced missing gate:** GitHub readback of `.github/workflows/ci.yml` on this exact base shows **zero occurrences** of the direct `ruke_pilot_eval validate-registry`, `ruke_pilot_eval preflight` or runtime-v3 qualification helper commands, despite #735 requiring all three. Full Python CI runs source tests and the release-contract checker, but does not directly gate the CLI or explicitly check this helper suite for skips.
- **Existing interfaces:** `scripts.ruke_pilot_eval` (`validate-registry` validates precisely 40 development tasks, 10 per cell; `preflight` executes canonical release-contract checker and the three Day 9 source test modules). `scripts.mandatory_test_gate` inspects JUnit for mandatory module/zero skips.
- **Changed files:** `.github/workflows/ci.yml`, `docs/coworker-roadmap/PROGRESS.md`, this task contract.
- **Compatibility:** insert source-only Coworker CI steps after the existing `uv sync --frozen --group dev --extra coworker`. Registry validation cannot read an external D-held corpus; preflight only runs source tests and the canonical contract. The helper suite covers offline source-only Runtime v3 validation. Do **not** invoke the paid, opt-in `tests/test_runtime_v3_live_qualification.py` or set its feature flag.
- **Direct execution commands:**
  ```bash
  uv run --extra coworker python -m scripts.ruke_pilot_eval validate-registry
  uv run --extra coworker python -m scripts.ruke_pilot_eval preflight
  uv run --extra coworker pytest tests/test_runtime_v3_qualification_helpers.py -q -rs --junitxml=/tmp/day9-runtime-v3-helpers.xml
  uv run --extra coworker python -m scripts.mandatory_test_gate /tmp/day9-runtime-v3-helpers.xml --required-module tests.test_runtime_v3_qualification_helpers
  ```
- **Observed failing exact-head preflight and compatible fix:** [PR #784 CI run #44290446763](https://github.com/rumman52/Shuddho/actions/runs/44290446763) passed `validate-registry` (40 development cases), and the canonical release checker, but `preflight` failed one historical `git show` provenance test (109 passed, one failed). The historical Git tree at `602f76f73ad845fe3ac4b4cb133fd8a07dbd20a8` contains the expected `A02_P01_GOAL_RUN_ADMISSION_REPLAY_2026-10-24.md` blob (SHA `7e728e4e55cd582aebbc2bb0085794c7f84cf14d`), so the actual cause is the Coworker job's depth-one checkout. `test-and-build` already uses `fetch-depth: 0`. This PR applies that exact checkout setting to Coworker only; it neither alters frozen evidence nor bypasses the failing provenance assertion. The initial failing head of #784 was merged without review while the corrected branch was still in flight; no pass/authorization should be inferred. Independently review and qualify this fix before merging.
- **Fault outcomes:** a bad registry, release contract, evaluator test or unexpected helper skip/failure fails this existing required CI job. No fabricated holdout pass, competitor result or staging recovery row is generated.
- **Owner and security boundaries:** A/C source checks and governance; owner/admin authorizes environment secrets and ruleset fixes; independent human D holds fresh corpus/answers/rubric with developer deny-read; two independent reviewers score; C runs 20 real staged PostgreSQL/Temporal/storage scenarios. No production, paid providers, external sends, changes to auth, migrations or credentials.
- **Budget/cancellation/revocation/rollback:** not modified. All production feature flags remain as-is; no activation.
- **Out of scope:** operating the heldout, privileged infrastructure provisioning, separate human signoffs, and claims of independent certification.

## Verification levels

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Branch source edit | New CI steps and task contract, PR head |
| Repository-verified | Pending exact-head CI | Do not infer from the preexisting main job |
| Staging-verified | No | No authenticated frozen API+worker+schema readbacks, no C scenario receipts |
| Production-qualified | No — Day 9 NO-GO | #665 custody and 40 cases / 20 scenarios outstanding |
| Activated | No | No approved release or paid provisioning |

**Required next action:** inspect the new PR's exact-head `coworker`, `test-and-build`, frontend, browser, PostgreSQL and branch ancestry results. Independently review/merge only if green. Separately authorize governance settings and independently run D/C operations. Preserve the first-run evidence if a D first-run fails; never overwrite it.
