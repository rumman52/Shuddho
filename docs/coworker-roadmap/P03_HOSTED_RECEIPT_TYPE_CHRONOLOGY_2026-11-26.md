# Prompt 03 — hosted transaction evidence type and chronology

Base: `43d99fd64467492a7da809cda0ae178191e53981`. Scope: TX-27/28/29, provider-neutral hosted receipt validation. No payment, shopping or travel adapter registration, permissions, provider calls, deployment or transaction activation.

## Reproduction and repair
- The rehashed handoff could contain a float or boolean total equal to the approved integer under Python equality. Require matching types and values for every canonical preview-bound field.
- The lower-level receipt validators intentionally allow clock skew, but the hosted two-phase completion must not claim that a provider confirmation observed at time T occurred later than T. Require confirmation no later than observation, while preserving reconciliation after expiry for an on-time confirmation.
- Test-first `85a39f27174a869a17797bf7de248095e36b4d95`; source `76ddfec4e43df835ab982d4de424bf4f3b0deed5`.

## Verification
Local GitHub checkout unavailable (DNS). In isolated copied module/dependency excerpts using real Pydantic preview and receipt models: `cd /tmp/rukh-p03-handoff && python -m pytest -q tests/test_exact_hosted.py --tb=short`: RED 8 failed / 4 passed; GREEN 12 passed, zero skips. Patched hosted module blob verified against GitHub: `4ecb041e37bbdd539a5b793ed003cd7479a307c0`. Compileall passed. This is not a full repository or provider-backed acceptance run.

Repository regression: `uv run --extra coworker pytest tests/test_hosted_transaction_handoff.py -q`. Full mandatory exact-head CI and distinct independent review pending. No staging acceptance credit; no live transaction calls authorized or performed. Rollback by reverting source and regression together.
