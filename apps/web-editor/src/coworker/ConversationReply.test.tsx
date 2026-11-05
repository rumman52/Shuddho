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


test("a streaming reply renders partial Markdown without completion-only actions", async () => {
  const restore = installWindow({});
  let tree: ReactTestRenderer | undefined;
  try {
    await act(async () => {
      tree = create(<ConversationReply
        reply={{ state: "generating", text: "Partial **answer**", context_truncated: false }}
        pending={true} retry={() => undefined} disabled={false}
      />);
    });
    assert.ok(tree!.root.findAllByProps({ role: "status" }).some(node =>
      node.children.join("").includes("Rukh is replying"),
    ));
    assert.ok(tree!.root.findAllByType("strong").some(node => node.children.join("") === "answer"));
    assert.equal(tree!.root.findAllByProps({ "aria-label": "Copy AI reply" }).length, 0);
    assert.equal(tree!.root.findAllByProps({ "aria-label": "Read AI reply aloud" }).length, 0);
  } finally {
    if (tree) await act(async () => { tree!.unmount(); });
    restore();
  }
});


test("a disconnected reply keeps visible partial text and offers recovery without a busy spinner", async () => {
  let tree: ReactTestRenderer | undefined;
  try {
    await act(async () => { tree = create(<ConversationReply
      reply={{ state: "generating", text: "Partial **answer**", context_truncated: false }}
      pending={false} error="Connection lost. Check the saved reply."
      retry={() => undefined} disabled={false} />); });
    assert.ok(tree!.root.findAllByType("strong").some(node => node.children.join("") === "answer"));
    assert.equal(tree!.root.findByProps({ "aria-label": "Rukh AI reply" }).props["aria-busy"], false);
    assert.equal(tree!.root.findByProps({ "aria-label": "Retry AI reply" }).props.disabled, false);
  } finally { if (tree) await act(async () => { tree!.unmount(); }); }
});


test("a generating reply exposes an explicit stop action", async () => {
  let stopped = 0;
  let tree: ReactTestRenderer | undefined;
  try {
    await act(async () => { tree = create(<ConversationReply
      reply={{ state: "generating", text: "Partial answer", request_key: "attempt-key-123", attempt: 1 }}
      pending={true} retry={() => undefined} disabled={false} onStop={() => { stopped += 1; }}
    />); });
    await act(async () => tree!.root.findByProps({ "aria-label": "Stop AI reply" }).props.onClick());
    assert.equal(stopped, 1);
  } finally { if (tree) await act(async () => { tree!.unmount(); }); }
});

test("failed, interrupted and cancelled replies expose a retry action", async () => {
  for (const state of ["failed", "interrupted", "cancelled"] as const) {
    let retried = 0;
    let tree: ReactTestRenderer | undefined;
    try {
      await act(async () => { tree = create(<ConversationReply
        reply={{ state, text: "", error: state === "cancelled" ? "You stopped this reply." : "The reply failed.", attempt: 1, request_key: "attempt-key-123" }}
        pending={false} retry={() => { retried += 1; }} disabled={false}
      />); });
      await act(async () => tree!.root.findByProps({ "aria-label": "Retry AI reply" }).props.onClick());
      assert.equal(retried, 1, `${state} reply should be retryable`);
      if (state === "cancelled") assert.ok(tree!.root.findAllByProps({ role: "status" }).some(node => node.children.join("").includes("Reply stopped")));
    } finally { if (tree) await act(async () => { tree!.unmount(); }); }
  }
});
