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
  UserPreferences,
} from "@shared/schemas/contracts";

import { SuggestionCard } from "./components/SuggestionCard";
import {
  analyzeText,
  analyzeTone,
  getApiBaseUrl,
  getApiConfiguration,
  getHealth,
  getUserPreferences,
  rewriteText,
  saveUserPreferences,
  sendFeedback,
  setApiBaseUrlOverride,
} from "./lib/api";
import { analyzeTextLocally } from "./lib/localAnalysis";
import { canAddSuggestionToDictionary, describeRuntimeState } from "./lib/runtimeStatus";

const INITIAL_TEXT = sampleFixtures[0]?.text ?? "আমি বাংলা লিখি।। বাংলা ভাষা খুব সুন্দর !!";
const USER_PROFILE_ID_STORAGE_KEY = "shuddho-user-id";
const ANALYSIS_DEBOUNCE_MS = 450;
const BACKEND_DISABLED_MESSAGE = "Backend is not connected. Contextual Bengali correction is disabled.";
const DEV_LOCAL_FALLBACK_LABEL = "Dev-only browser fallback";
const DEV_LOCAL_FALLBACK_DESCRIPTION = "Backend is not connected. Contextual Bengali correction is disabled. Dev-only local fallback is enabled.";

type BackendMode = "checking" | "online" | "offline" | "misconfigured";

export default function App() {
  const [text, setText] = useState(INITIAL_TEXT);
  const [mode, setMode] = useState<AnalyzeMode>("standard");
  const [userId, setUserId] = useState(loadOrCreateLocalUserId);
  const [preferences, setPreferences] = useState<UserPreferences>(() => defaultPreferences(loadOrCreateLocalUserId()));
  const [dictionaryDraft, setDictionaryDraft] = useState("");
  const [analysis, setAnalysis] = useState<AnalyzeResponse>(() => createEmptyAnalysis(INITIAL_TEXT, "standard"));
  const [tone, setTone] = useState<ToneAnalysisResponse | null>(null);
  const [rewriteResult, setRewriteResult] = useState<RewriteResponse | null>(null);
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<string | null>(null);
  const [status, setStatus] = useState("Ready");
  const [backendMode, setBackendMode] = useState<BackendMode>("checking");
  const [backendHealth, setBackendHealth] = useState<HealthDeepResponse | null>(null);
  const [apiBaseUrl, setApiBaseUrl] = useState(() => getApiBaseUrl());
  const [apiBaseUrlDraft, setApiBaseUrlDraft] = useState(() => getApiBaseUrl());
  const [apiConfiguration, setApiConfiguration] = useState(() => getApiConfiguration());
  const [selection, setSelection] = useState<{ start: number; end: number }>({ start: 0, end: 0 });
  const analysisTimerRef = useRef<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const runtimeDescriptor = useMemo(
    () =>
      describeRuntimeState({
        analysis,
        transport: backendMode,
        health: backendHealth,
        hardWarning: apiConfiguration.hardWarning,
      }),
    [analysis, apiConfiguration.hardWarning, backendHealth, backendMode],
  );

  const selectedSuggestion = useMemo(
    () => analysis.suggestions.find((suggestion) => suggestion.id === selectedSuggestionId) ?? null,
    [analysis.suggestions, selectedSuggestionId],
  );

  useEffect(() => {
    window.localStorage.setItem(USER_PROFILE_ID_STORAGE_KEY, userId);
  }, [userId]);

  useEffect(() => {
    void refreshBackendHealth();
  }, [apiBaseUrl, apiConfiguration.backendAllowed, apiConfiguration.hardWarning, apiConfiguration.localFallbackEnabled]);

  useEffect(() => {
    void loadPreferences(userId);
  }, [userId, apiBaseUrl]);

  useEffect(() => {
    scheduleAnalysis(text);
    return () => {
      if (analysisTimerRef.current) {
        window.clearTimeout(analysisTimerRef.current);
      }
    };
  }, [apiBaseUrl, apiConfiguration.backendAllowed, apiConfiguration.localFallbackEnabled, text, mode, preferences.personal_dictionary, userId]);

  async function refreshBackendHealth() {
    if (!apiConfiguration.backendAllowed) {
      setBackendMode("misconfigured");
      setBackendHealth(null);
      setStatus(
        apiConfiguration.localFallbackEnabled
          ? DEV_LOCAL_FALLBACK_DESCRIPTION
          : BACKEND_DISABLED_MESSAGE,
      );
      return;
    }

    try {
      const health = await getHealth();
      setBackendHealth(health);
      setBackendMode("online");
    } catch {
      setBackendHealth(null);
      setBackendMode("offline");
      setStatus(
        apiConfiguration.localFallbackEnabled
          ? DEV_LOCAL_FALLBACK_DESCRIPTION
          : BACKEND_DISABLED_MESSAGE,
      );
    }
  }

  async function loadPreferences(nextUserId: string) {
    if (!apiConfiguration.backendAllowed) {
      setPreferences((current) => ({ ...current, user_id: nextUserId }));
      return;
    }

    try {
      const remotePreferences = await getUserPreferences(nextUserId);
      setPreferences(remotePreferences);
      setMode(modeFromWritingGoal(remotePreferences.writing_goal));
    } catch {
      setPreferences((current) => ({ ...current, user_id: nextUserId }));
    }
  }

  function scheduleAnalysis(nextText: string) {
    if (analysisTimerRef.current) {
      window.clearTimeout(analysisTimerRef.current);
    }
    analysisTimerRef.current = window.setTimeout(() => {
      void runAnalysis(nextText);
    }, ANALYSIS_DEBOUNCE_MS);
  }

  async function runAnalysis(nextText: string) {
    if (!nextText.trim()) {
      setAnalysis(createEmptyAnalysis(nextText, mode));
      setTone(null);
      setRewriteResult(null);
      return;
    }

    if (!apiConfiguration.backendAllowed) {
      setAnalysis(
        apiConfiguration.localFallbackEnabled
          ? buildLocalFallbackResponse(nextText, mode, preferences.personal_dictionary)
          : createUnavailableAnalysis(nextText, mode, "backend_misconfigured_contextual_disabled"),
      );
      setBackendMode("misconfigured");
      setStatus(
        apiConfiguration.localFallbackEnabled
          ? DEV_LOCAL_FALLBACK_DESCRIPTION
          : BACKEND_DISABLED_MESSAGE,
      );
      setTone(null);
      setRewriteResult(null);
      return;
    }

    try {
      const response = await analyzeText({
        text: nextText,
        mode,
        personal_dictionary: preferences.personal_dictionary,
        user_id: userId,
      });
      setAnalysis(response);
      setBackendMode("online");
      setStatus(response.suggestions.length ? `${response.suggestions.length} suggestions ready` : "No high-confidence correction found.");
      if (preferences.auto_show_tone && nextText.trim().length >= 20) {
        void refreshTone(nextText);
      } else {
        setTone(null);
      }
    } catch {
      setAnalysis(
        apiConfiguration.localFallbackEnabled
          ? buildLocalFallbackResponse(nextText, mode, preferences.personal_dictionary)
          : createUnavailableAnalysis(nextText, mode, "backend_offline_contextual_disabled"),
      );
      setBackendMode("offline");
      setTone(null);
      setRewriteResult(null);
      setStatus(
        apiConfiguration.localFallbackEnabled
          ? DEV_LOCAL_FALLBACK_DESCRIPTION
          : BACKEND_DISABLED_MESSAGE,
      );
    }
  }

  async function refreshTone(nextText: string) {
    if (backendMode !== "online") {
      setTone(null);
      return;
    }
    try {
      const response = await analyzeTone({ text: nextText, user_id: userId });
      setTone(response);
    } catch {
      setTone(null);
    }
  }

  function handleSelectionChange() {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    setSelection({
      start: textarea.selectionStart ?? 0,
      end: textarea.selectionEnd ?? 0,
    });
  }

  function handleApplySuggestion(candidate: Suggestion | SuggestionAlternative, replacement: string, suggestion: Suggestion) {
    const nextText = replaceSpan(text, suggestion.span_start, suggestion.span_end, replacement);
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
      suppressed_rule_keys: upsertUnique(current.suppressed_rule_keys, `${suggestion.rule_id}:${suggestion.subtype}`),
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
      personal_dictionary: upsertUnique(current.personal_dictionary, entry),
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

    const selectionStart = suggestion?.span_start ?? (selection.end > selection.start ? selection.start : null);
    const selectionEnd = suggestion?.span_end ?? (selection.end > selection.start ? selection.end : null);

    if (backendMode !== "online") {
      setStatus(BACKEND_DISABLED_MESSAGE);
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
      setRewriteResult(response);
      setStatus(response.options.length ? "Rewrite options ready" : response.warnings.join(" "));
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Rewrite failed");
    }
  }

  function applyRewriteOption(optionText: string) {
    if (!rewriteResult) {
      return;
    }
    const nextText =
      rewriteResult.selection_start !== null && rewriteResult.selection_start !== undefined && rewriteResult.selection_end !== null && rewriteResult.selection_end !== undefined
        ? replaceSpan(text, rewriteResult.selection_start, rewriteResult.selection_end, optionText)
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
    if (backendMode !== "online") {
      setStatus("Preferences saved locally for this session");
      return;
    }

    try {
      const saved = await saveUserPreferences(userId, preferences);
      setPreferences(saved);
      setStatus("Preferences saved");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not save preferences");
    }
  }

  function applyApiBaseUrl() {
    const nextBaseUrl = setApiBaseUrlOverride(apiBaseUrlDraft);
    setApiConfiguration(getApiConfiguration());
    setApiBaseUrl(nextBaseUrl);
    setStatus(`API base URL set to ${nextBaseUrl}`);
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

  function dropSuggestion(suggestionId: string) {
    setAnalysis((current) => ({
      ...current,
      suggestions: current.suggestions.filter((item) => item.id !== suggestionId),
    }));
    setSelectedSuggestionId((current) => (current === suggestionId ? null : current));
  }

  return (
    <main className="app-shell">
      <section className="hero-band">
        <div>
          <p className="eyebrow">Shuddho</p>
          <h1>Bangla writing assistant</h1>
          <p className="lede">Extension-first backend, with the web editor as the fastest place to test analysis, tone, rewrites, and preference learning.</p>
        </div>
        <div className="status-band">
          <strong>{runtimeDescriptor.label}</strong>
          <span>{status}</span>
          <span>{backendMode === "online" ? apiBaseUrl : apiConfiguration.localFallbackEnabled ? DEV_LOCAL_FALLBACK_LABEL : "Suggestions disabled"}</span>
        </div>
      </section>

      <section className="workspace-grid">
        <aside className="sidebar-panel">
          <div className="panel-block">
            <h2>Runtime</h2>
            <div className="meta-list">
              <span>Backend: {backendMode}</span>
              <span>Detector: {analysis.used_detector ? "active" : "inactive"}</span>
              <span>Corrector: {analysis.used_corrector ? "active" : "inactive"}</span>
              <span>Lexicon: {analysis.lexicon_source}</span>
            </div>
            {analysis.runtime_warnings.length ? (
              <div className="chip-row">
                {analysis.runtime_warnings.map((warning) => (
                  <span key={warning} className="chip chip-warning">
                    {warning}
                  </span>
                ))}
              </div>
            ) : null}
            {backendHealth ? (
              <div className="meta-list">
                <span>Profile: {backendHealth.analysis_profile}</span>
                <span>Backend version: {backendHealth.backend_version ?? "unknown"}</span>
              </div>
            ) : null}
          </div>

          <div className="panel-block">
            <h2>Preferences</h2>
            <label>
              User ID
              <input value={userId} onChange={(event) => setUserId(event.target.value)} />
            </label>
            <label>
              API base URL
              <div className="row">
                <input value={apiBaseUrlDraft} onChange={(event) => setApiBaseUrlDraft(event.target.value)} />
                <button type="button" className="icon-button" onClick={applyApiBaseUrl}>
                  Apply
                </button>
              </div>
            </label>
            <label>
              Writing goal
              <select
                value={preferences.writing_goal}
                onChange={(event) => {
                  const nextGoal = event.target.value as UserPreferences["writing_goal"];
                  setPreferences((current) => ({ ...current, writing_goal: nextGoal }));
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
            <label>
              Tone goal
              <select
                value={preferences.tone_goal}
                onChange={(event) =>
                  setPreferences((current) => ({ ...current, tone_goal: event.target.value as UserPreferences["tone_goal"] }))
                }
              >
                <option value="neutral">Neutral</option>
                <option value="friendly">Friendly</option>
                <option value="professional">Professional</option>
                <option value="concise">Concise</option>
                <option value="confident">Confident</option>
              </select>
            </label>
            <label>
              Suggestion density
              <select
                value={preferences.suggestion_density}
                onChange={(event) =>
                  setPreferences((current) => ({
                    ...current,
                    suggestion_density: event.target.value as UserPreferences["suggestion_density"],
                  }))
                }
              >
                <option value="low">Low</option>
                <option value="balanced">Balanced</option>
                <option value="high">High</option>
              </select>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={preferences.auto_show_tone}
                onChange={(event) => setPreferences((current) => ({ ...current, auto_show_tone: event.target.checked }))}
              />
              <span>Auto-show tone</span>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={preferences.enable_rewrites}
                onChange={(event) => setPreferences((current) => ({ ...current, enable_rewrites: event.target.checked }))}
              />
              <span>Enable rewrites</span>
            </label>
            <button type="button" className="button-primary" onClick={() => void savePreferencesToBackend()}>
              Save preferences
            </button>
          </div>

          <div className="panel-block">
            <h2>Personal dictionary</h2>
            <div className="row">
              <input value={dictionaryDraft} onChange={(event) => setDictionaryDraft(event.target.value)} />
              <button
                type="button"
                className="icon-button"
                onClick={() => {
                  if (!dictionaryDraft.trim()) {
                    return;
                  }
                  setPreferences((current) => ({
                    ...current,
                    personal_dictionary: upsertUnique(current.personal_dictionary, dictionaryDraft),
                  }));
                  setDictionaryDraft("");
                }}
              >
                Add
              </button>
            </div>
            <div className="chip-row">
              {preferences.personal_dictionary.map((entry) => (
                <button
                  key={entry}
                  type="button"
                  className="chip chip-action"
                  onClick={() =>
                    setPreferences((current) => ({
                      ...current,
                      personal_dictionary: current.personal_dictionary.filter((item) => item !== entry),
                    }))
                  }
                >
                  {entry}
                </button>
              ))}
            </div>
          </div>
        </aside>

        <section className="editor-panel">
          <div className="panel-block">
            <div className="editor-toolbar">
              <div className="chip-row">
                <span className="chip">{analysis.suggestions.length} suggestions</span>
                <span className="chip">{mode} mode</span>
                <span className="chip">{analysis.sentence_count} sentences</span>
              </div>
              <div className="rewrite-toolbar">
                {(["clarity", "formal", "concise", "friendly", "professional"] as RewriteIntent[]).map((intent) => (
                  <button key={intent} type="button" className="icon-button" onClick={() => void handleRewrite(intent)}>
                    {intent}
                  </button>
                ))}
              </div>
            </div>
            <textarea
              ref={textareaRef}
              className="editor-textarea"
              value={text}
              onChange={(event) => setText(event.target.value)}
              onSelect={handleSelectionChange}
            />
            <div className="meta-list">
              <span>Corrected preview: {analysis.corrected_text}</span>
            </div>
          </div>

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
                {rewriteResult.options.map((option) => (
                  <article key={option.id} className="rewrite-option">
                    <div className="suggestion-card__header">
                      <h3>{option.label}</h3>
                      <div className="suggestion-card__chips">
                        <span>{Math.round(option.confidence * 100)}%</span>
                        <span>{option.source}</span>
                      </div>
                    </div>
                    <p>{option.rewritten_text}</p>
                    <p className="muted-text">{option.explanation_bn || option.explanation_en}</p>
                    <button type="button" className="button-primary" onClick={() => applyRewriteOption(option.rewritten_text)}>
                      Accept rewrite
                    </button>
                  </article>
                ))}
              </div>
              {rewriteResult.warnings.length ? (
                <div className="chip-row">
                  {rewriteResult.warnings.map((warning) => (
                    <span key={warning} className="chip chip-warning">
                      {warning}
                    </span>
                  ))}
                </div>
              ) : null}
              <button type="button" className="button-secondary" onClick={dismissRewrite}>
                Dismiss rewrite
              </button>
            </div>
          ) : null}

          {tone ? (
            <div className="panel-block">
              <div className="suggestion-card__header">
                <div>
                  <div className="suggestion-card__eyebrow">Tone</div>
                  <h2>{tone.primary_tone ?? "neutral"}</h2>
                </div>
                <div className="suggestion-card__chips">
                  <span>{Math.round(tone.confidence * 100)}%</span>
                  {tone.detected_tones.map((toneLabel) => (
                    <span key={toneLabel}>{toneLabel}</span>
                  ))}
                </div>
              </div>
              <p>{tone.explanation_bn || tone.explanation_en}</p>
              <div className="chip-row">
                {tone.suggestions.map((suggestion) => (
                  <span key={suggestion} className="chip">
                    {suggestion}
                  </span>
                ))}
              </div>
              <div className="row">
                <button type="button" className="button-secondary" onClick={() => void markToneFeedback("tone_helpful")}>
                  Helpful
                </button>
                <button type="button" className="button-secondary" onClick={() => void markToneFeedback("tone_not_helpful")}>
                  Not helpful
                </button>
              </div>
            </div>
          ) : null}
        </section>
      </section>

      <section className="panel-block">
        <div className="suggestion-card__header">
          <div>
            <div className="suggestion-card__eyebrow">Suggestions</div>
            <h2>Review queue</h2>
          </div>
          <div className="suggestion-card__chips">
            <span>{runtimeDescriptor.label}</span>
          </div>
        </div>

        {analysis.suggestions.length ? (
          <div className="suggestion-list">
            {analysis.suggestions.map((suggestion) => (
              <button
                key={suggestion.id}
                type="button"
                className={`suggestion-row ${selectedSuggestionId === suggestion.id ? "suggestion-row--active" : ""}`}
                onClick={() => setSelectedSuggestionId(suggestion.id)}
              >
                <strong>{suggestion.short_title ?? suggestion.subtype}</strong>
                <span>{suggestion.suggestion_reason_short_bn ?? suggestion.explanation_bn}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className="empty-state">
            {backendMode === "online" || apiConfiguration.localFallbackEnabled
              ? "No high-confidence correction found."
              : BACKEND_DISABLED_MESSAGE}
          </p>
        )}

        {selectedSuggestion ? (
          <SuggestionCard
            suggestion={selectedSuggestion}
            onApply={(candidate, replacement) => handleApplySuggestion(candidate, replacement, selectedSuggestion)}
            onDismiss={() => handleDismissSuggestion(selectedSuggestion)}
            onIgnoreForever={() => handleIgnoreForever(selectedSuggestion)}
            onAddToDictionary={
              canAddSuggestionToDictionary(selectedSuggestion) ? () => handleAddToDictionary(selectedSuggestion) : undefined
            }
            onRewrite={(intent) => void handleRewrite(intent, selectedSuggestion)}
          />
        ) : null}
      </section>
    </main>
  );
}

function buildLocalFallbackResponse(text: string, mode: AnalyzeMode, personalDictionary: string[]): AnalyzeResponse {
  const fallback = analyzeTextLocally({
    text,
    mode,
    personal_dictionary: personalDictionary,
  });
  return {
    ...fallback,
    runtime_warnings: Array.from(new Set([...(fallback.runtime_warnings ?? []), "frontend_local_fallback_enabled"])),
  };
}

async function sendFeedbackIfOnline(payload: Parameters<typeof sendFeedback>[0]) {
  try {
    await sendFeedback(payload);
  } catch {
    // Ignore feedback transport failures in the demo surface.
  }
}

function replaceSpan(text: string, start: number, end: number, replacement: string): string {
  return `${text.slice(0, start)}${replacement}${text.slice(end)}`;
}

function createEmptyAnalysis(
  text: string,
  mode: AnalyzeMode,
  profile: AnalyzeResponse["analysis_profile"] = "backend_rules_and_spell_only",
): AnalyzeResponse {
  return {
    text,
    normalized_text: text,
    corrected_text: text,
    suggestions: [],
    analysis_profile: profile,
    runtime_source: profile,
    runtime_warnings: [],
    used_detector: false,
    used_corrector: false,
    lexicon_source: "unknown",
    lexicon_version: null,
    backend_version: null,
    sentence_count: approximateSentenceCount(text),
    request_mode_applied: mode,
  };
}

function createUnavailableAnalysis(text: string, mode: AnalyzeMode, warning: string): AnalyzeResponse {
  return {
    ...createEmptyAnalysis(text, mode, "frontend_local_fallback"),
    runtime_warnings: [warning],
  };
}

function defaultPreferences(userId: string): UserPreferences {
  return {
    user_id: userId,
    preferred_language_variant: "bangla",
    writing_goal: "general",
    tone_goal: "neutral",
    suggestion_density: "balanced",
    auto_show_tone: true,
    enable_rewrites: true,
    personal_dictionary: [],
    suppressed_rule_keys: [],
    disabled_sites: [],
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
  const created = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `anon-${Date.now().toString(36)}`;
  window.localStorage.setItem(USER_PROFILE_ID_STORAGE_KEY, created);
  return created;
}

function upsertUnique(items: string[], value: string): string[] {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (!normalized || items.includes(normalized)) {
    return items;
  }
  return [...items, normalized];
}

function modeFromWritingGoal(writingGoal: UserPreferences["writing_goal"]): AnalyzeMode {
  if (writingGoal === "formal" || writingGoal === "academic" || writingGoal === "business") {
    return "formal";
  }
  return "standard";
}

function approximateSentenceCount(text: string): number {
  return text
    .split(/[.!?\u0964]+/u)
    .map((sentence) => sentence.trim())
    .filter(Boolean).length;
}
