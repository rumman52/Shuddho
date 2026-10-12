import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  CoworkerClient, WorkspaceError, type ConversationRecord,
  type ConversationMessageRecord, type ConversationActivityRecord,
} from "./client";

/** CW-07: messages are not run authorizations; explicit dispatch is a separate click. */
export default function ConversationWorkspace({ client, openAgent }: {
  client: CoworkerClient; openAgent: () => void;
}) {
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [selected, setSelected] = useState("");
  const [messages, setMessages] = useState<ConversationMessageRecord[]>([]);
  const [activity, setActivity] = useState<ConversationActivityRecord[]>([]);
  const [title, setTitle] = useState("");
  const [draft, setDraft] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [disabled, setDisabled] = useState(false);
  const createKey = useRef<string | null>(null);
  const messageKey = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    client.conversations(controller.signal).then(({ items }) => {
      if (controller.signal.aborted) return;
      setDisabled(false);
      setConversations(items);
      setSelected(current => items.some(item => item.id === current) ? current : (items[0]?.id ?? ""));
    }).catch(cause => {
      if (controller.signal.aborted) return;
      setDisabled(cause instanceof WorkspaceError && [403, 404, 409].includes(cause.status));
      setError(cause instanceof Error ? cause.message : "Could not load conversations.");
    });
    return () => controller.abort();
  }, [client]);

  async function reloadConversation(id: string) {
    const [messagesResponse, activityResponse] = await Promise.all([
      client.conversationMessages(id), client.conversationActivity(id),
    ]);
    setMessages(messagesResponse.items);
    setActivity(activityResponse.items);
  }

  useEffect(() => {
    setMessages([]);
    setActivity([]);
    if (!selected) return;
    const controller = new AbortController();
    const reload = async () => {
      try {
        const [chat, projection] = await Promise.all([
          client.conversationMessages(selected, controller.signal),
          client.conversationActivity(selected, controller.signal),
        ]);
        if (!controller.signal.aborted) {
          setMessages(chat.items);
          setActivity(projection.items);
        }
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Could not refresh conversation.");
      }
    };
    void reload();
    const timer = window.setInterval(() => { void reload(); }, 5000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [client, selected]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (working || !title.trim()) return;
    setWorking(true); setError(""); setNotice("");
    try {
      const key = createKey.current ?? crypto.randomUUID();
      createKey.current = key;
      const record = await client.createConversation(title.trim(), key);
      const response = await client.conversations();
      setConversations(response.items);
      setSelected(record.id);
      setTitle("");
      createKey.current = null;
      setNotice("Private conversation created.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Conversation creation failed.");
    } finally { setWorking(false); }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!selected || working || !draft.trim()) return;
    setWorking(true); setError(""); setNotice("");
    try {
      const key = messageKey.current ?? crypto.randomUUID();
      messageKey.current = key;
      await client.appendConversationMessage(selected, draft.trim(), key);
      setDraft("");
      messageKey.current = null;
      await reloadConversation(selected);
      setNotice("Message saved. Starting a task requires a separate action.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Message could not be saved.");
    } finally { setWorking(false); }
  }

  async function dispatch(item: ConversationMessageRecord) {
    if (!selected || working) return;
    setWorking(true); setError(""); setNotice("");
    try {
      await client.dispatchConversationMessage(selected, item.id, item.sequence);
      await reloadConversation(selected);
      setNotice("Bounded Agent work admitted. Check Agent for full progress.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Agent admission was not accepted.");
    } finally { setWorking(false); }
  }

  async function remove() {
    if (!selected || working || !window.confirm("Delete and redact this conversation?")) return;
    setWorking(true); setError("");
    try {
      await client.deleteConversation(selected);
      const response = await client.conversations();
      setConversations(response.items);
      setSelected(response.items[0]?.id ?? "");
      setNotice("Conversation deleted.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Deletion failed.");
    } finally { setWorking(false); }
  }

  const statusByMessage = new Map(activity.map(item => [item.message_id, item]));
  const selectedConversation = conversations.find(item => item.id === selected);
  return <section className="cw-card" aria-label="Private conversations">
    <header>
      <h2>Conversations & activity</h2>
      <p>Save a private brief, then explicitly start bounded Agent work. No message approves an external action.</p>
    </header>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {disabled ? <p>Conversations are not enabled for this workspace. Existing work is unchanged.</p> : <>
      <form onSubmit={create}>
        <label htmlFor="cw-conversation-title">New conversation</label>
        <input id="cw-conversation-title" value={title} minLength={1} maxLength={160}
          disabled={working} onChange={event => setTitle(event.target.value)} required />
        <button type="submit" disabled={working || !title.trim()}>Create private conversation</button>
      </form>
      <label htmlFor="cw-conversation-select">Conversation</label>
      <select id="cw-conversation-select" value={selected}
        onChange={event => { setSelected(event.target.value); setDraft(""); messageKey.current = null; }}>
        <option value="">Choose a conversation</option>
        {conversations.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select>
      {selectedConversation && <>
        <button type="button" onClick={() => { void remove(); }} disabled={working}>Delete and redact</button>
        <ol aria-label="Conversation messages">
          {messages.map(item => {
            const run = statusByMessage.get(item.id);
            const linked = item.resource_links.some(link => link.resource_type === "agent_run");
            return <li key={item.id}>
              <p dir="auto">{item.text}</p>
              <small>Message {item.sequence} · {new Date(item.created_at).toLocaleString()}</small>
              {run && <p role="status">Agent {run.state}: {run.detail}</p>}
              {!linked && item.sequence === selectedConversation.message_sequence &&
                <button type="button" disabled={working} onClick={() => { void dispatch(item); }}>
                  Start bounded Agent work
                </button>}
              {linked && <button type="button" onClick={openAgent}>View Agent runs</button>}
            </li>;
          })}
        </ol>
        <form onSubmit={send}>
          <label htmlFor="cw-conversation-message">New message</label>
          <textarea id="cw-conversation-message" dir="auto" value={draft} minLength={1} maxLength={12000}
            rows={4} disabled={working} required onChange={event => setDraft(event.target.value)} />
          <button type="submit" disabled={working || !draft.trim()}>Save message</button>
        </form>
      </>}
    </>}
  </section>;
}
