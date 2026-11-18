# Day 8 — proposed, non-emitting operational event contract

**Status:** source/test candidate only; not approved for PostHog or any other destination. Refs #734, #584. This patch does **not** register an exporter, a PostHog SDK, an endpoint, an identity, a deployment flag or a runtime call site. It does not mark D08.T02/T03/T04 as fully accepted without review/operated proof.

## Data-flow / enforced boundary

```text
Existing private Agent run/model/usage evidence (access-controlled)
    -> caller maps trusted structured counters/enums into the candidate allowlist
    -> EventPolicy gates: explicit feature enable AND approved privacy scope
       AND owner/user consent AND kill switch OFF AND staging only
       AND approved provider/model pair
    -> strict build_operational_event() (reject unknown keys, wrong types,
       free text, negative values; bucket elapsed time; unknown stays null)
    -> optional, injected server-side sink (no SDK/registered sink in this patch)
    -> separately authorized and verified destination, NOT YET CONFIGURED
```

The module is inert unless an explicit sink is injected. `emit_operational_event` catches validation and sink errors so no analytics failure can affect task execution; it does **not** log exception messages or raw inputs. This contract does not establish identity/authentication of a proposed sink, approval provenance, consent storage, or an approved deployment. Those require separate review before any runtime hook is installed.

## Fixed event and properties

The only candidate event name is `rukh_agent_run_operational_v1`. Its shape is stable and contains no distinct ID, account ID, run ID, arbitrary label, prompt, document, URL, identifier or request trace.

| Property | Type / values | Purpose | Redaction and absence policy | Retention |
| --- | --- | --- | --- | --- |
| `event_schema_version` | literal `1` | Consumer compatibility | Fixed in code | **Pending Founder/C approval** |
| `environment` | literal `staging` | Prevent cross-environment mixing | From gate, never arbitrary caller data | Pending approval |
| `workflow` | `research`, `report_email`, `daily_briefing`, `general_agent` | Aggregated workflow reliability | Exact enum only, never task name | Pending approval |
| `outcome` | `completed`, `failed`, `needs_input`, `blocked`, `cancelled`, `unknown` | Outcome denominator | Exact enum only | Pending approval |
| `provider`, `model` | exact pair in administrator-reviewed configuration | Breakdown of outcomes/cost | Reject unapproved or arbitrary values | Pending approval |
| `latency_bucket` | `lt_1s`, `1s_5s`, `5s_30s`, `30s_120s`, `gte_120s`, `unknown` | Coarse latency distribution | Derive from validated nonnegative integer ms; never emit exact timestamp or latency | Pending approval |
| `error_category` | `none`, `provider_unavailable`, `provider_rate_limited`, `provider_timeout`, `tool_timeout`, `authorization`, `validation`, `cancelled`, `unknown` | Reliability diagnosis | Reject raw exception text and arbitrary error codes | Pending approval |
| `input_tokens`, `output_tokens` | nonnegative integer or null | Aggregate usage | Unknown remains null; no raw text/tokens | Pending approval |
| `retry_model`, `retry_tool`, `retry_dispatch` | nonnegative integer or null | Retry rates by type | Missing remains null, not zero | Pending approval |
| `all_in_cost_microusd` | nonnegative integer or null | Estimated all-in cost | Caller must use reviewed rate/usage semantics; unknown remains null | Pending approval |

No other properties are accepted. Known-sensitive keys (`prompt`, `document_text`, `filename`, `account_id`, `run_id`, `email`, `recipient`, `url`, `access_token`, `connector_payload`, `raw_exception`, etc.) are rejected, not hashed, logged, or recursively scrubbed. Payload content does not become a PostHog `distinct_id`; downstream destination identity strategy is **not defined** and must be independently privacy-reviewed. Do not add frontend autocapture, pageviews, replays, or replay data.

## Required owner decisions and operational qualification

Before enabling even a single non-synthetic staging event, obtain a signed/datable decision from Founder + Owner C specifying the correct PostHog **project**, region, authorized hosts, event/properties, ingestion mechanism, opt-out/consent provenance, minimum retention/deletion policy and network egress. Establish secret storage and environment restrictions separately; do not trust hosts inferred from incoming events. No production enablement is permitted by this document.

Review the default-deny test suite `tests/test_day8_telemetry_privacy.py`. Then on an owner-approved staging deployment, instrument the already-owned observability path (not a duplicate ledger), record an authenticated sink delivery with only these properties, verify opt-out/kill switch and failures, and validate the receiving project. Until then, credit **source preparation only**. The existing private JSON/OpenMetrics evidence remains the allowed offline path.
