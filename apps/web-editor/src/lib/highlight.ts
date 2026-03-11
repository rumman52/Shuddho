import type { Editor } from "@tiptap/react";
import type { Suggestion } from "@shared/schemas/contracts";

function getTextSegments(editor: Editor): Array<{ start: number; end: number; from: number; to: number }> {
  const segments: Array<{ start: number; end: number; from: number; to: number }> = [];
  let textOffset = 0;

  editor.state.doc.descendants((node, position) => {
    if (!node.isText || !node.text) {
      return;
    }

    const length = node.text.length;
    segments.push({
      start: textOffset,
      end: textOffset + length,
      from: position,
      to: position + length
    });
    textOffset += length;
  });

  return segments;
}

function toDocumentRange(editor: Editor, start: number, end: number): { from: number; to: number } | null {
  const segments = getTextSegments(editor);
  let from: number | null = null;
  let to: number | null = null;

  for (const segment of segments) {
    if (from === null && start >= segment.start && start <= segment.end) {
      from = segment.from + (start - segment.start);
    }
    if (end > segment.start && end <= segment.end) {
      to = segment.from + (end - segment.start);
      break;
    }
  }

  if (from === null || to === null || from >= to) {
    return null;
  }

  return { from, to };
}

export function clearIssueMarks(editor: Editor): void {
  const issueMark = editor.state.schema.marks.issue;
  const transaction = editor.state.tr;

  editor.state.doc.descendants((node, position) => {
    if (!node.isText || !node.text) {
      return;
    }
    transaction.removeMark(position, position + node.text.length, issueMark);
  });

  if (transaction.docChanged) {
    editor.view.dispatch(transaction);
  }
}

export function applyIssueMarks(editor: Editor, suggestions: Suggestion[]): void {
  clearIssueMarks(editor);
  const issueMark = editor.state.schema.marks.issue;
  const transaction = editor.state.tr;

  for (const suggestion of suggestions) {
    const range = toDocumentRange(editor, suggestion.span_start, suggestion.span_end);
    if (!range) {
      continue;
    }
    transaction.addMark(
      range.from,
      range.to,
      issueMark.create({
        suggestionId: suggestion.id,
        severity: suggestion.severity
      })
    );
  }

  if (transaction.docChanged) {
    editor.view.dispatch(transaction);
  }
}

export function replaceSuggestion(editor: Editor, suggestion: Suggestion, replacement: string): boolean {
  const range = toDocumentRange(editor, suggestion.span_start, suggestion.span_end);
  if (!range) {
    return false;
  }

  editor.chain().focus().insertContentAt(range, replacement).run();
  return true;
}

