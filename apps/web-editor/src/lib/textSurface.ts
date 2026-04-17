import type { Editor } from "@tiptap/react";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import type { Suggestion } from "@shared/schemas/contracts";

export interface TextSegment {
  start: number;
  end: number;
  from: number;
  to: number;
}

export interface EditorTextSurface {
  text: string;
  segments: TextSegment[];
}

export interface ResolvedSuggestionMatch {
  status: "current" | "stale";
  spanStart: number;
  spanEnd: number;
}

export function getEditorTextSurface(editor: Editor): EditorTextSurface {
  const segments: TextSegment[] = [];
  const parts: string[] = [];
  let textOffset = 0;

  editor.state.doc.forEach((node, offset, index) => {
    textOffset = collectNodeText(node, offset, textOffset, parts, segments);
    if (index < editor.state.doc.childCount - 1) {
      parts.push("\n");
      textOffset += 1;
    }
  });

  return {
    text: parts.join(""),
    segments,
  };
}

export function resolveSuggestionMatch(text: string, suggestion: Suggestion): ResolvedSuggestionMatch {
  const exactMatch = resolveExactSuggestionMatch(text, suggestion);
  if (exactMatch) {
    return exactMatch;
  }

  const candidates = findSuggestionCandidates(text, suggestion.original_text);
  if (!candidates.length) {
    return staleSuggestion(suggestion);
  }

  const anchoredCandidates = candidates.filter(({ start, end }) => anchorsMatch(text, suggestion, start, end));
  if (anchoredCandidates.length === 1) {
    return {
      status: "current",
      spanStart: anchoredCandidates[0].start,
      spanEnd: anchoredCandidates[0].end,
    };
  }

  if (suggestion.occurrence_index !== undefined && suggestion.occurrence_index !== null) {
    const occurrenceCandidate = candidates[suggestion.occurrence_index];
    if (occurrenceCandidate && anchorsPartiallyMatch(text, suggestion, occurrenceCandidate.start, occurrenceCandidate.end)) {
      return {
        status: "current",
        spanStart: occurrenceCandidate.start,
        spanEnd: occurrenceCandidate.end,
      };
    }
  }

  return staleSuggestion(suggestion);
}

export function matchSuggestionByContext(previous: Suggestion | null, nextSuggestions: Suggestion[]): Suggestion | null {
  if (!previous) {
    return null;
  }

  for (const suggestion of nextSuggestions) {
    if (suggestion.id === previous.id) {
      return suggestion;
    }
  }

  const matches = nextSuggestions.filter((suggestion) => {
    if (suggestion.rule_id !== previous.rule_id) {
      return false;
    }
    if (suggestion.category !== previous.category || suggestion.subtype !== previous.subtype) {
      return false;
    }
    if (suggestion.source !== previous.source) {
      return false;
    }
    if (suggestion.original_text !== previous.original_text) {
      return false;
    }
    if ((suggestion.replacement_options[0] ?? "") !== (previous.replacement_options[0] ?? "")) {
      return false;
    }
    if (suggestion.occurrence_index !== previous.occurrence_index) {
      return false;
    }
    if ((suggestion.anchor_before ?? "") !== (previous.anchor_before ?? "")) {
      return false;
    }
    if ((suggestion.anchor_after ?? "") !== (previous.anchor_after ?? "")) {
      return false;
    }
    return suggestion.sentence_index === previous.sentence_index;
  });

  if (matches.length !== 1) {
    return null;
  }
  return matches[0];
}

function collectNodeText(
  node: ProseMirrorNode,
  nodePos: number,
  textOffset: number,
  parts: string[],
  segments: TextSegment[],
): number {
  let currentOffset = textOffset;

  node.forEach((child, childOffset, index) => {
    const childPos = nodePos + childOffset + 1;

    if (child.isText && child.text) {
      parts.push(child.text);
      segments.push({
        start: currentOffset,
        end: currentOffset + child.text.length,
        from: childPos,
        to: childPos + child.text.length,
      });
      currentOffset += child.text.length;
      return;
    }

    if (child.type.name === "hardBreak") {
      parts.push("\n");
      currentOffset += 1;
      return;
    }

    const beforeChild = currentOffset;
    currentOffset = collectNodeText(child, childPos, currentOffset, parts, segments);
    if (child.isBlock && index < node.childCount - 1 && currentOffset > beforeChild) {
      parts.push("\n");
      currentOffset += 1;
    }
  });

  return currentOffset;
}

function resolveExactSuggestionMatch(text: string, suggestion: Suggestion): ResolvedSuggestionMatch | null {
  if (
    suggestion.span_start >= 0 &&
    suggestion.span_end <= text.length &&
    suggestion.span_start < suggestion.span_end &&
    text.slice(suggestion.span_start, suggestion.span_end) === suggestion.original_text &&
    anchorsPartiallyMatch(text, suggestion, suggestion.span_start, suggestion.span_end)
  ) {
    return {
      status: "current",
      spanStart: suggestion.span_start,
      spanEnd: suggestion.span_end,
    };
  }

  return null;
}

function findSuggestionCandidates(text: string, originalText: string): Array<{ start: number; end: number }> {
  if (!originalText) {
    return [];
  }

  const candidates: Array<{ start: number; end: number }> = [];
  let cursor = 0;
  while (cursor < text.length) {
    const nextIndex = text.indexOf(originalText, cursor);
    if (nextIndex < 0) {
      break;
    }
    candidates.push({
      start: nextIndex,
      end: nextIndex + originalText.length,
    });
    cursor = nextIndex + 1;
  }
  return candidates;
}

function anchorsMatch(text: string, suggestion: Suggestion, start: number, end: number): boolean {
  const beforeMatches = suggestion.anchor_before
    ? text.slice(Math.max(0, start - suggestion.anchor_before.length), start) === suggestion.anchor_before
    : true;
  const afterMatches = suggestion.anchor_after
    ? text.slice(end, end + suggestion.anchor_after.length) === suggestion.anchor_after
    : true;
  return beforeMatches && afterMatches;
}

function anchorsPartiallyMatch(text: string, suggestion: Suggestion, start: number, end: number): boolean {
  if (!suggestion.anchor_before && !suggestion.anchor_after) {
    return true;
  }
  const beforeMatches = suggestion.anchor_before
    ? text.slice(Math.max(0, start - suggestion.anchor_before.length), start) === suggestion.anchor_before
    : true;
  const afterMatches = suggestion.anchor_after
    ? text.slice(end, end + suggestion.anchor_after.length) === suggestion.anchor_after
    : true;
  return beforeMatches || afterMatches;
}

function staleSuggestion(suggestion: Suggestion): ResolvedSuggestionMatch {
  return {
    status: "stale",
    spanStart: suggestion.span_start,
    spanEnd: suggestion.span_end,
  };
}
