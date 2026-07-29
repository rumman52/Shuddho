# Shuddho production root-cause report

## Confirmed repository cause

The default Docker result previously ended at the `ml-cpu` stage. Consequently an unqualified Docker deployment installed PyTorch/SentencePiece and selected automatic checkpoint engines even though hosted Gemma inference needs neither. The quick-fix documentation also used `uv sync`, whose default development group expands the install and made the native Render path inconsistent with the known-working base-package install. Both choices add avoidable startup work before an HTTP health response and match the observed symptom: the host accepted a connection but health endpoints timed out before any Gemma request.

The production repair makes the last Docker stage a lightweight `production` alias, retains `ml-cpu` only as an explicit target, and standardizes native Render on `python -m pip install --no-cache-dir .`. Explicitly disabled corrector startup now skips even optional model-download handling.

## Runtime architecture

The competition runtime uses the Google Gen AI SDK/API transport to call only pretrained instruction-tuned Gemma 4 (`gemma-4-26b-a4b-it`). Unsupported provider names and non-`gemma-*` models fail closed. Health and debug routes inspect state only; provider calls occur only for requested AI review. Local rules and spelling remain the honest fallback.

Repository changes cannot redeploy the existing Render/Vercel projects. The owner must apply the dashboard settings in `DEPLOYMENT.md`, clear Render's build cache, verify `/health`, and then redeploy Vercel.
