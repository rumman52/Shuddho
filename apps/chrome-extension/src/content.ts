import { DebouncedAnalyzer } from "./analyzer";
import {
  applyTextReplacement,
  extractEditableText,
  isAnalyzableText,
  supportsDirectApply,
  isSupportedEditable,
  isSupportedEditor,
  type SupportedEditable
} from "./editable";
import { IssueOverlay } from "./overlay";
import type { FeedbackRequest, SuggestionRange } from "./types";

const analyzer = new DebouncedAnalyzer();
const overlay = new IssueOverlay();
let activeTarget: SupportedEditable | null = null;
let activeScrollTarget: SupportedEditable | null = null;

function updateTarget(target: EventTarget | null): void {
  if (!isSupportedEditable(target)) {
    overlay.hide();
    detachTargetScrollListener();
    activeTarget = null;
    return;
  }

  if (!isSupportedEditor(target)) {
    overlay.hide();
    detachTargetScrollListener();
    activeTarget = null;
    return;
  }

  activeTarget = target;
  attachTargetScrollListener(target);
  scheduleAnalyze(target);
}

function scheduleAnalyze(target: SupportedEditable): void {
  const text = extractEditableText(target);
  if (!isAnalyzableText(text)) {
    overlay.hide();
    return;
  }

  analyzer.schedule(
    text,
    (response) => {
      if (!activeTarget || activeTarget !== target) {
        return;
      }
      const ranges: SuggestionRange[] = response.suggestions.map((suggestion) => ({
        suggestion,
        start: suggestion.span_start,
        end: suggestion.span_end
      }));
      overlay.render(target, {
        text: response.text,
        ranges
      }, {
        canApplySuggestion: supportsDirectApply(target),
        onAccept: (range, replacement) => applySuggestion(target, range, replacement),
        onDismiss: (range) => dismissSuggestion(target, range)
      });
    },
    () => {
      overlay.hide();
    }
  );
}

document.addEventListener("focusin", (event) => {
  updateTarget(event.target);
});

document.addEventListener("input", (event) => {
  if (!activeTarget || event.target !== activeTarget) {
    updateTarget(event.target);
    return;
  }
  scheduleAnalyze(activeTarget);
});

document.addEventListener("selectionchange", () => {
  if (activeTarget) {
    overlay.syncSelection();
    overlay.syncPosition();
  }
});

window.addEventListener("scroll", () => overlay.syncPosition(), true);
window.addEventListener("resize", () => overlay.syncPosition());

function attachTargetScrollListener(target: SupportedEditable): void {
  if (activeScrollTarget === target) {
    return;
  }

  detachTargetScrollListener();
  activeScrollTarget = target;
  activeScrollTarget.addEventListener("scroll", handleTargetScroll, { passive: true });
}

function detachTargetScrollListener(): void {
  if (!activeScrollTarget) {
    return;
  }

  activeScrollTarget.removeEventListener("scroll", handleTargetScroll);
  activeScrollTarget = null;
}

function handleTargetScroll(): void {
  overlay.syncPosition();
}

function applySuggestion(target: SupportedEditable, range: SuggestionRange, replacement: string): boolean {
  if (!activeTarget || activeTarget !== target) {
    return false;
  }
  const originalText = extractEditableText(target);
  const applied = applyTextReplacement(target, range.start, range.end, replacement);
  if (!applied) {
    return false;
  }

  overlay.hide();
  void sendFeedback({
    suggestion_id: range.suggestion.id,
    action: "accepted",
    text: originalText,
    replacement,
    feedback_key: range.suggestion.feedback_key,
    rule_id: range.suggestion.rule_id,
    subtype: range.suggestion.subtype,
    source: range.suggestion.source,
    original_text: range.suggestion.original_text
  });
  return true;
}

function dismissSuggestion(target: SupportedEditable, range: SuggestionRange): boolean {
  if (!activeTarget || activeTarget !== target) {
    return false;
  }

  void sendFeedback({
    suggestion_id: range.suggestion.id,
    action: "dismissed",
    text: extractEditableText(target),
    feedback_key: range.suggestion.feedback_key,
    rule_id: range.suggestion.rule_id,
    subtype: range.suggestion.subtype,
    source: range.suggestion.source,
    original_text: range.suggestion.original_text
  });
  return true;
}

async function sendFeedback(payload: FeedbackRequest): Promise<void> {
  try {
    await analyzer.sendFeedback(payload);
  } catch (error) {
    console.warn("Shuddho feedback request failed", error);
  }
}
