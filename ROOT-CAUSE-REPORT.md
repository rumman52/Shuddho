# Shuddho production root-cause report

## Current confirmed live failure (July 31, 2026)

The deployed Render service is reachable, but its dashboard environment selects
`SHUDDHO_LLM_PROVIDER=gemini`. Shuddho's competition runtime accepts only
`gemma`, so configuration resolution fails closed with
`unsupported_llm_provider_gemma_only` before it reads `GOOGLE_API_KEY` or makes
a model request. While the provider is invalid, `api_key_present: false` is not
evidence that the key is absent.

The Vercel production build also has dashboard overrides that set
`VITE_API_BASE_URL=https://shuddho-api.onrender.com` and
`VITE_COMPETITION_DEMO_MODE=true`. The former bypasses the working same-origin
`/backend` rewrite; the latter enables a demo mode that should be disabled in
production.

Repository commits cannot alter environment variables already stored in the
Render or Vercel dashboards. An authorized project owner must apply the
production settings below and redeploy both services.

## Required external remediation

Render must use `SHUDDHO_LLM_PROVIDER=gemma`, enable LLM review, select
`GEMMA_MODEL=gemma-4-26b-a4b-it`, and provide an approved server-side
`GOOGLE_API_KEY`. Detector and corrector engines remain disabled in the
lightweight service. After saving the variables, clear the Render build cache
and deploy, then verify `/health`, `/health/deep`, `/api/llm/debug`, and
`/version`.

Vercel Production must delete the direct `VITE_API_BASE_URL` override (or set it
to `/backend` only), set `VITE_COMPETITION_DEMO_MODE=false`, retain
`VITE_USE_GATEWAY=true` and `VITE_ENABLE_LOCAL_FALLBACK=false`, and redeploy
after Render is ready. Backend variables and secrets must never be added to
Vercel.

## Historical issues (resolved)

Earlier repository revisions made the ML-heavy `ml-cpu` Docker stage the
default and documented a development-oriented native install. Those startup and
dependency risks were repaired: the final Docker stage is now lightweight
`production`, `ml-cpu` remains an explicit opt-in target, and production uses
the base package without Torch or SentencePiece. They are not the cause of the
current AI-unavailable message.

## Runtime architecture

The Google Gen AI SDK/API is transport for the pretrained instruction-tuned
Gemma model `gemma-4-26b-a4b-it`; Shuddho does not use a Gemini model or claim
to have trained or fine-tuned Gemma. Unsupported providers and non-`gemma-*`
models fail closed. Local rules, dictionaries, spelling, punctuation, and
spacing checks remain available as deterministic fallback and quick typing
support.
