import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import ThemeToggle from "../src/components/ThemeToggle";
import { initializeRukhTheme, saveRukhTheme } from "../src/lib/theme";
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
  assert.match(html, /aria-label="Open navigation"/);
  assert.match(html, /aria-controls="rukh-conversation-list"/);
  assert.match(html, /href="\/fly"/);
  assert.match(html, /href="\/writing"/);
  assert.doesNotMatch(html, /href="\/editor"/);
  assert.match(html, /Projects/);
  assert.match(html, /aria-label="Open workspace context"/);
  assert.match(html, /aria-controls="rukh-context-panel"/);
});

test("Writing Assistant exposes a mobile Recent files drawer control", () => {
  const html = renderToString(<Editor />);
  assert.match(html, /aria-label="Open navigation"/);
  assert.match(html, /aria-controls="rukh-editor-library"/);
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(html, /Web Editor/);
});

test("theme preference is restored and persisted without requiring a backend", () => {
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const previousDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  const values = new Map<string, string>([["rukh-ai-theme:v1", "dark"]]);
  const meta = { content: "" };
  const fakeWindow = {
    localStorage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    },
    matchMedia: () => ({ matches: false }),
  };
  const fakeDocument = {
    documentElement: { dataset: {} as Record<string, string>, style: {} as { colorScheme?: string } },
    querySelector: () => meta,
  };

  Object.defineProperty(globalThis, "window", { configurable: true, value: fakeWindow });
  Object.defineProperty(globalThis, "document", { configurable: true, value: fakeDocument });
  try {
    assert.equal(initializeRukhTheme(), "dark");
    assert.equal(fakeDocument.documentElement.dataset.rukhTheme, "dark");
    assert.equal(fakeDocument.documentElement.style.colorScheme, "dark");
    saveRukhTheme("light");
    assert.equal(values.get("rukh-ai-theme:v1"), "light");
    assert.equal(fakeDocument.documentElement.dataset.rukhTheme, "light");
    assert.equal(meta.content, "#F7F7F5");
  } finally {
    if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
    else Reflect.deleteProperty(globalThis, "window");
    if (previousDocument) Object.defineProperty(globalThis, "document", previousDocument);
    else Reflect.deleteProperty(globalThis, "document");
  }
});
