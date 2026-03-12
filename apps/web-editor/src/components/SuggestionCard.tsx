import {
  forwardRef,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEventHandler,
  type ForwardedRef,
  type MouseEventHandler,
  type PointerEventHandler
} from "react";
import type { Suggestion } from "@shared/schemas/contracts";

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
  onAccept: (replacement: string) => void;
  onDismiss: () => void;
  onMouseEnter: MouseEventHandler<HTMLDivElement>;
  onMouseLeave: MouseEventHandler<HTMLDivElement>;
  onFocusCapture: FocusEventHandler<HTMLDivElement>;
  onBlurCapture: FocusEventHandler<HTMLDivElement>;
  onPointerDownCapture: PointerEventHandler<HTMLDivElement>;
}

const CARD_OFFSET = 12;
const VIEWPORT_PADDING = 16;
const FALLBACK_WIDTH = 320;
const FALLBACK_HEIGHT = 220;

export const SuggestionCard = forwardRef<HTMLDivElement, SuggestionCardProps>(function SuggestionCard(
  {
    suggestion,
    anchorRect,
    mode,
    onAccept,
    onDismiss,
    onMouseEnter,
    onMouseLeave,
    onFocusCapture,
    onBlurCapture,
    onPointerDownCapture
  },
  forwardedRef
) {
  const localRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const explanation = suggestion.explanation_bn || suggestion.explanation_en;

  useLayoutEffect(() => {
    if (!anchorRect || !localRef.current) {
      setPosition(null);
      return;
    }

    const { width, height } = localRef.current.getBoundingClientRect();
    setPosition(resolveCardPosition(anchorRect, width || FALLBACK_WIDTH, height || FALLBACK_HEIGHT));
  }, [
    anchorRect,
    explanation,
    suggestion.id,
    suggestion.original_text,
    suggestion.replacement_options.length
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
      tabIndex={-1}
      style={{
        left: resolvedPosition.left,
        top: resolvedPosition.top,
        visibility: position ? "visible" : "hidden"
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
          <span className="suggestion-card__mode">{mode === "pinned" ? "Pinned" : "Preview"}</span>
        </div>
      </div>
      <div className="suggestion-card__original">
        <span className="suggestion-card__label">Original</span>
        <strong>{suggestion.original_text}</strong>
      </div>
      <p className="suggestion-card__explanation">{explanation}</p>
      <div className="suggestion-card__actions">
        {suggestion.replacement_options.length > 0 ? (
          suggestion.replacement_options.map((option, index) => (
            <button
              key={option}
              type="button"
              className={`suggestion-card__option ${
                index === 0 ? "suggestion-card__option--primary" : "suggestion-card__option--secondary"
              }`}
              onClick={() => onAccept(option)}
            >
              {option}
            </button>
          ))
        ) : (
          <span className="suggestion-card__empty">No replacement available</span>
        )}
      </div>
      <button type="button" className="suggestion-card__dismiss" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
});

function resolveCardPosition(
  anchorRect: SuggestionCardAnchor,
  cardWidth: number,
  cardHeight: number
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
