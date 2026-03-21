export type SupportedEditable = HTMLTextAreaElement | HTMLInputElement | HTMLElement;
export interface EditableSelection {
  start: number;
  end: number;
}

const SUPPORTED_INPUT_TYPES = new Set(["text", "search", "email", "url"]);

export function isSupportedEditable(target: EventTarget | null): target is SupportedEditable {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  if (target instanceof HTMLTextAreaElement) {
    return true;
  }

  if (target instanceof HTMLInputElement) {
    return SUPPORTED_INPUT_TYPES.has(target.type);
  }

  return target.isContentEditable;
}

export function extractEditableText(target: SupportedEditable): string {
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLInputElement) {
    return target.value;
  }
  return target.innerText ?? "";
}

export function isAnalyzableText(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.length >= 2 && trimmed.length <= 4000;
}

export function isSupportedEditor(target: SupportedEditable): boolean {
  if (!target.isConnected) {
    return false;
  }

  const rect = target.getBoundingClientRect();
  if (rect.width < 80 || rect.height < 24) {
    return false;
  }

  return true;
}

export function supportsInlineMirror(target: SupportedEditable): target is HTMLTextAreaElement | HTMLInputElement {
  if (target instanceof HTMLTextAreaElement) {
    return true;
  }
  if (target instanceof HTMLInputElement) {
    return SUPPORTED_INPUT_TYPES.has(target.type);
  }
  return false;
}

export function getEditableSelection(target: SupportedEditable): EditableSelection | null {
  if (!supportsInlineMirror(target)) {
    return null;
  }

  const start = target.selectionStart ?? 0;
  const end = target.selectionEnd ?? start;
  return {
    start: Math.max(0, start),
    end: Math.max(start, end),
  };
}

export function selectEditableRange(
  target: SupportedEditable,
  start: number,
  end: number
): void {
  if (!supportsInlineMirror(target)) {
    return;
  }

  target.focus();
  target.setSelectionRange(Math.max(0, start), Math.max(start, end));
}
