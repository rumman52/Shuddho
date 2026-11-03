import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import CoworkerApp from "../../coworker/src/App";

test("Coworker navigation keeps the workspace directory and Web Editor reachable", () => {
  const html = renderToString(<CoworkerApp />);

  assert.match(html, /href="\/workspaces"/);
  assert.match(html, /All workspaces/);
  assert.match(html, /href="\/workspaces"[^>]*target="_blank"/);
  assert.match(html, /href="\/editor"/);
  assert.match(html, /Web Editor/);
  assert.match(html, /AI Coworker/);
});

test("Coworker sign-in explains the broader persistent-work workspace", () => {
  const html = renderToString(<CoworkerApp />);

  assert.match(html, /A coworker for complex work/);
  assert.match(html, /conversations, source material and Agent activity/);
  assert.match(html, /approve external actions/);
  assert.match(html, /Sign-in is not configured for this environment/);
});
