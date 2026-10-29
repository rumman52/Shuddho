#!/usr/bin/env node
/**
 * Explicitly gated Shuddho production API diagnostic. Safe default: 2 GETs.
 * This tool does NOT qualify a release, a model, or a provider transaction.
 * Do not print entire API payloads: responses may carry model/debug material.
 */
const ORIGINS = new Set([
  "https://shuddho-api.onrender.com",
  "https://shuddho-api-staging.onrender.com",
]);
const SAMPLE_TEXT = "গত মাসে আমি আর আমার ভাই চিড়িয়াখানায় যাবে। সেখানে অনেকগুলো সুন্দর পাখিরা ছিল।";
const SHA = /^[a-f\d]{40}$/i;
const DEGRADED_ANALYSIS_PROFILES = new Set([
  "backend_without_detector",
  "backend_without_corrector",
  "backend_rules_and_spell_only",
  "frontend_local_fallback",
]);
const FLAGS = new Set([
  "--inspect-components",
  "--allow-synthetic-analysis",
  "--allow-provider-inference",
]);

function configuration() {
  const args = process.argv.slice(2);
  if (args.length === 1 && args[0] === "--help") {
    console.log("Read-only by default: GET /health and GET /version. Options: --inspect-components, --allow-synthetic-analysis, --allow-provider-inference (requires both analysis flag and SHUDDHO_PROVIDER_SMOKE_AUTHORIZED=YES). No arbitrary API targets.");
    process.exit(0);
  }
  if (args.some(arg => !FLAGS.has(arg)) || new Set(args).size !== args.length) {
    throw new Error("unknown or duplicate argument; use --help");
  }
  const selected = new Set(args);
  const raw = process.env.SHUDDHO_PRODUCTION_API_URL ?? "https://shuddho-api.onrender.com";
  let parsed;
  try { parsed = new URL(raw); } catch { throw new Error("invalid API origin"); }
  if (!ORIGINS.has(parsed.origin) || parsed.username || parsed.password ||
      parsed.search || parsed.hash || parsed.pathname !== "/" ||
      ![parsed.origin, parsed.origin + "/"].includes(raw)) {
    throw new Error("API origin is not a pinned Shuddho HTTPS service");
  }
  const inferred = selected.has("--allow-provider-inference");
  const synthetic = selected.has("--allow-synthetic-analysis");
  if (inferred && (!synthetic || process.env.SHUDDHO_PROVIDER_SMOKE_AUTHORIZED !== "YES")) {
    throw new Error("provider inference needs both explicit analysis opt-in and SHUDDHO_PROVIDER_SMOKE_AUTHORIZED=YES");
  }
  const origin = process.env.SHUDDHO_PRODUCTION_WEB_ORIGIN ?? "https://shuddho-web-editor.vercel.app";
  let originUrl;
  try { originUrl = new URL(origin); } catch { throw new Error("invalid browser origin"); }
  if (originUrl.protocol !== "https:" || originUrl.username || originUrl.password ||
      originUrl.pathname !== "/" || originUrl.search || originUrl.hash ||
      ![originUrl.origin, originUrl.origin + "/"].includes(origin)) {
    throw new Error("browser origin must be an HTTPS origin without path, credentials, or query");
  }
  return { backend: parsed.origin, origin: originUrl.origin, selected, inferred, synthetic };
}

async function request({backend, origin}, method, route, payload) {
  const options = {
    method,
    headers: { Accept: "application/json", Origin: origin },
    redirect: "manual",
    signal: AbortSignal.timeout(10000),
  };
  if (payload !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }
  if (method === "OPTIONS") {
    options.headers["Access-Control-Request-Method"] = "POST";
    options.headers["Access-Control-Request-Headers"] = "content-type";
  }
  let response;
  try { response = await fetch(backend + route, options); }
  catch { throw new Error(method + " " + route + " network request failed"); }
  if (response.status < 200 || response.status >= 300) {
    throw new Error(method + " " + route + " returned HTTP " + response.status + "; expected success (no redirect following)");
  }
  console.log(method + " " + route + ": HTTP " + response.status);
  if (method === "OPTIONS") return {};
  if (!(response.headers.get("content-type") ?? "").toLowerCase().includes("application/json")) {
    throw new Error(method + " " + route + " returned an unexpected content type");
  }
  let json;
  try { json = await response.json(); }
  catch { throw new Error(method + " " + route + " returned invalid JSON"); }
  if (!json || typeof json !== "object" || Array.isArray(json)) {
    throw new Error(method + " " + route + " JSON must be an object");
  }
  return json;
}

async function main() {
  const config = configuration();
  const health = await request(config, "GET", "/health");
  if (health.ok !== true || health.service !== "shuddho-api" || health.status !== "ok" ||
      !Array.isArray(health.degraded_reasons) || health.degraded_reasons.some(x => typeof x !== "string" || !x)) {
    throw new Error("/health failed the Shuddho liveness contract");
  }
  const version = await request(config, "GET", "/version");
  if (typeof version.commit !== "string" || !SHA.test(version.commit)) {
    throw new Error("/version does not expose a full source revision");
  }
  if (config.selected.has("--inspect-components")) {
    await request(config, "GET", "/health/deep");
    await request(config, "GET", "/api/llm/debug");
  }
  if (config.synthetic) {
    await request(config, "OPTIONS", "/api/check");
    const payload = { text: SAMPLE_TEXT, language: "bn" };
    const deterministic = await request(config, "POST", "/api/check", {
      ...payload, options: { includeLLM: false, mode: "fast" },
    });
    if (!Array.isArray(deterministic.suggestions)) throw new Error("deterministic analysis response is malformed");
    if (config.inferred) {
      const inferred = await request(config, "POST", "/api/check", {
        ...payload,
        options: { includeLLM: true, asyncLLM: false, llmMode: "review_candidates", mode: "smart" },
      });
      if (!Array.isArray(inferred.suggestions)) throw new Error("provider analysis response is malformed");
    }
  }
  console.log(JSON.stringify({
    status: "passed",
    source_revision: version.commit.toLowerCase(),
    analysis_status: health.degraded_reasons.length || DEGRADED_ANALYSIS_PROFILES.has(health.analysis_profile)
      ? "degraded"
      : health.analysis_profile === "full_local" ? "ready" : "unverified",
    scope: config.inferred ? "authorized_synthetic_provider_probe" : config.synthetic ? "authorized_deterministic_synthetic_probe" : "read_only_liveness_and_revision",
    release_qualified: false,
  }));
}

try { await main(); }
catch (error) {
  // Never echo a response body, user text, bearer token or raw network error.
  console.error("Shuddho API smoke BLOCKED: " + (error instanceof Error ? error.message : "unexpected failure"));
  process.exitCode = 1;
}
