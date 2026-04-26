import type { RewriteIntent, Suggestion, SuggestionAlternative } from "@shared/schemas/contracts";

interface SuggestionCardProps {
  suggestion: Suggestion;
  debugMode?: boolean;
  onApply: (candidate: Suggestion | SuggestionAlternative, replacement: string) => void;
  onDismiss: () => void;
  onIgnoreForever: () => void;
  onAddToDictionary?: () => void;
  onRewrite: (intent: RewriteIntent) => void;
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
  const primaryExplanation = suggestion.suggestion_reason_short_bn ?? suggestion.explanation_bn ?? suggestion.explanation_en;
  const secondaryExplanation =
    suggestion.explanation_en && suggestion.explanation_en !== suggestion.explanation_bn
      ? suggestion.explanation_en
      : null;
  const alternatives = suggestion.alternatives ?? [];

  return (
    <article className="suggestion-card">
      <div className="suggestion-card__header">
        <div>
          <div className="suggestion-card__eyebrow">{suggestion.ui_group ?? suggestion.category}</div>
          <h3>{suggestion.short_title ?? "Writing suggestion"}</h3>
        </div>
        <div className="suggestion-card__chips">
          <span>{suggestion.category}</span>
          {debugMode ? <span>{Math.round(suggestion.confidence * 100)}%</span> : null}
          {debugMode ? <span>{suggestion.source}</span> : null}
          {debugMode ? <span>{suggestion.severity}</span> : null}
        </div>
      </div>

      <div className="suggestion-card__issue">
        <span className="suggestion-card__label">Issue</span>
        <strong>{suggestion.original_text}</strong>
      </div>

      {suggestion.replacement_options[0] ? (
        <div className="suggestion-card__issue">
          <span className="suggestion-card__label">Primary replacement</span>
          <strong>{suggestion.replacement_options[0]}</strong>
        </div>
      ) : null}

      <p className="suggestion-card__summary">{primaryExplanation}</p>

      <div className="suggestion-card__chips suggestion-card__chips--soft">
        {suggestion.tone_labels?.map((toneLabel) => (
          <span key={toneLabel}>{toneLabel}</span>
        ))}
        {suggestion.action_hints?.map((hint) => (
          <span key={hint}>{hint.replaceAll("_", " ")}</span>
        ))}
      </div>

      <div className="suggestion-card__options">
        {suggestion.replacement_options.map((option, index) => (
          <button
            key={`${suggestion.id}:${option}`}
            type="button"
            className={index === 0 ? "button-primary" : "button-secondary"}
            onClick={() => onApply(suggestion, option)}
          >
            {option}
          </button>
        ))}
      </div>

      {alternatives.length > 0 ? (
        <div className="suggestion-card__alternatives">
          {alternatives.map((alternative) => (
            <div key={alternative.id} className="suggestion-card__alternative">
              <div className="suggestion-card__options">
                {alternative.replacement_options.map((option) => (
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
              <p>{alternative.explanation_bn || alternative.explanation_en}</p>
            </div>
          ))}
        </div>
      ) : null}

      {suggestion.rewrite_intents?.length ? (
        <div className="suggestion-card__rewrite-row">
          {suggestion.rewrite_intents.map((intent) => (
            <button key={intent} type="button" className="icon-button" onClick={() => onRewrite(intent)} aria-label={intent}>
              {rewriteIntentLabel(intent)}
            </button>
          ))}
        </div>
      ) : null}

      <details className="suggestion-card__details">
        <summary>Why this suggestion</summary>
        <p>{suggestion.explanation_bn || suggestion.explanation_en}</p>
        {secondaryExplanation ? <p>{secondaryExplanation}</p> : null}
        {debugMode && suggestion.source_trace?.length ? <p>source_trace: {suggestion.source_trace.join(" -> ")}</p> : null}
      </details>

      <div className="suggestion-card__footer">
        <button type="button" className="button-secondary" onClick={onDismiss}>
          Dismiss
        </button>
        <button type="button" className="button-secondary" onClick={onIgnoreForever}>
          Ignore forever
        </button>
        {onAddToDictionary ? (
          <button type="button" className="button-secondary" onClick={onAddToDictionary}>
            Add to dictionary
          </button>
        ) : null}
      </div>
    </article>
  );
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
      return "Friendlier";
    case "professional":
      return "Professional";
    default:
      return intent;
  }
}
