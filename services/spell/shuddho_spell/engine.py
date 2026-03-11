from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shared.constants.bangla import BANGLA_LETTER_PATTERN, BANGLA_WORD_PATTERN, COMMON_BANGLA_CONFUSIONS
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id


@dataclass(frozen=True)
class SpellCandidate:
    word: str
    score: float


class SpellEngine:
    def __init__(self, lexicon_path: Path | None = None) -> None:
        data_path = lexicon_path or Path(__file__).resolve().parents[1] / "data" / "seed_lexicon.txt"
        self.lexicon, self.frequency_rank = self._load_lexicon(data_path)

    def analyze(self, text: str, personal_dictionary: list[str] | None = None) -> list[Suggestion]:
        personal = set(personal_dictionary or [])
        suggestions: list[Suggestion] = []

        for match in BANGLA_WORD_PATTERN.finditer(text):
            token = match.group(0)
            if token in personal or token in self.lexicon or not BANGLA_LETTER_PATTERN.search(token):
                continue
            if len(token) < 3:
                continue

            candidates = self.generate_candidates(token)
            if not candidates:
                continue

            top_candidates = [candidate.word for candidate in candidates[:3]]
            confidence = min(max(candidates[0].score, 0.0), 0.98)
            if confidence < 0.74:
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
                    explanation_bn="এই শব্দটি অভিধানে নেই। কাছাকাছি কিছু বিকল্প দেখানো হয়েছে।",
                    explanation_en="This word is not in the local lexicon. Nearby alternatives are suggested.",
                    source=SuggestionSource.SPELL,
                    severity=SuggestionSeverity.MEDIUM
                )
            )

        return suggestions

    def generate_candidates(self, token: str) -> list[SpellCandidate]:
        ranked: list[SpellCandidate] = []
        for word in self.lexicon:
            distance = levenshtein_distance(token, word)
            if distance > 2:
                continue
            score = self._score_candidate(token, word, distance)
            if score >= 0.68:
                ranked.append(SpellCandidate(word=word, score=score))
        ranked.sort(key=lambda candidate: candidate.score, reverse=True)
        return ranked

    def _score_candidate(self, token: str, candidate: str, distance: int) -> float:
        rank = self.frequency_rank.get(candidate, 999)
        score = 1.0 - (distance * 0.18) - (abs(len(token) - len(candidate)) * 0.03)
        if token[:1] == candidate[:1]:
            score += 0.08
        if token[-1:] == candidate[-1:]:
            score += 0.06
        score += common_confusion_bonus(token, candidate)
        score += max(0.0, 0.1 - (rank * 0.002))
        return round(score, 4)

    def _load_lexicon(self, path: Path) -> tuple[set[str], dict[str, int]]:
        lexicon: set[str] = set()
        ranks: dict[str, int] = {}
        for rank, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            word = stripped.split("\t")[0]
            lexicon.add(word)
            ranks[word] = rank
        return lexicon, ranks


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

