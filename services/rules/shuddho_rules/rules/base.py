from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from shared.constants.bangla import BANGLA_LETTER_PATTERN, PUNCTUATION_CHARS, TOKEN_PATTERN
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id


TOKEN_BOUNDARY_CHARS = r"\u0980-\u09FFA-Za-z0-9"
CLAUSE_BREAK_TOKENS = frozenset(PUNCTUATION_CHARS)
MAX_AGREEMENT_LOOKAHEAD_WORDS = 3


@dataclass(frozen=True)
class TokenSpan:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class RuleDefinition:
    key: str
    description: str
    analyze: Callable[[str], list[Suggestion]]
    noisy: bool = False


def token_spans(text: str) -> list[TokenSpan]:
    return [TokenSpan(text=match.group(0), start=match.start(), end=match.end()) for match in TOKEN_PATTERN.finditer(text)]


def next_non_space_character(text: str, start_index: int) -> str | None:
    for character in text[start_index:]:
        if not character.isspace():
            return character
    return None


def is_bangla_dominant(text: str, *, minimum_ratio: float) -> bool:
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return False
    bangla_letters = sum(1 for character in letters if BANGLA_LETTER_PATTERN.search(character))
    return (bangla_letters / len(letters)) >= minimum_ratio


def join_genitive(noun: str, marker: str) -> str:
    if marker == "র":
        return f"{noun}র"
    if noun.endswith(("া", "ি", "ী", "ু", "ূ", "ে", "ো", "ৌ")):
        return f"{noun}র"
    return f"{noun}এর"


def agreement_suggestions(
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
