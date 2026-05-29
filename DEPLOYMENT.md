# Shuddho Deployment

## Web editor on Vercel

The web editor is a Vite React single-page application in `apps/web-editor`. The repository uses npm workspaces with `package-lock.json`; use npm commands for Vercel and local validation.

### Recommended Vercel settings when Root Directory is `apps/web-editor`

Use these settings when the Vercel project is configured to build from the web editor package directory:

- Framework Preset: Vite
- Root Directory: `apps/web-editor`
- Install Command: `npm install`
- Build Command: `npm run build`
- Output Directory: `dist`

Fallback build command also supported:

```bash
npm run build:web-editor
```

`apps/web-editor/vercel.json` pins the app-root deployment to Vite, `npm run build`, `dist`, and an SPA rewrite to `index.html` so direct routes work after deployment.

### Alternative monorepo-root Vercel settings

Use these settings when the Vercel project is configured to build from the repository root:

- Framework Preset: Vite
- Root Directory: repository root
- Install Command: `npm install`
- Build Command: `npm run build:web-editor`
- Output Directory: `apps/web-editor/dist`

The root `vercel.json` is for this monorepo-root deployment shape. The root package script delegates to the `@shuddho/web-editor` npm workspace.

### Frontend environment variables

Set only public Vite variables in the Vercel frontend project:

```dotenv
VITE_API_BASE_URL=https://YOUR_BACKEND_URL
VITE_USE_GATEWAY=true
VITE_ENABLE_LOCAL_FALLBACK=true
```

If `VITE_API_BASE_URL` is missing, the frontend still builds and renders, but it shows a configuration warning and keeps backend/AI requests disabled until a valid public backend URL is configured.

Do **not** add these to Vercel frontend environment variables:

```dotenv
OPENAI_API_KEY
OPENROUTER_API_KEY
OPENAI_MODEL
OPENROUTER_MODEL
```

Those values belong only in the backend environment. Browser code must route AI review through the backend and must not receive private provider keys.

### Local validation

From the repository root:

```bash
npm install
npm run build:web-editor
```

From the app directory:

```bash
cd apps/web-editor
npm install
npm run build
npm run build:web-editor
```

Both app-directory build commands produce `dist` inside `apps/web-editor`. The root build command produces the same app output at `apps/web-editor/dist`.
