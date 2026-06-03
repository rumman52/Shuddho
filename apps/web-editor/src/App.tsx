import { useEffect, useMemo, useRef, useState } from "react";
import sampleFixtures from "@shared/fixtures/bangla_samples.json";
import type {
  AnalyzeMode,
  AnalyzeResponse,
  FeedbackAction,
  HealthDeepResponse,
  RewriteIntent,
  RewriteResponse,
  Suggestion,
  SuggestionAlternative,
  ToneAnalysisResponse,
} from "@shared/schemas/contracts";

import { SuggestionCard } from "./components/SuggestionCard";
import {
  analyzeText,
  type BackendHealthResponse,
  getApiBaseUrl,
  getApiConfiguration,
  getHealth,
  getHealthDeep,
  getUserPreferences,
  rewriteText,
  saveUserPreferences,
  sendFeedback,
  setApiBaseUrlOverride,
  clearApiBaseUrlOverride,
  friendlyLlmWarning,
} from "./lib/api";
import { createEmptyAnalysis, normalizeAnalyzeResponse } from "./lib/analysis";
import { analyzeTextLocally } from "./lib/localAnalysis";
import {
  createDefaultPreferences,
  normalizePreferences,
  type ShuddhoPreferences,
} from "./lib/preferences";
import {
  canAddSuggestionToDictionary,
  describeRuntimeState,
} from "./lib/runtimeStatus";

const INITIAL_TEXT =
  sampleFixtures[0]?.text ?? "আমি বাংলা লিখি।। বাংলা ভাষা খুব সুন্দর !!";
const USER_PROFILE_ID_STORAGE_KEY = "shuddho-user-id";
const ANALYSIS_DEBOUNCE_MS = 1200;
const AUTO_AI_ANALYSIS_DEBOUNCE_MS = 3000;
const DEBUG_MODE_STORAGE_KEY = "shuddho-web-editor-debug";
const BACKEND_UNAVAILABLE_MESSAGE =
  "Backend is unavailable. Check backend deployment, CORS, and /health.";
const SUGGESTIONS_DISABLED_MESSAGE = BACKEND_UNAVAILABLE_MESSAGE;
const REQUEST_TIMEOUT_MESSAGE =
  "Request timed out. Please try again or check backend deployment.";
const DEV_LOCAL_FALLBACK_DESCRIPTION = "Dev-only browser fallback";

type BackendMode = "checking" | "connected" | "degraded" | "ready" | "unavailable" | "misconfigured";

export default function App() {
  const [text, setText] = useState(INITIAL_TEXT);
  const [mode, setMode] = useState<AnalyzeMode>("standard");
  const [userId, setUserId] = useState(loadOrCreateLocalUserId);
  const [preferences, setPreferences] = useState<ShuddhoPreferences>(() =>
    createDefaultPreferences(userId),
  );
  const [preferencesWarning, setPreferencesWarning] = useState<string | null>(
    null,
  );
  const [dictionaryDraft, setDictionaryDraft] = useState("");
  const [analysis, setAnalysis] = useState<AnalyzeResponse>(() =>
    createEmptyAnalysis(INITIAL_TEXT, "standard"),
  );
  const [tone, setTone] = useState<ToneAnalysisResponse | null>(null);
  const [rewriteResult, setRewriteResult] = useState<RewriteResponse | null>(
    null,
  );
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<
    string | null
  >(null);
  const [activeInlineSuggestionId, setActiveInlineSuggestionId] = useState<
    string | null
  >(null);
  const [reviewFilter, setReviewFilter] = useState<
    "all" | "spelling" | "grammar" | "clarity"
  >("all");
  const [status, setStatus] = useState("Ready");
  const [autoAiReview, setAutoAiReview] = useState(false);
  const [debugMode, setDebugMode] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem(DEBUG_MODE_STORAGE_KEY) === "1";
  });
  const [backendMode, setBackendMode] = useState<BackendMode>("checking");
  const [backendHealth, setBackendHealth] =
    useState<BackendHealthResponse | null>(null);
  const [shallowHealth, setShallowHealth] =
    useState<BackendHealthResponse | null>(null);
  const [apiBaseUrl, setApiBaseUrl] = useState(() => getApiBaseUrl());
  const [apiBaseUrlDraft, setApiBaseUrlDraft] = useState(() => getApiBaseUrl());
  const [apiConfiguration, setApiConfiguration] = useState(() =>
    getApiConfiguration(),
  );
  const [selection, setSelection] = useState<{ start: number; end: number }>({
    start: 0,
    end: 0,
  });
  const analysisTimerRef = useRef<number | null>(null);
  const analysisAbortRef = useRef<AbortController | null>(null);
  const analysisRequestIdRef = useRef(0);
  const hasMountedAnalysisRef = useRef(false);
  const manualAnalysisInFlightRef = useRef(false);
  const aiReviewInFlightRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [isChecking, setIsChecking] = useState(false);

  const normalizedAnalysis = useMemo(
    () => normalizeAnalyzeResponse(analysis, text, mode),
    [analysis, mode, text],
  );

  const runtimeDescriptor = useMemo(
    () =>
      describeRuntimeState({
        analysis: normalizedAnalysis,
        transport: backendTransportForRuntime(backendMode),
        health: backendHealth?.ok === true || backendHealth?.status === "ok"
          ? (backendHealth as HealthDeepResponse)
          : null,
        hardWarning: apiConfiguration.hardWarning,
      }),
    [
      normalizedAnalysis,
      apiConfiguration.hardWarning,
      backendHealth,
      backendMode,
    ],
  );

  const suggestions = Array.isArray(normalizedAnalysis.suggestions)
    ? normalizedAnalysis.suggestions
    : [];
  const runtimeWarnings = Array.isArray(normalizedAnalysis.runtime_warnings)
    ? normalizedAnalysis.runtime_warnings
    : [];
  const inlineSegments = useMemo(
    () => buildInlineSegments(text, suggestions),
    [suggestions, text],
  );

  const wordCount = useMemo(() => countWords(text), [text]);
  const characterCount = text.length;
  const suggestionCounts = useMemo(
    () => ({
      spelling: suggestions.filter(
        (suggestion) => displaySuggestionType(suggestion) === "Spelling",
      ).length,
      grammar: suggestions.filter(
        (suggestion) => displaySuggestionType(suggestion) === "Grammar",
      ).length,
      clarity: suggestions.filter(
        (suggestion) => displaySuggestionType(suggestion) === "Clarity",
      ).length,
    }),
    [suggestions],
  );
  const filteredSuggestions = useMemo(
    () =>
      reviewFilter === "all"
        ? suggestions
        : suggestions.filter(
            (suggestion) =>
              displaySuggestionType(suggestion).toLowerCase() === reviewFilter,
          ),
    [reviewFilter, suggestions],
  );
  const connectivityBanner = apiConfiguration.hardWarning
    ? apiConfiguration.hardWarning
    : backendMode === "unavailable"
      ? BACKEND_UNAVAILABLE_MESSAGE
      : null;

  useEffect(() => {
    window.localStorage.setItem(USER_PROFILE_ID_STORAGE_KEY, userId);
  }, [userId]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(DEBUG_MODE_STORAGE_KEY, debugMode ? "1" : "0");
  }, [debugMode]);

  useEffect(() => {
    void refreshBackendHealth();
  }, [
    apiBaseUrl,
    apiConfiguration.backendAllowed,
    apiConfiguration.hardWarning,
    apiConfiguration.localFallbackEnabled,
  ]);

  useEffect(() => {
    void loadPreferences(userId);
  }, [userId, apiBaseUrl]);

  useEffect(() => {
    if (!hasMountedAnalysisRef.current) {
      hasMountedAnalysisRef.current = true;
      return;
    }

    scheduleAnalysis(text);
    return () => {
      if (analysisTimerRef.current) {
        window.clearTimeout(analysisTimerRef.current);
      }
    };
  }, [
    apiBaseUrl,
    apiConfiguration.backendAllowed,
    apiConfiguration.localFallbackEnabled,
    text,
    mode,
    preferences.personal_dictionary,
    userId,
    autoAiReview,
  ]);

  async function refreshBackendHealth() {
    if (!apiConfiguration.backendAllowed) {
      setBackendMode("misconfigured");
      setBackendHealth(null);
      setShallowHealth(null);
      setStatus(
        apiConfiguration.localFallbackEnabled
          ? DEV_LOCAL_FALLBACK_DESCRIPTION
          : apiConfiguration.hardWarning ?? SUGGESTIONS_DISABLED_MESSAGE,
      );
      return;
    }

    try {
      const [healthResult, deepResult] = await Promise.allSettled([
        getHealth(),
        getHealthDeep(),
      ]);
      if (healthResult.status === "rejected") {
        throw healthResult.reason;
      }
      setShallowHealth(healthResult.value);
      if (healthResult.value?.ok !== true) {
        throw new Error("Backend health response did not report ok:true.");
      }
      const nextHealth = deepResult.status === "fulfilled" ? deepResult.value : healthResult.value;
      setBackendHealth(nextHealth);
      const nextMode = deriveBackendModeFromHealth(healthResult.value, nextHealth);
      setBackendMode(nextMode);
      if (nextMode === "degraded") {
        setStatus("Backend connected, but sentence-level corrector is degraded.");
      } else if (nextMode === "ready") {
        setStatus("Backend connected and engines loaded.");
      } else {
        setStatus("Backend connected.");
      }
    } catch (error) {
      if ((import.meta as ImportMeta & { env?: { DEV?: boolean } }).env?.DEV) {
        console.debug("Backend health check failed", error);
      }
      setBackendHealth(null);
      setShallowHealth(null);
      setBackendMode("unavailable");
      setStatus(
        apiConfiguration.localFallbackEnabled
          ? DEV_LOCAL_FALLBACK_DESCRIPTION
          : BACKEND_UNAVAILABLE_MESSAGE,
      );
    }
  }

  async function loadPreferences(nextUserId: string) {
    if (!apiConfiguration.backendAllowed) {
      setPreferences((current) => ({ ...current, user_id: nextUserId }));
      return;
    }

    try {
      const remotePreferences = normalizePreferences({
        ...(await getUserPreferences(nextUserId)),
        user_id: nextUserId,
      });
      setPreferences(remotePreferences);
      setPreferencesWarning(null);
      setMode(modeFromWritingGoal(remotePreferences.writing_goal));
    } catch {
      setPreferences((current) =>
        normalizePreferences({ ...current, user_id: nextUserId }),
      );
      setPreferencesWarning(
        "Backend preferences could not be loaded. Using defaults.",
      );
    }
  }

  function scheduleAnalysis(nextText: string) {
    if (manualAnalysisInFlightRef.current || aiReviewInFlightRef.current) {
      return;
    }

    if (analysisTimerRef.current) {
      window.clearTimeout(analysisTimerRef.current);
    }
    analysisTimerRef.current = window.setTimeout(() => {
      if (manualAnalysisInFlightRef.current || aiReviewInFlightRef.current) {
        return;
      }
      void runAnalysis(nextText, autoAiReview);
    }, autoAiReview ? AUTO_AI_ANALYSIS_DEBOUNCE_MS : ANALYSIS_DEBOUNCE_MS);
  }

  async function runAnalysis(nextText: string, includeLLM: boolean) {
    if (includeLLM) {
      manualAnalysisInFlightRef.current = true;
      setIsChecking(true);
    }

    if (!nextText.trim()) {
      setAnalysis(createEmptyAnalysis(nextText, mode));
      setTone(null);
      setRewriteResult(null);
      if (includeLLM) {
        manualAnalysisInFlightRef.current = false;
        setIsChecking(false);
      }
      return;
    }

    if (!apiConfiguration.backendAllowed) {
      setAnalysis(
        apiConfiguration.localFallbackEnabled
          ? buildLocalFallbackResponse(
              nextText,
              mode,
              preferences.personal_dictionary ?? [],
            )
          : createUnavailableAnalysis(
              nextText,
              mode,
              "backend_misconfigured_contextual_disabled",
            ),
      );
      setBackendMode("misconfigured");
      setStatus(
        apiConfiguration.localFallbackEnabled
          ? DEV_LOCAL_FALLBACK_DESCRIPTION
          : apiConfiguration.hardWarning ?? SUGGESTIONS_DISABLED_MESSAGE,
      );
      setTone(null);
      setRewriteResult(null);
      if (includeLLM) {
        manualAnalysisInFlightRef.current = false;
        setIsChecking(false);
      }
      return;
    }

    try {
      analysisAbortRef.current?.abort();
      const controller = new AbortController();
      analysisAbortRef.current = controller;
      const requestId = ++analysisRequestIdRef.current;
      const response = await analyzeText({
        text: nextText,
        mode,
        personal_dictionary: preferences.personal_dictionary ?? [],
        user_id: userId,
      }, {
        includeLLM,
        asyncLLM: false,
        llmMode: includeLLM ? "review_candidates" : "none",
        mode: includeLLM ? "smart" : "fast",
        signal: controller.signal,
      });
      if (requestId !== analysisRequestIdRef.current) {
        return;
      }
      const normalizedResponse = normalizeAnalyzeResponse(
        response,
        nextText,
        mode,
      );
      const responseSuggestions = Array.isArray(normalizedResponse.suggestions)
        ? normalizedResponse.suggestions
        : [];
      setAnalysis(normalizedResponse);
      setBackendMode(deriveBackendModeFromHealth(shallowHealth, backendHealth));
      const responseWarnings = Array.isArray(normalizedResponse.runtime_warnings)
        ? normalizedResponse.runtime_warnings.filter(Boolean)
        : [];
      const llmStatusMessage = friendlyLlmWarning(normalizedResponse as never);
      setStatus(
        includeLLM
          ? llmStatusMessage ??
              (responseSuggestions.length
                ? "AI suggestions merged."
                : `${normalizedResponse.llm_provider === "openrouter" ? "OpenRouter" : normalizedResponse.llm_provider === "openai" ? "OpenAI" : "AI"} reviewed the text but found no extra high-confidence suggestions.`)
          : responseSuggestions.length
            ? `${responseSuggestions.length} local suggestions ready`
            : responseWarnings.length
              ? `No high-confidence correction found. Backend warnings: ${responseWarnings.join(", ")}`
              : "No high-confidence correction found.",
      );
      setTone(null);
    } catch (error) {
      if (analysisAbortRef.current?.signal.aborted) {
        return;
      }
      const message = error instanceof Error ? error.message : "";
      const checkErrorMessage = describeAnalyzeTextError(message, includeLLM);
      const shouldMarkOffline = checkErrorMessage.startsWith("Browser could not reach backend");
      if (message.includes("HTTP 422") || message.includes("Backend validation failed:")) {
        setStatus(
          "Backend validation failed. Request payload does not match /api/check schema.",
        );
        return;
      }
      setAnalysis(
        apiConfiguration.localFallbackEnabled
          ? buildLocalFallbackResponse(
              nextText,
              mode,
              preferences.personal_dictionary ?? [],
            )
          : createUnavailableAnalysis(
              nextText,
              mode,
              "backend_offline_contextual_disabled",
            ),
      );
      setBackendMode(shouldMarkOffline ? "unavailable" : deriveBackendModeFromHealth(shallowHealth, backendHealth));
      setTone(null);
      setRewriteResult(null);
      setStatus(
        apiConfiguration.localFallbackEnabled && shouldMarkOffline
          ? DEV_LOCAL_FALLBACK_DESCRIPTION
          : checkErrorMessage,
      );
    } finally {
      if (includeLLM) {
        manualAnalysisInFlightRef.current = false;
        setIsChecking(false);
      }
    }
  }

  function handleSelectionChange() {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    const nextSelection = {
      start: textarea.selectionStart ?? 0,
      end: textarea.selectionEnd ?? 0,
    };
    setSelection(nextSelection);
    const focusedSuggestion = suggestions.find(
      (suggestion) =>
        nextSelection.start >= suggestion.span_start &&
        nextSelection.start <= suggestion.span_end,
    );
    if (focusedSuggestion) {
      setActiveInlineSuggestionId(focusedSuggestion.id);
      setSelectedSuggestionId(focusedSuggestion.id);
    }
  }

  function handleEditorScroll() {
    const textarea = textareaRef.current;
    const highlightLayer = document.querySelector<HTMLDivElement>(
      ".editor-highlight-layer",
    );
    if (!textarea || !highlightLayer) {
      return;
    }
    highlightLayer.scrollTop = textarea.scrollTop;
    highlightLayer.scrollLeft = textarea.scrollLeft;
  }

  function handleApplySuggestion(
    candidate: Suggestion | SuggestionAlternative,
    replacement: string,
    suggestion: Suggestion,
  ) {
    const nextText = replaceSpan(
      text,
      suggestion.span_start,
      suggestion.span_end,
      replacement,
    );
    setText(nextText);
    dropSuggestion(suggestion.id);
    setStatus("Suggestion applied");
    void sendFeedbackIfOnline({
      suggestion_id: candidate.id,
      action: "accepted",
      text,
      replacement,
      feedback_key: candidate.feedback_key,
      rule_id: candidate.rule_id,
      subtype: candidate.subtype,
      source: candidate.source,
      original_text: suggestion.original_text,
      user_id: userId,
    });
  }

  function handleDismissSuggestion(suggestion: Suggestion) {
    dropSuggestion(suggestion.id);
    setStatus("Suggestion dismissed");
    void sendFeedbackIfOnline({
      suggestion_id: suggestion.id,
      action: "dismissed",
      text,
      feedback_key: suggestion.feedback_key,
      rule_id: suggestion.rule_id,
      subtype: suggestion.subtype,
      source: suggestion.source,
      original_text: suggestion.original_text,
      user_id: userId,
    });
  }

  function handleIgnoreForever(suggestion: Suggestion) {
    setPreferences((current) => ({
      ...current,
      suppressed_rule_keys: upsertUnique(
        current.suppressed_rule_keys ?? [],
        `${suggestion.rule_id}:${suggestion.subtype}`,
      ),
    }));
    dropSuggestion(suggestion.id);
    setStatus("Suggestion ignored forever");
    void sendFeedbackIfOnline({
      suggestion_id: suggestion.id,
      action: "ignore_forever",
      text,
      replacement: suggestion.replacement_options[0] ?? null,
      feedback_key: suggestion.feedback_key,
      rule_id: suggestion.rule_id,
      subtype: suggestion.subtype,
      source: suggestion.source,
      original_text: suggestion.original_text,
      suppression_key: suggestion.suppression_key,
      user_id: userId,
    });
  }

  function handleAddToDictionary(suggestion: Suggestion) {
    const entry = suggestion.original_text.trim();
    if (!entry) {
      return;
    }
    setPreferences((current) => ({
      ...current,
      personal_dictionary: upsertUnique(
        current.personal_dictionary ?? [],
        entry,
      ),
    }));
    dropSuggestion(suggestion.id);
    setStatus("Added to personal dictionary");
    void sendFeedbackIfOnline({
      suggestion_id: suggestion.id,
      action: "add_to_personal_dictionary",
      text,
      replacement: suggestion.replacement_options[0] ?? null,
      feedback_key: suggestion.feedback_key,
      rule_id: suggestion.rule_id,
      subtype: suggestion.subtype,
      source: suggestion.source,
      original_text: suggestion.original_text,
      user_dictionary_entry: entry,
      user_id: userId,
    });
  }

  async function handleRewrite(intent: RewriteIntent, suggestion?: Suggestion) {
    if (!preferences.enable_rewrites) {
      setStatus("Rewrites are disabled in preferences");
      return;
    }

    const selectionStart =
      suggestion?.span_start ??
      (selection.end > selection.start ? selection.start : null);
    const selectionEnd =
      suggestion?.span_end ??
      (selection.end > selection.start ? selection.end : null);

    if (!isBackendConnected(backendMode)) {
      setStatus(SUGGESTIONS_DISABLED_MESSAGE);
      return;
    }

    try {
      const response = await rewriteText({
        text,
        selection_start: selectionStart,
        selection_end: selectionEnd,
        intent,
        user_id: userId,
        writing_goal: preferences.writing_goal,
        tone_goal: preferences.tone_goal,
      });
      const rewriteOptions = Array.isArray(response.options)
        ? response.options
        : [];
      const rewriteWarnings = Array.isArray(response.warnings)
        ? response.warnings
        : [];
      setRewriteResult({
        ...response,
        options: rewriteOptions,
        warnings: rewriteWarnings,
      });
      setStatus(
        rewriteOptions.length
          ? "Rewrite options ready"
          : rewriteWarnings.join(" "),
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Rewrite failed");
    }
  }

  function applyRewriteOption(optionText: string) {
    if (!rewriteResult) {
      return;
    }
    const nextText =
      rewriteResult.selection_start !== null &&
      rewriteResult.selection_start !== undefined &&
      rewriteResult.selection_end !== null &&
      rewriteResult.selection_end !== undefined
        ? replaceSpan(
            text,
            rewriteResult.selection_start,
            rewriteResult.selection_end,
            optionText,
          )
        : optionText;
    setText(nextText);
    setRewriteResult(null);
    setStatus("Rewrite applied");
    void sendFeedbackIfOnline({
      suggestion_id: `rewrite:${rewriteResult.intent}`,
      action: "rewrite_accepted",
      text,
      replacement: optionText,
      original_text: rewriteResult.original_text,
      user_id: userId,
    });
  }

  function dismissRewrite() {
    if (rewriteResult) {
      void sendFeedbackIfOnline({
        suggestion_id: `rewrite:${rewriteResult.intent}`,
        action: "rewrite_dismissed",
        text,
        original_text: rewriteResult.original_text,
        user_id: userId,
      });
    }
    setRewriteResult(null);
  }

  async function savePreferencesToBackend() {
    if (!isBackendConnected(backendMode)) {
      setStatus("Preferences saved locally for this session");
      return;
    }

    try {
      const saved = await saveUserPreferences(userId, preferences);
      setPreferences(normalizePreferences(saved));
      setStatus("Preferences saved");
    } catch (error) {
      setStatus(
        error instanceof Error ? error.message : "Could not save preferences",
      );
    }
  }

  function applyApiBaseUrl() {
    const nextBaseUrl = setApiBaseUrlOverride(apiBaseUrlDraft);
    setApiConfiguration(getApiConfiguration());
    setApiBaseUrl(nextBaseUrl);
    setApiBaseUrlDraft(nextBaseUrl);
    setStatus(`API base URL set to ${nextBaseUrl}`);
  }

  function resetApiBaseUrl() {
    const nextBaseUrl = clearApiBaseUrlOverride();
    setApiConfiguration(getApiConfiguration());
    setApiBaseUrl(nextBaseUrl);
    setApiBaseUrlDraft(nextBaseUrl);
    setStatus(`API base URL reset to ${nextBaseUrl}`);
    void refreshBackendHealth();
  }

  function resetApiUrlOverrideAndReload() {
    clearApiBaseUrlOverride();
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("shuddho-api-base-url");
      window.location.reload();
    }
  }

  async function markToneFeedback(action: FeedbackAction) {
    if (!tone) {
      return;
    }
    await sendFeedbackIfOnline({
      suggestion_id: "tone-analysis",
      action,
      text,
      replacement: tone.primary_tone ?? null,
      user_id: userId,
    });
  }

  function handleCheckWriting() {
    if (isChecking) {
      return;
    }

    if (analysisTimerRef.current) {
      window.clearTimeout(analysisTimerRef.current);
      analysisTimerRef.current = null;
    }

    analysisAbortRef.current?.abort();
    aiReviewInFlightRef.current = true;
    setStatus("Reviewing with AI");
    void runAnalysis(text, true).finally(() => {
      aiReviewInFlightRef.current = false;
    });
  }


  function handleAcceptAll() {
    const applicableSuggestions = suggestions
      .filter((suggestion) => (suggestion.replacement_options[0] ?? "").length > 0)
      .sort((a, b) => b.span_start - a.span_start);

    if (!applicableSuggestions.length) {
      setStatus("No suggestions available to apply");
      return;
    }

    const nextText = applicableSuggestions.reduce(
      (draft, suggestion) =>
        replaceSpan(
          draft,
          suggestion.span_start,
          suggestion.span_end,
          suggestion.replacement_options[0] ?? "",
        ),
      text,
    );
    setText(nextText);
    setAnalysis((current) => ({ ...current, suggestions: [] }));
    setSelectedSuggestionId(null);
    setActiveInlineSuggestionId(null);
    setStatus(`${applicableSuggestions.length} suggestions applied`);
  }

  function handleDismissAll() {
    if (!suggestions.length) {
      setStatus("No suggestions to dismiss");
      return;
    }
    setAnalysis((current) => ({ ...current, suggestions: [] }));
    setSelectedSuggestionId(null);
    setActiveInlineSuggestionId(null);
    setStatus("All suggestions dismissed");
  }

  function dropSuggestion(suggestionId: string) {
    setAnalysis((current) => ({
      ...current,
      suggestions: (Array.isArray(current.suggestions)
        ? current.suggestions
        : []
      ).filter((item) => item.id !== suggestionId),
    }));
    setSelectedSuggestionId((current) =>
      current === suggestionId ? null : current,
    );
    setActiveInlineSuggestionId((current) =>
      current === suggestionId ? null : current,
    );
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-text" aria-label="Shuddho home">
          <strong>Shuddho</strong>
          <span>AI Bangla Writing Assistant</span>
        </div>
        <nav className="header-actions" aria-label="Top navigation">
          <button type="button" className="ghost-button">
            Dictionary
          </button>
          <button type="button" className="ghost-button">
            Settings
          </button>
          <button
            type="button"
            className="avatar-button"
            aria-label="User profile"
          >
            {userId.slice(0, 1).toUpperCase() || "S"}
          </button>
        </nav>
      </header>

      {preferencesWarning ? (
        <div className="warning-banner" role="status">
          {preferencesWarning}
        </div>
      ) : null}

      {connectivityBanner ? (
        <div className="warning-banner" role="status">
          {connectivityBanner}
        </div>
      ) : null}

      <section className="product-shell" aria-label="Bangla writing assistant workspace">
        <aside className="left-nav" aria-label="Primary navigation">
          <div className="left-nav__main">
            {["Write", "Review", "Dictionary", "History"].map((item) => (
              <button
                key={item}
                type="button"
                className={`left-nav__item ${item === "Write" ? "left-nav__item--active" : ""}`}
              >
                {item}
              </button>
            ))}
          </div>
          <div className="left-nav__footer">
            <button type="button" className="left-nav__item left-nav__item--quiet">
              Help
            </button>
            <button type="button" className="left-nav__item left-nav__item--quiet">
              Theme
            </button>
          </div>
        </aside>

        <section className="editor-column">
          <div className="context-bar" aria-label="Writing context">
            <label className="context-item">
              <span>Writing goal</span>
              <select
                value={preferences.writing_goal}
                onChange={(event) => {
                  const nextGoal = event.target
                    .value as ShuddhoPreferences["writing_goal"];
                  setPreferences((current) => ({
                    ...current,
                    writing_goal: nextGoal,
                  }));
                  setMode(modeFromWritingGoal(nextGoal));
                }}
              >
                <option value="general">General</option>
                <option value="formal">Formal</option>
                <option value="academic">Academic</option>
                <option value="business">Business</option>
                <option value="casual">Casual</option>
                <option value="social">Social</option>
              </select>
            </label>
            <label className="context-item">
              <span>Tone</span>
              <select
                value={preferences.tone_goal}
                onChange={(event) =>
                  setPreferences((current) => ({
                    ...current,
                    tone_goal: event.target
                      .value as ShuddhoPreferences["tone_goal"],
                  }))
                }
              >
                <option value="neutral">Neutral</option>
                <option value="friendly">Friendly</option>
                <option value="professional">Professional</option>
                <option value="concise">Concise</option>
                <option value="confident">Confident</option>
              </select>
            </label>
            <div className="context-item" aria-label="Suggestion count">
              <span>Suggestions</span>
              <strong>{suggestions.length}</strong>
            </div>
            <div className="context-item" aria-label="Dictionary word count">
              <span>Dictionary</span>
              <strong>{preferences.personal_dictionary?.length ?? 0} words</strong>
            </div>
          </div>

          <div className="editor-card">
            <div className="editor-toolbar" aria-label="Editor formatting toolbar">
              <button type="button">Normal</button>
              <button type="button" aria-label="Bold">
                <strong>B</strong>
              </button>
              <button type="button" aria-label="Italic">
                <em>I</em>
              </button>
              <button type="button" aria-label="Underline">
                <u>U</u>
              </button>
              <button type="button" aria-label="Bulleted list">• List</button>
              <span className="toolbar-spacer" />
              <button type="button" aria-label="Undo">Undo</button>
              <button type="button" aria-label="Redo">Redo</button>
            </div>

            <div className="editor-frame">
              <div className="editor-highlight-layer">
                {inlineSegments.map((segment) => {
                  if (!segment.suggestion) {
                    return <span key={segment.key}>{segment.text}</span>;
                  }
                  const suggestion = segment.suggestion;
                  const replacement = suggestion.replacement_options[0] ?? "";
                  const isActive = activeInlineSuggestionId === suggestion.id;
                  return (
                    <span
                      key={segment.key}
                      className={`inline-issue ${displaySuggestionType(suggestion).toLowerCase()}`}
                      data-issue-type={displaySuggestionType(suggestion)}
                      onMouseEnter={() => {
                        setActiveInlineSuggestionId(suggestion.id);
                        setSelectedSuggestionId(suggestion.id);
                      }}
                      onClick={() => {
                        setActiveInlineSuggestionId(suggestion.id);
                        setSelectedSuggestionId(suggestion.id);
                      }}
                      onFocus={() => {
                        setActiveInlineSuggestionId(suggestion.id);
                        setSelectedSuggestionId(suggestion.id);
                      }}
                      tabIndex={0}
                    >
                      {segment.text}
                      {isActive ? (
                        <span className="correction-popover" role="dialog">
                          <button
                            type="button"
                            className="popover-close"
                            aria-label="Dismiss correction popover"
                            onClick={() => setActiveInlineSuggestionId(null)}
                          >
                            ×
                          </button>
                          <span className="correction-type">
                            <span className="issue-dot" aria-hidden="true" />
                            {displaySuggestionType(suggestion)}
                          </span>
                          <span className="correction-change">
                            <span>{suggestion.original_text}</span>
                            {replacement ? <span>→</span> : null}
                            {replacement ? (
                              <strong>{replacement}</strong>
                            ) : null}
                          </span>
                          <span className="correction-copy">
                            {suggestion.suggestion_reason_short_bn ??
                              suggestion.explanation_bn ??
                              "এই অংশটি সংশোধন করলে লেখা আরও পরিষ্কার হবে।"}
                          </span>
                          <span className="correction-actions">
                            {replacement ? (
                              <button
                                type="button"
                                className="button-primary button-compact"
                                onClick={() =>
                                  handleApplySuggestion(
                                    suggestion,
                                    replacement,
                                    suggestion,
                                  )
                                }
                              >
                                Apply
                              </button>
                            ) : null}
                            <button
                              type="button"
                              className="button-secondary button-compact"
                              onClick={() =>
                                handleDismissSuggestion(suggestion)
                              }
                            >
                              Ignore
                            </button>
                          </span>
                        </span>
                      ) : null}
                    </span>
                  );
                })}
              </div>
              <textarea
                ref={textareaRef}
                className="editor-textarea"
                aria-label="Bangla editor"
                value={text}
                onChange={(event) => setText(event.target.value)}
                onSelect={handleSelectionChange}
                onKeyUp={handleSelectionChange}
                onClick={handleSelectionChange}
                onScroll={handleEditorScroll}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    setActiveInlineSuggestionId(null);
                  }
                }}
              />
            </div>

            <div className="editor-statusbar">
              <span>Words: {wordCount}</span>
              <span>Characters: {characterCount}</span>
              <label className="checkbox-row auto-ai-toggle">
                <input
                  type="checkbox"
                  checked={autoAiReview}
                  onChange={(event) => setAutoAiReview(event.target.checked)}
                />
                <span>Auto AI review</span>
              </label>
              <button
                type="button"
                className="button-primary check-writing-button"
                onClick={handleCheckWriting}
                disabled={isChecking}
              >
{isChecking ? "Checking with AI..." : "Deep AI Review"}
              </button>
            </div>
          </div>

          <section className="ai-actions" aria-label="AI Actions">
            <div>
              <h2>AI Actions</h2>
            </div>
            <div className="ai-actions__buttons">
              {(
                [
                  ["clarity", "Improve clarity"],
                  ["formal", "Make formal"],
                  ["friendly", "Make simpler"],
                  ["concise", "Shorten"],
                  ["professional", "Professional tone"],
                ] as [RewriteIntent, string][]
              ).map(([intent, label]) => (
                <button
                  key={intent}
                  type="button"
                  className="button-secondary"
                  onClick={() => void handleRewrite(intent)}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="ai-actions__tip">
              Select a sentence to see focused AI suggestions for improvement.
            </p>
          </section>

          {rewriteResult ? (
            <div className="panel-block">
              <h2>Rewrite options</h2>
              <div className="compare-grid">
                <div>
                  <span className="suggestion-card__label">Original</span>
                  <p>{rewriteResult.original_text}</p>
                </div>
                <div>
                  <span className="suggestion-card__label">Suggested</span>
                  <p>{rewriteResult.target_text}</p>
                </div>
              </div>
              <div className="suggestion-list">
                {(rewriteResult.options ?? []).map((option) => (
                  <article key={option.id} className="rewrite-option">
                    <h3>{option.label}</h3>
                    <p>{option.rewritten_text}</p>
                    <p className="muted-text">
                      {option.explanation_bn || option.explanation_en}
                    </p>
                    <button
                      type="button"
                      className="button-primary"
                      onClick={() => applyRewriteOption(option.rewritten_text)}
                    >
                      Apply rewrite
                    </button>
                  </article>
                ))}
              </div>
              <button
                type="button"
                className="button-secondary"
                onClick={dismissRewrite}
              >
                Dismiss rewrite
              </button>
            </div>
          ) : null}

          {tone ? (
            <div className="panel-block">
              <div className="suggestion-card__eyebrow">Tone</div>
              <h2>{tone.primary_tone ?? "neutral"}</h2>
              <p>{tone.explanation_bn || tone.explanation_en}</p>
              <div className="row">
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => void markToneFeedback("tone_helpful")}
                >
                  Helpful
                </button>
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => void markToneFeedback("tone_not_helpful")}
                >
                  Not helpful
                </button>
              </div>
            </div>
          ) : null}
        </section>

        <aside className="review-panel" aria-label="AI Review suggestions">
          <span className="sr-only">Review queue</span>
          <div className="review-panel__header">
            <div>
              <h2>AI Review</h2>
              <p className="review-count">{suggestions.length} suggestions</p>
            </div>
          </div>

          <p className="review-panel__status">
            Review spelling, grammar, and clarity suggestions.
          </p>

          <div className="review-tabs" role="tablist" aria-label="Suggestion filters">
            {(
              [
                ["all", "All", suggestions.length],
                ["spelling", "Spelling", suggestionCounts.spelling],
                ["grammar", "Grammar", suggestionCounts.grammar],
                ["clarity", "Clarity", suggestionCounts.clarity],
              ] as const
            ).map(([filter, label, count]) => (
              <button
                key={filter}
                type="button"
                role="tab"
                aria-selected={reviewFilter === filter}
                className={reviewFilter === filter ? "review-tab review-tab--active" : "review-tab"}
                onClick={() => setReviewFilter(filter)}
              >
                {label} <strong>{count}</strong>
              </button>
            ))}
          </div>

          {filteredSuggestions.length ? (
            <div className="suggestion-list">
              {filteredSuggestions.map((suggestion) => (
                <div
                  key={suggestion.id}
                  className={
                    selectedSuggestionId === suggestion.id
                      ? "review-suggestion review-suggestion--active"
                      : "review-suggestion"
                  }
                >
                  <SuggestionCard
                    suggestion={suggestion}
                    debugMode={debugMode}
                    onApply={(candidate, replacement) =>
                      handleApplySuggestion(candidate, replacement, suggestion)
                    }
                    onDismiss={() => handleDismissSuggestion(suggestion)}
                    onIgnoreForever={() => handleIgnoreForever(suggestion)}
                    onAddToDictionary={
                      canAddSuggestionToDictionary(suggestion)
                        ? () => handleAddToDictionary(suggestion)
                        : undefined
                    }
                    onRewrite={(intent) =>
                      void handleRewrite(intent, suggestion)
                    }
                  />
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-state">
              {isBackendConnected(backendMode) || apiConfiguration.localFallbackEnabled
                ? "No high-confidence correction found in this filter."
                : SUGGESTIONS_DISABLED_MESSAGE}
            </p>
          )}

          <div className="review-actions">
            <button
              type="button"
              className="button-primary"
              onClick={handleAcceptAll}
            >
              Accept All
            </button>
            <button
              type="button"
              className="button-secondary"
              onClick={handleDismissAll}
            >
              Dismiss All
            </button>
          </div>

          <details className="advanced-settings">
            <summary>Advanced settings for developers</summary>
            <div className="advanced-settings__body">
              <strong>{runtimeDescriptor.label}</strong>
              <span>{status}</span>
              <span>Backend: {backendMode}</span>
              <span>apiBaseUrl: {apiConfiguration.apiBaseUrl || "none"}</span>
              <span>apiBaseUrlSource: {apiConfiguration.apiBaseUrlSource}</span>
              <span>apiBaseUrl source: {apiConfiguration.source}</span>
              <span>envApiBaseUrlPresent: {String(apiConfiguration.envApiBaseUrlPresent)}</span>
              <span>localStorageOverridePresent: {String(apiConfiguration.localStorageOverridePresent)}</span>
              <span>localStorageOverrideIgnored: {String(apiConfiguration.localStorageOverrideIgnored)}</span>
              <span>backendAllowed: {String(apiConfiguration.backendAllowed)}</span>
              <span>hardWarning: {apiConfiguration.hardWarning ?? "none"}</span>
              <span>backendMode: {backendMode}</span>
              <span>healthOk: {String(shallowHealth?.ok === true)}</span>
              <span>deepHealthOk: {String(backendHealth?.ok === true)}</span>
              <span>/health status: {String(shallowHealth?.status ?? (shallowHealth?.ok === true ? "ok" : shallowHealth ? "unknown" : "not loaded"))}</span>
              <span>/health/deep status: {String(backendHealth?.status ?? (backendHealth?.ok === true ? "ok" : backendHealth ? "unknown" : "not loaded"))}</span>
              <span>/health result: {JSON.stringify(shallowHealth ?? null)}</span>
              <span>/health/deep result: {JSON.stringify(backendHealth ?? null)}</span>
              <span>backendReachable: {String(runtimeDescriptor.diagnostics.backendReachable)}</span>
              <span>backendStatus: {runtimeDescriptor.diagnostics.backendStatus}</span>
              <span>detectorLoaded: {String(runtimeDescriptor.diagnostics.detectorLoaded)}</span>
              <span>correctorLoaded: {String(runtimeDescriptor.diagnostics.correctorLoaded)}</span>
              <span>correctorReason: {runtimeDescriptor.diagnostics.correctorReason ?? "none"}</span>
              <span>llmEnabled: {String(runtimeDescriptor.diagnostics.llmEnabled)}</span>
              <span>llmConfigured: {String(runtimeDescriptor.diagnostics.llmConfigured)}</span>
              <span>llmProvider: {runtimeDescriptor.diagnostics.llmProvider ?? "unknown"}</span>
              <span>llmModel: {runtimeDescriptor.diagnostics.llmModel ?? "unknown"}</span>
              <span>llm.enabled: {String((backendHealth?.llm as Record<string, unknown> | undefined)?.enabled ?? "unknown")}</span>
              <span>llm.configured: {String((backendHealth?.llm as Record<string, unknown> | undefined)?.configured ?? "unknown")}</span>
              <span>llm.provider: {String((backendHealth?.llm as Record<string, unknown> | undefined)?.provider ?? "unknown")}</span>
              <span>llm.model: {String((backendHealth?.llm as Record<string, unknown> | undefined)?.model ?? "unknown")}</span>
              <span>llm.status: {String((backendHealth?.llm as Record<string, unknown> | undefined)?.status ?? "unknown")}</span>
              <span>llm.circuit_open: {String((backendHealth?.llm as Record<string, unknown> | undefined)?.circuit_open ?? "unknown")}</span>
              <span>llm.warnings: {JSON.stringify((backendHealth?.llm as Record<string, unknown> | undefined)?.warnings ?? [])}</span>
              <span>llm_requested: {String(normalizedAnalysis.llm_requested ?? false)}</span>
              <span>llm_attempted: {String(normalizedAnalysis.llm_attempted ?? false)}</span>
              <span>llm_used: {String(normalizedAnalysis.llm_used ?? false)}</span>
              <span>last check llm_status: {normalizedAnalysis.llm_status ?? "not requested"}</span>
              <span>llm_provider: {normalizedAnalysis.llm_provider ?? "none"}</span>
              <span>llm_model: {normalizedAnalysis.llm_model ?? "none"}</span>
              <span>llm_response_mode: {normalizedAnalysis.llm_response_mode ?? "none"}</span>
              <span>last check llm_http_status: {String((normalizedAnalysis.llm as Record<string, unknown> | null | undefined)?.http_status ?? "none")}</span>
              <span>llm warnings: {JSON.stringify((normalizedAnalysis.diagnostics?.llm as Record<string, unknown> | undefined)?.warnings ?? normalizedAnalysis.runtime_warnings ?? [])}</span>
              <span>local_suggestion_count: {normalizedAnalysis.local_suggestion_count ?? suggestions.length}</span>
              <span>ai_suggestion_count: {normalizedAnalysis.ai_suggestion_count ?? 0}</span>
              <span>rejected_ai_suggestion_count: {normalizedAnalysis.rejected_ai_suggestion_count ?? 0}</span>
              <span>timings: {JSON.stringify((normalizedAnalysis.llm as Record<string, unknown> | null | undefined)?.timings ?? { llm_ms: (normalizedAnalysis.llm as Record<string, unknown> | null | undefined)?.llm_ms ?? "none" })}</span>
              <span>Lexicon: {normalizedAnalysis.lexicon_source}</span>
              {runtimeWarnings.map((warning) => (
                <span key={warning} className="chip chip-warning">
                  {warning}
                </span>
              ))}
              <label>
                User ID
                <input
                  value={userId}
                  onChange={(event) => setUserId(event.target.value)}
                />
              </label>
              <label>
                API base URL
                <div className="row">
                  <input
                    value={apiBaseUrlDraft}
                    onChange={(event) => setApiBaseUrlDraft(event.target.value)}
                  />
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={applyApiBaseUrl}
                  >
                    Apply
                  </button>
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={resetApiBaseUrl}
                  >
                    Reset
                  </button>
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={resetApiUrlOverrideAndReload}
                  >
                    Reset API URL override
                  </button>
                </div>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={preferences.auto_show_tone}
                  onChange={(event) =>
                    setPreferences((current) => ({
                      ...current,
                      auto_show_tone: event.target.checked,
                    }))
                  }
                />
                <span>Auto-show tone</span>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={preferences.enable_rewrites}
                  onChange={(event) =>
                    setPreferences((current) => ({
                      ...current,
                      enable_rewrites: event.target.checked,
                    }))
                  }
                />
                <span>Enable rewrites</span>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={autoAiReview}
                  onChange={(event) => setAutoAiReview(event.target.checked)}
                />
                <span>AI on every check</span>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={debugMode}
                  onChange={(event) => setDebugMode(event.target.checked)}
                />
                <span>Show debug details</span>
              </label>
              <button
                type="button"
                className="button-primary"
                onClick={() => void savePreferencesToBackend()}
              >
                Save Preferences
              </button>
              <div className="dictionary-box">
                <h3>Personal dictionary</h3>
                <div className="row">
                  <input
                    value={dictionaryDraft}
                    onChange={(event) => setDictionaryDraft(event.target.value)}
                  />
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => {
                      if (!dictionaryDraft.trim()) {
                        return;
                      }
                      setPreferences((current) => ({
                        ...current,
                        personal_dictionary: upsertUnique(
                          current.personal_dictionary ?? [],
                          dictionaryDraft,
                        ),
                      }));
                      setDictionaryDraft("");
                    }}
                  >
                    Add
                  </button>
                </div>
                <div className="chip-row">
                  {(preferences.personal_dictionary ?? []).map((entry) => (
                    <button
                      key={entry}
                      type="button"
                      className="chip chip-action"
                      onClick={() =>
                        setPreferences((current) => ({
                          ...current,
                          personal_dictionary: (
                            current.personal_dictionary ?? []
                          ).filter((item) => item !== entry),
                        }))
                      }
                    >
                      {entry}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </details>
        </aside>
      </section>

      <footer className="trust-footer">
        Your text is private and secure. <strong>Shuddho</strong> does not store
        your content.
      </footer>
    </main>
  );
}

interface InlineSegment {
  key: string;
  text: string;
  suggestion: Suggestion | null;
}

function buildInlineSegments(
  text: string,
  suggestions: Suggestion[],
): InlineSegment[] {
  const ordered = suggestions
    .filter(
      (suggestion) =>
        Number.isInteger(suggestion.span_start) &&
        Number.isInteger(suggestion.span_end) &&
        suggestion.span_start >= 0 &&
        suggestion.span_end > suggestion.span_start &&
        suggestion.span_end <= text.length,
    )
    .sort((a, b) => a.span_start - b.span_start || a.span_end - b.span_end);

  const segments: InlineSegment[] = [];
  let cursor = 0;

  ordered.forEach((suggestion) => {
    if (suggestion.span_start < cursor) {
      return;
    }
    if (suggestion.span_start > cursor) {
      segments.push({
        key: `text:${cursor}:${suggestion.span_start}`,
        text: text.slice(cursor, suggestion.span_start),
        suggestion: null,
      });
    }
    segments.push({
      key: `issue:${suggestion.id}`,
      text: text.slice(suggestion.span_start, suggestion.span_end),
      suggestion,
    });
    cursor = suggestion.span_end;
  });

  if (cursor < text.length || segments.length === 0) {
    segments.push({
      key: `text:${cursor}:end`,
      text: text.slice(cursor),
      suggestion: null,
    });
  }

  return segments;
}

function displaySuggestionType(suggestion: Suggestion): string {
  const value =
    `${suggestion.ui_group ?? suggestion.category ?? suggestion.subtype}`.toLowerCase();
  if (value.includes("grammar")) {
    return "Grammar";
  }
  if (
    value.includes("clarity") ||
    value.includes("style") ||
    value.includes("tone")
  ) {
    return "Clarity";
  }
  return "Spelling";
}

function isBackendConnected(backendMode: BackendMode): boolean {
  return ["connected", "degraded", "ready"].includes(backendMode);
}

function backendTransportForRuntime(backendMode: BackendMode): "checking" | "online" | "offline" | "misconfigured" {
  if (backendMode === "connected" || backendMode === "degraded" || backendMode === "ready") {
    return "online";
  }
  if (backendMode === "unavailable") {
    return "offline";
  }
  return backendMode;
}

function deriveBackendModeFromHealth(
  health: BackendHealthResponse | null,
  deepHealth: BackendHealthResponse | null,
): BackendMode {
  if (health?.ok !== true) {
    return "unavailable";
  }
  const correctorLoaded = deepHealth?.corrector_loaded ?? deepHealth?.corrector?.loaded;
  const detectorLoaded = deepHealth?.detector_loaded ?? deepHealth?.detector?.loaded;
  if (correctorLoaded === false) {
    return "degraded";
  }
  if (correctorLoaded === true && detectorLoaded !== false) {
    return "ready";
  }
  return "connected";
}

function describeAnalyzeTextError(message: string, includeLLM: boolean): string {
  const lower = message.toLowerCase();
  if (lower.includes("timed out") || lower.includes("timeout")) {
    return includeLLM ? "AI review timed out. Showing local suggestions." : REQUEST_TIMEOUT_MESSAGE;
  }
  if (message.includes("HTTP 404") || /with 404[:;]/.test(message)) {
    return "Backend route /api/check was not found.";
  }
  if (message.includes("HTTP 422") || /with 422[:;]/.test(message)) {
    return "Backend validation failed. Request payload does not match /api/check schema.";
  }
  if (message.includes("HTTP 500") || /with 500[:;]/.test(message)) {
    return "Backend crashed during analysis. Check Render logs.";
  }
  if (lower.includes("openrouter") || lower.includes("provider_error")) {
    return `OpenRouter provider error while reviewing. ${message}`.slice(0, 240);
  }
  if (lower.includes("network request failed") || lower.includes("failed to fetch") || lower.includes("cors")) {
    return "Browser could not reach backend. Check CORS and VITE_API_BASE_URL.";
  }
  return message || "Backend analysis failed. Check /api/check response and Render logs.";
}

function buildLocalFallbackResponse(
  text: string,
  mode: AnalyzeMode,
  personalDictionary: string[],
): AnalyzeResponse {
  const fallback = analyzeTextLocally({
    text,
    mode,
    personal_dictionary: personalDictionary ?? [],
  });
  return {
    ...fallback,
    runtime_warnings: Array.from(
      new Set([
        ...(fallback.runtime_warnings ?? []),
        "frontend_local_fallback_enabled",
      ]),
    ),
  };
}

async function sendFeedbackIfOnline(
  payload: Parameters<typeof sendFeedback>[0],
) {
  try {
    await sendFeedback(payload);
  } catch (error) {
    console.warn("Shuddho feedback request failed", error);
  }
}

function countWords(value: string): number {
  return value.trim() ? value.trim().split(/\s+/u).length : 0;
}

function replaceSpan(
  text: string,
  start: number,
  end: number,
  replacement: string,
): string {
  return `${text.slice(0, start)}${replacement}${text.slice(end)}`;
}

function createUnavailableAnalysis(
  text: string,
  mode: AnalyzeMode,
  warning: string,
): AnalyzeResponse {
  return {
    ...createEmptyAnalysis(text, mode, "frontend_local_fallback"),
    runtime_warnings: [warning],
    backend_warning:
      "Suggestions are disabled because the backend is unavailable and browser fallback is off.",
  };
}

function loadOrCreateLocalUserId(): string {
  if (typeof window === "undefined") {
    return "anonymous-web-editor";
  }
  const existing = window.localStorage.getItem(USER_PROFILE_ID_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const created =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `anon-${Date.now().toString(36)}`;
  window.localStorage.setItem(USER_PROFILE_ID_STORAGE_KEY, created);
  return created;
}

function upsertUnique(
  items: string[] | null | undefined,
  value: string,
): string[] {
  const normalized = value.trim().replace(/\s+/g, " ");
  const safeItems = Array.isArray(items) ? items : [];
  if (!normalized || safeItems.includes(normalized)) {
    return safeItems;
  }
  return [...safeItems, normalized];
}

function modeFromWritingGoal(
  writingGoal: ShuddhoPreferences["writing_goal"],
): AnalyzeMode {
  if (
    writingGoal === "formal" ||
    writingGoal === "academic" ||
    writingGoal === "business"
  ) {
    return "formal";
  }
  return "standard";
}
