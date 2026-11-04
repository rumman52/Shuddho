import assert from "node:assert/strict";
import test from "node:test";
import {
  buildConversationJson,
  buildConversationMarkdown,
  conversationExportFilename,
} from "./conversationExport";
import type { ConversationMessageRecord, ConversationRecord } from "./client";

const conversation: ConversationRecord = {
  id: "conversation-1",
  title: "Project plan",
  message_sequence: 1,
  created_at: "2026-11-04T00:00:00Z",
  updated_at: "2026-11-04T00:01:00Z",
};
const messages: ConversationMessageRecord[] = [{
  id: "message-1",
  conversation_id: conversation.id,
  sequence: 1,
  text: "Prepare the project plan.",
  selected_sources: [{ resource_type: "document_version", resource_id: "version-1" }],
  resource_links: [],
  created_at: "2026-11-04T00:00:30Z",
  assistant_reply: {
    state: "completed",
    text: "## Summary\n\nThe plan is ready.",
    context_truncated: true,
  },
}];

test("Markdown export includes the full turn, assistant answer, and attachment label", () => {
  const value = buildConversationMarkdown(
    conversation,
    messages,
    source => source.resource_id === "version-1" ? "brief.pdf" : "Attached source",
    "2026-11-04T01:00:00Z",
  );
  assert.match(value, /^# Project plan/m);
  assert.match(value, /Prepare the project plan\./);
  assert.match(value, /## Rukh AI/);
  assert.match(value, /The plan is ready\./);
  assert.match(value, /brief\.pdf/);
  assert.match(value, /context was truncated/i);
});

test("JSON export is valid and preserves conversation message provenance", () => {
  const value = JSON.parse(buildConversationJson(conversation, messages, "2026-11-04T01:00:00Z"));
  assert.equal(value.schema_version, 1);
  assert.equal(value.conversation.title, "Project plan");
  assert.equal(value.messages[0].assistant_reply.text, "## Summary\n\nThe plan is ready.");
  assert.equal(value.messages[0].selected_sources[0].resource_id, "version-1");
});

test("export filenames remove path separators and control characters while retaining Unicode", () => {
  assert.equal(conversationExportFilename("../প্রকল্প\\report\n", "md"), "প্রকল্প-report.md");
});
