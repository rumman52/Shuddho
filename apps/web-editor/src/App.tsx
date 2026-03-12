import { useEffect, useMemo, useRef, useState, type FocusEvent as ReactFocusEvent, type MouseEvent as ReactMouseEvent } from "react";
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
const HOVER_HIDE_DELAY_MS = 180;
const POST_ACCEPT_ANALYSIS_DELAY_MS = 80;

export default function App() {
  const [analysis, setAnalysis] = useState<AnalyzeResponse>({
    text: INITIAL_TEXT,
    normalized_text: INITIAL_TEXT,
    suggestions: []
  });
  const [hoveredIssueId, setHoveredIssueId] = useState<string | null>(null);
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null);
  const [isPopupPinned, setIsPopupPinned] = useState(false);
  const [cardAnchorRect, setCardAnchorRect] = useState<SuggestionCardAnchor | null>(null);
  const [status, setStatus] = useState("Waiting for input");
  const analysisTimerRef = useRef<number | null>(null);
  const hoverCloseTimerRef = useRef<number | null>(null);
  const latestAnalysisRequestRef = useRef(0);
  const hoveredIssueIdRef = useRef<string | null>(null);
  const activeIssueIdRef = useRef<string | null>(null);
  const isPopupPinnedRef = useRef(false);
  const isPopupHoveredRef = useRef(false);
  const isPopupFocusedRef = useRef(false);
  const popupAnchorElementRef = useRef<HTMLElement | null>(null);
  const editorStageRef = useRef<HTMLDivElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const lastVisibleSuggestionRef = useRef<Suggestion | null>(null);

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

      if (isPopupPinnedRef.current) {
        syncPinnedPopupAnchor(currentEditor.view.dom);
      } else {
        clearHoverPreview();
      }

      scheduleAnalysis(text, ANALYSIS_DEBOUNCE_MS);
    }
  });

  const visibleIssueId = isPopupPinned ? activeIssueId : hoveredIssueId;
  const visibleSuggestion = useMemo(
    () => analysis.suggestions.find((suggestion) => suggestion.id === visibleIssueId) ?? null,
    [analysis.suggestions, visibleIssueId]
  );

  useEffect(() => {
    hoveredIssueIdRef.current = hoveredIssueId;
  }, [hoveredIssueId]);

  useEffect(() => {
    activeIssueIdRef.current = activeIssueId;
  }, [activeIssueId]);

  useEffect(() => {
    isPopupPinnedRef.current = isPopupPinned;
  }, [isPopupPinned]);

  useEffect(() => {
    if (visibleSuggestion) {
      lastVisibleSuggestionRef.current = visibleSuggestion;
      return;
    }
    if (!visibleIssueId) {
      lastVisibleSuggestionRef.current = null;
    }
  }, [visibleSuggestion, visibleIssueId]);

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
      if (element.dataset.issueId === visibleIssueId) {
        element.dataset.issueActive = "true";
      } else {
        delete element.dataset.issueActive;
      }
    });
  }, [editor, visibleIssueId, analysis.suggestions]);

  useEffect(() => {
    if (!visibleIssueId) {
      return;
    }

    const exactSuggestion = analysis.suggestions.find((suggestion) => suggestion.id === visibleIssueId);
    if (exactSuggestion) {
      return;
    }

    const matchedSuggestion = matchSuggestion(lastVisibleSuggestionRef.current, analysis.suggestions);
    if (!matchedSuggestion) {
      if (isPopupPinnedRef.current) {
        closePopup();
      } else {
        clearHoverPreview();
      }
      return;
    }

    popupAnchorElementRef.current = null;
    if (isPopupPinnedRef.current) {
      if (activeIssueIdRef.current !== matchedSuggestion.id) {
        setActiveIssueId(matchedSuggestion.id);
      }
      if (hoveredIssueIdRef.current !== matchedSuggestion.id) {
        setHoveredIssueId(matchedSuggestion.id);
      }
      return;
    }

    if (hoveredIssueIdRef.current !== matchedSuggestion.id) {
      setHoveredIssueId(matchedSuggestion.id);
    }
  }, [analysis.suggestions, visibleIssueId]);

  useEffect(() => {
    if (!visibleIssueId) {
      return;
    }

    const syncPopupAnchor = () => {
      const anchorElement = resolveAnchorElement(visibleIssueId);
      if (!anchorElement) {
        if (!isPopupPinnedRef.current) {
          clearHoverPreview();
        }
        return;
      }
      setCardAnchorRect(toCardAnchor(anchorElement));
    };

    syncPopupAnchor();
    window.addEventListener("resize", syncPopupAnchor);
    window.addEventListener("scroll", syncPopupAnchor, true);
    return () => {
      window.removeEventListener("resize", syncPopupAnchor);
      window.removeEventListener("scroll", syncPopupAnchor, true);
    };
  }, [editor, visibleIssueId]);

  useEffect(() => {
    if (!isPopupPinned) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && (cardRef.current?.contains(target) || editorStageRef.current?.contains(target))) {
        return;
      }
      closePopup();
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closePopup();
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isPopupPinned]);

  useEffect(() => {
    return () => {
      clearAnalysisTimer();
      clearHoverCloseTimer();
    };
  }, []);

  async function runAnalysis(text: string) {
    const requestId = ++latestAnalysisRequestRef.current;

    if (!text.trim()) {
      setAnalysis({ text, normalized_text: text, suggestions: [] });
      closePopup();
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
    if (!editor || !visibleSuggestion) {
      return;
    }

    const suggestion = visibleSuggestion;
    const feedbackText = analysis.text;
    const applied = replaceSuggestion(editor, suggestion, replacement);

    closePopup();
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
    if (!visibleSuggestion) {
      return;
    }

    const suggestion = visibleSuggestion;
    const feedbackText = analysis.text;

    setAnalysis((previous) => ({
      ...previous,
      suggestions: previous.suggestions.filter((item) => item.id !== suggestion.id)
    }));
    closePopup();
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
    if (isPopupPinnedRef.current) {
      return;
    }

    const issueElement = findIssueElement(event.target);
    const suggestionId = issueElement?.dataset.issueId;
    if (!issueElement || !suggestionId) {
      return;
    }

    clearHoverCloseTimer();
    if (hoveredIssueIdRef.current === suggestionId && popupAnchorElementRef.current === issueElement) {
      return;
    }
    showHoverPreview(suggestionId, issueElement);
  }

  function handleEditorMouseOut(event: ReactMouseEvent<HTMLDivElement>) {
    if (isPopupPinnedRef.current) {
      return;
    }

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

    scheduleHoverClose();
  }

  function handleEditorClick(event: ReactMouseEvent<HTMLDivElement>) {
    const issueElement = findIssueElement(event.target);
    const suggestionId = issueElement?.dataset.issueId;

    if (issueElement && suggestionId) {
      pinIssue(suggestionId, issueElement);
      return;
    }

    if (!isPopupPinnedRef.current) {
      clearHoverPreview();
    }
  }

  function handlePopupMouseEnter() {
    isPopupHoveredRef.current = true;
    clearHoverCloseTimer();
  }

  function handlePopupMouseLeave(event: ReactMouseEvent<HTMLDivElement>) {
    isPopupHoveredRef.current = false;
    if (isPopupPinnedRef.current || findIssueElement(event.relatedTarget)) {
      return;
    }
    scheduleHoverClose();
  }

  function handlePopupFocusCapture() {
    isPopupFocusedRef.current = true;
    clearHoverCloseTimer();
    if (!isPopupPinnedRef.current) {
      pinVisibleIssue();
    }
  }

  function handlePopupBlurCapture(event: ReactFocusEvent<HTMLDivElement>) {
    const relatedTarget = event.relatedTarget as Node | null;
    if (relatedTarget && cardRef.current?.contains(relatedTarget)) {
      return;
    }
    isPopupFocusedRef.current = false;
    if (!isPopupPinnedRef.current) {
      scheduleHoverClose();
    }
  }

  function handlePopupPointerDownCapture() {
    if (!isPopupPinnedRef.current) {
      pinVisibleIssue();
    }
  }

  function showHoverPreview(suggestionId: string, anchorElement: HTMLElement) {
    if (isPopupPinnedRef.current) {
      return;
    }
    clearHoverCloseTimer();
    popupAnchorElementRef.current = anchorElement;
    setHoveredIssueId(suggestionId);
    setCardAnchorRect(toCardAnchor(anchorElement));
  }

  function pinIssue(suggestionId: string, anchorElement: HTMLElement) {
    clearHoverCloseTimer();
    popupAnchorElementRef.current = anchorElement;
    setHoveredIssueId(suggestionId);
    setActiveIssueId(suggestionId);
    setIsPopupPinned(true);
    setCardAnchorRect(toCardAnchor(anchorElement));
  }

  function pinVisibleIssue() {
    const suggestionId = hoveredIssueIdRef.current ?? activeIssueIdRef.current;
    if (!suggestionId) {
      return;
    }

    const anchorElement = resolveAnchorElement(suggestionId);
    if (!anchorElement) {
      return;
    }

    pinIssue(suggestionId, anchorElement);
  }

  function clearHoverPreview() {
    if (isPopupPinnedRef.current) {
      return;
    }
    clearHoverCloseTimer();
    popupAnchorElementRef.current = null;
    setHoveredIssueId(null);
    setCardAnchorRect(null);
  }

  function closePopup() {
    clearHoverCloseTimer();
    isPopupHoveredRef.current = false;
    isPopupFocusedRef.current = false;
    popupAnchorElementRef.current = null;
    setHoveredIssueId(null);
    setActiveIssueId(null);
    setIsPopupPinned(false);
    setCardAnchorRect(null);
  }

  function scheduleHoverClose() {
    if (isPopupPinnedRef.current) {
      return;
    }

    clearHoverCloseTimer();
    hoverCloseTimerRef.current = window.setTimeout(() => {
      if (isPopupPinnedRef.current || isPopupHoveredRef.current || isPopupFocusedRef.current) {
        return;
      }
      popupAnchorElementRef.current = null;
      setHoveredIssueId(null);
      setCardAnchorRect(null);
      hoverCloseTimerRef.current = null;
    }, HOVER_HIDE_DELAY_MS);
  }

  function clearHoverCloseTimer() {
    if (hoverCloseTimerRef.current === null) {
      return;
    }
    window.clearTimeout(hoverCloseTimerRef.current);
    hoverCloseTimerRef.current = null;
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

  function syncPinnedPopupAnchor(editorRoot: ParentNode) {
    const suggestionId = activeIssueIdRef.current;
    if (!suggestionId) {
      return;
    }

    const currentAnchor = popupAnchorElementRef.current;
    if (currentAnchor?.isConnected && currentAnchor.dataset.issueId === suggestionId) {
      setCardAnchorRect(toCardAnchor(currentAnchor));
      return;
    }

    const issueAnchor = findIssueAnchor(editorRoot, suggestionId);
    if (!issueAnchor) {
      return;
    }

    popupAnchorElementRef.current = issueAnchor;
    setCardAnchorRect(toCardAnchor(issueAnchor));
  }

  function resolveAnchorElement(suggestionId: string): HTMLElement | null {
    const currentAnchor = popupAnchorElementRef.current;
    if (currentAnchor?.isConnected && currentAnchor.dataset.issueId === suggestionId) {
      return currentAnchor;
    }

    const issueAnchor = editor ? findIssueAnchor(editor.view.dom, suggestionId) : null;
    if (issueAnchor) {
      popupAnchorElementRef.current = issueAnchor;
      return issueAnchor;
    }

    if (currentAnchor?.isConnected) {
      return currentAnchor;
    }

    return null;
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
            <p>Hover for preview, click an issue to pin the correction popover, then edit without losing it.</p>
          </div>
          <button type="button" className="analyze-button" onClick={() => editor && void runAnalysis(editor.getText())}>
            Analyze now
          </button>
        </div>
        <div
          ref={editorStageRef}
          className="editor-stage"
          onMouseOver={handleEditorMouseOver}
          onMouseOut={handleEditorMouseOut}
          onClick={handleEditorClick}
        >
          <EditorContent editor={editor} />
        </div>
        {visibleSuggestion ? (
          <SuggestionCard
            ref={cardRef}
            suggestion={visibleSuggestion}
            anchorRect={cardAnchorRect}
            mode={isPopupPinned ? "pinned" : "preview"}
            onAccept={handleAccept}
            onDismiss={handleDismiss}
            onMouseEnter={handlePopupMouseEnter}
            onMouseLeave={handlePopupMouseLeave}
            onFocusCapture={handlePopupFocusCapture}
            onBlurCapture={handlePopupBlurCapture}
            onPointerDownCapture={handlePopupPointerDownCapture}
          />
        ) : null}
      </section>

      <section className="suggestions-panel">
        <div className="panel-header">
          <div>
            <h2>Open suggestions</h2>
            <p>Use this list to pin a suggestion if you prefer not to target the underline directly.</p>
          </div>
          <span>{analysis.normalized_text}</span>
        </div>
        <div className="suggestion-list">
          {analysis.suggestions.map((suggestion: Suggestion) => (
            <button
              key={suggestion.id}
              type="button"
              className="suggestion-list__item"
              onClick={(event) => pinIssue(suggestion.id, event.currentTarget)}
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

function findIssueAnchor(root: ParentNode, suggestionId: string): HTMLElement | null {
  return Array.from(root.querySelectorAll<HTMLElement>("[data-issue-id]")).find(
    (element) => element.dataset.issueId === suggestionId
  ) ?? null;
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

function matchSuggestion(previous: Suggestion | null, nextSuggestions: Suggestion[]): Suggestion | null {
  if (!previous) {
    return null;
  }

  let bestMatch: { suggestion: Suggestion; score: number } | null = null;
  for (const suggestion of nextSuggestions) {
    if (suggestion.id === previous.id) {
      return suggestion;
    }

    let score = 0;
    if (suggestion.subtype === previous.subtype) {
      score += 5;
    }
    if (suggestion.source === previous.source) {
      score += 3;
    }
    if (suggestion.category === previous.category) {
      score += 2;
    }
    if (suggestion.original_text === previous.original_text) {
      score += 4;
    }

    const spanDistance = Math.abs(suggestion.span_start - previous.span_start) + Math.abs(suggestion.span_end - previous.span_end);
    if (spanDistance === 0) {
      score += 4;
    } else if (spanDistance <= 4) {
      score += 3;
    } else if (spanDistance <= 10) {
      score += 1;
    }

    if (suggestion.replacement_options.some((option) => previous.replacement_options.includes(option))) {
      score += 2;
    }

    if (score < 7 || (bestMatch && score <= bestMatch.score)) {
      continue;
    }

    bestMatch = { suggestion, score };
  }

  return bestMatch?.suggestion ?? null;
}
