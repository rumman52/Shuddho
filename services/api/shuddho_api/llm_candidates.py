from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class SentenceSpan:
    text: str
    start: int
    end: int


_SPLIT_RE = re.compile(r"([।?!\n])")
_REPEAT_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)
_RISK_PATTERNS = ["কিনেছে", "ছিলো", "  ", " ,", ".."]


def split_bangla_sentences(text: str) -> list[SentenceSpan]:
    parts = _SPLIT_RE.split(text)
    spans: list[SentenceSpan] = []
    i = 0
    cursor = 0
    while i < len(parts):
        chunk = parts[i]
        if chunk == "":
            i += 1
            continue
        sentence = chunk
        if i + 1 < len(parts) and parts[i + 1] in {"।", "?", "!", "\n"}:
            sentence += parts[i + 1]
            i += 1
        end = cursor + len(sentence)
        if sentence.strip():
            spans.append(SentenceSpan(text=sentence, start=cursor, end=end))
        cursor = end
        i += 1
    return spans


def build_llm_candidates(text: str, local_suggestions: list[dict[str, Any]], max_sentences: int = 8, max_chars: int = 2200) -> list[dict[str, Any]]:
    max_sentences = max(1, int(max_sentences or 8))
    max_chars = max(200, int(max_chars or 2200))
    text_for_ai = text[:max_chars]
    sentences = split_bangla_sentences(text_for_ai) or [SentenceSpan(text=text_for_ai, start=0, end=len(text_for_ai))]

    scored: list[tuple[int, int, SentenceSpan, list[str], list[str]]] = []
    for idx, s in enumerate(sentences):
        reasons: list[str] = []
        local_ids: list[str] = []
        for sug in local_suggestions:
            span = sug.get("span") or {}
            start = span.get("startIndex", sug.get("span_start", -1))
            end = span.get("endIndex", sug.get("span_end", -1))
            if isinstance(start, int) and isinstance(end, int) and start < s.end and end > s.start:
                reasons.append("local_rule_overlap")
                if sug.get("id"):
                    local_ids.append(str(sug["id"]))
        if _REPEAT_RE.search(s.text):
            reasons.append("repeated_word")
        if any(p in s.text for p in _RISK_PATTERNS) or re.search(r"\b(আমি|তুমি|সে|তারা)\s+\S+\s+(না|নাই)\s+\S+", s.text):
            reasons.append("bangla_grammar_risk_pattern")
        if len(s.text) > 140:
            reasons.append("long_sentence")
        if re.search(r"\s+[।,!?]|[।,!?]{2,}|\S[।!?]\S| {2,}", s.text):
            reasons.append("punctuation_spacing_suspicious")
        if len(text_for_ai) <= max_chars and len(sentences) <= max_sentences:
            reasons.append("short_text_context")
        score = sum({
            "local_rule_overlap": 5,
            "repeated_word": 4,
            "bangla_grammar_risk_pattern": 3,
            "punctuation_spacing_suspicious": 3,
            "long_sentence": 2,
            "short_text_context": 1,
        }.get(reason, 1) for reason in set(reasons))
        if reasons:
            scored.append((score, idx, s, sorted(set(reasons)), sorted(set(local_ids))))

    if not scored and sentences:
        scored = [(1, idx, s, ["short_text_context"], []) for idx, s in enumerate(sentences[:max_sentences])]
    scored.sort(key=lambda item: (-item[0], item[1]))

    candidates: list[dict[str, Any]] = []
    used_chars = 0
    for _score, idx, s, reasons, local_ids in scored:
        if used_chars + len(s.text) > max_chars and candidates:
            continue
        used_chars += len(s.text)
        candidates.append({
            "id": f"cand_{idx}",
            "sentenceId": f"s_{idx}",
            "text": s.text,
            "start": s.start,
            "end": s.end,
            "reasons": reasons,
            "local_suggestion_ids": local_ids,
        })
        if len(candidates) >= max_sentences:
            break
    candidates.sort(key=lambda item: item["start"])
    return candidates
