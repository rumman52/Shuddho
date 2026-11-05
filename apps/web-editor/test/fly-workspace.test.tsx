import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import FlyWorkspace from "../src/coworker/FlyWorkspace";
import type { CoworkerClient } from "../src/coworker/client";

test("Fly renders a code workspace with clear execution and repository boundaries", () => {
  const html = renderToString(<FlyWorkspace client={{} as CoworkerClient} accountId="test-account" />);
  assert.match(html, /Fly code workspace/);
  assert.match(html, /Fly file explorer/);
  assert.match(html, /Code editor/);
  assert.match(html, /Run Python 3\.11/);
  assert.match(html, /Ask Rukh to review/);
  assert.match(html, /Terminal output/);
  assert.match(html, /Git clone\/push/);
});
