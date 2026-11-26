# Prompt 02 D04.T03 — task-brief provider envelope and conservative usage

Base: `43d99fd64467492a7da809cda0ae178191e53981`
Test-first: `b26c77f0c50d9731c09361a2c9fb1762336295c9`
Implementation: `d413e79d9573789dda0323dad5c0e5a995e5c16e`

The planner clamped negative total_tokens to zero; existing settle_provider_lease then refunded the entire reservation. Malformed non-object usage also aborted a valid brief, and the decoder accepted wrong role/index, error envelopes and legacy function_call. Preserve unknown usage as None so existing settlement conservatively charges the reservation. Accept known nonnegative integer usage. Require a single dictionary choice with clean stop, valid explicit index and assistant role, no action-bearing fields; keep legacy omitted index/role. No change to planner authority, digest, admission or model flags.

Local isolated test: copied pinned planner method and TaskBrief/TaskBriefSuggestion schema, real HTTPX MockTransport, stub _post_review and error classes. `python -m pytest -q --tb=short test_planner_probe.py`: RED 7 failed/4 passed; GREEN 11 passed in 0.16s; py_compile passed. Repository regression adds 11 cases plus actual service/provider reservation ledger assertions (not yet run locally). Full exact-head CI and independent review outstanding. No paid requests, hosted changes, new provider, tool grants or production activation. Shared PROGRESS.md not edited to avoid parallel conflicts.

## Follow-up: uniform planner boundary (2026-11-26)
Runtime v3, the legacy planner, reviewed Python drafts and repository patches had separate parsers that accepted non-assistant roles, nonzero/bool choice indices, error envelopes and legacy function calls. Three also converted negative usage to zero (potential reservation refunds) or rejected valid content solely because usage was not an object. Reuse the brief's completion validation in all five paths and preserve each typed schema, error code, approval guard and reported token metadata. No tool authorization, configuration, network or execution changes.

Test-first commit: `089f17122e84103aebf53d525256c69058b01de6` (60 repository HTTPX MockTransport cases in `tests/test_agent_approval_boundary.py`).
Implementation: `5b46056fae92a21de83268dc32a0cb9a4716df31`.
Isolated reproduction using copied parsing blocks, not a full repository checkout: `python -m pytest -q --tb=no test_probe.py` RED **26 failed, 34 passed**; after applying the shared helpers, `python -m pytest -q test_probe.py` GREEN **60 passed**; `python -m py_compile probe.py test_probe.py red_probe.py` exit 0. Full repository tests and independent review are still required. No provider calls or billing.
