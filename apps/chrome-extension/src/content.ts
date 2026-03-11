import { DebouncedAnalyzer } from "./analyzer";
import { extractEditableText, isAnalyzableText, isSupportedEditable, isSupportedEditor, type SupportedEditable } from "./editable";
import { IssueOverlay } from "./overlay";
import type { SuggestionRange } from "./types";

const analyzer = new DebouncedAnalyzer();
const overlay = new IssueOverlay();
let activeTarget: SupportedEditable | null = null;

function updateTarget(target: EventTarget | null): void {
  if (!isSupportedEditable(target)) {
    return;
  }

  if (!isSupportedEditor(target)) {
    overlay.hide();
    activeTarget = null;
    return;
  }

  activeTarget = target;
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
        textLength: response.text.length,
        ranges
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
    overlay.syncPosition();
  }
});

window.addEventListener("scroll", () => overlay.syncPosition(), true);
window.addEventListener("resize", () => overlay.syncPosition());

