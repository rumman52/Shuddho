import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import sampleFixtures from "@shared/fixtures/bangla_samples.json";
import type {
  AnalyzeMode,
  AnalyzeResponse,
  HealthDeepResponse,
  RewriteIntent,
  RewriteResponse,
  Suggestion,
  SuggestionAlternative,
  ToneAnalysisResponse,
} from "@shared/schemas/contracts";

import { SuggestionCard } from "./components/SuggestionCard";
import { CompetitionDemoPanel } from "./components/CompetitionDemoPanel";
import {
  analyzeText,
  type BackendHealthResponse,
  getApiBaseUrl,
  getApiConfiguration,
  getHealth,
  getHealthDeep,
  getLlmDebug,
  type LlmDebugResponse,
  getUserPreferences,
  rewriteText,
  saveUserPreferences,
  sendFeedback,
  setApiBaseUrlOverride,
  clearApiBaseUrlOverride,
  friendlyLlmWarning,
} from "./lib/api";
import { createEmptyAnalysis, normalizeAnalyzeResponse } from "./lib/analysis";
import { getPrimaryReplacement } from "./lib/suggestionAdapter";
import { applySuggestionTransaction, applySuggestionBatchTransaction } from "./lib/suggestionTransaction";
import { isAiUnavailableStatus } from "./lib/llmStatus";
import { analyzeTextLocally } from "./lib/localAnalysis";
import {
  competitionDemoFixtures,
  isCompetitionDemoModeEnabled,
  runCompetitionDemoReview,
  type CompetitionDemoFixture,
} from "./lib/competitionDemo";
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
const BACKEND_DEEP_HEALTH_DEGRADED_MESSAGE =
  "Backend connected, but deep health check is degraded or still warming up.";
const SUGGESTIONS_DISABLED_MESSAGE = BACKEND_UNAVAILABLE_MESSAGE;
const REQUEST_TIMEOUT_MESSAGE =
  "Request timed out. Please try again or check backend deployment.";
const DEV_LOCAL_FALLBACK_DESCRIPTION = "Dev-only browser fallback";
const COMPETITION_DEMO_MODE = isCompetitionDemoModeEnabled();

type AnalysisRequestState =
  | "idle"
  | "debouncing"
  | "queued"
  | "checking"
  | "waiting_for_ai"
  | "success"
  | "empty"
  | "error"
  | "cancelled"
  | "superseded";

type AnalysisSnapshot = {
  requestId: number;
  text: string;
  mode: AnalyzeMode;
  personalDictionary: string[];
  userId: string;
  includeLLM: boolean;
  asyncLLM: boolean;
  manual: boolean;
  createdAt: number;
};

type ApiCheckDiagnostic = {
  responseReceived: "yes" | "no";
  httpStatus: number | null;
  requestId: number | null;
  accepted: boolean | null;
  discardReason: string | null;
  responseSuggestionCount: number | null;
  durationMs: number | null;
  responseShape: string | null;
  rejectionReason: string | null;
};

const EMPTY_API_CHECK_DIAGNOSTIC: ApiCheckDiagnostic = {
  responseReceived: "no",
  httpStatus: null,
  requestId: null,
  accepted: null,
  discardReason: null,
  responseSuggestionCount: null,
  durationMs: null,
  responseShape: null,
  rejectionReason: null,
};

type BackendMode =
  | "checking"
  | "connected"
  | "degraded"
  | "ready"
  | "unavailable"
  | "misconfigured";

type InlineSegment = {
  key: string;
  text: string;
  suggestion: Suggestion | null;
};

type SafeApplyResult = {
  text: string;
  applied: number;
  skipped: number;
  appliedIds: string[];
};

type FriendlyStatus = { label: string; tone: "ok" | "warn" | "error" | "info" };

export default function App() {
  const [text, setText] = useState(INITIAL_TEXT);
  const [mode, setMode] = useState<AnalyzeMode>("standard");
  const [userId] = useState(loadOrCreateLocalUserId);
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
  const [, setTone] = useState<ToneAnalysisResponse | null>(null);
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
    "all" | "spelling" | "grammar" | "punctuation" | "spacing" | "clarity"
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
  const [backendHealthDiagnostic, setBackendHealthDiagnostic] = useState<
    string | null
  >(null);
  const [llmDebug, setLlmDebug] = useState<LlmDebugResponse | null>(null);
  const [llmDebugDiagnostic, setLlmDebugDiagnostic] = useState<string | null>(
    null,
  );
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
  const latestTextRef = useRef(text);
  const latestSnapshotRef = useRef<AnalysisSnapshot | null>(null);
  const pendingSnapshotRef = useRef<AnalysisSnapshot | null>(null);
  const activeSnapshotRef = useRef<AnalysisSnapshot | null>(null);
  const activeControllerRef = useRef<AbortController | null>(null);
  const processingRef = useRef(false);
  const requestSequenceRef = useRef(0);
  const latestRequestIdRef = requestSequenceRef;
  const manualAnalysisInFlightRef = useRef(false);
  const aiReviewInFlightRef = useRef(false);
  const activeAnalysisRef = activeSnapshotRef;
  const queuedAnalysisRef = pendingSnapshotRef;
  const apiCheckReachableRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [analysisState, setAnalysisState] = useState<AnalysisRequestState>("idle");
  const [apiCheckDiagnostic, setApiCheckDiagnostic] = useState<ApiCheckDiagnostic>(
    EMPTY_API_CHECK_DIAGNOSTIC,
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileReviewOpen, setMobileReviewOpen] = useState(false);
  const [bulkApplyResult, setBulkApplyResult] = useState<string | null>(null);
  const [selectedCompetitionFixtureId, setSelectedCompetitionFixtureId] = useState<string | null>(
    COMPETITION_DEMO_MODE ? (competitionDemoFixtures[0]?.id ?? null) : null,
  );
  const [loadedCompetitionFixtureId, setLoadedCompetitionFixtureId] = useState<string | null>(null);
  const [competitionReviewDurationMs, setCompetitionReviewDurationMs] = useState<number | null>(null);
  const competitionDemoActive = COMPETITION_DEMO_MODE && loadedCompetitionFixtureId !== null;

  const normalizedAnalysis = useMemo(
    () => normalizeAnalyzeResponse(analysis, text, mode),
    [analysis, mode, text],
  );

  const runtimeDescriptor = useMemo(
    () =>
      describeRuntimeState({
        analysis: normalizedAnalysis,
        transport: backendTransportForRuntime(backendMode),
        health:
          backendHealth?.ok === true || backendHealth?.status === "ok"
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
      punctuation: suggestions.filter(
        (suggestion) => displaySuggestionType(suggestion) === "Punctuation",
      ).length,
      spacing: suggestions.filter(
        (suggestion) => displaySuggestionType(suggestion) === "Spacing",
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
  const suggestionSourceSummary = useMemo(
    () => describeSuggestionSources(suggestions, normalizedAnalysis),
    [normalizedAnalysis, suggestions],
  );
  const lastAnalysisResult = useMemo(
    () => ({
      suggestionCount: suggestions.length,
      localSuggestionCount: normalizedAnalysis.local_suggestion_count ?? 0,
      aiSuggestionCount: normalizedAnalysis.ai_suggestion_count ?? 0,
      llmStatus: normalizedAnalysis.llm_status ?? "not_requested",
      warnings: normalizedAnalysis.runtime_warnings ?? [],
      timings:
        (normalizedAnalysis.llm as Record<string, unknown> | null | undefined)
          ?.timings ??
        normalizedAnalysis.diagnostics ??
        {},
    }),
    [normalizedAnalysis, suggestions.length],
  );
  const connectivityBanner = competitionDemoActive
    ? null
    : apiConfiguration.hardWarning
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
    latestTextRef.current = text;
  }, [text]);

  useEffect(() => {
    if (competitionDemoActive) {
      cancelNormalAnalysisForCompetitionDemo("active_demo");
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
    competitionDemoActive,
  ]);

  async function refreshBackendHealth() {
    if (!apiConfiguration.backendAllowed) {
      setBackendMode("misconfigured");
      setBackendHealth(null);
      setShallowHealth(null);
      setLlmDebug(null);
      setLlmDebugDiagnostic(apiConfiguration.hardWarning);
      setBackendHealthDiagnostic(apiConfiguration.hardWarning);
      setStatus(
        apiConfiguration.localFallbackEnabled
          ? DEV_LOCAL_FALLBACK_DESCRIPTION
          : (apiConfiguration.hardWarning ?? SUGGESTIONS_DISABLED_MESSAGE),
      );
      return;
    }

    let health: BackendHealthResponse;
    try {
      health = await getHealth();
      setShallowHealth(health);
      if (health?.ok !== true) {
        throw new Error("Backend health response did not report ok:true.");
      }
      setBackendMode("connected");
      setBackendHealth(health);
      setBackendHealthDiagnostic(null);
      setStatus("Backend connected.");
      try {
        setLlmDebug(await getLlmDebug());
        setLlmDebugDiagnostic(null);
      } catch (debugError) {
        const debugMessage =
          debugError instanceof Error
            ? debugError.message
            : String(debugError ?? "Unknown LLM debug error");
        setLlmDebug(null);
        setLlmDebugDiagnostic(debugMessage);
      }
    } catch (error) {
      if ((import.meta as ImportMeta & { env?: { DEV?: boolean } }).env?.DEV) {
        console.debug("Backend /health check failed", error);
      }
      const message =
        error instanceof Error
          ? error.message
          : String(error ?? "Unknown health check error");
      setBackendHealth(null);
      setShallowHealth(null);
      setLlmDebug(null);
      setLlmDebugDiagnostic(message);
      setBackendHealthDiagnostic(message);
      if (apiCheckReachableRef.current) {
        setBackendMode("connected");
        setStatus(
          "Backend connected through /api/check; /health diagnostics are stale or unavailable.",
        );
      } else {
        setBackendMode("unavailable");
        setStatus(
          apiConfiguration.localFallbackEnabled
            ? DEV_LOCAL_FALLBACK_DESCRIPTION
            : `${BACKEND_UNAVAILABLE_MESSAGE} ${friendlyHealthFailure(message)}`,
        );
      }
      return;
    }

    try {
      const deepHealth = await getHealthDeep();
      setBackendHealth(deepHealth);
      const nextMode = deriveBackendModeFromHealth(health, deepHealth);
      setBackendMode(nextMode);
      setBackendHealthDiagnostic(null);
      if (nextMode === "degraded") {
        setStatus(BACKEND_DEEP_HEALTH_DEGRADED_MESSAGE);
      } else if (nextMode === "ready") {
        setStatus("Backend connected and engines loaded.");
      } else {
        setStatus("Backend connected.");
      }
    } catch (error) {
      if ((import.meta as ImportMeta & { env?: { DEV?: boolean } }).env?.DEV) {
        console.debug("Backend /health/deep check failed", error);
      }
      const message =
        error instanceof Error
          ? error.message
          : String(error ?? "Unknown deep health check error");
      setBackendMode("degraded");
      setBackendHealth({
        ...health,
        status: "degraded",
        backend_warning: BACKEND_DEEP_HEALTH_DEGRADED_MESSAGE,
      });
      setBackendHealthDiagnostic(message);
      setStatus(BACKEND_DEEP_HEALTH_DEGRADED_MESSAGE);
    }
  }

  async function retestBackendDiagnostics() {
    setBackendMode("checking");
    setStatus("Retesting backend diagnostics.");
    await refreshBackendHealth();
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
    if (analysisTimerRef.current) {
      window.clearTimeout(analysisTimerRef.current);
    }
    const includeLLM = autoAiReview;
    analysisTimerRef.current = window.setTimeout(
      () => enqueueAnalysis(nextText, includeLLM, false),
      includeLLM ? AUTO_AI_ANALYSIS_DEBOUNCE_MS : ANALYSIS_DEBOUNCE_MS,
    );
  }

  const enqueueAnalysis = useCallback(
    (nextText: string, includeLLM: boolean, manual = false) => {
      const snapshot: AnalysisSnapshot = {
        requestId: latestRequestIdRef.current + 1,
        text: nextText,
        mode,
        personalDictionary: [...(preferences.personal_dictionary ?? [])],
        userId,
        includeLLM,
        // Manual Deep AI Review must be a direct frontend → backend → Gemma
        // request. In-memory async job polling is unsafe on Render because jobs
        // can disappear across sleeps, restarts, or workers.
        asyncLLM: false,
        manual,
        createdAt: Date.now(),
      };
      latestRequestIdRef.current = snapshot.requestId;
      latestSnapshotRef.current = snapshot;
      queuedAnalysisRef.current = snapshot;
      activeControllerRef.current?.abort();
      setAnalysisState(activeAnalysisRef.current ? "queued" : "checking");
      if (includeLLM) {
        aiReviewInFlightRef.current = true;
        manualAnalysisInFlightRef.current = true;
        setIsChecking(true);
      }
      void processLatestAnalysisQueue();
    },
    [mode, preferences.personal_dictionary, userId],
  );

  async function processLatestAnalysisQueue() {
    if (processingRef.current || activeAnalysisRef.current) {
      return;
    }
    processingRef.current = true;
    try {
      while (queuedAnalysisRef.current) {
        const snapshot = queuedAnalysisRef.current;
        queuedAnalysisRef.current = null;
        activeAnalysisRef.current = snapshot;
        setAnalysisState("checking");
        await runAnalysis(snapshot);
        if (activeAnalysisRef.current?.requestId === snapshot.requestId) {
          activeAnalysisRef.current = null;
        }
      }
    } finally {
      processingRef.current = false;
    }
  }

  async function runAnalysis(snapshot: AnalysisSnapshot) {
    const { includeLLM, requestId } = snapshot;
    const legacyQuickCheckContract = {
      includeLLM,
      asyncLLM: false,
    };
    void legacyQuickCheckContract;
    const startedAt = performance.now();

    const setDiagnostic = (patch: Partial<ApiCheckDiagnostic>) => {
      setApiCheckDiagnostic((current) => ({
        ...current,
        requestId,
        durationMs: Math.round(performance.now() - startedAt),
        ...patch,
      }));
    };

    const isCurrentRequest = () =>
      snapshot.requestId === latestRequestIdRef.current &&
      snapshot.text === latestTextRef.current;

    if (!snapshot.text.trim()) {
      if (isCurrentRequest()) {
        setAnalysis(createEmptyAnalysis(snapshot.text, snapshot.mode));
        setTone(null);
        setRewriteResult(null);
        setAnalysisState("empty");
        setStatus("Analysis complete — no issues found.");
      }
      return;
    }

    if (!apiConfiguration.backendAllowed) {
      if (isCurrentRequest()) {
        setAnalysis(
          apiConfiguration.localFallbackEnabled
            ? buildLocalFallbackResponse(snapshot.text, snapshot.mode, snapshot.personalDictionary)
            : createUnavailableAnalysis(
                snapshot.text,
                snapshot.mode,
                "backend_misconfigured_contextual_disabled",
              ),
        );
        setBackendMode("misconfigured");
        setStatus(
          apiConfiguration.localFallbackEnabled
            ? DEV_LOCAL_FALLBACK_DESCRIPTION
            : (apiConfiguration.hardWarning ?? SUGGESTIONS_DISABLED_MESSAGE),
        );
        setTone(null);
        setRewriteResult(null);
        setAnalysisState("error");
      }
      return;
    }

    try {
      const controller = new AbortController();
      analysisAbortRef.current = controller;
      activeControllerRef.current = controller;
      setDiagnostic({ responseReceived: "no", httpStatus: null, accepted: null, discardReason: null, responseSuggestionCount: null, responseShape: null, rejectionReason: null });
      const response = await analyzeText(
        {
          text: snapshot.text,
          mode: snapshot.mode,
          personal_dictionary: snapshot.personalDictionary,
          user_id: snapshot.userId,
        },
        {
          includeLLM,
          // Auto quick checks still use asyncLLM: false; Deep AI Review sets snapshot.asyncLLM.
          asyncLLM: snapshot.asyncLLM,
          llmMode: includeLLM ? "review_candidates" : "none",
          mode: includeLLM ? "smart" : "fast",
          signal: controller.signal,
        },
      );
      const normalizedResponse = normalizeAnalyzeResponse(
        response,
        snapshot.text,
        snapshot.mode,
      );
      const responseSuggestions = Array.isArray(normalizedResponse.suggestions)
        ? normalizedResponse.suggestions
        : [];
      setDiagnostic({
        responseReceived: "yes",
        httpStatus: readDiagnosticNumber(normalizedResponse.diagnostics, "http_status"),
        responseShape: describeResponseShape(response),
        responseSuggestionCount: responseSuggestions.length,
      });
      if (!isCurrentRequest()) {
        setDiagnostic({ accepted: false, discardReason: "stale_request_or_text" });
        return;
      }
      setDiagnostic({ accepted: true, discardReason: null });
      setAnalysis(normalizedResponse);
      apiCheckReachableRef.current = true;
      const checkReachableHealth =
        normalizeShallowHealthAfterSuccessfulCheck(shallowHealth);
      if (checkReachableHealth !== shallowHealth) {
        setShallowHealth(checkReachableHealth);
      }
      setBackendHealthDiagnostic(null);
      const nextBackendMode = deriveBackendModeAfterSuccessfulCheck(
        checkReachableHealth,
        backendHealth,
      );
      setBackendMode(nextBackendMode);
      const responseWarnings = Array.isArray(
        normalizedResponse.runtime_warnings,
      )
        ? normalizedResponse.runtime_warnings.filter(Boolean)
        : [];
      const llmStatusMessage = friendlyLlmWarning(normalizedResponse as never);
      setStatus(
        responseSuggestions.length === 0
          ? "Analysis complete — no issues found by the available checks."
          : includeLLM
            ? (llmStatusMessage ?? "AI review complete.")
            : `${responseSuggestions.length} local suggestions ready`,
      );
      setAnalysisState(responseSuggestions.length ? "success" : "empty");
      if (!responseSuggestions.length && responseWarnings.length) {
        setStatus(`Analysis complete — no issues found. Backend warnings: ${responseWarnings.join(", ")}`);
      }
      setTone(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "";
      const aborted = message.includes("Request aborted") ||
        (error instanceof DOMException && error.name === "AbortError");
      if (aborted) {
        if (isCurrentRequest()) {
          setAnalysisState("cancelled");
          setStatus("Analysis cancelled.");
        }
        setDiagnostic({ responseReceived: "no", accepted: false, discardReason: "cancelled", rejectionReason: "request_aborted" });
        return;
      }
      const checkErrorMessage = describeAnalyzeTextError(message, includeLLM);
      setDiagnostic({ responseReceived: "no", accepted: false, discardReason: "error", rejectionReason: sanitizeDiagnosticError(checkErrorMessage) });
      if (!isCurrentRequest()) {
        return;
      }
      const shouldMarkOffline = checkErrorMessage.startsWith(
        "Browser could not reach backend",
      );
      if (
        message.includes("HTTP 422") ||
        message.includes("Backend validation failed:")
      ) {
        setStatus(
          "Backend validation failed. Request payload does not match /api/check schema.",
        );
        setAnalysisState("error");
        return;
      }
      setAnalysis(
        apiConfiguration.localFallbackEnabled
          ? buildLocalFallbackResponse(
              snapshot.text,
              snapshot.mode,
              snapshot.personalDictionary,
            )
          : createUnavailableAnalysis(
              snapshot.text,
              snapshot.mode,
              "backend_offline_contextual_disabled",
            ),
      );
      if (shouldMarkOffline) {
        apiCheckReachableRef.current = false;
      }
      setBackendMode(
        shouldMarkOffline
          ? "unavailable"
          : deriveBackendModeFromHealth(shallowHealth, backendHealth),
      );
      setTone(null);
      setRewriteResult(null);
      setStatus(
        apiConfiguration.localFallbackEnabled && shouldMarkOffline
          ? DEV_LOCAL_FALLBACK_DESCRIPTION
          : checkErrorMessage,
      );
      setAnalysisState("error");
    } finally {
      if (activeAnalysisRef.current?.requestId === requestId && includeLLM) {
        manualAnalysisInFlightRef.current = false;
        aiReviewInFlightRef.current = false;
        if (activeControllerRef.current === analysisAbortRef.current) {
          activeControllerRef.current = null;
        }
        setIsChecking(Boolean(queuedAnalysisRef.current?.includeLLM));
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
    activeControllerRef.current?.abort();
    const transaction = applySuggestionTransaction(text, suggestion, replacement, suggestions);
    if (!transaction.ok) {
      setStatus(transaction.message);
      setAnalysis((current) => ({ ...current, suggestions: [] }));
      setSelectedSuggestionId(null);
      setActiveInlineSuggestionId(null);
      return;
    }
    setText(transaction.text);
    latestTextRef.current = transaction.text;
    setAnalysis((current) => ({ ...current, suggestions: transaction.suggestions }));
    setSelectedSuggestionId(null);
    setActiveInlineSuggestionId(null);
    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (textarea) {
        textarea.focus();
        textarea.setSelectionRange(transaction.caret, transaction.caret);
      }
    });
    setStatus("Suggestion applied");
    void sendFeedbackIfOnline({
      suggestion_id: candidate.id,
      action: "accepted",
      text: transaction.text,
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
      replacement: getPrimaryReplacement(suggestion) || null,
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
      replacement: getPrimaryReplacement(suggestion) || null,
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

  function cancelNormalAnalysisForCompetitionDemo(reason: string) {
    if (analysisTimerRef.current) {
      window.clearTimeout(analysisTimerRef.current);
      analysisTimerRef.current = null;
    }
    analysisAbortRef.current?.abort();
    activeControllerRef.current?.abort();
    queuedAnalysisRef.current = null;
    pendingSnapshotRef.current = null;
    activeAnalysisRef.current = null;
    latestSnapshotRef.current = null;
    latestRequestIdRef.current += 1;
    manualAnalysisInFlightRef.current = false;
    aiReviewInFlightRef.current = false;
    setIsChecking(false);
    setAnalysisState("idle");
    setApiCheckDiagnostic({ ...EMPTY_API_CHECK_DIAGNOSTIC, discardReason: reason });
    setSelectedSuggestionId(null);
    setActiveInlineSuggestionId(null);
    setBulkApplyResult(null);
  }

  function runLoadedCompetitionFixture(fixture: CompetitionDemoFixture) {
    if (!COMPETITION_DEMO_MODE) return;
    cancelNormalAnalysisForCompetitionDemo("competition_demo_started");
    const fixtureText = fixture.incorrectText;
    setSelectedCompetitionFixtureId(fixture.id);
    setLoadedCompetitionFixtureId(fixture.id);
    setText(fixtureText);
    latestTextRef.current = fixtureText;
    const startedAt = performance.now();
    const response = runCompetitionDemoReview(fixture.id, fixtureText);
    const duration = performance.now() - startedAt;
    setCompetitionReviewDurationMs(duration);
    setAnalysis(response);
    setAnalysisState(response.suggestions.length ? "success" : "empty");
    setReviewFilter("all");
    setStatus(`${response.suggestions.length} local demo suggestions ready.`);
  }

  function handleSelectCompetitionFixture(fixtureId: string | null) {
    setSelectedCompetitionFixtureId(fixtureId);
    setLoadedCompetitionFixtureId(null);
    setCompetitionReviewDurationMs(null);
  }

  function handleLoadCompetitionExample(fixture: CompetitionDemoFixture) {
    runLoadedCompetitionFixture(fixture);
  }

  function handleRunCompetitionDemoReview() {
    const fixture = competitionDemoFixtures.find((item) => item.id === selectedCompetitionFixtureId) ?? null;
    if (!fixture) {
      setStatus("Select a prepared competition example before running local review.");
      return;
    }
    runLoadedCompetitionFixture(fixture);
  }

  function handleResetCompetitionExample() {
    const fixture = competitionDemoFixtures.find((item) => item.id === selectedCompetitionFixtureId) ?? null;
    if (!fixture) {
      setStatus("Select a prepared competition example before resetting.");
      return;
    }
    runLoadedCompetitionFixture(fixture);
  }

  function handleTryOwnText() {
    cancelNormalAnalysisForCompetitionDemo("competition_demo_exit");
    setLoadedCompetitionFixtureId(null);
    setSelectedCompetitionFixtureId(null);
    setCompetitionReviewDurationMs(null);
    setAnalysis(createEmptyAnalysis(text, mode));
    setStatus("Try your own text. Normal production checks remain available.");
  }

  function handleCheckWriting() {
    if (isChecking) {
      return;
    }

    if (analysisTimerRef.current) {
      window.clearTimeout(analysisTimerRef.current);
      analysisTimerRef.current = null;
    }

    aiReviewInFlightRef.current = true;
    setStatus("Reviewing with AI");
    enqueueAnalysis(text, true, true);
  }

  function handleApplySafeSuggestions() {
    const result = applySuggestionBatchTransaction(text, suggestions);
    if (result.applied === 0 && result.skipped === 0) {
      setStatus("No safe suggestions available to apply");
      setBulkApplyResult("No safe suggestions available.");
      return;
    }
    setText(result.text);
    latestTextRef.current = result.text;
    setAnalysis((current) => ({ ...current, suggestions: result.suggestions }));
    setSelectedSuggestionId(null);
    setActiveInlineSuggestionId(null);
    const message = `${result.applied} applied, ${result.skipped} skipped`;
    setBulkApplyResult(message);
    setStatus(message);
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

  const friendlyStatus = competitionDemoActive
    ? { label: "Offline demo ready", tone: "ok" as const }
    : getFriendlyRuntimeStatus({
    backendMode,
    isChecking,
    suggestionCount: suggestions.length,
    runtimeDescriptorLabel: runtimeDescriptor.label,
    llmStatus: normalizedAnalysis.llm_status ?? null,
    sourceSummary: suggestionSourceSummary,
  });
  const reviewUnavailable = !competitionDemoActive &&
    (backendMode === "unavailable" || backendMode === "misconfigured");
  const aiUnavailable = isAiUnavailableStatus(
    normalizedAnalysis.llm_status,
    normalizedAnalysis.llm_requested,
  );

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-text" aria-label="Shuddho home">
          <strong>Shuddho</strong>
          <span>Bangla Writing Assistant</span>
        </div>
        <div className="header-actions" aria-label="Workspace actions">
          <span
            className={`runtime-chip runtime-chip--${friendlyStatus.tone}`}
            role="status"
          >
            {friendlyStatus.label}
          </span>
          <span className="header-wordcount" aria-label="Word count">
            {wordCount} words
          </span>
          <button
            type="button"
            className="ghost-button"
            onClick={() => setSettingsOpen(true)}
          >
            Settings
          </button>
          {competitionDemoActive ? (
            <button type="button" className="button-secondary header-review-button" onClick={handleTryOwnText}>
              Exit demo / Try own text
            </button>
          ) : (
            <button
              type="button"
              className="button-primary header-review-button"
              onClick={handleCheckWriting}
              disabled={isChecking || !text.trim()}
            >
              {isChecking ? "Checking" : "Deep AI Review"}
            </button>
          )}
        </div>
      </header>

      <div className="sr-only" aria-live="polite">
        {status}
      </div>
      {preferencesWarning || connectivityBanner ? (
        <div className="runtime-banner" role="status">
          <strong>{reviewUnavailable ? "Limited mode" : "Notice"}</strong>
          <span>{preferencesWarning ?? connectivityBanner}</span>
          {reviewUnavailable ? (
            <button
              type="button"
              className="text-button"
              onClick={() => void retestBackendDiagnostics()}
            >
              Retry
            </button>
          ) : null}
        </div>
      ) : null}

      <section
        className="workspace"
        aria-label="Bangla writing assistant workspace"
      >
        <section className="editor-column" aria-label="Writing workspace">
          {COMPETITION_DEMO_MODE ? (
            <CompetitionDemoPanel
              selectedFixtureId={selectedCompetitionFixtureId}
              loadedFixtureId={loadedCompetitionFixtureId}
              onSelectFixture={handleSelectCompetitionFixture}
              onLoadExample={handleLoadCompetitionExample}
              onRunDemoReview={handleRunCompetitionDemoReview}
              onResetExample={handleResetCompetitionExample}
              onTryOwnText={handleTryOwnText}
              reviewDurationMs={competitionReviewDurationMs}
            />
          ) : null}
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
            <button
              type="button"
              className="review-toggle"
              onClick={() => setMobileReviewOpen(true)}
            >
              Review · {suggestions.length}
            </button>
          </div>

          <article className="editor-card" aria-busy={isChecking}>
            <div className="editor-card__header">
              <div>
                <p className="eyebrow">Document</p>
                <h1>Write in Bangla with context-aware review</h1>
              </div>
              <p className="editor-card__status">
                {suggestions.length
                  ? `${suggestions.length} suggestions ready.`
                  : "Start writing; quick checks run quietly."}
              </p>
            </div>
            <div className="editor-frame">
              <div className="editor-highlight-layer" aria-hidden="false">
                {inlineSegments.map((segment) => {
                  if (!segment.suggestion)
                    return <span key={segment.key}>{segment.text}</span>;
                  const suggestion = segment.suggestion;
                  const replacement = getPrimaryReplacement(suggestion);
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
                    >
                      {segment.text}
                      {isActive ? (
                        <span
                          className="correction-popover"
                          role="dialog"
                          aria-label="Inline suggestion"
                        >
                          <button
                            type="button"
                            className="popover-close"
                            aria-label="Close suggestion"
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
                            <button
                              type="button"
                              className="text-button"
                              onClick={() =>
                                void handleRewrite("clarity", suggestion)
                              }
                            >
                              Explain
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
                placeholder="এখানে বাংলা লেখা শুরু করুন। Shuddho বানান, ব্যাকরণ, স্পষ্টতা ও প্রবাহ নিয়ে পরামর্শ দেবে।"
                value={text}
                onChange={(event) => setText(event.target.value)}
                onSelect={handleSelectionChange}
                onKeyUp={handleSelectionChange}
                onClick={handleSelectionChange}
                onScroll={handleEditorScroll}
                onKeyDown={(event) => {
                  if (event.key === "Escape") setActiveInlineSuggestionId(null);
                }}
              />
            </div>
            <div className="editor-statusbar">
              <span>{wordCount} words</span>
              <span>{characterCount} characters</span>
              <span>
                {suggestionSourceSummary === "hybrid"
                  ? "Local + AI"
                  : suggestionSourceSummary === "ai"
                    ? "AI"
                    : suggestionSourceSummary === "local"
                      ? "Local"
                      : "Ready"}
              </span>
            </div>
          </article>

          {rewriteResult ? (
            <section className="rewrite-panel" aria-label="Rewrite options">
              <div className="review-panel__header">
                <h2>Rewrite options</h2>
                <button
                  type="button"
                  className="text-button"
                  onClick={dismissRewrite}
                >
                  Dismiss
                </button>
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
            </section>
          ) : null}
        </section>

        <aside
          className={`review-panel ${mobileReviewOpen ? "review-panel--open" : ""}`}
          aria-label="Review suggestions"
        >
          <div className="review-panel__header">
            <div>
              <h2>Review</h2>
              <p className="review-count">{suggestions.length} suggestions</p>
            </div>
            <button
              type="button"
              className="review-close"
              aria-label="Close review"
              onClick={() => setMobileReviewOpen(false)}
            >
              ×
            </button>
          </div>
          <p className="review-panel__status">
            {analysisState === "checking" || analysisState === "queued" || analysisState === "waiting_for_ai"
              ? analysisState === "queued"
                ? "Latest edit queued for review…"
                : analysisState === "waiting_for_ai"
                  ? "AI review in progress…"
                  : "Checking your full text with AI…"
              : getReviewStatusCopy({
                  suggestions: suggestions.length,
                  competitionDemoActive,
                  reviewUnavailable,
                  aiUnavailable,
                  status,
                  llmStatus: normalizedAnalysis.llm_status,
                })}
          </p>
          {reviewUnavailable ? (
            <button
              type="button"
              className="button-secondary"
              onClick={() => void retestBackendDiagnostics()}
            >
              Retry backend
            </button>
          ) : null}
          <div
            className="review-tabs"
            role="tablist"
            aria-label="Suggestion filters"
          >
            {(
              [
                ["all", "All", suggestions.length],
                ["spelling", "Spelling", suggestionCounts.spelling],
                ["grammar", "Grammar", suggestionCounts.grammar],
                ["punctuation", "Punctuation", suggestionCounts.punctuation],
                ["spacing", "Spacing", suggestionCounts.spacing],
                ["clarity", "Clarity", suggestionCounts.clarity],
              ] as const
            ).map(([filter, label, count]) => (
              <button
                key={filter}
                type="button"
                role="tab"
                aria-selected={reviewFilter === filter}
                className={
                  reviewFilter === filter
                    ? "review-tab review-tab--active"
                    : "review-tab"
                }
                onClick={() => setReviewFilter(filter)}
              >
                {label} <strong>{count}</strong>
              </button>
            ))}
          </div>
          <div className="review-actions">
            <button
              type="button"
              className="button-secondary"
              onClick={handleApplySafeSuggestions}
            >
              Apply safe suggestions
            </button>
            <button
              type="button"
              className="text-button"
              onClick={handleDismissAll}
            >
              Dismiss all
            </button>
          </div>
          {bulkApplyResult ? (
            <p className="quiet-note" role="status">
              {bulkApplyResult}
            </p>
          ) : null}
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
                  onMouseEnter={() =>
                    setActiveInlineSuggestionId(suggestion.id)
                  }
                  onFocus={() => setActiveInlineSuggestionId(suggestion.id)}
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
            <div className="empty-state">
              {analysisState === "checking" || analysisState === "queued" || analysisState === "waiting_for_ai"
                ? "Review is running. You can keep typing."
                : analysisState === "empty"
                  ? "Analysis complete — no issues found."
                  : analysisState === "error"
                    ? status
                    : text.trim()
                      ? "Your writing looks clear."
                      : "Suggestions will appear here as you write."}
            </div>
          )}
          {normalizedAnalysis.corrected_text &&
          normalizedAnalysis.corrected_text !== text ? (
            <details className="corrected-preview">
              <summary>Corrected text preview</summary>
              <p>{normalizedAnalysis.corrected_text}</p>
            </details>
          ) : null}
        </aside>
      </section>

      {settingsOpen ? (
        <div
          className="drawer-backdrop"
          role="presentation"
          onClick={() => setSettingsOpen(false)}
        >
          <aside
            className="settings-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Settings"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape") setSettingsOpen(false);
            }}
          >
            <div className="review-panel__header">
              <h2>Settings</h2>
              <button
                type="button"
                className="review-close"
                aria-label="Close settings"
                onClick={() => setSettingsOpen(false)}
              >
                ×
              </button>
            </div>
            <label>
              Writing goal
              <select
                value={preferences.writing_goal}
                onChange={(event) =>
                  setPreferences((current) => ({
                    ...current,
                    writing_goal: event.target
                      .value as ShuddhoPreferences["writing_goal"],
                  }))
                }
              >
                <option value="general">General</option>
                <option value="formal">Formal</option>
                <option value="academic">Academic</option>
                <option value="business">Business</option>
                <option value="casual">Casual</option>
                <option value="social">Social</option>
              </select>
            </label>
            <label>
              Tone
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
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={autoAiReview}
                onChange={(event) => setAutoAiReview(event.target.checked)}
              />
              <span>Auto AI review</span>
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
              <span>Rewrite suggestions</span>
            </label>
            <label>
              Personal dictionary
              <input
                value={dictionaryDraft}
                placeholder="নতুন শব্দ"
                onChange={(event) => setDictionaryDraft(event.target.value)}
              />
            </label>
            <button
              type="button"
              className="button-secondary"
              onClick={() => {
                setPreferences((current) => ({
                  ...current,
                  personal_dictionary: upsertUnique(
                    current.personal_dictionary,
                    dictionaryDraft,
                  ),
                }));
                setDictionaryDraft("");
              }}
            >
              Add word
            </button>
            <button
              type="button"
              className="button-primary"
              onClick={() => void savePreferencesToBackend()}
            >
              Save settings
            </button>
            {debugMode ||
            (import.meta as ImportMeta & { env?: { DEV?: boolean } }).env
              ?.DEV ? (
              <details className="developer-diagnostics">
                <summary>Developer diagnostics</summary>
                <label>
                  Backend URL override
                  <input
                    value={apiBaseUrlDraft}
                    onChange={(event) => setApiBaseUrlDraft(event.target.value)}
                  />
                </label>
                <div className="row">
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={applyApiBaseUrl}
                  >
                    Apply URL
                  </button>
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={resetApiBaseUrl}
                  >
                    Reset API URL override
                  </button>
                </div>
                <pre>
                  {JSON.stringify(
                    {
                      apiBaseUrl,
                      backendMode,
                      backendHealthDiagnostic,
                      llmDebugDiagnostic,
                      lastAnalysisResult,
                      apiCheckDiagnostic,
                      analysisState,
                      llmDebug,
                      runtimeDescriptor: runtimeDescriptor.diagnostics,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            ) : (
              <button
                type="button"
                className="text-button"
                onClick={() => setDebugMode(true)}
              >
                Show developer diagnostics
              </button>
            )}
            <p className="quiet-note production-debug-line">
              API base URL: hidden in normal mode · API config source:{" "}
              {apiConfiguration.source} · backendMode: {backendMode} · last
              health error: {backendHealthDiagnostic ?? "none"} · last
              /api/check: {normalizedAnalysis.llm_status ?? "not requested"}
            </p>
          </aside>
        </div>
      ) : null}
    </main>
  );
}

export function createLatestAnalysisCoordinator<TSnapshot extends { requestId: number }>(
  worker: (snapshot: TSnapshot) => Promise<void>,
) {
  let active = false;
  let queued: TSnapshot | null = null;

  const drain = async () => {
    if (active || !queued) {
      return;
    }
    const snapshot = queued;
    queued = null;
    active = true;
    try {
      await worker(snapshot);
    } finally {
      active = false;
      if (queued) {
        void drain();
      }
    }
  };

  return {
    enqueue(snapshot: TSnapshot) {
      queued = snapshot;
      void drain();
    },
    get queued() {
      return queued;
    },
    get active() {
      return active;
    },
  };
}

function describeResponseShape(response: unknown): string {
  if (!response || typeof response !== "object") {
    return typeof response;
  }
  const record = response as Record<string, unknown>;
  return Object.keys(record)
    .filter((key) => !["text", "normalized_text", "corrected_text"].includes(key))
    .sort()
    .join(",");
}

function readDiagnosticNumber(
  diagnostics: Record<string, unknown> | undefined,
  key: string,
): number | null {
  const value = diagnostics?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function sanitizeDiagnosticError(message: string): string {
  return message.replace(/(authorization|api[_-]?key|token)=([^\s&]+)/gi, "$1=[redacted]");
}

export function applySafeSuggestionBatch(
  text: string,
  suggestions: Suggestion[],
): SafeApplyResult {
  const candidates = suggestions
    .filter(
      (suggestion) => getPrimaryReplacement(suggestion).length > 0,
    )
    .sort((a, b) => a.span_start - b.span_start || a.span_end - b.span_end);
  const selected: Suggestion[] = [];
  let skipped = 0;

  for (const suggestion of candidates) {
    const validSpan =
      Number.isInteger(suggestion.span_start) &&
      Number.isInteger(suggestion.span_end) &&
      suggestion.span_start >= 0 &&
      suggestion.span_end > suggestion.span_start &&
      suggestion.span_end <= text.length;
    const stale =
      !validSpan ||
      text.slice(suggestion.span_start, suggestion.span_end) !==
        suggestion.original_text;
    const overlaps = selected.some(
      (range) =>
        suggestion.span_start < range.span_end &&
        suggestion.span_end > range.span_start,
    );
    if (stale || overlaps) {
      skipped += 1;
      continue;
    }
    selected.push(suggestion);
  }

  let draft = text;
  const appliedIds: string[] = [];
  for (const suggestion of [...selected].sort(
    (a, b) => b.span_start - a.span_start,
  )) {
    draft = replaceSpan(
      draft,
      suggestion.span_start,
      suggestion.span_end,
      getPrimaryReplacement(suggestion),
    );
    appliedIds.push(suggestion.id);
  }

  return { text: draft, applied: appliedIds.length, skipped, appliedIds };
}

function getFriendlyRuntimeStatus(args: {
  backendMode: BackendMode;
  isChecking: boolean;
  suggestionCount: number;
  runtimeDescriptorLabel: string;
  llmStatus: string | null;
  sourceSummary: "local" | "ai" | "hybrid" | "none";
}): FriendlyStatus {
  if (args.isChecking) return { label: "Checking", tone: "info" };
  if (args.backendMode === "unavailable")
    return { label: "Backend unavailable", tone: "error" };
  if (args.backendMode === "misconfigured")
    return { label: "Limited mode", tone: "warn" };
  if (
    args.sourceSummary === "ai" ||
    args.sourceSummary === "hybrid" ||
    args.llmStatus === "ok"
  ) {
    return { label: args.llmStatus === "completed" ? "Gemma review ready" : "AI review ready", tone: "ok" };
  }
  if (
    args.backendMode === "degraded" ||
    args.runtimeDescriptorLabel.toLowerCase().includes("degraded")
  ) {
    return { label: "Local checks active", tone: "warn" };
  }
  if (args.suggestionCount > 0) return { label: "Ready", tone: "ok" };
  return { label: "Ready", tone: "info" };
}

function getReviewStatusCopy(args: {
  suggestions: number;
  competitionDemoActive?: boolean;
  reviewUnavailable: boolean;
  aiUnavailable: boolean;
  status: string;
  llmStatus?: string | null;
}): string {
  if (args.competitionDemoActive) {
    return args.suggestions > 0 ? `${args.suggestions} local demo suggestions ready.` : "Offline demo ready. Load & Run Local Review to show prepared demo annotations.";
  }
  if (args.reviewUnavailable) {
    return "Contextual AI review is not connected. Retry the backend or continue only when limited local checks are available.";
  }
  if (args.status.toLowerCase().includes("timed out")) {
    return "Gemma review timed out. Local suggestions are still available. Try again.";
  }
  if (args.aiUnavailable) {
    const llmStatus = String(args.llmStatus ?? "failed");
    if (llmStatus === "invalid_json") return "Gemma returned malformed JSON, so Shuddho safely ignored it and kept local suggestions.";
    if (llmStatus === "invalid_schema") return "Gemma returned a response in the wrong format, so Shuddho safely kept local suggestions.";
    if (llmStatus === "truncated") return "Gemma’s response was incomplete. Local suggestions are still available.";
    if (llmStatus === "rate_limited") return "Gemma is temporarily rate-limited. Local suggestions are still available.";
    if (["auth_or_forbidden", "missing_key", "unsupported_provider"].includes(llmStatus)) return "Gemma is not configured correctly. Local suggestions are still available.";
    if (llmStatus === "network_error") return "Gemma could not be reached. Local suggestions are still available.";
    return "Gemma review is unavailable. Local suggestions are still available.";
  }
  if (args.suggestions > 0) {
    return `${args.suggestions} suggestions ready.`;
  }
  return "Your writing looks clear.";
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
  if (value.includes("punctuation")) {
    return "Punctuation";
  }
  if (value.includes("spacing") || value.includes("space")) {
    return "Spacing";
  }
  if (value.includes("grammar")) {
    return "Grammar";
  }
  if (
    value.includes("clarity") ||
    value.includes("style") ||
    value.includes("tone") ||
    value.includes("register")
  ) {
    return "Clarity";
  }
  return "Spelling";
}

function describeSuggestionSources(
  suggestions: Suggestion[],
  analysis: AnalyzeResponse,
): "local" | "ai" | "hybrid" | "none" {
  if (!suggestions.length) {
    return "none";
  }
  const hasAi = suggestions.some((suggestion) => {
    const metadata = (suggestion.metadata ?? {}) as Record<string, unknown>;
    const sources = Array.isArray(metadata.sources)
      ? metadata.sources.map(String)
      : [];
    return (
      suggestion.source === "model" ||
      suggestion.source === "hybrid" ||
      suggestion.provider === "gemma" ||
      sources.includes("ai")
    );
  });
  const localCount = Number(analysis.local_suggestion_count ?? 0);
  const aiCount = Number(analysis.ai_suggestion_count ?? 0);
  if ((hasAi || aiCount > 0) && localCount > 0) {
    return "hybrid";
  }
  if (hasAi || aiCount > 0) {
    return "ai";
  }
  return "local";
}

function isBackendConnected(backendMode: BackendMode): boolean {
  return ["connected", "degraded", "ready"].includes(backendMode);
}

function backendTransportForRuntime(
  backendMode: BackendMode,
): "checking" | "online" | "offline" | "misconfigured" {
  if (
    backendMode === "connected" ||
    backendMode === "degraded" ||
    backendMode === "ready"
  ) {
    return "online";
  }
  if (backendMode === "unavailable") {
    return "offline";
  }
  return backendMode;
}

function friendlyHealthFailure(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return "The backend timed out and may still be waking up on Render Free.";
  }
  if (
    lower.includes("cors") ||
    lower.includes("network") ||
    lower.includes("failed to fetch")
  ) {
    return "This looks like a CORS or network failure.";
  }
  if (lower.includes("http")) {
    return "The backend returned an HTTP error.";
  }
  if (lower.includes("json")) {
    return "The backend returned invalid JSON.";
  }
  return "";
}

export function deriveBackendModeFromHealth(
  health: Partial<BackendHealthResponse> | null,
  deepHealth: Partial<BackendHealthResponse> | null,
): BackendMode {
  if (health?.ok !== true) {
    return "unavailable";
  }
  const correctorLoaded =
    deepHealth?.corrector_loaded ?? deepHealth?.corrector?.loaded;
  const detectorLoaded =
    deepHealth?.detector_loaded ?? deepHealth?.detector?.loaded;
  if (correctorLoaded === false) {
    return "degraded";
  }
  if (correctorLoaded === true && detectorLoaded !== false) {
    return "ready";
  }
  return "connected";
}

export function normalizeShallowHealthAfterSuccessfulCheck(
  health: Partial<BackendHealthResponse> | null,
): BackendHealthResponse {
  if (health?.ok === true) {
    return health;
  }
  return { ok: true, status: "ok" };
}

export function deriveBackendModeAfterSuccessfulCheck(
  health: Partial<BackendHealthResponse> | null,
  deepHealth: Partial<BackendHealthResponse> | null,
): BackendMode {
  return deriveBackendModeFromHealth(
    normalizeShallowHealthAfterSuccessfulCheck(health),
    deepHealth,
  );
}

export function describeAnalyzeTextError(
  message: string,
  includeLLM: boolean,
): string {
  const lower = message.toLowerCase();
  if (lower.includes("timed out") || lower.includes("timeout")) {
    return includeLLM
      ? "AI review timed out. Showing local suggestions."
      : REQUEST_TIMEOUT_MESSAGE;
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
  if (
    lower.includes("backend json invalid") ||
    lower.includes("invalid json")
  ) {
    return "Backend returned invalid JSON. Check /api/check response and Render logs.";
  }
  if (lower.includes("gemma") || lower.includes("provider_error")) {
    return `Gemma provider error while reviewing. ${message}`.slice(
      0,
      240,
    );
  }
  if (
    lower.includes("network request failed") ||
    lower.includes("failed to fetch") ||
    lower.includes("cors") ||
    lower.includes("network failure")
  ) {
    return "Browser could not reach backend. Check CORS and VITE_API_BASE_URL.";
  }
  return (
    message ||
    "Backend analysis failed. Check /api/check response and Render logs."
  );
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
