'use client';
import { useEffect, useMemo, useRef } from 'react';
import type { Suggestion } from '@shuddho/shared';
import { checkText, trackSuggestion } from '../lib/api';
import { useEditorStore } from '../lib/editorStore';

const spanStart = (s: Suggestion) => s.span.utf16StartIndex ?? s.span.startIndex;
const spanEnd = (s: Suggestion) => s.span.utf16EndIndex ?? s.span.endIndex;

const statusLabel: Record<string, string> = {
  idle: 'Ready',
  checking: 'Analyzing',
  synced: 'Synced',
  offline: 'Offline mode',
};

const statusTone: Record<string, string> = {
  idle: 'neutral',
  checking: 'working',
  synced: 'success',
  offline: 'warning',
};

export function Editor() {
  const abortRef = useRef<AbortController | null>(null);
  const { documentId, revision, text, suggestions, status, setText, setSuggestions, accept, reject, setStatus } = useEditorStore();

  const stats = useMemo(() => {
    const words = text.trim().split(/\s+/u).filter(Boolean).length;
    const highConfidence = suggestions.filter((suggestion) => suggestion.confidence >= 0.8).length;
    const types = new Set(suggestions.map((suggestion) => suggestion.type));
    return { words, characters: text.length, highConfidence, typeCount: types.size };
  }, [suggestions, text]);

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

  const runManualCheck = () => {
    setStatus('checking');
    void checkText(text, documentId, revision)
      .then((response) => {
        setSuggestions(response.suggestions, response.revision);
        setStatus('synced');
      })
      .catch(() => setStatus('offline'));
  };

  return <section className="workspace" aria-label="AI writing workspace">
    <div className="editorCard">
      <div className="cardTopline">
        <div>
          <p className="sectionKicker">Draft canvas</p>
          <h2>Bangla Document Studio</h2>
        </div>
        <div className={`syncPill syncPill--${statusTone[status] ?? 'neutral'}`}>
          <span aria-hidden="true" />{statusLabel[status] ?? status}
        </div>
      </div>

      <div className="toolbar" aria-label="Editor actions">
        <button type="button" className="primary" onClick={runManualCheck}>Run AI review</button>
        <button type="button" onClick={() => setText('আমি  আমি ভাত খাই ।বাংলা ভাষা সুন্দর')}>Load sample</button>
        <div className="toolbar__meta">Revision {revision} · {documentId}</div>
      </div>

      <div className="qualityStrip" aria-label="Document statistics">
        <span><strong>{stats.words}</strong> words</span>
        <span><strong>{stats.characters}</strong> characters</span>
        <span><strong>{suggestions.length}</strong> open insights</span>
        <span><strong>{stats.highConfidence}</strong> high confidence</span>
      </div>

      <label className="editorWrap">
        <span className="srOnly">Bangla writing editor</span>
        <textarea className="editor" value={text} onChange={(event) => setText(event.currentTarget.value)} aria-label="Bangla writing editor" spellCheck={false} />
      </label>
    </div>

    <aside className="sidePanel" aria-label="AI suggestions">
      <div className="panelHeader">
        <p className="sectionKicker">Quality command center</p>
        <h2>AI recommendations</h2>
        <p className="muted">Each suggestion keeps the human in control and applies only when the original span still matches the current draft.</p>
      </div>

      <div className="insightGrid" aria-label="Suggestion summary">
        <div><strong>{suggestions.length}</strong><span>Total</span></div>
        <div><strong>{stats.typeCount}</strong><span>Categories</span></div>
      </div>

      <div className="suggestionList">
        {suggestions.length === 0 ? <div className="emptyState">
          <span aria-hidden="true">✓</span>
          <strong>No active suggestions</strong>
          <p>Your draft is clear, or the local service is waiting for more text.</p>
        </div> : suggestions.map((suggestion) => <article className="suggestion" key={suggestion.id}>
          <div className="suggestion__meta">
            <span>{suggestion.type.toUpperCase()}</span>
            <span>{Math.round(suggestion.confidence * 100)}%</span>
            <span>{suggestion.provider}</span>
          </div>
          <strong>{suggestion.originalText || 'কার্সর'} <span aria-hidden="true">→</span> {suggestion.suggestedText}</strong>
          <p>{suggestion.explanationBn}</p>
          <small>Span {spanStart(suggestion)}–{spanEnd(suggestion)}</small>
          <div className="actions"><button className="accept" onClick={() => { accept(suggestion); void trackSuggestion('suggestion_accepted', suggestion, documentId); }}>Accept</button><button onClick={() => { reject(suggestion); void trackSuggestion('suggestion_rejected', suggestion, documentId); }}>Dismiss</button></div>
        </article>)}
      </div>
    </aside>
  </section>;
}
