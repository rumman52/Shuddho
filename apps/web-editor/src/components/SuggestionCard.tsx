import {
  forwardRef,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEventHandler,
  type ForwardedRef,
  type MouseEventHandler,
  type PointerEventHandler,
} from "react";
import type { Suggestion, SuggestionAlternative } from "@shared/schemas/contracts";

export interface SuggestionCardAnchor {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

interface SuggestionCardProps {
  suggestion: Suggestion;
  anchorRect: SuggestionCardAnchor | null;
  mode: "preview" | "pinned";
  navigation: {
    current: number;
    total: number;
    onPrevious: () => void;
    onNext: () => void;
  } | null;
  runtimeLabel: string;
  sourceLabel: string;
  isStale: boolean;
  canAddToDictionary: boolean;
  onAccept: (candidate: Suggestion | SuggestionAlternative, replacement: string) => void;
  onDismiss: () => void;
  onAddToDictionary: () => void;
  onMouseEnter: MouseEventHandler<HTMLDivElement>;
  onMouseLeave: MouseEventHandler<HTMLDivElement>;
  onFocusCapture: FocusEventHandler<HTMLDivElement>;
  onBlurCapture: FocusEventHandler<HTMLDivElement>;
  onPointerDownCapture: PointerEventHandler<HTMLDivElement>;
}

const CARD_OFFSET = 12;
const VIEWPORT_PADDING = 16;
const FALLBACK_WIDTH = 360;
const FALLBACK_HEIGHT = 280;

export const SuggestionCard = forwardRef<HTMLDivElement, SuggestionCardProps>(function SuggestionCard(
  {
    suggestion,
    anchorRect,
    mode,
    navigation,
    runtimeLabel,
    sourceLabel,
    isStale,
    canAddToDictionary,
    onAccept,
    onDismiss,
    onAddToDictionary,
    onMouseEnter,
    onMouseLeave,
    onFocusCapture,
    onBlurCapture,
    onPointerDownCapture,
  },
  forwardedRef,
) {
  const localRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const primaryExplanation = suggestion.explanation_bn || suggestion.explanation_en;
  const secondaryExplanation =
    suggestion.explanation_bn && suggestion.explanation_en && suggestion.explanation_en !== suggestion.explanation_bn
      ? suggestion.explanation_en
      : null;
  const alternatives = suggestion.alternatives ?? [];

  useLayoutEffect(() => {
    if (!anchorRect || !localRef.current) {
      setPosition(null);
      return;
    }

    const { width, height } = localRef.current.getBoundingClientRect();
    setPosition(resolveCardPosition(anchorRect, width || FALLBACK_WIDTH, height || FALLBACK_HEIGHT));
  }, [
    anchorRect,
    primaryExplanation,
    secondaryExplanation,
    suggestion.alternatives?.length,
    suggestion.id,
    suggestion.original_text,
    suggestion.primary_reason,
    suggestion.replacement_options.length,
  ]);

  if (!anchorRect) {
    return null;
  }

  const resolvedPosition = position ?? resolveCardPosition(anchorRect, FALLBACK_WIDTH, FALLBACK_HEIGHT);

  return (
    <div
      ref={mergeRefs(forwardedRef, localRef)}
      className="suggestion-card"
      role="dialog"
      aria-modal="false"
      data-popup-mode={mode}
      data-stale={isStale ? "true" : undefined}
      tabIndex={-1}
      style={{
        left: resolvedPosition.left,
        top: resolvedPosition.top,
        visibility: position ? "visible" : "hidden",
      }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocusCapture={onFocusCapture}
      onBlurCapture={onBlurCapture}
      onPointerDownCapture={onPointerDownCapture}
    >
      <div className="suggestion-card__meta">
        <span>{suggestion.category}</span>
        <div className="suggestion-card__badges">
          <span>{Math.round(suggestion.confidence * 100)}%</span>
          <span className="suggestion-card__badge">{sourceLabel}</span>
          <span className="suggestion-card__mode">{mode === "pinned" ? "Pinned" : "Preview"}</span>
        </div>
      </div>
      <div className="suggestion-card__runtime">
        <span className="suggestion-card__label">Runtime</span>
        <strong>{runtimeLabel}</strong>
      </div>
      {navigation ? (
        <div className="suggestion-card__navigation">
          <button type="button" className="suggestion-card__nav-button" onClick={navigation.onPrevious}>
            Previous
          </button>
          <span className="suggestion-card__nav-status">
            {navigation.current} / {navigation.total}
          </span>
          <button type="button" className="suggestion-card__nav-button" onClick={navigation.onNext}>
            Next
          </button>
        </div>
      ) : null}
      <div className="suggestion-card__original">
        <span className="suggestion-card__label">Issue</span>
        <strong>{suggestion.original_text}</strong>
      </div>
      <div className="suggestion-card__why">
        <span className="suggestion-card__label">Why this suggestion</span>
        <p className="suggestion-card__explanation">{primaryExplanation}</p>
        {secondaryExplanation ? <p className="suggestion-card__explanation suggestion-card__explanation--secondary">{secondaryExplanation}</p> : null}
      </div>
      {suggestion.primary_reason ? (
        <div className="suggestion-card__why">
          <span className="suggestion-card__label">Why this is primary</span>
          <p className="suggestion-card__explanation">{suggestion.primary_reason}</p>
        </div>
      ) : null}
      {isStale ? (
        <div className="suggestion-card__stale">
          This suggestion no longer anchors safely to the current text. Run analysis again before accepting it.
        </div>
      ) : null}
      <div className="suggestion-card__actions">
        {suggestion.replacement_options.length > 0 ? (
          suggestion.replacement_options.map((option, index) => (
            <button
              key={option}
              type="button"
              className={`suggestion-card__option ${
                index === 0 ? "suggestion-card__option--primary" : "suggestion-card__option--secondary"
              }`}
              onClick={() => onAccept(suggestion, option)}
              disabled={isStale}
            >
              {option}
            </button>
          ))
        ) : (
          <span className="suggestion-card__empty">No replacement available</span>
        )}
      </div>
      {alternatives.length > 0 ? (
        <div className="suggestion-card__why">
          <span className="suggestion-card__label">Alternatives</span>
          {alternatives.map((alternative) => {
            const alternativeExplanation = alternative.explanation_bn || alternative.explanation_en;
            return (
              <div key={alternative.id} style={{ display: "grid", gap: "0.45rem" }}>
                <div className="suggestion-card__actions">
                  {alternative.replacement_options.map((option) => (
                    <button
                      key={`${alternative.id}:${option}`}
                      type="button"
                      className="suggestion-card__option suggestion-card__option--secondary"
                      onClick={() => onAccept(alternative, option)}
                      disabled={isStale}
                    >
                      {option}
                    </button>
                  ))}
                </div>
                {alternativeExplanation ? (
                  <p className="suggestion-card__explanation suggestion-card__explanation--secondary">{alternativeExplanation}</p>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
      <div className="suggestion-card__footer">
        <button type="button" className="suggestion-card__dismiss" onClick={onDismiss}>
          Dismiss
        </button>
        {canAddToDictionary ? (
          <button type="button" className="suggestion-card__dismiss" onClick={onAddToDictionary}>
            Add to personal dictionary
          </button>
        ) : null}
      </div>
    </div>
  );
});

function resolveCardPosition(
  anchorRect: SuggestionCardAnchor,
  cardWidth: number,
  cardHeight: number,
): { left: number; top: number } {
  const maxLeft = Math.max(VIEWPORT_PADDING, window.innerWidth - cardWidth - VIEWPORT_PADDING);
  const maxTop = Math.max(VIEWPORT_PADDING, window.innerHeight - cardHeight - VIEWPORT_PADDING);
  const left = clamp(anchorRect.left, VIEWPORT_PADDING, maxLeft);
  const preferredTop = anchorRect.bottom + CARD_OFFSET;
  const top =
    preferredTop + cardHeight <= window.innerHeight - VIEWPORT_PADDING
      ? preferredTop
      : clamp(anchorRect.top - cardHeight - CARD_OFFSET, VIEWPORT_PADDING, maxTop);

  return { left, top };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function mergeRefs<T>(...refs: Array<ForwardedRef<T> | undefined>) {
  return (value: T | null) => {
    for (const ref of refs) {
      if (!ref) {
        continue;
      }
      if (typeof ref === "function") {
        ref(value);
        continue;
      }
      (ref as { current: T | null }).current = value;
    }
  };
}
