# Prompt 02 / Day 6 — deduplicate accepted research evidence only

- Base: `f7138e2025f6f5719aea4f4babfcc3549fae324b`; branch: `fix/p02-research-valid-source-dedup-20261126`.
- Regression test commit: `d9f9f6f69ffe8a38e35a36b922fc0656a56d2a47`.
- Source commit: `67347d8b7a0ccc271e1cc9e6458f4a30ae6d9a67`.
- Root cause: TavilyResearchProvider.parse inserted the normalized URL into seen before date, readable-text and strict UTF-8 validation. A rejected first row shadowed subsequent valid evidence from the same URL.
- Fix: add URL only after row validation; preserve first valid source, canonical IDs, SHA-256, credit accounting, existing range filters and duplicate suppression. No network, grants, provider, schema or feature-flag changes.
- Local evidence: `python -m pytest -q /tmp/rukh-p02/probe.py --tb=short` on manually copied parser logic with fixed valid URL stub and dataclass/error stand-ins: RED 4 failures (research_no_evidence); GREEN 4 passed. This is not the full repository suite. Local git ls-remote failed DNS.
- Repository regression: test_research_rejected_duplicate_does_not_shadow_valid_source in tests/test_coworker_research.py, covering short content, invalid title, invalid text, stale date; valid duplicate still ignored and digest/credits retained.
- Required: full exact-head CI, focused `uv run --extra coworker pytest tests/test_coworker_research.py -q -rs`, independent review. Staging remains blocked: no persistent worker, stale API revision, no operated evidence. No deployment, provider calls or authorization changes.

| Level | Status |
| --- | --- |
| Implemented | Source committed |
| Repository-verified | Pending |
| Staging-verified | Blocked |
| Production-qualified / activated | No |
