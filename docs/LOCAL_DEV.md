# Local development

Install dependencies with optional native packages:

```bash
npm install --include=optional
```

If registry policy blocks optional packages, use the checked-in lockfile/workspace sources and rerun in an environment with npm registry access.

Start the Python Bangla API:

```bash
python -m uvicorn services.api.shuddho_api.app:app --host 127.0.0.1 --port 8000 --reload
```

Start the TypeScript gateway:

```bash
npm run dev --workspace @shuddho/api
```

Start the Vite editor:

```bash
npm run dev --workspace @shuddho/web-editor
```

Optional Next app:

```bash
npm run dev --workspace @shuddho/web
```

Tests:

```bash
npm test --workspace @shuddho/shared
npm test --workspace @shuddho/api
.venv/bin/python -m pytest -m "not slow"
```
