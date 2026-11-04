import assert from "node:assert/strict";
import test from "node:test";
import {
  cancelSpeechSynthesis,
  createBrowserSpeechRecognition,
  createSpeechUtterance,
  hasBrowserSpeechRecognition,
  hasBrowserSpeechSynthesis,
  resolveSpeechLanguage,
  speechRecognitionErrorMessage,
  type BrowserSpeechRecognition,
  type SpeechRecognitionHost,
  type SpeechRecognitionResultEvent,
  type SpeechSynthesisHost,
} from "./speech";

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

test("speech recognition prefers the standard API and emits only final transcript segments once", () => {
  const instances: FakeRecognition[] = [];
  class StandardRecognition extends FakeRecognition {
    constructor() { super(); instances.push(this); }
  }
  class WebkitRecognition extends FakeRecognition {
    constructor() { super(); instances.push(this); }
  }
  const host: SpeechRecognitionHost = {
    SpeechRecognition: StandardRecognition,
    webkitSpeechRecognition: WebkitRecognition,
  };
  const transcripts: string[] = [];
  const recognition = createBrowserSpeechRecognition(host, "bn-BD", {
    onTranscript: value => transcripts.push(value),
    onError: () => assert.fail("unexpected recognition error"),
    onEnd: () => undefined,
  });

  assert.ok(recognition);
  assert.equal(instances.length, 1);
  assert.equal(recognition.lang, "bn-BD");
  assert.equal(recognition.continuous, true);
  assert.equal(recognition.interimResults, true);
  assert.equal(recognition.maxAlternatives, 1);

  recognition.onresult?.({
    resultIndex: 0,
    results: [{ isFinal: false, 0: { transcript: "ami" } }],
  });
  assert.deepEqual(transcripts, []);

  recognition.onresult?.({
    resultIndex: 0,
    results: [{ isFinal: true, 0: { transcript: "আমি" } }],
  });
  recognition.onresult?.({
    resultIndex: 1,
    results: [
      { isFinal: true, 0: { transcript: "আমি" } },
      { isFinal: true, 0: { transcript: "ভালো আছি" } },
    ],
  });
  assert.deepEqual(transcripts, ["আমি", "ভালো আছি"]);
});

test("speech recognition falls back to the prefixed browser API and reports unsupported browsers", () => {
  const instances: FakeRecognition[] = [];
  const host: SpeechRecognitionHost = {
    webkitSpeechRecognition: class extends FakeRecognition {
      constructor() { super(); instances.push(this); }
    },
  };
  assert.equal(hasBrowserSpeechRecognition(host), true);
  const recognition = createBrowserSpeechRecognition(host, "en-US", {
    onTranscript: () => undefined, onError: () => undefined, onEnd: () => undefined,
  });
  assert.equal(recognition, instances[0]);
  assert.equal(hasBrowserSpeechRecognition({}), false);
  assert.equal(createBrowserSpeechRecognition(undefined, "en-US", {
    onTranscript: () => undefined, onError: () => undefined, onEnd: () => undefined,
  }), null);
});

test("speech recognition errors explain microphone and connectivity recovery", () => {
  assert.match(speechRecognitionErrorMessage("not-allowed"), /permission/i);
  assert.match(speechRecognitionErrorMessage("audio-capture"), /microphone/i);
  assert.match(speechRecognitionErrorMessage("no-speech"), /speech/i);
  assert.match(speechRecognitionErrorMessage("network"), /network/i);
  assert.match(speechRecognitionErrorMessage("unknown"), /typing/i);
});

test("speech language selection preserves the device locale or uses the selected language", () => {
  assert.equal(resolveSpeechLanguage("device", "bn-BD"), "bn-BD");
  assert.equal(resolveSpeechLanguage("device", ""), "en-US");
  assert.equal(resolveSpeechLanguage("bn-BD", "en-US"), "bn-BD");
  assert.equal(resolveSpeechLanguage("en-US", "bn-BD"), "en-US");
});

test("browser read-aloud starts a single utterance, replaces previous speech and can be cancelled", () => {
  const spoken: unknown[] = [];
  let cancelled = 0;
  class FakeUtterance {
    lang = "";
    text: string;
    onend: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(text = "") { this.text = text; }
  }
  const host = {
    SpeechSynthesisUtterance: FakeUtterance,
    speechSynthesis: {
      cancel() { cancelled += 1; },
      speak(utterance: FakeUtterance) { spoken.push(utterance); },
    },
  } as unknown as SpeechSynthesisHost;

  assert.equal(hasBrowserSpeechSynthesis(host), true);
  const utterance = createSpeechUtterance(host, "বাংলায় উত্তর", "bn-BD") as unknown as FakeUtterance;
  assert.ok(utterance);
  assert.equal(utterance.text, "বাংলায় উত্তর");
  assert.equal(utterance.lang, "bn-BD");
  assert.equal(spoken.length, 1);
  assert.equal(spoken[0], utterance);
  assert.equal(cancelled, 1);

  cancelSpeechSynthesis(host);
  assert.equal(cancelled, 2);
  assert.equal(createSpeechUtterance(host, "   ", "en-US"), null);
  assert.equal(hasBrowserSpeechSynthesis({}), false);
});
