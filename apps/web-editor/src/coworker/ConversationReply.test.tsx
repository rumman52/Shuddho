import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import ConversationReply from "./ConversationReply";

function installWindow(value: unknown) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", { configurable: true, writable: true, value });
  return () => {
    if (previous) Object.defineProperty(globalThis, "window", previous);
    else Reflect.deleteProperty(globalThis, "window");
  };
}

test("a completed reply can be read aloud and stopped with browser speech synthesis", async () => {
  const spoken: { text: string; lang: string; onend: (() => void) | null }[] = [];
  let cancelCount = 0;
  class FakeUtterance {
    lang = "";
    onend: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(public text = "") {}
  }
  const restore = installWindow({
    SpeechSynthesisUtterance: FakeUtterance,
    speechSynthesis: {
      cancel() { cancelCount += 1; },
      speak(utterance: FakeUtterance) { spoken.push(utterance); },
    },
  });
  let tree: ReactTestRenderer | undefined;
  try {
    await act(async () => {
      tree = create(<ConversationReply
        reply={{ state: "completed", text: "বাংলায় উত্তর", context_truncated: false }}
        pending={false}
        retry={() => undefined}
        disabled={false}
      />);
    });
    await act(async () => tree!.root.findByProps({ "aria-label": "Read AI reply aloud" }).props.onClick());
    assert.equal(spoken.length, 1);
    assert.equal(spoken[0].text, "বাংলায় উত্তর");
    assert.equal(spoken[0].lang, "bn-BD");

    await act(async () => tree!.root.findByProps({ "aria-label": "Stop reading aloud" }).props.onClick());
    assert.ok(cancelCount >= 2);
    assert.ok(tree!.root.findAllByProps({ role: "status" }).some(node => node.children.join("").includes("stopped")));
  } finally {
    if (tree) await act(async () => { tree!.unmount(); });
    restore();
  }
});

test("unmounting a reply while reading cancels browser speech synthesis", async () => {
  let cancelCount = 0;
  const spoken: unknown[] = [];
  class FakeUtterance {
    lang = "";
    onend: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(public text = "") {}
  }
  const restore = installWindow({
    SpeechSynthesisUtterance: FakeUtterance,
    speechSynthesis: {
      cancel() { cancelCount += 1; },
      speak(utterance: FakeUtterance) { spoken.push(utterance); },
    },
  });
  let tree: ReactTestRenderer | undefined;
  try {
    await act(async () => {
      tree = create(<ConversationReply
        reply={{ state: "completed", text: "Read this answer", context_truncated: false }}
        pending={false} retry={() => undefined} disabled={false}
      />);
    });
    await act(async () => tree!.root.findByProps({ "aria-label": "Read AI reply aloud" }).props.onClick());
    assert.equal(spoken.length, 1);
    await act(async () => { tree!.unmount(); });
    tree = undefined;
    assert.ok(cancelCount >= 2);
  } finally {
    tree?.unmount();
    restore();
  }
});
