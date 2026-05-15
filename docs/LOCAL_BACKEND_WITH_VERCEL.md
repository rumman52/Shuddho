# Run the Shuddho backend locally behind a Vercel frontend

This setup keeps the deployed Vercel web editor aligned with the Shuddho service architecture: browser clients talk to one TypeScript API gateway, and that gateway routes Bangla NLP work to the Python service.

```text
[Vercel apps/web-editor frontend]
        |
        | HTTPS
        v
[Public tunnel URL]
        |
        v
[Your computer: TypeScript API Gateway localhost:4000]
        |
        v
[Your computer: Python Bangla NLP backend localhost:8000]
```

## 1. Start the Python Bangla NLP backend

```bash
python -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port 8000 --reload
```

## 2. Start the TypeScript API gateway

```bash
SHUDDHO_PYTHON_API_URL=http://127.0.0.1:8000 \
SHUDDHO_NLP_PROVIDER=python \
SHUDDHO_ENABLE_LOCAL_FALLBACK=true \
SHUDDHO_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://shuddho-web-editor.vercel.app \
npm run dev --workspace @shuddho/api
```

## 3. Start a tunnel to the gateway only

Tunnel port `4000`, not the Python service on port `8000`.

### Option A: ngrok

```bash
ngrok http 4000
```

### Option B: Cloudflare Tunnel

```bash
cloudflared tunnel --url http://localhost:4000
```

Copy the public HTTPS URL, for example `https://abc123.ngrok-free.app` or `https://something.trycloudflare.com`.

## 4. Configure Vercel

Go to **Project Settings → Environment Variables** and set:

```bash
VITE_API_BASE_URL=https://your-tunnel-url
```

Example:

```bash
VITE_API_BASE_URL=https://abc123.ngrok-free.app
```

Redeploy the frontend after changing this variable because Vite reads `VITE_*` variables at build time.

## 5. Required Vercel build settings

Recommended monorepo setup:

- Framework Preset: `Vite`
- Root Directory: repository root
- Install Command: `npm install --include=optional`
- Build Command: `npm run build --workspace @shuddho/web-editor`
- Output Directory: `apps/web-editor/dist`

Alternate setup if the Vercel Root Directory is `apps/web-editor`:

- Install Command: `npm install --include=optional`
- Build Command: `npm run build`
- Output Directory: `dist`

## 6. Test from the deployed frontend

Open the deployed Vercel URL and check the browser DevTools Network tab. Requests should go to:

```text
https://your-tunnel-url/api/check
```

They should **not** go to:

```text
http://localhost:4000
http://localhost:8000
```

Manual gateway checks:

```bash
curl http://127.0.0.1:4000/health
```

```bash
curl -X POST http://127.0.0.1:4000/api/check \
  -H "Content-Type: application/json" \
  -d '{"text":"আমি  আমি ভাত খাই।","language":"bn"}'
```

Windows PowerShell:

```powershell
curl.exe -X POST http://127.0.0.1:4000/api/check `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"আমি  আমি ভাত খাই।\",\"language\":\"bn\"}"
```

## Warnings and limitations

- This setup is for testing only.
- The backend stops when your computer is off, asleep, offline, or the terminal process exits.
- Free tunnel URLs often change; update `VITE_API_BASE_URL` and redeploy Vercel after each change.
- Windows Firewall, antivirus software, routers, and corporate networks can block tunnel traffic.
- Do not expose raw user text in logs. The gateway logs request IDs, paths, latencies, text length, and provider status only.
- For production, deploy the gateway and Python backend to a real hosting platform such as Render, Railway, Fly.io, DigitalOcean, AWS, Azure, or similar.
