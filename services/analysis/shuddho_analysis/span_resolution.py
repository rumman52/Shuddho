from __future__ import annotations

import re
from dataclasses import dataclass

from shared.schemas.python_models import Suggestion, SuggestionSource


SENTENCE_PATTERN = re.compile(r"[^.!?\u0964\n]+(?:[.!?\u0964]+|$)")
ANCHOR_WINDOW = 12
SAFE_NEAREST_RESOLUTION_CONFIDENCE = 0.94


@dataclass(frozen=True)
class SentenceSpan:
    sentence_index: int
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class SentenceLocalMatch:
    occurrence_index: int
    start: int
    end: int


@dataclass(frozen=True)
class ResolvedSentenceSpan:
    match: SentenceLocalMatch
    source_trace: list[str]


def split_sentences(text: str) -> list[SentenceSpan]:
    sentences: list[SentenceSpan] = []
    for sentence_index, match in enumerate(SENTENCE_PATTERN.finditer(text)):
        raw_start = match.start()
        raw_end = match.end()
        while raw_start < raw_end and text[raw_start].isspace():
            raw_start += 1
        while raw_end > raw_start and text[raw_end - 1].isspace():
            raw_end -= 1
        if raw_end <= raw_start:
            continue
        sentences.append(
            SentenceSpan(
                sentence_index=sentence_index,
                start=raw_start,
                end=raw_end,
                text=text[raw_start:raw_end],
            )
        )
    return sentences


def enrich_suggestions_with_text_context(
    text: str,
    suggestions: list[Suggestion],
) -> list[Suggestion]:
    if not suggestions:
        return []

    sentences = split_sentences(text)
    enriched: list[Suggestion] = []
    for suggestion in suggestions:
        sentence = _find_sentence_for_span(sentences, suggestion.span_start, suggestion.span_end)
        if sentence is None:
            enriched.append(
                suggestion.model_copy(
                    update={
                        "source_trace": suggestion.source_trace or _default_source_trace(suggestion),
                    }
                )
            )
            continue

        occurrence_index = _resolve_occurrence_index(sentence, suggestion)
        anchor_before, anchor_after = build_anchor_context(
            sentence.text,
            max(0, suggestion.span_start - sentence.start),
            max(0, suggestion.span_end - sentence.start),
        )
        enriched.append(
            suggestion.model_copy(
                update={
                    "sentence_index": sentence.sentence_index,
                    "sentence_start": sentence.start,
                    "sentence_end": sentence.end,
                    "occurrence_index": occurrence_index,
                    "anchor_before": anchor_before,
                    "anchor_after": anchor_after,
                    "source_trace": suggestion.source_trace or _default_source_trace(suggestion),
                }
            )
        )
    return enriched


def resolve_sentence_span(
    *,
    sentence: SentenceSpan,
    span_text: str,
    occurrence_index: int | None,
    anchor_before: str | None,
    anchor_after: str | None,
    confidence: float,
) -> ResolvedSentenceSpan | None:
    normalized_span = span_text.strip()
    if not normalized_span:
        return None

    matches = find_sentence_local_matches(sentence.text, normalized_span)
    if not matches:
        return None
    if len(matches) == 1:
        return ResolvedSentenceSpan(match=matches[0], source_trace=["exact_unique_match"])

    if occurrence_index is not None and 0 <= occurrence_index < len(matches):
        return ResolvedSentenceSpan(match=matches[occurrence_index], source_trace=["occurrence_index"])

    anchored_matches = [
        match
        for match in matches
        if _match_anchor(sentence.text, match, anchor_before=anchor_before, anchor_after=anchor_after)
    ]
    if len(anchored_matches) == 1:
        return ResolvedSentenceSpan(match=anchored_matches[0], source_trace=["anchor_triplet"])

    partial_scores = [
        (
            _partial_anchor_score(sentence.text, match, anchor_before=anchor_before, anchor_after=anchor_after),
            _occurrence_distance(match.occurrence_index, occurrence_index),
            match,
        )
        for match in matches
    ]
    partial_scores.sort(key=lambda item: (-item[0], item[1], item[2].start))
    if confidence < SAFE_NEAREST_RESOLUTION_CONFIDENCE:
        return None
    if not partial_scores or partial_scores[0][0] <= 0:
        return None
    if len(partial_scores) > 1 and partial_scores[0][0] == partial_scores[1][0] and partial_scores[0][1] == partial_scores[1][1]:
        return None
    return ResolvedSentenceSpan(match=partial_scores[0][2], source_trace=["anchor_nearest_safe"])


def find_sentence_local_matches(sentence: str, span_text: str) -> list[SentenceLocalMatch]:
    matches: list[SentenceLocalMatch] = []
    cursor = 0
    occurrence_index = 0
    while True:
        index = sentence.find(span_text, cursor)
        if index < 0:
            break
        matches.append(
            SentenceLocalMatch(
                occurrence_index=occurrence_index,
                start=index,
                end=index + len(span_text),
            )
        )
        occurrence_index += 1
        cursor = index + 1
    return matches


def build_anchor_context(sentence: str, start: int, end: int) -> tuple[str | None, str | None]:
    anchor_before = sentence[max(0, start - ANCHOR_WINDOW) : start] or None
    anchor_after = sentence[end : min(len(sentence), end + ANCHOR_WINDOW)] or None
    return anchor_before, anchor_after


def _find_sentence_for_span(
    sentences: list[SentenceSpan],
    span_start: int,
    span_end: int,
) -> SentenceSpan | None:
    for sentence in sentences:
        if sentence.start <= span_start and span_end <= sentence.end:
            return sentence
    return None


def _resolve_occurrence_index(sentence: SentenceSpan, suggestion: Suggestion) -> int | None:
    sentence_local_start = suggestion.span_start - sentence.start
    sentence_local_end = suggestion.span_end - sentence.start
    if sentence_local_start < 0 or sentence_local_end > len(sentence.text):
        return None
    if sentence.text[sentence_local_start:sentence_local_end] != suggestion.original_text:
        return None
    matches = find_sentence_local_matches(sentence.text, suggestion.original_text)
    for match in matches:
        if match.start == sentence_local_start and match.end == sentence_local_end:
            return match.occurrence_index
    return None


def _default_source_trace(suggestion: Suggestion) -> list[str]:
    if suggestion.source == SuggestionSource.RULE:
        return ["rule_engine"]
    if suggestion.source == SuggestionSource.SPELL:
        return ["spell_engine"]
    if suggestion.source == SuggestionSource.HYBRID:
        return ["hybrid_consensus"]
    return ["model_runtime"]


def _match_anchor(
    sentence: str,
    match: SentenceLocalMatch,
    *,
    anchor_before: str | None,
    anchor_after: str | None,
) -> bool:
    before_matches = True
    after_matches = True
    if anchor_before:
        before_matches = sentence[max(0, match.start - len(anchor_before)) : match.start] == anchor_before
    if anchor_after:
        after_matches = sentence[match.end : match.end + len(anchor_after)] == anchor_after
    return before_matches and after_matches


def _partial_anchor_score(
    sentence: str,
    match: SentenceLocalMatch,
    *,
    anchor_before: str | None,
    anchor_after: str | None,
) -> int:
    score = 0
    if anchor_before and sentence[max(0, match.start - len(anchor_before)) : match.start] == anchor_before:
        score += 2
    if anchor_after and sentence[match.end : match.end + len(anchor_after)] == anchor_after:
        score += 2
    return score


def _occurrence_distance(left: int, right: int | None) -> int:
    if right is None:
        return 0
    return abs(left - right)
