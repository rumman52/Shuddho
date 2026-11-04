import type { ConversationMessageRecord, ConversationRecord } from "./client";

export type ConversationSourceLabel = (source: Record<string, unknown>) => string;

export function buildConversationMarkdown(
  conversation: ConversationRecord,
  messages: ConversationMessageRecord[],
  sourceLabel: ConversationSourceLabel = () => "Attached source",
  exportedAt = new Date().toISOString(),
): string {
  const lines = [
    "# " + conversation.title,
    "",
    "Exported: " + exportedAt,
    "",
  ];

  for (const message of messages) {
    lines.push("## You", "", message.created_at, "", message.text, "");

    const labels = message.selected_sources.map(sourceLabel).filter(Boolean);
    if (labels.length) lines.push("Attachments: " + labels.join(", "), "");

    const reply = message.assistant_reply;
    if (reply?.state === "completed" && reply.text.trim()) {
      lines.push("## Rukh AI", "", reply.text.trim(), "");
      if (reply.context_truncated) {
        lines.push("> Context was truncated to the most recent messages that fit.", "");
      }
    } else if (reply) {
      lines.push("> Rukh AI reply status: " + reply.state, "");
      if (reply.error) lines.push("> " + reply.error, "");
    }

    const agentRunCount = message.resource_links.filter(link => link.resource_type === "agent_run").length;
    if (agentRunCount) lines.push("Agent runs linked: " + agentRunCount, "");
    lines.push("---", "");
  }

  return lines.join("\n").trimEnd() + "\n";
}

export function buildConversationJson(
  conversation: ConversationRecord,
  messages: ConversationMessageRecord[],
  exportedAt = new Date().toISOString(),
): string {
  return JSON.stringify({
    schema_version: 1,
    exported_at: exportedAt,
    conversation,
    messages,
  }, null, 2) + "\n";
}

export function conversationExportFilename(title: string, extension: "md" | "json"): string {
  const safe = title.normalize("NFKC")
    .replace(/[\/\\\u0000-\u001f\u007f]+/g, "-")
    .replace(/[^\p{L}\p{M}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return (safe || "rukh-conversation") + "." + extension;
}
