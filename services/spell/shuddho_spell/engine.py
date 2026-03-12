from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from shared.constants.bangla import BANGLA_LETTER_PATTERN, BANGLA_WORD_PATTERN, COMMON_BANGLA_CONFUSIONS
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .runtime_lexicon import load_runtime_lexicon


USE_SQLITE_LEXICON_ENV = "SHUDDHO_USE_SQLITE_LEXICON"
USE_SQLITE_CORRECTION_MAP_ENV = "SHUDDHO_USE_SQLITE_CORRECTION_MAP"
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
DIRECT_MAP_EXPLANATION_BN = "এই শব্দটির মানক রূপ অভিধানে ভিন্নভাবে সংরক্ষিত আছে।"
DIRECT_MAP_EXPLANATION_EN = "This form maps to a normalized canonical spelling in the lexicon."
UNKNOWN_WORD_EXPLANATION_BN = "এই শব্দটি অভিধানে নেই। কাছাকাছি কিছু বিকল্প দেখানো হয়েছে।"
UNKNOWN_WORD_EXPLANATION_EN = "This word is not in the local lexicon. Nearby alternatives are suggested."
DIRECT_MAP_CONFIDENCE = 0.99
MIN_GENERIC_CANDIDATE_SCORE = 0.9
MIN_GENERIC_SUGGESTION_CONFIDENCE = 0.92
MAX_GENERIC_REPLACEMENTS = 1


@dataclass(frozen=True)
class SpellCandidate:
    word: str
    score: float


class SpellEngine:
    def __init__(
        self,
        lexicon_path: Path | None = None,
        lexicon_db_path: Path | None = None,
        *,
        use_sqlite_lexicon: bool | None = None,
        use_sqlite_correction_map: bool | None = None,
    ) -> None:
        default_seed_path = Path(__file__).resolve().parents[1] / "data" / "seed_lexicon.txt"
        default_db_path = Path(__file__).resolve().parents[3] / "data" / "shuddho_lexicon.db"
        runtime_lexicon = load_runtime_lexicon(
            seed_path=lexicon_path or default_seed_path,
            database_path=lexicon_db_path or default_db_path,
            use_sqlite_lexicon=_resolve_bool_setting(
                use_sqlite_lexicon,
                USE_SQLITE_LEXICON_ENV,
                default=False,
            ),
            use_sqlite_correction_map=_resolve_bool_setting(
                use_sqlite_correction_map,
                USE_SQLITE_CORRECTION_MAP_ENV,
                default=True,
            ),
        )

        self.lexicon_source = runtime_lexicon.source
        self.lexicon = set(runtime_lexicon.accepted_words)
        self.correction_map = runtime_lexicon.correction_map
        self.frequency_rank = {word: rank for rank, word in enumerate(runtime_lexicon.candidate_words)}
        self._candidate_index, self._length_index = self._build_candidate_indexes(runtime_lexicon.candidate_words)

    def analyze(self, text: str, personal_dictionary: list[str] | None = None) -> list[Suggestion]:
        personal = set(personal_dictionary or [])
        suggestions: list[Suggestion] = []

        for match in BANGLA_WORD_PATTERN.finditer(text):
            token = match.group(0)
            if token in personal or token in self.lexicon or not BANGLA_LETTER_PATTERN.search(token):
                continue
            if len(token) < 3:
                continue

            mapped_candidate = self.correction_map.get(token)
            candidates = self.generate_candidates(token)
            if not candidates:
                continue

            if mapped_candidate:
                top_candidates = [mapped_candidate]
                confidence = DIRECT_MAP_CONFIDENCE
            else:
                top_candidates = [candidate.word for candidate in candidates[:MAX_GENERIC_REPLACEMENTS]]
                confidence = min(max(candidates[0].score, 0.0), 0.96)
                if confidence < MIN_GENERIC_SUGGESTION_CONFIDENCE:
                    continue

            suggestions.append(
                Suggestion(
                    id=stable_id("spell", f"{match.start()}:{match.end()}:{token}:{','.join(top_candidates)}"),
                    category=SuggestionCategory.SPELLING,
                    subtype="unknown_word",
                    span_start=match.start(),
                    span_end=match.end(),
                    original_text=token,
                    replacement_options=top_candidates,
                    confidence=round(confidence, 2),
                    explanation_bn=DIRECT_MAP_EXPLANATION_BN if mapped_candidate else UNKNOWN_WORD_EXPLANATION_BN,
                    explanation_en=DIRECT_MAP_EXPLANATION_EN if mapped_candidate else UNKNOWN_WORD_EXPLANATION_EN,
                    source=SuggestionSource.SPELL,
                    severity=SuggestionSeverity.MEDIUM,
                )
            )

        return suggestions

    def generate_candidates(self, token: str) -> list[SpellCandidate]:
        mapped_candidate = self.correction_map.get(token)
        if mapped_candidate:
            return [SpellCandidate(word=mapped_candidate, score=DIRECT_MAP_CONFIDENCE)]

        ranked: list[SpellCandidate] = []
        seen_candidates: set[str] = set()

        for word in self._iter_candidate_pool(token):
            if word in seen_candidates:
                continue
            seen_candidates.add(word)

            distance = levenshtein_distance(token, word)
            if distance > 1:
                continue
            if not is_safe_generic_candidate(token, word, distance):
                continue
            score = self._score_candidate(token, word, distance)
            if score >= MIN_GENERIC_CANDIDATE_SCORE:
                ranked.append(SpellCandidate(word=word, score=score))

        ranked.sort(key=lambda candidate: candidate.score, reverse=True)
        return ranked

    def _score_candidate(self, token: str, candidate: str, distance: int) -> float:
        rank = self.frequency_rank.get(candidate, 999)
        score = 1.0 - (distance * 0.2) - (abs(len(token) - len(candidate)) * 0.04)
        if token[:1] == candidate[:1]:
            score += 0.08
        if token[-1:] == candidate[-1:]:
            score += 0.06
        score += common_confusion_bonus(token, candidate)
        score += max(0.0, 0.08 - (rank * 0.002))
        return round(score, 4)

    def _build_candidate_indexes(
        self,
        ordered_words: tuple[str, ...],
    ) -> tuple[dict[tuple[str, int], tuple[str, ...]], dict[int, tuple[str, ...]]]:
        indexed_words: dict[tuple[str, int], list[str]] = {}
        length_index: dict[int, list[str]] = {}

        for word in ordered_words:
            indexed_words.setdefault((word[:1], len(word)), []).append(word)
            length_index.setdefault(len(word), []).append(word)

        return (
            {key: tuple(words) for key, words in indexed_words.items()},
            {key: tuple(words) for key, words in length_index.items()},
        )

    def _iter_candidate_pool(self, token: str) -> Iterator[str]:
        token_length = len(token)
        yielded_from_initial_bucket = False

        for first_character in candidate_initial_chars(token):
            for candidate_length in range(max(1, token_length - 1), token_length + 2):
                bucket = self._candidate_index.get((first_character, candidate_length), ())
                if bucket:
                    yielded_from_initial_bucket = True
                yield from bucket

        if yielded_from_initial_bucket:
            return

        for candidate_length in range(max(1, token_length - 1), token_length + 2):
            yield from self._length_index.get(candidate_length, ())


def common_confusion_bonus(source: str, target: str) -> float:
    bonus = 0.0
    for left, right in zip(source, target):
        if left == right:
            bonus += 0.015
            continue
        if right in COMMON_BANGLA_CONFUSIONS.get(left, ()):
            bonus += 0.03
    return bonus


def levenshtein_distance(source: str, target: str) -> int:
    if source == target:
        return 0
    if not source:
        return len(target)
    if not target:
        return len(source)

    previous = list(range(len(target) + 1))
    for row, source_char in enumerate(source, start=1):
        current = [row]
        for column, target_char in enumerate(target, start=1):
            insert_cost = current[column - 1] + 1
            delete_cost = previous[column] + 1
            replace_cost = previous[column - 1] + (0 if source_char == target_char else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def candidate_initial_chars(token: str) -> tuple[str, ...]:
    first_character = token[:1]
    characters = [
        first_character,
        *COMMON_BANGLA_CONFUSIONS.get(first_character, ()),
        *REVERSE_BANGLA_CONFUSIONS.get(first_character, ()),
    ]
    seen_characters: set[str] = set()
    ordered_characters: list[str] = []
    for character in characters:
        if not character or character in seen_characters:
            continue
        seen_characters.add(character)
        ordered_characters.append(character)
    return tuple(ordered_characters)


def is_safe_generic_candidate(token: str, candidate: str, distance: int) -> bool:
    if distance != 1:
        return False
    if len(token) <= 4 and token[-1:] != candidate[-1:]:
        return False
    if _bigram_overlap_score(token, candidate) < 0.5:
        return False
    return True


def _bigram_overlap_score(source: str, target: str) -> float:
    if len(source) < 2 or len(target) < 2:
        return 0.0

    source_bigrams = {source[index : index + 2] for index in range(len(source) - 1)}
    target_bigrams = {target[index : index + 2] for index in range(len(target) - 1)}
    if not source_bigrams or not target_bigrams:
        return 0.0

    overlap = len(source_bigrams & target_bigrams)
    return overlap / max(len(source_bigrams), len(target_bigrams))


def _build_reverse_confusions() -> dict[str, tuple[str, ...]]:
    reverse_confusions: dict[str, list[str]] = {}
    for source_character, target_characters in COMMON_BANGLA_CONFUSIONS.items():
        for target_character in target_characters:
            reverse_confusions.setdefault(target_character, [])
            if source_character not in reverse_confusions[target_character]:
                reverse_confusions[target_character].append(source_character)
    return {key: tuple(values) for key, values in reverse_confusions.items()}


def _resolve_bool_setting(explicit_value: bool | None, env_name: str, *, default: bool) -> bool:
    if explicit_value is not None:
        return explicit_value

    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


REVERSE_BANGLA_CONFUSIONS = _build_reverse_confusions()
