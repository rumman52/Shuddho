from __future__ import annotations
import argparse, asyncio, hashlib, json, math, os, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from services.coworker.config import Settings
from services.coworker.drafting import DeepSeekDraftModel, DraftFailure
from services.coworker.schemas import parse_draft, source_references
from services.coworker.skills import SKILLS

DEFAULT_CASES=Path("tests/fixtures/coworker_quality_eval_cases.jsonl")

def sha256_file(path):
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()
KEYS={"id","skill_id","language","instruction","sources","required_terms","forbidden_terms","required_source_ids","missing_information","empty_paths","draft"}

def norm(v): return unicodedata.normalize("NFKC",v).casefold()
def strings(v):
    if isinstance(v,str): return [v]
    if isinstance(v,dict): return sum((strings(x) for x in v.values()),[])
    if isinstance(v,list): return sum((strings(x) for x in v),[])
    return []
def at(v,path):
    for part in path.split("."):
        if not isinstance(v,dict) or part not in v: return object()
        v=v[part]
    return v
def load_cases(path):
    out=[]
    for n,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        v=json.loads(line)
        if set(v)!=KEYS: raise ValueError(f"{path}:{n} invalid keys")
        if v["skill_id"] not in SKILLS or v["skill_id"]=="research": raise ValueError(f"{path}:{n} invalid skill")
        if v["missing_information"] not in {"empty","required"}: raise ValueError(f"{path}:{n} invalid missing_information")
        ids=[s.get("id") for s in v["sources"]]
        if not ids or len(ids)!=len(set(ids)) or not set(v["required_source_ids"]).issubset(ids): raise ValueError(f"{path}:{n} invalid sources")
        out.append(v)
    if not out or len({x["id"] for x in out})!=len(out): raise ValueError("quality fixture empty or duplicate ids")
    return out
def score(case,draft_value):
    r={"id":case["id"],"skill_id":case["skill_id"],"language":case["language"],"passed":False,"checks":{},"facts_total":len(case["required_terms"]),"facts_matched":0}
    try: d=parse_draft(case["skill_id"],draft_value)
    except Exception as e:
        r["checks"]["schema_valid"]=False; r["error"]=type(e).__name__; return r
    p=d.model_dump(); r["checks"]["schema_valid"]=True
    r["checks"]["language_match"]=d.output_language.lower()==case["language"].lower()
    available={s["id"] for s in case["sources"]}; refs=source_references(d)
    r["checks"]["source_reference_valid"]=refs.issubset(available)
    r["checks"]["required_source_coverage"]=set(case["required_source_ids"]).issubset(refs)
    text=norm("\n".join(strings(p)))
    missing=[x for x in case["required_terms"] if norm(x) not in text]
    forbidden=[x for x in case["forbidden_terms"] if norm(x) in text]
    r["missing_required_terms"]=missing; r["found_forbidden_terms"]=forbidden
    r["facts_matched"]=r["facts_total"]-len(missing)
    r["checks"]["required_fact_preservation"]=not missing
    r["checks"]["forbidden_claim_absence"]=not forbidden
    mi=p.get("missing_information",[])
    r["checks"]["missing_information_contract"]=(mi==[]) if case["missing_information"]=="empty" else bool(mi)
    bad=[x for x in case["empty_paths"] if at(p,x) not in (None,"",[],{})]
    r["empty_path_failures"]=bad; r["checks"]["empty_path_contracts"]=not bad
    r["passed"]=all(r["checks"].values()); return r
def pct(values,f):
    if not values:return None
    values=sorted(values); return values[max(0,math.ceil(len(values)*f)-1)]
def aggregate(mode,cases,results):
    passed=sum(x.get("passed",False) for x in results); total=sum(x.get("facts_total",0) for x in results); matched=sum(x.get("facts_matched",0) for x in results)
    lat=[x["latency_ms"] for x in results if isinstance(x.get("latency_ms"),int)]; tok=[x["tokens"] for x in results if isinstance(x.get("tokens"),int)]
    return {"mode":mode,"cases":len(cases),"languages":sorted({x["language"] for x in cases}),"passed":passed,"failed":len(cases)-passed,"pass_rate":round(passed/len(cases),4),"required_fact_recall":round(matched/total,4) if total else 1.0,"p95_latency_ms":pct(lat,.95),"average_tokens":round(sum(tok)/len(tok),2) if tok else None,"failures":[x["id"] for x in results if not x.get("passed")],"results":results}
def evaluate_offline(cases): return aggregate("offline",cases,[score(c,c["draft"]) for c in cases])
def live_settings():
    return Settings(database_url="sqlite://",auth_issuer="https://identity.example.test/auth/v1",environment="development",storage_backend="local",work_services_enabled=True,artifact_services_enabled=True,deepseek_model=os.environ.get("DEEPSEEK_MODEL","deepseek-flash"),deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY",""))
async def evaluate_live(cases):
    settings=live_settings()
    out=[]
    for c in cases:
        m=DeepSeekDraftModel(settings,skill_id=c["skill_id"]); ids={s["id"] for s in c["sources"]}
        try:
            x=await m.generate(m.messages({"instruction":c["instruction"],"output_language":c["language"]},c["sources"]),c["language"],ids)
            y=score(c,x.draft.model_dump()); y["tokens"]=x.total_tokens; y["latency_ms"]=x.latency_ms; out.append(y)
        except DraftFailure as e: out.append({"id":c["id"],"skill_id":c["skill_id"],"language":c["language"],"passed":False,"model_error":e.code,"tokens":e.total_tokens,"latency_ms":None,"facts_total":len(c["required_terms"]),"facts_matched":0,"checks":{"model_generation":False}})
    return aggregate("live",cases,out)
def main():
    p=argparse.ArgumentParser(); p.add_argument("--cases",type=Path,default=DEFAULT_CASES); p.add_argument("--live",action="store_true"); p.add_argument("--release-id",default="ci-quality-contract"); p.add_argument("--rollout",type=Path); p.add_argument("--min-pass-rate",type=float,default=1.0); p.add_argument("--min-fact-recall",type=float,default=1.0); p.add_argument("--max-average-tokens",type=float); p.add_argument("--max-p95-latency-ms",type=int); p.add_argument("--output",type=Path); a=p.parse_args()
    rollout_sha=None
    if a.live:
        if a.rollout is None: raise SystemExit("--rollout is required with --live.")
        rollout=json.loads(a.rollout.read_text(encoding="utf-8"))
        if not isinstance(rollout,dict): raise SystemExit("Rollout manifest must contain a JSON object.")
        if rollout.get("release_id")!=a.release_id: raise SystemExit("Quality release_id does not match the rollout manifest.")
        rollout_sha=sha256_file(a.rollout)
    cases=load_cases(a.cases); r=asyncio.run(evaluate_live(cases)) if a.live else evaluate_offline(cases); failures=[]
    if r["pass_rate"]<a.min_pass_rate: failures.append("pass_rate")
    if r["required_fact_recall"]<a.min_fact_recall: failures.append("required_fact_recall")
    if a.live and a.max_average_tokens is not None and (r["average_tokens"] is None or r["average_tokens"]>a.max_average_tokens): failures.append("average_tokens")
    if a.live and a.max_p95_latency_ms is not None and (r["p95_latency_ms"] is None or r["p95_latency_ms"]>a.max_p95_latency_ms): failures.append("p95_latency_ms")
    r["gate_decision"]="PASS" if not failures else "FAIL"; r["gate_failures"]=failures
    r["release_id"]=a.release_id
    r["generated_at"]=datetime.now(timezone.utc).isoformat()
    r["fixture_sha256"]=sha256_file(a.cases)
    r["provider_model"]=os.environ.get("DEEPSEEK_MODEL","deepseek-flash") if a.live else None
    if rollout_sha is not None:
        r["rollout_manifest_sha256"]=rollout_sha
        revision=(os.environ.get("SHUDDHO_SOURCE_REVISION") or os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GITHUB_SHA") or "").strip().lower()
        if len(revision)!=40 or any(ch not in "0123456789abcdef" for ch in revision): raise SystemExit("Live quality evaluation requires a full lowercase source revision.")
        r["source_revision"]=revision
    enc=json.dumps(r,ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(enc+"\n",encoding="utf-8")
    print(enc)
    if failures: raise SystemExit("Coworker quality gate failed: "+", ".join(failures))
if __name__=="__main__": main()
