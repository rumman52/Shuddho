from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


OPENROUTER_ANALYSIS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "grammar",
                            "spelling",
                            "orthography",
                            "punctuation",
                            "style",
                        ],
                    },
                    "subtype": {"type": "string"},
                    "span_text": {"type": "string"},
                    "replacement": {"type": "string"},
                    "explanation_bn": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "category",
                    "subtype",
                    "span_text",
                    "replacement",
                    "explanation_bn",
                    "confidence",
                ],
            },
        }
    },
    "required": ["issues"],
}


SYSTEM_INSTRUCTION = """
You are Shuddho's precise Bangla writing assistant.
Analyze Bangla text only.
Return JSON only with no Markdown, no prose, and no extra keys.
Identify only high-confidence, localized issues.
Allowed categories are:
- grammar
- spelling
- orthography
- punctuation
- style
If uncertain, return {"issues": []}.
Do not flag proper nouns, named entities, likely user words, or code-mixed tokens unless they are clearly wrong.
Do not rewrite whole sentences or change sentence meaning.
Prefer the shortest unambiguous span edit.
Only return replacements that are short, local, and directly grounded in the sentence.
Always return:
- category
- subtype
- span_text
- replacement
- explanation_bn
- confidence
Use category "punctuation" for punctuation or spacing fixes.
Use a precise subtype such as repeated_word, spacing_error, duplicate_punctuation, pronoun_verb_agreement, spelling_error, orthography_variant, or usage_confusion.
Good targets include repeated words, duplicated particles, pronoun-verb agreement, punctuation or spacing fixes, and exact standard Bangla word or phrase corrections.
Do not invent broad rewrites, paraphrases, tone changes, or speculative grammar changes.
""".strip()


@dataclass(frozen=True)
class OpenRouterPrompt:
    messages: list[dict[str, str]]
    response_format: dict[str, object]


def build_openrouter_prompt(
    sentence: str,
    mode: str,
    *,
    local_hints: list[dict[str, object]] | None = None,
) -> OpenRouterPrompt:
    hint_payload = json.dumps((local_hints or [])[:6], ensure_ascii=False)
    mode_guidance = _mode_guidance(mode)
    user_content = "\n".join(
        [
            "Analyze this Bangla sentence conservatively and return JSON only.",
            f"Mode: {mode}",
            mode_guidance,
            "Use the exact shortest unambiguous span_text from the sentence below. Do not return character offsets.",
            "Return only precise, localized edits with short replacements.",
            "Never rewrite the whole sentence.",
            "If you are not highly confident, return {\"issues\": []}.",
            f"Sentence: {sentence}",
            f"Local hints: {hint_payload}",
        ]
    )
    return OpenRouterPrompt(
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_content},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "shuddho_bangla_analysis",
                "strict": True,
                "schema": OPENROUTER_ANALYSIS_RESPONSE_SCHEMA,
            },
        },
    )


def _mode_guidance(mode: str) -> str:
    if mode == "formal":
        return (
            "Formal mode may include careful style or standard-form normalization, but only when the edit stays short, local, and clearly justified."
        )
    if mode == "strict":
        return "Strict mode may include more context-sensitive Bengali grammar or orthography issues, but only when they are still grounded, local, and specific."
    return "Standard mode must stay low-noise, but it should still return strong localized Bengali corrections when the problem is clear and the edit is precise."
