from __future__ import annotations
import argparse, asyncio, hashlib, json, math, os, unicodedata
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from services.coworker.config import Settings
from services.coworker.content_generation import CONTENT_TASK_TYPES, PROMPT_VERSION, classify_content_task
from services.coworker.drafting import DeepSeekDraftModel, DraftFailure
from services.coworker.research import validate_evidence
from services.coworker.schemas import parse_draft, source_references
from services.coworker.skills import SKILLS

DEFAULT_CASES=Path("tests/fixtures/coworker_quality_eval_cases.jsonl")

def sha256_file(path):
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()
KEYS={"id","skill_id","language","instruction","sources","required_terms","forbidden_terms","required_source_ids","missing_information","empty_paths","expected_task_type","draft"}

def norm(v): return unicodedata.normalize("NFKC",v).casefold()
def strings(v):
    if isinstance(v, str):
        return [v]
    if isinstance(v, bool) or v is None:
        return []
    if isinstance(v, (int, float)):
        return [format(v, "g")] if math.isfinite(v) else []
    if isinstance(v, dict):
        return sum((strings(item) for item in v.values()), [])
    if isinstance(v, list):
        return sum((strings(item) for item in v), [])
    return []
# Evidence quotes and provenance validate citation integrity, not facts
# actually carried into the user-visible draft. In particular a research
# finding cannot pass fact recall merely by attaching a source quote.
NON_AUTHOR_CONTENT_KEYS=frozenset({"citations","source_ids","labels","output_language"})
def authored_strings(v):
    if isinstance(v,dict):
        return sum((authored_strings(item) for key,item in v.items()
                    if key not in NON_AUTHOR_CONTENT_KEYS),[])
    if isinstance(v,list):
        return sum((authored_strings(item) for item in v),[])
    return strings(v)

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
        if v["skill_id"] not in SKILLS: raise ValueError(f"{path}:{n} invalid skill")
        if v["expected_task_type"] not in CONTENT_TASK_TYPES: raise ValueError(f"{path}:{n} invalid expected_task_type")
        if v["missing_information"] not in {"empty","required"}: raise ValueError(f"{path}:{n} invalid missing_information")
        ids=[s.get("id") for s in v["sources"]]
        if not ids or len(ids)!=len(set(ids)) or not set(v["required_source_ids"]).issubset(ids): raise ValueError(f"{path}:{n} invalid sources")
        out.append(v)
    if not out or len({x["id"] for x in out})!=len(out): raise ValueError("quality fixture empty or duplicate ids")
    return out
def score(case,draft_value):
    r={"id":case["id"],"skill_id":case["skill_id"],"language":case["language"],
       "task_type":case["expected_task_type"],"passed":False,"checks":{},
       "facts_total":len(case["required_terms"]),"facts_matched":0}
    try: d=parse_draft(case["skill_id"],draft_value)
    except Exception as e:
        r["checks"]["schema_valid"]=False; r["error"]=type(e).__name__; return r
    p=d.model_dump(); r["checks"]["schema_valid"]=True
    r["checks"]["task_type_match"]=classify_content_task(case["skill_id"],case["instruction"])==case["expected_task_type"]
    r["checks"]["language_match"]=d.output_language.lower()==case["language"].lower()
    available={s["id"] for s in case["sources"]}; refs=source_references(d)
    required_refs=set(case["required_source_ids"])
    valid_refs=refs.intersection(available)
    r["checks"]["source_reference_valid"]=refs.issubset(available)
    r["checks"]["required_source_coverage"]=required_refs.issubset(refs)
    r["citation_source_precision"]=len(valid_refs)/len(refs) if refs else 1.0
    r["citation_source_recall"]=len(required_refs.intersection(refs))/len(required_refs) if required_refs else 1.0
    if case["skill_id"]=="research":
        try:
            validate_evidence(d,case["sources"])
            r["checks"]["citation_validation"]=True
        except (ValueError,TypeError,KeyError):
            r["checks"]["citation_validation"]=False
    text=norm("\n".join(authored_strings(p)))
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
    passed=sum(x.get("passed",False) for x in results)
    total=sum(x.get("facts_total",0) for x in results)
    matched=sum(x.get("facts_matched",0) for x in results)
    lat=[x["latency_ms"] for x in results if isinstance(x.get("latency_ms"),int) and x["latency_ms"]>=0]
    tok=[x["tokens"] for x in results if isinstance(x.get("tokens"),int) and not isinstance(x.get("tokens"),bool) and x["tokens"]>=0]
    token_usage_complete=len(tok)==len(results)
    citation_precision=[x["citation_source_precision"] for x in results if isinstance(x.get("citation_source_precision"),(int,float))]
    citation_recall=[x["citation_source_recall"] for x in results if isinstance(x.get("citation_source_recall"),(int,float))]
    generations=[x.get("generation") for x in results if isinstance(x.get("generation"),dict)]
    by_language={}
    for language in sorted({x["language"] for x in cases}):
        language_cases=[x for x in cases if x["language"]==language]
        language_results=[x for x in results if x["language"]==language]
        language_passed=sum(x.get("passed",False) for x in language_results)
        language_facts=sum(x.get("facts_total",0) for x in language_results)
        language_matched=sum(x.get("facts_matched",0) for x in language_results)
        language_latencies=[x["latency_ms"] for x in language_results if isinstance(x.get("latency_ms"),int)]
        language_tokens=[x["tokens"] for x in language_results if isinstance(x.get("tokens"),int) and not isinstance(x.get("tokens"),bool)]
        by_language[language]={
            "cases":len(language_cases),
            "evaluated_cases":len(language_results),
            "passed":language_passed,
            "failed":len(language_cases)-language_passed,
            "pass_rate":round(language_passed/len(language_cases),4) if language_cases else 1.0,
            "required_fact_recall":round(language_matched/language_facts,4) if language_facts else 1.0,
            "p95_latency_ms":pct(language_latencies,.95),
            "average_tokens":round(sum(language_tokens)/len(language_tokens),2) if language_tokens else None,
            "evaluation_complete":len(language_results)==len(language_cases),
        }
    return {
        "mode":mode,
        "cases":len(cases),
        "evaluated_cases":len(results),
        "evaluation_complete":len(results)==len(cases),
        "languages":sorted({x["language"] for x in cases}),
        "by_language":by_language,
        "citation_source_precision":round(sum(citation_precision)/len(citation_precision),4) if citation_precision else 1.0,
        "citation_source_recall":round(sum(citation_recall)/len(citation_recall),4) if citation_recall else 1.0,
        "task_types":sorted({x["expected_task_type"] for x in cases}),
        "prompt_versions":sorted({x["prompt_version"] for x in generations if x.get("prompt_version")}),
        "models":sorted({x["model"] for x in generations if x.get("model")}),
        "passed":passed,
        "failed":len(cases)-passed,
        "pass_rate":round(passed/len(cases),4) if cases else 1.0,
        "required_fact_recall":round(matched/total,4) if total else 1.0,
        "total_tokens":sum(tok) if token_usage_complete else None,
        "token_usage_complete":token_usage_complete,
        "total_latency_ms":sum(lat) if lat else None,
        "p50_latency_ms":pct(lat,.50),
        "p95_latency_ms":pct(lat,.95),
        "p99_latency_ms":pct(lat,.99),
        "average_tokens":round(sum(tok)/len(tok),2) if tok else None,
        "failures":[x["id"] for x in results if not x.get("passed")],
        "results":results,
    }
def evaluate_offline(cases): return aggregate("offline",cases,[score(c,c["draft"]) for c in cases])
def live_settings():
    return Settings(database_url="sqlite://",auth_issuer="https://identity.example.test/auth/v1",environment="development",storage_backend="local",work_services_enabled=True,artifact_services_enabled=True,deepseek_model=os.environ.get("DEEPSEEK_MODEL","deepseek-flash"),deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY",""))
async def evaluate_live(
    cases,
    *,
    max_total_tokens=100000,
    max_total_cost_microusd=500000,
    cost_rate_microusd_per_1k_tokens=0,
):
    if max_total_tokens < 1 or max_total_cost_microusd < 1 or cost_rate_microusd_per_1k_tokens < 1:
        raise ValueError("Live quality evaluation requires positive token, cost and reviewed rate limits.")
    cost_token_limit=(max_total_cost_microusd*1000)//cost_rate_microusd_per_1k_tokens
    effective_token_limit=min(max_total_tokens,cost_token_limit)
    if effective_token_limit < 1:
        raise ValueError("The configured quality evaluation cost budget cannot fund one model token.")
    settings=replace(
        live_settings(),
        agent_v3_planner_cost_microusd_per_1k_tokens=cost_rate_microusd_per_1k_tokens,
    )
    out=[]
    budget_failures=[]
    token_usage_complete=True
    total_tokens=0
    for c in cases:
        if effective_token_limit-total_tokens <= 0:
            budget_failures.append("total_token_budget")
            break
        m=DeepSeekDraftModel(settings,skill_id=c["skill_id"])
        ids={s["id"] for s in c["sources"]}
        messages=m.messages({"instruction":c["instruction"],"output_language":c["language"]},c["sources"])
        prompt_sha256=hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
        tokens=None
        try:
            x=await m.generate(messages,c["language"],ids)
            tokens=x.total_tokens
            usage_valid=isinstance(tokens,int) and not isinstance(tokens,bool) and tokens>=0
            if not usage_valid:
                token_usage_complete=False
                raise RuntimeError("token_usage_incomplete")
            total_tokens+=tokens
            if not isinstance(x.latency_ms,int) or isinstance(x.latency_ms,bool) or x.latency_ms<0:
                raise RuntimeError("invalid_latency_metadata")
            y=score(c,x.draft.model_dump())
            y["tokens"]=tokens
            y["latency_ms"]=x.latency_ms
            y["generation"]=x.generation_metadata(
                validator_result="passed" if y["passed"] else "failed",
                error_class=None if y["passed"] else "quality_evaluation_failed",
            )
            out.append(y)
        except DraftFailure as e:
            tokens=e.total_tokens
            error_tokens_valid=isinstance(tokens,int) and not isinstance(tokens,bool) and tokens>=0
            if not error_tokens_valid:
                token_usage_complete=False
                budget_failures.append("token_usage_incomplete")
            else:
                total_tokens+=tokens
            out.append({
                "id":c["id"],"skill_id":c["skill_id"],"language":c["language"],
                "task_type":c["expected_task_type"],"passed":False,"model_error":e.code,
                "tokens":tokens,"latency_ms":None,"facts_total":len(c["required_terms"]),
                "facts_matched":0,"checks":{"model_generation":False},
                "generation":{
                    "provider":"deepseek","model":settings.deepseek_model,
                    "prompt_version":PROMPT_VERSION,"prompt_sha256":prompt_sha256,
                    "task_type":c["expected_task_type"],"validator_result":"failed",
                    "error_class":e.code,
                },
            })
        except RuntimeError as e:
            budget_failures.append(str(e))
            out.append({
                "id":c["id"],"skill_id":c["skill_id"],"language":c["language"],
                "task_type":c["expected_task_type"],"passed":False,"model_error":str(e),
                "tokens":tokens if isinstance(tokens,int) and not isinstance(tokens,bool) and tokens>=0 else None,
                "latency_ms":None,"facts_total":len(c["required_terms"]),
                "facts_matched":0,"checks":{"model_generation":False},
                "generation":{
                    "provider":"deepseek","model":settings.deepseek_model,
                    "prompt_version":PROMPT_VERSION,"prompt_sha256":prompt_sha256,
                    "task_type":c["expected_task_type"],"validator_result":"failed",
                    "error_class":str(e),
                },
            })
        if total_tokens>effective_token_limit:
            budget_failures.append("total_token_budget")
        if budget_failures:
            break

    result=aggregate("live",cases,out)
    estimated_cost=(
        (total_tokens*cost_rate_microusd_per_1k_tokens+999)//1000
        if token_usage_complete else None
    )
    if total_tokens>max_total_tokens:
        budget_failures.append("total_token_budget")
    if estimated_cost is not None and estimated_cost>max_total_cost_microusd:
        budget_failures.append("total_cost_budget")
    if not token_usage_complete:
        budget_failures.append("token_usage_incomplete")
    result.update({
        "total_tokens":total_tokens if token_usage_complete else None,
        "token_usage_complete":token_usage_complete,
        "total_latency_ms":sum(x["latency_ms"] for x in out if isinstance(x.get("latency_ms"),int)),
        "estimated_cost_microusd":estimated_cost,
        "cost_rate_microusd_per_1k_tokens":cost_rate_microusd_per_1k_tokens,
        "cost_basis":"operator-configured blended effective rate; estimate, not provider invoice",
        "cost_is_estimate":True,
        "max_total_tokens":max_total_tokens,
        "max_total_cost_microusd":max_total_cost_microusd,
        "effective_token_limit":effective_token_limit,
        "budget_failures":list(dict.fromkeys(budget_failures)),
    })
    return result
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cases",type=Path,default=DEFAULT_CASES)
    p.add_argument("--live",action="store_true")
    p.add_argument("--release-id",default="ci-quality-contract")
    p.add_argument("--rollout",type=Path)
    p.add_argument("--min-pass-rate",type=float,default=1.0)
    p.add_argument("--min-fact-recall",type=float,default=1.0)
    p.add_argument("--max-average-tokens",type=float)
    p.add_argument("--max-p95-latency-ms",type=int)
    p.add_argument("--max-total-tokens",type=int,default=100000)
    p.add_argument("--max-total-cost-microusd",type=int,default=500000)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    rollout_sha=None
    revision=None
    if a.live:
        if a.rollout is None:
            raise SystemExit("--rollout is required with --live.")
        rollout=json.loads(a.rollout.read_text(encoding="utf-8"))
        if not isinstance(rollout,dict):
            raise SystemExit("Rollout manifest must contain a JSON object.")
        if rollout.get("release_id")!=a.release_id:
            raise SystemExit("Quality release_id does not match the rollout manifest.")
        rollout_sha=sha256_file(a.rollout)
        revision=(os.environ.get("SHUDDHO_SOURCE_REVISION") or os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GITHUB_SHA") or "").strip().lower()
        if len(revision)!=40 or any(ch not in "0123456789abcdef" for ch in revision):
            raise SystemExit("Live quality evaluation requires a full lowercase source revision.")
        if not os.environ.get("DEEPSEEK_API_KEY","").strip():
            raise SystemExit("Live quality evaluation requires a backend-only DEEPSEEK_API_KEY.")
        try:
            rate=int(os.environ.get("SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS","0"))
        except (TypeError,ValueError):
            rate=0
        if rate<=0:
            raise SystemExit("Live quality evaluation requires a reviewed positive SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS rate.")
    cases=load_cases(a.cases)
    r=asyncio.run(evaluate_live(
        cases,
        max_total_tokens=a.max_total_tokens,
        max_total_cost_microusd=a.max_total_cost_microusd,
        cost_rate_microusd_per_1k_tokens=rate,
    )) if a.live else evaluate_offline(cases)
    failures=[]
    if r["pass_rate"]<a.min_pass_rate:
        failures.append("pass_rate")
    if r["required_fact_recall"]<a.min_fact_recall:
        failures.append("required_fact_recall")
    if a.live and a.max_average_tokens is not None and (r["average_tokens"] is None or r["average_tokens"]>a.max_average_tokens):
        failures.append("average_tokens")
    if a.live and a.max_p95_latency_ms is not None and (r["p95_latency_ms"] is None or r["p95_latency_ms"]>a.max_p95_latency_ms):
        failures.append("p95_latency_ms")
    failures.extend(r.get("budget_failures",[]))
    r["gate_decision"]="PASS" if not failures else "FAIL"
    r["gate_failures"]=list(dict.fromkeys(failures))
    r["release_id"]=a.release_id
    r["generated_at"]=datetime.now(timezone.utc).isoformat()
    r["fixture_sha256"]=sha256_file(a.cases)
    r["provider_model"]=os.environ.get("DEEPSEEK_MODEL","deepseek-flash") if a.live else None
    if rollout_sha is not None:
        r["rollout_manifest_sha256"]=rollout_sha
        r["source_revision"]=revision
    enc=json.dumps(r,ensure_ascii=False,indent=2)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(enc+"\n",encoding="utf-8")
    print(enc)
    if failures:
        raise SystemExit("Coworker quality gate failed: "+", ".join(r["gate_failures"]))

if __name__=="__main__": main()
