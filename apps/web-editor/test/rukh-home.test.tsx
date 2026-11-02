import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import RukhHome from "../src/RukhHome";

test("Rukh home presents both products and keeps Co-workers unavailable while preview is off", () => {
  const html = renderToString(<RukhHome coworkerEnabled={false} />);

  assert.match(html, /Rukh AI/);
  assert.match(html, /Co-workers/);
  assert.match(html, /Web Editor/);
  assert.match(html, /Private preview/);
  assert.match(html, /href="\/editor"/);
  assert.doesNotMatch(html, /href="\/coworker"/);
  assert.match(html, /disabled=""/);
});

test("Rukh home exposes Co-workers only when its release flag is enabled", () => {
  const html = renderToString(<RukhHome coworkerEnabled={true} />);

  assert.match(html, /href="\/coworker"/);
  assert.match(html, /Open Co-workers/);
  assert.doesNotMatch(html, /Private preview/);
});
