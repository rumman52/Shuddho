from __future__ import annotations
import json, os, re
from typing import Any
import httpx

OPENAI_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = "You are Shuddho, a professional Bangla writing assistant. Review the entire user text with full context before suggesting corrections. Do not check only isolated words. Find spelling, grammar, punctuation, spacing, word choice, clarity, fluency, style, and meaning/context problems. Preserve the user's intended meaning. Prefer natural modern Bangla. Do not change names, numbers, URLs, emails, code, or quoted text unless clearly wrong. Return only structured JSON that matches the required schema. For every inline suggestion, provide the exact original substring from the user's text, the replacement, category, severity, confidence, and a short explanation. If a correction cannot be attached to an exact original substring, put it in documentAssessment instead of inventing an offset. Always include correctedText for the whole reviewed text."


def _extract_json(text:str)->Any:
    text=text.strip()
    text=re.sub(r"^```(?:json)?\\s*","",text,flags=re.I)
    text=re.sub(r"\\s*```$","",text)
    try:return json.loads(text)
    except Exception:pass
    m=re.search(r"\{[\s\S]*\}",text)
    if m:return json.loads(m.group(0))
    raise json.JSONDecodeError("bad",text,0)


def run_openai_check(text:str, model:str, api_key:str, timeout_seconds:float=35.0)->dict[str,Any]:
    model=(model or DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    if not api_key:
        return {"suggestions":[],"correctedText":"","documentAssessment":{},"warnings":["openai_api_key_missing"],"provider":"openai","model":model,"llm_enabled":True,"status":"failed","response_mode":"json_schema","finish_reasons":[],"diagnostics":{}}
    payload={"model":model,"input":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":text}],"text":{"format":{"type":"json_object"}},"max_output_tokens":1200}
    try:
        with httpx.Client(timeout=timeout_seconds) as c:
            r=c.post(OPENAI_URL,headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},json=payload)
    except httpx.TimeoutException:
        return {"suggestions":[],"correctedText":"","documentAssessment":{},"warnings":["openai_timeout"],"provider":"openai","model":model,"llm_enabled":True,"status":"timeout","response_mode":"json_object","finish_reasons":[],"diagnostics":{}}
    if r.status_code==401: w=["openai_http_401_invalid_key"]
    elif r.status_code==402: w=["openai_http_402_payment_required"]
    elif r.status_code==429: w=["openai_http_429_quota_or_rate_limit"]
    elif r.status_code>=400: w=["openai_unexpected_error"]
    else: w=[]
    if w:
        return {"suggestions":[],"correctedText":"","documentAssessment":{},"warnings":w,"provider":"openai","model":model,"llm_enabled":True,"status":"failed","response_mode":"json_object","finish_reasons":[],"diagnostics":{"status_code":r.status_code}}
    data=r.json()
    out=(data.get("output_text") or "").strip()
    try: parsed=_extract_json(out)
    except Exception:
        return {"suggestions":[],"correctedText":"","documentAssessment":{},"warnings":["openai_invalid_json"],"provider":"openai","model":model,"llm_enabled":True,"status":"invalid_json","response_mode":"plain_json","finish_reasons":[],"diagnostics":{}}
    sugs=parsed.get("suggestions") or parsed.get("corrections") or parsed.get("issues") or parsed.get("edits") or ([] if not isinstance(parsed,list) else parsed)
    if not isinstance(sugs,list): sugs=[]
    return {"suggestions":sugs,"correctedText":parsed.get("correctedText","") if isinstance(parsed,dict) else "","documentAssessment":parsed.get("documentAssessment",{}) if isinstance(parsed,dict) else {},"warnings":[],"provider":"openai","model":model,"llm_enabled":True,"status":"completed","response_mode":"json_object","finish_reasons":[],"diagnostics":{}}
