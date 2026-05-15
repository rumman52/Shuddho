'use client';
import { useEffect, useRef } from 'react';
import type { Suggestion } from '@shuddho/shared';
import { checkText, trackSuggestion } from '../lib/api';
import { useEditorStore } from '../lib/editorStore';

const spanStart = (s: Suggestion) => s.span.utf16StartIndex ?? s.span.startIndex;
const spanEnd = (s: Suggestion) => s.span.utf16EndIndex ?? s.span.endIndex;

export function Editor() {
  const abortRef = useRef<AbortController | null>(null);
  const { documentId, revision, text, suggestions, status, setText, setSuggestions, accept, reject, setStatus } = useEditorStore();

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current?.abort(); abortRef.current = controller;
    const sentRevision = revision;
    const handle = window.setTimeout(async () => {
      setStatus('checking');
      try {
        const response = await checkText(text, documentId, sentRevision, controller.signal);
        setSuggestions(response.suggestions, response.revision);
        setStatus('synced');
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setStatus('offline');
      }
    }, 450);
    return () => { window.clearTimeout(handle); controller.abort(); };
  }, [text, documentId, revision, setSuggestions, setStatus]);

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_ENABLE_WS_SYNC !== 'true') return;
    const wsUrl = (process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:4000/ws/docs').replace(/\/$/, '');
    const ws = new WebSocket(`${wsUrl}/${documentId}`);
    ws.onopen = () => ws.send(JSON.stringify({ type: 'client_hello', documentId }));
    ws.onerror = () => setStatus('offline');
    return () => ws.close();
  }, [documentId, setStatus]);

  return <div className="grid">
    <section className="editorCard">
      <div className="toolbar"><button type="button" className="primary" onClick={() => void checkText(text, documentId, revision).then((r) => setSuggestions(r.suggestions, r.revision))}>Check now</button></div>
      <div className="status"><span>Document revision {revision}</span><span>{status}</span></div>
      <textarea className="editor" value={text} onChange={(event) => setText(event.currentTarget.value)} aria-label="Bangla writing editor" spellCheck={false} />
    </section>
    <aside className="sidePanel">
      <h2>Shuddho suggestions</h2>
      <p className="muted">Bangla suggestions come from the common gateway and are applied only when the original span still matches.</p>
      {suggestions.length === 0 ? <p>No active suggestions.</p> : suggestions.map((suggestion) => <article className="suggestion" key={suggestion.id}>
        <small>{suggestion.type.toUpperCase()} · {Math.round(suggestion.confidence * 100)}% · {suggestion.provider}</small>
        <strong>{suggestion.originalText || 'কার্সর'} → {suggestion.suggestedText}</strong>
        <p>{suggestion.explanationBn}</p>
        <small>Span {spanStart(suggestion)}–{spanEnd(suggestion)}</small>
        <div className="actions"><button className="accept" onClick={() => { accept(suggestion); void trackSuggestion('suggestion_accepted', suggestion, documentId); }}>Accept</button><button onClick={() => { reject(suggestion); void trackSuggestion('suggestion_rejected', suggestion, documentId); }}>Reject</button></div>
      </article>)}
    </aside>
  </div>;
}
