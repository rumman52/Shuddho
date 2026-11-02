# Rukh AI content-generation quality implementation plan

> **For agentic workers:** Execute this plan on the isolated feature branch with a test-first loop. Verify the exact final branch head through GitHub Actions before reporting completion.

**Goal:** Apply the uploaded Rukh content-generation specification to the existing Coworker drafting pipeline, improving prompt structure, task-specific behavior, validation evidence and generation metadata without adding unrelated product scope.

**Architecture:** Add a small, provider-independent prompt-policy module that classifies existing drafting tasks and builds a layered system prompt plus a separate task/context/output contract. Keep the existing DeepSeek adapter, Pydantic output schemas, source checks, research evidence validation, durable task checkpoints and quality-evaluation harness. Persist only safe generation metadata in the existing draft checkpoint; do not add a new database ledger.

**Tech Stack:** Python 3.11, existing Pydantic schemas, httpx, pytest, GitHub Actions.

**Spec:** Uploaded attachment `deep-research-report.md` (Rukh AI content-generation specification).

## Global constraints

- Preserve the existing DeepSeek provider and explicit Gemma rollback; do not add provider fallback or change model identity.
- Preserve strict Pydantic output schemas, exact source IDs, research quote checks, multilingual behavior and draft-only external-action boundaries.
- Preserve all existing default-off capability gates and the current database/Temporal architecture.
- Add no dependency, database migration, new orchestrator, production activation or deployment.
- Do not add PostHog SDK/events: repository privacy policy blocks telemetry until event scope, consent, region, retention and exclusions are approved.
- Do not send raw prompts, document text, tokens, account identifiers or connector payloads to analytics.
- Do not change the frontend or invent a colour palette; the uploaded specification contains no UI design or colour requirements.
- If the existing output schema cannot represent a requested modality, report the exact limitation instead of claiming an unsupported capability.

## Review Focus

- Source/document/memory content containing prompt-injection instructions must remain untrusted data.
- Unsupported facts, invented sources, inaccurate quotes and missing details must not pass validation.
- Code requests must not claim code was executed or tests passed without execution evidence.
- Image requests must produce text prompts only when supported; never claim an image was generated.
- Provider usage fields may be absent, malformed or booleans and must not corrupt accounting.
- Existing clients and historical task checkpoints must remain compatible with additive metadata.

---

### Task 1: Prompt policy and task classification

**Files:**
- Create: `services/coworker/content_generation.py`
- Create: `tests/test_content_generation.py`

**Interfaces:**
- Produces `PROMPT_VERSION`, `classify_content_task(skill_id, instruction)`, and `build_content_messages(...)`.
- The builder receives the server-owned skill guidance and Pydantic schema; user content cannot replace either.

- [ ] Write tests for the existing skill-to-task mappings, explicit code/image-prompt requests, separate task/context payloads, default output-contract fields, source-as-untrusted-data handling and schema ownership.
- [ ] Run the focused test and confirm it fails because the module is not implemented.
- [ ] Implement the minimal pure prompt-policy module.
- [ ] Run the focused test and confirm it passes.

### Task 2: Draft model integration and generation evidence

**Files:**
- Modify: `services/coworker/drafting.py`
- Modify: `tests/test_coworker.py`

**Interfaces:**
- `DeepSeekDraftModel.messages()` delegates prompt construction to Task 1.
- `DraftResult` gains optional, backwards-compatible metadata for provider/model, prompt version/hash, task type, input/output/total tokens, latency, finish reason, reasoning mode, retrieval and tools.
- Existing model-response validation and error codes remain authoritative.

- [ ] Extend the existing model success test to assert the prompt contract and safe generation metadata.
- [ ] Run the focused test and confirm the new metadata assertions fail.
- [ ] Integrate the prompt builder and capture validated provider usage without changing provider, temperature or reasoning settings.
- [ ] Run the focused model tests and confirm they pass.

### Task 3: Persist safe metadata and expand quality evaluation

**Files:**
- Modify: `services/coworker/runner.py`
- Modify: `scripts/coworker_quality_eval.py`
- Modify: `tests/test_coworker_services.py`
- Modify: `tests/test_coworker_quality_eval.py`
- Modify: `tests/fixtures/coworker_quality_eval_cases.jsonl`

**Interfaces:**
- The existing draft checkpoint stores safe generation metadata only after the complete schema/source/research validation passes.
- The existing quality evaluator reports prompt version/hash, task type, provider/model, token counts, finish reason, latency and validation result for live runs.
- Offline fixtures validate task classification, schema, language, source attribution, missing-information behavior and research quote fidelity.

- [ ] Add tests for metadata persistence and the expanded offline evaluation categories.
- [ ] Run the focused tests and confirm the new assertions fail.
- [ ] Persist metadata in the existing JSON checkpoint; do not add a migration or external telemetry.
- [ ] Expand the existing evaluator and fixtures, including exact-quote research validation.
- [ ] Run focused tests and the complete offline Coworker quality gate.

### Task 4: Exact-head verification and handoff

**Files:**
- No production files beyond Tasks 1–3.

- [ ] Open/update a draft PR on the feature branch.
- [ ] Run the repository's required GitHub Actions checks on the final head.
- [ ] Inspect the exact-head test/build results and final diff.
- [ ] Keep the PR unmerged pending the repository's independent current-head review and normal protected merge gate.
- [ ] Report unavailable checks and the PostHog privacy blocker explicitly.
