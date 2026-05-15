import type { TextSpan } from '../index.js';

export interface Segment { segment: string; index: number; endIndex: number; codePointIndex: number; }
const BANGLA_RE = /[\u0980-\u09FF]/u;
const MARK_OR_JOINER_RE = /[\u09BC\u09BE-\u09C4\u09C7\u09C8\u09CB\u09CC\u09CD\u0981-\u0983\u200C\u200D]/u;

export function normalizeBanglaText(text: string): string { return text.normalize('NFC'); }
export function isBanglaChar(char: string): boolean { return BANGLA_RE.test(char) || char === '।' || char === '॥'; }
export function isBanglaText(text: string): boolean { return [...text].some(isBanglaChar); }

export function toCodePointOffsets(text: string, utf16Start: number, utf16End: number): { codePointStartIndex: number; codePointEndIndex: number } {
  const start = [...text.slice(0, utf16Start)].length;
  const end = start + [...text.slice(utf16Start, utf16End)].length;
  return { codePointStartIndex: start, codePointEndIndex: end };
}
export function toUtf16Offsets(text: string, codePointStart: number, codePointEnd: number): { utf16StartIndex: number; utf16EndIndex: number } {
  const chars = [...text];
  return { utf16StartIndex: chars.slice(0, codePointStart).join('').length, utf16EndIndex: chars.slice(0, codePointEnd).join('').length };
}

export function getGraphemeSegments(text: string): Segment[] {
  const Seg = (Intl as typeof Intl & { Segmenter?: new (locale?: string, options?: { granularity: 'grapheme' }) => { segment(input: string): Iterable<{ segment: string; index: number }> } }).Segmenter;
  if (Seg) {
    let cp = 0;
    return [...new Seg('bn', { granularity: 'grapheme' }).segment(text)].map((item) => {
      const out = { segment: item.segment, index: item.index, endIndex: item.index + item.segment.length, codePointIndex: cp };
      cp += [...item.segment].length;
      return out;
    });
  }
  const result: Segment[] = [];
  let utf16 = 0;
  let cp = 0;
  for (const char of text) {
    if (result.length && MARK_OR_JOINER_RE.test(char)) {
      const prev = result[result.length - 1]!;
      prev.segment += char;
      prev.endIndex += char.length;
    } else {
      result.push({ segment: char, index: utf16, endIndex: utf16 + char.length, codePointIndex: cp });
    }
    utf16 += char.length;
    cp += 1;
  }
  return result;
}

export function snapSpanToGraphemeBoundary(text: string, start: number, end: number): TextSpan {
  const segments = getGraphemeSegments(text);
  let s = Math.max(0, Math.min(start, text.length));
  let e = Math.max(s, Math.min(end, text.length));
  for (const seg of segments) {
    if (s > seg.index && s < seg.endIndex) s = seg.index;
    if (e > seg.index && e < seg.endIndex) e = seg.endIndex;
  }
  const cp = toCodePointOffsets(text, s, e);
  return { startIndex: s, endIndex: e, utf16StartIndex: s, utf16EndIndex: e, codePointStartIndex: cp.codePointStartIndex, codePointEndIndex: cp.codePointEndIndex, graphemeStartIndex: segments.findIndex((x) => x.index >= s), graphemeEndIndex: segments.findIndex((x) => x.endIndex >= e) + 1 };
}
