import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create } from "react-test-renderer";
import CoworkerPreview from "../src/coworker/CoworkerPreview";

test("draft workspace edits and copies a brief without calling a backend or saving it", async () => {
  const previousNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const originalFetch = globalThis.fetch;
  let copied = "";
  globalThis.fetch = async () => { throw new Error("Preview must not request backend access"); };
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { clipboard: { writeText: async (value: string) => { copied = value; } } } });
  let tree: ReturnType<typeof create>;
  try {
    await act(async () => { tree = create(<CoworkerPreview />); });
    const copy = () => tree!.root.findAllByType("button").find(node => node.children.includes("Copy draft"))!;
    assert.equal(copy().props.disabled, true);
    const starter = tree!.root.findAllByType("button").find(node => node.children.includes("Plan a project"))!;
    await act(async () => { starter.props.onClick(); });
    assert.match(tree!.root.findByType("textarea").props.value, /Help me plan a project/);
    await act(async () => { tree!.root.findByType("textarea").props.onChange({ target: { value: "আমার গবেষণার পরিকল্পনা" } }); });
    await act(async () => { await copy().props.onClick(); });
    assert.equal(copied, "আমার গবেষণার পরিকল্পনা");
    assert.match(JSON.stringify(tree!.toJSON()), /Draft copied/);
    Object.defineProperty(globalThis, "navigator", { configurable: true, value: {} });
    await act(async () => { await copy().props.onClick(); });
    assert.match(JSON.stringify(tree!.toJSON()), /Copy could not finish/);
    await act(async () => { tree!.unmount(); });
    await act(async () => { tree = create(<CoworkerPreview />); });
    assert.equal(tree!.root.findByType("textarea").props.value, "");
  } finally {
    act(() => tree?.unmount());
    globalThis.fetch = originalFetch;
    if (previousNavigator) Object.defineProperty(globalThis, "navigator", previousNavigator);
    else Reflect.deleteProperty(globalThis, "navigator");
  }
});
