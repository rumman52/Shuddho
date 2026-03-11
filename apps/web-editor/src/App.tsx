import { useEffect, useMemo, useRef, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import sampleFixtures from "@shared/fixtures/bangla_samples.json";
import type { AnalyzeResponse, Suggestion } from "@shared/schemas/contracts";
import { SuggestionCard } from "./components/SuggestionCard";
import { IssueMark } from "./lib/editorExtensions";
import { analyzeText, sendFeedback } from "./lib/api";
import { applyIssueMarks, replaceSuggestion } from "./lib/highlight";

const INITIAL_TEXT = sampleFixtures[0]?.text ?? "আমি  বাংলা লিখি  ।। বাংলা বাংলা ভাষা খুব সুন্দর !!";

export default function App() {
  const [analysis, setAnalysis] = useState<AnalyzeResponse>({
    text: INITIAL_TEXT,
    normalized_text: INITIAL_TEXT,
    suggestions: []
  });
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<string | null>(null);
  const [cardPosition, setCardPosition] = useState<{ left: number; top: number } | null>(null);
  const [status, setStatus] = useState("Waiting for input");
  const timerRef = useRef<number | null>(null);

  const editor = useEditor({
    extensions: [StarterKit.configure({ heading: false, bulletList: false, orderedList: false }), IssueMark],
    content: `<p>${INITIAL_TEXT}</p>`,
    editorProps: {
      attributes: {
        class: "shuddho-editor"
      },
      handleKeyDown: (_view, event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          return true;
        }
        return false;
      },
      handleClick: (_view, _position, event) => {
        const target = event.target as HTMLElement | null;
        const issueElement = target?.closest<HTMLElement>("[data-issue-id]");
        if (!issueElement) {
          setSelectedSuggestionId(null);
          return false;
        }
        setSelectedSuggestionId(issueElement.dataset.issueId ?? null);
        setCardPosition({
          left: event.clientX + 12,
          top: event.clientY + 12
        });
        return false;
      }
    },
    onUpdate: ({ editor: currentEditor }) => {
      const text = currentEditor.getText();
      setAnalysis((previous) => ({
        ...previous,
        text
      }));
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
      }
      timerRef.current = window.setTimeout(() => {
        void runAnalysis(text);
      }, 550);
    }
  });

  const selectedSuggestion = useMemo(
    () => analysis.suggestions.find((suggestion) => suggestion.id === selectedSuggestionId) ?? null,
    [analysis.suggestions, selectedSuggestionId]
  );

  useEffect(() => {
    if (!editor) {
      return;
    }
    void runAnalysis(editor.getText());
  }, [editor]);

  useEffect(() => {
    if (!editor) {
      return;
    }
    applyIssueMarks(editor, analysis.suggestions);
  }, [analysis.suggestions, editor]);

  async function runAnalysis(text: string) {
    if (!text.trim()) {
      setAnalysis({ text, normalized_text: text, suggestions: [] });
      setStatus("Empty input");
      return;
    }

    setStatus("Analyzing...");
    try {
      const response = await analyzeText({ text });
      setAnalysis(response);
      setStatus(`${response.suggestions.length} suggestion(s)`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Analyze request failed");
    }
  }

  async function handleAccept(replacement: string) {
    if (!editor || !selectedSuggestion) {
      return;
    }

    const applied = replaceSuggestion(editor, selectedSuggestion, replacement);
    await sendFeedback({
      suggestion_id: selectedSuggestion.id,
      action: "accepted",
      text: analysis.text,
      replacement
    });
    setSelectedSuggestionId(null);
    setCardPosition(null);
    setStatus(applied ? "Suggestion accepted" : "Suggestion no longer matched current text");
    window.setTimeout(() => {
      void runAnalysis(editor.getText());
    }, 20);
  }

  async function handleDismiss() {
    if (!selectedSuggestion) {
      return;
    }
    await sendFeedback({
      suggestion_id: selectedSuggestion.id,
      action: "dismissed",
      text: analysis.text
    });
    setAnalysis((previous) => ({
      ...previous,
      suggestions: previous.suggestions.filter((suggestion) => suggestion.id !== selectedSuggestion.id)
    }));
    setSelectedSuggestionId(null);
    setCardPosition(null);
    setStatus("Suggestion dismissed");
  }

  return (
    <main className="app-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Shuddho</p>
          <h1>Bangla writing assistant MVP</h1>
          <p className="lede">
            Type Bangla text, inspect conservative suggestions, and send accept or dismiss feedback to the FastAPI backend.
          </p>
        </div>
        <div className="status-panel">
          <span>{status}</span>
          <strong>{analysis.suggestions.length}</strong>
        </div>
      </section>

      <section className="editor-panel">
        <div className="panel-header">
          <div>
            <h2>Web editor</h2>
            <p>Single-paragraph Tiptap editor for the first MVP slice.</p>
          </div>
          <button className="analyze-button" onClick={() => editor && void runAnalysis(editor.getText())}>
            Analyze now
          </button>
        </div>
        <EditorContent editor={editor} />
        {selectedSuggestion ? (
          <SuggestionCard
            suggestion={selectedSuggestion}
            position={cardPosition}
            onAccept={handleAccept}
            onDismiss={handleDismiss}
          />
        ) : null}
      </section>

      <section className="suggestions-panel">
        <div className="panel-header">
          <div>
            <h2>Open suggestions</h2>
            <p>Click highlighted text or use this list.</p>
          </div>
          <span>{analysis.normalized_text}</span>
        </div>
        <div className="suggestion-list">
          {analysis.suggestions.map((suggestion: Suggestion) => (
            <button
              key={suggestion.id}
              className="suggestion-list__item"
              onClick={() => {
                setSelectedSuggestionId(suggestion.id);
                setCardPosition({ left: window.innerWidth - 340, top: 190 });
              }}
            >
              <strong>{suggestion.original_text}</strong>
              <span>{suggestion.explanation_en}</span>
            </button>
          ))}
          {analysis.suggestions.length === 0 ? <p className="empty-state">No issues found for this draft.</p> : null}
        </div>
      </section>
    </main>
  );
}

