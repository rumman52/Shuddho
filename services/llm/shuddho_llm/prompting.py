from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


GEMINI_ANALYSIS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "integer", "minimum": 0},
                    "end": {"type": "integer", "minimum": 0},
                    "original": {"type": "string"},
                    "replacement": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "grammar_error",
                            "spelling_error",
                            "punctuation_error",
                            "spacing_error",
                            "orthography_variant",
                            "style_suggestion",
                        ],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason_bn": {"type": "string"},
                },
                "required": [
                    "start",
                    "end",
                    "original",
                    "replacement",
                    "category",
                    "confidence",
                    "reason_bn",
                ],
            },
        }
    },
    "required": ["issues"],
}


SYSTEM_INSTRUCTION = """
You are a conservative Bangla writing assistant for Shuddho.
Analyze Bangla text only.
Return JSON only with no Markdown, no prose, and no extra keys.
Identify only high-confidence issues.
Allowed categories are:
- grammar_error
- spelling_error
- punctuation_error
- spacing_error
- orthography_variant
- style_suggestion
If uncertain, return {"issues": []}.
Do not flag proper nouns, named entities, likely user words, or code-mixed tokens unless they are clearly wrong.
Do not rewrite the whole sentence unless a precise localized correction is truly necessary.
Prefer minimal span edits over sentence rewrites.
""".strip()


@dataclass(frozen=True)
class GeminiPrompt:
    system_instruction: str
    user_content: str


def build_bangla_analysis_prompt(
    sentence: str,
    mode: str,
    *,
    local_hints: list[dict[str, object]] | None = None,
) -> GeminiPrompt:
    hint_payload = json.dumps((local_hints or [])[:6], ensure_ascii=False)
    mode_guidance = _mode_guidance(mode)
    user_content = "\n".join(
        [
            "Analyze this Bangla sentence conservatively and return JSON only.",
            f"Mode: {mode}",
            mode_guidance,
            "Use 0-based character offsets relative to the sentence below.",
            "If you are not highly confident, return {\"issues\": []}.",
            f"Sentence: {sentence}",
            f"Local hints: {hint_payload}",
        ]
    )
    return GeminiPrompt(
        system_instruction=SYSTEM_INSTRUCTION,
        user_content=user_content,
    )


def _mode_guidance(mode: str) -> str:
    if mode == "formal":
        return (
            "Formal mode may include careful style normalization, but only when the suggestion is still precise and justified."
        )
    if mode == "strict":
        return "Strict mode may include more context-sensitive issues, but only when they are still grounded and specific."
    return "Standard mode must stay low-noise and should avoid optional variants or stylistic rewrites unless the issue is highly trustworthy."
