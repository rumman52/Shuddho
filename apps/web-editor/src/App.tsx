import { useEffect, useMemo, useRef, useState, type FocusEvent as ReactFocusEvent, type MouseEvent as ReactMouseEvent } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import sampleFixtures from "@shared/fixtures/bangla_samples.json";
import type { AnalyzeMode, AnalyzeResponse, FeedbackAction, HealthDeepResponse, HealthResponse, Suggestion } from "@shared/schemas/contracts";
import { SuggestionCard, type SuggestionCardAnchor } from "./components/SuggestionCard";
import { IssueMark } from "./lib/editorExtensions";
import { analyzeText, getApiBaseUrl, getApiConfiguration, getHealth, sendFeedback, setApiBaseUrlOverride } from "./lib/api";
import { applyIssueMarks, replaceSuggestion } from "./lib/highlight";
import { LOCAL_FALLBACK_DESCRIPTION, LOCAL_FALLBACK_LABEL, analyzeTextLocally } from "./lib/localAnalysis";
import { canAddSuggestionToDictionary, describeRuntimeState, describeSuggestionSource } from "./lib/runtimeStatus";
import { getEditorTextSurface, matchSuggestionByContext, resolveSuggestionMatch } from "./lib/textSurface";

const INITIAL_TEXT = sampleFixtures[0]?.text ?? "à¦†à¦®à¦¿  à¦¬à¦¾à¦‚à¦²à¦¾ à¦²à¦¿à¦–à¦¿  à¥¤à¥¤ à¦¬à¦¾à¦‚à¦²à¦¾ à¦¬à¦¾à¦‚à¦²à¦¾ à¦­à¦¾à¦·à¦¾ à¦–à§à¦¬ à¦¸à§à¦¨à§à¦¦à¦° !!";
const ANALYSIS_DEBOUNCE_MS = 550;
const HOVER_HIDE_DELAY_MS = 180;
const POST_ACCEPT_ANALYSIS_DELAY_MS = 80;
const PERSONAL_DICTIONARY_STORAGE_KEY = "shuddho-personal-dictionary";
const USER_PROFILE_ID_STORAGE_KEY = "shuddho-user-id";
type BackendMode = "checking" | "online" | "offline" | "misconfigured";

export default function App() {
  const [requestMode, setRequestMode] = useState<AnalyzeMode>("standard");
  const [userId] = useState<string>(() => loadOrCreateLocalUserId());
  const [personalDictionary, setPersonalDictionary] = useState<string[]>(() => loadPersonalDictionary());
  const [analysis, setAnalysis] = useState<AnalyzeResponse>(() => createEmptyAnalysis(INITIAL_TEXT, "standard"));
  const [showStyleSuggestions, setShowStyleSuggestions] = useState(false);
  const [hoveredIssueId, setHoveredIssueId] = useState<string | null>(null);
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null);
  const [isPopupPinned, setIsPopupPinned] = useState(false);
  const [cardAnchorRect, setCardAnchorRect] = useState<SuggestionCardAnchor | null>(null);
  const [status, setStatus] = useState("Waiting for input");
  const [backendMode, setBackendMode] = useState<BackendMode>("checking");
  const [backendMessage, setBackendMessage] = useState("Checking backend connection...");
  const [backendHealth, setBackendHealth] = useState<HealthDeepResponse | null>(null);
  const [apiConfiguration, setApiConfiguration] = useState(() => getApiConfiguration());
  const [apiBaseUrl, setApiBaseUrl] = useState(() => getApiBaseUrl());
  const [apiBaseUrlDraft, setApiBaseUrlDraft] = useState(() => getApiBaseUrl());
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
  const runtimeDescriptor = useMemo(
    () =>
      describeRuntimeState({
        analysis,
        transport: backendMode,
        health: backendHealth,
        hardWarning: apiConfiguration.hardWarning,
      }),
    [analysis, backendHealth, backendMode, apiConfiguration.hardWarning]
  );
  const runtimeBanner = useMemo(
    () => buildRuntimeBanner(runtimeDescriptor, analysis, backendHealth, apiConfiguration.hardWarning, apiBaseUrl),
    [analysis, apiBaseUrl, apiConfiguration.hardWarning, backendHealth, runtimeDescriptor]
  );
  const isLocalFallbackActive = runtimeDescriptor.localOnly;
  const visibleSuggestionMatch = useMemo(
    () => (visibleSuggestion ? resolveSuggestionMatch(analysis.text, visibleSuggestion) : null),
    [analysis.text, visibleSuggestion]
  );
  const visibleSuggestionIsStale = visibleSuggestionMatch?.status === "stale";

  useEffect(() => {
    requestModeRef.current = requestMode;
  }, [requestMode]);

  useEffect(() => {
    setShowStyleSuggestions(requestMode === "formal");
  }, [requestMode]);

  useEffect(() => {
    window.localStorage.setItem(PERSONAL_DICTIONARY_STORAGE_KEY, JSON.stringify(personalDictionary));
  }, [personalDictionary]);

  useEffect(() => {
    void refreshBackendHealth();
  }, [apiBaseUrl, apiConfiguration.hardWarning]);

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
  }, [editor, requestMode, personalDictionary]);

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

    const matchedSuggestion = matchSuggestionByContext(lastVisibleSuggestionRef.current, analysis.suggestions);
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
      setAnalysis(createEmptyAnalysis(text, mode));
      closePopup();
      setStatus("Empty input");
      return;
    }

    if (!apiConfiguration.backendAllowed) {
      const fallbackResponse = buildLocalFallbackResponse(text, mode, [apiConfiguration.hardWarning], personalDictionary);
      setBackendMode("misconfigured");
      setBackendHealth(null);
      setBackendMessage(apiConfiguration.hardWarning ?? LOCAL_FALLBACK_DESCRIPTION);
      setAnalysis(fallbackResponse);
      setStatus(formatRuntimeSummaryStatus(fallbackResponse.suggestions, mode, fallbackResponse.runtime_source));
      return;
    }

    setStatus("Analyzing...");
    try {
      const response = await analyzeText({ text, mode, personal_dictionary: personalDictionary, user_id: userId });
      if (requestId !== latestAnalysisRequestRef.current) {
        return;
      }
      if (editor && getEditorTextSurface(editor).text !== text) {
        return;
      }
      setBackendMode("online");
      setBackendMessage(formatBackendRuntimeMessage(response, backendHealth, apiBaseUrl));
      setAnalysis(response);
      setStatus(formatRuntimeSummaryStatus(response.suggestions, mode, response.runtime_source));
    } catch (error) {
      if (requestId !== latestAnalysisRequestRef.current) {
        return;
      }
      if (editor && getEditorTextSurface(editor).text !== text) {
        return;
      }
      const fallbackResponse = buildLocalFallbackResponse(text, mode, [
        error instanceof Error ? error.message : LOCAL_FALLBACK_DESCRIPTION,
      ], personalDictionary);
      setBackendMode("offline");
      setBackendHealth(null);
      setBackendMessage(
        `${LOCAL_FALLBACK_LABEL} are active because the backend request failed at ${apiBaseUrl}. ` +
          `${error instanceof Error ? error.message : LOCAL_FALLBACK_DESCRIPTION}`
      );
      setAnalysis(fallbackResponse);
      setStatus(formatRuntimeSummaryStatus(fallbackResponse.suggestions, mode, fallbackResponse.runtime_source));
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
      setStatus("Suggestion no longer anchors to the current text");
      scheduleAnalysis(getEditorTextSurface(editor).text, POST_ACCEPT_ANALYSIS_DELAY_MS);
      return;
    }

    setStatus("Suggestion accepted");
    scheduleAnalysis(getEditorTextSurface(editor).text, POST_ACCEPT_ANALYSIS_DELAY_MS);

    if (backendMode !== "online") {
      setStatus("Suggestion accepted locally");
      return;
    }

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
        original_text: suggestion.original_text,
        user_id: userId,
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

    if (backendMode !== "online") {
      return;
    }

    try {
      await sendFeedback({
        suggestion_id: suggestion.id,
        action: "dismissed",
        text: feedbackText,
        feedback_key: suggestion.feedback_key,
        rule_id: suggestion.rule_id,
        subtype: suggestion.subtype,
        source: suggestion.source,
        original_text: suggestion.original_text,
        user_id: userId,
      });
    } catch (error) {
      setStatus(error instanceof Error ? `Feedback failed: ${error.message}` : "Feedback failed");
    }
  }

  async function handlePersistentFeedbackAction(
    action: FeedbackAction,
    { userDictionaryEntry }: { userDictionaryEntry?: string } = {}
  ) {
    if (!visibleSuggestion) {
      return;
    }

    const suggestion = visibleSuggestion;
    setAnalysis((previous) => ({
      ...previous,
      suggestions: previous.suggestions.filter((item) => item.id !== suggestion.id)
    }));
    closePopup();

    if (action === "add_to_personal_dictionary") {
      const nextEntry = (userDictionaryEntry ?? suggestion.original_text).trim();
      if (nextEntry) {
        setPersonalDictionary((previous) => {
          const normalizedEntry = normalizeDictionaryEntry(nextEntry);
          if (!normalizedEntry || previous.includes(normalizedEntry)) {
            return previous;
          }
          return [...previous, normalizedEntry];
        });
      }
      setStatus("Added to personal dictionary");
    } else if (action === "ignore_forever") {
      setStatus("Suggestion ignored forever");
    } else {
      setStatus("Marked as not wrong");
    }

    const currentText = editor ? getEditorTextSurface(editor).text : analysis.text;
    scheduleAnalysis(currentText, POST_ACCEPT_ANALYSIS_DELAY_MS);

    if (backendMode !== "online") {
      return;
    }

    try {
      await sendFeedback({
        suggestion_id: suggestion.id,
        action,
        text: analysis.text,
        replacement: suggestion.replacement_options[0] ?? null,
        feedback_key: suggestion.feedback_key,
        rule_id: suggestion.rule_id,
        subtype: suggestion.subtype,
        source: suggestion.source,
        original_text: suggestion.original_text,
        suppression_key: suggestion.suppression_key,
        user_dictionary_entry: userDictionaryEntry ?? suggestion.original_text,
        user_id: userId,
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

  function handleApiBaseUrlSave() {
    const nextApiBaseUrl = setApiBaseUrlOverride(apiBaseUrlDraft);
    setApiConfiguration(getApiConfiguration());
    setApiBaseUrlDraft(nextApiBaseUrl);
    setApiBaseUrl(nextApiBaseUrl);
  }

  async function refreshBackendHealth() {
    if (!apiConfiguration.backendAllowed) {
      setBackendHealth(null);
      setBackendMode("misconfigured");
      setBackendMessage(apiConfiguration.hardWarning ?? LOCAL_FALLBACK_DESCRIPTION);
      return;
    }
    setBackendMode("checking");
    setBackendMessage(`Checking backend at ${apiBaseUrl}...`);
    try {
      const health = await getHealth();
      setBackendHealth(health);
      setBackendMode("online");
      setBackendMessage(formatHealthRuntimeMessage(health, apiBaseUrl));
    } catch (error) {
      setBackendHealth(null);
      setBackendMode("offline");
      setBackendMessage(
        `${LOCAL_FALLBACK_LABEL} are active because the backend is unreachable at ${apiBaseUrl}. ${
          error instanceof Error ? error.message : LOCAL_FALLBACK_DESCRIPTION
        }`,
      );
    }
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
    const sourceBadge = describeSuggestionSource(suggestion, analysis);
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
        <span className="suggestion-list__badges">
          <span className="suggestion-list__badge">{sourceBadge}</span>
          {isLocalFallbackActive ? <span className="suggestion-list__badge">{LOCAL_FALLBACK_LABEL}</span> : null}
        </span>
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
          <h1>Bangla writing assistant</h1>
          <p className="lede">
            Type Bangla text and Shuddho will tell you plainly whether you are using the live backend or local fallback-only checks.
          </p>
        </div>
        <div className="status-panel">
          <span
            style={{
              padding: "0.3rem 0.65rem",
              borderRadius: "999px",
              background:
                backendMode === "online"
                  ? "rgba(255, 255, 255, 0.16)"
                  : backendMode === "offline" || backendMode === "misconfigured"
                    ? "rgba(255, 244, 228, 0.22)"
                    : "rgba(255, 255, 255, 0.12)",
            }}
          >
            {runtimeDescriptor.label}
          </span>
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
            <p>{backendMessage}</p>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "end", flexWrap: "wrap" }}>
            <label style={{ display: "grid", gap: "0.35rem", color: "var(--muted)", fontSize: "0.9rem" }}>
              <span>API URL</span>
              <input
                value={apiBaseUrlDraft}
                onChange={(event) => setApiBaseUrlDraft(event.target.value)}
                placeholder="http://127.0.0.1:8000"
                style={{
                  minWidth: "15rem",
                  borderRadius: "999px",
                  border: "1px solid var(--border)",
                  padding: "0.7rem 0.9rem",
                  background: "white",
                  color: "var(--ink)"
                }}
              />
            </label>
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
            <button type="button" className="suggestion-card__dismiss" onClick={handleApiBaseUrlSave}>
              Use API URL
            </button>
            <button type="button" className="suggestion-card__dismiss" onClick={() => void refreshBackendHealth()}>
              Retry API
            </button>
            <button
              type="button"
              className="analyze-button"
              onClick={() => editor && void runAnalysis(getEditorTextSurface(editor).text, requestMode)}
            >
              Analyze now
            </button>
          </div>
        </div>
        {backendMode === "offline" || backendMode === "misconfigured" ? (
          <div
            role="status"
            style={{
              marginBottom: "0.9rem",
              padding: "0.85rem 1rem",
              borderRadius: "18px",
              border: "1px solid rgba(187, 128, 48, 0.28)",
              background: "rgba(255, 244, 228, 0.82)",
              color: "var(--ink)"
            }}
          >
            {runtimeBanner}
          </div>
        ) : runtimeBanner ? (
          <div
            role="status"
            style={{
              marginBottom: "0.9rem",
              padding: "0.85rem 1rem",
              borderRadius: "18px",
              border: "1px solid rgba(15, 109, 98, 0.2)",
              background: "rgba(240, 249, 247, 0.94)",
              color: "var(--ink)"
            }}
          >
            {runtimeBanner}
          </div>
        ) : null}
        <div
          style={{
            marginBottom: "0.9rem",
            padding: "0.85rem 1rem",
            borderRadius: "18px",
            border: "1px solid var(--border)",
            background: "rgba(255, 255, 255, 0.82)",
            display: "grid",
            gap: "0.45rem"
          }}
        >
          <strong>{runtimeDescriptor.label}</strong>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", color: "var(--muted)", fontSize: "0.9rem" }}>
            <span>Detector used: {analysis.used_detector ? "yes" : "no"}</span>
            <span>OpenRouter used: {analysis.used_openrouter ? "yes" : "no"}</span>
            <span>Local-only suggestions: {runtimeDescriptor.localOnly ? "yes" : "no"}</span>
            <span>Lexicon: {analysis.lexicon_source}{analysis.lexicon_version ? ` (${analysis.lexicon_version})` : ""}</span>
            {analysis.backend_version ? <span>Backend: {analysis.backend_version}</span> : null}
          </div>
          {runtimeDescriptor.warnings.length > 0 ? (
            <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
              {runtimeDescriptor.warnings.map((warning) => (
                <span
                  key={warning}
                  style={{
                    borderRadius: "999px",
                    padding: "0.2rem 0.55rem",
                    background: "rgba(184, 50, 74, 0.08)",
                    color: "var(--danger)",
                    fontSize: "0.85rem"
                  }}
                >
                  {warning}
                </span>
              ))}
            </div>
          ) : null}
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
            runtimeLabel={runtimeDescriptor.label}
            sourceLabel={describeSuggestionSource(visibleSuggestion, analysis)}
            isStale={visibleSuggestionIsStale}
            canAddToDictionary={canAddSuggestionToDictionary(visibleSuggestion)}
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
            onAddToDictionary={() => void handlePersistentFeedbackAction("add_to_personal_dictionary")}
            onMouseEnter={handlePopupMouseEnter}
            onMouseLeave={handlePopupMouseLeave}
            onFocusCapture={handlePopupFocusCapture}
            onBlurCapture={handlePopupBlurCapture}
            onPointerDownCapture={handlePopupPointerDownCapture}
          />
        ) : null}
        {visibleSuggestion ? (
          <div
            style={{
              marginTop: "0.85rem",
              padding: "0.85rem 1rem",
              borderRadius: "18px",
              border: "1px solid var(--border)",
              background: "rgba(255, 255, 255, 0.82)"
            }}
          >
            <div className="panel-header" style={{ marginBottom: "0.65rem" }}>
              <div>
                <h2 style={{ fontSize: "1.1rem" }}>Trust & adapt</h2>
                <p style={{ margin: 0 }}>
                  Tell Shuddho when this suggestion should be suppressed or treated as your preferred wording.
                </p>
              </div>
            </div>
            <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
              <button
                type="button"
                className="suggestion-card__dismiss"
                onClick={() => void handlePersistentFeedbackAction("not_wrong")}
              >
                This is not wrong
              </button>
              <button
                type="button"
                className="suggestion-card__dismiss"
                onClick={() => void handlePersistentFeedbackAction("ignore_forever")}
              >
                Ignore forever
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="suggestions-panel">
        <div className="panel-header">
          <div>
            <h2>Open suggestions</h2>
            <p>
              {isLocalFallbackActive
                ? "Local fallback checks are shown here. Backend contextual corrections are unavailable until the API reconnects."
                : "Hard errors stay visible here. Optional style guidance is separated below and muted by default."}
            </p>
            <p style={{ marginTop: "0.35rem" }}>
              {runtimeDescriptor.label}. Detector used: {analysis.used_detector ? "yes" : "no"}. OpenRouter used: {analysis.used_openrouter ? "yes" : "no"}.
            </p>
          </div>
          <pre className="panel-header__normalized">{analysis.normalized_text}</pre>
        </div>
        <div ref={suggestionListRef} className="suggestion-list">
          {hardSuggestions.map((suggestion) => renderSuggestionListItem(suggestion))}
          {hardSuggestions.length === 0 ? (
            <p className="empty-state">
              {isLocalFallbackActive
                ? "No local fallback issues found. Contextual backend suggestions are unavailable in this degraded mode."
                : optionalStyleSuggestions.length > 0
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
                <h2 style={{ fontSize: "1.2rem" }}>Optional style & orthography suggestions</h2>
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

function describeBackendStatus(backendMode: BackendMode, health: HealthResponse | null): string {
  if (backendMode === "offline") {
    return "Backend unreachable — local fallback only";
  }
  if (backendMode === "checking") {
    return "Checking backend";
  }
  if (health && !health.detector.loaded) {
    return "Backend live but detector disabled";
  }
  if (health && !health.openrouter.available) {
    return "Backend live but OpenRouter unavailable";
  }
  return "Backend live";
}

function formatBackendMessage(health: HealthResponse, apiBaseUrl: string): string {
  const details = [`Backend reached at ${apiBaseUrl}.`];
  if (health.detector.loaded) {
    details.push(`Detector ready at ${health.detector.checkpoint ?? "configured checkpoint"}.`);
  } else {
    details.push(`Detector unavailable${health.detector.reason ? `: ${health.detector.reason}` : "."}`);
  }

  if (health.openrouter.available) {
    details.push(`OpenRouter ready with ${health.openrouter.model ?? "the configured model"}.`);
  } else {
    details.push(`OpenRouter unavailable${health.openrouter.reason ? `: ${health.openrouter.reason}` : "."}`);
  }

  return details.join(" ");
}

function describeRuntimeBanner(
  backendMode: BackendMode,
  health: HealthResponse | null,
  apiBaseUrl: string,
): string | null {
  if (backendMode === "offline") {
    return `Local fallback checks only. The backend could not be reached at ${apiBaseUrl}, so contextual backend corrections are turned off in this session.`;
  }
  if (backendMode !== "online" || !health || health.analysis_profile === "full_backend") {
    return null;
  }

  const reasons: string[] = [];
  if (!health.detector.loaded) {
    reasons.push(`Detector unavailable${health.detector.reason ? `: ${health.detector.reason}` : "."}`);
  }
  if (!health.openrouter.available) {
    reasons.push(`OpenRouter unavailable${health.openrouter.reason ? `: ${health.openrouter.reason}` : "."}`);
  }

  if (!reasons.length) {
    return null;
  }

  return `${describeBackendStatus("online", health)}. ${reasons.join(" ")} You are still getting backend rules and spelling checks, but not the full contextual stack.`;
}

export function formatAnalysisStatus(suggestions: Suggestion[], mode: AnalyzeMode): string {
  const hardIssueCount = suggestions.filter((suggestion) => suggestion.category !== "style").length;
  const styleSuggestionCount = suggestions.length - hardIssueCount;
  const hardLabel = hardIssueCount === 1 ? "hard issue" : "hard issues";
  const styleLabel = styleSuggestionCount === 1 ? "optional style suggestion" : "optional style suggestions";

  if (styleSuggestionCount === 0) {
    return `${hardIssueCount} ${hardLabel} • ${mode} mode`;
  }

  return `${hardIssueCount} ${hardLabel}, ${styleSuggestionCount} ${styleLabel} • ${mode} mode`;
}

export function formatFallbackStatus(suggestions: Suggestion[], mode: AnalyzeMode): string {
  const hardIssueCount = suggestions.filter((suggestion) => suggestion.category !== "style").length;
  const styleSuggestionCount = suggestions.length - hardIssueCount;
  const hardLabel = hardIssueCount === 1 ? "hard issue" : "hard issues";
  const styleLabel = styleSuggestionCount === 1 ? "optional style suggestion" : "optional style suggestions";

  if (styleSuggestionCount === 0) {
    return `${hardIssueCount} ${hardLabel} • ${LOCAL_FALLBACK_LABEL.toLowerCase()} • ${mode} mode`;
  }

  return `${hardIssueCount} ${hardLabel}, ${styleSuggestionCount} ${styleLabel} • ${LOCAL_FALLBACK_LABEL.toLowerCase()} • ${mode} mode`;
}

function formatPreciseAnalysisStatus(suggestions: Suggestion[], mode: AnalyzeMode): string {
  const hardIssueCount = suggestions.filter((suggestion) => suggestion.category !== "style").length;
  const styleSuggestionCount = suggestions.length - hardIssueCount;
  const hardLabel = hardIssueCount === 1 ? "hard issue" : "hard issues";
  const styleLabel = styleSuggestionCount === 1 ? "optional style suggestion" : "optional style suggestions";

  if (styleSuggestionCount === 0) {
    return `${hardIssueCount} ${hardLabel} | ${mode} mode`;
  }

  return `${hardIssueCount} ${hardLabel}, ${styleSuggestionCount} ${styleLabel} | ${mode} mode`;
}

function formatPreciseFallbackStatus(suggestions: Suggestion[], mode: AnalyzeMode): string {
  const hardIssueCount = suggestions.filter((suggestion) => suggestion.category !== "style").length;
  const styleSuggestionCount = suggestions.length - hardIssueCount;
  const hardLabel = hardIssueCount === 1 ? "hard issue" : "hard issues";
  const styleLabel = styleSuggestionCount === 1 ? "optional style suggestion" : "optional style suggestions";

  if (styleSuggestionCount === 0) {
    return `${hardIssueCount} ${hardLabel} | ${LOCAL_FALLBACK_LABEL.toLowerCase()} | ${mode} mode`;
  }

  return `${hardIssueCount} ${hardLabel}, ${styleSuggestionCount} ${styleLabel} | ${LOCAL_FALLBACK_LABEL.toLowerCase()} | ${mode} mode`;
}

function formatHealthRuntimeMessage(health: HealthDeepResponse, apiBaseUrl: string): string {
  const details = [`Backend reached at ${apiBaseUrl}.`, `${health.analysis_profile}.`];
  if (health.backend_version) {
    details.push(`Backend version ${health.backend_version}.`);
  }
  details.push(`Lexicon ${health.lexicon.runtime_source}${health.lexicon.version ? ` (${health.lexicon.version})` : ""}.`);
  if (health.detector.loaded) {
    details.push(`Detector ready at ${health.detector.checkpoint ?? "configured checkpoint"}.`);
  } else {
    details.push(`Detector unavailable${health.detector.reason ? `: ${health.detector.reason}` : "."}`);
  }
  if (health.openrouter.available) {
    details.push(`OpenRouter ready with ${health.openrouter.model ?? "the configured model"}.`);
  } else {
    details.push(`OpenRouter unavailable${health.openrouter.reason ? `: ${health.openrouter.reason}` : "."}`);
  }
  return details.join(" ");
}

function formatBackendRuntimeMessage(
  analysis: AnalyzeResponse,
  health: HealthDeepResponse | null,
  apiBaseUrl: string,
): string {
  if (analysis.runtime_source === "frontend_local_fallback") {
    return `${LOCAL_FALLBACK_LABEL} are active because backend analysis is unavailable at ${apiBaseUrl}.`;
  }
  if (health) {
    formatBackendMessage(health, apiBaseUrl);
    return formatHealthRuntimeMessage(health, apiBaseUrl);
  }
  return `${analysis.runtime_source}. Backend reached at ${apiBaseUrl}.`;
}

function buildRuntimeBanner(
  runtimeDescriptor: ReturnType<typeof describeRuntimeState>,
  analysis: AnalyzeResponse,
  health: HealthDeepResponse | null,
  hardWarning: string | null,
  apiBaseUrl: string,
): string | null {
  if (hardWarning) {
    return hardWarning;
  }
  if (analysis.runtime_source === "frontend_local_fallback") {
    return `Local fallback checks only. The backend could not be reached at ${apiBaseUrl}, so contextual backend corrections are turned off in this session.`;
  }
  describeRuntimeBanner("online", health, apiBaseUrl);
  if (runtimeDescriptor.label === "Full backend contextual analysis active" && !analysis.runtime_warnings.length) {
    return null;
  }
  const reasons: string[] = [];
  if (health && !health.detector.loaded) {
    reasons.push(`Detector unavailable${health.detector.reason ? `: ${health.detector.reason}` : "."}`);
  }
  if (health && !health.openrouter.available) {
    reasons.push(`OpenRouter unavailable${health.openrouter.reason ? `: ${health.openrouter.reason}` : "."}`);
  }
  const warningText = [...reasons, ...analysis.runtime_warnings].join(" ");
  if (!warningText) {
    return runtimeDescriptor.label === "Full backend contextual analysis active" ? null : runtimeDescriptor.label;
  }
  return `${runtimeDescriptor.label}. ${warningText}`.trim();
}

function formatRuntimeSummaryStatus(
  suggestions: Suggestion[],
  mode: AnalyzeMode,
  runtimeSource: AnalyzeResponse["runtime_source"],
): string {
  if (runtimeSource === "frontend_local_fallback") {
    return formatPreciseFallbackStatus(suggestions, mode);
  }
  return formatPreciseAnalysisStatus(suggestions, mode);
}

function createEmptyAnalysis(text: string, mode: AnalyzeMode): AnalyzeResponse {
  return {
    text,
    normalized_text: text,
    corrected_text: text,
    suggestions: [],
    analysis_profile: "frontend_local_fallback",
    runtime_source: "frontend_local_fallback",
    runtime_warnings: [],
    used_detector: false,
    used_openrouter: false,
    lexicon_source: "unknown",
    lexicon_version: null,
    backend_version: null,
    sentence_count: 0,
    request_mode_applied: mode,
  };
}

function buildLocalFallbackResponse(
  text: string,
  mode: AnalyzeMode,
  runtimeWarnings: Array<string | null | undefined>,
  personalDictionary: string[],
): AnalyzeResponse {
  const response = analyzeTextLocally({
    text,
    mode,
    personal_dictionary: personalDictionary,
  });
  return {
    ...response,
    runtime_warnings: [
      ...new Set(
        [response.runtime_warnings, runtimeWarnings]
          .flat()
          .filter((warning): warning is string => Boolean(warning && warning.trim()))
      ),
    ],
  };
}

function loadPersonalDictionary(): string[] {
  if (typeof window === "undefined") {
    return [];
  }

  const rawValue = window.localStorage.getItem(PERSONAL_DICTIONARY_STORAGE_KEY);
  if (!rawValue) {
    return [];
  }

  try {
    const parsed = JSON.parse(rawValue);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .map((entry) => normalizeDictionaryEntry(String(entry)))
      .filter((entry): entry is string => Boolean(entry));
  } catch {
    return [];
  }
}

function normalizeDictionaryEntry(entry: string): string {
  return entry.trim().replace(/\s+/g, " ");
}

function loadOrCreateLocalUserId(): string {
  if (typeof window === "undefined") {
    return "anonymous-web-editor";
  }

  const existingUserId = window.localStorage.getItem(USER_PROFILE_ID_STORAGE_KEY);
  if (existingUserId) {
    return existingUserId;
  }

  const generatedUserId = createLocalUserId();
  window.localStorage.setItem(USER_PROFILE_ID_STORAGE_KEY, generatedUserId);
  return generatedUserId;
}

function createLocalUserId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `anon-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
