from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from services.spell.shuddho_spell.engine import SpellEngine
from shared.constants.bangla import BANGLA_WORD_PATTERN, COMMON_POSTPOSITIONS, SAFE_EXACT_TYPOS
from shared.schemas.python_models import AnalyzeMode, Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .models import CandidateBundle, DetectorFinding

MULTISPACE_PATTERN = re.compile(r"[^\S\r\n]{2,}")
SPACE_BEFORE_PUNCTUATION_PATTERN = re.compile(r"^\s*([,.;:!?।])$")
SPACE_AFTER_PUNCTUATION_PATTERN = re.compile(r"^([,.;:!?।])([^\s])$")
REPEATED_WORD_PATTERN = re.compile(r"^(?P<word>[\u0980-\u09FF]+)(?P<space>\s+)(?P=word)$")
GENITIVE_PATTERN = re.compile(r"^(?P<noun>[\u0980-\u09FF]+)\s+(?P<marker>এর|র)$")
CURATED_REPEATED_WORD_PATTERN = re.compile(r"(?<![\u0980-\u09FFA-Za-z])(?P<word>[\u0980-\u09FF]{2,})(?P<space>\s+)(?P=word)(?![\u0980-\u09FFA-Za-z])")
DUPLICATE_PUNCTUATION_PATTERN = re.compile(r"([,.;:!?।])\1+")
SPACE_BEFORE_PUNCTUATION_SCAN_PATTERN = re.compile(r"\s+([,.;:!?।])")
SPACE_AFTER_TERMINATOR_SCAN_PATTERN = re.compile(r"([।!?])([^\s\"'”’)\]}])")


class CandidateGenerator:
    def __init__(self, *, spell_engine: SpellEngine | None = None) -> None:
        self.spell_engine = spell_engine

    def generate(
        self,
        *,
        spell_suggestions: list[Suggestion],
        rule_suggestions: list[Suggestion],
        detector_findings: list[DetectorFinding],
        corrector_suggestions: list[Suggestion] | None = None,
        text: str = "",
        personal_dictionary: list[str] | None = None,
        mode: AnalyzeMode = AnalyzeMode.STANDARD,
    ) -> CandidateBundle:
        curated_contextual_suggestions = self._curated_contextual_candidates(
            text=text,
            spell_suggestions=spell_suggestions,
            rule_suggestions=rule_suggestions,
            personal_dictionary=personal_dictionary,
            mode=mode,
        )
        merged_rule_suggestions = self._merge_unique_suggestions(rule_suggestions, curated_contextual_suggestions)
        return CandidateBundle(
            spell_suggestions=self._rulebacked_candidates(spell_suggestions),
            rule_suggestions=self._rulebacked_candidates(merged_rule_suggestions),
            detector_suggestions=self._detector_backed_candidates(
                detector_findings,
                spell_suggestions=spell_suggestions,
                rule_suggestions=merged_rule_suggestions,
                text=text,
            ),
            corrector_suggestions=self._corrector_candidates(corrector_suggestions or []),
        )

    def _rulebacked_candidates(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        return list(suggestions)

    def _corrector_candidates(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        return [
            suggestion
            for suggestion in suggestions
            if self._is_safe_corrector_suggestion(suggestion)
        ]

    def _curated_contextual_candidates(
        self,
        *,
        text: str,
        spell_suggestions: Sequence[Suggestion],
        rule_suggestions: Sequence[Suggestion],
        personal_dictionary: list[str] | None,
        mode: AnalyzeMode,
    ) -> list[Suggestion]:
        del mode
        existing_suggestions = [*spell_suggestions, *rule_suggestions]
        personal_words = self._expanded_personal_dictionary(personal_dictionary)
        suggestions: list[Suggestion] = []
        suggestions.extend(
            self._curated_repeated_word_suggestions(
                text,
                existing_suggestions,
                personal_words=personal_words,
                personal_dictionary=personal_dictionary,
            )
        )
        suggestions.extend(self._curated_duplicate_punctuation_suggestions(text, existing_suggestions))
        suggestions.extend(self._curated_space_before_punctuation_suggestions(text, existing_suggestions))
        suggestions.extend(self._curated_space_after_terminator_suggestions(text, existing_suggestions))
        suggestions.extend(
            self._curated_exact_correction_suggestions(
                text,
                existing_suggestions,
                personal_words=personal_words,
            )
        )
        return self._merge_unique_suggestions([], suggestions)

    def _detector_backed_candidates(
        self,
        findings: list[DetectorFinding],
        *,
        spell_suggestions: list[Suggestion],
        rule_suggestions: list[Suggestion],
        text: str,
    ) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for finding in findings:
            contextual_replacements = self._contextual_replacements(
                finding,
                spell_suggestions=spell_suggestions,
                rule_suggestions=rule_suggestions,
            )
            if contextual_replacements:
                suggestions.append(
                    self._to_suggestion(
                        finding,
                        replacement_options=contextual_replacements,
                        actionable=True,
                        contextual_support=len(contextual_replacements),
                    )
                )
                continue

            if finding.replacement_options:
                suggestions.append(
                    self._to_suggestion(
                        finding,
                        replacement_options=self._unique_replacements(finding.replacement_options),
                    )
                )
                continue

            replacements = self._resolve_replacements(finding, text=text)
            if replacements:
                suggestions.append(
                    self._to_suggestion(
                        finding,
                        replacement_options=replacements,
                        actionable=True,
                        contextual_support=1,
                    )
                )
                continue
        return suggestions

    def _curated_repeated_word_suggestions(
        self,
        text: str,
        existing_suggestions: Sequence[Suggestion],
        *,
        personal_words: set[str],
        personal_dictionary: list[str] | None,
    ) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in CURATED_REPEATED_WORD_PATTERN.finditer(text):
            word = match.group("word")
            if word in personal_words:
                continue
            if self.spell_engine is not None and self.spell_engine.is_probable_named_entity_or_user_word(
                word,
                personal_dictionary=personal_dictionary,
            ):
                continue
            span_start = match.start()
            span_end = match.end()
            if self._has_covering_suggestion(
                existing_suggestions,
                span_start,
                span_end,
                word,
                minimum_confidence=0.9,
            ):
                continue
            suggestions.append(
                Suggestion(
                    id=stable_id("curated", f"repeat:{span_start}:{span_end}:{word}"),
                    rule_id="REP_001",
                    category=SuggestionCategory.GRAMMAR,
                    subtype="repeated_word",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=text[span_start:span_end],
                    replacement_options=[word],
                    confidence=0.95,
                    explanation_bn=f"একই শব্দ '{word}' পরপর দুইবার এসেছে।",
                    explanation_en=f"The word '{word}' appears twice in a row.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM,
                )
            )
        return suggestions

    def _curated_duplicate_punctuation_suggestions(
        self,
        text: str,
        existing_suggestions: Sequence[Suggestion],
    ) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in DUPLICATE_PUNCTUATION_PATTERN.finditer(text):
            original_text = match.group(0)
            replacement = original_text[0]
            span_start = match.start()
            span_end = match.end()
            if self._has_covering_suggestion(existing_suggestions, span_start, span_end, replacement):
                continue
            suggestions.append(
                Suggestion(
                    id=stable_id("curated", f"punctuation:{span_start}:{span_end}:{original_text}"),
                    rule_id="PUNC_001",
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="duplicate_punctuation",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=original_text,
                    replacement_options=[replacement],
                    confidence=0.99,
                    explanation_bn="এখানে বাড়তি যতিচিহ্ন আছে।",
                    explanation_en="There is duplicate punctuation here.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _curated_space_before_punctuation_suggestions(
        self,
        text: str,
        existing_suggestions: Sequence[Suggestion],
    ) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in SPACE_BEFORE_PUNCTUATION_SCAN_PATTERN.finditer(text):
            punctuation = match.group(1)
            span_start = match.start()
            span_end = match.end()
            if self._has_covering_suggestion(existing_suggestions, span_start, span_end, punctuation):
                continue
            suggestions.append(
                Suggestion(
                    id=stable_id("curated", f"space-before:{span_start}:{span_end}:{punctuation}"),
                    rule_id="PUNC_002",
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="space_before_punctuation",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=text[span_start:span_end],
                    replacement_options=[punctuation],
                    confidence=0.98,
                    explanation_bn="যতিচিহ্নের আগে অপ্রয়োজনীয় ফাঁকা আছে।",
                    explanation_en="There is unnecessary whitespace before punctuation.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _curated_space_after_terminator_suggestions(
        self,
        text: str,
        existing_suggestions: Sequence[Suggestion],
    ) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in SPACE_AFTER_TERMINATOR_SCAN_PATTERN.finditer(text):
            punctuation = match.group(1)
            next_character = match.group(2)
            span_start = match.start()
            span_end = match.end()
            replacement = f"{punctuation} {next_character}"
            if self._has_covering_suggestion(existing_suggestions, span_start, span_end, replacement):
                continue
            suggestions.append(
                Suggestion(
                    id=stable_id("curated", f"space-after:{span_start}:{span_end}:{replacement}"),
                    rule_id="PUNC_004",
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="space_after_punctuation",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=text[span_start:span_end],
                    replacement_options=[replacement],
                    confidence=0.88,
                    explanation_bn="যতিচিহ্নের পরে সাধারণত একটি ফাঁকা থাকে।",
                    explanation_en="Punctuation is usually followed by a space here.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _curated_exact_correction_suggestions(
        self,
        text: str,
        existing_suggestions: Sequence[Suggestion],
        *,
        personal_words: set[str],
    ) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for typo, replacement in SAFE_EXACT_TYPOS.items():
            typo_pattern = re.compile(rf"(?<![\u0980-\u09FFA-Za-z]){re.escape(typo)}(?![\u0980-\u09FFA-Za-z])")
            for match in typo_pattern.finditer(text):
                original_text = match.group(0)
                if original_text in personal_words or replacement in personal_words:
                    continue
                span_start = match.start()
                span_end = match.end()
                if self._has_covering_suggestion(existing_suggestions, span_start, span_end, replacement):
                    continue
                category = SuggestionCategory.SPELLING if " " not in original_text else SuggestionCategory.GRAMMAR
                suggestions.append(
                    Suggestion(
                        id=stable_id("curated", f"exact:{span_start}:{span_end}:{original_text}->{replacement}"),
                        rule_id="SPELL_001" if category == SuggestionCategory.SPELLING else "GRAM_009",
                        category=category,
                        subtype="spelling_error" if category == SuggestionCategory.SPELLING else "safe_exact_correction",
                        span_start=span_start,
                        span_end=span_end,
                        original_text=original_text,
                        replacement_options=[replacement],
                        confidence=0.98,
                        explanation_bn=f"এখানে '{original_text}' এর বদলে '{replacement}' লেখা উচিত।",
                        explanation_en=f"Replace '{original_text}' with '{replacement}' here.",
                        source=SuggestionSource.RULE,
                        severity=SuggestionSeverity.MEDIUM if category == SuggestionCategory.SPELLING else SuggestionSeverity.LOW,
                    )
                )
        return suggestions

    def _contextual_replacements(
        self,
        finding: DetectorFinding,
        *,
        spell_suggestions: Sequence[Suggestion],
        rule_suggestions: Sequence[Suggestion],
    ) -> list[str]:
        exact_support = self._supporting_suggestions(
            finding,
            suggestions=[*spell_suggestions, *rule_suggestions],
            require_exact_span=True,
        )
        if exact_support:
            return self._unique_replacements(
                replacement
                for suggestion in exact_support
                for replacement in suggestion.replacement_options
            )

        overlap_support = self._supporting_suggestions(
            finding,
            suggestions=[*spell_suggestions, *rule_suggestions],
            require_exact_span=False,
        )
        return self._unique_replacements(
            replacement
            for suggestion in overlap_support
            for replacement in suggestion.replacement_options
        )

    def _supporting_suggestions(
        self,
        finding: DetectorFinding,
        *,
        suggestions: Sequence[Suggestion],
        require_exact_span: bool,
    ) -> list[Suggestion]:
        supported: list[Suggestion] = []
        for suggestion in suggestions:
            if not suggestion.replacement_options:
                continue
            if require_exact_span:
                if suggestion.span_start != finding.span_start or suggestion.span_end != finding.span_end:
                    continue
            elif not self._overlaps(finding, suggestion):
                continue

            if suggestion.category != finding.category:
                continue
            supported.append(suggestion)
        return supported

    def _resolve_replacements(self, finding: DetectorFinding, *, text: str) -> list[str]:
        if finding.replacement_options:
            return self._unique_replacements(finding.replacement_options)

        if finding.category == SuggestionCategory.SPELLING:
            return self._spell_backed_replacements(finding.original_text)
        if finding.category == SuggestionCategory.PUNCTUATION:
            return self._punctuation_replacements(finding.original_text, text=text)
        if finding.category == SuggestionCategory.GRAMMAR:
            return self._grammar_replacements(finding.original_text)
        if finding.category == SuggestionCategory.STYLE:
            spacing_replacements = self._spacing_replacements(finding.original_text)
            if spacing_replacements:
                return spacing_replacements
            return []
        return []

    def _spell_backed_replacements(self, token: str) -> list[str]:
        if self.spell_engine is None:
            return []
        if not BANGLA_WORD_PATTERN.fullmatch(token):
            return []
        candidates = self.spell_engine.generate_candidates(token)
        if not candidates:
            return []
        return self._unique_replacements(candidate.word for candidate in candidates[:1])

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
        contextual_support: int = 0,
    ) -> Suggestion:
        resolved_replacements = replacement_options or list(finding.replacement_options)
        resolved_source = SuggestionSource.HYBRID if actionable and finding.source == SuggestionSource.MODEL else finding.source
        resolved_confidence = finding.confidence
        if actionable:
            resolved_confidence = min(
                0.98,
                round(
                    finding.confidence + 0.04 + (min(contextual_support, 3) * 0.02),
                    2,
                ),
            )

        explanation_bn, explanation_en = self._build_explanation(
            finding,
            replacement_options=resolved_replacements,
            actionable=actionable,
            contextual_support=contextual_support,
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
            is_contextual=actionable or finding.source in {SuggestionSource.MODEL, SuggestionSource.HYBRID},
            source_trace=["detector_contextual_support"] if actionable else ["model_runtime"],
        )

    def _build_explanation(
        self,
        finding: DetectorFinding,
        *,
        replacement_options: list[str],
        actionable: bool,
        contextual_support: int,
    ) -> tuple[str, str]:
        if not actionable or not replacement_options:
            return finding.explanation_bn, finding.explanation_en

        primary_replacement = replacement_options[0]
        if contextual_support > 0:
            return (
                f"এই অংশের প্রাসঙ্গিক সংকেত মিলিয়ে এখানে '{primary_replacement}' সবচেয়ে নিরাপদ সংশোধন।",
                f"Context around this detector span supports '{primary_replacement}' as the most grounded correction.",
            )
        if finding.category == SuggestionCategory.SPELLING:
            return (
                f"এখানে '{finding.original_text}' শব্দটির জন্য '{primary_replacement}'-ই সবচেয়ে নির্ভরযোগ্য বানান সংশোধন।",
                f"Detector and spelling candidates both support '{primary_replacement}' as the best correction here.",
            )
        if finding.category == SuggestionCategory.GRAMMAR:
            return (
                f"এখানে '{finding.original_text}' এর বদলে '{primary_replacement}' ব্যবহার করলে বাক্যটি ব্যাকরণগতভাবে ঠিক হয়।",
                f"Replacing '{finding.original_text}' with '{primary_replacement}' makes this phrase more natural.",
            )
        if finding.category == SuggestionCategory.PUNCTUATION:
            return (
                f"এখানে '{finding.original_text}' এর বদলে '{primary_replacement}' যতিচিহ্নটি ব্যবহার করা উচিত।",
                f"Use '{primary_replacement}' instead of '{finding.original_text}' here.",
            )
        return (
            f"এখানে '{finding.original_text}' এর বদলে '{primary_replacement}' ব্যবহার করলে অংশটি বেশি সুনির্দিষ্ট হয়।",
            f"Changing '{finding.original_text}' to '{primary_replacement}' makes this text clearer.",
        )

    def _expanded_personal_dictionary(self, personal_dictionary: list[str] | None) -> set[str]:
        if self.spell_engine is None:
            return {entry.strip() for entry in (personal_dictionary or []) if entry.strip()}
        return self.spell_engine.expand_personal_dictionary(personal_dictionary)

    def _has_covering_suggestion(
        self,
        suggestions: Sequence[Suggestion],
        span_start: int,
        span_end: int,
        replacement: str,
        *,
        minimum_confidence: float = 0.0,
    ) -> bool:
        for suggestion in suggestions:
            if suggestion.span_start != span_start or suggestion.span_end != span_end:
                continue
            if suggestion.confidence < minimum_confidence:
                continue
            if not suggestion.replacement_options:
                return True
            if replacement in suggestion.replacement_options:
                return True
        return False

    def _merge_unique_suggestions(
        self,
        primary: Sequence[Suggestion],
        secondary: Sequence[Suggestion],
    ) -> list[Suggestion]:
        merged: list[Suggestion] = []
        positions: dict[tuple[int, int, str, tuple[str, ...]], int] = {}
        for suggestion in [*primary, *secondary]:
            key = (
                suggestion.span_start,
                suggestion.span_end,
                suggestion.rule_id,
                tuple(suggestion.replacement_options),
            )
            existing_index = positions.get(key)
            if existing_index is not None:
                if self._prefer_duplicate_candidate(merged[existing_index], suggestion):
                    merged[existing_index] = suggestion
                continue
            positions[key] = len(merged)
            merged.append(suggestion)
        return merged

    def _prefer_duplicate_candidate(self, existing: Suggestion, incoming: Suggestion) -> bool:
        if incoming.confidence != existing.confidence:
            return incoming.confidence > existing.confidence
        return incoming.source == SuggestionSource.HYBRID and existing.source != SuggestionSource.HYBRID

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

    def _overlaps(self, finding: DetectorFinding, suggestion: Suggestion) -> bool:
        return finding.span_start < suggestion.span_end and suggestion.span_start < finding.span_end

    def _is_safe_corrector_suggestion(self, suggestion: Suggestion) -> bool:
        if suggestion.source != SuggestionSource.MODEL:
            return True
        if not suggestion.replacement_options:
            return False
        if suggestion.confidence < 0.8:
            return False
        if not suggestion.source_trace:
            return False
        if "anchor_nearest_safe" in suggestion.source_trace and suggestion.confidence < 0.94:
            return False
        if "anchor_nearest_safe" in suggestion.source_trace:
            return False
        if suggestion.occurrence_index is None and not suggestion.anchor_before and not suggestion.anchor_after and "exact_unique_match" not in suggestion.source_trace:
            return False

        primary_replacement = suggestion.replacement_options[0].strip()
        normalized_original = suggestion.original_text.strip()
        if not primary_replacement or primary_replacement == normalized_original:
            return False
        if len((suggestion.explanation_bn or "").split()) <= 3:
            return False

        if suggestion.category == SuggestionCategory.SPELLING:
            return len(suggestion.replacement_options) == 1 and " " not in normalized_original and " " not in primary_replacement

        if suggestion.category == SuggestionCategory.GRAMMAR:
            if len(suggestion.replacement_options) != 1:
                return False
            return len(primary_replacement) <= max(int(len(normalized_original) * 2.5), len(normalized_original) + 8, 24)

        if suggestion.category == SuggestionCategory.PUNCTUATION:
            return len(primary_replacement) <= 12

        return len(primary_replacement) <= max(int(len(normalized_original) * 2.5), len(normalized_original) + 8, 24)


def _severity_rank(severity: SuggestionSeverity) -> int:
    return {
        SuggestionSeverity.LOW: 0,
        SuggestionSeverity.MEDIUM: 1,
        SuggestionSeverity.HIGH: 2,
    }[severity]
