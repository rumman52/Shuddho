from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from shared.constants.bangla import (
    BANGLA_LETTER_PATTERN,
    BANGLA_WORD_PATTERN,
    COMMON_BANGLA_CONFUSIONS,
    CURATED_VARIANT_CORRECTIONS,
    SAFE_EXACT_TYPOS,
)
from shared.schemas.python_models import (
    AnalyzeMode,
    Suggestion,
    SuggestionCategory,
    SuggestionKind,
    SuggestionSeverity,
    SuggestionSource,
)
from shared.utils.text import stable_id

from .repository import LexiconRepository, RuntimeLexiconSnapshot


DIRECT_SPELLING_CONFIDENCE = 0.99
DIRECT_VARIANT_CONFIDENCE = 0.84
MIN_GENERIC_CANDIDATE_SCORE = 0.96
MIN_GENERIC_SUGGESTION_CONFIDENCE = 0.95
MIN_GENERIC_SCORE_MARGIN = 0.04
MAX_GENERIC_REPLACEMENTS = 1
LATIN_OR_DIGIT_PATTERN = re.compile(r"[A-Za-z0-9]")


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
        default_csv_path = Path(__file__).resolve().parents[3] / "data" / "runtime" / "lexicon" / "runtime_words.csv"
        default_metadata_path = default_csv_path.with_name("runtime_metadata.json")
        default_seed_path = Path(__file__).resolve().parents[1] / "data" / "seed_lexicon.txt"
        default_database_path = Path(__file__).resolve().parents[3] / "data" / "shuddho_lexicon.db"
        resolved_runtime_path = runtime_csv_path or default_csv_path
        self.repository = LexiconRepository(
            resolved_runtime_path,
            fallback_seed_path=fallback_seed_path or default_seed_path,
            import_database_path=default_database_path,
            runtime_metadata_path=(
                resolved_runtime_path.with_name("runtime_metadata.json")
                if resolved_runtime_path.name == "runtime_words.csv"
                else default_metadata_path if resolved_runtime_path == default_csv_path else None
            ),
        )
        self._apply_snapshot(self.repository.snapshot)

    def reload_runtime_lexicon(self) -> None:
        self._apply_snapshot(self.repository.reload())

    def _apply_snapshot(self, runtime_lexicon: RuntimeLexiconSnapshot) -> None:
        self.lexicon_source = runtime_lexicon.runtime_source
        self.lexicon_version = runtime_lexicon.version
        self.lexicon_checksum = runtime_lexicon.checksum
        self.lexicon_runtime_path = runtime_lexicon.runtime_path
        self.lexicon_runtime_exists = runtime_lexicon.runtime_exists
        self.lexicon_import_database_path = runtime_lexicon.import_database_path
        self.lexicon_import_database_exists = runtime_lexicon.import_database_exists
        self.lexicon_loaded_at = runtime_lexicon.loaded_at
        self.lexicon_row_counts = {
            "accepted_words": runtime_lexicon.accepted_word_count,
            "candidate_words": runtime_lexicon.candidate_word_count,
            "correction_map": runtime_lexicon.correction_map_count,
        }
        self.lexicon = set(runtime_lexicon.accepted_words)
        self.protected_words = set(runtime_lexicon.protected_words)
        self.curated_spelling_map = {
            source: target
            for source, target in SAFE_EXACT_TYPOS.items()
            if " " not in source and " " not in target
        }
        self.runtime_variant_map = dict(runtime_lexicon.variant_map)
        self.spelling_error_map = {
            **runtime_lexicon.correction_map,
            **self.curated_spelling_map,
        }
        self.orthography_variant_map = {
            **self.runtime_variant_map,
            **CURATED_VARIANT_CORRECTIONS,
        }
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
                        explanation_bn=f"'{token}' রূপটি গ্রহণযোগ্য, তবে মানক রূপ '{variant_candidate}' এখানে বেশি উপযুক্ত হতে পারে।",
                        explanation_en=f"'{token}' is acceptable, but '{variant_candidate}' is the preferred standard form here.",
                        source=SuggestionSource.SPELL,
                        severity=SuggestionSeverity.LOW,
                        suggestion_kind=SuggestionKind.ORTHOGRAPHY_VARIANT,
                        optional_mode_visibility=[AnalyzeMode.STRICT, AnalyzeMode.FORMAL],
                        is_variant_only=True,
                        source_trace=["spell_engine", "orthography_variant"],
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
                        suggestion_kind=SuggestionKind.TRUE_SPELLING_ERROR,
                        source_trace=["spell_engine", "exact_runtime_typo"],
                    )
                )
                continue

            candidates = self.generate_candidates(token)
            if not candidates:
                continue
            if self._looks_like_named_entity_or_user_word(token, candidates):
                continue
            if self._is_ambiguous_generic_candidate(candidates):
                continue
            if not self._is_high_precision_generic_candidate(token, candidates):
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
                    explanation_bn=f"'{token}' শব্দটির নির্ভরযোগ্য উচ্চ-নির্ভুল সংশোধন '{primary_candidate}'।",
                    explanation_en=f"The only high-precision correction for '{token}' here is '{primary_candidate}'.",
                    source=SuggestionSource.SPELL,
                    severity=SuggestionSeverity.LOW,
                    suggestion_kind=SuggestionKind.TRUE_SPELLING_ERROR,
                    source_trace=["spell_engine", "generic_high_margin"],
                )
            )

        return suggestions

    def _should_skip_token(self, token: str, personal: set[str]) -> bool:
        if token in personal:
            return True
        if token in self.protected_words:
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

    def expand_personal_dictionary(self, personal_dictionary: list[str] | None) -> set[str]:
        return self._expand_personal_dictionary(personal_dictionary)

    def looks_code_mixed_token(self, token: str) -> bool:
        return bool(BANGLA_LETTER_PATTERN.search(token) and LATIN_OR_DIGIT_PATTERN.search(token))

    def is_probable_named_entity_or_user_word(
        self,
        token: str,
        *,
        personal_dictionary: list[str] | None = None,
    ) -> bool:
        personal = self._expand_personal_dictionary(personal_dictionary)
        if token in personal:
            return True
        if token in self.protected_words:
            return True
        if self.looks_code_mixed_token(token):
            return True
        if token in self.correction_map or token in self.lexicon:
            return False
        candidates = self.generate_candidates(token)
        return self._looks_like_named_entity_or_user_word(token, candidates)

    def is_safe_spelling_replacement(
        self,
        token: str,
        replacement: str,
        *,
        personal_dictionary: list[str] | None = None,
    ) -> bool:
        personal = self._expand_personal_dictionary(personal_dictionary)
        if token in personal or replacement in personal:
            return False
        if self.looks_code_mixed_token(token):
            return False
        if self.is_probable_named_entity_or_user_word(token, personal_dictionary=personal_dictionary):
            return False

        direct_candidate = self.spelling_error_map.get(token)
        if direct_candidate == replacement:
            return True

        candidates = self.generate_candidates(token)
        if not candidates:
            return False
        if self._is_ambiguous_generic_candidate(candidates):
            return False
        if not self._is_high_precision_generic_candidate(token, candidates):
            return False
        return candidates[0].word == replacement

    def is_safe_orthography_variant(
        self,
        token: str,
        replacement: str,
        *,
        personal_dictionary: list[str] | None = None,
    ) -> bool:
        personal = self._expand_personal_dictionary(personal_dictionary)
        if token in personal or replacement in personal:
            return False
        if self.looks_code_mixed_token(token):
            return False
        return self.orthography_variant_map.get(token) == replacement

    def _looks_like_named_entity_or_user_word(self, token: str, candidates: list[SpellCandidate]) -> bool:
        if token in self.correction_map:
            return False
        if len(token) >= 6 and not candidates:
            return True
        if not candidates:
            return False
        top_candidate = candidates[0]
        if len(token) >= 6 and top_candidate.score < 0.97:
            return True
        if len(candidates) > 1 and len(token) >= 6 and (top_candidate.score - candidates[1].score) < 0.05:
            return True
        return False

    def _is_ambiguous_generic_candidate(self, candidates: list[SpellCandidate]) -> bool:
        return len(candidates) > 1 and (candidates[0].score - candidates[1].score) < MIN_GENERIC_SCORE_MARGIN

    def _is_high_precision_generic_candidate(self, token: str, candidates: list[SpellCandidate]) -> bool:
        top_candidate = candidates[0]
        if top_candidate.score < MIN_GENERIC_CANDIDATE_SCORE:
            return False
        distance = levenshtein_distance(token, top_candidate.word)
        if distance != 1:
            return False
        if len(token) >= 5 and _bigram_overlap_score(token, top_candidate.word) < 0.67:
            return False
        if len(candidates) > 1 and (top_candidate.score - candidates[1].score) < MIN_GENERIC_SCORE_MARGIN:
            return False
        return True

    def generate_candidates(self, token: str) -> list[SpellCandidate]:
        mapped_candidate = self.spelling_error_map.get(token)
        if mapped_candidate:
            return [SpellCandidate(word=mapped_candidate, score=DIRECT_SPELLING_CONFIDENCE)]

        ranked: list[SpellCandidate] = []
        seen_candidates: set[str] = set()

        for candidate in self._iter_candidate_pool(token):
            if candidate in seen_candidates:
                continue
            seen_candidates.add(candidate)

            distance = levenshtein_distance(token, candidate)
            if distance > 1:
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
        score = 1.0 - (distance * 0.18) - (abs(len(token) - len(candidate)) * 0.06)
        if token[:1] == candidate[:1]:
            score += 0.12
        if token[-1:] == candidate[-1:]:
            score += 0.1
        score += common_confusion_bonus(token, candidate)
        score += _bigram_overlap_score(token, candidate) * 0.12
        score += max(0.0, 0.015 - (rank * 0.00008))
        return round(score, 4)

    def _build_candidate_index(self, candidate_words: tuple[str, ...]) -> dict[tuple[str, int], tuple[str, ...]]:
        indexed_words: dict[tuple[str, int], list[str]] = {}
        for word in candidate_words:
            indexed_words.setdefault((word[:1], len(word)), []).append(word)
        return {key: tuple(words) for key, words in indexed_words.items()}

    def _iter_candidate_pool(self, token: str) -> Iterator[str]:
        token_length = len(token)
        for first_character in candidate_initial_chars(token):
            for candidate_length in range(max(1, token_length - 1), token_length + 2):
                yield from self._candidate_index.get((first_character, candidate_length), ())


def common_confusion_bonus(source: str, target: str) -> float:
    bonus = 0.0
    for left, right in zip(source, target):
        if left == right:
            bonus += 0.02
            continue
        if right in COMMON_BANGLA_CONFUSIONS.get(left, ()):
            bonus += 0.04
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
    if token[-1:] != candidate[-1:]:
        return False
    if token[:1] != candidate[:1]:
        return False
    return _bigram_overlap_score(token, candidate) >= 0.5


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
