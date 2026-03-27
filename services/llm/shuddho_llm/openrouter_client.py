from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import requests

from .parsing import OpenRouterIssue, parse_openrouter_response
from .prompting import build_openrouter_prompt

logger = logging.getLogger(__name__)

DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-super-120b-a12b"
DEFAULT_TIMEOUT_SECONDS = 20
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY_ENV_VAR = "OPENROUTER_API_KEY"
OPENROUTER_MODEL_ENV_VAR = "OPENROUTER_MODEL"
OPENROUTER_TIMEOUT_SECONDS_ENV_VAR = "OPENROUTER_TIMEOUT_SECONDS"
PLACEHOLDER_API_KEY_VALUES = {
    "your_key_here",
    "paste_my_new_real_key_here",
}


@dataclass(frozen=True)
class OpenRouterHint:
    start: int
    end: int
    category: str
    subtype: str
    text: str


class OpenRouterClient:
    def __init__(
        self,
        *,
        session: requests.Session | Any | None,
        api_key: str | None,
        model_name: str,
        timeout_seconds: int,
        enabled: bool,
    ) -> None:
        self.session = session
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> "OpenRouterClient":
        environment = os.environ if environ is None else environ
        model_name = (environment.get(OPENROUTER_MODEL_ENV_VAR) or DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL
        timeout_seconds = _parse_timeout(environment.get(OPENROUTER_TIMEOUT_SECONDS_ENV_VAR))
        api_key = (environment.get(OPENROUTER_API_KEY_ENV_VAR) or "").strip()

        if not api_key or api_key.casefold() in PLACEHOLDER_API_KEY_VALUES:
            logger.info(
                "OpenRouter integration is disabled because %s is missing or still set to a placeholder value.",
                OPENROUTER_API_KEY_ENV_VAR,
            )
            return cls.disabled(model_name=model_name, timeout_seconds=timeout_seconds)

        return cls(
            session=requests.Session(),
            api_key=api_key,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            enabled=True,
        )

    @classmethod
    def disabled(
        cls,
        *,
        model_name: str = DEFAULT_OPENROUTER_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> "OpenRouterClient":
        return cls(
            session=None,
            api_key=None,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            enabled=False,
        )

    def is_available(self) -> bool:
        return self.enabled and self.session is not None and bool(self.api_key)

    def analyze_sentence(
        self,
        sentence: str,
        mode: str,
        *,
        local_hints: list[OpenRouterHint] | None = None,
    ) -> list[OpenRouterIssue]:
        if not self.is_available():
            return []
        if not sentence.strip():
            return []

        prompt = build_openrouter_prompt(
            sentence,
            mode,
            local_hints=[
                {
                    "start": hint.start,
                    "end": hint.end,
                    "category": hint.category,
                    "subtype": hint.subtype,
                    "text": hint.text,
                }
                for hint in (local_hints or [])
            ],
        )

        payload = {
            "model": self.model_name,
            "messages": prompt.messages,
            "temperature": 0.1,
            "reasoning": {
                "enabled": True,
                "exclude": True,
            },
            "response_format": prompt.response_format,
        }

        try:
            response = self.session.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as error:
            logger.warning("OpenRouter analyze_sentence failed: %s", error)
            return []

        if getattr(response, "status_code", 500) >= 400:
            logger.warning("OpenRouter analyze_sentence returned status %s", getattr(response, "status_code", "unknown"))
            return []

        try:
            response_payload = response.json()
        except ValueError:
            return []

        raw_text = _extract_message_content(response_payload)
        return parse_openrouter_response(raw_text, sentence=sentence)


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        return "\n".join(text_parts)
    return ""


def _parse_timeout(value: str | None) -> int:
    if value is None or not value.strip():
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout_seconds = int(value)
    except ValueError:
        logger.warning(
            "Invalid %s value '%s'; falling back to %s.",
            OPENROUTER_TIMEOUT_SECONDS_ENV_VAR,
            value,
            DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS
    if timeout_seconds <= 0:
        logger.warning(
            "Non-positive %s value '%s'; falling back to %s.",
            OPENROUTER_TIMEOUT_SECONDS_ENV_VAR,
            value,
            DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS
    return timeout_seconds
