import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import {
  CoworkerClient, WorkspaceError, type AssistantReply, type ConversationRecord,
  type ConversationMessageRecord, type ConversationActivityRecord, type WorkspaceManifest, type MemoryFact, type TaskBrief, type TaskBriefPreview, type ProjectDetail, CoworkerView,
} from "./client";
import ConversationReply from "./ConversationReply";
import ConversationRunStatus from "./ConversationRunStatus";
import NavigationIcon from "./WorkspaceNavigationIcon";
import CoworkerWelcome, { RukhCompanionMark } from "./CoworkerWelcome";
import ThemeToggle from "../components/ThemeToggle";
import WorkspaceNavigation from "./WorkspaceNavigation";
import VoiceDictation from "./VoiceDictation";
import { buildConversationJson, buildConversationMarkdown, conversationExportFilename } from "./conversationExport";
import "./conversation-enhancements.css";
import { RefreshOrder } from "./refreshOrder";
import { getInitialConversationId } from "../../../coworker/src/navigation.mjs";

function sourceLabel(source: Record<string, unknown>, manifest: WorkspaceManifest | null): string {
  const resourceId = typeof source.resource_id === "string" ? source.resource_id : "";
  const document = manifest?.documents.find(item => item.version_id === resourceId);
  if (document) return document.name;
  const artifact = manifest?.artifacts.find(item => item.artifact_id === resourceId);
  return artifact?.name ?? "Attached source";
}

/** CW-07: messages are not run authorizations; explicit dispatch is a separate click. */
export default function ConversationWorkspace({ client, openAgent, initialDraft = "", onInitialDraftChange, onNavigate, email, signOut, startEmpty = false }: {
  startEmpty?: boolean;
  email?: string;
  signOut?: () => void;
  client: CoworkerClient;
  openAgent: (runId: string) => void;
  initialDraft?: string;
  onInitialDraftChange?: (draft: string) => void;
  onNavigate?: (view: CoworkerView) => void;
}) {
  const projectId = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("project") : null;
  const projectNewChat = useRef(Boolean(projectId && !getInitialConversationId(typeof window !== "undefined" ? window.location.search : "")));
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [projectContext, setProjectContext] = useState<ProjectDetail | null>(null);
  const [projectContextLoading, setProjectContextLoading] = useState(Boolean(projectId));
  const [projectContextError, setProjectContextError] = useState("");
  const [selected, setSelected] = useState(() => startEmpty ? "" : typeof window !== "undefined" ? getInitialConversationId(window.location.search) ?? "" : "");
  const [messages, setMessages] = useState<ConversationMessageRecord[]>([]);
  const [activity, setActivity] = useState<ConversationActivityRecord[]>([]);
  const [manifest, setManifest] = useState<WorkspaceManifest | null>(null);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [editingTitle, setEditingTitle] = useState(false);
  const [renameDraft, setRenameDraft] = useState("");
  const [uploadingSource, setUploadingSource] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [manifestError, setManifestError] = useState("");
  const [memoryFacts, setMemoryFacts] = useState<MemoryFact[]>([]);
  const [memoryEnabled, setMemoryEnabled] = useState(false);
  const [memoryError, setMemoryError] = useState("");
  const [editingMemory, setEditingMemory] = useState("");
  const [memoryDraft, setMemoryDraft] = useState("");
  const [chatAvailable, setChatAvailable] = useState(false);
  const [chatMode, setChatMode] = useState(false);
  const [dictating, setDictating] = useState(false);
  const [replyingId, setReplyingId] = useState("");
  const [replyErrors, setReplyErrors] = useState<Record<string, string>>({});
  const replyController = useRef<AbortController | null>(null);
  const [listRevision, setListRevision] = useState(0);
  const [listReady, setListReady] = useState(false);
  const [search, setSearch] = useState("");
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const messageListRef = useRef<HTMLOListElement | null>(null);
  const followLatest = useRef(true);
  const firstMessage = useRef<{ fingerprint: string; key: string; conversation: ConversationRecord | null } | null>(null);
  const [title, setTitle] = useState("");
  const [draft, setDraft] = useState(initialDraft);
  const [working, setWorking] = useState(false);
  const [briefMessageId, setBriefMessageId] = useState("");
  const [briefDraft, setBriefDraft] = useState<TaskBrief | null>(null);
  const [briefPreview, setBriefPreview] = useState<TaskBriefPreview | null>(null);
  const [briefQuestion, setBriefQuestion] = useState("");
  const [steeringMessageId, setSteeringMessageId] = useState("");
  const [steeringDraft, setSteeringDraft] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [disabled, setDisabled] = useState(false);
  const createKey = useRef<{ fingerprint: string; key: string } | null>(null);
  const messageKey = useRef<{ fingerprint: string; key: string } | null>(null);
  const refreshOrder = useRef(new RefreshOrder());
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  useEffect(() => {
    setBriefMessageId(""); setBriefDraft(null); setBriefPreview(null); setBriefQuestion("");
  }, [selected, projectId]);
  const [mobilePanel, setMobilePanel] = useState<"conversations" | "context" | null>(null);
  const [contextOpen, setContextOpen] = useState(false);
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

  function toggleContext(event: { currentTarget: HTMLButtonElement }) {
    if (typeof window !== "undefined" && window.matchMedia("(max-width: 900px)").matches) {
      openMobilePanel("context", event.currentTarget);
    } else {
      setContextOpen(value => !value);
    }
  }

  useEffect(() => {
    if (!mobilePanel || typeof window === "undefined" || typeof document === "undefined") return;
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
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(min-width: 901px)");
    const closeOnDesktop = () => { if (media.matches) { setMobilePanel(null); setContextOpen(false); } };
    closeOnDesktop();
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", closeOnDesktop);
      return () => media.removeEventListener("change", closeOnDesktop);
    }
    media.addListener?.(closeOnDesktop);
    return () => media.removeListener?.(closeOnDesktop);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setListReady(false); setError("");
    client.conversations(controller.signal).then(({ items }) => {
      if (controller.signal.aborted) return;
      setDisabled(false);
      setListReady(true);
      setConversations(items);
      setSelected(current => items.some(item => item.id === current)
        ? current
        : (startEmpty || projectId || projectNewChat.current ? "" : items[0]?.id ?? ""));
    }).catch(cause => {
      if (controller.signal.aborted) return;
      setDisabled(cause instanceof WorkspaceError && [403, 404, 409].includes(cause.status));
      setError(cause instanceof Error ? cause.message : "Could not load conversations.");
    });
    return () => controller.abort();
  }, [client, listRevision]);

  useEffect(() => {
    if (!projectId) {
      setProjectContext(null);
      setProjectContextLoading(false);
      setProjectContextError("");
      return;
    }
    const controller = new AbortController();
    setProjectContext(null);
    setProjectContextLoading(true);
    setProjectContextError("");
    client.project(projectId, controller.signal).then(detail => {
      if (!controller.signal.aborted) setProjectContext(detail);
    }).catch(cause => {
      if (!controller.signal.aborted) {
        setProjectContextError(cause instanceof Error ? cause.message : "This project is unavailable.");
      }
    }).finally(() => {
      if (!controller.signal.aborted) setProjectContextLoading(false);
    });
    return () => controller.abort();
  }, [client, projectId]);

  useEffect(() => {
    if (!projectId || !projectContext || !selected) return;
    const linked = projectContext.resources.some(item =>
      item.resource_type === "conversation" && item.resource_id === selected
    );
    if (linked) return;
    selectedRef.current = "";
    setSelected("");
    setMessages([]);
    setActivity([]);
    setError("This conversation is not linked to the selected project.");
  }, [projectId, projectContext, selected]);

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

  useEffect(() => {
    const controller = new AbortController();
    if (typeof client.runtimeManifest !== "function") return;
    client.runtimeManifest(controller.signal).then(result => {
      if (!controller.signal.aborted) {
        const enabled = result.capabilities.conversation_replies === true;
        setChatAvailable(enabled); setChatMode(enabled);
      }
    }).catch(() => { if (!controller.signal.aborted) { setChatAvailable(false); setChatMode(false); } });
    return () => controller.abort();
  }, [client]);

  useEffect(() => () => { replyController.current?.abort(); }, [client, selected]);
  useEffect(() => { setEditingTitle(false); setRenameDraft(""); }, [selected]);

  const lastReply = messages[messages.length - 1]?.assistant_reply;
  useEffect(() => {
    const list = messageListRef.current;
    if (list && followLatest.current) list.scrollTop = list.scrollHeight;
  }, [messages.length, lastReply?.state, lastReply?.text, replyingId]);

  async function askForReply(item: ConversationMessageRecord) {
    followLatest.current = true;
    const id = item.conversation_id;
    const controller = new AbortController();
    replyController.current?.abort(); replyController.current = controller;
    setReplyingId(item.id); setReplyErrors(current => ({ ...current, [item.id]: "" }));
    const applyReply = (reply: AssistantReply) => {
      if (!controller.signal.aborted && selectedRef.current === id) {
        refreshOrder.current.invalidate();
        setMessages(current => current.map(message => message.id === item.id
          ? { ...message, assistant_reply: reply } : message));
      }
    };
    try {
      const reply = typeof client.replyToConversationMessageStream === "function"
        ? await client.replyToConversationMessageStream(id, item.id, item.sequence, applyReply, controller.signal, projectId ?? undefined)
        : await client.replyToConversationMessage(id, item.id, item.sequence, controller.signal, projectId ?? undefined);
      applyReply(reply);
    } catch (cause) {
      if (!controller.signal.aborted && selectedRef.current === id)
        setReplyErrors(current => ({ ...current, [item.id]: cause instanceof Error ? cause.message : "Could not load the AI reply." }));
    } finally {
      if (replyController.current === controller) setReplyingId("");
    }
  }

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
    followLatest.current = true;
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

  async function linkProjectConversation(conversationId: string) {
    if (!projectId) return;
    const project = await client.project(projectId);
    const linked = await client.linkProjectResource(project.id, "conversation", conversationId, project.revision);
    setProjectContext(linked);
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!listReady || disabled || working || !title.trim()) return;
    setWorking(true); setError(""); setNotice("");
    try {
      const normalizedTitle = title.trim();
      if (createKey.current?.fingerprint !== normalizedTitle)
        createKey.current = { fingerprint: normalizedTitle, key: crypto.randomUUID() };
      const record = await client.createConversation(normalizedTitle, createKey.current.key);
      await linkProjectConversation(record.id);
      const response = await client.conversations();
      setConversations(response.items);
      setSelected(record.id);
      firstMessage.current = null;
      setMobilePanel(null);
      setTitle("");
      setEditingTitle(false); setRenameDraft("");
      createKey.current = null;
      setNotice("Private conversation created.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Conversation creation failed.");
    } finally { setWorking(false); }
  }

  function startNew() {
    if (working) return;
    setSelected(""); setDraft(""); onInitialDraftChange?.(""); setSelectedSources([]); setError(""); setNotice("");
    setEditingTitle(false); setRenameDraft("");
    setMobilePanel(null); messageKey.current = null; firstMessage.current = null;
    composerRef.current?.focus();
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!listReady || disabled || working || dictating || !draft.trim()) return;
    setWorking(true); setError(""); setNotice("");
    try {
      const text = draft.trim();
      const sources = [...selectedSources];
      let conversationId = selected;
      if (!conversationId) {
        const fingerprint = JSON.stringify({ text, sources });
        if (firstMessage.current?.fingerprint !== fingerprint)
          firstMessage.current = { fingerprint, key: crypto.randomUUID(), conversation: null };
        const pending = firstMessage.current;
        if (!pending.conversation) {
          const record = await client.createConversation(Array.from(text).slice(0, 80).join(""), pending.key);
          pending.conversation = record;
        }
        conversationId = pending.conversation.id;
      }
      if (!selected) await linkProjectConversation(conversationId);
      const fingerprint = JSON.stringify({ conversation: conversationId, text, sources });
      if (messageKey.current?.fingerprint !== fingerprint)
        messageKey.current = { fingerprint, key: crypto.randomUUID() };
      const savedMessage = await client.appendConversationMessage(conversationId, text, messageKey.current.key, sources);
      // Admission succeeded. Keep this thread reachable even if a subsequent read fails.
      if (!selected) {
        const created = firstMessage.current!.conversation!;
        setConversations(current => current.some(item => item.id === conversationId) ? current : [
          created, ...current,
        ]);
        selectedRef.current = conversationId;
        setSelected(conversationId);
      }
      firstMessage.current = null;
      setDraft("");
      onInitialDraftChange?.("");
      setSelectedSources([]);
      messageKey.current = null;
      const currentManifest = await client.workspaceManifest().catch(() => null);
      if (currentManifest) setManifest(currentManifest);
      await reloadConversation(conversationId);
      if (chatMode && sources.length === 0) {
        setNotice("");
        await askForReply(savedMessage);
      } else setNotice(sources.length
        ? "Message saved with attachments. Use Start task to let the Agent read them; direct chat does not read attached files."
        : "Message saved. Choose Start task when you are ready.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Message could not be saved.");
    } finally { setWorking(false); }
  }

  async function proposeBrief(item: ConversationMessageRecord) {
    if (!selected || working) return;
    if (briefMessageId === item.id) {
      setBriefMessageId(""); setBriefDraft(null); setBriefPreview(null); setBriefQuestion("");
      return;
    }
    setBriefMessageId(item.id); setBriefPreview(null); setBriefQuestion(""); setBriefDraft(null);
    setWorking(true); setError("");
    try {
      const suggestion = await client.proposeConversationTaskBrief(selected, item.id, item.sequence, projectId);
      if (selectedRef.current !== selected) return;
      if (suggestion.state === "needs_input") {
        setBriefQuestion(suggestion.question ?? "Please clarify the requested task.");
      } else {
        setBriefDraft(suggestion.brief);
        setBriefPreview(suggestion);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Task brief proposal failed.");
      // Allow a manual review when the proposal provider is offline.
      setBriefDraft({ objective: item.text.slice(0, 4000), deliverables: ["Requested task output"],
        constraints: [], source_ids: item.selected_sources.map(source => String(source.resource_id)),
        output_language: "auto" });
    } finally { setWorking(false); }
  }

  function editBrief(patch: Partial<TaskBrief>) {
    setBriefDraft(current => current ? { ...current, ...patch } : null);
    setBriefPreview(null);
  }

  async function previewBrief(item: ConversationMessageRecord) {
    if (!selected || !briefDraft || working) return;
    setWorking(true); setError("");
    try {
      const preview = await client.previewConversationTaskBrief(
        selected, item.id, item.sequence, briefDraft, projectId);
      if (selectedRef.current === selected) setBriefPreview(preview);
    } catch (cause) {
      setBriefPreview(null);
      setError(cause instanceof Error ? cause.message : "Task brief could not be validated.");
    } finally { setWorking(false); }
  }

  async function dispatch(item: ConversationMessageRecord) {
    if (!selected || working || !briefDraft || !briefPreview?.canonical_digest
      || briefMessageId !== item.id) return;
    setWorking(true); setError(""); setNotice("");
    try {
      await client.dispatchConversationMessage(
        selected, item.id, item.sequence, projectId, briefDraft, briefPreview.canonical_digest);
      setBriefMessageId(""); setBriefDraft(null); setBriefPreview(null);
      await reloadConversation(selected);
      setNotice("Reviewed task started. Follow progress below or open Agent activity.");
    } catch (cause) {
      setBriefPreview(null);
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

  async function steer(item: ConversationMessageRecord, run: ConversationActivityRecord) {
    if (!selected || !selectedConversation || working || !steeringDraft.trim()) return;
    setWorking(true); setError(""); setNotice("");
    try {
      await client.steerConversationAgent(
        selected, item.id, selectedConversation.message_sequence,
        run.steering_revision, steeringDraft.trim(),
      );
      setSteeringMessageId(""); setSteeringDraft("");
      await reloadConversation(selected);
      setNotice("Instruction added. Rukh will apply it at the next planning checkpoint.");
    } catch (cause) {
      await reloadConversation(selected).catch(() => undefined);
      setError(cause instanceof Error ? cause.message : "Agent steering was not accepted.");
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
      setEditingTitle(false); setRenameDraft("");
      setNotice("Conversation deleted.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Deletion failed.");
    } finally { setWorking(false); }
  }

  const projectConversationIds = projectId && projectContext
    ? new Set(projectContext.resources.filter(item => item.resource_type === "conversation").map(item => item.resource_id))
    : null;
  const visibleConversations = projectId
    ? conversations.filter(item => projectConversationIds?.has(item.id))
    : conversations;
  const filteredConversations = visibleConversations.filter(item => item.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const hasGeneratingReply = messages.some(item => item.assistant_reply?.state === "generating");
  const composerDisabled = working || uploadingSource || Boolean(replyingId) || hasGeneratingReply || disabled || !listReady
    || projectContextLoading || Boolean(projectContextError);
  // Load the newest result eagerly; older histories may contain thousands of runs.
  const latestRunMessageId = [...messages].reverse().find(item => item.resource_links.some(link => link.resource_type === "agent_run"))?.id;
  const statusByMessage = new Map(activity.map(item => [item.message_id, item]));
  const selectedConversation = visibleConversations.find(item => item.id === selected);

  function beginRename() {
    if (!selectedConversation || working) return;
    setRenameDraft(selectedConversation.title);
    setEditingTitle(true);
    setError(""); setNotice("");
  }

  function cancelRename() {
    setEditingTitle(false);
    setRenameDraft("");
  }

  async function saveConversationTitle(event: FormEvent) {
    event.preventDefault();
    if (!selectedConversation || working || !renameDraft.trim()) return;
    setWorking(true); setError(""); setNotice("");
    try {
      const updated = await client.renameConversation(
        selectedConversation.id, renameDraft.trim(), selectedConversation.updated_at,
      );
      setConversations(current => current.map(item => item.id === updated.id ? updated : item));
      setEditingTitle(false); setRenameDraft("");
      setNotice("Conversation renamed.");
    } catch (cause) {
      if (cause instanceof WorkspaceError && cause.status === 409) {
        const latest = await client.conversations().catch(() => null);
        if (latest) setConversations(latest.items);
        setEditingTitle(false); setRenameDraft("");
        setError("This conversation changed in another tab. Its latest version has been reloaded; review it before renaming again.");
      } else {
        setError(cause instanceof Error ? cause.message : "Conversation rename failed.");
      }
    } finally { setWorking(false); }
  }

  async function uploadSource(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    setUploadingSource(true); setUploadError("");
    try {
      const uploaded = await client.upload(file);
      const refreshed = await client.workspaceManifest();
      setManifest(refreshed);
      const source = refreshed.documents.find(item => item.document_id === uploaded.id && item.available);
      if (!source) {
        setNotice("Uploaded " + uploaded.filename + ". It is not available as a source yet; refresh the context panel and try again.");
        return;
      }
      if (selectedSources.includes(source.version_id) || selectedSources.length < 5) {
        setSelectedSources(current => current.includes(source.version_id)
          ? current
          : current.length < 5 ? [...current, source.version_id] : current);
        setNotice("Uploaded " + uploaded.filename + ". Use Start task to let the Agent read this untrusted source; direct chat does not read attached files.");
      } else {
        setNotice("Uploaded " + uploaded.filename + ". Remove a selected source before attaching another; the limit is five.");
      }
    } catch (cause) {
      setUploadError(cause instanceof Error ? cause.message : "File upload failed.");
    } finally {
      setUploadingSource(false);
      input.value = "";
    }
  }

  function toggleSource(resourceId: string, checked: boolean) {
    setSelectedSources(current => checked
      ? (current.includes(resourceId) ? current : current.length < 5 ? [...current, resourceId] : current)
      : current.filter(id => id !== resourceId));
  }

  function downloadConversation(format: "markdown" | "json") {
    if (!selectedConversation) return;
    const exportedAt = new Date().toISOString();
    const body = format === "markdown"
      ? buildConversationMarkdown(selectedConversation, messages, source => sourceLabel(source, manifest), exportedAt)
      : buildConversationJson(selectedConversation, messages, exportedAt);
    const extension = format === "markdown" ? "md" : "json";
    const mime = format === "markdown" ? "text/markdown;charset=utf-8" : "application/json;charset=utf-8";
    const url = URL.createObjectURL(new Blob([body], { type: mime }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = conversationExportFilename(selectedConversation.title, extension);
    anchor.style.display = "none";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className={"rukh-conversation-workspace" + (contextOpen ? " rukh-context-open" : "")} aria-label="Coworker workspace">
    <div className="rukh-mobile-workspace-tools" aria-label="Workspace panels" aria-hidden={mobilePanel !== null ? true : undefined}>
      <button type="button" aria-label="Open navigation" aria-controls="rukh-conversation-list"
        aria-expanded={mobilePanel === "conversations"}
        onClick={event => openMobilePanel("conversations", event.currentTarget)}>
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M3 4.5h14M3 9.9h14M3 15.3h9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
        <strong>Coworker</strong>
      </button>
      <button type="button" aria-label="Open workspace context" aria-controls="rukh-context-panel"
        aria-expanded={mobilePanel === "context"}
        onClick={event => openMobilePanel("context", event.currentTarget)}>
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 5h12M4 10h8M4 15h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><circle cx="15" cy="10" r="2" stroke="currentColor" strokeWidth="1.3"/></svg>
        <span className="rukh-sr-only">Activity &amp; context</span>
      </button>
    </div>
    <aside ref={conversationPanelRef} id="rukh-conversation-list"
      className={"rukh-conversation-list" + (mobilePanel === "conversations" ? " rukh-mobile-panel-open" : "")}
      aria-label="Coworker navigation and conversations"
      role={mobilePanel === "conversations" ? "dialog" : undefined}
      aria-modal={mobilePanel === "conversations" ? true : undefined}
      aria-labelledby="rukh-conversations-heading"
      aria-hidden={mobilePanel === "context" ? true : undefined}>
      <div className="rukh-design-brand"><RukhCompanionMark /><strong>rukh<sup>AI</sup></strong></div>
      <button type="button" className="rukh-design-new" aria-label="New chat" disabled={composerDisabled} onClick={startNew}>+ New chat</button>
      <WorkspaceNavigation active="conversations" writingHref={selected || projectId ? "/writing?" + new URLSearchParams({ ...(selected ? { conversation: selected } : {}), ...(projectId ? { project: projectId } : {}) }) : "/writing"} onNavigate={view => { onNavigate?.(view); setMobilePanel(null); }} />
      <div className="rukh-panel-heading"><div><span className="cw-eyebrow">HISTORY</span><h2 id="rukh-conversations-heading">Conversations</h2></div>
        <div className="rukh-panel-heading-actions"><span className="rukh-count">{visibleConversations.length}</span>
          <button className="rukh-mobile-panel-close" ref={mobilePanel === "conversations" ? mobilePanelCloseRef : null}
            type="button" aria-label="Close conversations" onClick={closeMobilePanel}>×</button>
        </div>
      </div>

      {mobilePanel === "conversations" && error && <p className="cw-error" role="alert">{error}</p>}
      {disabled ? <p className="rukh-muted">Conversations are not enabled for this workspace. Existing work is unchanged.</p> : <>
        <label className="rukh-sr-only" htmlFor="cw-conversation-search">Search conversations</label>
        <input id="cw-conversation-search" className="rukh-conversation-search" type="search" aria-label="Search conversations"
          placeholder="Search conversations" value={search} onChange={event => setSearch(event.target.value)} />
        <form className="rukh-conversation-create" onSubmit={create}>
          <label className="rukh-sr-only" htmlFor="cw-conversation-title">New conversation title</label>
          <input id="cw-conversation-title" value={title} placeholder="Name a conversation…" minLength={1} maxLength={160}
            disabled={composerDisabled} onChange={event => setTitle(event.target.value)} required />
          <button type="submit" aria-label="Create private conversation" disabled={composerDisabled || !title.trim()}>+</button>
        </form>
        <ul className="rukh-conversation-items">
          {filteredConversations.map(item => <li key={item.id}>
            <button type="button" disabled={working} aria-pressed={selected === item.id} onClick={() => { setSelected(item.id); setDraft(""); onInitialDraftChange?.(""); setSelectedSources([]); setEditingTitle(false); setRenameDraft(""); messageKey.current = null; setMobilePanel(null); firstMessage.current = null; }}>
              <span className="rukh-conversation-item-title">{item.title}</span>
              <small>{new Date(item.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</small>
            </button>
          </li>)}
        </ul>
        {search.trim() && filteredConversations.length === 0 && <p className="rukh-muted" role="status">No conversations match your search.</p>}
        {!search.trim() && visibleConversations.length === 0 && <p className="rukh-muted">{projectId ? "No chats in this project yet." : "Your private conversations will appear here."}</p>}
      </>}
      <p className="rukh-panel-footnote">Messages are private. Agent work starts only when you choose Start task.</p>
      {email && <div className="rukh-design-account"><div><span className="rukh-design-account-avatar">{email[0].toUpperCase()}</span><span><strong title={email}>{email}</strong><small>Personal workspace</small></span></div><ThemeToggle />{signOut && <button type="button" className="cw-text-button" onClick={signOut}>Sign out</button>}</div>}
    </aside>

    <section aria-hidden={mobilePanel !== null ? true : undefined} className="rukh-conversation-thread" aria-label="Conversation">
      <header className={"rukh-thread-header" + (!selectedConversation ? " is-new" : "")}>
        {editingTitle && selectedConversation ? <form className="rukh-rename-form" aria-label="Rename conversation form" onSubmit={saveConversationTitle}>
          <label className="rukh-sr-only" htmlFor="cw-conversation-rename">Conversation title</label>
          <input id="cw-conversation-rename" aria-label="Conversation title" value={renameDraft} maxLength={160}
            disabled={working} autoFocus onChange={event => setRenameDraft(event.target.value)} />
          <div className="rukh-rename-actions">
            <button type="submit" aria-label="Save conversation name" disabled={working || !renameDraft.trim()}>Save</button>
            <button type="button" aria-label="Cancel conversation rename" disabled={working} onClick={cancelRename}>Cancel</button>
          </div>
        </form> : <div className="rukh-thread-title"><span className="cw-eyebrow">YOUR COWORKER</span><h2>{selectedConversation?.title ?? "Coworker"}</h2></div>}
        <div className="rukh-thread-tools">
          <button type="button" className="cw-text-button" aria-label="New conversation" disabled={composerDisabled} onClick={startNew}>+ New chat</button>
          {selectedConversation && !editingTitle && <button type="button" className="cw-text-button" aria-label="Rename conversation" onClick={beginRename} disabled={working}>Rename</button>}
          {selectedConversation && <details className="rukh-export-menu">
            <summary aria-label="Export conversation">Export</summary>
            <div className="rukh-export-menu-items">
              <button type="button" onClick={() => downloadConversation("markdown")}>Markdown (.md)</button>
              <button type="button" onClick={() => downloadConversation("json")}>JSON (.json)</button>
            </div>
          </details>}
          <button type="button" className="cw-text-button rukh-context-toggle" aria-label="Activity and context" aria-expanded={contextOpen || mobilePanel === "context"} onClick={toggleContext}>Activity &amp; context</button>
          {selectedConversation && <button type="button" className="cw-text-button" onClick={() => { void remove(); }} disabled={working}>Delete conversation</button>}
        </div>
      </header>
      {projectId && <section className="rukh-project-chat-context" aria-label="Project context" aria-busy={projectContextLoading}>
        <span className="rukh-project-chat-context-icon"><NavigationIcon name="folder" /></span>
        <div className="rukh-project-chat-context-copy">
          <span className="rukh-project-chat-context-eyebrow">PROJECT CHAT</span>
          <strong>{projectContext?.name ?? (projectContextLoading ? "Loading project…" : "Project unavailable")}</strong>
          {projectContext?.description && <p>{projectContext.description}</p>}
          <small>{projectContext?.description ? "Saved project instructions are applied to Rukh’s replies." : "No custom instructions saved. Edit this project to guide Rukh’s replies."} Linked files are not read automatically; attach a file and choose Start task.</small>
          {projectContextError && <span className="cw-error" role="alert">{projectContextError}</span>}
        </div>
        <button type="button" className="cw-text-button rukh-project-chat-back" onClick={() => onNavigate?.("projects")}>All projects</button>
      </section>}
      {error && <div className="rukh-thread-error"><p className="cw-error" role="alert">{error}</p>
        {!listReady && <button type="button" className="cw-text-button" aria-label="Retry conversations" onClick={() => setListRevision(value => value + 1)}>Retry loading conversations</button>}
      </div>}
      {notice && <p className="cw-notice" role="status">{notice}</p>}
      {disabled && <p className="rukh-muted" role="status">Conversations are not enabled for this workspace. Contact your workspace administrator.</p>}
      {messages.length === 0 ? <CoworkerWelcome disabled={composerDisabled} onChoose={prompt => { setDraft(prompt); onInitialDraftChange?.(prompt); composerRef.current?.focus(); }} /> :
          <ol ref={messageListRef} className="rukh-message-list" aria-label="Conversation messages"
            onScroll={event => { const list = event.currentTarget; followLatest.current = list.scrollHeight - list.scrollTop - list.clientHeight < 96; }}>
            {messages.map(item => {
              const run = statusByMessage.get(item.id);
              const linked = item.resource_links.find(link => link.resource_type === "agent_run");
              const activeRun = run && !["completed", "failed", "cancelled", "needs_input", "blocked"].includes(run.state);
              const canSteer = Boolean(activeRun && run?.runtime_version === 3
                && ["queued", "planning", "running"].includes(run.state) && !run.cancel_requested);
              const canDispatch = !linked && item.sequence === selectedConversation?.message_sequence;
              return <li className="rukh-message rukh-chat-turn" key={item.id}>
                <div className="rukh-user-message">
                <span className="rukh-message-author">You</span>
                <p dir="auto">{item.text}</p>
                {item.selected_sources.length > 0 && <ul className="rukh-message-sources" aria-label="Attached sources">
                  {item.selected_sources.map((source, sourceIndex) => <li key={String(source.resource_id ?? sourceIndex)}>{sourceLabel(source, manifest)}</li>)}
                </ul>}
                <div className="rukh-message-meta"><small>Message {item.sequence} · {new Date(item.created_at).toLocaleString()}</small>
                  {run && <span role="status">Agent {run.state}: {run.detail}</span>}
                </div>
                </div>
                {(activeRun || canDispatch || linked || chatAvailable) && <div className="rukh-message-actions">
                  {chatAvailable && !item.assistant_reply && item.sequence === selectedConversation?.message_sequence && <button type="button" disabled={composerDisabled || item.selected_sources.length > 0} onClick={() => { void askForReply(item); }}>Ask Rukh</button>}
                  {canSteer && <button type="button" aria-label="Steer Agent task" disabled={working}
                    onClick={() => { setSteeringMessageId(current => current === item.id ? "" : item.id); setSteeringDraft(""); }}>
                    {steeringMessageId === item.id ? "Close steering" : "Steer"}
                  </button>}
                  {activeRun && run && <button type="button" disabled={working} onClick={() => { void cancel(item, run); }}>Cancel Agent work</button>}
                  {canDispatch && <button type="button" disabled={working} onClick={() => { void proposeBrief(item); }}>
                    {briefMessageId === item.id ? "Close task brief" : "Start task"}
                  </button>}
                  {linked && <button type="button" onClick={() => openAgent(linked.resource_id)}>View Agent run</button>}
                </div>}
                {canDispatch && briefMessageId === item.id && <section className="rukh-task-brief-review" aria-label="Review task brief">
                  <h3>Review task before starting</h3>
                  {briefQuestion && <p role="status">{briefQuestion} Reply in the conversation to clarify.</p>}
                  {briefDraft && <form className="rukh-steer-form" onSubmit={event => {
                    event.preventDefault();
                    if (briefPreview?.canonical_digest) void dispatch(item);
                    else void previewBrief(item);
                  }}>
                    <label>Task objective
                      <textarea value={briefDraft.objective} maxLength={4000} rows={3} disabled={working}
                        onChange={event => editBrief({ objective: event.target.value })} />
                    </label>
                    <label>Constraints (one per line)
                      <textarea aria-label="Task constraints" value={briefDraft.constraints.join("\n")} rows={3} disabled={working}
                        onChange={event => editBrief({ constraints: event.target.value.split("\n").map(v => v.trim()).filter(Boolean) })} />
                    </label>
                    <label>Deliverables (one per line)
                      <textarea aria-label="Task deliverables" value={briefDraft.deliverables.join("\n")} rows={3} disabled={working}
                        onChange={event => editBrief({ deliverables: event.target.value.split("\n").map(v => v.trim()).filter(Boolean) })} />
                    </label>
                    <label>Output language
                      <input aria-label="Task output language" value={briefDraft.output_language} maxLength={35}
                        disabled={working} onChange={event => editBrief({ output_language: event.target.value })} />
                    </label>
                    {Array.from(new Map(messages.flatMap(message => message.selected_sources)
                      .filter(source => typeof source.resource_id === "string")
                      .map(source => [String(source.resource_id), source])).values()).map(source => {
                      const sourceId = String(source.resource_id);
                      return <label key={sourceId}>
                        <input type="checkbox" checked={briefDraft.source_ids.includes(sourceId)} disabled={working ||
                            (!briefDraft.source_ids.includes(sourceId) && briefDraft.source_ids.length >= 5)}
                          onChange={event => editBrief({ source_ids: event.target.checked
                            ? [...briefDraft.source_ids, sourceId] : briefDraft.source_ids.filter(id => id !== sourceId) })} />
                        {sourceLabel(source, manifest)}
                      </label>;
                    })}
                    {briefPreview?.canonical_digest && <p role="status">Validated preview: {briefPreview.canonical_digest.slice(0, 12)}…</p>}
                    <small>Edits invalidate the preview. Sources are untrusted data; this does not approve external actions.</small>
                    <button type="submit" disabled={working || !briefDraft.objective.trim() || briefDraft.deliverables.length === 0}>
                      {briefPreview?.canonical_digest ? "Confirm and start reviewed task" : "Validate task preview"}
                    </button>
                  </form>}
                </section>}
                {canSteer && steeringMessageId === item.id && run && <form className="rukh-steer-form" aria-label="Steer Agent form"
                  onSubmit={event => { event.preventDefault(); void steer(item, run); }}>
                  <label className="rukh-sr-only" htmlFor={`cw-steer-${item.id}`}>Instruction for Agent</label>
                  <textarea id={`cw-steer-${item.id}`} aria-label="Instruction for Agent" dir="auto" rows={2}
                    maxLength={4000} value={steeringDraft} disabled={working}
                    onChange={event => setSteeringDraft(event.target.value)}
                    placeholder="Add an instruction for the next planning checkpoint…" />
                  <div className="rukh-steer-form-actions">
                    <small>Applies to this Agent run only. It does not approve external actions.</small>
                    <button type="submit" disabled={working || !steeringDraft.trim()}>Send instruction</button>
                  </div>
                </form>}
                {(item.assistant_reply || replyingId === item.id || replyErrors[item.id]) && <ConversationReply reply={item.assistant_reply}
                  pending={replyingId === item.id} error={replyErrors[item.id]} disabled={composerDisabled} retry={() => { void askForReply(item); }} />}
                {linked && <ConversationRunStatus client={client} runId={linked.resource_id}
                  eager={Boolean(activeRun) || item.id === latestRunMessageId} />}
              </li>;
            })}
          </ol>}
        <form className="rukh-message-composer" aria-label="Message composer" onSubmit={send}>
          <label className="rukh-sr-only" htmlFor="cw-conversation-message">New message</label>
          <textarea ref={composerRef} id="cw-conversation-message" dir="auto" value={draft} minLength={1} maxLength={12000}
            rows={2} disabled={composerDisabled || dictating} required onChange={event => { setDraft(event.target.value); onInitialDraftChange?.(event.target.value); }}
            onKeyDown={event => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                event.preventDefault();
                if (!composerDisabled && !dictating && draft.trim()) event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Ask Rukh to do something…" />
          <div className="rukh-composer-controls">
            <button type="button" className="rukh-design-attach" aria-label="Attach files" disabled={composerDisabled} onClick={toggleContext}><NavigationIcon name="plus" /><span>Attach files</span></button>
            {selectedSources.length > 0 && <span className="rukh-selected-source-count">{selectedSources.length} attached · Start task to use files</span>}
            <details className="rukh-composer-tools"><summary>Tools</summary><div>
              {chatAvailable && <div className="rukh-chat-mode" aria-label="Message mode">
                <button type="button" aria-pressed={chatMode} disabled={composerDisabled} onClick={() => setChatMode(true)}>Chat with Rukh</button>
                <button type="button" aria-pressed={!chatMode} disabled={composerDisabled} onClick={() => setChatMode(false)}>Save only</button>
              </div>}
              <p>Start task separately to use attached files.</p>
            </div></details>
            <VoiceDictation key={selected} draft={draft} onDraftChange={setDraft} onListeningChange={setDictating} disabled={composerDisabled} compact />
            {replyingId && <button type="button" className="rukh-stop-stream" onClick={() => { replyController.current?.abort(); setNotice("Stopped receiving the response. A saved reply may still finish; reopen this conversation to recover it."); }}>Stop response</button>}
            <button className="rukh-design-send" type="submit" aria-label={replyingId ? "Replying…" : working ? "Saving…" : chatMode && !selectedSources.length ? "Send message" : "Save message"} disabled={composerDisabled || dictating || !draft.trim()}><NavigationIcon name="arrow" /></button>
          </div>
        </form>
        <p className="rukh-composer-hint">{chatMode ? "Enter to send" : "Enter to save"} · Shift + Enter for a new line · {selectedSources.length ? "Direct chat does not read attached files; use Start task." : "Start task separately."}</p>
    </section>

    <aside ref={contextPanelRef} id="rukh-context-panel" hidden={!contextOpen && mobilePanel !== "context"}
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
          <div className="rukh-context-upload">
            <label htmlFor="cw-source-upload">Upload a source file</label>
            <input id="cw-source-upload" type="file" aria-label="Upload a source file"
              accept=".txt,.docx,.pdf" disabled={working || uploadingSource}
              onChange={event => { void uploadSource(event); }} />
            <small>TXT, DOCX or PDF · maximum 8 MB</small>
          </div>
          {uploadError && <p className="cw-error" role="alert">{uploadError}</p>}
          {manifest.truncated.documents && <p className="rukh-muted">Only the first document page is shown.</p>}
          {manifest.documents.filter(doc => doc.available).length === 0 ? <p className="rukh-muted">No available documents yet.</p> :
            <div className="rukh-source-list">
              {manifest.documents.filter(doc => doc.available).map(doc =>
                <label key={doc.version_id}>
                  <input type="checkbox" aria-label={"Attach source file " + doc.name}
                    checked={selectedSources.includes(doc.version_id)}
                    disabled={working || uploadingSource || (!selectedSources.includes(doc.version_id) && selectedSources.length >= 5)}
                    onChange={event => toggleSource(doc.version_id, event.target.checked)} />
                  <span><strong>{doc.name}</strong><small>Version {doc.version} · {doc.sha256.slice(0, 10)}</small></span>
                </label>
              )}
            </div>}
          {manifest.artifacts.filter(artifact => artifact.available).length > 0 && <>
            <h4 className="rukh-source-group-heading">Generated artifacts</h4>
            <div className="rukh-source-list">
              {manifest.artifacts.filter(artifact => artifact.available).map(artifact =>
                <label key={artifact.artifact_id}>
                  <input type="checkbox" aria-label={"Attach generated artifact " + artifact.name}
                    checked={selectedSources.includes(artifact.artifact_id)}
                    disabled={working || uploadingSource || (!selectedSources.includes(artifact.artifact_id) && selectedSources.length >= 5)}
                    onChange={event => toggleSource(artifact.artifact_id, event.target.checked)} />
                  <span><strong>{artifact.name}</strong><small>Generated artifact · {artifact.sha256.slice(0, 10)}</small></span>
                </label>
              )}
            </div>
          </>}
          {manifest.truncated.artifacts && <p className="rukh-muted">Only the first generated-artifact page is shown.</p>}
          <p className="rukh-panel-footnote">Selected sources are untrusted inputs, not instructions or permissions. Maximum five per message. Direct chat does not read attached files; use Start task to let the Agent process them.</p>
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
    {mobilePanel && <button className="rukh-mobile-backdrop" type="button" aria-hidden="true" tabIndex={-1} onClick={closeMobilePanel} />}
  </section>;
}
