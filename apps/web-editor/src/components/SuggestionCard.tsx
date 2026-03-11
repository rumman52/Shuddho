import type { Suggestion } from "@shared/schemas/contracts";

interface SuggestionCardProps {
  suggestion: Suggestion;
  position: { left: number; top: number } | null;
  onAccept: (replacement: string) => void;
  onDismiss: () => void;
}

export function SuggestionCard({ suggestion, position, onAccept, onDismiss }: SuggestionCardProps) {
  if (!position) {
    return null;
  }

  return (
    <div className="suggestion-card" style={{ left: position.left, top: position.top }}>
      <div className="suggestion-card__meta">
        <span>{suggestion.category}</span>
        <span>{Math.round(suggestion.confidence * 100)}%</span>
      </div>
      <h3>{suggestion.original_text}</h3>
      <p>{suggestion.explanation_bn}</p>
      <div className="suggestion-card__actions">
        {suggestion.replacement_options.map((option) => (
          <button key={option} className="suggestion-card__option" onClick={() => onAccept(option)}>
            {option}
          </button>
        ))}
      </div>
      <button className="suggestion-card__dismiss" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}

