# Runtime v3 live qualification — 9 November 2026

## Purpose

This qualification closes the gap between synthetic adapter tests and a live Runtime v3 execution. It reuses the existing DeepSeekAgentPlanner, AgentRuntime, AgentWorkflowV3, AgentActivities, DocumentRunner, and server-owned tool contracts. It does not introduce a second production runtime or change production flags.

The live suite is opt-in because it calls the configured DeepSeek model and can incur provider charges.

## What the live suite proves

| Gate | Evidence |
| --- | --- |
| Real model inference | Actual DeepSeek API responses; model identity and provider usage metadata recorded |
| Temporal execution | A real Temporal test server and registered Worker, not a mocked workflow/activity runner |
| Grounded multi-step work | document.create followed by email.draft; the downstream draft must include the completed upstream artifact and its SHA-256 provenance |
| Worker restart | A worker is stopped after the first child draft checkpoint; a replacement worker resumes the same workflow history and must not repeat that draft model call |
| Cancellation | The provider response is received but held before delivery to the planner; the run is cancelled, then the late response is released and must not create a decision or tool invocation |
| Bangla and English | Separate live multi-step tasks; language metadata and Bangla Unicode output are asserted |
| Cost and latency | Provider-reported input/output/total tokens, per-call latency, p50/p95, and an estimated cost using the operator-reviewed blended rate |

The evidence file contains run identifiers, state/decision metadata, tool receipt metadata, hashes, model usage and latency. It does not store API keys, prompts, original source text, provider response bodies, or workflow history content. It does include up to 1,600 characters of the generated draft preview so a human reviewer can inspect language quality.

## Run it

Configure these GitHub repository secrets/variables before dispatching the Runtime v3 live qualification workflow:

- Secret DEEPSEEK_API_KEY: a dedicated, low-limit qualification key.
- Variable DEEPSEEK_MODEL: the exact provider model identifier to qualify; defaults to deepseek-flash only when unset.
- Variable SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS: a reviewed positive blended effective rate in micro-USD per 1,000 tokens. Zero is rejected because it would make cost evidence misleading.

Then select Actions → Runtime v3 live qualification → Run workflow. The workflow uses an isolated SQLite database/local object store and the Temporal test server. It does not connect to Render, production PostgreSQL, Temporal Cloud, S3, Gmail, Calendar, or any external action provider.

The report is uploaded as runtime-v3-live-qualification-<run-id>. Each test adds one row to the JSON evidence file. The JUnit file is uploaded alongside it.

## Acceptance criteria

A live run is not qualified unless all of the following are true:

1. Both English and Bangla multi-step cases complete with exactly three planner decisions and exactly two successful tool receipts.
2. The downstream email draft includes the exact upstream artifact handoff identity and a 64-character SHA-256 digest.
3. Bangla output includes Bengali Unicode and both cases report the requested output language.
4. The worker-restart case completes after one worker replacement and records exactly one document-draft model call for the interrupted step.
5. The cancellation case ends in cancelled, with no committed decision or tool invocation after the late provider response is released.
6. Every successful provider call reports token usage; the report has non-zero token totals, non-zero estimated cost, and p50/p95 latency.
7. A human reviewer marks the English and Bangla output as accepted. Automated language metadata is not a substitute for human quality review.

## Important boundary: Temporal test server versus operated staging

This live suite proves the Runtime v3 workflow against a real Temporal test server and proves worker replacement while that server retains workflow history. It is not evidence that the deployed Render worker or Temporal Cloud namespace is operational.

The Render inspection on 9 November found:

- shuddho-api-staging exists, but its last recorded deployment is stale relative to current main and automatic deployment is disabled.
- shuddho-staging-db is suspended/expired after 31 October 2026.
- No persistent shuddho-worker-staging service is present.
- The production API is a separate service and must not be used for this qualification.

The external staging prerequisites remain tracked in [issue #291](https://github.com/rumman52/Shuddho/issues/291). That issue records the prior owner approval for the 0.5c-512mb background-worker plan at $7/month at the time of approval. It also records that Temporal Cloud credentials, Supabase S3 server credentials, the managed synthetic identity/token, and the worker/database Blueprint alignment must be completed securely in the dashboards.

Do not paste credentials or access tokens into GitHub, commit files, test reports, or chat. Do not enable production flags. Do not run the PA-10 release-freeze procedure as a substitute for this Runtime v3 qualification.

## Current status

- Code foundations: present on main before this qualification branch.
- Live qualification harness: added by this change; pending exact-head CI and an operator-triggered live run.
- Human Bangla/English review: pending.
- Deployed staging API/worker qualification: blocked by the expired staging database and missing persistent worker/Temporal credentials.
- Production activation: not authorized.
