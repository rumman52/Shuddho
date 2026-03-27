from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from .parsing import GeminiIssue, parse_gemini_response
from .prompting import GEMINI_ANALYSIS_RESPONSE_SCHEMA, build_bangla_analysis_prompt

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
DEFAULT_TIMEOUT_SECONDS = 20
GEMINI_API_KEY_ENV_VAR = "GEMINI_API_KEY"
GEMINI_MODEL_ENV_VAR = "GEMINI_MODEL"
GEMINI_TIMEOUT_SECONDS_ENV_VAR = "GEMINI_TIMEOUT_SECONDS"

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - exercised in fallback tests via monkeypatch
    genai = None
    types = None


@dataclass(frozen=True)
class GeminiHint:
    start: int
    end: int
    category: str
    subtype: str
    text: str


class GeminiClient:
    def __init__(
        self,
        *,
        api_client: Any | None,
        model_name: str,
        timeout_seconds: int,
        enabled: bool,
    ) -> None:
        self.api_client = api_client
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> "GeminiClient":
        environment = os.environ if environ is None else environ
        model_name = (environment.get(GEMINI_MODEL_ENV_VAR) or DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
        timeout_seconds = _parse_timeout(environment.get(GEMINI_TIMEOUT_SECONDS_ENV_VAR))
        api_key = (environment.get(GEMINI_API_KEY_ENV_VAR) or "").strip()

        if not api_key:
            logger.info("Gemini integration is disabled because %s is not set.", GEMINI_API_KEY_ENV_VAR)
            return cls.disabled(model_name=model_name, timeout_seconds=timeout_seconds)

        if genai is None or types is None:
            logger.warning("Gemini integration is disabled because google-genai is not installed.")
            return cls.disabled(model_name=model_name, timeout_seconds=timeout_seconds)

        try:
            api_client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    api_version="v1alpha",
                    timeout=timeout_seconds,
                ),
            )
        except Exception as error:  # pragma: no cover - constructor failures are environment-specific
            logger.warning("Gemini client initialization failed: %s", error)
            return cls.disabled(model_name=model_name, timeout_seconds=timeout_seconds)

        return cls(
            api_client=api_client,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            enabled=True,
        )

    @classmethod
    def disabled(
        cls,
        *,
        model_name: str = DEFAULT_GEMINI_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> "GeminiClient":
        return cls(
            api_client=None,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            enabled=False,
        )

    def is_available(self) -> bool:
        return self.enabled and self.api_client is not None

    def analyze_sentence(
        self,
        sentence: str,
        mode: str,
        *,
        local_hints: list[GeminiHint] | None = None,
    ) -> list[GeminiIssue]:
        if not self.is_available():
            return []
        if not sentence.strip():
            return []

        prompt = build_bangla_analysis_prompt(
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

        try:
            response = self.api_client.models.generate_content(
                model=self.model_name,
                contents=prompt.user_content,
                config=types.GenerateContentConfig(
                    system_instruction=prompt.system_instruction,
                    response_mime_type="application/json",
                    response_schema=GEMINI_ANALYSIS_RESPONSE_SCHEMA,
                    temperature=0.1,
                    candidate_count=1,
                    max_output_tokens=512,
                ),
            )
        except Exception as error:
            logger.warning("Gemini analyze_sentence failed: %s", error)
            return []

        raw_text = getattr(response, "text", "") or ""
        return parse_gemini_response(raw_text, sentence=sentence)


def _parse_timeout(value: str | None) -> int:
    if value is None or not value.strip():
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout_seconds = int(value)
    except ValueError:
        logger.warning(
            "Invalid %s value '%s'; falling back to %s.",
            GEMINI_TIMEOUT_SECONDS_ENV_VAR,
            value,
            DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS
    if timeout_seconds <= 0:
        logger.warning(
            "Non-positive %s value '%s'; falling back to %s.",
            GEMINI_TIMEOUT_SECONDS_ENV_VAR,
            value,
            DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS
    return timeout_seconds
