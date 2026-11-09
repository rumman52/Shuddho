# Fly Repository Coding Implementation Plan

> **For agentic workers:** Use the installed `shuddho-engineering` skill and `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Complete Fly's repository-level coding loop: generate bounded multi-file changes, display the exact immutable diff, require separate human approval and application, run repository tests in the existing isolated worker, and generate reviewable repairs from failed test output.

**Architecture:** Extend CW-10's inert code-proposal and sandbox foundations with a project-scoped logical workspace manifest that references existing owned `DocumentVersion` records. Store temporary patch payloads in the existing private object store. Keep model proposals inert; bind review to exact hashes; apply through one owner/project-locked database transaction. Execute a trusted test harness plus untrusted project files inside the existing bubblewrap worker. Never write to GitHub.

**Tech Stack:** Existing FastAPI, Pydantic, SQLAlchemy, Alembic, DeepSeek planner, private object storage, bubblewrap sandbox worker, React/TypeScript and GitHub App read-only repository access.

**Spec:** `docs/coworker-roadmap/CW10_FLY_REPOSITORY_CODING_2026-11-09.md`

## Global Constraints

- Preserve existing CW-10 Python proposal and direct-user sandbox contracts.
- Use existing `Document`/`DocumentVersion` records and private object storage; a Fly manifest stores metadata and relationships only, not a second copy of file contents.
- GitHub App remains read-only. Apply changes to the Fly project workspace only; no push, commit, branch mutation or PR creation in the connected repository.
- No package installation, network egress, host filesystem, Docker socket, credentials or provider authority inside the sandbox.
- Model-generated patches remain inert until the owner reviews the exact diff, approves its digest and separately applies it.
- A repair is another proposal, never an automatic apply. Every repair requires a fresh review and approval.
- New Fly generation, repository execution and repair flags default off. Do not enable staging or production and do not change deployment configuration.
- Preserve old worker compatibility: legacy workers may claim Python jobs but must not claim the new repository-test execution kind.
- All workspace, proposal, review and execution reads/writes remain owner- and project-scoped. Enforce optimistic revision checks and idempotency.
- No silent provider fallback; use the configured backend-only DeepSeek model and existing provider budget leases.

## Review Focus

- A workspace changes while generation or review is in progress: reject stale apply and preserve the newer workspace.
- Paths contain traversal, hidden credential files, symlinks, duplicate paths, or excluded dependency/build directories: reject before model context or execution.
- A document/version belongs to another owner/project, is expired, deleted, or has a mismatched digest: reject before use.
- A worker restarts, loses its lease, is cancelled, or reports a late result: preserve terminal state, scrub source and do not accept late output.
- Test output contains prompt injection or instructions to weaken tests: treat it as untrusted diagnostics; repair generation cannot override system policy or bypass human review.

---

## Task 1: Persist a verified Fly workspace manifest

**Files:**
- Create: `services/coworker/fly_workspace.py`
- Create: `services/coworker/fly_code_schemas.py`
- Modify: `services/coworker/models.py`
- Create: `services/coworker/migrations/versions/0068_fly_repository_coding.py`
- Modify: `services/coworker/container.py`, `services/coworker/api.py`, `services/coworker/config.py`
- Modify: `services/coworker/retention.py`, `services/coworker/project_repository.py`
- Test: `tests/test_fly_repository_coding.py`

**Interfaces:**
- `FlyWorkspaceService.sync(owner_id: str, project_id: str, request: FlyWorkspaceSync) -> dict`
- `FlyWorkspaceService.get(owner_id: str, project_id: str) -> dict`
- `FlyWorkspaceService.read_version(owner_id: str, document_id: str, version_id: str) -> bytes`

The manifest is one owner/project-scoped row with a monotonically increasing revision and a canonical SHA-256. Each file entry references an existing uploaded `DocumentVersion`, its path, digest, size and optional GitHub origin metadata. Verify project-resource linkage, owner, version state, expiry, object bytes and GitHub blob provenance. Extend the selected workspace versions to a bounded retention TTL.

- [ ] Write tests for first sync, idempotent same-manifest sync, expected-revision conflict, cross-owner document denial, expired version, bad digest, unsafe path and secret-file rejection.
- [ ] Run the focused tests and confirm they fail because the service/schema is absent.
- [ ] Add additive manifest/proposal/review and sandbox execution metadata models plus migration 0068.
- [ ] Implement workspace sync/load using existing private object storage and existing document versions.
- [ ] Add owner-erasure and project-deletion cleanup; ensure temporary patch objects become unreferenced and are swept.
- [ ] Run focused tests and the existing GitHub repository tests.

## Task 2: Generate immutable multi-file proposals with DeepSeek

**Files:**
- Modify: `services/coworker/agent_planning_model.py`, `services/coworker/provider_capacity.py`, `services/coworker/config.py`
- Create: `services/coworker/fly_code.py`
- Modify: `services/coworker/container.py`, `services/coworker/api.py`
- Test: `tests/test_fly_repository_coding.py`

**Interfaces:**
- `DeepSeekAgentPlanner.propose_repository_patch(instruction: str, files: list[dict], repair_context: dict | None = None) -> tuple[dict, int | None]`
- `FlyCodeService.generate(owner_id: str, project_id: str, request: FlyPatchGenerateRequest, idempotency_key: str) -> dict`

The model returns a bounded JSON object containing a summary and complete create/update/delete file operations. The server validates paths, operations, uniqueness, byte limits and file existence; computes before/after digests; stores the inert patch in private object storage; and binds the exact proposal digest to the base manifest revision and commit. Reserve/settle the existing shared provider lease under a distinct `fly_patch` kind.

- [ ] Add failing tests for malformed model JSON, prompt injection in source/logs, duplicate paths, invalid create/update/delete transitions, output limits, repeated idempotency keys and provider-capacity denial.
- [ ] Run the focused tests and verify expected failures.
- [ ] Add the structured DeepSeek patch producer and bounded prompt; source files and diagnostics are untrusted data.
- [ ] Add default-off feature flags and provider lease accounting.
- [ ] Persist a proposal as inert; generation must not create an execution or approval.
- [ ] Run model, budget and workspace tests.

## Task 3: Exact-diff review, approval and atomic application

**Files:**
- Modify: `services/coworker/fly_code.py`, `services/coworker/api.py`
- Modify: `services/coworker/models.py` and migration 0068 if needed
- Test: `tests/test_fly_repository_coding.py`

**Interfaces:**
- `FlyCodeService.get_proposal(owner_id: str, project_id: str, proposal_id: str) -> dict`
- `FlyCodeService.review(owner_id: str, project_id: str, proposal_id: str, request: FlyPatchReviewRequest) -> dict`
- `FlyCodeService.apply(owner_id: str, project_id: str, proposal_id: str, review_sha256: str) -> dict`

Return server-generated unified diffs for every changed file. Approval is a durable owner decision bound to the exact proposal digest and a short expiry. Applying is a separate action; it locks the project, manifest, proposal and review, rechecks base revision and all before-version hashes, writes new private document versions, updates the metadata-only manifest in one DB transaction and marks the proposal applied. A retry returns the same applied result.

- [ ] Add failing tests for altered review hash, expired approval, rejected proposal, stale manifest, changed before-version, duplicate apply, cross-project access and partial-apply rollback.
- [ ] Run tests and confirm expected failures.
- [ ] Implement exact server-side diff generation, immutable review records and atomic application.
- [ ] Ensure object-store writes are cleaned on DB failure and successful patch objects are deleted after commit.
- [ ] Run focused tests and account/project retention tests.

## Task 4: Isolated repository tests and reviewable automated repair

**Files:**
- Modify: `services/coworker/sandbox.py`, `services/coworker/sandbox_schemas.py`, `services/coworker/api.py`
- Modify: `scripts/sandbox_worker.py`, `Dockerfile.sandbox-worker`
- Modify: `services/coworker/models.py` and migration 0068
- Modify: `tests/test_sandbox_control_plane.py`
- Test: `tests/test_fly_repository_coding.py`

**Interfaces:**
- `SandboxRepository.prepare_repository_execution(owner_id: str, project_id: str, manifest_revision: int, manifest_sha256: str, proposal_id: str | None, files: list[dict], runners: list[dict], idempotency_key: str) -> dict`
- `FlyCodeService.run_tests(owner_id: str, project_id: str, request: FlyRepositoryTestRequest, idempotency_key: str) -> dict`
- `FlyCodeService.generate_repair(owner_id: str, project_id: str, execution_id: str, idempotency_key: str) -> dict`

Use the existing bubblewrap control plane. A trusted Python harness materializes a bounded immutable file snapshot in scratch and invokes only allowlisted Python `unittest` and Node built-in test runners (JavaScript and erasable TypeScript). The worker runs with a private empty network namespace, read-only runtime/workspace, bounded writable scratch, cleared environment, CPU/memory/disk/time/output limits and bounded child processes. Legacy workers must not claim `repository_test` jobs.

On a failed run, one repair action may use bounded stdout/stderr and the exact tested workspace revision to generate a new inert proposal. Cap repair attempts. Never auto-approve or auto-apply.

- [ ] Add failing tests for unsupported worker capability, source tampering, stale revision, path traversal, no-test detection, runner allowlist, cancellation, restart, lease loss and output limits.
- [ ] Run the focused tests and verify expected failures.
- [ ] Add repository-test execution kind, worker capability negotiation and a distinct executor contract for Python+Node.
- [ ] Extend the worker image with Node 22 and Python 3.11; do not install project dependencies.
- [ ] Add test runner harness, bounded scratch writes and result metadata. Preserve the existing direct Python execution contract.
- [ ] Add failed-run repair generation with a two-attempt cap and fresh review requirement.
- [ ] Run sandbox control-plane and worker tests; inspect cancellation and restart paths.

## Task 5: Integrate the complete workflow into Fly

**Files:**
- Create: `apps/web-editor/src/coworker/FlyCodePanel.tsx`
- Create: `apps/web-editor/src/coworker/fly-code-panel.css`
- Modify: `apps/web-editor/src/coworker/FlyWorkspace.tsx`
- Modify: `apps/web-editor/src/coworker/client.ts`
- Test: existing Fly/React tests plus new panel tests where the repository's test harness supports them.

**Interfaces:**
- Add typed client methods for Fly workspace sync/load, status, proposal generate/list/detail/review/apply, repository tests and repair.
- `FlyCodePanel` receives `projectId`, `syncWorkspace` and `onWorkspaceApplied` callbacks.

Place the workflow in Fly's existing Tests panel. Show feature-gate status, file-by-file unified diffs, exact review digest, a deliberate review checkbox, separate Approve and Apply actions, test progress/results and a Generate repair action on failure. After application, reload the server workspace into the editor. State clearly that Apply affects Fly only and does not push to GitHub.

- [ ] Add client and panel tests for separate approval/application, stale proposal handling, disabled flags and repair review.
- [ ] Run frontend tests and confirm expected failures.
- [ ] Implement typed API calls and panel integration without replacing the existing editor or chat.
- [ ] Run frontend test suite and production build.

## Task 6: Evidence, documentation and review

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/coworker-roadmap/PROGRESS.md`
- Create/update: `docs/coworker-roadmap/CW10_FLY_REPOSITORY_CODING_2026-11-09.md`

- [ ] Include the new backend tests in the mandatory coworker CI job.
- [ ] Run `uv run --extra coworker pytest tests/test_fly_repository_coding.py tests/test_sandbox_control_plane.py tests/test_fly_github_repository.py -q -rs`.
- [ ] Run the full backend coworker test job, frontend tests and frontend build through GitHub Actions.
- [ ] Inspect the final branch diff and exact-head workflow results. Record the existing main CI failure at run 42559048152 separately from feature results; PR #660 addresses its browser selector failure.
- [ ] Perform a read-only whole-branch review for owner isolation, stale hashes, path validation, storage cleanup, worker compatibility, cancellation, repair limits and disabled-by-default gates.
- [ ] Open/keep a draft PR. Do not merge, activate, deploy, or claim staging/production qualification.

## Completion contract

Implemented means source code and tests exist. Repository-verified means exact-head required CI passes. Staging-verified, production-qualified and activated remain separate evidence levels. With feature flags default-off and no authorized staging identity/worker, this task can at most reach repository-verified.
