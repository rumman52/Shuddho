import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MarkdownMessage from "./MarkdownMessage";

test("renders common Markdown blocks, inline formatting, code and tables", () => {
  const tick = String.fromCharCode(96);
  const markdownText = [
    "# Heading",
    "",
    "**Bold** and *italic* with " + tick + "inline code" + tick + ".",
    "",
    "- First",
    "- Second",
    "",
    tick.repeat(3) + "ts",
    "const answer = 42;",
    tick.repeat(3),
    "",
    "| Name | Value |",
    "| --- | --- |",
    "| Rukh | AI |",
  ].join("\n");
  const html = renderToStaticMarkup(<MarkdownMessage content={markdownText} />);
  assert.match(html, /<h1>Heading<\/h1>/);
  assert.match(html, /<strong>Bold<\/strong>/);
  assert.match(html, /<em>italic<\/em>/);
  assert.match(html, /<code>inline code<\/code>/);
  assert.match(html, /<pre><code/);
  assert.match(html, /<table>/);
  assert.match(html, /<th>Name<\/th>/);
});

test("raw HTML is escaped and never becomes executable markup", () => {
  const html = renderToStaticMarkup(<MarkdownMessage content={'<img src=x onerror="alert(1)">\n<script>alert(1)</script>'} />);
  assert.doesNotMatch(html, /<img/);
  assert.doesNotMatch(html, /<script/);
  assert.match(html, /&lt;img/);
  assert.match(html, /&lt;script/);
});

test("unsafe link schemes are rendered as plain text instead of anchors", () => {
  const html = renderToStaticMarkup(<MarkdownMessage content={"[unsafe](javascript:alert(1)) and [safe](https://example.com/path)"} />);
  assert.doesNotMatch(html, /href="javascript:/i);
  assert.match(html, /href="https:\/\/example\.com\/path"/);
});
