# Prompt 02: exact configured CORS origin validation

Base: 460db9ff97c3f4adcc43beaf4d4db82a3957b097
Test-first commit: a9fcc4774ca68661304164a4b8499e9df006bc2f
Source fix: 33a798c33ad7cc1ba6d3cd9dfd9eb3dba2c7d495

## Defect and contract
Malformed explicit origins could crash initialization or be silently normalized into a different, credential-enabled origin. Reject malformed authorities, invalid ports, userinfo, query/fragment, non-root paths, wildcards, and embedded whitespace/control characters. Preserve defaults, explicit valid origin/port, one optional trailing slash, deduplication, and existing middleware policy. Warnings do not include raw input.

## Evidence
Test-first regression committed in tests/test_api_app.py. Local isolated probe used the existing parser copied verbatim, with real FastAPI/Starlette TestClient OPTIONS requests: RED 12 failed, 1 passed; GREEN 13 passed, 0 skipped; py_compile passed. Command: python -m pytest -q --tb=short test_origin_probe.py (isolated probe, not full repository). Repository checkout unavailable (DNS); exact-head repository CI and independent review are required. The production OPTIONS problem is not claimed resolved until approved same-release staging reproduces and validates it.

## Safety and handoff
No hosted changes, telemetry activation, paid provisioning, or deployment. Keep this PR draft pending CI and independent review. Shared PROGRESS.md is intentionally untouched because parallel branches own it; consolidate this checkpoint after coordination. Status: SOURCE_IN_PROGRESS; operational and independent gates not qualified.
