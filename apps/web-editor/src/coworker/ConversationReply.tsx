import { useState } from "react";
import type { AssistantReply } from "./client";
import MarkdownMessage from "./MarkdownMessage";
import ReadAloudButton from "./ReadAloudButton";

export default function ConversationReply({ reply, pending, error, retry, disabled }: {
  reply?: AssistantReply | null; pending: boolean; error?: string; retry: () => void; disabled: boolean;
}) {
  const [copyStatus, setCopyStatus] = useState("");
  const complete = reply?.state === "completed";
  return <section className="rukh-chat-answer" aria-label="Rukh AI reply" aria-busy={pending || reply?.state === "generating"}>
    <div className="rukh-answer-heading"><span className="rukh-chat-mark" aria-hidden="true">R</span><strong>Rukh AI</strong></div>
    {complete ? <>
      <div className="rukh-answer-text"><MarkdownMessage content={reply.text} /></div>
      {reply.context_truncated && <p className="rukh-muted">This answer used the most recent messages that fit in the conversation context.</p>}
      <div className="rukh-speech-actions">
        <button type="button" className="cw-text-button" aria-label="Copy AI reply" onClick={async () => {
          try { await navigator.clipboard.writeText(reply.text); setCopyStatus("Copied"); }
          catch { setCopyStatus("Could not copy. Select the answer to copy it."); }
        }}>Copy answer</button>
        <ReadAloudButton text={reply.text} disabled={disabled} />
      </div>
      <span className="rukh-copy-status" role="status">{copyStatus}</span>
    </> : error ? <><p className="cw-error" role="alert">{error}</p><button type="button" className="cw-text-button" aria-label="Retry AI reply" disabled={disabled} onClick={retry}>Check reply again</button></> :
      pending || reply?.state === "generating" ? <p className="rukh-reply-pending" role="status"><span aria-hidden="true">•••</span> Rukh is replying…</p> :
      <p className="cw-error" role="alert">{reply?.error ?? "This reply could not be completed. Send a new message to try again."}</p>}
  </section>;
}
