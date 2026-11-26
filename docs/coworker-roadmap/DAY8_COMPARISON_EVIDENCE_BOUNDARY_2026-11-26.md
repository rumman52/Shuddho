# Day 8 comparison evidence input boundary

Issue: #734. Base: `f7138e2025f6f5719aea4f4babfcc3549fae324b`.

## Scope and acceptance

- Read each operator-supplied Day 8 comparison JSON through the existing no-follow bounded regular-file evidence reader instead of checking and reopening its pathname.
- Retain the original 2,000,000-byte acceptance limit (the shared reader bounds the physical read at 4,000,001 bytes).
- Reuse strict JSON parsing to reject duplicate keys, nonfinite literals and exponent overflow, and continue requiring a top-level object.
- Preserve comparison metrics, quality/security/cost thresholds, model/provider configuration, feature flags and output behavior.
- No changes to live infrastructure, provider calls, telemetry, deployment or admission.

## Verification

Test-first commit `d533b853a743eb441c1fd213777b3f527094f0fd`; implementation `796467d1112dbc7b19a19cf557de2464c0ff1d38`.
Local clone failed because GitHub DNS was unavailable. Isolated pytest on transcribed exact reader and existing evidence-helper excerpts: RED 3 failed / 4 passed (positive and negative exponent overflow and pathname substitution); GREEN 7 passed. These are not integrated repository test results.

Repository regression: `uv run --extra coworker pytest tests/test_core_agent_observability.py -k day8_input -q`. Full exact-head mandatory CI, zero mandatory skips and distinct independent review are pending. No staging acceptance credit. A no-follow inode does not attest immutable operator custody or guarantee stability against all concurrent in-place writes; protected operated evidence remains separately mandatory.

Rollback: revert source and regression together; no migration or runtime configuration change.

Current staging API deployed SHA `0e0b662fad0a02817a79a4514abba8f94e0ad022`, no persistent worker in Render inventory; Supabase revision `0070`, 0 Auth users and 0 storage objects. Day 8 comparison, protected evaluation, and controlled pilot remain NO-GO. This change is source-only.
