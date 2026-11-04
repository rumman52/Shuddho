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

export function hasBrowserSpeechRecognition(_host?: SpeechRecognitionHost): boolean {
  return false;
}
export function createBrowserSpeechRecognition(
  _host: SpeechRecognitionHost | undefined,
  _language: string,
  _handlers: SpeechRecognitionHandlers,
): BrowserSpeechRecognition | null {
  return null;
}
export function speechRecognitionErrorMessage(_code?: string): string {
  return "";
}
export function resolveSpeechLanguage(
  _choice: SpeechLanguageChoice,
  _deviceLanguage?: string,
): string {
  return "";
}
export function hasBrowserSpeechSynthesis(_host?: SpeechSynthesisHost): boolean {
  return false;
}
export function createSpeechUtterance(
  _host: SpeechSynthesisHost | undefined,
  _text: string,
  _language: string,
): SpeechSynthesisUtterance | null {
  return null;
}
export function cancelSpeechSynthesis(_host?: SpeechSynthesisHost): void {}
