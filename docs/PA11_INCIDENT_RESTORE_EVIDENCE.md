# PA-11 Incident and Restore Evidence

PA-11 cohort expansion must not rely only on capacity, output quality and task economics. This bounded slice compiles **fresh, rollout-bound recovery evidence** from Shuddho's existing controlled staging drills before a human scale review can qualify.

It does not perform a backup, restore, worker restart, rollback or production change. Those exercises remain explicit operator actions.

## Inputs

Use the exact release rollout plus the staging-evidence file produced by the existing controlled exercises. The staging evidence must already mark all five recovery controls as `passed` with non-empty references:

- `backup_restore`;
- `temporal`;
- `parallel_restart`;
- `fan_in`;
- `flag_rollback`.

Each of the five staging recovery records must itself carry the exact release ID, rollout-manifest SHA-256, deployed 40-character source revision, immutable prepare-time exercise start, and verification timestamp. The operator review is copied from `docs/pa11-incident-restore-review.template.json` and records the same source revision, drill start/completion timestamps, reviewed RTO and data-loss limits, durable incident/backup/restore/restart/rollback references, reviewer reference and any unresolved failures.

The compiler fails closed when a required recovery gate is not passed, a staging record belongs to another rollout/revision, a staging verification timestamp falls outside the claimed drill window, the exercise exceeds its RTO, observed data loss exceeds the reviewed limit, timestamps are invalid/future, source revision is malformed, or the operator review has unresolved failures. The validator recomputes restore duration from the exercise timestamps instead of trusting the stored duration field.

## Compile evidence

```bash
cp docs/pa11-incident-restore-review.template.json /secure/release/pa11-incident-restore-review.json

uv run python scripts/incident_restore_evidence.py \
  --rollout /secure/release/cohort-rollout.json \
  --staging-evidence /secure/release/staging-evidence.json \
  --review /secure/release/pa11-incident-restore-review.json \
  --output /secure/release/incident-restore-evidence.json
```

The resulting artifact records only bounded operational facts and references. It SHA-256 binds the exact rollout manifest, staging evidence and operator review. It does not copy credentials, database contents, object bytes, prompts or provider response bodies.

## Scale-review binding

The bounded cohort scale review requires the exact incident/restore artifact:

```bash
uv run python scripts/cohort_scale_review.py \
  --plan docs/cohort-scale-review-plan.template.json \
  --review /secure/release/cohort-scale-review.json \
  --rollout /secure/release/cohort-rollout.json \
  --capacity-qualification /secure/release/capacity-qualification.json \
  --quality-eval /secure/release/coworker-quality-eval.json \
  --task-economics /secure/release/task-economics-evidence.json \
  --incident-restore /secure/release/incident-restore-evidence.json \
  --operator-status /secure/release/post-review-operator-status.json \
  --output /secure/release/bounded-scale-decision.json
```

Scale review revalidates release ID, rollout SHA-256 and the same source revision used by live quality evidence. Both the compiled evidence timestamp and the underlying `exercise_completed_at` must satisfy the existing freshness window, so recompiling an old drill cannot make recovery readiness fresh.

The final operator-health snapshot must be newer than capacity, quality, task-economics **and** incident/restore evidence. A passing result only makes the proposed cohort eligible for separate reviewed expansion; it does not change a flag, cohort, provider quota or deployment by itself.

## Qualification boundary

Repository tests validate the evidence contract. Production readiness still requires a real managed PostgreSQL/private-object restore, real Temporal worker replacement/recovery, reviewed rollback practice, and durable operator references for the exact release. Synthetic or mocked repository fixtures are not staging/production qualification.


## Downstream enforcement

A scale decision created before this gate, or any hand-authored decision that omits the exact `artifact_sha256.incident_restore` binding, is rejected by both cohort-scale activation and downstream provider-policy compilation. Both consumers require the actual incident/restore file, compare its computed SHA-256 to the decision, and validate the artifact contents. The gate cannot be bypassed with an invented 64-character digest.
