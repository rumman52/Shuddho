import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import VoiceDictation from "./VoiceDictation";
import type { BrowserSpeechRecognition, SpeechRecognitionResultEvent } from "./speech";

class FakeRecognition implements BrowserSpeechRecognition {
  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 0;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null = null;
  onerror: ((event: { error?: string }) => void) | null = null;
  onend: (() => void) | null = null;
  started = false;
  stopped = false;
  aborted = false;
  start() { this.started = true; }
  stop() { this.stopped = true; }
  abort() { this.aborted = true; }
}

function installWindow(value: unknown) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", { configurable: true, writable: true, value });
  return () => {
    if (previous) Object.defineProperty(globalThis, "window", previous);
    else Reflect.deleteProperty(globalThis, "window");
  };
}

test("dictation appends final Bangla speech to the draft and stops on explicit request", async () => {
  let recognition: FakeRecognition | undefined;
  class MockRecognition extends FakeRecognition {
    constructor() { super(); recognition = this; }
  }
  const restore = installWindow({ SpeechRecognition: MockRecognition });
  const changes: string[] = [];
  const listening: boolean[] = [];
  let tree: ReactTestRenderer | undefined;
  try {
    await act(async () => {
      tree = create(<VoiceDictation
        draft="Existing note"
        onDraftChange={value => changes.push(value)}
        onListeningChange={value => listening.push(value)}
        disabled={false}
      />);
    });
    await act(async () => tree!.root.findByProps({ "aria-label": "Dictation language" }).props.onChange({ target: { value: "bn-BD" } }));
    await act(async () => tree!.root.findByProps({ "aria-label": "Start voice dictation" }).props.onClick());
    assert.ok(recognition);
    assert.equal(recognition.lang, "bn-BD");
    assert.equal(recognition.started, true);

    await act(async () => recognition!.onresult?.({
      resultIndex: 0, results: [{ isFinal: false, 0: { transcript: "hello" } }],
    }));
    assert.deepEqual(changes, []);

    await act(async () => recognition!.onresult?.({
      resultIndex: 0, results: [{ isFinal: true, 0: { transcript: "হ্যালো" } }],
    }));
    await act(async () => recognition!.onresult?.({
      resultIndex: 0, results: [{ isFinal: true, 0: { transcript: "হ্যালো" } }],
    }));
    assert.deepEqual(changes, ["Existing note হ্যালো"]);

    await act(async () => tree!.root.findByProps({ "aria-label": "Stop voice dictation" }).props.onClick());
    assert.equal(recognition.stopped, true);
    assert.equal(listening[listening.length - 1], false);
  } finally {
    tree?.unmount();
    restore();
  }
});

test("unsupported browsers expose a disabled dictation control and a typing fallback", async () => {
  const restore = installWindow({});
  let tree: ReactTestRenderer | undefined;
  try {
    await act(async () => {
      tree = create(<VoiceDictation draft="" onDraftChange={() => undefined} disabled={false} />);
    });
    assert.equal(tree!.root.findByProps({ "aria-label": "Start voice dictation" }).props.disabled, true);
    assert.ok(tree!.root.findAllByProps({ role: "status" }).some(node =>
      node.children.join("").includes("not supported"),
    ));
  } finally {
    tree?.unmount();
    restore();
  }
});
