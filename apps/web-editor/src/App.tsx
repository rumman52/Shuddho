import { useEffect, useMemo, useRef, useState, type FocusEvent as ReactFocusEvent, type MouseEvent as ReactMouseEvent } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import sampleFixtures from "@shared/fixtures/bangla_samples.json";
import type { AnalyzeMode, AnalyzeResponse, Suggestion } from "@shared/schemas/contracts";
import { SuggestionCard, type SuggestionCardAnchor } from "./components/SuggestionCard";
import { IssueMark } from "./lib/editorExtensions";
import { analyzeText, sendFeedback } from "./lib/api";
import { applyIssueMarks, replaceSuggestion } from "./lib/highlight";
import { getEditorTextSurface } from "./lib/textSurface";

const INITIAL_TEXT = sampleFixtures[0]?.text ?? "à¦†à¦®à¦¿  à¦¬à¦¾à¦‚à¦²à¦¾ à¦²à¦¿à¦–à¦¿  à¥¤à¥¤ à¦¬à¦¾à¦‚à¦²à¦¾ à¦¬à¦¾à¦‚à¦²à¦¾ à¦­à¦¾à¦·à¦¾ à¦–à§à¦¬ à¦¸à§à¦¨à§à¦¦à¦° !!";
const ANALYSIS_DEBOUNCE_MS = 550;
const HOVER_HIDE_DELAY_MS = 180;
const POST_ACCEPT_ANALYSIS_DELAY_MS = 80;

export default function App() {
  const [requestMode, setRequestMode] = useState<AnalyzeMode>("standard");
  const [analysis, setAnalysis] = useState<AnalyzeResponse>({
    text: INITIAL_TEXT,
    normalized_text: INITIAL_TEXT,
    suggestions: []
  });
  const [showStyleSuggestions, setShowStyleSuggestions] = useState(false);
  const [hoveredIssueId, setHoveredIssueId] = useState<string | null>(null);
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null);
  const [isPopupPinned, setIsPopupPinned] = useState(false);
  const [cardAnchorRect, setCardAnchorRect] = useState<SuggestionCardAnchor | null>(null);
  const [status, setStatus] = useState("Waiting for input");
  const analysisTimerRef = useRef<number | null>(null);
  const hoverCloseTimerRef = useRef<number | null>(null);
  const latestAnalysisRequestRef = useRef(0);
  const requestModeRef = useRef<AnalyzeMode>(requestMode);
  const hoveredIssueIdRef = useRef<string | null>(null);
  const activeIssueIdRef = useRef<string | null>(null);
  const isPopupPinnedRef = useRef(false);
  const isPopupHoveredRef = useRef(false);
  const isPopupFocusedRef = useRef(false);
  const popupAnchorElementRef = useRef<HTMLElement | null>(null);
  const editorStageRef = useRef<HTMLDivElement | null>(null);
  const suggestionListRef = useRef<HTMLDivElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const lastVisibleSuggestionRef = useRef<Suggestion | null>(null);

  const editor = useEditor({
    extensions: [StarterKit.configure({ heading: false, bulletList: false, orderedList: false }), IssueMark],
    content: `<p>${INITIAL_TEXT}</p>`,
    editorProps: {
      attributes: {
        class: "shuddho-editor"
      }
    },
    onUpdate: ({ editor: currentEditor }) => {
      const text = getEditorTextSurface(currentEditor).text;
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
  const visibleSuggestionIndex = useMemo(
    () => (visibleSuggestion ? analysis.suggestions.findIndex((suggestion) => suggestion.id === visibleSuggestion.id) : -1),
    [analysis.suggestions, visibleSuggestion]
  );
  const hardSuggestions = useMemo(
    () => analysis.suggestions.filter((suggestion) => suggestion.category !== "style"),
    [analysis.suggestions]
  );
  const optionalStyleSuggestions = useMemo(
    () => analysis.suggestions.filter((suggestion) => suggestion.category === "style"),
    [analysis.suggestions]
  );

  useEffect(() => {
    requestModeRef.current = requestMode;
  }, [requestMode]);

  useEffect(() => {
    setShowStyleSuggestions(requestMode === "formal");
  }, [requestMode]);

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
    void runAnalysis(getEditorTextSurface(editor).text, requestMode);
  }, [editor, requestMode]);

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

  async function runAnalysis(text: string, mode: AnalyzeMode = requestModeRef.current) {
    const requestId = ++latestAnalysisRequestRef.current;

    if (!text.trim()) {
      setAnalysis({ text, normalized_text: text, suggestions: [] });
      closePopup();
      setStatus("Empty input");
      return;
    }

    setStatus("Analyzing...");
    try {
      const response = await analyzeText({ text, mode });
      if (requestId !== latestAnalysisRequestRef.current) {
        return;
      }
      setAnalysis(response);
      setStatus(formatAnalysisStatus(response.suggestions, mode));
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
      scheduleAnalysis(getEditorTextSurface(editor).text, POST_ACCEPT_ANALYSIS_DELAY_MS);
      return;
    }

    setStatus("Suggestion accepted");
    scheduleAnalysis(getEditorTextSurface(editor).text, POST_ACCEPT_ANALYSIS_DELAY_MS);

    try {
      await sendFeedback({
        suggestion_id: suggestion.id,
        action: "accepted",
        text: feedbackText,
        replacement,
        feedback_key: suggestion.feedback_key,
        rule_id: suggestion.rule_id,
        subtype: suggestion.subtype,
        source: suggestion.source,
        original_text: suggestion.original_text
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
        text: feedbackText,
        feedback_key: suggestion.feedback_key,
        rule_id: suggestion.rule_id,
        subtype: suggestion.subtype,
        source: suggestion.source,
        original_text: suggestion.original_text
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

  function navigateVisibleSuggestion(direction: -1 | 1) {
    if (!analysis.suggestions.length) {
      return;
    }

    const currentIndex = visibleSuggestionIndex >= 0 ? visibleSuggestionIndex : 0;
    const nextIndex = (currentIndex + direction + analysis.suggestions.length) % analysis.suggestions.length;
    const nextSuggestion = analysis.suggestions[nextIndex];
    const anchorElement = resolveAnchorElement(nextSuggestion.id) ?? resolveSuggestionListAnchor(nextSuggestion.id);
    if (!anchorElement) {
      return;
    }

    anchorElement.scrollIntoView({ block: "nearest", inline: "nearest" });
    pinIssue(nextSuggestion.id, anchorElement);
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
      void runAnalysis(text, requestModeRef.current);
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

  function resolveSuggestionListAnchor(suggestionId: string): HTMLElement | null {
    if (!suggestionListRef.current) {
      return null;
    }
    return findSuggestionListAnchor(suggestionListRef.current, suggestionId);
  }

  function renderSuggestionListItem(suggestion: Suggestion, deemphasized = false) {
    return (
      <button
        key={suggestion.id}
        type="button"
        className="suggestion-list__item"
        data-suggestion-id={suggestion.id}
        data-suggestion-active={suggestion.id === visibleIssueId ? "true" : undefined}
        style={deemphasized ? { opacity: 0.82 } : undefined}
        onMouseEnter={(event) => {
          if (!isPopupPinnedRef.current) {
            showHoverPreview(suggestion.id, event.currentTarget);
          }
        }}
        onFocus={(event) => {
          if (!isPopupPinnedRef.current) {
            showHoverPreview(suggestion.id, event.currentTarget);
          }
        }}
        onBlur={() => {
          if (!isPopupPinnedRef.current) {
            scheduleHoverClose();
          }
        }}
        onClick={(event) => pinIssue(suggestion.id, event.currentTarget)}
      >
        <strong>{suggestion.original_text}</strong>
        {suggestion.replacement_options[0] ? (
          <span className="suggestion-list__replacement">{suggestion.replacement_options[0]}</span>
        ) : null}
        <span>{suggestion.explanation_bn || suggestion.explanation_en}</span>
      </button>
    );
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
          <strong>{hardSuggestions.length}</strong>
          <span>{hardSuggestions.length === 1 ? "hard issue" : "hard issues"}</span>
          {optionalStyleSuggestions.length > 0 ? (
            <span>{optionalStyleSuggestions.length} optional style</span>
          ) : null}
        </div>
      </section>

      <section className="editor-panel">
        <div className="panel-header">
          <div>
            <h2>Web editor</h2>
            <p>Hover for preview, click an issue to pin the correction popover, then edit without losing it.</p>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "end", flexWrap: "wrap" }}>
            <label style={{ display: "grid", gap: "0.35rem", color: "var(--muted)", fontSize: "0.9rem" }}>
              <span>Request mode</span>
              <select
                value={requestMode}
                onChange={(event) => setRequestMode(event.target.value as AnalyzeMode)}
                style={{
                  minWidth: "10rem",
                  borderRadius: "999px",
                  border: "1px solid var(--border)",
                  padding: "0.7rem 0.9rem",
                  background: "white",
                  color: "var(--ink)"
                }}
              >
                <option value="standard">Standard</option>
                <option value="strict">Strict</option>
                <option value="formal">Formal</option>
              </select>
            </label>
            <button
              type="button"
              className="analyze-button"
              onClick={() => editor && void runAnalysis(getEditorTextSurface(editor).text, requestMode)}
            >
              Analyze now
            </button>
          </div>
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
            navigation={
              analysis.suggestions.length > 1 && visibleSuggestionIndex >= 0
                ? {
                    current: visibleSuggestionIndex + 1,
                    total: analysis.suggestions.length,
                    onPrevious: () => navigateVisibleSuggestion(-1),
                    onNext: () => navigateVisibleSuggestion(1)
                  }
                : null
            }
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
            <p>Hard errors stay visible here. Optional style guidance is separated below and muted by default.</p>
          </div>
          <pre className="panel-header__normalized">{analysis.normalized_text}</pre>
        </div>
        <div ref={suggestionListRef} className="suggestion-list">
          {hardSuggestions.map((suggestion) => renderSuggestionListItem(suggestion))}
          {hardSuggestions.length === 0 ? (
            <p className="empty-state">
              {optionalStyleSuggestions.length > 0
                ? "No hard errors found. Optional style guidance is available below."
                : "No issues found for this draft."}
            </p>
          ) : null}
        </div>
        {optionalStyleSuggestions.length > 0 ? (
          <section
            aria-label="Optional style suggestions"
            style={{
              marginTop: "1rem",
              paddingTop: "1rem",
              borderTop: "1px solid var(--border)",
              opacity: requestMode === "formal" ? 1 : 0.9
            }}
          >
            <div className="panel-header" style={{ marginBottom: "0.75rem" }}>
              <div>
                <h2 style={{ fontSize: "1.2rem" }}>Optional style suggestions</h2>
                <p style={{ margin: 0 }}>
                  {requestMode === "formal"
                    ? "Formal mode opens style and register guidance automatically."
                    : "Style suggestions stay collapsed by default so likely errors remain prominent."}
                </p>
              </div>
              <button
                type="button"
                className="suggestion-card__dismiss"
                onClick={() => setShowStyleSuggestions((current) => !current)}
              >
                {showStyleSuggestions ? "Hide style suggestions" : `Show style suggestions (${optionalStyleSuggestions.length})`}
              </button>
            </div>
            {showStyleSuggestions ? (
              <div className="suggestion-list">
                {optionalStyleSuggestions.map((suggestion) => renderSuggestionListItem(suggestion, true))}
              </div>
            ) : (
              <p className="empty-state" style={{ margin: 0 }}>
                Optional style guidance is hidden in {requestMode} mode.
              </p>
            )}
          </section>
        ) : null}
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

function findSuggestionListAnchor(root: ParentNode, suggestionId: string): HTMLElement | null {
  return Array.from(root.querySelectorAll<HTMLElement>("[data-suggestion-id]")).find(
    (element) => element.dataset.suggestionId === suggestionId
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

function formatAnalysisStatus(suggestions: Suggestion[], mode: AnalyzeMode): string {
  const hardIssueCount = suggestions.filter((suggestion) => suggestion.category !== "style").length;
  const styleSuggestionCount = suggestions.length - hardIssueCount;
  const hardLabel = hardIssueCount === 1 ? "hard issue" : "hard issues";
  const styleLabel = styleSuggestionCount === 1 ? "optional style suggestion" : "optional style suggestions";

  if (styleSuggestionCount === 0) {
    return `${hardIssueCount} ${hardLabel} • ${mode} mode`;
  }

  return `${hardIssueCount} ${hardLabel}, ${styleSuggestionCount} ${styleLabel} • ${mode} mode`;
}
