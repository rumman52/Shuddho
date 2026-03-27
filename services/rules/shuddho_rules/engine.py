from __future__ import annotations

import re
from dataclasses import dataclass

from shared.constants.bangla import (
    BANGLA_LETTER_PATTERN,
    BANGLA_TO_LATIN_DIGITS,
    BANGLA_WORD_PATTERN,
    CASUAL_PRONOUNS,
    CLOSING_DELIMITERS,
    CODE_MIX_REPLACEMENTS,
    COMMON_POSTPOSITIONS,
    COMMON_UNITS,
    COORDINATORS,
    FIRST_PERSON_PRONOUNS,
    FIRST_PERSON_VERB_MAP,
    GENITIVE_MARKERS,
    LATIN_TO_BANGLA_DIGITS,
    OPENING_DELIMITERS,
    POLITE_IMPERATIVE_MAP,
    POLITE_PRONOUNS,
    POSTPOSITION_EXCEPTIONS,
    PUNCTUATION_CHARS,
    REDUPLICATION_WHITELIST,
    SAFE_EXACT_TYPOS,
    TOKEN_PATTERN,
)
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id


TOKEN_BOUNDARY_CHARS = r"\u0980-\u09FFA-Za-z0-9"
CLAUSE_BREAK_TOKENS = frozenset(PUNCTUATION_CHARS)
CASUAL_IMPERATIVE_MAP = {replacement: original for original, replacement in POLITE_IMPERATIVE_MAP.items()}
MAX_AGREEMENT_LOOKAHEAD_WORDS = 3


@dataclass(frozen=True)
class TokenSpan:
    text: str
    start: int
    end: int


class RuleEngine:
    repeated_word_pattern = re.compile(
        rf"(?<![{TOKEN_BOUNDARY_CHARS}])(?P<word>[\u0980-\u09FFA-Za-z]+)(?P<space>\s+)(?P=word)(?![{TOKEN_BOUNDARY_CHARS}])"
    )
    duplicate_punctuation_pattern = re.compile(rf"([{re.escape(PUNCTUATION_CHARS)}])\1+")
    extra_whitespace_pattern = re.compile(rf"(?<=[{TOKEN_BOUNDARY_CHARS}])[^\S\r\n]{{2,}}(?=[{TOKEN_BOUNDARY_CHARS}])")
    whitespace_before_punctuation_pattern = re.compile(rf"\s+([{re.escape(PUNCTUATION_CHARS)}])")
    bangla_full_stop_pattern = re.compile(r"(?<![.\d])\.(?!\.)(?=\s|$)")
    space_after_terminator_pattern = re.compile(r"([।!?])([^\s\"'”’)\]}])")
    duplicate_negation_pattern = re.compile(r"(?<![\u0980-\u09FFA-Za-z])না(?P<space>\s+)না(?![\u0980-\u09FFA-Za-z])")
    number_unit_spacing_pattern = re.compile(r"([0-9০-৯]+)(কেজি|কিমি|মিটার|ঘণ্টা|টাকা|জন)")
    latin_word_pattern = re.compile(r"[A-Za-z]{2,}")

    def analyze(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        suggestions.extend(self._repeated_word_suggestions(text))
        suggestions.extend(self._duplicate_punctuation_suggestions(text))
        suggestions.extend(self._extra_whitespace_suggestions(text))
        suggestions.extend(self._whitespace_before_punctuation_suggestions(text))
        suggestions.extend(self._bangla_full_stop_suggestions(text))
        suggestions.extend(self._space_after_terminator_suggestions(text))
        suggestions.extend(self._unbalanced_delimiter_suggestions(text))
        suggestions.extend(self._duplicate_negation_suggestions(text))
        suggestions.extend(self._coordinator_repetition_suggestions(text))
        suggestions.extend(self._pronoun_verb_mismatch_suggestions(text))
        suggestions.extend(self._first_person_verb_mismatch_suggestions(text))
        suggestions.extend(self._mixed_address_register_suggestions(text))
        suggestions.extend(self._fused_postposition_suggestions(text))
        suggestions.extend(self._genitive_spacing_suggestions(text))
        suggestions.extend(self._mixed_digit_style_suggestions(text))
        suggestions.extend(self._number_unit_spacing_suggestions(text))
        suggestions.extend(self._code_mixed_latin_suggestions(text))
        suggestions.extend(self._exact_typo_suggestions(text))
        return suggestions

    def _repeated_word_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.repeated_word_pattern.finditer(text):
            word = match.group("word")
            normalized_bigram = f"{word} {word}"
            if normalized_bigram in REDUPLICATION_WHITELIST or len(word) < 2:
                continue

            span_start = match.start()
            span_end = match.end()
            confidence = 0.95 if word in {"আমি", "সে", "এই", "ওই", "যে", "না"} else 0.7
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"repeat:{span_start}:{span_end}:{word}"),
                    rule_id="REP_001",
                    category=SuggestionCategory.GRAMMAR,
                    subtype="repeated_word",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=text[span_start:span_end],
                    replacement_options=[word],
                    confidence=confidence,
                    explanation_bn=f"একই শব্দ '{word}' পরপর দুইবার এসেছে।",
                    explanation_en=f"The word '{word}' appears twice in a row.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM,
                )
            )
        return suggestions

    def _duplicate_punctuation_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.duplicate_punctuation_pattern.finditer(text):
            characters = match.group(0)
            replacement = characters[0]
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"punctuation:{match.start()}:{match.end()}:{characters}"),
                    rule_id="PUNC_001",
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="duplicate_punctuation",
                    span_start=match.start(),
                    span_end=match.end(),
                    original_text=characters,
                    replacement_options=[replacement],
                    confidence=0.99,
                    explanation_bn=f"এখানে '{characters}' এর বদলে '{replacement}' ব্যবহার করুন।",
                    explanation_en=f"Replace '{characters}' with '{replacement}' here.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _extra_whitespace_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.extra_whitespace_pattern.finditer(text):
            span_start = match.start()
            span_end = match.end()
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"extra-space:{span_start}:{span_end}"),
                    rule_id="SPACE_001",
                    category=SuggestionCategory.GRAMMAR,
                    subtype="extra_whitespace",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=text[span_start:span_end],
                    replacement_options=[" "],
                    confidence=0.99,
                    explanation_bn="দুইটি শব্দের মাঝে অতিরিক্ত ফাঁকা আছে।",
                    explanation_en="There is extra whitespace between these words.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _whitespace_before_punctuation_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.whitespace_before_punctuation_pattern.finditer(text):
            punctuation = match.group(1)
            span_start = match.start()
            span_end = match.end()
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"spacing-before:{span_start}:{span_end}:{punctuation}"),
                    rule_id="PUNC_002",
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="space_before_punctuation",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=text[span_start:span_end],
                    replacement_options=[punctuation],
                    confidence=0.98,
                    explanation_bn=f"যতিচিহ্ন '{punctuation}' এর আগে অপ্রয়োজনীয় ফাঁকা আছে।",
                    explanation_en=f"There is unnecessary whitespace before '{punctuation}'.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _bangla_full_stop_suggestions(self, text: str) -> list[Suggestion]:
        if not self._is_bangla_dominant(text, minimum_ratio=0.6):
            return []

        suggestions: list[Suggestion] = []
        for match in self.bangla_full_stop_pattern.finditer(text):
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"bangla-full-stop:{match.start()}:{match.end()}"),
                    rule_id="PUNC_003",
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="bangla_full_stop",
                    span_start=match.start(),
                    span_end=match.end(),
                    original_text=match.group(0),
                    replacement_options=["।"],
                    confidence=0.9,
                    explanation_bn="বাংলা বাক্যের শেষে '.' এর বদলে '।' ব্যবহার করুন।",
                    explanation_en="Use '।' instead of '.' at the end of a Bangla sentence.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _space_after_terminator_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.space_after_terminator_pattern.finditer(text):
            punctuation = match.group(1)
            next_character = match.group(2)
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"spacing-after:{match.start()}:{match.end()}:{punctuation}"),
                    rule_id="PUNC_004",
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="space_after_punctuation",
                    span_start=match.start(),
                    span_end=match.end(),
                    original_text=match.group(0),
                    replacement_options=[f"{punctuation} {next_character}"],
                    confidence=0.85,
                    explanation_bn=f"যতিচিহ্ন '{punctuation}' এর পরে সাধারণত একটি ফাঁকা থাকে।",
                    explanation_en=f"'{punctuation}' is usually followed by a space here.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _unbalanced_delimiter_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        stack: list[tuple[str, int]] = []

        for index, character in enumerate(text):
            if character in OPENING_DELIMITERS:
                stack.append((character, index))
                continue

            if character not in CLOSING_DELIMITERS:
                continue

            if stack and stack[-1][0] == CLOSING_DELIMITERS[character]:
                stack.pop()
                continue

            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"unbalanced-closing:{index}:{character}"),
                    rule_id="PUNC_005",
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="unbalanced_delimiter",
                    span_start=index,
                    span_end=index + 1,
                    original_text=character,
                    replacement_options=[],
                    confidence=0.7,
                    explanation_bn="বন্ধনী বা উদ্ধৃতি চিহ্নের জোড়া অসম্পূর্ণ।",
                    explanation_en="This bracket or quote is unbalanced.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM,
                )
            )

        for character, index in stack:
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"unbalanced-opening:{index}:{character}"),
                    rule_id="PUNC_005",
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="unbalanced_delimiter",
                    span_start=index,
                    span_end=index + 1,
                    original_text=character,
                    replacement_options=[],
                    confidence=0.7,
                    explanation_bn="বন্ধনী বা উদ্ধৃতি চিহ্নের জোড়া অসম্পূর্ণ।",
                    explanation_en="This bracket or quote is unbalanced.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM,
                )
            )

        return suggestions

    def _duplicate_negation_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.duplicate_negation_pattern.finditer(text):
            next_non_space = self._next_non_space_character(text, match.end())
            if next_non_space == "!":
                continue

            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"duplicate-negation:{match.start()}:{match.end()}"),
                    rule_id="GRAM_001",
                    category=SuggestionCategory.GRAMMAR,
                    subtype="duplicate_negation",
                    span_start=match.start(),
                    span_end=match.end(),
                    original_text=match.group(0),
                    replacement_options=["না"],
                    confidence=0.7,
                    explanation_bn="এখানে 'না' শব্দটি অপ্রয়োজনীয়ভাবে দুইবার এসেছে।",
                    explanation_en="The word 'না' appears twice here unnecessarily.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM,
                )
            )
        return suggestions

    def _coordinator_repetition_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        tokens = self._token_spans(text)

        for index in range(len(tokens) - 1):
            left = tokens[index]
            right = tokens[index + 1]
            if left.text != right.text or left.text not in COORDINATORS:
                continue

            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"coordinator-repeat:{left.start}:{right.end}:{left.text}"),
                    rule_id="GRAM_002",
                    category=SuggestionCategory.GRAMMAR,
                    subtype="repeated_coordinator",
                    span_start=left.start,
                    span_end=right.end,
                    original_text=text[left.start:right.end],
                    replacement_options=[left.text],
                    confidence=0.9,
                    explanation_bn=f"সংযোজক '{left.text}' পরপর দুইবার এসেছে।",
                    explanation_en=f"The coordinator '{left.text}' appears twice in a row.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM,
                )
            )

        return suggestions

    def _pronoun_verb_mismatch_suggestions(self, text: str) -> list[Suggestion]:
        tokens = self._token_spans(text)
        suggestions: list[Suggestion] = []

        for index, token in enumerate(tokens):
            if token.text in POLITE_PRONOUNS:
                suggestions.extend(
                    self._agreement_suggestions(
                        tokens=tokens,
                        subject_token=token,
                        subject_index=index,
                        replacement_map=POLITE_IMPERATIVE_MAP,
                        rule_id="GRAM_003",
                        subtype="honorific_pronoun_verb_mismatch",
                        confidence=0.85,
                    )
                )
                continue

            if token.text in CASUAL_PRONOUNS:
                suggestions.extend(
                    self._agreement_suggestions(
                        tokens=tokens,
                        subject_token=token,
                        subject_index=index,
                        replacement_map=CASUAL_IMPERATIVE_MAP,
                        rule_id="GRAM_004",
                        subtype="casual_pronoun_verb_mismatch",
                        confidence=0.85,
                    )
                )

        return suggestions

    def _first_person_verb_mismatch_suggestions(self, text: str) -> list[Suggestion]:
        tokens = self._token_spans(text)
        suggestions: list[Suggestion] = []

        for index, token in enumerate(tokens):
            if token.text not in FIRST_PERSON_PRONOUNS:
                continue

            suggestions.extend(
                self._agreement_suggestions(
                    tokens=tokens,
                    subject_token=token,
                    subject_index=index,
                    replacement_map=FIRST_PERSON_VERB_MAP,
                    rule_id="GRAM_005",
                    subtype="first_person_verb_mismatch",
                    confidence=0.65,
                )
            )

        return suggestions

    def _mixed_address_register_suggestions(self, text: str) -> list[Suggestion]:
        tokens = self._token_spans(text)
        seen_polite: TokenSpan | None = None
        seen_casual: TokenSpan | None = None

        for token in tokens:
            if token.text in POLITE_PRONOUNS and seen_polite is None:
                seen_polite = token
            if token.text in CASUAL_PRONOUNS and seen_casual is None:
                seen_casual = token

        if not seen_polite or not seen_casual:
            return []

        later = seen_casual if seen_casual.start > seen_polite.start else seen_polite
        return [
            Suggestion(
                id=stable_id("rule", f"mixed-address:{seen_polite.start}:{seen_casual.end}"),
                rule_id="GRAM_006",
                category=SuggestionCategory.GRAMMAR,
                subtype="mixed_address_register",
                span_start=later.start,
                span_end=later.end,
                original_text=later.text,
                replacement_options=[],
                confidence=0.7,
                explanation_bn="একই বাক্যে ভিন্ন সম্বোধন-স্তর মিশেছে; সম্বোধন একরকম রাখুন।",
                explanation_en="This sentence mixes different address levels; keep the register consistent.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.MEDIUM,
            )
        ]

    def _fused_postposition_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        tokens = self._token_spans(text)

        for token in tokens:
            if not BANGLA_WORD_PATTERN.fullmatch(token.text):
                continue
            if token.text in POSTPOSITION_EXCEPTIONS:
                continue

            for suffix in COMMON_POSTPOSITIONS:
                if not token.text.endswith(suffix) or len(token.text) <= len(suffix) + 1:
                    continue

                stem = token.text[: -len(suffix)]
                if not BANGLA_WORD_PATTERN.fullmatch(stem) or stem.endswith("্"):
                    continue

                confidence = 0.9 if len(stem) >= 2 else 0.7
                suggestions.append(
                    Suggestion(
                        id=stable_id("rule", f"postposition-split:{token.start}:{token.end}:{suffix}"),
                        rule_id="GRAM_007",
                        category=SuggestionCategory.GRAMMAR,
                        subtype="fused_postposition",
                        span_start=token.start,
                        span_end=token.end,
                        original_text=token.text,
                        replacement_options=[f"{stem} {suffix}"],
                        confidence=confidence,
                        explanation_bn=f"'{suffix}' এর আগে সাধারণত একটি ফাঁকা থাকে।",
                        explanation_en=f"'{suffix}' is usually written with a preceding space.",
                        source=SuggestionSource.RULE,
                        severity=SuggestionSeverity.MEDIUM,
                    )
                )
                break

        return suggestions

    def _genitive_spacing_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        tokens = self._token_spans(text)

        for index in range(len(tokens) - 1):
            noun = tokens[index]
            marker = tokens[index + 1]
            if marker.text not in GENITIVE_MARKERS:
                continue
            if not BANGLA_WORD_PATTERN.fullmatch(noun.text):
                continue

            replacement = self._join_genitive(noun.text, marker.text)
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"genitive-join:{noun.start}:{marker.end}:{marker.text}"),
                    rule_id="GRAM_008",
                    category=SuggestionCategory.GRAMMAR,
                    subtype="genitive_spacing",
                    span_start=noun.start,
                    span_end=marker.end,
                    original_text=text[noun.start:marker.end],
                    replacement_options=[replacement],
                    confidence=0.62,
                    explanation_bn="সম্বন্ধসূচক রূপটি এখানে আলাদা না লিখে যুক্তভাবে লেখা ভালো।",
                    explanation_en="The genitive form is usually written joined here.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )

        return suggestions

    def _mixed_digit_style_suggestions(self, text: str) -> list[Suggestion]:
        if not re.search(r"[0-9]", text) or not re.search(r"[০-৯]", text):
            return []

        bangla_digits = text.translate(LATIN_TO_BANGLA_DIGITS)
        latin_digits = text.translate(BANGLA_TO_LATIN_DIGITS)
        replacements = []
        if bangla_digits != text:
            replacements.append(bangla_digits)
        if latin_digits != text:
            replacements.append(latin_digits)

        return [
            Suggestion(
                id=stable_id("rule", f"mixed-digits:{len(text)}:{text}"),
                rule_id="STYLE_001",
                category=SuggestionCategory.STYLE,
                subtype="mixed_digit_style",
                span_start=0,
                span_end=len(text),
                original_text=text,
                replacement_options=replacements,
                confidence=0.7,
                explanation_bn="একই লেখায় বাংলা ও ইংরেজি অঙ্ক মিশেছে; একরকম অঙ্ক ব্যবহার করুন।",
                explanation_en="This text mixes Bengali and Latin digits; use one digit style consistently.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
            )
        ]

    def _number_unit_spacing_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.number_unit_spacing_pattern.finditer(text):
            number = match.group(1)
            unit = match.group(2)
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"unit-spacing:{match.start()}:{match.end()}:{unit}"),
                    rule_id="STYLE_002",
                    category=SuggestionCategory.STYLE,
                    subtype="number_unit_spacing",
                    span_start=match.start(),
                    span_end=match.end(),
                    original_text=match.group(0),
                    replacement_options=[f"{number} {unit}"],
                    confidence=0.85,
                    explanation_bn=f"সংখ্যার পরে একক '{unit}' হলে সাধারণত একটি ফাঁকা থাকে।",
                    explanation_en=f"A space is usually written before the unit '{unit}'.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _code_mixed_latin_suggestions(self, text: str) -> list[Suggestion]:
        if not self._is_bangla_dominant(text, minimum_ratio=0.7):
            return []

        suggestions: list[Suggestion] = []
        for match in self.latin_word_pattern.finditer(text):
            token = match.group(0)
            replacement = CODE_MIX_REPLACEMENTS.get(token.lower())
            replacement_options = [replacement] if replacement else []
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"code-mix:{match.start()}:{match.end()}:{token.lower()}"),
                    rule_id="STYLE_003",
                    category=SuggestionCategory.STYLE,
                    subtype="code_mixed_latin",
                    span_start=match.start(),
                    span_end=match.end(),
                    original_text=token,
                    replacement_options=replacement_options,
                    confidence=0.5,
                    explanation_bn="বাংলা বাক্যে ইংরেজি শব্দ মিশেছে।",
                    explanation_en="This Bangla sentence contains a mixed-in Latin word.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _exact_typo_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for typo, replacement in SAFE_EXACT_TYPOS.items():
            typo_pattern = re.compile(rf"(?<![{TOKEN_BOUNDARY_CHARS}]){re.escape(typo)}(?![{TOKEN_BOUNDARY_CHARS}])")
            for match in typo_pattern.finditer(text):
                original_text = match.group(0)
                suggestions.append(
                    Suggestion(
                        id=stable_id("rule", f"typo:{match.start()}:{match.end()}:{typo}->{replacement}"),
                        rule_id="SPELL_001",
                        category=SuggestionCategory.SPELLING,
                        subtype="spelling_error",
                        span_start=match.start(),
                        span_end=match.end(),
                        original_text=original_text,
                        replacement_options=[replacement],
                        confidence=0.98,
                        explanation_bn=f"এখানে '{original_text}' এর বদলে '{replacement}' লেখা উচিত।",
                        explanation_en=f"Replace '{original_text}' with '{replacement}' here.",
                        source=SuggestionSource.RULE,
                        severity=SuggestionSeverity.MEDIUM,
                    )
                )
        return suggestions

    def _agreement_suggestions(
        self,
        *,
        tokens: list[TokenSpan],
        subject_token: TokenSpan,
        subject_index: int,
        replacement_map: dict[str, str],
        rule_id: str,
        subtype: str,
        confidence: float,
    ) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        looked_ahead_words = 0

        for candidate in tokens[subject_index + 1 :]:
            if candidate.text in CLAUSE_BREAK_TOKENS:
                break
            if not BANGLA_LETTER_PATTERN.search(candidate.text):
                continue

            looked_ahead_words += 1
            if looked_ahead_words > MAX_AGREEMENT_LOOKAHEAD_WORDS:
                break

            replacement = replacement_map.get(candidate.text)
            if not replacement:
                continue

            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"agree:{subtype}:{candidate.start}:{candidate.end}:{candidate.text}->{replacement}"),
                    rule_id=rule_id,
                    category=SuggestionCategory.GRAMMAR,
                    subtype=subtype,
                    span_start=candidate.start,
                    span_end=candidate.end,
                    original_text=candidate.text,
                    replacement_options=[replacement],
                    confidence=confidence,
                    explanation_bn=f"'{subject_token.text}' এর সাথে '{replacement}' ক্রিয়ারূপটি মানানসই।",
                    explanation_en=f"'{subject_token.text}' usually takes the verb form '{replacement}' here.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM,
                )
            )
            break

        return suggestions

    def _token_spans(self, text: str) -> list[TokenSpan]:
        return [TokenSpan(text=match.group(0), start=match.start(), end=match.end()) for match in TOKEN_PATTERN.finditer(text)]

    def _next_non_space_character(self, text: str, start_index: int) -> str | None:
        for character in text[start_index:]:
            if not character.isspace():
                return character
        return None

    def _is_bangla_dominant(self, text: str, *, minimum_ratio: float) -> bool:
        letters = [character for character in text if character.isalpha()]
        if not letters:
            return False
        bangla_letters = sum(1 for character in letters if BANGLA_LETTER_PATTERN.search(character))
        return (bangla_letters / len(letters)) >= minimum_ratio

    def _join_genitive(self, noun: str, marker: str) -> str:
        if marker == "র":
            return f"{noun}র"
        if noun.endswith(("া", "ি", "ী", "ু", "ূ", "ে", "ো", "ৌ")):
            return f"{noun}র"
        return f"{noun}এর"
