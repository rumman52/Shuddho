"""Checkpointed business steps, independent of Temporal and HTTP connections."""
from __future__ import annotations

import asyncio
import hashlib
import json

from .container import Container
from .drafting import DeepSeekDraftModel, DraftFailure, DraftModel
from .errors import CoworkerError
from .extraction import extract_in_subprocess
from .exports import render_in_subprocess
from .schemas import ResearchOptions, parse_draft, source_references
from .research import ResearchProvider, SearchFailure, TavilyResearchProvider, validate_evidence
from .skills import skill_for_version

PHASE_MESSAGES = {
    "extract": "Reading your source material.",
    "research": "Searching the web and collecting source evidence.",
    "draft": "Preparing your draft.",
    "export": "Creating your downloadable documents.",
    "complete": "Checking your downloads.",
}


class DocumentRunner:
    def __init__(self, container: Container, model: DraftModel | None = None, renderer=render_in_subprocess,
                 research: ResearchProvider | None = None):
        self.container = container
        self.repo = container.repository
        self.model = model or DeepSeekDraftModel(container.settings)
        self.renderer = renderer
        self.research_provider = research or TavilyResearchProvider(container.settings)

    async def phase(self, task_id: str, phase: str):
        task = await asyncio.to_thread(self.repo.worker_task, task_id, False)
        # Completion can reach the database before the activity acknowledgement.
        if task["state"] in {"completed", "needs_input"}:
            return
        skill_for_version(task["workflow_version"])
        if phase not in PHASE_MESSAGES:
            raise CoworkerError("workflow_version", "This task uses an unsupported workflow version.")
        if phase == "research" and task["skill_id"] != "research":
            raise CoworkerError("workflow_version", "This task cannot use web research.")
        checkpoint = await asyncio.to_thread(self.repo.begin_phase, task_id, phase, PHASE_MESSAGES[phase])
        if checkpoint is not None:
            return
        if phase == "extract":
            await self.extract(task)
        elif phase == "research":
            await self.research(task)
        elif phase == "draft":
            await self.draft(task)
        elif phase == "export":
            await self.export(task)
        else:
            await self.complete(task)

    async def extract(self, task):
        sources = []
        if task["skill_id"] != "report_email":
            # A complete natural-language brief can be enough for a work service.
            # Include it as an owned source so facts in the request have provenance.
            sources.append({"id": "brief", "label": "Your brief", "text": task["instruction"],
                            "sha256": hashlib.sha256(task["instruction"].encode()).hexdigest()})
        if task["notes"]:
            notes = task["notes"]
            sources.append({"id": "notes", "label": "Provided notes", "text": notes,
                            "sha256": hashlib.sha256(notes.encode()).hexdigest()})
        for document in task["documents"]:
            await asyncio.to_thread(self.repo.worker_task, task["id"])
            body = await asyncio.to_thread(self.container.storage.get, document["object_key"], document["byte_size"])
            if len(body) != document["byte_size"] or hashlib.sha256(body).hexdigest() != document["sha256"]:
                raise CoworkerError("source_changed", "A source file could not be verified. Upload it again.")
            text = await asyncio.to_thread(extract_in_subprocess, body, document["kind"], self.container.settings.max_source_chars)
            sources.append({"id": document["version_id"], "label": document["filename"], "text": text,
                            "sha256": document["sha256"], "document_id": document["id"]})
        if sum(len(source["text"]) for source in sources) > self.container.settings.max_source_chars:
            raise CoworkerError("source_too_large", "The combined source is too long. Use up to 20,000 characters per task.", 413)
        await asyncio.to_thread(self.repo.save_step, task["id"], "extract", {"sources": sources})

    async def research(self, task):
        if isinstance(self.model, DeepSeekDraftModel) and not self.container.settings.deepseek_api_key:
            raise CoworkerError("model_not_configured", "Your coworker is temporarily unavailable. Please try again later.", 503)
        options = await asyncio.to_thread(self.repo.step, task["id"], "research_input")
        if options is None:
            raise CoworkerError("checkpoint_missing", "The search query could not be recovered. Please create a new task.")
        if isinstance(self.research_provider, TavilyResearchProvider):
            self.research_provider.configured()
        await asyncio.to_thread(self.repo.reserve_search, task["id"])
        try:
            result = await self.research_provider.retrieve(ResearchOptions.model_validate(options))
        except SearchFailure as error:
            await asyncio.to_thread(self.repo.settle_search, task["id"], "failed", error.credits)
            raise
        except BaseException:
            await asyncio.shield(asyncio.to_thread(self.repo.settle_search, task["id"], "unknown"))
            raise
        await asyncio.to_thread(self.repo.settle_search, task["id"], "completed", result.credits)
        await asyncio.to_thread(self.repo.save_step, task["id"], "research", {
            "sources": result.sources, "metadata": result.metadata,
        })

    async def draft(self, task):
        extracted = await asyncio.to_thread(self.repo.step, task["id"], "extract")
        if extracted is None:
            raise CoworkerError("checkpoint_missing", "Your source could not be recovered. Please create a new task.")
        if isinstance(self.model, DeepSeekDraftModel) and not self.container.settings.deepseek_api_key:
            raise CoworkerError("model_not_configured", "Your coworker is temporarily unavailable. Please try again later.", 503)
        sources = list(extracted["sources"])
        research = None
        if task["skill_id"] == "research":
            research = await asyncio.to_thread(self.repo.step, task["id"], "research")
            if not research or not research.get("sources"):
                raise CoworkerError("checkpoint_missing", "Web evidence could not be recovered. Please create a new task.")
            sources.extend(research["sources"])
        skill = skill_for_version(task["workflow_version"])
        model = (DeepSeekDraftModel(self.container.settings, self.model.transport, skill_id=skill.id)
                 if isinstance(self.model, DeepSeekDraftModel) else self.model)
        messages = model.messages(task | ({"research": research["metadata"]} if research else {}), sources)
        # Conservative UTF-8 byte bound, with room for chat framing and output.
        reservation = len(json.dumps(messages, ensure_ascii=False).encode()) + self.container.settings.max_output_tokens + 512
        attempt = await asyncio.to_thread(self.repo.reserve_model, task["id"], reservation)
        try:
            source_ids = {source["id"] for source in sources}
            result = await model.generate(messages, task["output_language"], source_ids)
            try:
                validated = parse_draft(skill.id, result.draft.model_dump())
                if skill.id == "research":
                    validate_evidence(validated, sources)
                if not source_references(validated).issubset(source_ids) or (
                    task["output_language"] != "auto" and validated.output_language.lower() != task["output_language"].lower()
                ):
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise DraftFailure("invalid_draft", "The draft did not match the requested service or sources. Please try again.", total_tokens=result.total_tokens) from None
        except DraftFailure as error:
            await asyncio.to_thread(self.repo.settle_model, task["id"], attempt, error.total_tokens, None, "failed")
            raise
        except BaseException:
            # Cancellation/worker loss has an unknown provider outcome. A lost
            # process leaves the same conservative reservation in the database.
            await asyncio.shield(asyncio.to_thread(self.repo.settle_model, task["id"], attempt, None, None, "unknown"))
            raise
        await asyncio.to_thread(self.repo.settle_model, task["id"], attempt, result.total_tokens, result.latency_ms, "completed")
        manifest = [{key: value for key, value in source.items() if key != "text"} for source in sources]
        from .calculations import table_values
        preview = table_values(validated) if skill.id == "spreadsheet" else None
        await asyncio.to_thread(self.repo.save_step, task["id"], "draft", {
            "draft": validated.model_dump(), "sources": manifest, "preview": preview,
            "research": research["metadata"] if research else None,
        })

    async def export(self, task):
        saved = await asyncio.to_thread(self.repo.step, task["id"], "draft")
        if saved is None:
            raise CoworkerError("checkpoint_missing", "The draft could not be recovered. Please create a new task.")
        skill = skill_for_version(task["workflow_version"])
        options = {} if skill.id == "report_email" else {"skill_id": skill.id}
        outputs = await asyncio.to_thread(self.renderer, parse_draft(skill.id, saved["draft"]), saved["sources"], **options)
        manifest = []
        for filename, content_type, body in outputs:
            await asyncio.to_thread(self.repo.worker_task, task["id"])
            if not body or len(body) > 16 * 1024 * 1024:
                raise CoworkerError("export_limit", "The generated document exceeded the export limit.")
            digest = hashlib.sha256(body).hexdigest()
            key = f'{task["owner_id"]}/outputs/{task["id"]}/{digest}/{filename}'
            await asyncio.to_thread(self.container.storage.put, key, body, content_type)
            manifest.append({"filename": filename, "content_type": content_type, "object_key": key,
                             "byte_size": len(body), "sha256": digest})
        await asyncio.to_thread(self.repo.save_step, task["id"], "export", {"artifacts": manifest})

    async def complete(self, task):
        saved = await asyncio.to_thread(self.repo.step, task["id"], "export")
        draft = await asyncio.to_thread(self.repo.step, task["id"], "draft")
        if saved is None or draft is None:
            raise CoworkerError("checkpoint_missing", "The downloads could not be recovered. Please create a new task.")
        for artifact in saved["artifacts"]:
            body = await asyncio.to_thread(self.container.storage.get, artifact["object_key"], artifact["byte_size"])
            if hashlib.sha256(body).hexdigest() != artifact["sha256"]:
                raise CoworkerError("artifact_invalid", "A generated download could not be verified. Please retry.")
        await asyncio.to_thread(self.repo.complete, task["id"], saved["artifacts"], bool(draft["draft"]["missing_information"]))

    async def run_for_test(self, task_id):
        """Same business steps for deterministic tests; never an HTTP background job."""
        try:
            for phase in PHASE_MESSAGES:
                if phase == "research" and (await asyncio.to_thread(self.repo.worker_task, task_id, False))["skill_id"] != "research":
                    continue
                await self.phase(task_id, phase)
        except CoworkerError as error:
            await asyncio.to_thread(self.repo.fail, task_id, error.code, error.message)
            raise
