import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import RukhHome from "../src/RukhHome";

test("Rukh home presents Coworker, Fly, Web Editor and Writing Assistant as distinct workspaces", () => {
  const html = renderToString(<RukhHome coworkerEnabled={false} />);

  assert.match(html, /Rukh AI/);
  assert.match(html, /AI Coworker/);
  assert.match(html, /Fly/);
  assert.match(html, /Web Editor/);
  assert.match(html, /Writing Assistant/);
  assert.match(html, /Open AI Coworker/);
  assert.match(html, /href="\/editor"/);
  assert.match(html, /href="\/fly"/);
  assert.match(html, /href="\/writing"/);
  assert.match(html, /href="\/coworker"/);
  assert.match(html, /Account required/);
});

test("Rukh home exposes AI Coworker only when its release flag is enabled", () => {
  const html = renderToString(<RukhHome coworkerEnabled={true} />);

  assert.match(html, /href="\/coworker"/);
  assert.match(html, /Open AI Coworker/);
  assert.doesNotMatch(html, /Private preview/);
});
