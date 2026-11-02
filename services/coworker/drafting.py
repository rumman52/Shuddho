from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from pydantic import ValidationError

from services.api.shuddho_api.llm_deepseek import ResponseTooLarge, _post_review
from .config import Settings
from .content_generation import PROMPT_VERSION, build_content_messages
from .errors import CoworkerError
from .schemas import AnyDraft, DRAFT_TYPES, source_references
from .skills import SKILLS, SkillId


@dataclass
class DraftResult:
    draft: AnyDraft
    total_tokens: int | None
    latency_ms: int
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    prompt_sha256: str | None = None
    task_type: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    reasoning_mode: str | None = None
    retrieval_used: bool = False
    tools_used: list[str] = field(default_factory=list)

    def generation_metadata(self, *, validator_result="passed", error_class=None):
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256,
            "task_type": self.task_type,
            "reasoning_mode": self.reasoning_mode,
            "retrieval_used": self.retrieval_used,
            "tools_used": list(self.tools_used),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "validator_result": validator_result,
            "error_class": error_class,
        }


class DraftFailure(CoworkerError):
    def __init__(self, code, message, *, retryable=False, total_tokens=None):
        super().__init__(code, message, 502)
        self.retryable = retryable
        self.total_tokens = total_tokens


class DraftModel(Protocol):
    def messages(self, task: dict, sources: list[dict]) -> list[dict]: ...
    async def generate(self, messages: list[dict], language: str, source_ids: set[str]) -> DraftResult: ...


class DeepSeekDraftModel:
    def __init__(self, settings: Settings, transport=None, *, skill_id: SkillId = "report_email"):
        self.settings = settings
        self.transport = transport
        self.skill = SKILLS[skill_id]
        self.draft_type = DRAFT_TYPES[skill_id]

    def messages(self, task, sources):
        generation_context = task.get("generation_context") or {}
        tools_used = generation_context.get("tools_used")
        if tools_used is None and task.get("research"):
            tools_used = ["tavily.search"]
        return build_content_messages(
            skill_id=self.skill.id,
            instruction=task["instruction"],
            output_language=task["output_language"],
            sources=sources,
            skill_guidance=self.skill.guidance,
            output_schema=self.draft_type.model_json_schema(),
            research=task.get("research"),
            memory=task.get("memory"),
            retrieval_used=bool(generation_context.get(
                "retrieval_used", task.get("research") or task.get("memory")
            )),
            tools_used=tools_used,
        )

    async def generate(self, messages, language, source_ids):
        if not self.settings.deepseek_api_key:
            raise DraftFailure("model_not_configured", "Your coworker is temporarily unavailable. Please try again later.")
        started = time.monotonic()
        payload = {"model": self.settings.deepseek_model, "messages": messages, "stream": False,
                   "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"},
                   "temperature": 0.2, "max_tokens": self.settings.max_output_tokens}
        try:
            # Shares Part 1's bounded HTTP transport; the coworker has its own
            # structured contract, timeout and account/task budget.
            response = await _post_review(payload, self.settings.deepseek_api_key, self.settings.model_timeout_seconds, self.transport)
        except (TimeoutError, httpx.TimeoutException):
            raise DraftFailure("model_timeout", "The AI response timed out. Please retry with a shorter document.", retryable=True) from None
        except httpx.RequestError:
            raise DraftFailure("model_connection", "The AI service could not be reached. Please try again.", retryable=True) from None
        except ResponseTooLarge:
            raise DraftFailure("model_output_limit", "The AI response exceeded the allowed size. Try a shorter document.") from None
        if response.status_code != 200:
            retryable = response.status_code in {408, 429, 500, 502, 503, 504}
            code = "model_busy" if response.status_code == 429 else "model_unavailable"
            raise DraftFailure(code, "The AI service is unavailable or busy. Please try again shortly.", retryable=retryable)
        total_tokens = None
        input_tokens = None
        output_tokens = None
        finish_reason = None
        task_type = None
        retrieval_used = False
        tools_used = []
        try:
            prompt_bytes = json.dumps(
                messages, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            prompt_sha256 = hashlib.sha256(prompt_bytes).hexdigest()
            if isinstance(messages, list):
                user_message = next(
                    (item for item in reversed(messages)
                     if isinstance(item, dict) and item.get("role") == "user"),
                    None,
                )
                if user_message and isinstance(user_message.get("content"), str):
                    prompt_data = json.loads(user_message["content"])
                    task_data = prompt_data.get("task") if isinstance(prompt_data, dict) else None
                    execution_data = prompt_data.get("execution_metadata") if isinstance(prompt_data, dict) else None
                    if isinstance(task_data, dict) and isinstance(task_data.get("task_type"), str):
                        task_type = task_data["task_type"]
                    if isinstance(execution_data, dict):
                        retrieval_used = execution_data.get("retrieval_used") is True
                        raw_tools = execution_data.get("tools_used")
                        if isinstance(raw_tools, list):
                            tools_used = [value for value in raw_tools if isinstance(value, str)]
            data = response.json()
            usage = data.get("usage")
            if not isinstance(usage, dict):
                usage = {}
            def token_count(name):
                value = usage.get(name)
                return value if type(value) is int and value >= 0 else None
            total_tokens = token_count("total_tokens")
            input_tokens = token_count("prompt_tokens")
            output_tokens = token_count("completion_tokens")
            choices = data["choices"]
            if len(choices) != 1:
                raise ValueError()
            choice = choices[0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason")
            if finish_reason != "stop" or message.get("tool_calls") or message.get("refusal"):
                raise ValueError()
            draft = self.draft_type.model_validate_json(message["content"])
            if language != "auto" and draft.output_language.lower() != language.lower():
                raise ValueError()
            if not source_references(draft).issubset(source_ids):
                raise ValueError()
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, ValidationError):
            raise DraftFailure("invalid_draft", "The AI draft was incomplete or could not be verified. Please try again.", total_tokens=total_tokens) from None
        return DraftResult(
            draft,
            total_tokens,
            int((time.monotonic() - started) * 1000),
            provider="deepseek",
            model=self.settings.deepseek_model,
            prompt_version=PROMPT_VERSION,
            prompt_sha256=prompt_sha256,
            task_type=task_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=finish_reason,
            reasoning_mode="disabled",
            retrieval_used=retrieval_used,
            tools_used=tools_used,
        )
