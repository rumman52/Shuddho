export type SupportedEditable = HTMLTextAreaElement | HTMLInputElement | HTMLElement;
export interface EditableSelection {
  start: number;
  end: number;
}

interface EditablePoint {
  node: Node;
  offset: number;
}

interface ContentEditableTextModel {
  text: string;
  points: EditablePoint[];
}

const SUPPORTED_INPUT_TYPES = new Set(["text", "search", "email", "url"]);
const BLOCK_BREAK_TAGS = new Set([
  "ADDRESS",
  "ARTICLE",
  "ASIDE",
  "BLOCKQUOTE",
  "DD",
  "DIV",
  "DL",
  "DT",
  "FIELDSET",
  "FIGCAPTION",
  "FIGURE",
  "FOOTER",
  "FORM",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "HEADER",
  "HR",
  "LI",
  "MAIN",
  "NAV",
  "OL",
  "P",
  "PRE",
  "SECTION",
  "TABLE",
  "TBODY",
  "TD",
  "TH",
  "TR",
  "UL",
]);
const NON_SERIALIZED_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT"]);

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
  return buildContentEditableTextModel(target).text;
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

export function supportsDirectApply(target: SupportedEditable): boolean {
  return supportsInlineMirror(target) || target.isContentEditable;
}

export function getEditableSelection(target: SupportedEditable): EditableSelection | null {
  if (supportsInlineMirror(target)) {
    const start = target.selectionStart ?? 0;
    const end = target.selectionEnd ?? start;
    return {
      start: Math.max(0, start),
      end: Math.max(start, end),
    };
  }

  if (!target.isContentEditable) {
    return null;
  }

  return getContentEditableSelection(target);
}

export function selectEditableRange(
  target: SupportedEditable,
  start: number,
  end: number
): void {
  if (supportsInlineMirror(target)) {
    target.focus();
    target.setSelectionRange(Math.max(0, start), Math.max(start, end));
    return;
  }

  if (!target.isContentEditable) {
    return;
  }

  const model = buildContentEditableTextModel(target);
  const safeStart = clamp(start, 0, model.text.length);
  const safeEnd = clamp(end, safeStart, model.text.length);
  const selection = window.getSelection();
  if (!selection) {
    return;
  }

  const range = document.createRange();
  const startPoint = resolveTextPoint(model, safeStart);
  const endPoint = resolveTextPoint(model, safeEnd);
  range.setStart(startPoint.node, startPoint.offset);
  range.setEnd(endPoint.node, endPoint.offset);

  target.focus();
  selection.removeAllRanges();
  selection.addRange(range);
}

export function applyTextReplacement(
  target: SupportedEditable,
  start: number,
  end: number,
  replacement: string
): boolean {
  if (supportsInlineMirror(target)) {
    const safeStart = Math.max(0, start);
    const safeEnd = Math.max(safeStart, end);
    target.focus();
    target.setSelectionRange(safeStart, safeEnd);
    target.setRangeText(replacement, safeStart, safeEnd, "end");
    target.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  }

  if (!target.isContentEditable) {
    return false;
  }

  const model = buildContentEditableTextModel(target);
  const safeStart = clamp(start, 0, model.text.length);
  const safeEnd = clamp(end, safeStart, model.text.length);
  const range = document.createRange();
  const startPoint = resolveTextPoint(model, safeStart);
  const endPoint = resolveTextPoint(model, safeEnd);
  range.setStart(startPoint.node, startPoint.offset);
  range.setEnd(endPoint.node, endPoint.offset);

  target.focus();
  range.deleteContents();

  const selection = window.getSelection();
  if (replacement) {
    const replacementNode = document.createTextNode(replacement);
    range.insertNode(replacementNode);
    range.setStart(replacementNode, replacement.length);
  }
  range.collapse(true);

  if (selection) {
    selection.removeAllRanges();
    selection.addRange(range);
  }

  target.dispatchEvent(new Event("input", { bubbles: true }));
  return true;
}

function getContentEditableSelection(target: HTMLElement): EditableSelection | null {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) {
    return null;
  }

  const range = selection.getRangeAt(0);
  if (!isNodeWithinTarget(target, range.startContainer) || !isNodeWithinTarget(target, range.endContainer)) {
    return null;
  }

  const model = buildContentEditableTextModel(target);
  const start = domPointToOffset(model, range.startContainer, range.startOffset);
  const end = domPointToOffset(model, range.endContainer, range.endOffset);
  return {
    start: Math.max(0, start),
    end: Math.max(start, end),
  };
}

function buildContentEditableTextModel(target: HTMLElement): ContentEditableTextModel {
  const points: EditablePoint[] = [{ node: target, offset: 0 }];
  const state = {
    text: "",
    points,
  };

  serializeNodeChildren(target, state);
  return state;
}

function serializeNodeChildren(
  parent: Node,
  state: ContentEditableTextModel,
): void {
  const children = Array.from(parent.childNodes);
  children.forEach((child, index) => {
    const lengthBeforeChild = state.text.length;
    serializeNode(child, state);

    if (child instanceof HTMLBRElement) {
      appendSyntheticBreak(state, domPointAfterNode(child));
      return;
    }

    const childAddedText = state.text.length > lengthBeforeChild;
    if (
      childAddedText &&
      child instanceof HTMLElement &&
      BLOCK_BREAK_TAGS.has(child.tagName) &&
      hasSerializableSibling(children, index + 1)
    ) {
      appendSyntheticBreak(state, domPointAfterNode(child));
    }
  });
}

function serializeNode(
  node: Node,
  state: ContentEditableTextModel,
): void {
  if (node instanceof Text) {
    appendTextContent(state, node);
    return;
  }

  if (!(node instanceof HTMLElement)) {
    return;
  }

  if (NON_SERIALIZED_TAGS.has(node.tagName)) {
    return;
  }

  if (node instanceof HTMLBRElement) {
    return;
  }

  serializeNodeChildren(node, state);
}

function appendTextContent(
  state: ContentEditableTextModel,
  textNode: Text,
): void {
  const value = textNode.data ?? "";
  for (let index = 0; index < value.length; index += 1) {
    state.text += value[index];
    state.points.push({ node: textNode, offset: index + 1 });
  }
}

function appendSyntheticBreak(
  state: ContentEditableTextModel,
  point: EditablePoint,
): void {
  if (state.text.endsWith("\n")) {
    return;
  }

  state.text += "\n";
  state.points.push(point);
}

function hasSerializableSibling(nodes: Node[], startIndex: number): boolean {
  for (let index = startIndex; index < nodes.length; index += 1) {
    if (nodeHasSerializableContent(nodes[index])) {
      return true;
    }
  }
  return false;
}

function nodeHasSerializableContent(node: Node): boolean {
  if (node instanceof Text) {
    return (node.data ?? "").length > 0;
  }

  if (!(node instanceof HTMLElement)) {
    return false;
  }

  if (NON_SERIALIZED_TAGS.has(node.tagName)) {
    return false;
  }

  if (node instanceof HTMLBRElement) {
    return true;
  }

  return Array.from(node.childNodes).some(nodeHasSerializableContent);
}

function resolveTextPoint(
  model: ContentEditableTextModel,
  offset: number,
): EditablePoint {
  const safeOffset = clamp(offset, 0, model.text.length);
  return model.points[safeOffset] ?? model.points[model.points.length - 1];
}

function domPointToOffset(
  model: ContentEditableTextModel,
  node: Node,
  offset: number,
): number {
  let resolvedOffset = 0;
  for (let index = 0; index < model.points.length; index += 1) {
    const comparison = compareDomPoints(model.points[index], { node, offset });
    if (comparison > 0) {
      break;
    }
    resolvedOffset = index;
    if (comparison === 0) {
      break;
    }
  }

  return clamp(resolvedOffset, 0, model.text.length);
}

function compareDomPoints(
  left: EditablePoint,
  right: EditablePoint,
): number {
  if (left.node === right.node) {
    return Math.sign(left.offset - right.offset);
  }

  const range = document.createRange();
  range.setStart(left.node, left.offset);
  range.collapse(true);
  return -range.comparePoint(right.node, right.offset);
}

function isNodeWithinTarget(target: HTMLElement, node: Node): boolean {
  if (node === target) {
    return true;
  }

  if (node instanceof Element) {
    return target.contains(node);
  }

  return node.parentElement ? target.contains(node.parentElement) : false;
}

function domPointAfterNode(node: Node): EditablePoint {
  const parent = node.parentNode;
  if (!parent) {
    return { node, offset: 0 };
  }

  const childIndex = Array.prototype.indexOf.call(parent.childNodes, node);
  return {
    node: parent,
    offset: Math.max(0, childIndex + 1),
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}
