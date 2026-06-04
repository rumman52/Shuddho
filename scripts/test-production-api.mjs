#!/usr/bin/env node
const backend = (process.env.SHUDDHO_PRODUCTION_API_URL ?? "https://shuddho-api.onrender.com").replace(/\/$/, "");
const origin = process.env.SHUDDHO_PRODUCTION_WEB_ORIGIN ?? "https://shuddho-web-editor.vercel.app";
const sampleText = "গত মাসে আমি আর আমার ভাই চিড়িয়াখানায় যাবে। সেখানে অনেকগুলো সুন্দর পাখিরা ছিল।";

async function request(label, path, init) {
  const url = `${backend}${path}`;
  try {
    const response = await fetch(url, init);
    await printResponse(label, url, response);
    return response;
  } catch (error) {
    console.log(`\n## ${label}`);
    console.log(url);
    console.log(`REQUEST_FAILED ${error instanceof Error ? error.message : String(error)}`);
    return null;
  }
}

async function printResponse(label, url, response) {
  const text = await response.text();
  console.log(`\n## ${label}`);
  console.log(url);
  console.log(`${response.status} ${response.statusText}`);
  console.log(`access-control-allow-origin: ${response.headers.get("access-control-allow-origin") ?? "<missing>"}`);
  let json = null;
  try {
    json = JSON.parse(text);
    console.log(JSON.stringify(json, null, 2));
  } catch {
    console.log(text || "<empty body>");
  }
  if (json && pathLooksLikeCheck(label)) {
    printCheckSummary(json);
  }
}

function pathLooksLikeCheck(label) {
  return label.includes("/api/check");
}

function printCheckSummary(json) {
  const diagnostics = json.diagnostics ?? {};
  const llm = json.llm ?? diagnostics.llm ?? {};
  console.log("-- check summary --");
  console.log(`suggestions=${Array.isArray(json.suggestions) ? json.suggestions.length : "unknown"}`);
  console.log(`llm_status=${json.llm_status ?? llm.status ?? "missing"}`);
  console.log(`llm_provider=${json.llm_provider ?? llm.provider ?? "missing"}`);
  console.log(`llm_model=${json.llm_model ?? llm.model ?? "missing"}`);
  console.log(`llm_attempted=${json.llm_attempted ?? llm.attempted ?? "missing"}`);
  console.log(`llm_used=${json.llm_used ?? llm.used ?? "missing"}`);
  console.log(`warnings=${JSON.stringify(json.warnings ?? llm.warnings ?? [])}`);
  console.log(`diagnostics.llm=${JSON.stringify(diagnostics.llm ?? llm)}`);
}

console.log(`Backend: ${backend}`);
console.log(`Origin: ${origin}`);

await request("GET /health", "/health", { headers: { Accept: "application/json", Origin: origin } });
await request("GET /health/deep", "/health/deep", { headers: { Accept: "application/json", Origin: origin } });
await request("GET /api/llm/debug", "/api/llm/debug", { headers: { Accept: "application/json", Origin: origin } });
await request("OPTIONS /api/check", "/api/check", {
  method: "OPTIONS",
  headers: {
    Origin: origin,
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type",
  },
});

const baseCheckPayload = { text: sampleText, language: "bn" };
await request("POST /api/check includeLLM=false", "/api/check", {
  method: "POST",
  headers: { "Content-Type": "application/json", Origin: origin },
  body: JSON.stringify({ ...baseCheckPayload, options: { includeLLM: false, mode: "fast" } }),
});
await request("POST /api/check includeLLM=true", "/api/check", {
  method: "POST",
  headers: { "Content-Type": "application/json", Origin: origin },
  body: JSON.stringify({
    ...baseCheckPayload,
    options: {
      includeLLM: true,
      asyncLLM: false,
      llmMode: "review_candidates",
      mode: "smart",
    },
  }),
});
