import { useEffect, useRef, useState } from "react";
import {
  cancelSpeechSynthesis, createSpeechUtterance, hasBrowserSpeechSynthesis,
  resolveSpeechLanguage, type SpeechSynthesisHost,
} from "./speech";

function browserSpeechHost(): SpeechSynthesisHost | undefined {
  if (typeof window === "undefined") return undefined;
  return window as unknown as SpeechSynthesisHost;
}

function SpeakerIcon({ speaking }: { speaking: boolean }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none">
    <path d="M4 9v6h4l5 4V5L8 9H4Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    {speaking
      ? <path d="m16 9 5 6m0-6-5 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      : <><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></>}
  </svg>;
}

export default function ReadAloudButton({ text, disabled }: { text: string; disabled: boolean }) {
  const [speaking, setSpeaking] = useState(false);
  const [status, setStatus] = useState("");
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const host = browserSpeechHost();
  const supported = hasBrowserSpeechSynthesis(host);

  useEffect(() => {
    setSpeaking(false);
    setStatus("");
    return () => {
      if (utteranceRef.current) {
        utteranceRef.current = null;
        cancelSpeechSynthesis(host);
      }
    };
  }, [text]);

  function toggle() {
    if (speaking) {
      utteranceRef.current = null;
      cancelSpeechSynthesis(host);
      setSpeaking(false);
      setStatus("Reading stopped.");
      return;
    }
    const deviceLocale = typeof navigator !== "undefined" ? navigator.language : "en-US";
    const containsBangla = Array.from(text).some(character => {
      const codePoint = character.codePointAt(0) ?? 0;
      return codePoint >= 0x0980 && codePoint <= 0x09ff;
    });
    const locale = containsBangla ? "bn-BD" : deviceLocale;
    let utterance: SpeechSynthesisUtterance | null;
    try {
      utterance = createSpeechUtterance(host, text, resolveSpeechLanguage("device", locale));
    } catch {
      setStatus("Could not start read aloud. Check your device speech settings and try again.");
      return;
    }
    if (!utterance) {
      setStatus("Read aloud is not supported in this browser.");
      return;
    }
    utterance.onend = () => {
      if (utteranceRef.current !== utterance) return;
      utteranceRef.current = null;
      setSpeaking(false);
      setStatus("Finished reading.");
    };
    utterance.onerror = () => {
      if (utteranceRef.current !== utterance) return;
      utteranceRef.current = null;
      setSpeaking(false);
      setStatus("Could not read this answer aloud. Try again.");
    };
    utteranceRef.current = utterance;
    setSpeaking(true);
    setStatus("Reading answer aloud.");
  }

  return <span className="rukh-read-aloud">
    <button type="button" className="cw-text-button"
      aria-label={speaking ? "Stop reading aloud" : "Read AI reply aloud"}
      aria-pressed={speaking} disabled={disabled || !supported}
      title={supported ? (speaking ? "Stop reading aloud" : "Read this answer aloud") : "Read aloud is not supported in this browser"}
      onClick={toggle}>
      <SpeakerIcon speaking={speaking} /><span>{speaking ? "Stop reading" : "Read aloud"}</span>
    </button>
    {status && <span className="rukh-speech-status" role="status" aria-live="polite">{status}</span>}
    {!supported && <span className="rukh-speech-status" role="status">Read aloud is not supported in this browser.</span>}
  </span>;
}
