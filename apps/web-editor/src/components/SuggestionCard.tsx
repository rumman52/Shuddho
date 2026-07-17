import type {
  RewriteIntent,
  Suggestion,
  SuggestionAlternative,
} from "@shared/schemas/contracts";
import { getReplacementOptions } from "../lib/suggestionAdapter";

interface SuggestionCardProps {
  suggestion: Suggestion;
  debugMode?: boolean;
  onApply: (
    candidate: Suggestion | SuggestionAlternative,
    replacement: string,
  ) => void;
  onDismiss: () => void;
  onIgnoreForever: () => void;
  onAddToDictionary?: () => void;
  onRewrite: (intent: RewriteIntent) => void;
  position?: number;
  total?: number;
}

export function SuggestionCard({
  suggestion,
  debugMode = false,
  onApply,
  onDismiss,
  onIgnoreForever,
  onAddToDictionary,
  onRewrite,
}: SuggestionCardProps) {
  const primaryExplanation =
    suggestion.suggestion_reason_short_bn ??
    suggestion.explanation_bn ??
    suggestion.explanation_en;
  const replacementOptions = getReplacementOptions(suggestion);
  const alternatives = Array.isArray(suggestion.alternatives)
    ? suggestion.alternatives
    : [];
  const rewriteIntents = Array.isArray(suggestion.rewrite_intents)
    ? suggestion.rewrite_intents
    : [];
  const sourceTrace = Array.isArray(suggestion.source_trace)
    ? suggestion.source_trace
    : [];
  const primaryReplacement = replacementOptions[0] ?? "";

  return (
    <article className="suggestion-card">
      <div className="suggestion-card__header">
        <span className="suggestion-card__type">
          <span className="issue-dot" aria-hidden="true" />
          {displaySuggestionType(suggestion)}
        </span>
        <span className="chip suggestion-card__source">{displaySuggestionSource(suggestion)}</span>
      </div>

      <div className="suggestion-card__change">
        <span>{suggestion.original_text}</span>
        {primaryReplacement ? <span aria-hidden="true">→</span> : null}
        {primaryReplacement ? <strong>{primaryReplacement}</strong> : null}
      </div>

      <p className="suggestion-card__summary">{primaryExplanation}</p>

      <div className="suggestion-card__footer">
        {primaryReplacement ? (
          <button
            type="button"
            className="button-primary"
            onClick={() => onApply(suggestion, primaryReplacement)}
          >
            Apply
          </button>
        ) : null}
        <button type="button" className="button-secondary" onClick={onDismiss}>
          Ignore
        </button>
        <details className="explain-details">
          <summary>Explain</summary>
          <p>{suggestion.explanation_bn || suggestion.explanation_en}</p>
        </details>
        <details className="suggestion-menu">
          <summary aria-label="More options">•••</summary>
          <div className="suggestion-menu__content">
            <button type="button" className="text-button" onClick={onIgnoreForever}>
              Ignore forever
            </button>
            {onAddToDictionary ? (
              <button
                type="button"
                className="text-button"
                onClick={onAddToDictionary}
              >
                Add to dictionary
              </button>
            ) : null}
          </div>
        </details>
      </div>

      {alternatives.length > 0 ? (
        <details className="suggestion-card__details">
          <summary>Other replacements</summary>
          <div className="suggestion-card__alternatives">
            {alternatives.map((alternative) => (
              <div
                key={alternative.id}
                className="suggestion-card__alternative"
              >
                <div className="suggestion-card__options">
                  {(alternative.replacement_options ?? []).map((option) => (
                    <button
                      key={`${alternative.id}:${option}`}
                      type="button"
                      className="button-secondary"
                      onClick={() => onApply(alternative, option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
                <p>
                  {alternative.explanation_bn || alternative.explanation_en}
                </p>
              </div>
            ))}
          </div>
        </details>
      ) : null}

      {rewriteIntents.length ? (
        <div className="suggestion-card__rewrite-row">
          {rewriteIntents.map((intent) => (
            <button
              key={intent}
              type="button"
              className="button-secondary button-compact"
              onClick={() => onRewrite(intent)}
            >
              {rewriteIntentLabel(intent)}
            </button>
          ))}
        </div>
      ) : null}


      {debugMode ? (
        <details className="suggestion-card__details">
          <summary>Debug details</summary>
          <p>confidence: {Math.round(suggestion.confidence * 100)}%</p>
          <p>source: {suggestion.source}</p>
          <p>severity: {suggestion.severity}</p>
          <p>provider: {suggestion.provider ?? "local"}</p>
          {suggestion.metadata ? <p>metadata: {JSON.stringify(suggestion.metadata)}</p> : null}
          <p>
            span: {suggestion.span_start}–{suggestion.span_end}
          </p>
          {sourceTrace.length ? (
            <p>source_trace: {sourceTrace.join(" → ")}</p>
          ) : null}
        </details>
      ) : null}
    </article>
  );
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

function rewriteIntentLabel(intent: RewriteIntent): string {
  switch (intent) {
    case "clarity":
      return "Clarity";
    case "formal":
      return "Formal";
    case "concise":
      return "Shorter";
    case "friendly":
      return "Simpler";
    case "professional":
      return "Professional";
    default:
      return intent;
  }
}

function displaySuggestionSource(suggestion: Suggestion): string {
  if (suggestion.source === "hybrid") {
    return "Local + AI";
  }
  if (suggestion.source === "model") {
    return "AI";
  }
  return "Local";
}
