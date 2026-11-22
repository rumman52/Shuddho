# Day 10 canary evidence integrity implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development; verify actual test outcomes before advancing. These checkboxes record source-level work, not admission/release approval.

**Goal:** Keep post-admission cohort-stage progression decisions grounded in strictly parsed, bounded, no-follow health and plan evidence, with private write-once outputs.

**Architecture:** In the existing `scripts/cohort_canary_progression.py` entry point, reuse canonical strict JSON and private report writer from `scripts.ruke_pilot_eval`. Anchor directory enumeration and child opens to the same descriptor; change no release/rollout/stage/approval semantics.

**Tech Stack:** Python 3.11, `os.open`/`dir_fd`, POSIX no-follow/fstat, pytest, GitHub Actions.

**Spec:** `docs/coworker-roadmap/DAY10_CANARY_EVIDENCE_INTEGRITY_2026-11-22.md` and Part 05 pp. 6–7.

## Global constraints

- NO controlled-pilot GO or staging claim from parser or synthetic tests.
- Keep current 5–10 member pilot cap and distinct eligibility/admission/verification transitions.
- Preserve canonical `STOP_ROLLOUT` precedence, `HOLD` when missing, recovery epoch and prior release checks.
- Fail closed for linked inputs or ambiguous duplicate/nonfinite JSON; no owner or model credentials exposed.
- No schema, API, database, worker, telemetry, rollout or branch-governance mutation.

## Review focus

- An earlier `STOP_ROLLOUT` followed by a duplicate `CONTINUE_COHORT` must be rejected, not silently treated as healthy.
- Stage minimums or window gaps with duplicate keys must not be resolved by last-wins JSON.
- Both symlinked members and symlinked history directories must be refused without redirecting verification.
- A health file larger than the cap must fail before parsing; growth after pre-check also cannot escape the read bound.
- The first canary decision must not be overwritten; mode remains 0600 under ordinary umask.

---

### Task 1 — Reproduce untrusted health and plan read, plus mutable decision

**Files:** `tests/test_cohort_canary_progression.py`.

- [x] Add seven tests with controlled JSON and temp paths; test actual CLI result using three synthetic timely healthy windows and real `evaluate_progression`.
- [x] Commit tests first: `604d92cae8fa37703b4d66c740908cf1c6131366`.
- [x] Inspect [GitHub Actions #45034201001](https://github.com/rumman52/Shuddho/actions/runs/45034201001), `Run Python tests`: 7 expected failures, 3647 passing, 107 skipped, 6 warnings, no other failing tests.
- [x] Diagnose sources of failures: permissive JSON, following filesystem names, unbounded read, and `Path.write_text` default mode/overwrite.

### Task 2 — Minimal safe implementation

**Files:** `scripts/cohort_canary_progression.py`.

- [x] Read plan with bounded strict no-follow helper; map parse failure to `CanaryProgressionError`.
- [x] Open history directory `O_NOFOLLOW`, enumerate via opened descriptor, open direct `*.json` members by `dir_fd` with `O_NOFOLLOW/O_NONBLOCK`; `fstat` regular size and cap actual reads to `MAX_BYTES+1`; parse strict JSON.
- [x] Write output with `immutable_write` (`O_EXCL`, mode 0600, fsync); surface pre-existing output as nonzero exit without printing an eligible decision.
- [x] Commit source: `b13908fde0e5e9aea8d5d0cee655081701459873`.
- [ ] Run focused and whole repository suite plus release-contract check at exact final PR SHA; inspect all required jobs and zero-skips.
- [ ] Independently review descriptor race, file permissions and old reader compatibility.

### Task 3 — Audit-proof handoff

**Files:** `docs/coworker-roadmap/DAY10_CANARY_EVIDENCE_INTEGRITY_2026-11-22.md`, `docs/coworker-roadmap/PROGRESS.md`.

- [x] Record Part 05 acceptance, exact test-first RED and fix SHAs, no controlled pilot claims.
- [ ] Link final-head CI/checks and separate human review; do not overwrite historical baseline.
- [ ] Owner C and D perform genuine hosted controls on frozen release before opening the canary; Founder and C separately approve exact digest and cohort prior to any new admission.

**End state:** Reviewable source patch and independently inspectable regression evidence. Staging/production qualification and activation are explicitly outside this source task.
