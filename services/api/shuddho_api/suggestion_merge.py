from __future__ import annotations

import hashlib
import re
from typing import Any

from services.api.shuddho_api.llm_candidates import split_bangla_sentences

SAFE_CHANGE_TYPES = {"punctuation", "spacing"}
HIGH_CONFIDENCE = 0.75
VALID_ISSUE_TYPES = {"spelling", "grammar", "punctuation", "spacing", "repeated_word", "fluency", "sentence_rewrite", "style", "clarity", "tone", "word_choice", "other"}
VALID_SEVERITIES = {"low", "medium", "high"}


def _norm(value: str) -> str:
    return " ".join(str(value).split())


def _stable_id(prefix: str, start: int, end: int, original: str, replacement: str) -> str:
    digest = hashlib.sha1(f"{start}:{end}:{original}:{replacement}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{start}-{end}-{digest}"


def _sentence_index(text: str) -> list[dict[str, Any]]:
    return [
        {"sentenceId": f"s_{idx}", "id": f"s_{idx}", "text": s.text, "start": s.start, "end": s.end}
        for idx, s in enumerate(split_bangla_sentences(text))
    ] or [{"sentenceId": "s_0", "id": "s_0", "text": text, "start": 0, "end": len(text)}]


def _as_index(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _find_span(text: str, original: str, start: Any = None, end: Any = None, sentence_id: str | None = None) -> tuple[int, int, str | None]:
    start_index = _as_index(start)
    end_index = _as_index(end)
    if (
        start_index is not None
        and end_index is not None
        and 0 <= start_index < end_index <= len(text)
        and text[start_index:end_index] == original
    ):
        return start_index, end_index, None

    matches = [m.start() for m in re.finditer(re.escape(original), text)]
    if matches and sentence_id:
        for sentence in _sentence_index(text):
            if sentence.get("sentenceId") == sentence_id or sentence.get("id") == sentence_id:
                contained = [m for m in matches if sentence["start"] <= m and m + len(original) <= sentence["end"]]
                if len(contained) == 1:
                    s = contained[0]
                    return s, s + len(original), None
                if len(contained) > 1 and start_index is not None:
                    nearest = min(contained, key=lambda m: abs(m - start_index))
                    if abs(nearest - start_index) <= max(3, len(original)):
                        return nearest, nearest + len(original), None
                    return -1, -1, "ai_suggestion_ambiguous_span"
                if len(contained) > 1:
                    return -1, -1, "ai_suggestion_ambiguous_span"
                break
    if len(matches) == 1:
        s = matches[0]
        return s, s + len(original), None
    if len(matches) > 1 and start_index is not None:
        nearest = min(matches, key=lambda m: abs(m - start_index))
        if abs(nearest - start_index) <= max(3, len(original)):
            return nearest, nearest + len(original), None
    if len(matches) > 1:
        return -1, -1, "ai_suggestion_ambiguous_span"
    whitespace_span = _find_whitespace_normalized_span(text, original)
    if whitespace_span is not None:
        return whitespace_span[0], whitespace_span[1], None
    return -1, -1, "ai_suggestion_original_not_found"



def _find_whitespace_normalized_span(text: str, original: str) -> tuple[int, int] | None:
    target = _norm(original)
    if not target:
        return None
    tokens = original.split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    matches = list(re.finditer(pattern, text))
    if len(matches) == 1:
        match = matches[0]
        return match.start(), match.end()
    return None

def _looks_sensitive_change(original: str, replacement: str, issue_type: str) -> bool:
    if issue_type in SAFE_CHANGE_TYPES:
        return False
    tokens = [
        r"https?://\S+",
        r"[\w.+-]+@[\w.-]+",
        r"\b\d+[\w.-]*\b",
        r"[`\"“”‘’].*[`\"“”‘’]",
        r"\b[A-Z]{2,}[-_A-Z0-9]*\d+[-_A-Z0-9]*\b",
    ]
    if any(re.search(pattern, original) and original != replacement for pattern in tokens):
        return True
    original_numbers = re.findall(r"[০-৯0-9]+(?:[.,][০-৯0-9]+)?", original)
    replacement_numbers = re.findall(r"[০-৯0-9]+(?:[.,][০-৯0-9]+)?", replacement)
    return original_numbers != replacement_numbers


def validate_ai_suggestions(
    text: str,
    ai_suggestions: list[dict[str, Any]],
    sentences: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    valid: list[dict[str, Any]] = []
    sentence_count = len(sentences or _sentence_index(text))
    known_sentence_ids = {str(s.get("sentenceId") or s.get("id")) for s in (sentences or _sentence_index(text))}
    for index, item in enumerate(ai_suggestions):
        if not isinstance(item, dict):
            warnings.append("ai_suggestion_invalid_schema")
            continue
        original = item.get("original") or item.get("originalText") or item.get("original_text")
        replacement = item.get("replacement") or item.get("suggestedText") or item.get("suggested_text") or item.get("replacementText") or item.get("replacement_text")
        if not isinstance(original, str) or not isinstance(replacement, str) or not original.strip() or not replacement.strip():
            warnings.append("ai_suggestion_invalid_schema")
            continue
        issue_type = str(item.get("issueType") or item.get("type") or "grammar")
        if original == replacement or (issue_type not in SAFE_CHANGE_TYPES and _norm(original) == _norm(replacement)):
            warnings.append("ai_suggestion_identical_replacement")
            continue
        try:
            confidence = float(item.get("confidence", 0.75))
        except (TypeError, ValueError):
            warnings.append("ai_suggestion_invalid_confidence")
            continue
        if confidence < 0 or confidence > 1:
            warnings.append("ai_suggestion_invalid_confidence")
            continue
        if issue_type not in VALID_ISSUE_TYPES:
            warnings.append("ai_suggestion_invalid_issue_type")
            continue
        severity = str(item.get("severity") or "medium")
        if severity not in VALID_SEVERITIES:
            warnings.append("ai_suggestion_invalid_severity")
            continue
        sentence_id = str(item.get("sentenceId") or item.get("sentence_id") or "")
        start, end, warning = _find_span(text, original, item.get("start", item.get("span_start")), item.get("end", item.get("span_end")), sentence_id)
        if warning:
            warnings.append(warning)
            continue
        if _norm(original) == _norm(text) or (len(original) >= max(1, int(len(text) * 0.8)) and sentence_count > 1):
            warnings.append("ai_suggestion_rewrites_whole_text")
            continue
        if sentence_id and sentence_id not in known_sentence_ids:
            resolved = next((s for s in (sentences or _sentence_index(text)) if s["start"] <= start and end <= s["end"]), None)
            if not resolved:
                warnings.append("ai_suggestion_unknown_sentence_id")
                continue
            sentence_id = str(resolved.get("sentenceId") or resolved.get("id") or sentence_id)
        if _looks_sensitive_change(original, replacement, issue_type):
            warnings.append("ai_suggestion_sensitive_text_change_rejected")
            continue
        valid.append({
            "id": str(item.get("id") or _stable_id("ai", start, end, original, replacement)),
            "sentenceId": sentence_id or "s_0",
            "original": original,
            "replacement": replacement,
            "issueType": issue_type,
            "severity": severity,
            "explanation": str(item.get("explanation") or item.get("message") or "প্রস্তাবিত সংশোধন"),
            "confidence": confidence,
            "source": "ai",
            "span_start": start,
            "span_end": end,
        })
    return valid, warnings


def _canonicalize_local(item: dict[str, Any]) -> dict[str, Any] | None:
    span = item.get("span") or {}
    start = span.get("startIndex", item.get("span_start"))
    end = span.get("endIndex", item.get("span_end"))
    original = item.get("originalText") or item.get("original_text")
    suggested = item.get("suggestedText") or item.get("suggested_text") or (item.get("replacementOptions") or item.get("replacement_options") or [None])[0]
    if not isinstance(start, int) or not isinstance(end, int) or not isinstance(original, str) or not isinstance(suggested, str):
        return None
    return {
        "id": str(item.get("id") or _stable_id("local", start, end, original, suggested)),
        "suppressionKey": str(item.get("suppressionKey") or item.get("suppression_key") or f"local:{start}:{end}:{original}"),
        "ruleId": str(item.get("ruleId") or item.get("rule_id") or "local.suggestion"),
        "type": str(item.get("type") or item.get("category") or "grammar"),
        "severity": str(item.get("severity") or "low"),
        "originalText": original,
        "suggestedText": suggested,
        "replacementOptions": list(item.get("replacementOptions") or item.get("replacement_options") or [suggested]),
        "explanationBn": str(item.get("explanationBn") or item.get("explanation_bn") or "প্রস্তাবিত সংশোধন"),
        "explanationEn": item.get("explanationEn") or item.get("explanation_en"),
        "span": {"startIndex": start, "endIndex": end},
        "confidence": float(item.get("confidence", 0.6)),
        "source": item.get("source") or "rule",
        "provider": item.get("provider") or "local",
        "metadata": {**(item.get("metadata") or {}), "sources": ["local"], "mergeStatus": "local_only"},
    }


def _canonicalize_ai(item: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
    start, end = int(item["span_start"]), int(item["span_end"])
    original, replacement = str(item["original"]), str(item["replacement"])
    return {
        "id": _stable_id("ai", start, end, original, replacement),
        "suppressionKey": f"ai:{provider}:{start}:{end}:{_norm(original)}",
        "ruleId": f"ai.{item.get('issueType', 'grammar')}",
        "type": str(item.get("issueType") or "grammar"),
        "severity": str(item.get("severity") or "medium"),
        "originalText": original,
        "suggestedText": replacement,
        "replacementOptions": [replacement],
        "explanationBn": str(item.get("explanation") or "প্রস্তাবিত সংশোধন"),
        "explanationEn": None,
        "span": {"startIndex": start, "endIndex": end},
        "confidence": float(item.get("confidence", 0.75)),
        "source": "model",
        "provider": provider,
        "metadata": {"sources": ["ai"], "provider": provider, "model": model, "mergeStatus": "ai_only"},
    }


def merge_suggestions(
    text: str,
    local_suggestions: list[dict[str, Any]],
    ai_suggestions: list[dict[str, Any]],
    provider: str,
    model: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    merged: list[dict[str, Any]] = []
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}

    def key_for(item: dict[str, Any]) -> tuple[Any, ...]:
        span = item["span"]
        return (span["startIndex"], span["endIndex"], _norm(item["originalText"]), _norm(item["suggestedText"]), item["type"])

    span_type_index: dict[tuple[int, int, str], dict[str, Any]] = {}
    for local in local_suggestions:
        canonical = _canonicalize_local(local)
        if canonical is None:
            warnings.append("local_suggestion_invalid_shape")
            continue
        start, end = canonical["span"]["startIndex"], canonical["span"]["endIndex"]
        if not (0 <= start < end <= len(text)) or text[start:end] != canonical["originalText"]:
            warnings.append("local_suggestion_invalid_span")
            continue
        if canonical["originalText"] == canonical["suggestedText"] or (canonical["type"] not in SAFE_CHANGE_TYPES and _norm(canonical["originalText"]) == _norm(canonical["suggestedText"])):
            warnings.append("local_suggestion_identical_replacement")
            continue
        k = key_for(canonical)
        if k in by_key:
            warnings.append("local_suggestion_duplicate_dropped")
            continue
        by_key[k] = canonical
        span_type_index.setdefault((start, end, canonical["type"]), canonical)
        merged.append(canonical)

    for ai in ai_suggestions:
        canonical = _canonicalize_ai(ai, provider, model)
        start, end = canonical["span"]["startIndex"], canonical["span"]["endIndex"]
        if not (0 <= start < end <= len(text)) or text[start:end] != canonical["originalText"]:
            warnings.append("ai_suggestion_invalid_span")
            continue
        if canonical["originalText"] not in text:
            warnings.append("ai_suggestion_original_not_found")
            continue
        if canonical["originalText"] == canonical["suggestedText"] or (canonical["type"] not in SAFE_CHANGE_TYPES and _norm(canonical["originalText"]) == _norm(canonical["suggestedText"])):
            warnings.append("ai_suggestion_identical_replacement")
            continue
        exact = by_key.get(key_for(canonical))
        if exact:
            meta = dict(exact.get("metadata") or {})
            meta["sources"] = sorted(set(meta.get("sources", ["local"]) + ["ai"]))
            meta.update({"provider": provider, "model": model, "mergeStatus": "merged"})
            exact["metadata"] = meta
            exact["source"] = "hybrid"
            exact["provider"] = provider
            exact["confidence"] = max(float(exact.get("confidence", 0)), float(canonical.get("confidence", 0)))
            if len(canonical.get("explanationBn", "")) > len(exact.get("explanationBn", "")):
                exact["explanationBn"] = canonical["explanationBn"]
            continue
        competing = span_type_index.get((start, end, canonical["type"]))
        if competing and float(canonical.get("confidence", 0)) >= HIGH_CONFIDENCE:
            meta = dict(competing.get("metadata") or {})
            meta["sources"] = sorted(set(meta.get("sources", ["local"]) + ["ai"]))
            meta.update({"provider": provider, "model": model, "mergeStatus": "merged"})
            competing.update({
                "suggestedText": canonical["suggestedText"],
                "replacementOptions": canonical["replacementOptions"],
                "confidence": max(float(competing.get("confidence", 0)), float(canonical.get("confidence", 0))),
                "explanationBn": canonical["explanationBn"],
                "source": "hybrid",
                "provider": provider,
                "metadata": meta,
            })
            continue
        if competing and key_for(competing) != key_for(canonical):
            # Keep independent AI corrections instead of dropping valid lower-confidence
            # items; exact duplicates were handled above.
            pass
        by_key[key_for(canonical)] = canonical
        span_type_index[(start, end, canonical["type"])] = canonical
        merged.append(canonical)

    actionable = [
        item for item in merged
        if item["originalText"] != item["suggestedText"]
        and (item["type"] in SAFE_CHANGE_TYPES or _norm(item["originalText"]) != _norm(item["suggestedText"]))
    ]
    actionable.sort(key=lambda item: (item["span"]["startIndex"], item["span"]["endIndex"], item["type"], item["id"]))
    return actionable, warnings
