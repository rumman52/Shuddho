import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import ThemeToggle from "../src/components/ThemeToggle";
import ConversationWorkspace from "../src/coworker/ConversationWorkspace";
import type { CoworkerClient } from "../src/coworker/client";
import Editor from "../../editor/src/App";

test("shared theme toggle exposes a labelled, keyboard-operable theme state", () => {
  const html = renderToString(<ThemeToggle />);
  assert.match(html, /aria-label="Switch to dark theme"/);
  assert.match(html, /aria-pressed="false"/);
});

test("Coworker exposes mobile controls for conversation history and Context", () => {
  const html = renderToString(
    <ConversationWorkspace client={{} as CoworkerClient} openAgent={() => undefined} />,
  );
  assert.match(html, /aria-label="Open conversations"/);
  assert.match(html, /aria-controls="rukh-conversation-list"/);
  assert.match(html, /aria-label="Open workspace context"/);
  assert.match(html, /aria-controls="rukh-context-panel"/);
});

test("Web Editor exposes a mobile Recent files drawer control", () => {
  const html = renderToString(<Editor />);
  assert.match(html, /aria-label="Open recent files"/);
  assert.match(html, /aria-controls="rukh-editor-library"/);
  assert.match(html, /aria-expanded="false"/);
});
