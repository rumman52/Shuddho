# Shuddho Frontend Shell and Artifact Preview Repair

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Restore a green, buildable React/Vite frontend across the canonical web editor and the standalone Rukh Coworker/Editor workspaces, including the already-tested secure text-artifact reader contract.

**Architecture:** Keep `apps/web-editor` as the canonical implementation. Make `apps/coworker` and `apps/editor` thin application entry points that reuse its reviewed CoworkerGate and writing editor, while using the existing `@rukh/auth` and `@rukh/coworker-client` packages. Text previews may read only the exact authenticated owner-bound artifact content route; signed object-storage URLs are never fetched with account credentials.

**Tech Stack:** React 18, TypeScript, Vite, Supabase JS, Node's built-in test runner, GitHub Actions.

**Spec:** Root `AGENTS.md`, `docs/coworker-roadmap/SPEC.md`, current `main` at `cd242d73031890bbf7e4154ad8be030cc707b82e`, and failing CI run #2412.

## Global Constraints

- Preserve the free Bangla writing experience, local fallback and AI failure diagnostics.
- Do not expose Supabase service-role/provider secrets in browser code or `VITE_*` variables.
- Do not weaken owner authentication, artifact ownership, or redirect protections.
- Never forward a bearer token to a signed object-storage URL.
- Do not activate production features, change Render/Supabase/Vercel production settings, or modify backend capability gates.
- Work on a dedicated branch; do not merge to `main`.

## Review Focus

- Binary or unsupported artifact MIME types must be rejected before content fetch.
- Oversized text artifacts must be rejected before fetch using declared size and after fetch using actual bytes.
- Signed URLs must never receive the Coworker bearer token.
- Both standalone apps must resolve all relative entry-point imports.
- Auth callback and shared-session behavior must remain compatible with the existing Supabase client.

---

### Task 1: Pin standalone app shell import resolution

**Files:**
- Create: `apps/coworker/test/app-shell.test.mjs`
- Create: `apps/editor/test/app-shell.test.mjs`
- Modify: `.github/workflows/ci.yml`

**Interfaces:** Tests inspect each package's `src/main.tsx` and `src/App.tsx`; no runtime API changes.

- [x] **Step 1: Write failing tests** that require `src/App.tsx`, `src/styles.css`, and resolution of all relative imports from the entry and App.
- [ ] **Step 2: Run the new package tests** and retain the expected missing-file failures.
- [ ] **Step 3: Keep the standalone app tests visible in CI** before the root workspace test command, which currently stops at the first failing workspace.
- [ ] **Step 4: Re-run both package test commands** after implementing the app wrappers.

### Task 2: Restore the authenticated text-artifact reader

**Files:**
- Modify: `apps/web-editor/src/coworker/client.ts`
- Test: existing `apps/web-editor/src/coworker/client.test.ts`

**Interface:** `CoworkerClient.readTextArtifact(artifact: Artifact): Promise<string>`.

- [ ] **Step 1:** Use the existing failing tests as the reproduction: the method is absent and both text-artifact tests fail with `client.readTextArtifact is not a function`.
- [ ] **Step 2:** Reject unsupported MIME types and metadata sizes above 2 MiB before any request.
- [ ] **Step 3:** Read the download descriptor; accept only `url: null` and the exact `/api/v1/artifacts/{id}/content` path.
- [ ] **Step 4:** Fetch that path through the existing authenticated `response()` helper, require a supported text response MIME type, enforce the 2 MiB response limit, and return text without rendering HTML.
- [ ] **Step 5:** Run `npm run test --workspace @shuddho/web-editor`.

### Task 3: Complete standalone Coworker and Editor entry points

**Files:**
- Create: `apps/coworker/src/App.tsx`, `apps/coworker/src/styles.css`
- Create: `apps/editor/src/App.tsx`, `apps/editor/src/styles.css`
- Modify: `apps/web-editor/src/coworker/CoworkerGate.tsx`, `apps/web-editor/src/coworker/authConfig.ts`
- Modify: `packages/auth/src/index.ts`
- Modify: `apps/editor/.env.example`

**Interfaces:**
- Coworker app reuses `CoworkerGate` and `ErrorBoundary`.
- Editor app reuses the existing writing `App` and `ErrorBoundary`.
- `@rukh/auth` exports `Session` and `SupabaseClient` types and remains the only package that constructs the shared Supabase client.
- `CoworkerGate` uses `getRukhAuthClient` and `CoworkerClient` from the existing workspace packages.

- [ ] **Step 1:** Add minimal app wrappers; do not duplicate the editor or Coworker implementation.
- [ ] **Step 2:** Route auth/client construction through the existing workspace packages while preserving the default Supabase storage key and auth callback handling.
- [ ] **Step 3:** Add the editor API build-time defaults to its example environment file; keep secrets out of it.
- [ ] **Step 4:** Run standalone tests and TypeScript/Vite builds for all three frontend workspaces.

### Task 4: Full verification and handoff

**Files:**
- Modify: `docs/coworker-roadmap/PROGRESS.md`
- Update: `docs/coworker-roadmap/FRONTEND_APP_SHELL_QUALIFICATION_2026-11-02.md`

- [ ] Run `npm ci`, `npm test`, `npm run build`, the browser-worker policy tests, and the required coworker CI job.
- [ ] Inspect exact final-head GitHub Actions results and the complete diff.
- [ ] Record exact commit, PR, pass/fail/skip counts, and unavailable external checks.
- [ ] Keep staging verification, production qualification, and activation explicitly separate from repository completion.
