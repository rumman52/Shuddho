from __future__ import annotations
import json, os, re, httpx
from typing import Any
OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
ALLOWED_TYPES = {"spelling", "grammar", "punctuation", "style", "fluency"}
SYSTEM_PROMPT = "You are Shuddho, a Bangla writing correction engine. Return strict JSON only. Do not use markdown. Do not explain. Do not include reasoning. Do not rewrite the whole text unless asked. Only return correction suggestions for exact spans from the input."
def _build_prompt(text: str) -> str:
    return f"""You are correcting Bangla writing for Shuddho.\n\nInput text:\n<<<TEXT\n{text}\nTEXT\n\nReturn strict JSON only in this exact shape:\n\n{{\"suggestions\":[{{\"type\":\"grammar\",\"message\":\"short Bangla or English explanation\",\"original\":\"exact substring from the input\",\"replacement\":\"corrected text\",\"start\":null,\"end\":null,\"confidence\":0.85,\"source\":\"openrouter\"}}]}}\n\nRules:\n- Return only JSON.\n- No markdown.\n- No explanation outside JSON.\n- If there are no problems, return {{\"suggestions\":[]}}.\n- \"original\" must be an exact substring from the input text.\n- Do not invent text that is not present.\n- Do not rewrite the whole paragraph.\n- Prefer short precise corrections.\n- Allowed types: spelling, grammar, punctuation, style, fluency.\n- confidence must be between 0 and 1.\n- source must be \"openrouter\"."""
def _strip_fences(content: str) -> str:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()
def _map_http(status: int) -> str:
    return {401:"openrouter_http_401_invalid_key",402:"openrouter_http_402_payment_required",403:"openrouter_http_403_forbidden",404:"openrouter_http_404_model_not_found",408:"openrouter_http_408_timeout",413:"openrouter_http_413_content_too_large",429:"openrouter_http_429_quota_or_rate_limit",500:"openrouter_provider_or_server_error",502:"openrouter_provider_or_server_error",503:"openrouter_provider_or_server_error",504:"openrouter_provider_or_server_error"}.get(status,"openrouter_http_error")
def _normalize_suggestions(input_text: str, items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list): return []
    seen, out = set(), []
    for item in items:
        if not isinstance(item, dict): continue
        original, replacement = item.get("original"), item.get("replacement")
        if not isinstance(original, str) or not isinstance(replacement, str): continue
        if not original or not replacement: continue
        start, end = item.get("start"), item.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            start = input_text.find(original); end = start + len(original) if start >= 0 else -1
        if start < 0 or input_text[start:end] != original: continue
        stype = item.get("type") if isinstance(item.get("type"), str) else "grammar"
        stype = stype if stype in ALLOWED_TYPES else "grammar"
        try: conf = float(item.get("confidence", 0.75))
        except (TypeError, ValueError): conf = 0.75
        conf = conf if 0 <= conf <= 1 else 0.75
        key = (original, replacement, start, end)
        if key in seen: continue
        seen.add(key)
        out.append({"type": stype,"message": str(item.get("message") or "Correction suggestion"),"original": original,"replacement": replacement,"start": start,"end": end,"confidence": conf,"source": "openrouter"})
    return out
def run_openrouter_check(text: str, model: str, api_key: str, language: str = "bn", timeout_seconds: float = 35.0) -> dict[str, Any]:
    del language
    model = (model or DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL
    if not api_key or not api_key.strip():
        return {"suggestions": [], "warnings": ["openrouter_api_key_missing"], "provider": "openrouter", "model": model, "raw_used": False}
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
    if os.environ.get("OPENROUTER_HTTP_REFERER", "").strip(): headers["HTTP-Referer"] = os.environ["OPENROUTER_HTTP_REFERER"].strip()
    if os.environ.get("OPENROUTER_APP_TITLE", "").strip(): headers["X-OpenRouter-Title"] = os.environ["OPENROUTER_APP_TITLE"].strip()
    payload = {"model": model,"messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":_build_prompt(text)}],"temperature":0.1,"max_completion_tokens":900,"stream":False}
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(OPENROUTER_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
    except httpx.TimeoutException:
        return {"suggestions": [], "warnings": ["openrouter_http_408_timeout"], "provider": "openrouter", "model": model, "raw_used": False}
    except httpx.RequestError:
        return {"suggestions": [], "warnings": ["openrouter_request_failed"], "provider": "openrouter", "model": model, "raw_used": False}
    if resp.status_code >= 400:
        return {"suggestions": [], "warnings": [_map_http(resp.status_code)], "provider": "openrouter", "model": model, "raw_used": False}
    try:
        outer = resp.json()
    except json.JSONDecodeError:
        return {"suggestions": [], "warnings": ["openrouter_invalid_json"], "provider": "openrouter", "model": model, "raw_used": False}
    content = ((((outer.get("choices") or [{}])[0]).get("message") or {}).get("content"))
    if not isinstance(content, str) or not content.strip():
        return {"suggestions": [], "warnings": ["openrouter_empty_response"], "provider": "openrouter", "model": model, "raw_used": False}
    try:
        parsed = json.loads(_strip_fences(content))
    except json.JSONDecodeError:
        return {"suggestions": [], "warnings": ["openrouter_invalid_json"], "provider": "openrouter", "model": model, "raw_used": False}
    suggestions = _normalize_suggestions(text, parsed.get("suggestions") if isinstance(parsed, dict) else None)
    return {"suggestions": suggestions, "warnings": [], "provider": "openrouter", "model": model, "raw_used": False}
