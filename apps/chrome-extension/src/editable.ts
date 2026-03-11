export type SupportedEditable = HTMLTextAreaElement | HTMLInputElement | HTMLElement;

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

