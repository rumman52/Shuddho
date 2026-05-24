import { DebouncedAnalyzer } from "./analyzer";
import { EXTENSION_SETTINGS_STORAGE_KEY, getExtensionSettings, updateExtensionSettings } from "./config";
import {
  applyTextReplacement,
  extractEditableText,
  isAnalyzableText,
  supportsDirectApply,
  isSupportedEditor,
  resolveEditableRoot,
  type SupportedEditable,
} from "./editable";
import { IssueOverlay } from "./overlay";
import type { ExtensionSettings, FeedbackRequest, RewriteIntent, RewriteResponse, SuggestionRange } from "./types";

const analyzer = new DebouncedAnalyzer();
const overlay = new IssueOverlay();
let activeTarget: SupportedEditable | null = null;
let activeScrollTarget: SupportedEditable | null = null;
let settings: ExtensionSettings | null = null;

void initializeSettings();

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local" || !changes[EXTENSION_SETTINGS_STORAGE_KEY]) {
    return;
  }
  void initializeSettings();
});

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

async function initializeSettings(): Promise<void> {
  settings = await getExtensionSettings();
  if (isSiteDisabled()) {
    overlay.hide();
    activeTarget = null;
    detachTargetScrollListener();
  }
}

function updateTarget(target: EventTarget | null): void {
  if (!settings || isSiteDisabled()) {
    overlay.hide();
    detachTargetScrollListener();
    activeTarget = null;
    return;
  }

  const editableRoot = resolveEditableRoot(target);
  if (!editableRoot || !isSupportedEditor(editableRoot)) {
    overlay.hide();
    detachTargetScrollListener();
    activeTarget = null;
    return;
  }

  activeTarget = editableRoot;
  attachTargetScrollListener(editableRoot);
  scheduleAnalyze(editableRoot);
}

function scheduleAnalyze(target: SupportedEditable): void {
  if (!settings || isSiteDisabled()) {
    overlay.hide();
    return;
  }

  const text = extractEditableText(target);
  if (!isAnalyzableText(text)) {
    overlay.hide();
    return;
  }

  analyzer.schedule(
    text,
    settings,
    (response, tone) => {
      if (!activeTarget || activeTarget !== target || !settings) {
        return;
      }

      const suppressedRuleKeys = new Set(settings.suppressedRuleKeys);
      const ranges: SuggestionRange[] = response.suggestions
        .filter((suggestion) => !suppressedRuleKeys.has(`${suggestion.rule_id}:${suggestion.subtype}`))
        .map((suggestion) => ({
          suggestion,
          start: suggestion.span_start,
          end: suggestion.span_end,
        }));

      overlay.render(
        target,
        {
          text: response.text,
          ranges,
          tone,
        },
        {
          canApplySuggestion: supportsDirectApply(target),
          onAccept: (range, replacement) => applySuggestion(target, range, replacement),
          onDismiss: (range) => dismissSuggestion(target, range),
          onIgnoreForever: (range) => ignoreForever(target, range),
          onAddToDictionary: (range) => addToDictionary(target, range),
          onRewrite: settings.rewritesEnabled ? (range, intent) => requestRewrite(response.text, range, intent) : undefined,
          onApplyRewrite: (rewriteResponse, replacement) => applyRewrite(target, rewriteResponse, replacement),
        },
      );
    },
    (error) => {
      if (!activeTarget || activeTarget !== target) {
        return;
      }
      overlay.showNotice(
        target,
        "Backend unavailable",
        `Shuddho could not analyze this field. ${error instanceof Error ? error.message : ""}`.trim(),
      );
    },
  );
}

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
  if (!settings || !activeTarget || activeTarget !== target) {
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
    original_text: range.suggestion.original_text,
    user_id: settings.currentUserId,
  });
  return true;
}

function dismissSuggestion(target: SupportedEditable, range: SuggestionRange): boolean {
  if (!settings || !activeTarget || activeTarget !== target) {
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
    original_text: range.suggestion.original_text,
    user_id: settings.currentUserId,
  });
  return true;
}

function ignoreForever(target: SupportedEditable, range: SuggestionRange): boolean {
  if (!settings || !activeTarget || activeTarget !== target) {
    return false;
  }
  const ruleKey = `${range.suggestion.rule_id}:${range.suggestion.subtype}`;
  settings = {
    ...settings,
    suppressedRuleKeys: upsertUnique(settings.suppressedRuleKeys, ruleKey),
  };
  void updateExtensionSettings({ suppressedRuleKeys: settings.suppressedRuleKeys });
  void sendFeedback({
    suggestion_id: range.suggestion.id,
    action: "ignore_forever",
    text: extractEditableText(target),
    replacement: range.suggestion.replacement_options[0] ?? null,
    feedback_key: range.suggestion.feedback_key,
    rule_id: range.suggestion.rule_id,
    subtype: range.suggestion.subtype,
    source: range.suggestion.source,
    original_text: range.suggestion.original_text,
    suppression_key: range.suggestion.suppression_key,
    user_id: settings.currentUserId,
  });
  return true;
}

function addToDictionary(target: SupportedEditable, range: SuggestionRange): boolean {
  if (!settings || !activeTarget || activeTarget !== target) {
    return false;
  }
  const entry = range.suggestion.original_text.trim();
  if (!entry) {
    return false;
  }
  settings = {
    ...settings,
    localPersonalDictionaryMirror: upsertUnique(settings.localPersonalDictionaryMirror, entry),
  };
  void updateExtensionSettings({
    localPersonalDictionaryMirror: settings.localPersonalDictionaryMirror,
  });
  void sendFeedback({
    suggestion_id: range.suggestion.id,
    action: "add_to_personal_dictionary",
    text: extractEditableText(target),
    replacement: range.suggestion.replacement_options[0] ?? null,
    feedback_key: range.suggestion.feedback_key,
    rule_id: range.suggestion.rule_id,
    subtype: range.suggestion.subtype,
    source: range.suggestion.source,
    original_text: range.suggestion.original_text,
    user_dictionary_entry: entry,
    user_id: settings.currentUserId,
  });
  return true;
}

async function requestRewrite(text: string, range: SuggestionRange, intent: RewriteIntent): Promise<RewriteResponse | null> {
  if (!settings) {
    return null;
  }
  try {
    return await analyzer.rewrite(text, range, intent, settings);
  } catch (error) {
    console.warn("Shuddho rewrite request failed", error);
    return null;
  }
}

function applyRewrite(target: SupportedEditable, response: RewriteResponse, replacement: string): boolean {
  if (!activeTarget || activeTarget !== target) {
    return false;
  }
  if (response.selection_start === null || response.selection_start === undefined || response.selection_end === null || response.selection_end === undefined) {
    return false;
  }
  const applied = applyTextReplacement(target, response.selection_start, response.selection_end, replacement);
  if (applied && settings) {
    void sendFeedback({
      suggestion_id: `rewrite:${response.intent}`,
      action: "rewrite_accepted",
      text: extractEditableText(target),
      replacement,
      original_text: response.original_text,
      user_id: settings.currentUserId,
    });
  }
  return applied;
}

async function sendFeedback(payload: FeedbackRequest): Promise<void> {
  if (!settings) {
    return;
  }
  try {
    await analyzer.sendFeedback(payload);
  } catch (error) {
    console.warn("Shuddho feedback request failed", error);
  }
}

function isSiteDisabled(): boolean {
  if (!settings) {
    return false;
  }
  return settings.disabledSites.includes(window.location.hostname.toLowerCase());
}

function upsertUnique(items: string[], value: string): string[] {
  if (!value || items.includes(value)) {
    return items;
  }
  return [...items, value];
}
