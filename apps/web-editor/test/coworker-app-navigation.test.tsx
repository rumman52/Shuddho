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

  assert.match(html, /Start with a question, a draft, or an idea/);
  assert.match(html, /Your first message opens a private conversation with Rukh/);
  assert.match(html, /Account access is not configured for this deployment/);
  assert.match(html, /Messages are saved only after you sign in and send them/);
});
