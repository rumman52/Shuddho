import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";
import FlyWorkspace, { normalizeStoredDraft } from "../src/coworker/FlyWorkspace";
import type { CoworkerClient } from "../src/coworker/client";

test("Fly renders an agent-first Codex-style workspace with explicit runtime boundaries", () => {
  const html = renderToString(<FlyWorkspace client={{} as CoworkerClient} accountId="test-account" />);
  assert.match(html, /Fly code workspace/);
  assert.match(html, /Fly file explorer/);
  assert.match(html, /Recent coding tasks/);
  assert.match(html, /What are we building/);
  assert.match(html, /Code &amp; changes/);
  assert.match(html, /Code editor/);
  assert.match(html, /Run Python 3\.11/);
  assert.match(html, /Ask Rukh to review/);
  assert.match(html, /Terminal output/);
  assert.match(html, /Rukh Agent/);
  assert.match(html, /Ask Rukh about this code/);
  assert.match(html, /Git clone\/push/);
  assert.match(html, /Test runner not connected/);
});


test("Fly restores only valid source files and falls back to a valid active file", () => {
  const draft = normalizeStoredDraft({
    activeId: "missing-file",
    files: [
      {
        id: "valid-html",
        name: "../index.html",
        language: "html",
        content: "<h1>Saved source</h1>",
        saved: { documentId: "doc-1", versionId: "version-1", sha256: "abc123", filename: "index.html" },
      },
      { id: "invalid-language", name: "bad.exe", language: "exe", content: "not executable" },
      { id: "oversized", name: "large.txt", language: "text", content: "x".repeat(512 * 1024 + 1) },
    ],
  });

  assert.equal(draft.files.length, 1);
  assert.equal(draft.files[0].id, "valid-html");
  assert.equal(draft.files[0].name, "index.html");
  assert.equal(draft.files[0].saved?.documentId, "doc-1");
  assert.equal(draft.activeId, "valid-html");
});

test("Fly malformed stored drafts safely restore the starter file", () => {
  const draft = normalizeStoredDraft({ files: "not-an-array", activeId: "missing" });
  assert.equal(draft.files.length, 1);
  assert.equal(draft.files[0].id, "fly-main");
  assert.equal(draft.files[0].name, "main.py");
  assert.equal(draft.activeId, "fly-main");
});


test("Fly local diff reports added and removed lines without claiming repository history", () => {
  const { buildLineDiff } = require("../src/coworker/FlyWorkspace");
  assert.deepEqual(buildLineDiff("before", "after"), [
    { kind: "remove", text: "before" },
    { kind: "add", text: "after" },
  ]);
  assert.deepEqual(buildLineDiff("same\nline", "same\nline"), []);
  assert.equal(buildLineDiff(Array(301).fill("x").join("\n"), "small"), null);
});
