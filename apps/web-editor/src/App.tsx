import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import sampleFixtures from "@shared/fixtures/bangla_samples.json";
import type { AnalyzeResponse, Suggestion } from "@shared/schemas/contracts";
import { SuggestionCard, type SuggestionCardAnchor } from "./components/SuggestionCard";
import { IssueMark } from "./lib/editorExtensions";
import { analyzeText, sendFeedback } from "./lib/api";
import { applyIssueMarks, replaceSuggestion } from "./lib/highlight";

const INITIAL_TEXT = sampleFixtures[0]?.text ?? "à¦†à¦®à¦¿  à¦¬à¦¾à¦‚à¦²à¦¾ à¦²à¦¿à¦–à¦¿  à¥¤à¥¤ à¦¬à¦¾à¦‚à¦²à¦¾ à¦¬à¦¾à¦‚à¦²à¦¾ à¦­à¦¾à¦·à¦¾ à¦–à§à¦¬ à¦¸à§à¦¨à§à¦¦à¦° !!";
const ANALYSIS_DEBOUNCE_MS = 550;
const HOVER_HIDE_DELAY_MS = 160;
const POST_ACCEPT_ANALYSIS_DELAY_MS = 80;

export default function App() {
  const [analysis, setAnalysis] = useState<AnalyzeResponse>({
    text: INITIAL_TEXT,
    normalized_text: INITIAL_TEXT,
    suggestions: []
  });
  const [activeSuggestionId, setActiveSuggestionId] = useState<string | null>(null);
  const [cardAnchorRect, setCardAnchorRect] = useState<SuggestionCardAnchor | null>(null);
  const [status, setStatus] = useState("Waiting for input");
  const analysisTimerRef = useRef<number | null>(null);
  const hideTimerRef = useRef<number | null>(null);
  const latestAnalysisRequestRef = useRef(0);
  const activeAnchorElementRef = useRef<HTMLElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);

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
      }
    },
    onUpdate: ({ editor: currentEditor }) => {
      const text = currentEditor.getText();
      setAnalysis((previous) => ({
        ...previous,
        text
      }));
      closeSuggestionCard();
      scheduleAnalysis(text, ANALYSIS_DEBOUNCE_MS);
    }
  });

  const activeSuggestion = useMemo(
    () => analysis.suggestions.find((suggestion) => suggestion.id === activeSuggestionId) ?? null,
    [analysis.suggestions, activeSuggestionId]
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

  useEffect(() => {
    if (!editor) {
      return;
    }

    const issueElements = editor.view.dom.querySelectorAll<HTMLElement>("[data-issue-id]");
    issueElements.forEach((element) => {
      if (element.dataset.issueId === activeSuggestionId) {
        element.dataset.issueActive = "true";
      } else {
        delete element.dataset.issueActive;
      }
    });
  }, [activeSuggestionId, analysis.suggestions, editor]);

  useEffect(() => {
    if (!activeSuggestionId) {
      return;
    }
    if (analysis.suggestions.some((suggestion) => suggestion.id === activeSuggestionId)) {
      return;
    }
    closeSuggestionCard();
  }, [analysis.suggestions, activeSuggestionId]);

  useEffect(() => {
    if (!activeSuggestionId) {
      return;
    }

    const syncCardAnchor = () => {
      const anchorElement = getActiveAnchorElement(activeSuggestionId);
      if (!anchorElement) {
        closeSuggestionCard();
        return;
      }
      setCardAnchorRect(toCardAnchor(anchorElement));
    };

    syncCardAnchor();
    window.addEventListener("resize", syncCardAnchor);
    window.addEventListener("scroll", syncCardAnchor, true);
    return () => {
      window.removeEventListener("resize", syncCardAnchor);
      window.removeEventListener("scroll", syncCardAnchor, true);
    };
  }, [activeSuggestionId, editor]);

  useEffect(() => {
    return () => {
      clearAnalysisTimer();
      clearHideTimer();
    };
  }, []);

  async function runAnalysis(text: string) {
    const requestId = ++latestAnalysisRequestRef.current;

    if (!text.trim()) {
      setAnalysis({ text, normalized_text: text, suggestions: [] });
      closeSuggestionCard();
      setStatus("Empty input");
      return;
    }

    setStatus("Analyzing...");
    try {
      const response = await analyzeText({ text });
      if (requestId !== latestAnalysisRequestRef.current) {
        return;
      }
      setAnalysis(response);
      setStatus(`${response.suggestions.length} suggestion(s)`);
    } catch (error) {
      if (requestId !== latestAnalysisRequestRef.current) {
        return;
      }
      setStatus(error instanceof Error ? error.message : "Analyze request failed");
    }
  }

  async function handleAccept(replacement: string) {
    if (!editor || !activeSuggestion) {
      return;
    }

    const suggestion = activeSuggestion;
    const feedbackText = analysis.text;
    const applied = replaceSuggestion(editor, suggestion, replacement);

    closeSuggestionCard();
    if (!applied) {
      setStatus("Suggestion no longer matched current text");
      scheduleAnalysis(editor.getText(), POST_ACCEPT_ANALYSIS_DELAY_MS);
      return;
    }

    setStatus("Suggestion accepted");
    scheduleAnalysis(editor.getText(), POST_ACCEPT_ANALYSIS_DELAY_MS);

    try {
      await sendFeedback({
        suggestion_id: suggestion.id,
        action: "accepted",
        text: feedbackText,
        replacement
      });
    } catch (error) {
      setStatus(error instanceof Error ? `Feedback failed: ${error.message}` : "Feedback failed");
    }
  }

  async function handleDismiss() {
    if (!activeSuggestion) {
      return;
    }

    const suggestion = activeSuggestion;
    const feedbackText = analysis.text;

    setAnalysis((previous) => ({
      ...previous,
      suggestions: previous.suggestions.filter((item) => item.id !== suggestion.id)
    }));
    closeSuggestionCard();
    setStatus("Suggestion dismissed");

    try {
      await sendFeedback({
        suggestion_id: suggestion.id,
        action: "dismissed",
        text: feedbackText
      });
    } catch (error) {
      setStatus(error instanceof Error ? `Feedback failed: ${error.message}` : "Feedback failed");
    }
  }

  function handleEditorMouseOver(event: ReactMouseEvent<HTMLDivElement>) {
    const issueElement = findIssueElement(event.target);
    const suggestionId = issueElement?.dataset.issueId;
    if (!issueElement || !suggestionId) {
      return;
    }

    clearHideTimer();
    if (activeSuggestionId === suggestionId && activeAnchorElementRef.current === issueElement) {
      return;
    }
    openSuggestionCard(suggestionId, issueElement);
  }

  function handleEditorMouseOut(event: ReactMouseEvent<HTMLDivElement>) {
    const issueElement = findIssueElement(event.target);
    if (!issueElement) {
      return;
    }

    const relatedTarget = event.relatedTarget as Node | null;
    if (relatedTarget && cardRef.current?.contains(relatedTarget)) {
      return;
    }

    if (findIssueElement(event.relatedTarget)) {
      return;
    }

    scheduleHideCard();
  }

  function handleEditorClick(event: ReactMouseEvent<HTMLDivElement>) {
    const issueElement = findIssueElement(event.target);
    const suggestionId = issueElement?.dataset.issueId;

    if (!issueElement || !suggestionId) {
      closeSuggestionCard();
      return;
    }

    openSuggestionCard(suggestionId, issueElement);
  }

  function handleCardMouseEnter() {
    clearHideTimer();
  }

  function handleCardMouseLeave(event: ReactMouseEvent<HTMLDivElement>) {
    if (findIssueElement(event.relatedTarget)) {
      return;
    }
    scheduleHideCard();
  }

  function openSuggestionCard(suggestionId: string, anchorElement: HTMLElement) {
    clearHideTimer();
    activeAnchorElementRef.current = anchorElement;
    setActiveSuggestionId(suggestionId);
    setCardAnchorRect(toCardAnchor(anchorElement));
  }

  function closeSuggestionCard() {
    clearHideTimer();
    activeAnchorElementRef.current = null;
    setActiveSuggestionId(null);
    setCardAnchorRect(null);
  }

  function scheduleHideCard() {
    clearHideTimer();
    hideTimerRef.current = window.setTimeout(() => {
      activeAnchorElementRef.current = null;
      setActiveSuggestionId(null);
      setCardAnchorRect(null);
      hideTimerRef.current = null;
    }, HOVER_HIDE_DELAY_MS);
  }

  function clearHideTimer() {
    if (hideTimerRef.current === null) {
      return;
    }
    window.clearTimeout(hideTimerRef.current);
    hideTimerRef.current = null;
  }

  function scheduleAnalysis(text: string, delayMs: number) {
    clearAnalysisTimer();
    analysisTimerRef.current = window.setTimeout(() => {
      void runAnalysis(text);
    }, delayMs);
  }

  function clearAnalysisTimer() {
    if (analysisTimerRef.current === null) {
      return;
    }
    window.clearTimeout(analysisTimerRef.current);
    analysisTimerRef.current = null;
  }

  function getActiveAnchorElement(suggestionId: string): HTMLElement | null {
    if (activeAnchorElementRef.current?.isConnected) {
      return activeAnchorElementRef.current;
    }
    if (!editor) {
      return null;
    }

    const nextAnchor =
      Array.from(editor.view.dom.querySelectorAll<HTMLElement>("[data-issue-id]")).find(
        (element) => element.dataset.issueId === suggestionId
      ) ?? null;

    activeAnchorElementRef.current = nextAnchor;
    return nextAnchor;
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
            <p>Hover highlighted text to inspect suggestions without leaving the editor flow.</p>
          </div>
          <button type="button" className="analyze-button" onClick={() => editor && void runAnalysis(editor.getText())}>
            Analyze now
          </button>
        </div>
        <div className="editor-stage" onMouseOver={handleEditorMouseOver} onMouseOut={handleEditorMouseOut} onClick={handleEditorClick}>
          <EditorContent editor={editor} />
        </div>
        {activeSuggestion ? (
          <SuggestionCard
            ref={cardRef}
            suggestion={activeSuggestion}
            anchorRect={cardAnchorRect}
            onAccept={handleAccept}
            onDismiss={handleDismiss}
            onMouseEnter={handleCardMouseEnter}
            onMouseLeave={handleCardMouseLeave}
          />
        ) : null}
      </section>

      <section className="suggestions-panel">
        <div className="panel-header">
          <div>
            <h2>Open suggestions</h2>
            <p>Hover highlighted text or use this list to reopen a suggestion card.</p>
          </div>
          <span>{analysis.normalized_text}</span>
        </div>
        <div className="suggestion-list">
          {analysis.suggestions.map((suggestion: Suggestion) => (
            <button
              key={suggestion.id}
              type="button"
              className="suggestion-list__item"
              onClick={(event) => openSuggestionCard(suggestion.id, event.currentTarget)}
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

function findIssueElement(target: EventTarget | null): HTMLElement | null {
  const element = getElementFromTarget(target);
  return element?.closest<HTMLElement>("[data-issue-id]") ?? null;
}

function getElementFromTarget(target: EventTarget | null): HTMLElement | null {
  if (target instanceof HTMLElement) {
    return target;
  }
  if (target instanceof Text) {
    return target.parentElement;
  }
  return null;
}

function toCardAnchor(element: HTMLElement): SuggestionCardAnchor {
  const rect = element.getBoundingClientRect();
  return {
    left: rect.left,
    top: rect.top,
    right: rect.right,
    bottom: rect.bottom,
    width: rect.width,
    height: rect.height
  };
}
