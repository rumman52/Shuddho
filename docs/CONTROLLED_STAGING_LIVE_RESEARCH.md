# Controlled Staging Live Tavily Research Validation

This gate validates the real Tavily adapter and the deployed Shuddho Research workflow before research is enabled for a user cohort.

CI does **not** call Tavily or DeepSeek. The live exercise is explicit, budgeted and staging-only.

## Preconditions

Use controlled staging with:

```bash
SHUDDHO_STAGING_ALLOW_LIVE_RESEARCH_EXERCISE=true
SHUDDHO_RESEARCH_SERVICES_ENABLED=true
SHUDDHO_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=<backend-only staging key>
DEEPSEEK_API_KEY=<backend-only staging key>
SHUDDHO_STAGING_API_BASE_URL=https://staging-api.example.com
SHUDDHO_STAGING_TOKEN_A=<short-lived disposable staging account token>
```

Set provider-side spending limits/alerts before running the exercise.

## Run

```bash
uv run --extra coworker python scripts/staging_live_research.py \
  --query "Python programming language official documentation" \
  --time-range any \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.research.json
```

Use a stable, public, non-sensitive query. Do not put customer notes, files, secrets or personal data in the live search query.

## Direct Tavily adapter proof

The first half calls Shuddho's real `TavilyResearchProvider` and requires:

- research is explicitly enabled;
- provider is exactly `tavily`;
- a backend-only key is configured;
- one bounded request returns 1–5 usable sources;
- every retained source is a validated public HTTP(S) URL;
- provider-retrieved page text is at least 80 characters and no more than 3,000 retained characters;
- SHA-256 matches the exact retained text;
- retrieval timestamps parse correctly;
- source dates, when present, parse correctly;
- latency metadata is present;
- provider credit metadata, when supplied, is bounded;
- an exact quote from retained live page text passes Shuddho's citation validator.

A reachable provider with unusable page evidence does not pass.

## Deployed end-to-end Research proof

The second half submits one synthetic authenticated Research task through the deployed API and waits for the normal Temporal/worker path.

A pass requires:

- task state is `completed` rather than `needs_input`, failed or cancelled;
- workflow version is `work_research_v1`;
- Tavily provenance is present;
- source metadata survives but raw page text is removed from the completed task DTO;
- at least one cited finding exists;
- every citation references one returned source ID;
- citation quote lengths remain bounded;
- search accounting evidence exists;
- at least three cited artifacts are produced;
- every artifact can be downloaded through the normal owner-authorized path;
- downloaded bytes are non-empty and match artifact SHA-256 metadata.

Only then is the conditional `research` staging gate promoted to `passed`.

## What this does not prove

A successful provider/workflow exercise proves compatibility, provenance mechanics and deployed integration. It does not establish that every search result is true, that Tavily ranking is optimal, or that DeepSeek interprets every source correctly.

Before user rollout, review a small multilingual evaluation set for source relevance, citation entailment, stale/undated information and misleading pages. Keep the existing bounded-search and no-action restrictions in place.

## Rollback

Disable:

```bash
SHUDDHO_RESEARCH_SERVICES_ENABLED=false
```

This blocks new research submissions. Keep the current code/workers and provider credentials long enough to drain already accepted tasks and preserve existing research artifacts/citations.
