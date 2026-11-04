import { useEffect, useRef, useState, type ChangeEvent } from "react";
import {
  createBrowserSpeechRecognition,
  hasBrowserSpeechRecognition,
  resolveSpeechLanguage,
  type BrowserSpeechRecognition,
  type SpeechLanguageChoice,
  type SpeechRecognitionHost,
} from "./speech";

function browserSpeechHost(): SpeechRecognitionHost | undefined {
  if (typeof window === "undefined") return undefined;
  return window as unknown as SpeechRecognitionHost;
}

function deviceLanguage(): string {
  return typeof navigator !== "undefined" && navigator.language ? navigator.language : "en-US";
}

function MicrophoneIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none">
    <rect x="9" y="3" width="6" height="12" rx="3" stroke="currentColor" strokeWidth="1.6" />
    <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3m-3 0h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>;
}

export default function VoiceDictation({ draft, onDraftChange, onListeningChange, disabled }: {
  draft: string;
  onDraftChange: (value: string) => void;
  onListeningChange?: (listening: boolean) => void;
  disabled: boolean;
}) {
  const [language, setLanguage] = useState<SpeechLanguageChoice>("device");
  const [listening, setListening] = useState(false);
  const [status, setStatus] = useState("");
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const draftRef = useRef(draft);
  const stopReasonRef = useRef<"user" | "error" | null>(null);
  const host = browserSpeechHost();
  const supported = hasBrowserSpeechRecognition(host);

  useEffect(() => { draftRef.current = draft; }, [draft]);
  useEffect(() => { onListeningChange?.(listening); }, [listening, onListeningChange]);

  function stopRecognition() {
    const recognition = recognitionRef.current;
    if (!recognition) return;
    recognitionRef.current = null;
    stopReasonRef.current = "user";
    try { recognition.stop(); }
    catch { try { recognition.abort(); } catch { /* Browser already stopped. */ } }
    setListening(false);
    setStatus("Dictation stopped.");
  }

  useEffect(() => {
    if (disabled && recognitionRef.current) stopRecognition();
  }, [disabled]);

  useEffect(() => () => {
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    if (recognition) {
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      try { recognition.abort(); } catch { /* Browser already stopped. */ }
    }
    onListeningChange?.(false);
  }, [onListeningChange]);

  function startRecognition() {
    if (!host) {
      setStatus("Voice dictation is not available in this browser.");
      return;
    }
    let recognition: BrowserSpeechRecognition | null = null;
    recognition = createBrowserSpeechRecognition(host, resolveSpeechLanguage(language, deviceLanguage()), {
      onTranscript: segment => {
        if (!recognition || recognitionRef.current !== recognition) return;
        const current = draftRef.current;
        const separator = current && !/\s$/.test(current) ? " " : "";
        const next = current + separator + segment;
        draftRef.current = next;
        onDraftChange(next);
      },
      onError: message => {
        if (!recognition || recognitionRef.current !== recognition) return;
        stopReasonRef.current = "error";
        recognitionRef.current = null;
        setListening(false);
        setStatus(message);
      },
      onEnd: () => {
        if (!recognition || recognitionRef.current !== recognition) return;
        recognitionRef.current = null;
        setListening(false);
        if (stopReasonRef.current === null) setStatus("Dictation finished.");
        stopReasonRef.current = null;
      },
    });
    if (!recognition) {
      setStatus("Voice dictation is not supported in this browser. You can continue typing.");
      return;
    }

    recognitionRef.current = recognition;
    stopReasonRef.current = null;
    setListening(true);
    setStatus("Listening. Your browser may process microphone audio; only the transcript enters this draft until you send it.");
    try { recognition.start(); }
    catch {
      recognitionRef.current = null;
      stopReasonRef.current = "error";
      try { recognition.abort(); } catch { /* Browser already stopped. */ }
      setListening(false);
      setStatus("Microphone could not start. Check browser permission and try again.");
    }
  }

  function changeLanguage(event: ChangeEvent<HTMLSelectElement>) {
    setLanguage(event.target.value as SpeechLanguageChoice);
    setStatus("");
  }

  return <div className="rukh-voice-controls">
    <label className="rukh-sr-only" htmlFor="cw-dictation-language">Dictation language</label>
    <select id="cw-dictation-language" aria-label="Dictation language" value={language}
      disabled={disabled || listening} onChange={changeLanguage}>
      <option value="device">Device language</option>
      <option value="bn-BD">বাংলা</option>
      <option value="en-US">English</option>
    </select>
    <button type="button" aria-label={listening ? "Stop voice dictation" : "Start voice dictation"}
      aria-pressed={listening} disabled={disabled || !supported}
      title={supported ? (listening ? "Stop dictation" : "Dictate. Your browser may process microphone audio.") : "Voice dictation is not supported in this browser"}
      onClick={() => { if (listening) stopRecognition(); else startRecognition(); }}>
      <MicrophoneIcon /><span>{listening ? "Stop" : "Dictate"}</span>
    </button>
    {status ? <span className="rukh-voice-status" role="status" aria-live="polite">{status}</span> :
      !supported ? <span className="rukh-voice-status" role="status">Voice dictation is not supported in this browser.</span> : null}
  </div>;
}
