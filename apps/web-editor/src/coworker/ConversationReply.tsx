import React from "react";
import type { AssistantReply } from "./client";
import MarkdownMessage from "./MarkdownMessage";
import ReadAloudButton from "./ReadAloudButton";

export default function ConversationReply({
  reply, pending, error = "", retry, disabled, onStop, stopping = false,
}: {
  reply: AssistantReply | null;
  pending: boolean;
  error?: string;
  retry: () => void;
  disabled: boolean;
  onStop?: () => void;
  stopping?: boolean;
}) {
  const complete = reply?.state === "completed";
  const generating = reply?.state === "generating";
  const stopped = reply?.state === "cancelled";
  const recoverable = Boolean(error) || ["failed", "interrupted"].includes(reply?.state ?? "");
  const hasPartialText = Boolean(reply?.text.trim()) && (generating || Boolean(error));
  const showStop = Boolean(onStop) && (pending || generating || Boolean(error));
  return <div className="cw-reply" aria-label="Rukh AI reply" aria-busy={(pending || generating) && !error}>
    {complete ? <>
      {reply.context_truncated ? <p className="cw-context-note">Earlier conversation context was shortened to keep this reply focused.</p> : null}
      <MarkdownMessage text={reply.text} />
      <div className="cw-reply-actions">
        <button type="button" className="cw-text-button" aria-label="Copy AI reply" onClick={() => void navigator.clipboard?.writeText(reply.text)}>Copy</button>
        <ReadAloudButton text={reply.text} />
      </div>
    </> : stopped ? <>
      {reply.text ? <MarkdownMessage text={reply.text} /> : null}
      <p className="cw-reply-status" role="status">Reply stopped.</p>
      <button type="button" className="cw-text-button" aria-label="Retry AI reply" disabled={disabled} onClick={retry}>Try again</button>
    </> : recoverable ? <>
      {hasPartialText ? <MarkdownMessage text={reply?.text ?? ""} /> : null}
      <p className="cw-reply-error" role="alert">{error || reply?.error || "The reply was interrupted. Try again."}</p>
      <button type="button" className="cw-text-button" aria-label="Retry AI reply" disabled={disabled} onClick={retry}>Try again</button>
      {showStop ? <button type="button" className="cw-text-button" aria-label="Stop AI reply" disabled={stopping} onClick={onStop}>{stopping ? "Stopping…" : "Stop"}</button> : null}
    </> : hasPartialText ? <>
      <MarkdownMessage text={reply?.text ?? ""} />
      <p className="cw-reply-status" role="status">Rukh is replying…</p>
      {showStop ? <button type="button" className="cw-text-button" aria-label="Stop AI reply" disabled={stopping} onClick={onStop}>{stopping ? "Stopping…" : "Stop"}</button> : null}
    </> : pending || generating ? <>
      <p className="cw-reply-status" role="status">Rukh is replying…</p>
      {showStop ? <button type="button" className="cw-text-button" aria-label="Stop AI reply" disabled={stopping} onClick={onStop}>{stopping ? "Stopping…" : "Stop"}</button> : null}
    </> : <p className="cw-reply-error" role="alert">{reply?.error ?? "No AI reply is available yet."}</p>}
  </div>;
}