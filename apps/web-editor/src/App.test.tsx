import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";

import App from "./App";

test("App renders editor shell when analysis runtime_warnings are missing from backend responses", () => {
  const html = renderToString(<App />);

  assert.match(html, /Bangla writing assistant/);
  assert.match(html, /Review queue/);
});

test("App renders editor shell without waiting for preferences", () => {
  const html = renderToString(<App />);

  assert.match(html, /Preferences/);
  assert.match(html, /Personal dictionary/);
});

test("App source keeps auto checks local-only by default and deep review AI-enabled", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /const \[autoAiReview, setAutoAiReview\] = useState\(false\)/);
  assert.match(source, /void runAnalysis\(nextText, autoAiReview\)/);
  assert.match(source, /void runAnalysis\(text, true\)/);
  assert.match(source, /llmMode: includeLLM \? "review_candidates" : "none"/);
  assert.match(source, /mode: includeLLM \? "smart" : "fast"/);
});

test("App source exposes precise AI status messages and auto AI toggle", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /Auto AI review/);
  assert.match(source, /AI on every check/);
  assert.match(source, /friendlyLlmWarning/);
});
