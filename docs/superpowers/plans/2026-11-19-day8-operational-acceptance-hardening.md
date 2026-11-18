# Days 7–8 operational acceptance hardening — 19 November 2026

## Goal and boundary

Implement missing **source-level** acceptance safeguards for the exact Day 7/8 pilot contract without fabricating two natural Temporal firings, 80 paid development runs, owner privacy consent, API/worker deployment, or release freeze. Source changes alone **do not** satisfy issue #734.

Base: main observed at `cebe322d88d2120e6c78c6755b70445eedf8c39f`. Branch: `fix/day8-operational-acceptance-hardening-20261119`.

## Implemented

1. `scripts/core_agent_observability.py`: require a finite positive `time_limit_seconds` (1–3600) on both configurations, **equal** across profiles. Missing legacy envelopes return BLOCKED, not a freeze; mismatched limits raise an explicit validation error. Freeze records the time limit via the validated configuration object.
2. `scripts/staging_day7_two_day_gate.py`: compare document/version pairs by document ID rather than unstable list order. Require **exactly one** authorized document to change its immutable version across the two independently gathered daily firings. Report `changed_document_id`.
3. `services/coworker/operational_telemetry.py`: no SDK/HTTP/automatic integration, and no sink call by default. It exposes an explicit testable staging-only gate requiring an authenticated integration to supply explicit enabled, owner-approved, consent-confirmed, non-killed status, exact destination project, receipt fingerprint, and pinned model. Reject all unknown keys and raw/free-form values instead of attempting recursive redaction. The allowlist uses finite enums and nonnegative bounded integer metrics. Transport errors cannot fail the user's task.
4. Tests: `tests/test_core_agent_observability.py`, `tests/test_staging_day7_two_day_gate.py`, `tests/test_operational_telemetry.py` cover strict limits, one-document update, reordered source vectors, off-by-default behavior, consent/kill-switch checks, private-string rejection, invalid numeric/enumerated values, missing usage and transport failure.

## Reproduce

```bash
uv run --extra coworker pytest tests/test_core_agent_observability.py tests/test_task_economics_evidence.py tests/test_staging_day7_two_day_gate.py tests/test_operational_telemetry.py -q -rs
```

Run all required GitHub CI checks on the exact final PR SHA. Telemetry synthetic approval fixtures are **not real owner approval**. This patch adds no event ingestion, billing, resource provisioning, release deployment, production flag, schema migration or provider switch.

## Outstanding external evidence (not source-test pass)

- An authorized synthetic owner, approved goal/project/document, live same-release API and worker, Temporal server access and two consecutive **natural** calendar firings. Collect independent provenance, one owner notification lifecycle, revision update, replay, restart, pause, expiry, quiet-hours, bounded catch-up and one-version-only evidence under the existing Day 7/8 operator probes. A unit test is not evidence of a natural firing.
- Approved provider spend, authenticated 40-task development registry, two independently generated 40-case cohorts, actual directional provider tokens, failure/retry/latency/cost receipts, independent rubric judgments and owner-approved p95 ceiling. `compare_day8_development` must return FROZEN_FOR_DAY9 only after all requirements; its result is a **development candidate**, not a production release.
- Founder/C's concrete PostHog project, region, retention, purpose, consent/opt-out, authorized URLs and kill switch approval under #584. Telemetry stays disconnected. No event is sent from this PR.
- Before release promotion, independently authenticate actual API/worker source + image build digests, matching deployed schema, provider/model, prompt registry, tool registry, context budget, and **all 43** booleans using `scripts/ruke_pilot_eval.py:validate_candidate_readbacks` and `scripts/staging_release_freeze.py`. Do not infer these from source defaults or GitHub HEAD.
- Required governance-audit and CI merge gate are separate release blockers. Render currently lists a staging API but no paired staging worker; connected Supabase staging reported empty goals/runs/documents on the previous read.

## Evidence levels

| Level | Verdict |
| --- | --- |
| Source change | Implemented on PR branch; awaiting exact-head CI and independent review |
| Synthetic regression tests | Provided; CI outcome must be verified separately |
| Staging natural-fire drill | BLOCKED — missing approved operator/worker/owner resources |
| 80 real benchmark generations | NOT RUN — spend/privacy/receipt prerequisites absent |
| Approved telemetry | OFF — approval absent |
| Deployment/manifest freeze | NO-GO — actual paired readbacks absent |

Rollback: revert this PR. This patch never turns on telemetry or a capability.
