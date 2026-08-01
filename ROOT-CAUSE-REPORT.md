# Shuddho production root-cause report

## Current confirmed live failure (July 31, 2026)

The live backend is healthy and correctly configured for `gemma` with
`gemma-4-26b-a4b-it`. The latency repair exposed the active failure: Gemma completes within its
deadline and returns non-empty output. Render's stale explicit
`SHUDDHO_GEMMA_RESPONSE_MODE=json_mime` overrode the repository default; the
valid decoded response had a non-object top level, and the broad parse handler
incorrectly classified that schema mismatch as `invalid_json`.

## Repository repair

Production now sends one compact forced `submit_shuddho_review` function call, includes the original text
once, uses offset-only sentence boundaries and compact local hints, explicitly
selects minimal thinking, disables SDK retries, and uses a 40-second provider
budget within the 45/50-second backend and 60-second frontend hierarchy.
Returned JSON still passes Pydantic and exact-span validation. Timeout failures
remain explicit and local deterministic suggestions are preserved.
The shared resolver exposes requested and effective response modes and safely
overrides stale production legacy modes. Legacy JSON modes require the explicit
local-only `SHUDDHO_ALLOW_LEGACY_GEMMA_RESPONSE_MODE=true` compatibility gate.

## Required deployment actions

Render must retain its existing secret, set `SHUDDHO_LLM_PROVIDER=gemma`,
`SHUDDHO_ENABLE_LLM=true`, `GEMMA_MODEL=gemma-4-26b-a4b-it`,
`SHUDDHO_GEMMA_THINKING_LEVEL=minimal`, `SHUDDHO_GEMMA_RESPONSE_MODE=function_call`,
`SHUDDHO_GEMMA_TIMEOUT_SECONDS=40`, `SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45`,
`SHUDDHO_LLM_TOTAL_TIMEOUT_SECONDS=50`, and
`SHUDDHO_LLM_MAX_COMPLETION_TOKENS=1400`, then clear build cache and deploy.
Vercel must set `VITE_COMPETITION_DEMO_MODE=false` and redeploy. Never put the
Google API key in Vercel or client code.
