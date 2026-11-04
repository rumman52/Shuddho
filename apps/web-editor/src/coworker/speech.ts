/** Browser-native voice helpers. Audio is neither uploaded nor persisted. */
export type SpeechLanguageChoice = "device" | "bn-BD" | "en-US";
export type SpeechRecognitionResult = { isFinal: boolean; 0?: { transcript?: string } };
export type SpeechRecognitionResultEvent = { resultIndex: number; results: ArrayLike<SpeechRecognitionResult> };

export interface BrowserSpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

export type SpeechRecognitionHost = {
  SpeechRecognition?: new () => BrowserSpeechRecognition;
  webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
};

export type SpeechRecognitionHandlers = {
  onTranscript(value: string): void;
  onError(message: string): void;
  onEnd(): void;
};

export type SpeechSynthesisHost = {
  speechSynthesis?: Pick<SpeechSynthesis, "speak" | "cancel">;
  SpeechSynthesisUtterance?: new (text?: string) => SpeechSynthesisUtterance;
};

export function hasBrowserSpeechRecognition(host?: SpeechRecognitionHost): boolean {
  return Boolean(host?.SpeechRecognition ?? host?.webkitSpeechRecognition);
}

export function createBrowserSpeechRecognition(
  host: SpeechRecognitionHost | undefined,
  language: string,
  handlers: SpeechRecognitionHandlers,
): BrowserSpeechRecognition | null {
  const Recognition = host?.SpeechRecognition ?? host?.webkitSpeechRecognition;
  if (!Recognition) return null;

  const recognition = new Recognition();
  recognition.lang = language;
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  // A result list contains earlier final segments as well as the changed
  // segment. Track final indexes so browser re-emissions cannot duplicate text.
  const delivered = new Map<number, string>();
  recognition.onresult = event => {
    const start = Math.max(0, Math.min(event.resultIndex, event.results.length));
    for (let index = start; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (!result?.isFinal) continue;
      const transcript = result[0]?.transcript?.trim();
      if (!transcript || delivered.get(index) === transcript) continue;
      delivered.set(index, transcript);
      handlers.onTranscript(transcript);
    }
  };
  recognition.onerror = event => handlers.onError(speechRecognitionErrorMessage(event.error));
  recognition.onend = handlers.onEnd;
  return recognition;
}

export function speechRecognitionErrorMessage(code?: string): string {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return "Microphone permission was denied or blocked. Allow microphone access in your browser and try again.";
    case "audio-capture":
      return "No microphone was found. Connect or enable a microphone and try again.";
    case "no-speech":
      return "No speech was detected. Speak closer to the microphone and try again.";
    case "network":
      return "Speech recognition needs a network connection in this browser. Check your connection and try again.";
    case "aborted":
      return "Dictation was stopped.";
    default:
      return "Voice dictation stopped unexpectedly. You can continue typing or try again.";
  }
}

export function resolveSpeechLanguage(
  choice: SpeechLanguageChoice,
  deviceLanguage = "en-US",
): string {
  if (choice !== "device") return choice;
  return deviceLanguage.trim() || "en-US";
}

export function hasBrowserSpeechSynthesis(host?: SpeechSynthesisHost): boolean {
  return Boolean(host?.speechSynthesis && host.SpeechSynthesisUtterance);
}

export function createSpeechUtterance(
  host: SpeechSynthesisHost | undefined,
  text: string,
  language: string,
): SpeechSynthesisUtterance | null {
  if (!host?.speechSynthesis || !host.SpeechSynthesisUtterance || !text.trim()) return null;
  host.speechSynthesis.cancel();
  const utterance = new host.SpeechSynthesisUtterance(text);
  utterance.lang = language;
  host.speechSynthesis.speak(utterance);
  return utterance;
}

export function cancelSpeechSynthesis(host?: SpeechSynthesisHost): void {
  host?.speechSynthesis?.cancel();
}
