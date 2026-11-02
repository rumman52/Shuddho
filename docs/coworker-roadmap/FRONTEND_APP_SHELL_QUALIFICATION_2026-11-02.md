# Frontend app-shell and artifact-preview task contract — 2 November 2026

- Objective and user-visible behavior: the canonical writing editor and authenticated Coworker remain available, and the standalone Rukh Editor/Coworker Vite workspaces resolve and build. Authorized text artifacts can be read only through their owner-bound content route.
- Dependency tasks and current evidence: current `main` is `cd242d73031890bbf7e4154ad8be030cc707b82e`; PR #602 is merged. CI #2412 fails in `test-and-build` during JavaScript tests. The two existing text-artifact tests fail because `CoworkerClient.readTextArtifact` is missing. Coworker/editor app entry points import missing `App.tsx` and `styles.css`.
- Base branch/SHA: `main` / `cd242d73031890bbf7e4154ad8be030cc707b82e`.
- Work branch/PR: `fix/frontend-shell-build-20261102` / PR not yet opened.
- Existing interfaces to reuse: `CoworkerGate`, `CoworkerWorkspace`, `apps/web-editor/src/App.tsx`, `ErrorBoundary`, `getRukhAuthClient`, `CoworkerClient`, and the existing `/api/v1/artifacts/{id}/download` and `/content` routes.
- Exact files to create/modify: `apps/coworker/src/App.tsx`, `apps/coworker/src/styles.css`, `apps/editor/src/App.tsx`, `apps/editor/src/styles.css`, package auth exports, CoworkerGate imports, `client.ts`, standalone app tests, CI workflow, editor env example, and this evidence record.
- New interface signatures / schema and compatibility: `readTextArtifact(artifact: Artifact): Promise<string>`; accept only supported text MIME types and the exact authenticated owner-bound content path; keep `download()` behavior unchanged.
- Acceptance scenarios and assertions: existing text preview succeeds; binary metadata is rejected before network access; signed URL is never fetched with account credentials; app-shell imports resolve; both standalone app test commands and all workspace builds pass.
- Reproduction / initial failure: CI #2412 reports two failures: `client.readTextArtifact is not a function` in the authenticated text-reader tests. Git tree and direct fetch return 404 for both standalone `App.tsx` files; both local `styles.css` imports are also absent.
- Expected failure outcomes: unsupported type, oversize metadata/body, missing or external content path, non-text response, or owner-auth failure must fail closed and show an error; no token may be sent to an external URL.
- Tests and required CI commands: `npm run test --workspace @rukh/coworker`; `npm run test --workspace @rukh/editor`; `npm run test --workspace @shuddho/web-editor`; `npm test`; `npm run build`; browser-worker policy tests; mandatory coworker CI job.
- Secrets / owner / grant / approval / egress boundaries: public Supabase publishable key only in frontend; Coworker API requests remain owner-authenticated; object storage signed URLs never receive bearer tokens.
- Budget / timeout / cancellation / revocation behavior: retain existing `fetchWithTimeout`, token refresh, abort and redirect protections; cap text preview at 2 MiB.
- Default-off gate and rollback: preserve `VITE_COWORKER_ENABLED` and all backend capability flags; no production feature flag changes.
- External prerequisites: no staging/provider action is required for this source repair. Vercel sandbox creation is currently denied by a 403; Vercel project/deployment inspection is returning 403/404 through the connected API.
- Out of scope: production deployment/merge, backend activation, database/schema changes, paid resources, branding redesign, and broad editor rewrite.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Pending | |
| Repository-verified | Pending | |
| Staging-verified | Not performed | |
| Production-qualified | Not qualified | |
| Activated | No | |

- Test pass/fail/skip counts: baseline CI #2412: JavaScript tests fail (2); Python and Coworker jobs pass; workspace build skipped.
- Exact-head CI links: https://github.com/rumman52/Shuddho/actions/runs/41439628190
- Review findings and resolution: pending.
- Residual risks: deployed Vercel UI and production environment flags cannot currently be verified; this task does not prove production Coworker availability.
- Next exact action: add the failing app-shell tests and restore the missing client/app-shell implementations; run full exact-head CI.
