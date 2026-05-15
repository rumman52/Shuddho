import assert from "node:assert/strict";
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
