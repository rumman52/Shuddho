from __future__ import annotations

import hashlib
import re
from typing import Any

from services.api.shuddho_api.llm_candidates import split_bangla_sentences

SAFE_CHANGE_TYPES = {"punctuation", "spacing"}
HIGH_CONFIDENCE = 0.75


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


def _find_span(text: str, original: str, start: Any = None, end: Any = None, sentence_id: str | None = None) -> tuple[int, int, str | None]:
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text) and text[start:end] == original:
        return start, end, None
    matches = [m.start() for m in re.finditer(re.escape(original), text)]
    if not matches:
        return -1, -1, "ai_suggestion_original_not_found"
    if len(matches) == 1:
        s = matches[0]
        return s, s + len(original), None
    if sentence_id:
        for sentence in _sentence_index(text):
            if sentence.get("sentenceId") == sentence_id or sentence.get("id") == sentence_id:
                contained = [m for m in matches if sentence["start"] <= m and m + len(original) <= sentence["end"]]
                if len(contained) == 1:
                    s = contained[0]
                    return s, s + len(original), None
    return -1, -1, "ai_suggestion_ambiguous_span"


def _looks_sensitive_change(original: str, replacement: str, issue_type: str) -> bool:
    if issue_type in SAFE_CHANGE_TYPES:
        return False
    tokens = [r"https?://\S+", r"[\w.+-]+@[\w.-]+", r"\b\d+[\w.-]*\b", r"[`\"“”‘’].*[`\"“”‘’]"]
    return any(re.search(pattern, original) and original != replacement for pattern in tokens)


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
        replacement = item.get("replacement") or item.get("suggestedText") or item.get("suggested_text")
        if not isinstance(original, str) or not isinstance(replacement, str) or not original.strip() or not replacement.strip():
            warnings.append("ai_suggestion_invalid_schema")
            continue
        if _norm(original) == _norm(replacement):
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
        issue_type = str(item.get("issueType") or item.get("type") or "grammar")
        sentence_id = str(item.get("sentenceId") or item.get("sentence_id") or "")
        start, end, warning = _find_span(text, original, item.get("start") or item.get("span_start"), item.get("end") or item.get("span_end"), sentence_id)
        if warning:
            warnings.append(warning)
            continue
        if _norm(original) == _norm(text) and sentence_count > 1:
            warnings.append("ai_suggestion_rewrites_whole_text")
            continue
        if sentence_id and sentence_id not in known_sentence_ids:
            resolved = next((s for s in (sentences or _sentence_index(text)) if s["start"] <= start and end <= s["end"]), None)
            sentence_id = str((resolved or {}).get("sentenceId") or (resolved or {}).get("id") or sentence_id)
        if _looks_sensitive_change(original, replacement, issue_type):
            warnings.append("ai_suggestion_sensitive_text_change_rejected")
            continue
        valid.append({
            "id": str(item.get("id") or _stable_id("ai", start, end, original, replacement)),
            "sentenceId": sentence_id or "s_0",
            "original": original,
            "replacement": replacement,
            "issueType": issue_type if issue_type in {"grammar","spelling","punctuation","spacing","style","clarity","fluency","tone","word_choice","other"} else "other",
            "severity": str(item.get("severity") or "medium") if str(item.get("severity") or "medium") in {"low","medium","high"} else "medium",
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
        k = key_for(canonical)
        by_key[k] = canonical
        span_type_index[(start, end, canonical["type"])] = canonical
        merged.append(canonical)

    for ai in ai_suggestions:
        canonical = _canonicalize_ai(ai, provider, model)
        start, end = canonical["span"]["startIndex"], canonical["span"]["endIndex"]
        if not (0 <= start < end <= len(text)) or text[start:end] != canonical["originalText"]:
            warnings.append("ai_suggestion_invalid_span")
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
        if competing and float(canonical.get("confidence", 0)) < HIGH_CONFIDENCE and competing["type"] in {"spelling", "grammar"}:
            continue
        by_key[key_for(canonical)] = canonical
        span_type_index[(start, end, canonical["type"])] = canonical
        merged.append(canonical)

    actionable = [item for item in merged if _norm(item["originalText"]) != _norm(item["suggestedText"])]
    actionable.sort(key=lambda item: (item["span"]["startIndex"], item["span"]["endIndex"], item["id"]))
    return actionable, warnings
