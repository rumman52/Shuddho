import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const dir = mkdtempSync(path.join(os.tmpdir(), "shuddho-prod-api-test-"));
const preload = path.join(dir, "mock-fetch.mjs");
writeFileSync(preload, [
  'globalThis.fetch = async (url, options = {}) => {',
  ' const method = options.method ?? "GET";',
  ' console.log("SMOKE_REQUEST " + JSON.stringify({url:String(url),method,redirect:options.redirect,body:options.body ?? null}));',
  ' const route = new URL(url).pathname;',
  ' if (process.env.MOCK_THROW_SECRET === "1") throw new Error("api-key=DO_NOT_ECHO_IN_DIAGNOSTIC");',
  ' const status = process.env.MOCK_FAIL_VERSION === "1" && route === "/version" ? 503 : process.env.MOCK_REDIRECT === "1" && route === "/health" ? 302 : 200;',
  ' const data = route === "/health" ? {ok:process.env.MOCK_BAD_HEALTH !== "1",service:"shuddho-api",status:"ok",degraded_reasons:[],secret:"DO_NOT_ECHO_API_PAYLOAD"} : route === "/version" ? {commit:process.env.MOCK_BAD_SHA === "1" ? "unknown" : "a".repeat(40)} : {diagnostics:{llm:{attempted:false}},suggestions:[]};',
  ' return new Response(JSON.stringify(data),{status,headers:{"content-type":"application/json"}});',
  '};',
].join("\n"));
process.on("exit", () => rmSync(dir, { recursive: true, force: true }));
const script = fileURLToPath(new URL("./test-production-api.mjs", import.meta.url));
function run(args = [], env = {}) {
  const clean = { ...process.env };
  delete clean.SHUDDHO_PRODUCTION_API_URL;
  delete clean.SHUDDHO_PRODUCTION_WEB_ORIGIN;
  delete clean.SHUDDHO_PROVIDER_SMOKE_AUTHORIZED;
  const p = spawnSync(process.execPath, ["--import", preload, script, ...args], {
    env: { ...clean, ...env }, encoding: "utf8", timeout: 3000,
  });
  const records = (p.stdout ?? "").split("\n").filter(x => x.startsWith("SMOKE_REQUEST ")).map(x => JSON.parse(x.slice(14)));
  return { status: p.status, records, stdout:p.stdout ?? "", stderr:p.stderr ?? "" };
}

const routes = p => p.records.map(x => [x.method, new URL(x.url).pathname]);

test("default is two read-only health/version GETs with redirects disabled", () => {
  const p = run();
  assert.equal(p.status, 0, p.stderr);
  assert.deepEqual(routes(p), [["GET","/health"],["GET","/version"]]);
  assert.ok(p.records.every(x=>x.url.startsWith("https://shuddho-api.onrender.com/") && x.redirect === "manual"));
});
test("component inspection adds only safe GETs", () => {
  const p=run(["--inspect-components"]);
  assert.equal(p.status,0,p.stderr);
  assert.deepEqual(routes(p), [["GET","/health"],["GET","/version"],["GET","/health/deep"],["GET","/api/llm/debug"]]);
});
test("synthetic opt-in sends exactly one POST with includeLLM=false", () => {
  const p=run(["--allow-synthetic-analysis"]);
  assert.equal(p.status,0,p.stderr);
  const posts=p.records.filter(x=>x.method==="POST");
  assert.equal(posts.length,1);
  assert.equal(JSON.parse(posts[0].body).options.includeLLM,false);
});
test("provider mode needs an independent opt-in environment gate", () => {
  const p=run(["--allow-synthetic-analysis","--allow-provider-inference"]);
  assert.notEqual(p.status,0);
  assert.equal(p.records.length,0);
});
test("provider mode sends one extra synthetic request only when doubly authorized", () => {
  const p=run(["--allow-synthetic-analysis","--allow-provider-inference"],{SHUDDHO_PROVIDER_SMOKE_AUTHORIZED:"YES"});
  assert.equal(p.status,0,p.stderr);
  assert.deepEqual(p.records.filter(x=>x.method==="POST").map(x=>JSON.parse(x.body).options.includeLLM),[false,true]);
});
test("external and ambiguous targets fail before any request", () => {
  for(const url of ["https://example.com","http://shuddho-api.onrender.com","https://shuddho-api.onrender.com.evil.tld","https://shuddho-api.onrender.com/admin","https://shuddho-api.onrender.com?token=foo","https://user:pass@shuddho-api.onrender.com"]){
    const p=run([],{SHUDDHO_PRODUCTION_API_URL:url});
    assert.notEqual(p.status,0,url);assert.equal(p.records.length,0,url);
  }
});
test("pinned staging is allowed read-only", () => {
  const p=run([],{SHUDDHO_PRODUCTION_API_URL:"https://shuddho-api-staging.onrender.com"});
  assert.equal(p.status,0,p.stderr);
  assert.ok(p.records.every(x=>x.url.startsWith("https://shuddho-api-staging.onrender.com/") && x.method==="GET"));
});
test("unknown argument blocks before network",()=>{
  const p=run(["--force-everything"]);assert.notEqual(p.status,0);assert.equal(p.records.length,0);
});
test("upstream HTTP error causes nonzero exit",()=>{
  const p=run([],{MOCK_FAIL_VERSION:"1"});assert.notEqual(p.status,0);assert.deepEqual(routes(p),[["GET","/health"],["GET","/version"]]);
});
test("provider authorization alone leaves default read-only",()=>{
  const p=run([],{SHUDDHO_PROVIDER_SMOKE_AUTHORIZED:"YES"});assert.equal(p.status,0,p.stderr);assert.ok(p.records.every(x=>x.method==="GET"));
});
test("bad liveness prevents even the version call",()=>{
  const p=run([],{MOCK_BAD_HEALTH:"1"});assert.notEqual(p.status,0);assert.deepEqual(routes(p),[["GET","/health"]]);
});
test("unknown deployed revision fails closed",()=>{
  const p=run([],{MOCK_BAD_SHA:"1"});assert.notEqual(p.status,0);assert.deepEqual(routes(p),[["GET","/health"],["GET","/version"]]);
});
test("redirect cannot trigger another request",()=>{
  const p=run([],{MOCK_REDIRECT:"1"});assert.notEqual(p.status,0);assert.deepEqual(routes(p),[["GET","/health"]]);assert.equal(p.records[0].redirect,"manual");
});
test("live responses and network error details are not printed",()=>{
  const p=run();assert.equal(p.status,0,p.stderr);assert.ok(!p.stdout.includes("DO_NOT_ECHO_API_PAYLOAD"));
  const failed=run([],{MOCK_THROW_SECRET:"1"});assert.notEqual(failed.status,0);assert.ok(!failed.stderr.includes("DO_NOT_ECHO_IN_DIAGNOSTIC"));
});
