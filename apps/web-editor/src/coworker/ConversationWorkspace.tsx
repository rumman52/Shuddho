import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  CoworkerClient, WorkspaceError, type ConversationRecord,
  type ConversationMessageRecord, type ConversationActivityRecord, type WorkspaceManifest, type MemoryFact,
} from "./client";
import { RefreshOrder } from "./refreshOrder";
import { getInitialConversationId } from "../../../coworker/src/navigation.mjs";

/** CW-07: messages are not run authorizations; explicit dispatch is a separate click. */
export default function ConversationWorkspace({ client, openAgent }: {
  client: CoworkerClient; openAgent: (runId: string) => void;
}) {
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [selected, setSelected] = useState(() => typeof window !== "undefined" ? getInitialConversationId(window.location.search) ?? "" : "");
  const [messages, setMessages] = useState<ConversationMessageRecord[]>([]);
  const [activity, setActivity] = useState<ConversationActivityRecord[]>([]);
  const [manifest, setManifest] = useState<WorkspaceManifest | null>(null);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [manifestError, setManifestError] = useState("");
  const [memoryFacts, setMemoryFacts] = useState<MemoryFact[]>([]);
  const [memoryEnabled, setMemoryEnabled] = useState(false);
  const [memoryError, setMemoryError] = useState("");
  const [editingMemory, setEditingMemory] = useState("");
  const [memoryDraft, setMemoryDraft] = useState("");
  const [title, setTitle] = useState("");
  const [draft, setDraft] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [disabled, setDisabled] = useState(false);
  const createKey = useRef<{ fingerprint: string; key: string } | null>(null);
  const messageKey = useRef<{ fingerprint: string; key: string } | null>(null);
  const refreshOrder = useRef(new RefreshOrder());
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [mobilePanel, setMobilePanel] = useState<"conversations" | "context" | null>(null);
  const mobilePanelTriggerRef = useRef<HTMLButtonElement | null>(null);
  const mobilePanelCloseRef = useRef<HTMLButtonElement | null>(null);
  const conversationPanelRef = useRef<HTMLElement | null>(null);
  const contextPanelRef = useRef<HTMLElement | null>(null);

  function openMobilePanel(panel: "conversations" | "context", trigger: HTMLButtonElement) {
    mobilePanelTriggerRef.current = trigger;
    setMobilePanel(panel);
  }

  function closeMobilePanel() {
    setMobilePanel(null);
  }

  useEffect(() => {
    if (!mobilePanel) return;
    const panel = mobilePanel === "conversations" ? conversationPanelRef.current : contextPanelRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => panel?.querySelectorAll<HTMLElement>(
      "a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex='-1'])"
    ) ?? [];
    const frame = window.requestAnimationFrame(() => {
      (mobilePanelCloseRef.current ?? focusable()[0])?.focus();
    });
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobilePanel(null);
        return;
      }
      if (event.key !== "Tab") return;
      const items = Array.from(focusable());
      if (!items.length) { event.preventDefault(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      window.requestAnimationFrame(() => mobilePanelTriggerRef.current?.focus());
    };
  }, [mobilePanel]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 721px)");
    const closeOnDesktop = () => { if (media.matches) setMobilePanel(null); };
    media.addEventListener("change", closeOnDesktop);
    return () => media.removeEventListener("change", closeOnDesktop);
  }, []);

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

  useEffect(() => {
    const controller = new AbortController();
    client.workspaceManifest(controller.signal).then(result => {
      if (!controller.signal.aborted) { setManifest(result); setManifestError(""); }
    }).catch(cause => {
      if (!controller.signal.aborted) setManifestError(
        cause instanceof Error ? cause.message : "Workspace sources are unavailable."
      );
    });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    const controller = new AbortController();
    client.memory(controller.signal).then(reply => {
      if (!controller.signal.aborted) {
        setMemoryEnabled(reply.enabled);
        setMemoryFacts(reply.enabled ? reply.facts : []);
      }
    }).catch(cause => {
      if (!controller.signal.aborted) setMemoryError(
        cause instanceof Error ? cause.message : "Memory review is unavailable."
      );
    });
    return () => controller.abort();
  }, [client]);

  async function refreshMemory() {
    const reply = await client.memory();
    setMemoryEnabled(reply.enabled);
    setMemoryFacts(reply.enabled ? reply.facts : []);
  }

  async function saveMemory(fact: MemoryFact) {
    if (working || !memoryDraft.trim()) return;
    setWorking(true); setMemoryError("");
    try {
      await client.updateMemoryFact(
        fact.id, memoryDraft.trim(), fact.language, fact.version, fact.expires_at ?? null,
      );
      await refreshMemory();
      setEditingMemory(""); setMemoryDraft("");
      setNotice("Memory updated with version check.");
    } catch (cause) {
      setMemoryError(cause instanceof Error ? cause.message : "Memory update failed.");
      await refreshMemory().catch(() => undefined);
    } finally { setWorking(false); }
  }

  async function removeMemory(fact: MemoryFact) {
    if (working || !window.confirm("Delete this saved memory fact?")) return;
    setWorking(true); setMemoryError("");
    try {
      await client.deleteMemoryFact(fact.id);
      await refreshMemory();
      setEditingMemory(""); setMemoryDraft("");
      setNotice("Selected memory fact deleted.");
    } catch (cause) {
      setMemoryError(cause instanceof Error ? cause.message : "Memory deletion failed.");
    } finally { setWorking(false); }
  }

  async function reloadConversation(id: string) {
    if (selectedRef.current !== id) return;
    const revision = refreshOrder.current.start();
    const [messagesResponse, activityResponse, listResponse] = await Promise.all([
      client.conversationHistory(id), client.conversationActivityHistory(id), client.conversations(),
    ]);
    if (selectedRef.current !== id || !refreshOrder.current.isCurrent(revision)) return;
    setMessages(messagesResponse.items);
    setActivity(activityResponse.items);
    setConversations(listResponse.items);
  }

  useEffect(() => {
    // A response from an old conversation or refresh must not roll back newer
    // run progress, especially after a user-initiated dispatch/cancellation.
    refreshOrder.current.invalidate();
    setMessages([]);
    setActivity([]);
    if (!selected) return;
    const controller = new AbortController();
    let polling = false;
    const reload = async () => {
      if (polling || controller.signal.aborted) return;
      polling = true;
      const revision = refreshOrder.current.start();
      try {
        const [chat, projection, latestList] = await Promise.all([
          client.conversationHistory(selected, controller.signal),
          client.conversationActivityHistory(selected, controller.signal),
          client.conversations(controller.signal),
        ]);
        if (!controller.signal.aborted && selectedRef.current === selected
            && refreshOrder.current.isCurrent(revision)) {
          setMessages(chat.items);
          setActivity(projection.items);
          setConversations(latestList.items);
        }
      } catch (cause) {
        if (!controller.signal.aborted && refreshOrder.current.isCurrent(revision))
          setError(cause instanceof Error ? cause.message : "Could not refresh conversation.");
      } finally {
        polling = false;
      }
    };
    void reload();
    const timer = window.setInterval(() => { void reload(); }, 5000);
    return () => { controller.abort(); window.clearInterval(timer); refreshOrder.current.invalidate(); };
  }, [client, selected]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (working || !title.trim()) return;
    setWorking(true); setError(""); setNotice("");
    try {
      const normalizedTitle = title.trim();
      if (createKey.current?.fingerprint !== normalizedTitle)
        createKey.current = { fingerprint: normalizedTitle, key: crypto.randomUUID() };
      const record = await client.createConversation(normalizedTitle, createKey.current.key);
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
      const text = draft.trim();
      const sources = [...selectedSources];
      const fingerprint = JSON.stringify({ conversation: selected, text, sources });
      if (messageKey.current?.fingerprint !== fingerprint)
        messageKey.current = { fingerprint, key: crypto.randomUUID() };
      await client.appendConversationMessage(selected, text, messageKey.current.key, sources);
      setDraft("");
      setSelectedSources([]);
      messageKey.current = null;
      const currentManifest = await client.workspaceManifest().catch(() => null);
      if (currentManifest) setManifest(currentManifest);
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

  async function cancel(item: ConversationMessageRecord, run: ConversationActivityRecord) {
    if (!selected || !selectedConversation || working) return;
    setWorking(true); setError(""); setNotice("");
    try {
      await client.cancelConversationAgent(selected, item.id, selectedConversation.message_sequence, run.event_sequence);
      await reloadConversation(selected);
      setNotice("Agent cancellation recorded. Continue with a new reviewed message.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Agent cancellation was not accepted.");
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
  return <section className="rukh-conversation-workspace" aria-label="Private conversations">
    <div className="rukh-mobile-workspace-tools" aria-label="Workspace panels" aria-hidden={mobilePanel !== null ? true : undefined}>
      <button type="button" aria-label="Open conversations" aria-controls="rukh-conversation-list"
        aria-expanded={mobilePanel === "conversations"}
        onClick={event => openMobilePanel("conversations", event.currentTarget)}>
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M3 4.5h14M3 9.9h14M3 15.3h9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
        Conversations
      </button>
      <button type="button" aria-label="Open workspace context" aria-controls="rukh-context-panel"
        aria-expanded={mobilePanel === "context"}
        onClick={event => openMobilePanel("context", event.currentTarget)}>
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 5h12M4 10h8M4 15h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><circle cx="15" cy="10" r="2" stroke="currentColor" strokeWidth="1.3"/></svg>
        Context
      </button>
    </div>
    <aside ref={conversationPanelRef} id="rukh-conversation-list"
      className={"rukh-conversation-list" + (mobilePanel === "conversations" ? " rukh-mobile-panel-open" : "")}
      aria-label="Private conversations"
      role={mobilePanel === "conversations" ? "dialog" : undefined}
      aria-modal={mobilePanel === "conversations" ? true : undefined}
      aria-labelledby="rukh-conversations-heading"
      aria-hidden={mobilePanel === "context" ? true : undefined}>
      <div className="rukh-panel-heading"><div><span className="cw-eyebrow">WORKSPACE</span><h2 id="rukh-conversations-heading">Conversations</h2></div>
        <div className="rukh-panel-heading-actions"><span className="rukh-count">{conversations.length}</span>
          <button className="rukh-mobile-panel-close" ref={mobilePanel === "conversations" ? mobilePanelCloseRef : null}
            type="button" aria-label="Close conversations" onClick={closeMobilePanel}>×</button>
        </div>
      </div>
      {error && <p className="cw-error" role="alert">{error}</p>}
      {notice && <p className="cw-notice" role="status">{notice}</p>}
      {disabled ? <p className="rukh-muted">Conversations are not enabled for this workspace. Existing work is unchanged.</p> : <>
        <form className="rukh-conversation-create" onSubmit={create}>
          <label className="rukh-sr-only" htmlFor="cw-conversation-title">New conversation title</label>
          <input id="cw-conversation-title" value={title} placeholder="Name a conversation…" minLength={1} maxLength={160}
            disabled={working} onChange={event => setTitle(event.target.value)} required />
          <button type="submit" aria-label="Create private conversation" disabled={working || !title.trim()}>＋</button>
        </form>
        <ul className="rukh-conversation-items">
          {conversations.map(item => <li key={item.id}>
            <button type="button" aria-pressed={selected === item.id} onClick={() => { setSelected(item.id); setDraft(""); setSelectedSources([]); messageKey.current = null; setMobilePanel(null); }}>
              <span className="rukh-conversation-item-title">{item.title}</span>
              <small>{new Date(item.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</small>
            </button>
          </li>)}
        </ul>
        {conversations.length === 0 && <p className="rukh-muted">Your private conversations will appear here.</p>}
      </>}
      <p className="rukh-panel-footnote">Messages are private workspace records. Saving a message does not start Agent work.</p>
    </aside>

    <section aria-hidden={mobilePanel !== null ? true : undefined} className="rukh-conversation-thread" aria-label="Conversation">
      <header className="rukh-thread-header">
        <div><span className="cw-eyebrow">YOUR COWORKER</span><h2>{selectedConversation?.title ?? "Start a conversation"}</h2></div>
        {selectedConversation && <button type="button" className="cw-text-button" onClick={() => { void remove(); }} disabled={working}>Delete conversation</button>}
      </header>
      {!selectedConversation ? <div className="rukh-thread-empty"><span aria-hidden="true">✳</span><h3>Give your work a place to begin.</h3><p>Create a private conversation on the left, then add a brief or a question. Agent work always requires a separate action.</p></div> : <>
        {messages.length === 0 ? <div className="rukh-thread-empty"><span aria-hidden="true">✳</span><h3>What should we work on?</h3><p>Share context, attach approved workspace documents, or ask for a plan. Nothing is dispatched automatically.</p></div> :
          <ol className="rukh-message-list" aria-label="Conversation messages">
            {messages.map(item => {
              const run = statusByMessage.get(item.id);
              const linked = item.resource_links.find(link => link.resource_type === "agent_run");
              const activeRun = run && !["completed", "failed", "cancelled", "needs_input", "blocked"].includes(run.state);
              const canDispatch = !linked && item.sequence === selectedConversation.message_sequence;
              return <li className="rukh-message" key={item.id}>
                <p dir="auto">{item.text}</p>
                <div className="rukh-message-meta"><small>Message {item.sequence} · {new Date(item.created_at).toLocaleString()}</small>
                  {run && <span role="status">Agent {run.state}: {run.detail}</span>}
                </div>
                {(activeRun || canDispatch || linked) && <div className="rukh-message-actions">
                  {activeRun && run && <button type="button" disabled={working} onClick={() => { void cancel(item, run); }}>Cancel Agent work</button>}
                  {canDispatch && <button type="button" disabled={working} onClick={() => { void dispatch(item); }}>Start bounded Agent work</button>}
                  {linked && <button type="button" onClick={() => openAgent(linked.resource_id)}>View Agent run</button>}
                </div>}
              </li>;
            })}
          </ol>}
        <form className="rukh-message-composer" onSubmit={send}>
          <label className="rukh-sr-only" htmlFor="cw-conversation-message">New message</label>
          <textarea id="cw-conversation-message" dir="auto" value={draft} minLength={1} maxLength={12000}
            rows={4} disabled={working} required onChange={event => setDraft(event.target.value)}
            placeholder="Message your coworker…" />
          <div><span>{selectedSources.length ? `${selectedSources.length} source(s) attached` : "Your message is saved privately"}</span>
            <button type="submit" disabled={working || !draft.trim()}>Save message <span aria-hidden="true">↗</span></button>
          </div>
        </form>
      </>}
    </section>

    <aside ref={contextPanelRef} id="rukh-context-panel"
      className={"rukh-context-panel" + (mobilePanel === "context" ? " rukh-mobile-panel-open" : "")}
      aria-label="Workspace context"
      role={mobilePanel === "context" ? "dialog" : undefined}
      aria-modal={mobilePanel === "context" ? true : undefined}
      aria-labelledby="rukh-context-heading"
      aria-hidden={mobilePanel === "conversations" ? true : undefined}>
      <section>
        <div className="rukh-panel-heading"><div><span className="cw-eyebrow">CONTEXT</span><h3 id="rukh-context-heading">Workspace sources</h3></div>
          <button className="rukh-mobile-panel-close" ref={mobilePanel === "context" ? mobilePanelCloseRef : null}
            type="button" aria-label="Close workspace context" onClick={closeMobilePanel}>×</button>
        </div>
        {manifestError && <p className="rukh-muted" role="status">{manifestError}</p>}
        {!manifest && !manifestError && <p className="rukh-muted">Loading available sources…</p>}
        {manifest && <>
          <p className="rukh-context-revision">Revision <code>{manifest.revision_sha256.slice(0, 12)}</code></p>
          {manifest.truncated.documents && <p className="rukh-muted">Only the first document page is shown.</p>}
          {manifest.documents.filter(doc => doc.available).length === 0 ? <p className="rukh-muted">No available documents yet.</p> :
            <div className="rukh-source-list">
              {manifest.documents.filter(doc => doc.available).map(doc =>
                <label key={doc.version_id}>
                  <input type="checkbox" checked={selectedSources.includes(doc.version_id)}
                    disabled={working || (!selectedSources.includes(doc.version_id) && selectedSources.length >= 5)}
                    onChange={event => setSelectedSources(current => event.target.checked
                      ? [...current, doc.version_id].slice(0, 5)
                      : current.filter(id => id !== doc.version_id))} />
                  <span><strong>{doc.name}</strong><small>Version {doc.version} · {doc.sha256.slice(0, 10)}</small></span>
                </label>
              )}
            </div>}
          <p className="rukh-panel-footnote">Selected sources are untrusted inputs, not instructions or permissions. Maximum five per message.</p>
        </>}
      </section>
      <section>
        <div className="rukh-panel-heading"><div><span className="cw-eyebrow">ACTIVITY</span><h3>Agent activity</h3></div></div>
        {activity.length === 0 ? <p className="rukh-muted">No Agent runs in this conversation.</p> :
          <ul className="rukh-activity-list">{activity.slice(-5).reverse().map(item => <li key={item.run_id}>
            <span className={`rukh-activity-dot rukh-activity-${item.state}`} aria-hidden="true" />
            <span><strong>{item.state.replace(/_/g, " ")}</strong><small>{item.detail}</small></span>
          </li>)}</ul>}
      </section>
      <section>
        <div className="rukh-panel-heading"><div><span className="cw-eyebrow">MEMORY</span><h3>Saved context</h3></div></div>
        {memoryError && <p className="cw-error" role="alert">{memoryError}</p>}
        {!memoryEnabled ? <p className="rukh-muted">Memory is disabled for this workspace.</p> :
          <details className="rukh-memory-details">
            <summary>Review saved memory ({memoryFacts.length})</summary>
            <p className="rukh-panel-footnote">Memory is separate from messages and never authorizes external actions.</p>
            <ul>{memoryFacts.map(fact => <li key={fact.id}>
              <strong>{fact.namespace} / {fact.key}</strong><small>Version {fact.version}{!fact.active ? " · Expired" : ""}</small>
              <p dir="auto">{fact.value}</p>
              {editingMemory === fact.id ? <>
                <label htmlFor="cw-memory-edit">Edit memory fact</label>
                <textarea id="cw-memory-edit" value={memoryDraft} maxLength={2000} rows={3}
                  disabled={working} onChange={event => setMemoryDraft(event.target.value)} />
                <div className="rukh-memory-actions">
                  <button type="button" onClick={() => { void saveMemory(fact); }} disabled={working || !memoryDraft.trim()}>Save edit</button>
                  <button type="button" onClick={() => { setEditingMemory(""); setMemoryDraft(""); }} disabled={working}>Cancel</button>
                </div>
              </> : <div className="rukh-memory-actions">
                <button type="button" disabled={working} onClick={() => { setEditingMemory(fact.id); setMemoryDraft(fact.value); }}>Edit</button>
                <button type="button" disabled={working} onClick={() => { void removeMemory(fact); }}>Delete</button>
              </div>}
            </li>)}</ul>
          </details>}
      </section>
    </aside>
    {mobilePanel && <button className="rukh-mobile-backdrop" type="button" aria-label="Close workspace panel" onClick={closeMobilePanel} />}
  </section>;
}
