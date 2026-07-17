# Shuddho Render/Vercel deployment

## Render backend environment

Set these variables on the Render service for `services/api/shuddho_api`:

```text
SHUDDHO_ENABLE_LLM=true

SHUDDHO_LLM_PROVIDER=gemini
GEMINI_API_KEY=<secret>
GEMINI_MODEL=gemini-3.5-flash

SHUDDHO_LLM_FALLBACK_PROVIDER=openrouter
OPENROUTER_API_KEY=<secret>
OPENROUTER_MODEL=openai/gpt-oss-20b:free
OPENROUTER_HTTP_REFERER=https://shuddho-web-editor.vercel.app
OPENROUTER_APP_TITLE=Shuddho

SHUDDHO_LLM_ON_CHECK=manual
SHUDDHO_LLM_TOTAL_TIMEOUT_SECONDS=50
SHUDDHO_GEMINI_TIMEOUT_SECONDS=30
SHUDDHO_OPENROUTER_TIMEOUT_SECONDS=18
SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS=50

SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app,https://shuddho-web-editor-luqrebd0p-rumman52s-projects.vercel.app,http://localhost:5173,http://127.0.0.1:5173
SHUDDHO_ALLOW_VERCEL_PREVIEWS=false

SHUDDHO_LOG_RAW_TEXT=false
SHUDDHO_DETECTOR_ENABLED=false
SHUDDHO_CORRECTOR_ENABLED=false
```

Use only `GEMINI_API_KEY` for Gemini. Remove stale `GOOGLE_API_KEY`; if both are present, Google's SDK gives `GOOGLE_API_KEY` precedence and Shuddho emits a diagnostic warning.

## Vercel frontend environment

Only public values belong in Vercel:

```text
VITE_API_BASE_URL=https://shuddho-api.onrender.com
VITE_USE_GATEWAY=true
VITE_ENABLE_LOCAL_FALLBACK=false
```

Never set provider secrets in Vercel: `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, or `OPENAI_API_KEY`.


### Competition Demo · Local Engine (Vercel only)

For a competition/demo deployment that must run the prepared Bangla examples fully offline in the browser, set this public build-time Vite variable in the Vercel frontend project:

```dotenv
VITE_COMPETITION_DEMO_MODE=true
```

Use the exact lowercase string `true`. Configure it in Vercel, not Render, because it controls the Vite frontend bundle. Redeploy Vercel after changing it; Vite variables are baked in at build time. If you use both Vercel Production and Preview environments, set the variable separately in each environment. Do not put Gemini, OpenRouter, OpenAI, or any other secret provider keys in Vercel; keep the existing backend provider configuration on Render or another private backend runtime.

## Deployment order

1. Push the branch containing the backend and frontend fixes.
2. Update Render variables exactly as above.
3. Trigger Render **Clear build cache & deploy**.
4. Wait for `GET https://shuddho-api.onrender.com/health` to return HTTP 200.
5. Verify the preview-origin CORS preflight:

   ```bash
   curl -i -X OPTIONS \
     -H "Origin: https://shuddho-web-editor-luqrebd0p-rumman52s-projects.vercel.app" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: content-type" \
     https://shuddho-api.onrender.com/api/check
   ```

   Expected: HTTP 200 and `Access-Control-Allow-Origin: https://shuddho-web-editor-luqrebd0p-rumman52s-projects.vercel.app`.

6. Redeploy Vercel.
7. Confirm the generated Vercel bundle points at `https://shuddho-api.onrender.com`.
8. Hard-refresh the browser with Ctrl+Shift+R.
9. Test local suggestions first with `includeLLM=false` and the sample text.
10. Test Deep AI Review second; local suggestions should remain visible while Gemini runs, OpenRouter should be attempted after fallback-eligible Gemini failures, and every poll should reach a terminal UI state.

## External limitations

Code cannot create Gemini quota. Another key in the same Google project does not create a new project quota. If Gemini quota is exhausted, the owner must wait for reset, reduce request volume, enable billing, use a project with available quota, or request a higher quota tier.

OpenRouter free models can be useful for development, but they cannot guarantee production availability or capacity. Keep the model configurable and use a tested model with sufficient credits for production reliability.

Missing detector/corrector checkpoints are health warnings for the lightweight deployment. Do not hide those warnings or fake a trained checkpoint.

## Deep AI Review production environment checklist

Render must keep all provider keys backend-only and use origin-only CORS values:

```text
SHUDDHO_ENABLE_LLM=true
SHUDDHO_LLM_PROVIDER=gemini
GEMINI_API_KEY=<Google AI Studio secret>
GEMINI_MODEL=gemini-3.5-flash

SHUDDHO_LLM_FALLBACK_PROVIDER=openrouter
OPENROUTER_API_KEY=<OpenRouter secret>
OPENROUTER_MODEL=openai/gpt-oss-20b:free
OPENROUTER_HTTP_REFERER=https://shuddho-web-editor.vercel.app
OPENROUTER_APP_TITLE=Shuddho

SHUDDHO_LLM_ON_CHECK=manual
SHUDDHO_LLM_TOTAL_TIMEOUT_SECONDS=50
SHUDDHO_GEMINI_TIMEOUT_SECONDS=30
SHUDDHO_OPENROUTER_TIMEOUT_SECONDS=18
SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS=50
SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45

SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app,https://shuddho-web-editor-luqrebd0p-rumman52s-projects.vercel.app,http://localhost:5173,http://127.0.0.1:5173
SHUDDHO_ALLOW_VERCEL_PREVIEWS=false

SHUDDHO_LOG_RAW_TEXT=false
SHUDDHO_DETECTOR_ENABLED=false
SHUDDHO_CORRECTOR_ENABLED=false
```

Do not paste `SHUDDHO_ALLOWED_ORIGINS=` inside the Render value field; the value must be only the comma-separated origins. Do not enable a broad `*.vercel.app` wildcard.

Vercel must contain only public frontend configuration:

```text
VITE_API_BASE_URL=https://shuddho-api.onrender.com
VITE_USE_GATEWAY=true
VITE_ENABLE_LOCAL_FALLBACK=false
```

No Gemini, OpenRouter, OpenAI, or other secret API keys belong in Vercel.
