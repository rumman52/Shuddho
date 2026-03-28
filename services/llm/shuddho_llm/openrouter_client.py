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
OPENROUTER_API_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_CHAT_COMPLETIONS_URL = f"{OPENROUTER_API_BASE_URL}/chat/completions"
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
        configured: bool | None = None,
        api_key_present: bool | None = None,
    ) -> None:
        self.session = session
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self.configured = enabled if configured is None else configured
        self.api_key_present = bool(api_key) if api_key_present is None else api_key_present

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> "OpenRouterClient":
        environment = os.environ if environ is None else environ
        model_name = (environment.get(OPENROUTER_MODEL_ENV_VAR) or DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL
        timeout_seconds = _parse_timeout(environment.get(OPENROUTER_TIMEOUT_SECONDS_ENV_VAR))
        api_key = (environment.get(OPENROUTER_API_KEY_ENV_VAR) or "").strip()
        api_key_present = bool(api_key)
        configured = api_key_present and api_key.casefold() not in PLACEHOLDER_API_KEY_VALUES

        logger.info(
            "OpenRouter client initialization api_key_found=%s configured=%s model=%s timeout_seconds=%s",
            api_key_present,
            configured,
            model_name,
            timeout_seconds,
        )

        if not configured:
            if not api_key_present:
                logger.warning(
                    "OpenRouter integration is disabled because %s is missing from the environment.",
                    OPENROUTER_API_KEY_ENV_VAR,
                )
            else:
                logger.warning(
                    "OpenRouter integration is disabled because %s is still set to a placeholder value.",
                    OPENROUTER_API_KEY_ENV_VAR,
                )
            return cls.disabled(
                model_name=model_name,
                timeout_seconds=timeout_seconds,
                configured=False,
                api_key_present=api_key_present,
            )

        return cls(
            session=requests.Session(),
            api_key=api_key,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            enabled=True,
            configured=True,
            api_key_present=True,
        )

    @classmethod
    def disabled(
        cls,
        *,
        model_name: str = DEFAULT_OPENROUTER_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        configured: bool = False,
        api_key_present: bool = False,
    ) -> "OpenRouterClient":
        return cls(
            session=None,
            api_key=None,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            enabled=False,
            configured=configured,
            api_key_present=api_key_present,
        )

    def is_available(self) -> bool:
        return self.enabled and self.session is not None and bool(self.api_key)

    def is_configured(self) -> bool:
        return self.configured

    def has_api_key(self) -> bool:
        return self.api_key_present

    def analyze_sentence(
        self,
        sentence: str,
        mode: str,
        *,
        local_hints: list[OpenRouterHint] | None = None,
    ) -> list[OpenRouterIssue]:
        if not self.is_available():
            logger.debug(
                "Skipping OpenRouter request because client is unavailable model=%s configured=%s",
                self.model_name,
                self.is_configured(),
            )
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

        logger.debug(
            "Sending OpenRouter request model=%s mode=%s chars=%s local_hints=%s",
            self.model_name,
            mode,
            len(sentence),
            len(local_hints or []),
        )

        try:
            response = self.session.post(
                OPENROUTER_CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as error:
            logger.warning(
                "OpenRouter analyze_sentence failed model=%s timeout_seconds=%s error=%s",
                self.model_name,
                self.timeout_seconds,
                error,
            )
            return []

        if getattr(response, "status_code", 500) >= 400:
            logger.warning(
                "OpenRouter analyze_sentence returned status=%s model=%s response_body=%r",
                getattr(response, "status_code", "unknown"),
                self.model_name,
                _extract_response_text(response),
            )
            return []

        try:
            response_payload = response.json()
        except ValueError:
            logger.warning(
                "OpenRouter analyze_sentence returned non-JSON payload model=%s response_body=%r",
                self.model_name,
                _extract_response_text(response),
            )
            return []

        raw_text = _extract_message_content(response_payload)
        issues = parse_openrouter_response(raw_text, sentence=sentence)
        if raw_text.strip() and not issues:
            logger.info(
                "OpenRouter response was discarded after parsing or validation model=%s raw_chars=%s",
                self.model_name,
                len(raw_text),
            )
        return issues


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


def _extract_response_text(response: Any, max_chars: int = 400) -> str:
    raw_text = getattr(response, "text", "")
    if not isinstance(raw_text, str):
        return ""
    compact = " ".join(raw_text.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars]}..."
