"""Owner-scoped, bounded, read-only grounding for direct conversation replies.

Selected pins are data, never permission to dispatch Agent work. The original
pin's owner, version and digest are checked both before extraction and again
at reply commitment. No object key or raw attachment body is returned to UI.
"""
from __future__ import annotations

import json
import re
from pathlib import PurePath

from sqlalchemy import select

from .context import _snippet, _utf8_prefix, read_verified_source
from .context_policy import filter_sensitive
from .conversation_context import require_current_selected_sources
from .errors import CoworkerError
from .models import Artifact, Document, DocumentVersion

SUPPORTED_KINDS = frozenset({"pdf", "txt", "docx", "csv", "xlsx", "pptx"})
# This is data cited by the model, never another system-level instruction.
CITATION = re.compile(r"\[\[([^\[\]\r\n]{1,80})\]\]")
MAX_CHAT_SOURCES = 5


def check_grounded_citations(text: str, source_map: dict[str, dict]) -> None:
    """Reject ungrounded replies and invented IDs before durable completion."""
    citations = CITATION.findall(text)
    if not citations or any(identifier not in source_map for identifier in citations):
        raise ValueError("Grounded reply is missing or inventing citations")
    # Malformed source-style markers must not sidestep the allow-list.
    if "[[src-" in CITATION.sub("", text):
        raise ValueError("Malformed source citation")


class ConversationGroundingService:
    def __init__(self, sessions, settings, storage):
        self.sessions, self.settings, self.storage = sessions, settings, storage

    def resolve(self, db, owner: str, selected_sources: list[dict], question: str) -> dict:
        """Resolve only the persisted, owner-bound selection into bounded excerpts.

        Must be called with the conversation's locked admission transaction.
        A missing, expired, foreign or changed selection fails the whole reply.
        """
        if not selected_sources:
            return {"items": [], "source_map": {}, "sources": [], "prompt": ""}
        if len(selected_sources) > MAX_CHAT_SOURCES:
            raise CoworkerError("chat_sources_limit", "Select no more than five files for chat.", 422)
        pins = require_current_selected_sources(db, owner, selected_sources)
        items = []
        source_map = {}
        remaining = min(12288, self.settings.max_agent_context_bytes)
        per_source = min(2048, self.settings.max_agent_context_item_bytes)

        for index, pin in enumerate(pins, start=1):
            kind = ""
            if pin["resource_type"] == "document_version":
                record = db.execute(
                    select(DocumentVersion, Document)
                    .join(Document, Document.id == DocumentVersion.document_id)
                    .where(
                        DocumentVersion.id == pin["resource_id"],
                        DocumentVersion.owner_id == owner,
                        Document.owner_id == owner,
                        Document.id == pin["document_id"],
                        Document.deleted.is_(False),
                    )
                ).first()
                if record is None:
                    raise CoworkerError("context_sources_changed", "Selected source is no longer available. Choose it again.", 409)
                version, document = record
                kind = version.kind.lower()
                label = document.filename
                stored = version
            else:
                stored = db.scalar(select(Artifact).where(
                    Artifact.id == pin["resource_id"], Artifact.owner_id == owner,
                ))
                if stored is None:
                    raise CoworkerError("context_sources_changed", "Selected source is no longer available. Choose it again.", 409)
                kind = PurePath(stored.filename).suffix.lower().lstrip(".")
                label = stored.filename

            if kind not in SUPPORTED_KINDS:
                raise CoworkerError(
                    "chat_source_unsupported",
                    "Chat can read text-based PDF, TXT, DOCX, CSV, XLSX and PPTX files. Use Start task for other attachments.",
                    415,
                )
            if stored.byte_size < 1 or stored.byte_size > self.settings.max_upload_bytes:
                raise CoworkerError("chat_source_too_large", "Choose a smaller attachment for chat.", 413)
            if remaining < 128:
                raise CoworkerError("chat_source_context_limit", "Select fewer or shorter sources for this question.", 422)

            def is_current() -> bool:
                try:
                    require_current_selected_sources(db, owner, selected_sources)
                except CoworkerError:
                    return False
                return True

            text = read_verified_source(
                storage=self.storage,
                object_key=stored.object_key,
                byte_size=int(stored.byte_size),
                sha256=stored.sha256,
                kind=kind,
                max_chars=self.settings.max_source_chars,
                is_current=is_current,
            )
            safe_text, _ = filter_sensitive(text)
            safe_label, _ = filter_sensitive(label)
            excerpt = _snippet(safe_text, question, min(per_source, remaining))
            if not excerpt:
                raise CoworkerError("chat_source_missing_context", "The selected file has no readable context for chat.", 422)
            excerpt = _utf8_prefix(excerpt, min(per_source, remaining))
            remaining -= len(excerpt.encode("utf-8"))
            source_id = f"src-{index}"
            items.append({"source_id": source_id, "label": safe_label[:160], "excerpt": excerpt})
            source_map[source_id] = {
                "resource_type": pin["resource_type"], "resource_id": pin["resource_id"],
                "sha256": pin["sha256"],
            }

        if not items:
            raise CoworkerError("chat_source_missing_context", "The selected files contain no readable context for chat.", 422)
        public_sources = [{
            "source_id": item["source_id"],
            "label": item["label"],
            "resource_type": source_map[item["source_id"]]["resource_type"],
        } for item in items]
        # The source is marshalled as plain user-level data; its instructions do
        # not become policy, tool calls or approvals.
        prompt = json.dumps(
            {"untrusted_selected_source_excerpts": items},
            ensure_ascii=False, separators=(",", ":"),
        )
        return {"items": items, "source_map": source_map, "sources": public_sources, "prompt": prompt}
