from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from shared.constants.bangla import (
    BANGLA_LETTER_PATTERN,
    BANGLA_WORD_PATTERN,
    COMMON_BANGLA_CONFUSIONS,
    CURATED_VARIANT_CORRECTIONS,
)
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .runtime_lexicon import load_runtime_lexicon


DIRECT_SPELLING_CONFIDENCE = 0.99
DIRECT_VARIANT_CONFIDENCE = 0.9
MIN_GENERIC_CANDIDATE_SCORE = 0.95
MIN_GENERIC_SUGGESTION_CONFIDENCE = 0.96
MIN_GENERIC_SCORE_MARGIN = 0.03
MAX_GENERIC_REPLACEMENTS = 1


@dataclass(frozen=True)
class SpellCandidate:
    word: str
    score: float


class SpellEngine:
    def __init__(
        self,
        runtime_csv_path: Path | None = None,
        *,
        fallback_seed_path: Path | None = None,
    ) -> None:
        default_csv_path = Path(__file__).resolve().parents[3] / "data" / "imports" / "lexicon" / "words_clean.csv"
        default_seed_path = Path(__file__).resolve().parents[1] / "data" / "seed_lexicon.txt"
        runtime_lexicon = load_runtime_lexicon(
            runtime_csv_path or default_csv_path,
            fallback_seed_path=fallback_seed_path or default_seed_path,
        )

        self.lexicon_source = runtime_lexicon.source
        self.lexicon = set(runtime_lexicon.accepted_words)
        self.spelling_error_map = dict(runtime_lexicon.correction_map)
        self.orthography_variant_map = dict(CURATED_VARIANT_CORRECTIONS)
        self.correction_map = {**self.spelling_error_map, **self.orthography_variant_map}
        self.frequency_rank = {word: rank for rank, word in enumerate(runtime_lexicon.candidate_words)}
        self._candidate_index = self._build_candidate_index(runtime_lexicon.candidate_words)
        self._reverse_correction_map = _build_reverse_correction_map(self.correction_map)

    def analyze(self, text: str, personal_dictionary: list[str] | None = None) -> list[Suggestion]:
        personal = self._expand_personal_dictionary(personal_dictionary)
        suggestions: list[Suggestion] = []

        for match in BANGLA_WORD_PATTERN.finditer(text):
            token = match.group(0)
            if self._should_skip_token(token, personal):
                continue

            variant_candidate = self.orthography_variant_map.get(token)
            if variant_candidate:
                if variant_candidate in personal:
                    continue
                suggestions.append(
                    Suggestion(
                        id=stable_id("spell", f"{match.start()}:{match.end()}:{token}:{variant_candidate}"),
                        rule_id="SPELL_002",
                        category=SuggestionCategory.SPELLING,
                        subtype="orthography_variant",
                        span_start=match.start(),
                        span_end=match.end(),
                        original_text=token,
                        replacement_options=[variant_candidate],
                        confidence=DIRECT_VARIANT_CONFIDENCE,
                        explanation_bn=f"'{token}' রূপটি গ্রহণযোগ্য ভিন্নরূপ হলেও এখানে মানক বানান '{variant_candidate}' বেশি প্রচলিত।",
                        explanation_en=f"'{token}' is an acceptable variant, but '{variant_candidate}' is the preferred standard spelling here.",
                        source=SuggestionSource.SPELL,
                        severity=SuggestionSeverity.LOW,
                    )
                )
                continue

            direct_candidate = self.spelling_error_map.get(token)
            if direct_candidate:
                if direct_candidate in personal:
                    continue
                suggestions.append(
                    Suggestion(
                        id=stable_id("spell", f"{match.start()}:{match.end()}:{token}:{direct_candidate}"),
                        rule_id="SPELL_002",
                        category=SuggestionCategory.SPELLING,
                        subtype="spelling_error",
                        span_start=match.start(),
                        span_end=match.end(),
                        original_text=token,
                        replacement_options=[direct_candidate],
                        confidence=DIRECT_SPELLING_CONFIDENCE,
                        explanation_bn=f"এখানে '{token}' এর অভিধানভিত্তিক শুদ্ধ রূপ '{direct_candidate}'।",
                        explanation_en=f"The dictionary-backed spelling for '{token}' here is '{direct_candidate}'.",
                        source=SuggestionSource.SPELL,
                        severity=SuggestionSeverity.MEDIUM,
                    )
                )
                continue

            candidates = self.generate_candidates(token)
            if not candidates or self._is_ambiguous_generic_candidate(candidates):
                continue

            top_candidates = [candidate.word for candidate in candidates[:MAX_GENERIC_REPLACEMENTS]]
            if any(candidate in personal for candidate in top_candidates):
                continue

            primary_candidate = top_candidates[0]
            confidence = min(max(candidates[0].score, 0.0), 0.97)
            if confidence < MIN_GENERIC_SUGGESTION_CONFIDENCE:
                continue

            suggestions.append(
                Suggestion(
                    id=stable_id("spell", f"{match.start()}:{match.end()}:{token}:{','.join(top_candidates)}"),
                    rule_id="SPELL_003",
                    category=SuggestionCategory.SPELLING,
                    subtype="spelling_error",
                    span_start=match.start(),
                    span_end=match.end(),
                    original_text=token,
                    replacement_options=top_candidates,
                    confidence=round(confidence, 2),
                    explanation_bn=f"'{token}' শব্দটির সবচেয়ে কাছের নিরাপদ সংশোধন '{primary_candidate}'।",
                    explanation_en=f"The closest safe correction for '{token}' is '{primary_candidate}'.",
                    source=SuggestionSource.SPELL,
                    severity=SuggestionSeverity.LOW,
                )
            )

        return suggestions

    def _should_skip_token(self, token: str, personal: set[str]) -> bool:
        if token in personal:
            return True
        if not BANGLA_LETTER_PATTERN.search(token):
            return True
        if len(token) < 3:
            return True
        return token in self.lexicon and token not in self.correction_map

    def _expand_personal_dictionary(self, personal_dictionary: list[str] | None) -> set[str]:
        personal_words: set[str] = set()
        for entry in personal_dictionary or []:
            for token in BANGLA_WORD_PATTERN.findall(entry.strip()):
                if token:
                    personal_words.add(token)

        expanded = set(personal_words)
        for token in tuple(personal_words):
            mapped = self.correction_map.get(token)
            if mapped:
                expanded.add(mapped)
            expanded.update(self._reverse_correction_map.get(token, ()))

        return expanded

    def _is_ambiguous_generic_candidate(self, candidates: list[SpellCandidate]) -> bool:
        return len(candidates) > 1 and (candidates[0].score - candidates[1].score) < MIN_GENERIC_SCORE_MARGIN

    def generate_candidates(self, token: str) -> list[SpellCandidate]:
        mapped_candidate = self.correction_map.get(token)
        if mapped_candidate:
            return [SpellCandidate(word=mapped_candidate, score=DIRECT_SPELLING_CONFIDENCE)]

        ranked: list[SpellCandidate] = []
        seen_candidates: set[str] = set()

        for candidate in self._iter_candidate_pool(token):
            if candidate in seen_candidates:
                continue
            seen_candidates.add(candidate)

            distance = levenshtein_distance(token, candidate)
            if distance > 2:
                continue
            if not is_safe_generic_candidate(token, candidate, distance):
                continue

            score = self._score_candidate(token, candidate, distance)
            if score >= MIN_GENERIC_CANDIDATE_SCORE:
                ranked.append(SpellCandidate(word=candidate, score=score))

        ranked.sort(key=lambda candidate: candidate.score, reverse=True)
        return ranked

    def _score_candidate(self, token: str, candidate: str, distance: int) -> float:
        rank = self.frequency_rank.get(candidate, 999)
        score = 1.0 - (distance * 0.28) - (abs(len(token) - len(candidate)) * 0.08)
        if token[:1] == candidate[:1]:
            score += 0.1
        if token[-1:] == candidate[-1:]:
            score += 0.08
        score += common_confusion_bonus(token, candidate)
        score += _bigram_overlap_score(token, candidate) * 0.1
        score += max(0.0, 0.02 - (rank * 0.0001))
        return round(score, 4)

    def _build_candidate_index(self, candidate_words: tuple[str, ...]) -> dict[tuple[str, int], tuple[str, ...]]:
        indexed_words: dict[tuple[str, int], list[str]] = {}
        for word in candidate_words:
            indexed_words.setdefault((word[:1], len(word)), []).append(word)
        return {key: tuple(words) for key, words in indexed_words.items()}

    def _iter_candidate_pool(self, token: str) -> Iterator[str]:
        token_length = len(token)
        for first_character in candidate_initial_chars(token):
            for candidate_length in range(max(1, token_length - 2), token_length + 3):
                yield from self._candidate_index.get((first_character, candidate_length), ())


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
    if distance <= 0:
        return False
    if token[-1:] != candidate[-1:]:
        return False

    overlap = _bigram_overlap_score(token, candidate)
    if distance == 1:
        return overlap >= 0.5
    if min(len(token), len(candidate)) < 6:
        return False
    if token[-1:] != candidate[-1:]:
        return False
    return overlap >= 0.75


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


def _build_reverse_correction_map(correction_map: dict[str, str]) -> dict[str, tuple[str, ...]]:
    reverse_map: dict[str, list[str]] = {}
    for source, target in correction_map.items():
        reverse_map.setdefault(target, [])
        if source not in reverse_map[target]:
            reverse_map[target].append(source)
    return {key: tuple(values) for key, values in reverse_map.items()}


REVERSE_BANGLA_CONFUSIONS = _build_reverse_confusions()
