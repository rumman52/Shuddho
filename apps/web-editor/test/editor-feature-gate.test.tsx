import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import Editor from "../../editor/src/App";

test("Editor remains usable while Coworker integration is disabled", () => {
  const html = renderToString(<Editor />);

  assert.match(html, /Multilingual Writing Studio/);
  assert.doesNotMatch(html, /Send to Coworker/);
  assert.doesNotMatch(html, /Open Coworker/);
  assert.doesNotMatch(html, /Recent coworker files/);
  assert.match(html, /href="\/workspaces"/);
  assert.match(html, /All workspaces/);
  assert.match(html, /href="\/workspaces"[^>]*target="_blank"/);
});
