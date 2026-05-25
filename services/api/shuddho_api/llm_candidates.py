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
    sentences = split_bangla_sentences(text)
    if len(text) <= max_chars:
        selected = sentences
    else:
        scored: list[tuple[int, SentenceSpan, list[str], list[str]]] = []
        for s in sentences:
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
            if any(p in s.text for p in _RISK_PATTERNS):
                reasons.append("grammar_risk_pattern")
            if len(s.text) > 140:
                reasons.append("long_sentence")
            score = 0
            for reason in reasons:
                score += {"local_rule_overlap": 4, "repeated_word": 3, "grammar_risk_pattern": 2, "long_sentence": 1}.get(reason, 1)
            if score:
                scored.append((score, s, sorted(set(reasons)), sorted(set(local_ids))))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [item[1] for item in scored[:max_sentences]]

    candidates: list[dict[str, Any]] = []
    used_chars = 0
    for idx, s in enumerate(selected, start=1):
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
        if any(p in s.text for p in _RISK_PATTERNS):
            reasons.append("grammar_risk_pattern")
        if used_chars + len(s.text) > max_chars:
            break
        used_chars += len(s.text)
        candidates.append({"id": f"cand_{idx}", "text": s.text, "start": s.start, "end": s.end, "reasons": sorted(set(reasons)) or ["short_text_context"], "local_suggestion_ids": sorted(set(local_ids))})
        if len(candidates) >= max_sentences:
            break
    return candidates
