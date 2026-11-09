# CW-10 extension — Fly repository-level coding

- **Objective and user-visible behavior:** Fly generates multi-file code changes from the selected project workspace; displays the exact server-computed diff; requires explicit review and approval; applies only to the Fly workspace; runs supported repository tests in the existing isolated sandbox; and generates a new reviewable repair proposal from failed test output.
- **Dependency tasks and current evidence:** CW-10 foundations exist: inert Python code proposals, immutable review hashes, owner decisions, reviewed dispatch and a Python bubblewrap worker. PR #659 is merged and supplies GitHub App authorization, repository browsing/import and source provenance. The current Fly UI still says repository patch approval/application and isolated multi-language repository tests are not connected.
- **Base branch/SHA:** `main` / `39014fed635eef699697133952e6a6fccfe0d7aa`.
- **Work branch/PR:** `feat/fly-repository-coding-20261109` / draft PR to be opened after the test-first commit.
- **Existing interfaces to reuse:** `GitHubAppService.read_repository_file`; `Document`/`DocumentVersion`; `ProjectResource`; `WorkspaceManifestService`; `DeepSeekAgentPlanner`; `ProviderLease`; `SandboxRepository`; `scripts/sandbox_worker.py`; `FlyWorkspace.tsx`; `CoworkerClient`.
- **Exact files to create/modify:** See `docs/superpowers/plans/2026-11-09-fly-repository-coding.md`.
- **New interface signatures / schema and compatibility:** See plan tasks 1–5. Additive migration 0068. Existing Python sandbox execution remains compatible; old workers default to claiming only `python` jobs.
- **Acceptance scenarios and assertions:**
  1. Owner syncs repository files into a metadata-only workspace manifest; every document/version and GitHub origin is verified.
  2. DeepSeek creates a bounded multi-file proposal with exact before/after hashes; model output cannot create approval or execution.
  3. The UI displays all diffs and digest; approval and application are separate operations.
  4. Changed workspace revision, source digest, review hash or expired approval rejects application without partial changes.
  5. Applied files are saved as new private DocumentVersions and the workspace manifest revision increments atomically.
  6. Tests run inside bubblewrap with no network, host mounts, credentials or dependency installation; cancellation/worker loss/late completion fail closed.
  7. Failed test logs produce a new proposal only; each repair requires a new human review and approval; attempts are capped.
  8. GitHub remains read-only and no production flag is enabled.
- **Reproduction / initial failure:** Existing Fly UI contains explicit placeholder copy stating that repository patch approval/application and isolated multi-language tests are not connected. Existing model proposal path is single-file Python and AgentRun-scoped.
- **Expected failure outcomes:** Unsafe path, secret file, owner mismatch, missing/expired source, invalid model JSON, oversized output, stale revision, changed digest, expired approval, worker capability mismatch, cancellation, timeout, output/resource limit or failed repair budget -> typed error, no partial apply and no automatic retry/approval.
- **Tests and required CI commands:** `uv run --extra coworker pytest tests/test_fly_repository_coding.py tests/test_sandbox_control_plane.py tests/test_fly_github_repository.py -q -rs`; full coworker CI; frontend tests and build.
- **Secrets / owner / grant / approval / egress boundaries:** Backend-only DeepSeek key; owner/project/document/version checks; GitHub read-only app grant; no raw secrets in model context; exact owner approval; sandbox network namespace empty; no provider mutation authority.
- **Budget / timeout / cancellation / revocation behavior:** Reuse provider lease admission and configured daily budget; bounded output/context/file counts; sandbox CPU/wall/memory/disk/output caps; exact revision binding; worker cancellation and lease checks; two repair attempts maximum.
- **Default-off gate and rollback:** `fly_code_generation_enabled=false`, `fly_repository_execution_enabled=false`, `fly_automated_repair_enabled=false`. Rollback by leaving flags off; migration is additive; existing Python proposal path remains unchanged.
- **External prerequisites:** No staging or production work is required for repository implementation. Live DeepSeek credentials and a matching persistent worker are required for operational qualification; neither is provisioned or enabled by this task.
- **Out of scope:** GitHub commits/pushes, arbitrary package installation, network-enabled tests, production/staging deployment, autonomous apply, arbitrary shell commands, additional orchestration engines and new storage systems.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Pending | |
| Repository-verified | Pending | |
| Staging-verified | Not run | No authorized staging worker/identity in this task |
| Production-qualified | Not qualified | No production deployment or live qualification authorized |
| Activated | No | All new flags remain default-off |

- **Baseline CI:** main run 42559048152 failed in the coworker browser continuity test because it queried the visible label `+ New chat` as the accessible name. PR #660 addresses this test selector. Main also reports `protected=false`; governance is outside this task.
- **Test pass/fail/skip counts:** Pending exact-head CI.
- **Exact-head CI links:** Pending PR.
- **Review findings and resolution:** Pending final read-only review.
- **Residual risks:** Node/Python test runners use only built-in/stdlib modules; project dependencies are not installed. No live worker qualification is claimed.
- **Next exact action:** Add failing service/API/sandbox tests and mandatory CI collection before production implementation.
