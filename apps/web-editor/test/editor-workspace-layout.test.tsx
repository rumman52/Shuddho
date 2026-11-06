import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import Editor from "../../editor/src/App";

test("Writing Assistant keeps Coworker navigation and presents recent files before the writing canvas", () => {
  const html = renderToString(<Editor />);

  assert.match(html, /href="\/coworker"/);
  assert.match(html, /AI Coworker/);
  assert.match(html, /Recent files/);
  assert.match(html, /aria-label="Writing editor"/);

  const libraryIndex = html.indexOf('class="rukh-editor-library"');
  const canvasIndex = html.indexOf('class="rukh-editor-canvas"');
  assert.ok(libraryIndex >= 0, "the recent-files workspace should render when Coworker is enabled");
  assert.ok(canvasIndex >= 0, "the writing canvas should render");
  assert.ok(libraryIndex < canvasIndex, "recent files should be the left navigation region");
});
