# Prompt 02 / Day 6 — malformed research provider evidence

## Task contract
- Objective: malformed provider dates or non-UTF-8 persisted source fields must not crash a bounded search or publish invalid evidence; retain valid independent pages.
- Base: `67d187f972c8069e4369ebc9fdb28dae55c40e3f` on main. Branch: `codex/p02-research-provider-input-boundary-20261125`.
- Existing interfaces: `source_date`, `TavilyResearchProvider.parse`, `SearchFailure` in `services/coworker/research.py`; no API/schema changes.
- Test-first commit: `2c0a203de5933be212eec189f2c4db180dd9b070`. Source commit: `3642322151e184024fc53277633ca57e7b348259`.
- Tests: `test_research_provider_out_of_range_utc_date_is_unavailable` (two boundary offsets) and `test_research_provider_skips_non_utf8_evidence_and_preserves_valid_page` (body and title).
- Reproduction: isolated local pytest probe using copied parser/date logic, valid URL stub and synthetic options/errors/fixtures: 4 failed before patch (2 OverflowError, 1 UnicodeEncodeError, 1 invalid accepted title), 4 passed after patch. This is not the repository suite or exact revision execution. Local git checkout failed DNS resolution.
- Behavior: unrepresentable publication dates are unknown, excluded from dated searches; malformed persisted URL/title/excerpt rows are skipped, without replacement characters or fabricated data. If none remain, existing research_no_evidence failure retains provider credit metadata. Excerpt digest uses exactly the validated UTF-8 bytes.
- No changes to provider credentials, origin, explicit public query, request limits, permissions, billing, flags, runtime architecture, or the multilingual writing path.
- Required next command: `uv run --extra coworker pytest tests/test_coworker_research.py -q -rs`; require exact PR head mandatory CI and independent human review before merge.
- Residual: semantic entailment is not established by quote matching; real provider, private-document golden scenario, browser/sandbox and memory quality evaluation still require authorized operated acceptance.

## Completion evidence
| Level | Status |
| --- | --- |
| Implemented | Source committed, remote diff read back |
| Repository-verified | Pending exact final-head CI |
| Staging-verified | BLOCKED_EXTERNAL |
| Production-qualified | No |
| Activated | No |

## Fresh dependency snapshot (25 November 2026)
- [Main CI #45351544500](https://github.com/rumman52/Shuddho/actions/runs/45351544500): test-and-build, Coworker, frontend, PostgreSQL 18 and browser qualification success; governance-audit and ci-merge-gate failed. Governance log: missing non-empty GitHub App client-id/app-id. Ruleset 27324410 is active but has zero required approvals and no required status checks in its returned rule list.
- Supabase shuddho-staging reports ACTIVE_HEALTHY PG17.11.0.003; this is metadata, not migration or tenant-isolation proof.
- Render workspace lists free staging API last live deploy `0e0b662fad0a02817a79a4514abba8f94e0ad022`, auto-deploy off, no persistent Shuddho staging worker. Do not provision paid infrastructure.
- No live provider calls, external mutation, deployment, migrations, telemetry, production activation or merge. Prompt 02 exit gate remains unmet.
