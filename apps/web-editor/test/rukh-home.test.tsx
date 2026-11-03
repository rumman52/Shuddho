import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import RukhHome from "../src/RukhHome";

test("Rukh home presents both products and keeps AI Coworker unavailable while preview is off", () => {
  const html = renderToString(<RukhHome coworkerEnabled={false} />);

  assert.match(html, /Rukh AI/);
  assert.match(html, /AI Coworker/);
  assert.match(html, /Web Editor/);
  assert.match(html, /Private preview/);
  assert.match(html, /href="\/editor"/);
  assert.doesNotMatch(html, /href="\/coworker"/);
  assert.match(html, /disabled=""/);
});

test("Rukh home exposes AI Coworker only when its release flag is enabled", () => {
  const html = renderToString(<RukhHome coworkerEnabled={true} />);

  assert.match(html, /href="\/coworker"/);
  assert.match(html, /Open AI Coworker/);
  assert.doesNotMatch(html, /Private preview/);
});
