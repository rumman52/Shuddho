import React, { type ReactNode } from "react";
import "./markdown-message.css";

const codeMarker = String.fromCharCode(96);
const fenceMarker = codeMarker.repeat(3);
const inlinePattern = new RegExp(
  "(" + codeMarker + "[^" + codeMarker + "\\n]+" + codeMarker +
  "|\\*\\*[^*\\n]+\\*\\*|__[^_\\n]+__|~~[^~\\n]+~~|\\*[^*\\n]+\\*|_[^_\\n]+_" +
  "|\\[([^\\]\\n]+)\\]\\(([^)\\s]+)(?:\\s+[\"']([^\"']*)[\"'])?\\))",
  "g",
);
const openingFencePattern = new RegExp("^" + fenceMarker + "([A-Za-z0-9_+.-]{0,24})[^\\n]*$");
const closingFencePattern = new RegExp("^" + fenceMarker + "\\s*$");

function safeHref(value: string): string | null {
  const candidate = value.trim();
  if (!candidate || candidate.length > 2048 || /[\s\\\u0000-\u001f\u007f]/.test(candidate)) return null;
  try {
    const url = new URL(candidate);
    if (!["http:", "https:", "mailto:"].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch {
    return null;
  }
}

function inlineNodes(value: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let index = 0;

  for (const match of value.matchAll(inlinePattern)) {
    const token = match[0];
    const start = match.index ?? 0;
    if (start > last) nodes.push(value.slice(last, start));

    if (token.startsWith(codeMarker)) {
      nodes.push(<code key={"code-" + index++}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**") || token.startsWith("__")) {
      nodes.push(<strong key={"strong-" + index++}>{inlineNodes(token.slice(2, -2))}</strong>);
    } else if (token.startsWith("~~")) {
      nodes.push(<del key={"del-" + index++}>{inlineNodes(token.slice(2, -2))}</del>);
    } else if (token.startsWith("*") || token.startsWith("_")) {
      nodes.push(<em key={"em-" + index++}>{inlineNodes(token.slice(1, -1))}</em>);
    } else {
      const label = match[2] ?? token;
      const href = safeHref(match[3] ?? "");
      nodes.push(href
        ? <a key={"link-" + index++} href={href} target={href.startsWith("mailto:") ? undefined : "_blank"} rel="noopener noreferrer">{label}</a>
        : label);
    }
    last = start + token.length;
  }

  if (last < value.length) nodes.push(value.slice(last));
  return nodes;
}

function tableCells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(cell => cell.trim());
}

function isTableSeparator(line: string): boolean {
  const cells = tableCells(line);
  return cells.length >= 2 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
}

function isTableAt(lines: string[], index: number): boolean {
  return index + 1 < lines.length && lines[index].includes("|") && isTableSeparator(lines[index + 1]);
}

function isHorizontalRule(line: string): boolean {
  return /^(?:-{3,}|_{3,}|\*{3,})\s*$/.test(line.trim());
}

function isListLine(line: string): boolean {
  return /^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(line);
}

function startsBlock(lines: string[], index: number): boolean {
  const line = lines[index] ?? "";
  return line.startsWith(fenceMarker) || /^#{1,6}\s+/.test(line) || /^>\s?/.test(line) ||
    isHorizontalRule(line) || isListLine(line) || isTableAt(lines, index);
}

function renderBlocks(source: string, prefix = "block"): ReactNode[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  let blockIndex = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(openingFencePattern);
    if (fence) {
      const language = fence[1];
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !closingFencePattern.test(lines[index])) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      const className = language ? "language-" + language : undefined;
      blocks.push(<pre key={prefix + "-code-" + blockIndex++}><code className={className}>{code.join("\n")}</code></pre>);
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      const tag = ("h" + heading[1].length) as "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
      blocks.push(React.createElement(tag, { key: prefix + "-heading-" + blockIndex++ }, inlineNodes(heading[2])));
      index += 1;
      continue;
    }

    if (isHorizontalRule(line)) {
      blocks.push(<hr key={prefix + "-hr-" + blockIndex++} />);
      index += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push(<blockquote key={prefix + "-quote-" + blockIndex++}>{renderBlocks(quote.join("\n"), prefix + "-quote")}</blockquote>);
      continue;
    }

    if (isListLine(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const items: string[] = [];
      let start = 1;
      while (index < lines.length && isListLine(lines[index]) &&
        /^\s*\d+[.)]\s+/.test(lines[index]) === ordered) {
        const current = lines[index];
        if (items.length === 0 && ordered) start = Number(current.match(/^\s*(\d+)/)?.[1] ?? 1);
        items.push(current.replace(/^\s*(?:[-*+]\s+|\d+[.)]\s+)/, ""));
        index += 1;
      }
      const children = items.map((item, itemIndex) => <li key={prefix + "-item-" + itemIndex}>{inlineNodes(item)}</li>);
      blocks.push(ordered
        ? <ol key={prefix + "-list-" + blockIndex++} start={start}>{children}</ol>
        : <ul key={prefix + "-list-" + blockIndex++}>{children}</ul>);
      continue;
    }

    if (isTableAt(lines, index)) {
      const headers = tableCells(lines[index]);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="rukh-markdown-table-scroll" role="region" aria-label="Scrollable table" tabIndex={0} key={prefix + "-table-" + blockIndex++}>
          <table>
            <thead><tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{inlineNodes(cell)}</th>)}</tr></thead>
            <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{headers.map((_, cellIndex) =>
              <td key={cellIndex}>{inlineNodes(row[cellIndex] ?? "")}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }

    const paragraph = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !startsBlock(lines, index)) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={prefix + "-paragraph-" + blockIndex++}>{inlineNodes(paragraph.join(" "))}</p>);
  }

  return blocks;
}

export default function MarkdownMessage({ content }: { content: string }) {
  return <div className="rukh-markdown" dir="auto">{renderBlocks(content || "")}</div>;
}
