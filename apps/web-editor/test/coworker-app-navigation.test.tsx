import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import CoworkerApp from "../../coworker/src/App";

test("Coworker navigation keeps the workspace directory, Fly and Writing Assistant reachable", () => {
  const html = renderToString(<CoworkerApp />);

  assert.match(html, /href="\/workspaces"/);
  assert.match(html, /All workspaces/);
  assert.match(html, /aria-label="Primary workspace navigation"/);
  assert.match(html, /href="\/fly"/);
  assert.match(html, /Fly/);
  assert.doesNotMatch(html, /href="\/editor"/);
  assert.doesNotMatch(html, /Web Editor/);
  assert.match(html, /href="\/writing"/);
  assert.match(html, /Writing Assistant/);
  assert.match(html, /AI Coworker/);
});

test("Coworker sign-in explains the broader persistent-work workspace", () => {
  const html = renderToString(<CoworkerApp />);

  assert.match(html, /What shall we/);
  assert.match(html, /Think it through. Make something. Move it forward/);
  assert.match(html, /Account access is not configured for this deployment/);
  assert.match(html, /Sign in to see your conversations/);
});
