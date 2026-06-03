#!/usr/bin/env node
const backend = process.env.SHUDDHO_PRODUCTION_API_URL ?? "https://shuddho-api.onrender.com";
const origin = process.env.SHUDDHO_PRODUCTION_WEB_ORIGIN ?? "https://shuddho-web-editor.vercel.app";
const sampleText = "গত মাসে আমি আর আমার ভাই চিড়িয়াখানায় যাবে। সেখানে অনেকগুলো সুন্দর পাখিরা ছিল।";

async function printJson(label, response) {
  const text = await response.text();
  console.log(`\n## ${label}`);
  console.log(`${response.status} ${response.statusText}`);
  try {
    console.log(JSON.stringify(JSON.parse(text), null, 2));
  } catch {
    console.log(text);
  }
}

await printJson("health", await fetch(`${backend}/health`));
await printJson("health/deep", await fetch(`${backend}/health/deep`));
await printJson("preflight /api/check", await fetch(`${backend}/api/check`, {
  method: "OPTIONS",
  headers: {
    Origin: origin,
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type",
  },
}));
await printJson("AI /api/check", await fetch(`${backend}/api/check`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Origin: origin,
  },
  body: JSON.stringify({
    text: sampleText,
    language: "bn",
    options: {
      includeLLM: true,
      asyncLLM: false,
      llmMode: "review_candidates",
      mode: "smart",
    },
  }),
}));
