from __future__ import annotations

import re
from collections.abc import Iterable

from services.spell.shuddho_spell.engine import SpellEngine
from shared.constants.bangla import BANGLA_WORD_PATTERN, COMMON_POSTPOSITIONS
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .models import CandidateBundle, DetectorFinding

MULTISPACE_PATTERN = re.compile(r"[^\S\r\n]{2,}")
SPACE_BEFORE_PUNCTUATION_PATTERN = re.compile(r"^\s*([,.;:!?।])$")
SPACE_AFTER_PUNCTUATION_PATTERN = re.compile(r"^([,.;:!?।])([^\s])$")
REPEATED_WORD_PATTERN = re.compile(r"^(?P<word>[\u0980-\u09FF]+)(?P<space>\s+)(?P=word)$")
GENITIVE_PATTERN = re.compile(r"^(?P<noun>[\u0980-\u09FF]+)\s+(?P<marker>এর|র)$")


class CandidateGenerator:
    def __init__(self, *, spell_engine: SpellEngine | None = None) -> None:
        self.spell_engine = spell_engine

    def generate(
        self,
        *,
        spell_suggestions: list[Suggestion],
        rule_suggestions: list[Suggestion],
        detector_findings: list[DetectorFinding],
        model_suggestions: list[Suggestion] | None = None,
        text: str = "",
    ) -> CandidateBundle:
        return CandidateBundle(
            spell_suggestions=self._rulebacked_candidates(spell_suggestions),
            rule_suggestions=self._rulebacked_candidates(rule_suggestions),
            detector_suggestions=self._detector_backed_candidates(detector_findings, text=text),
            model_suggestions=self._rulebacked_candidates(model_suggestions or []),
        )

    def _rulebacked_candidates(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        return list(suggestions)

    def _detector_backed_candidates(self, findings: list[DetectorFinding], *, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for finding in findings:
            if finding.replacement_options:
                suggestions.append(self._to_suggestion(finding, replacement_options=self._unique_replacements(finding.replacement_options)))
                continue

            replacements = self._resolve_replacements(finding, text=text)
            if replacements:
                suggestions.append(self._to_suggestion(finding, replacement_options=replacements, actionable=True))
                continue
            suggestions.append(self._to_suggestion(finding))
        return suggestions

    def _resolve_replacements(self, finding: DetectorFinding, *, text: str) -> list[str]:
        if finding.replacement_options:
            return self._unique_replacements(finding.replacement_options)

        if finding.category == SuggestionCategory.SPELLING:
            return self._spell_backed_replacements(finding.original_text)
        if finding.category == SuggestionCategory.PUNCTUATION:
            return self._punctuation_replacements(finding.original_text, text=text)
        if finding.category == SuggestionCategory.GRAMMAR:
            grammar_replacements = self._grammar_replacements(finding.original_text)
            if grammar_replacements:
                return grammar_replacements
            return self._spell_backed_replacements(finding.original_text)
        if finding.category == SuggestionCategory.STYLE:
            spacing_replacements = self._spacing_replacements(finding.original_text)
            if spacing_replacements:
                return spacing_replacements
            return self._punctuation_replacements(finding.original_text, text=text)
        return []

    def _spell_backed_replacements(self, token: str) -> list[str]:
        if self.spell_engine is None:
            return []
        if not BANGLA_WORD_PATTERN.fullmatch(token):
            return []
        candidates = self.spell_engine.generate_candidates(token)
        return self._unique_replacements(candidate.word for candidate in candidates[:2])

    def _punctuation_replacements(self, original_text: str, *, text: str) -> list[str]:
        stripped = original_text.strip()
        if not stripped:
            return []

        if len(stripped) > 1 and len(set(stripped)) == 1 and stripped[0] in ",.;:!?।":
            return [stripped[0]]

        if stripped == "." and self._looks_bengali_context(text):
            return ["।"]

        before_match = SPACE_BEFORE_PUNCTUATION_PATTERN.fullmatch(original_text)
        if before_match:
            return [before_match.group(1)]

        after_match = SPACE_AFTER_PUNCTUATION_PATTERN.fullmatch(original_text)
        if after_match:
            return [f"{after_match.group(1)} {after_match.group(2)}"]

        return []

    def _spacing_replacements(self, original_text: str) -> list[str]:
        replacements: list[str] = []
        collapsed = MULTISPACE_PATTERN.sub(" ", original_text)
        if collapsed != original_text and collapsed.strip():
            replacements.append(collapsed)

        before_match = SPACE_BEFORE_PUNCTUATION_PATTERN.fullmatch(original_text)
        if before_match:
            replacements.append(before_match.group(1))

        after_match = SPACE_AFTER_PUNCTUATION_PATTERN.fullmatch(original_text)
        if after_match:
            replacements.append(f"{after_match.group(1)} {after_match.group(2)}")

        return self._unique_replacements(replacements)

    def _grammar_replacements(self, original_text: str) -> list[str]:
        repeated_match = REPEATED_WORD_PATTERN.fullmatch(original_text)
        if repeated_match:
            return [repeated_match.group("word")]

        if original_text == "না না":
            return ["না"]

        genitive_match = GENITIVE_PATTERN.fullmatch(original_text)
        if genitive_match:
            noun = genitive_match.group("noun")
            marker = genitive_match.group("marker")
            return [self._join_genitive(noun, marker)]

        if BANGLA_WORD_PATTERN.fullmatch(original_text):
            for suffix in COMMON_POSTPOSITIONS:
                if original_text.endswith(suffix) and len(original_text) > len(suffix) + 1:
                    stem = original_text[: -len(suffix)]
                    if BANGLA_WORD_PATTERN.fullmatch(stem):
                        return [f"{stem} {suffix}"]

        return []

    def _to_suggestion(
        self,
        finding: DetectorFinding,
        *,
        replacement_options: list[str] | None = None,
        actionable: bool = False,
    ) -> Suggestion:
        resolved_replacements = replacement_options or list(finding.replacement_options)
        resolved_source = SuggestionSource.HYBRID if actionable and finding.source == SuggestionSource.MODEL else finding.source
        resolved_confidence = finding.confidence
        if actionable:
            resolved_confidence = min(0.97, round(finding.confidence + 0.06, 2))

        explanation_bn, explanation_en = self._build_explanation(
            finding,
            replacement_options=resolved_replacements,
            actionable=actionable,
        )

        return Suggestion(
            id=stable_id(
                "detector",
                f"{finding.rule_id}:{finding.subtype}:{finding.span_start}:{finding.span_end}:{finding.original_text}:{','.join(resolved_replacements)}",
            ),
            rule_id=finding.rule_id,
            category=finding.category,
            subtype=finding.subtype,
            span_start=finding.span_start,
            span_end=finding.span_end,
            original_text=finding.original_text,
            replacement_options=resolved_replacements,
            confidence=resolved_confidence,
            explanation_bn=explanation_bn,
            explanation_en=explanation_en,
            source=resolved_source,
            severity=finding.severity if actionable else max(finding.severity, SuggestionSeverity.LOW, key=_severity_rank),
        )

    def _build_explanation(
        self,
        finding: DetectorFinding,
        *,
        replacement_options: list[str],
        actionable: bool,
    ) -> tuple[str, str]:
        if not actionable or not replacement_options:
            return finding.explanation_bn, finding.explanation_en

        primary_replacement = replacement_options[0]
        if finding.category == SuggestionCategory.SPELLING:
            return (
                f"ডিটেক্টর ও বানান-প্রার্থী মিলিয়ে এখানে '{finding.original_text}' এর বদলে '{primary_replacement}' ভালো হবে।",
                f"Detector and spelling candidates both support '{primary_replacement}' as the best correction here.",
            )
        if finding.category == SuggestionCategory.GRAMMAR:
            return (
                f"এখানে '{finding.original_text}' এর বদলে '{primary_replacement}' লিখলে বাক্যটি বেশি স্বাভাবিক হবে।",
                f"Replacing '{finding.original_text}' with '{primary_replacement}' makes this phrase more natural.",
            )
        if finding.category == SuggestionCategory.PUNCTUATION:
            return (
                f"এখানে '{finding.original_text}' এর বদলে '{primary_replacement}' ব্যবহার করুন।",
                f"Use '{primary_replacement}' instead of '{finding.original_text}' here.",
            )
        return (
            f"এখানে '{finding.original_text}' অংশটি '{primary_replacement}' করলে লেখাটি বেশি পরিষ্কার হবে।",
            f"Changing '{finding.original_text}' to '{primary_replacement}' makes this text clearer.",
        )

    def _unique_replacements(self, replacements: Iterable[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for replacement in replacements:
            normalized = replacement.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
        return unique

    def _looks_bengali_context(self, text: str) -> bool:
        return sum(1 for character in text if "\u0980" <= character <= "\u09ff") >= 2

    def _join_genitive(self, noun: str, marker: str) -> str:
        if marker == "র":
            return f"{noun}র"
        if noun.endswith(("া", "ি", "ী", "ু", "ূ", "ে", "ো", "ৌ")):
            return f"{noun}র"
        return f"{noun}এর"


def _severity_rank(severity: SuggestionSeverity) -> int:
    return {
        SuggestionSeverity.LOW: 0,
        SuggestionSeverity.MEDIUM: 1,
        SuggestionSeverity.HIGH: 2,
    }[severity]
